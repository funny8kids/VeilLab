from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import (
    get_db,
    get_indexer_client,
    get_local_rpc_client,
    get_request_id,
    get_settings,
)
from ..errors import ApiError
from ..ids import new_id
from ..indexer_client import IndexerClient, IndexerError
from ..local_chain import (
    GROTH16_PROOF_ENCODING,
    LOCAL_CHAIN_ID,
    LOCAL_CHAIN_LABEL,
    LocalRpcClient,
    LocalRpcError,
    IndexerMismatch,
    encode_deposit_calldata,
    encode_withdraw_calldata,
    normalize_address,
    normalize_hex32,
    normalize_proof,
    wait_for_indexed_deposit,
    wait_for_indexed_withdrawal,
    wait_for_transaction_receipt,
)
from ..local_read import (
    GROTH16_WARNING,
    LOCAL_POOL_IDS,
    verifier_kind_value,
)
from ..models import (
    ComplianceCheck,
    Deposit,
    DepositIntent,
    LocalDepositBroadcast,
    LocalWithdrawalBroadcast,
    Nullifier,
    Pool,
    Withdrawal,
    WithdrawalQuote,
    iso_z,
    utcnow,
)
from ..presenters import deposit_view
from ..schemas import LocalDepositRequest, LocalWithdrawalRequest
from ..services.audit import append_audit
from ..services.compliance import hash_address, require_allowed

router = APIRouter(tags=["local"])


def _existing_deposit(db: Session, intent: DepositIntent) -> Deposit | None:
    if intent.compliance_check_id is None:
        return None
    return db.execute(
        select(Deposit)
        .where(
            Deposit.pool_id == intent.pool_id,
            Deposit.compliance_check_id == intent.compliance_check_id,
            Deposit.is_canonical.is_(True),
        )
        .order_by(Deposit.block_number.desc(), Deposit.log_index.desc())
        .limit(1)
    ).scalar_one_or_none()


def _local_result(
    db: Session,
    deposit: Deposit,
    pool: Pool,
    *,
    intent_id: str,
    indexer: IndexerClient,
) -> dict:
    result = deposit_view(db, deposit, pool.chain_id)
    lag = None
    confirmations = 1
    finality = "unknown"
    try:
        health = indexer.health()
        lag = health.get("lag")
        tip = health.get("tip_block")
        threshold = int(health.get("finality_confirmations") or 1)
        if tip is not None:
            confirmations = max(0, int(tip) - int(deposit.block_number) + 1)
            finality = (
                "final" if confirmations >= threshold else "optimistic"
            )
    except IndexerError:
        # The deposit is already persisted; a health read failure only hides
        # lag, it does not change the confirmed public chain fields.
        pass
    result.update(
        {
            "mock": False,
            "chain_source": "indexer",
            "local_chain": LOCAL_CHAIN_LABEL,
            "intent_id": intent_id,
            "tx_hash": deposit.tx_hash,
            "block_number": deposit.block_number,
            "indexer_lag": lag,
            "confirmations": confirmations,
            "finality": finality,
        }
    )
    return result


def _proof_digest(proof: str) -> str:
    """Stable digest for replay checks. Proof bytes themselves are not stored."""

    return "0x" + hashlib.sha256(bytes.fromhex(proof[2:])).hexdigest()


def _withdrawal_confirmation(
    indexer: IndexerClient,
    withdrawal: Withdrawal,
    item: dict | None,
) -> tuple[int, str]:
    confirmations = None if item is None else item.get("confirmations")
    finality = None if item is None else item.get("finality")
    threshold = 1
    if confirmations is None or finality in {None, "unknown"}:
        try:
            health = indexer.health()
            tip = health.get("tip_block")
            threshold = int(health.get("finality_confirmations") or 1)
            if tip is not None and withdrawal.block_number is not None:
                confirmations = max(
                    0, int(tip) - int(withdrawal.block_number) + 1
                )
        except IndexerError:
            pass
    if confirmations is None:
        confirmations = 1
    if finality in {None, "unknown"}:
        finality = "final" if int(confirmations) >= threshold else "optimistic"
    return int(confirmations), str(finality)


