from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..amounts import split_fee
from ..config import Settings
from ..deps import (
    get_db,
    get_request_id,
    get_settings,
    require_idempotency_key,
)
from ..errors import ApiError
from ..ids import new_id
from ..local_chain import GROTH16_PROOF_ENCODING
from ..local_read import GROTH16_WARNING, verifier_kind_value
from ..models import (
    ComplianceCheck,
    Nullifier,
    Pool,
    PoolRoot,
    Relayer,
    Withdrawal,
    WithdrawalQuote,
    iso_z,
    utcnow,
)
from ..presenters import withdrawal_view
from ..schemas import WithdrawalQuoteRequest, WithdrawalSubmitRequest, validate_hex32
from ..services.audit import append_audit
from ..services.compliance import (
    compliance_view,
    hash_address,
    require_allowed,
    screen_action,
)
from ..services.idempotency import check_replay, find, remember, replay
from ..services.mock_chain import MockChain, current_root
from ..services.verifier import MOCK_VERIFIER_NAME, MockVerifier

router = APIRouter(tags=["withdrawals"])


def _get_pool(db: Session, pool_id: str) -> Pool:
    pool = db.get(Pool, pool_id)
    if pool is None:
        raise ApiError(404, "POOL_NOT_FOUND", "Unknown pool id.")
    return pool


def _gas_estimate(pool: Pool) -> int:
    # Mock gas accounting. ETH pools subtract a small native-asset gas estimate;
    # token pools report zero because gas would be paid separately in reality.
    if pool.asset_symbol == "ETH":
        return min(310_000_000_000_000, pool.denomination_wei // 100)
    return 0


def _review_response(check: ComplianceCheck) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            "code": "COMPLIANCE_REVIEW",
            "decision": "review",
            "review_id": check.id,
            "check_id": check.id,
            "compliance": compliance_view(check),
            "expires_at": iso_z(check.expires_at),
            "mock": True,
        },
    )


def _root_is_known(
    db: Session, pool: Pool, root: str, settings: Settings
) -> bool:
    candidates = {current_root(db, pool).lower()}
    snapshots = db.execute(
        select(PoolRoot.root)
        .where(PoolRoot.pool_id == pool.id)
        .order_by(PoolRoot.block_number.desc())
        .limit(max(1, settings.root_window_size))
    ).scalars()
    candidates.update(item.lower() for item in snapshots)
    return root.lower() in candidates