def _local_withdrawal_result(
    db: Session,
    withdrawal: Withdrawal,
    pool: Pool,
    settings: Settings,
    indexer: IndexerClient,
    *,
    item: dict | None = None,
) -> dict:
    confirmations, finality = _withdrawal_confirmation(
        indexer, withdrawal, item
    )
    return {
        "withdrawal_id": withdrawal.id,
        "pool_id": pool.id,
        "status": "confirmed",
        "tx_hash": withdrawal.tx_hash,
        "block_number": withdrawal.block_number,
        "block_hash": withdrawal.block_hash,
        "nullifier": withdrawal.nullifier_hash,
        "recipient": withdrawal.recipient_address,
        "fee_wei": str(withdrawal.relayer_fee_wei),
        "confirmations": confirmations,
        "finality": finality,
        "local_chain": LOCAL_CHAIN_LABEL,
        "chain_source": "indexer",
        "verifier_kind": verifier_kind_value(settings),
        "proof_encoding": GROTH16_PROOF_ENCODING,
        "mock": False,
        "confirmed_at": iso_z(withdrawal.confirmed_at),
        "warning": (
            GROTH16_WARNING
            if settings.local_verifier_kind == "groth16"
            else (
                "LOCAL ANVIL DEV BRIDGE. The configured local verifier is "
                "labelled as a mock; this response is not evidence of real ZK "
                "verification. No real funds."
            )
        ),
    }


def _canonical_db_withdrawal(
    db: Session, pool_id: str, nullifier_hash: str
) -> Withdrawal | None:
    return db.execute(
        select(Withdrawal)
        .where(
            Withdrawal.pool_id == pool_id,
            Withdrawal.nullifier_hash == nullifier_hash,
            Withdrawal.is_canonical.is_(True),
        )
        .order_by(Withdrawal.block_number.desc(), Withdrawal.log_index.desc())
        .limit(1)
    ).scalar_one_or_none()


@router.post("/local/deposits", status_code=201)
def create_local_deposit(
    body: LocalDepositRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
    rpc: LocalRpcClient = Depends(get_local_rpc_client),
    request_id: str = Depends(get_request_id),
):
    """Dev-only Anvil deposit bridge.

    It validates the existing deposit intent, optionally asks Anvil to send
    ``deposit(bytes32 commitment)`` from the configured unlocked dev account,
    then waits for the indexer to expose the canonical deposit. It never
    accepts a private key and never stores note material.
    """

    if settings.mode != "local" or settings.chain_id != LOCAL_CHAIN_ID:
        raise ApiError(
            404,
            "LOCAL_ONLY",
            "The local Anvil deposit bridge is only available in local mode.",
        )

    intent = db.get(DepositIntent, body.intent_id)
    if intent is None:
        raise ApiError(404, "INTENT_NOT_FOUND", "Unknown deposit intent id.")
    pool = db.get(Pool, intent.pool_id)
    if pool is None:
        raise ApiError(404, "POOL_NOT_FOUND", "Unknown pool id.")
    commitment = body.commitment.lower()

    if intent.status == "consumed":
        existing = _existing_deposit(db, intent)
        if existing is not None:
            if existing.commitment.lower() != commitment:
                raise ApiError(
                    409,
                    "COMMITMENT_MISMATCH",
                    "This deposit intent was consumed with a different commitment.",
                )
            return JSONResponse(
                status_code=200,
                content=_local_result(
                    db,
                    existing,
                    pool,
                    intent_id=intent.id,
                    indexer=indexer,
                ),
            )
        raise ApiError(
            409,
            "INTENT_CONSUMED",
            "This deposit intent has already been consumed.",
        )

    if pool.status != "active":
        raise ApiError(409, "POOL_PAUSED", "This pool is not active.")
    if intent.status in {"expired", "blocked"}:
        raise ApiError(
            409, "INTENT_EXPIRED", "This deposit intent is no longer usable."
        )
    if intent.expires_at <= utcnow():
        intent.status = "expired"
        db.commit()
        raise ApiError(409, "INTENT_EXPIRED", "This deposit intent has expired.")
    if intent.commitment is not None and intent.commitment.lower() != commitment:
        raise ApiError(
            422,
            "COMMITMENT_MISMATCH",
            "The commitment does not match the deposit intent.",
        )

    check = db.get(ComplianceCheck, intent.compliance_check_id)
    try:
        require_allowed(check, expected_amount_wei=pool.denomination_wei)
    except ApiError as exc:
        if exc.code == "COMPLIANCE_EXPIRED":
            intent.status = "expired"
            db.commit()
        raise

    try:
        calldata = encode_deposit_calldata(commitment)
    except ValueError as exc:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "commitment must be exactly one public 32-byte word.",
        ) from exc

    if not settings.local_auto_deposit:
        raise ApiError(
            409,
            "LOCAL_DEPOSIT_DISABLED",
            (
                "Automatic local deposit broadcasting is disabled. Submit the "
                "deposit transaction from your own wallet."
            ),
            extra={
                "contract_address": settings.contract_address,
                "denomination_wei": str(pool.denomination_wei),
                "calldata": calldata,
                "instruction": "submit the deposit from your own wallet",
                "local_chain": LOCAL_CHAIN_LABEL,
            },
        )

    broadcast = db.get(LocalDepositBroadcast, intent.id)
    if broadcast is not None:
        if broadcast.commitment.lower() != commitment:
            raise ApiError(
                409,
                "COMMITMENT_MISMATCH",
                "This deposit intent was broadcast with a different commitment.",
            )
        tx_hash = broadcast.tx_hash
    else:
        try:
            tx_hash = rpc.send_transaction(
                from_address=settings.local_from_address,
                to_address=settings.contract_address,
                value_wei=int(pool.denomination_wei),
                data=calldata,
            )
        except LocalRpcError as exc:
            raise ApiError(
                exc.status_code,
                exc.code,
                exc.detail,
                extra={
                    "local_chain": LOCAL_CHAIN_LABEL,
                    "contract_address": settings.contract_address,
                    "intent_id": intent.id,
                },
            ) from exc
        # Persist the broadcast before polling. If confirmation times out, a
        # retry polls this tx instead of sending a second deposit.
        db.add(
            LocalDepositBroadcast(
                intent_id=intent.id,
                pool_id=pool.id,
                commitment=commitment,
                tx_hash=tx_hash,
            )
        )
        db.commit()

    try:
        item, poll_error = wait_for_indexed_deposit(
            indexer,
            pool.id,
            tx_hash=tx_hash,
            commitment=commitment,
            timeout_seconds=settings.local_deposit_timeout_seconds,
        )
    except IndexerMismatch as exc:
        raise ApiError(
            502,
            "INDEXER_MISMATCH",
            str(exc),
            extra={
                "tx_hash": tx_hash,
                "local_chain": LOCAL_CHAIN_LABEL,
                "intent_id": intent.id,
            },
        ) from exc

    if item is None:
        extra = {
            "tx_hash": tx_hash,
            "local_chain": LOCAL_CHAIN_LABEL,
            "intent_id": intent.id,
            "pool_id": pool.id,
            "status": "submitted",
        }
        if poll_error is not None:
            extra["indexer_error"] = {
                "code": poll_error.code,
                "detail": poll_error.detail,
            }
        raise ApiError(
            504,
            "INDEXER_CONFIRMATION_TIMEOUT",
            (
                "The deposit transaction was broadcast but the indexer did "
                "not expose a matching canonical deposit before the timeout."
            ),
            extra=extra,
        )

    if item["commitment"].lower() != commitment:
        raise ApiError(
            502,
            "INDEXER_MISMATCH",
            "The indexed deposit has a different commitment.",
            extra={"tx_hash": tx_hash, "intent_id": intent.id},
        )
    if item.get("pool_key") not in {None, pool.id}:
        raise ApiError(
            502,
            "INDEXER_MISMATCH",
            "The indexed deposit belongs to a different pool.",
            extra={"tx_hash": tx_hash, "intent_id": intent.id},
        )

    existing = db.execute(
        select(Deposit)
        .where(
            Deposit.tx_hash == tx_hash,
            Deposit.log_index == int(item["log_index"]),
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.pool_id != pool.id
            or existing.commitment.lower() != commitment
        ):
            raise ApiError(
                502,
                "INDEXER_MISMATCH",
                "The indexed deposit conflicts with local canonical state.",
                extra={"tx_hash": tx_hash, "intent_id": intent.id},
            )
        deposit = existing
    else:
        leaf_existing = db.execute(
            select(Deposit)
            .where(
                Deposit.pool_id == pool.id,
                Deposit.leaf_index == int(item["leaf_index"]),
                Deposit.is_canonical.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if leaf_existing is not None and leaf_existing.tx_hash != tx_hash:
            raise ApiError(
                502,
                "INDEXER_MISMATCH",
                "The indexed leaf index conflicts with local canonical state.",
                extra={"tx_hash": tx_hash, "intent_id": intent.id},
            )
        try:
            confirmed_at = datetime.fromtimestamp(
                int(item["block_timestamp"]), tz=timezone.utc
            ).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError):
            confirmed_at = utcnow()
        deposit = Deposit(
            id=new_id("dep"),
            pool_id=pool.id,
            commitment=commitment,
            leaf_index=int(item["leaf_index"]),
            tx_hash=tx_hash,
            block_number=int(item["block_number"]),
            block_hash=item["block_hash"].lower(),
            log_index=int(item["log_index"]),
            depositor_address=None,
            compliance_check_id=intent.compliance_check_id,
            status="confirmed",
            is_canonical=True,
            confirmed_at=confirmed_at,
            created_at=utcnow(),
        )
        db.add(deposit)

    intent.status = "consumed"
    append_audit(
        db,
        action="deposit.local_chain_recorded",
        resource_type="deposit",
        resource_id=deposit.id,
        actor_type="local_chain",
        actor_id=LOCAL_CHAIN_LABEL,
        decision="confirmed",
        request_id=request_id,
        metadata={
            "pool_id": pool.id,
            "tx_hash": tx_hash,
            "leaf_index": deposit.leaf_index,
            "commitment": commitment,
            "chain_id": settings.chain_id,
            "local_chain": LOCAL_CHAIN_LABEL,
            "mock": False,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            502,
            "INDEXER_MISMATCH",
            "The indexed deposit conflicts with local canonical state.",
            extra={"tx_hash": tx_hash, "intent_id": intent.id},
        ) from exc

    return JSONResponse(
        status_code=201,
        content=_local_result(
            db,
            deposit,
            pool,
            intent_id=intent.id,
            indexer=indexer,
        ),
    )


@router.post("/local/withdrawals", status_code=201)
def create_local_withdrawal(
    body: LocalWithdrawalRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
    rpc: LocalRpcClient = Depends(get_local_rpc_client),
    request_id: str = Depends(get_request_id),
):
    """Dev-only Anvil withdrawal bridge for a real Groth16 proof.

    The endpoint accepts only a 256-byte Groth16 proof and the public signals
    already bound to an existing quote. It never accepts or stores note,
    witness or secret material. With auto-withdraw disabled it returns the
    calldata for a caller-owned wallet instead of sending a transaction.
    """

    if settings.mode != "local" or settings.chain_id != LOCAL_CHAIN_ID:
        raise ApiError(
            404,
            "LOCAL_ONLY",
            "The local Anvil withdrawal bridge is only available in local mode.",
        )

    quote = db.get(WithdrawalQuote, body.quote_id)
    if quote is None:
        raise ApiError(404, "QUOTE_NOT_FOUND", "Unknown withdrawal quote id.")
    pool = db.get(Pool, quote.pool_id)
    if pool is None:
        raise ApiError(404, "POOL_NOT_FOUND", "Unknown pool id.")

    try:
        proof = normalize_proof(body.proof)
    except ValueError as exc:
        raise ApiError(
            422,
            "INVALID_PROOF",
            "The proof must be exactly 256 ABI-encoded Groth16 bytes.",
            extra={
                "proof_encoding": GROTH16_PROOF_ENCODING,
                "local_chain": LOCAL_CHAIN_LABEL,
            },
        ) from exc
    try:
        root = normalize_hex32(body.root, name="root")
        nullifier = normalize_hex32(body.nullifier, name="nullifier")
        recipient = normalize_address(body.recipient)
    except ValueError as exc:
        raise ApiError(
            422,
            "INVALID_PUBLIC_SIGNALS",
            "root, nullifier and recipient must be canonical public values.",
            extra={"local_chain": LOCAL_CHAIN_LABEL},
        ) from exc
    if not body.relayer_fee_wei.isdigit():
        raise ApiError(
            422,
            "INVALID_PUBLIC_SIGNALS",
            "relayer_fee_wei must be an unsigned integer string.",
            extra={"local_chain": LOCAL_CHAIN_LABEL},
        )
    relayer_fee = int(body.relayer_fee_wei)

    if quote.recipient_address.lower() != recipient:
        raise ApiError(
            422,
            "INVALID_PUBLIC_SIGNALS",
            "The recipient does not match the withdrawal quote.",
            extra={"field": "recipient", "quote_id": quote.id},
        )
    if relayer_fee != int(quote.relayer_fee_wei):
        raise ApiError(
            422,
            "INVALID_PUBLIC_SIGNALS",
            "The relayer fee does not match the withdrawal quote.",
            extra={"field": "relayer_fee_wei", "quote_id": quote.id},
        )

    proof_digest = _proof_digest(proof)
    broadcast = db.get(LocalWithdrawalBroadcast, quote.id)
    if broadcast is not None:
        if (
            broadcast.nullifier_hash.lower() != nullifier
            or broadcast.recipient_address.lower() != recipient
            or int(broadcast.relayer_fee_wei) != relayer_fee
            or (
                broadcast.proof_sha256 is not None
                and broadcast.proof_sha256 != proof_digest
            )
        ):
            raise ApiError(
                409,
                "QUOTE_CONSUMED",
                "This withdrawal quote was already used for a different proof.",
                extra={"quote_id": quote.id},
            )
        if broadcast.withdrawal_id is not None:
            stored = db.get(Withdrawal, broadcast.withdrawal_id)
            if stored is not None:
                return JSONResponse(
                    status_code=200,
                    content=_local_withdrawal_result(
                        db,
                        stored,
                        pool,
                        settings,
                        indexer,
                    ),
                )

    if quote.status == "expired" or quote.expires_at <= utcnow():
        quote.status = "expired"
        db.commit()
        raise ApiError(409, "QUOTE_EXPIRED", "The withdrawal quote has expired.")
    if pool.id not in LOCAL_POOL_IDS:
        raise ApiError(
            409,
            "POOL_RETIRED",
            "This pool is not configured for the local Anvil deployment.",
        )
    if pool.status != "active":
        raise ApiError(409, "POOL_PAUSED", "This pool is not active.")

    if broadcast is None:
        if quote.status == "submitted":
            raise ApiError(
                409,
                "QUOTE_CONSUMED",
                "This withdrawal quote has already been used.",
                extra={"quote_id": quote.id},
            )

        check = db.get(ComplianceCheck, quote.compliance_check_id)
        try:
            require_allowed(check, expected_amount_wei=pool.denomination_wei)
        except ApiError as exc:
            if exc.code == "COMPLIANCE_EXPIRED":
                quote.status = "expired"
                db.commit()
            raise
        assert check is not None
        if (
            check.pool_id != pool.id
            or check.address_hash != hash_address(settings, recipient)
        ):
            raise ApiError(
                409,
                "COMPLIANCE_EXPIRED",
                "The compliance decision is bound to a different pool or recipient.",
            )

        try:
            existing = indexer.get_withdrawal(nullifier, pool_id=pool.id)
        except IndexerError as exc:
            raise ApiError(
                exc.status_code,
                exc.code,
                exc.detail,
                extra={
                    "pool_id": pool.id,
                    "local_chain": LOCAL_CHAIN_LABEL,
                    "chain_data_status": "unavailable",
                },
            ) from exc
        if existing is not None:
            raise ApiError(
                409,
                "NULLIFIER_SPENT",
                "This nullifier is already spent in this pool.",
                extra={
                    "withdrawal": existing,
                    "existing_withdrawal": existing,
                    "pool_id": pool.id,
                    "local_chain": LOCAL_CHAIN_LABEL,
                },
            )
        stored_same_nullifier = _canonical_db_withdrawal(
            db, pool.id, nullifier
        )
        if stored_same_nullifier is not None:
            existing_view = _local_withdrawal_result(
                db,
                stored_same_nullifier,
                pool,
                settings,
                indexer,
            )
            raise ApiError(
                409,
                "NULLIFIER_SPENT",
                "This nullifier is already spent in this pool.",
                extra={
                    "withdrawal": existing_view,
                    "existing_withdrawal": existing_view,
                    "pool_id": pool.id,
                    "local_chain": LOCAL_CHAIN_LABEL,
                },
            )

        try:
            roots = indexer.get_roots(pool.id, limit=1000)
        except IndexerError as exc:
            raise ApiError(
                exc.status_code,
                exc.code,
                exc.detail,
                extra={
                    "pool_id": pool.id,
                    "local_chain": LOCAL_CHAIN_LABEL,
                    "chain_data_status": "unavailable",
                },
            ) from exc
        current_root = roots.get("current_root")
        ready_roots: list[str] = []
        for value in [current_root, *[item["root"] for item in roots["items"]]]:
            if isinstance(value, str) and value.lower() not in ready_roots:
                ready_roots.append(value.lower())
        if not ready_roots:
            raise ApiError(
                409,
                "UNKNOWN_ROOT",
                "The indexer has no canonical root history for this pool.",
                extra={
                    "pool_id": pool.id,
                    "current_root": None,
                    "ready_roots": [],
                    "local_chain": LOCAL_CHAIN_LABEL,
                },
            )
        if root not in ready_roots:
            raise ApiError(
                409,
                "ROOT_STALE",
                "The proof root is outside the accepted indexer root history.",
                extra={
                    "pool_id": pool.id,
                    "current_root": current_root,
                    "ready_roots": ready_roots,
                    "local_chain": LOCAL_CHAIN_LABEL,
                },
            )

        try:
            calldata = encode_withdraw_calldata(
                proof,
                root,
                nullifier,
                recipient,
                relayer_fee,
                pool.id,
            )
        except ValueError as exc:
            raise ApiError(
                422,
                "INVALID_PUBLIC_SIGNALS",
                "The withdrawal public signals could not be ABI-encoded.",
                extra={"local_chain": LOCAL_CHAIN_LABEL},
            ) from exc

        if not settings.local_auto_withdraw:
            raise ApiError(
                409,
                "LOCAL_WITHDRAWAL_DISABLED",
                (
                    "Automatic local withdrawal broadcasting is disabled. "
                    "Submit the withdrawal transaction from your own wallet."
                ),
                extra={
                    "contract_address": settings.contract_address,
                    "calldata": calldata,
                    "instruction": "submit the withdrawal from your own wallet",
                    "local_chain": LOCAL_CHAIN_LABEL,
                    "pool_id": pool.id,
                    "quote_id": quote.id,
                    "verifier_kind": verifier_kind_value(settings),
                },
            )

        try:
            tx_hash = rpc.send_transaction(
                from_address=settings.local_from_address,
                to_address=settings.contract_address,
                value_wei=0,
                data=calldata,
            )
        except LocalRpcError as exc:
            raise ApiError(
                exc.status_code,
                exc.code,
                exc.detail,
                extra={
                    "local_chain": LOCAL_CHAIN_LABEL,
                    "contract_address": settings.contract_address,
                    "pool_id": pool.id,
                    "quote_id": quote.id,
                },
            ) from exc

        broadcast = LocalWithdrawalBroadcast(
            quote_id=quote.id,
            pool_id=pool.id,
            nullifier_hash=nullifier,
            tx_hash=tx_hash,
            recipient_address=recipient,
            relayer_fee_wei=relayer_fee,
            proof_sha256=proof_digest,
        )
        db.add(broadcast)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            existing_broadcast = db.get(LocalWithdrawalBroadcast, quote.id)
            if (
                existing_broadcast is None
                or existing_broadcast.nullifier_hash.lower() != nullifier
                or existing_broadcast.proof_sha256 != proof_digest
            ):
                raise ApiError(
                    409,
                    "QUOTE_CONSUMED",
                    "This withdrawal quote was consumed by a concurrent request.",
                    extra={"quote_id": quote.id},
                ) from exc
            broadcast = existing_broadcast
            tx_hash = broadcast.tx_hash
    else:
        tx_hash = broadcast.tx_hash

    # Anvil mines immediately. A receipt check reports a revert as a clear
    # 502 instead of waiting for an indexer event that can never arrive.
    try:
        receipt = wait_for_transaction_receipt(
            rpc,
            tx_hash,
            timeout_seconds=min(
                2.0, max(0.0, settings.local_withdrawal_timeout_seconds)
            ),
        )
    except LocalRpcError:
        # Receipt lookup is a diagnostic aid; an RPC that does not support it
        # must not break the indexer confirmation path.
        receipt = None
    if receipt is not None and receipt["status"] == 0:
        # The transaction did not spend the nullifier. Drop the broadcast so
        # the quote stays usable for a corrected proof/root.
        db.delete(broadcast)
        db.commit()
        raise ApiError(
            502,
            "WITHDRAWAL_REVERTED",
            (
                "The local Anvil transaction reverted. The quote was not "
                "consumed and no withdrawal was recorded."
            ),
            extra={
                "tx_hash": tx_hash,
                "quote_id": quote.id,
                "pool_id": pool.id,
                "status": "reverted",
                "block_number": receipt.get("block_number"),
                "block_hash": receipt.get("block_hash"),
                "gas_used": receipt.get("gas_used"),
                "local_chain": LOCAL_CHAIN_LABEL,
            },
        )

    try:
        item, poll_error = wait_for_indexed_withdrawal(
            indexer,
            pool.id,
            tx_hash=tx_hash,
            nullifier=nullifier,
            recipient=recipient,
            relayer_fee_wei=relayer_fee,
            timeout_seconds=settings.local_withdrawal_timeout_seconds,
        )
    except IndexerMismatch as exc:
        raise ApiError(
            502,
            "INDEXER_MISMATCH",
            str(exc),
            extra={
                "tx_hash": tx_hash,
                "pool_id": pool.id,
                "quote_id": quote.id,
                "local_chain": LOCAL_CHAIN_LABEL,
            },
        ) from exc

    if item is None:
        extra = {
            "tx_hash": tx_hash,
            "local_chain": LOCAL_CHAIN_LABEL,
            "pool_id": pool.id,
            "quote_id": quote.id,
            "status": "submitted",
        }
        if poll_error is not None:
            extra["indexer_error"] = {
                "code": poll_error.code,
                "detail": poll_error.detail,
            }
        raise ApiError(
            504,
            "INDEXER_CONFIRMATION_TIMEOUT",
            (
                "The withdrawal transaction was broadcast but the indexer did "
                "not expose a matching canonical withdrawal before the timeout."
            ),
            extra=extra,
        )

    # The wait helper checks tx hash, nullifier, recipient, fee and pool key.
    existing_withdrawal = _canonical_db_withdrawal(db, pool.id, nullifier)
    if existing_withdrawal is not None:
        if existing_withdrawal.tx_hash != tx_hash:
            raise ApiError(
                409,
                "NULLIFIER_SPENT",
                "This nullifier is already spent in this pool.",
                extra={
                    "withdrawal": _local_withdrawal_result(
                        db,
                        existing_withdrawal,
                        pool,
                        settings,
                        indexer,
                        item=item,
                    ),
                    "pool_id": pool.id,
                    "local_chain": LOCAL_CHAIN_LABEL,
                },
            )
        withdrawal = existing_withdrawal
    else:
        try:
            confirmed_at = datetime.fromtimestamp(
                int(item["block_timestamp"]), tz=timezone.utc
            ).replace(tzinfo=None)
        except (KeyError, TypeError, ValueError, OverflowError):
            confirmed_at = utcnow()
        withdrawal = Withdrawal(
            id=new_id("wdr"),
            pool_id=pool.id,
            nullifier_hash=nullifier,
            recipient_address=recipient,
            relayer_id=quote.relayer_id,
            tx_hash=tx_hash,
            block_number=int(item["block_number"]),
            block_hash=item["block_hash"].lower(),
            log_index=int(item["log_index"]),
            protocol_fee_wei=quote.protocol_fee_wei,
            relayer_fee_wei=relayer_fee,
            gas_cost_wei=quote.gas_estimate_wei,
            compliance_check_id=quote.compliance_check_id,
            status="confirmed",
            is_canonical=True,
            confirmed_at=confirmed_at,
            created_at=utcnow(),
        )
        db.add(withdrawal)
        db.flush()
        db.add(
            Nullifier(
                pool_id=pool.id,
                nullifier_hash=nullifier,
                withdrawal_id=withdrawal.id,
                block_number=withdrawal.block_number,
                spent_at=confirmed_at,
            )
        )

    quote.status = "submitted"
    broadcast.withdrawal_id = withdrawal.id
    append_audit(
        db,
        action="withdrawal.local_chain_recorded",
        resource_type="withdrawal",
        resource_id=withdrawal.id,
        actor_type="local_chain",
        actor_id=LOCAL_CHAIN_LABEL,
        decision="confirmed",
        request_id=request_id,
        metadata={
            "pool_id": pool.id,
            "quote_id": quote.id,
            "tx_hash": tx_hash,
            "nullifier_hash": nullifier,
            "recipient": recipient,
            "fee_wei": str(relayer_fee),
            "block_number": withdrawal.block_number,
            "chain_id": settings.chain_id,
            "local_chain": LOCAL_CHAIN_LABEL,
            "verifier_kind": verifier_kind_value(settings),
            "mock": False,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        stored = _canonical_db_withdrawal(db, pool.id, nullifier)
        if stored is not None and stored.tx_hash == tx_hash:
            return JSONResponse(
                status_code=200,
                content=_local_withdrawal_result(
                    db,
                    stored,
                    pool,
                    settings,
                    indexer,
                    item=item,
                ),
            )
        raise ApiError(
            409,
            "NULLIFIER_SPENT",
            "This nullifier was spent by a concurrent withdrawal.",
            extra={
                "tx_hash": tx_hash,
                "pool_id": pool.id,
                "local_chain": LOCAL_CHAIN_LABEL,
            },
        ) from exc

    return JSONResponse(
        status_code=201,
        content=_local_withdrawal_result(
            db,
            withdrawal,
            pool,
            settings,
            indexer,
            item=item,
        ),
    )