@router.post("/withdrawals/quote")
def create_withdrawal_quote(
    body: WithdrawalQuoteRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    pool = _get_pool(db, body.pool_id)
    if pool.status == "paused":
        raise ApiError(409, "POOL_PAUSED", "This pool is paused.")
    if pool.status == "retired":
        raise ApiError(409, "POOL_RETIRED", "This pool is retired.")

    relayer = db.get(Relayer, body.relayer_id)
    if relayer is None:
        raise ApiError(404, "RELAYER_NOT_FOUND", "Unknown relayer id.")
    if relayer.status in {"offline", "disabled"}:
        raise ApiError(503, "RELAYER_OFFLINE", "This relayer is not accepting work.")
    if pool.id not in (relayer.supported_pools or []):
        raise ApiError(
            422,
            "RELAYER_UNSUPPORTED",
            "This relayer does not support the selected pool.",
        )

    quote_id = new_id("q")
    check = screen_action(
        db,
        settings,
        subject_type="withdrawal",
        subject_ref=quote_id,
        address=body.recipient_address,
        pool=pool,
        amount_wei=pool.denomination_wei,
        request_id=request_id,
    )
    if check.decision == "block":
        db.commit()
        raise ApiError(
            403,
            "COMPLIANCE_BLOCKED",
            "The recipient address was blocked by the mock compliance policy.",
            extra={
                "check_id": check.id,
                "decision": "block",
                "reasons": list(check.reasons or []),
                "policy_version": check.policy_version,
            },
        )
    if check.decision == "review":
        db.commit()
        return _review_response(check)

    protocol_fee_wei = split_fee(pool.denomination_wei, pool.protocol_fee_bps)
    relayer_fee_wei = split_fee(pool.denomination_wei, relayer.fee_bps)
    gas_estimate_wei = _gas_estimate(pool)
    recipient_receives_wei = (
        pool.denomination_wei
        - protocol_fee_wei
        - relayer_fee_wei
        - gas_estimate_wei
    )
    if recipient_receives_wei <= 0:
        db.commit()
        raise ApiError(
            422,
            "FEE_EXCEEDS_DENOMINATION",
            "Configured fees exceed the pool denomination; the pool should be paused.",
        )

    expires_at = utcnow() + timedelta(seconds=settings.quote_ttl_seconds)
    if check.expires_at is not None and check.expires_at < expires_at:
        expires_at = check.expires_at

    quote = WithdrawalQuote(
        id=quote_id,
        pool_id=pool.id,
        relayer_id=relayer.id,
        recipient_address=body.recipient_address,
        amount_wei=pool.denomination_wei,
        protocol_fee_wei=protocol_fee_wei,
        relayer_fee_wei=relayer_fee_wei,
        gas_estimate_wei=gas_estimate_wei,
        recipient_receives_wei=recipient_receives_wei,
        compliance_check_id=check.id,
        status="active",
        expires_at=expires_at,
    )
    db.add(quote)
    append_audit(
        db,
        action="withdrawal.quote.created",
        resource_type="withdrawal_quote",
        resource_id=quote.id,
        actor_type="client",
        decision="allow",
        request_id=request_id,
        metadata={
            "pool_id": pool.id,
            "relayer_id": relayer.id,
            "amount_wei": str(pool.denomination_wei),
            "check_id": check.id,
            "mock": True,
        },
    )
    db.commit()

    return {
        "quote_id": quote.id,
        "pool_id": pool.id,
        "relayer_id": relayer.id,
        "relayer_fee_bps": relayer.fee_bps,
        "relayer_fee_wei": str(relayer_fee_wei),
        "gas_estimate_wei": str(gas_estimate_wei),
        "recipient_receives_wei": str(recipient_receives_wei),
        "expires_at": iso_z(expires_at),
        "compliance": compliance_view(check),
        "proof_verifier": (
            "GROTH16_POSEIDON"
            if settings.mode == "local"
            and settings.local_verifier_kind == "groth16"
            else MOCK_VERIFIER_NAME
        ),
        "mock": settings.mode == "mock",
        **(
            {
                "local_chain": True,
                "proof_encoding": GROTH16_PROOF_ENCODING,
                "verifier_kind": verifier_kind_value(settings),
                "submission_available": bool(settings.local_auto_withdraw),
                **(
                    {
                        "submission_endpoint": "/api/v1/local/withdrawals",
                        "warning": (
                            GROTH16_WARNING
                            if settings.local_verifier_kind == "groth16"
                            else (
                                "Automatic local withdrawal is enabled, but "
                                "this local deployment is labelled with the "
                                "mock verifier. The bridge submits a 256-byte "
                                "Groth16 proof and only works against a "
                                "VeilPoolPoseidon + Groth16VerifierAdapter "
                                "deployment."
                            )
                        ),
                    }
                    if settings.local_auto_withdraw
                    else {
                        "warning": (
                            "Quote only. Automatic local withdrawal is "
                            "disabled. Submit the returned calldata from your "
                            "own wallet, or enable "
                            "VEILPOOL_LOCAL_AUTO_WITHDRAW for the dev bridge."
                        )
                    }
                ),
            }
            if settings.mode == "local"
            else {}
        ),
    }


@router.post("/withdrawals/submit")
def submit_withdrawal(
    body: WithdrawalSubmitRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    idempotency_key: str = Depends(require_idempotency_key),
):
    payload = body.model_dump(mode="json")
    if settings.mode != "mock":
        raise ApiError(
            409,
            "MOCK_ONLY",
            (
                "Withdrawal submission uses the mock relayer and mock chain, "
                "which are disabled in local mode. No transaction was sent."
            ),
            extra={"local_chain": settings.mode == "local"},
        )
    stored = check_replay(
        db, scope="withdrawal:submit", key=idempotency_key, payload=payload
    )
    if stored is not None:
        return replay(stored)

    pool = _get_pool(db, body.pool_id)
    if pool.status != "active":
        raise ApiError(409, "POOL_PAUSED", "This pool is not active.")

    quote = db.get(WithdrawalQuote, body.quote_id)
    if quote is None:
        raise ApiError(404, "QUOTE_NOT_FOUND", "Unknown withdrawal quote id.")
    if quote.pool_id != pool.id:
        raise ApiError(
            422, "PROOF_INVALID", "The quote belongs to a different pool."
        )
    if quote.status == "expired" or quote.expires_at <= utcnow():
        quote.status = "expired"
        db.commit()
        raise ApiError(409, "QUOTE_EXPIRED", "The withdrawal quote has expired.")
    if quote.recipient_address.lower() != body.recipient_address.lower():
        raise ApiError(
            422,
            "PROOF_INVALID",
            "The recipient does not match the quoted recipient.",
        )
    if (
        body.public_signals.recipient.lower()
        != body.recipient_address.lower()
    ):
        raise ApiError(
            422,
            "PROOF_INVALID",
            "The recipient public signal does not match the request.",
        )
    if int(body.public_signals.fee_wei) != quote.relayer_fee_wei:
        raise ApiError(
            422,
            "PROOF_INVALID",
            "The fee public signal does not match the relayer quote.",
        )
    if not MockVerifier.verify(body.proof):
        raise ApiError(
            422,
            "PROOF_INVALID",
            "The proof shape is invalid. The mock verifier is shape-only.",
            extra={"verifier": MOCK_VERIFIER_NAME, "mock": True},
        )
    if not _root_is_known(db, pool, body.public_signals.root, settings):
        raise ApiError(
            409,
            "ROOT_STALE",
            "The proof root is outside the accepted mock root window.",
        )

    existing_nullifier = db.get(
        Nullifier, (pool.id, body.public_signals.nullifier_hash.lower())
    )
    if existing_nullifier is not None:
        raise ApiError(
            409,
            "NULLIFIER_SPENT",
            "This nullifier is already spent in this pool.",
        )
    existing_withdrawal = db.execute(
        select(Withdrawal.id)
        .where(
            Withdrawal.pool_id == pool.id,
            Withdrawal.nullifier_hash == body.public_signals.nullifier_hash.lower(),
            Withdrawal.is_canonical.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_withdrawal is not None:
        raise ApiError(
            409,
            "NULLIFIER_SPENT",
            "This nullifier is already spent in this pool.",
        )
    if quote.status == "submitted":
        raise ApiError(409, "QUOTE_USED", "This quote has already been used.")

    check = db.get(ComplianceCheck, quote.compliance_check_id)
    require_allowed(check, expected_amount_wei=pool.denomination_wei)
    if (
        check.pool_id != pool.id
        or check.address_hash
        != hash_address(settings, body.recipient_address)
    ):
        raise ApiError(
            409,
            "COMPLIANCE_EXPIRED",
            "The compliance decision is bound to a different pool or recipient.",
        )

    withdrawal = Withdrawal(
        id=new_id("wdr"),
        pool_id=pool.id,
        nullifier_hash=body.public_signals.nullifier_hash.lower(),
        recipient_address=body.recipient_address,
        relayer_id=quote.relayer_id,
        protocol_fee_wei=quote.protocol_fee_wei,
        relayer_fee_wei=quote.relayer_fee_wei,
        gas_cost_wei=quote.gas_estimate_wei,
        compliance_check_id=check.id,
        status="submitted",
        is_canonical=True,
    )
    db.add(withdrawal)
    db.flush()

    MockChain(db, settings).record_withdrawal(
        withdrawal=withdrawal, quote=quote, request_id=request_id
    )
    append_audit(
        db,
        action="withdrawal.submitted",
        resource_type="withdrawal",
        resource_id=withdrawal.id,
        actor_type="client",
        decision="allow",
        request_id=request_id,
        metadata={
            "pool_id": pool.id,
            "nullifier_hash": withdrawal.nullifier_hash,
            "relayer_id": quote.relayer_id,
            "quote_id": quote.id,
            "mock": True,
        },
    )

    response = {
        "withdrawal_id": withdrawal.id,
        "status": "submitted",
        "chain_status": withdrawal.status,
        "tx_hash": withdrawal.tx_hash,
        "block_number": withdrawal.block_number,
        "relayer_id": withdrawal.relayer_id,
        "proof_verifier": MOCK_VERIFIER_NAME,
        "mock_chain": "MOCK_CHAIN",
        "mock": True,
    }
    remember(
        db,
        scope="withdrawal:submit",
        key=idempotency_key,
        payload=payload,
        status_code=202,
        response=response,
        resource_type="withdrawal",
        resource_id=withdrawal.id,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if (
            db.get(
                Nullifier, (pool.id, body.public_signals.nullifier_hash.lower())
            )
            is not None
        ):
            raise ApiError(
                409,
                "NULLIFIER_SPENT",
                "This nullifier is already spent in this pool.",
            ) from exc
        existing = find(db, "withdrawal:submit", idempotency_key)
        if existing is not None:
            return replay(existing)
        raise ApiError(
            409,
            "IDEMPOTENCY_MISMATCH",
            "The request conflicted with a concurrent submission.",
        ) from exc

    return JSONResponse(status_code=202, content=response)


@router.get("/withdrawals/by-nullifier/{nullifier_hash}")
def get_withdrawal_by_nullifier(
    nullifier_hash: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        normalized = validate_hex32(nullifier_hash).lower()
    except ValueError as exc:
        raise ApiError(
            422, "VALIDATION_ERROR", "nullifier_hash must be 0x-prefixed 32-byte hex."
        ) from exc
    withdrawal = db.execute(
        select(Withdrawal)
        .where(
            Withdrawal.nullifier_hash == normalized,
            Withdrawal.is_canonical.is_(True),
        )
        .order_by(Withdrawal.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if withdrawal is None:
        raise ApiError(
            404, "WITHDRAWAL_NOT_FOUND", "No canonical withdrawal uses this nullifier."
        )
    return {
        **withdrawal_view(db, withdrawal, settings.chain_id),
        "privacy_warning": (
            "Nullifier lookups are privacy-sensitive. Prefer local client history."
        ),
    }


@router.get("/withdrawals/{withdrawal_id}")
def get_withdrawal(
    withdrawal_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    withdrawal = db.get(Withdrawal, withdrawal_id)
    if withdrawal is None:
        raise ApiError(404, "WITHDRAWAL_NOT_FOUND", "Unknown withdrawal id.")
    return withdrawal_view(db, withdrawal, settings.chain_id)
