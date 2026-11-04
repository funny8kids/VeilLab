"""Read-only HTTP API for the local-chain indexer.

The API deliberately exposes public chain facts only. There is no endpoint that
accepts or returns a note, secret, nullifier secret or proof material.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query

from . import __version__
from .config import ConfigError, Settings, VERIFIER_KINDS
from .merkle import CommitmentError, TREE_DEPTH, build_path, validate_commitments
from .poolids import normalize_bytes32, parse_pool_selector
from .poseidon import field_from_hex, field_to_hex32
from .store import Store

DISCLAIMER = (
    "LOCAL CHAIN / MOCK VERIFIER. Events come from a local Anvil chain and the "
    "on-chain verifier is MockVerifier, which performs no ZK proof verification. "
    "No real funds, no real privacy, testnet/local only. Notes never leave the client."
)

GROTH16_DISCLAIMER = (
    "LOCAL CHAIN / GROTH16 VERIFIER (development zkey, not audited). "
    "No production security or anonymity claim. Notes never leave the client."
)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def create_app(settings: Settings, store: Store | None = None) -> FastAPI:
    verifier_kind = settings.verifier_kind.strip().lower()
    if verifier_kind not in VERIFIER_KINDS:
        raise ConfigError(
            "INDEXER_VERIFIER_KIND must be one of: " + ", ".join(sorted(VERIFIER_KINDS))
        )
    is_mock = verifier_kind == "mock"
    disclaimer = DISCLAIMER if is_mock else GROTH16_DISCLAIMER

    store = store or Store(settings.database_path)
    store.initialize()
    store.set_meta("finality_confirmations", str(settings.finality_confirmations))

    app = FastAPI(
        title="VeilPool local-chain indexer",
        version=__version__,
        description=(
            "LOCAL DEMO ONLY. Reads public VeilPool events from Anvil. "
            + (
                "MockVerifier performs no cryptography."
                if is_mock
                else "Groth16 verifier uses a development zkey; it is not audited."
            )
        ),
    )

    def chain_id_or_none() -> int | None:
        raw = store.get_meta("chain_id")
        return None if raw is None else int(raw)

    def require_chain_id() -> int:
        chain_id = chain_id_or_none()
        if chain_id is None:
            raise _error(
                503,
                "INDEXER_NOT_READY",
                "The indexer has not verified a chain yet. Start the poller or run --once.",
            )
        return chain_id

    def resolve_pool(pool_id: str) -> tuple[int, str, str | None]:
        try:
            pool_hex, pool_key = parse_pool_selector(pool_id)
        except ValueError as exc:
            raise _error(400, "INVALID_POOL_ID", str(exc)) from exc
        chain_id = require_chain_id()
        if not store.known_pool(
            chain_id, settings.contract_address, pool_hex, pool_key
        ):
            raise _error(404, "POOL_NOT_FOUND", "No canonical events for this pool.")
        return chain_id, pool_hex, pool_key

    def envelope(chain_id: int, pool_hex: str, pool_key: str | None) -> dict[str, Any]:
        return {
            "chain_id": chain_id,
            "contract_address": settings.contract_address,
            "pool_id": pool_hex,
            "pool_key": pool_key,
            "canonical_only": True,
            "mock_verifier": is_mock,
            "verifier_kind": verifier_kind,
            "disclaimer": disclaimer,
        }

    @app.get("/health")
    def health() -> dict[str, Any]:
        chain_id = chain_id_or_none()
        cursor = (
            None
            if chain_id is None
            else store.get_cursor(chain_id, settings.contract_address)
        )
        tip_raw = store.get_meta("tip_block")
        tip = None if tip_raw is None else int(tip_raw)
        indexed = (
            None
            if cursor is None or int(cursor["last_block"]) < 0
            else int(cursor["last_block"])
        )
        last_error = store.get_meta("last_error")
        status = "ok"
        if last_error:
            status = "degraded"
        elif chain_id is None or tip is None:
            status = "starting"
        counts = (
            {}
            if chain_id is None
            else store.event_counts(chain_id, settings.contract_address)
        )
        return {
            "status": status,
            "service": "veilpool-indexer",
            "version": __version__,
            "mode": "local-chain",
            "mock_verifier": is_mock,
            "verifier_kind": verifier_kind,
            "testnet_only": True,
            "chain_id": chain_id,
            "contract_address": settings.contract_address,
            "indexed_block": indexed,
            "tip_block": tip,
            "lag": None if tip is None or indexed is None else max(0, tip - indexed),
            "finality_confirmations": settings.finality_confirmations,
            "last_synced_at": store.get_meta("last_synced_at"),
            "last_error": last_error,
            "reorgs": store.reorg_count(),
            "event_counts": counts,
            "disclaimer": disclaimer,
        }

    @app.get("/pools")
    def pools() -> dict[str, Any]:
        chain_id = require_chain_id()
        items = store.list_pools(chain_id, settings.contract_address)
        return {
            "items": items,
            "count": len(items),
            "chain_id": chain_id,
            "contract_address": settings.contract_address,
            "canonical_only": True,
            "mock_verifier": is_mock,
            "verifier_kind": verifier_kind,
            "disclaimer": disclaimer,
        }

    @app.get("/pools/{pool_id}/deposits")
    def deposits(
        pool_id: str,
        limit: int = Query(1000, ge=1, le=1000),
    ) -> dict[str, Any]:
        chain_id, pool_hex, pool_key = resolve_pool(pool_id)
        items = store.list_events(
            chain_id=chain_id,
            contract_address=settings.contract_address,
            pool_id=pool_hex,
            event_type="Deposit",
            limit=limit,
        )
        body = envelope(chain_id, pool_hex, pool_key)
        body.update(
            {
                "items": items,
                "count": len(items),
                "next_cursor": None,
            }
        )
        return body

    @app.get("/pools/{pool_id}/path/{commitment}")
    def path(
        pool_id: str,
        commitment: str,
    ) -> dict[str, Any]:
        chain_id, pool_hex, pool_key = resolve_pool(pool_id)
        raw_selector = commitment.strip()
        if raw_selector[:2].lower() == "0x":
            raw_selector = "0x" + raw_selector[2:]
        try:
            normalized = normalize_bytes32(raw_selector)
        except ValueError as exc:
            raise _error(
                400, "INVALID_COMMITMENT", f"Invalid commitment: {exc}"
            ) from exc
        try:
            target: int | None = field_from_hex(normalized)
        except ValueError:
            # Defer the canonical-field rejection until stored leaves are
            # validated, so a non-canonical *stored* commitment is reported as
            # 422 NON_CANONICAL_COMMITMENT even when the caller asks for it.
            target = None

        deposits = store.list_pool_deposits(
            chain_id=chain_id,
            contract_address=settings.contract_address,
            pool_id=pool_hex,
        )
        if not deposits:
            raise _error(
                404,
                "POOL_EMPTY",
                "The pool has no canonical deposits, so it has no Merkle leaves.",
            )

        # The on-chain tree assigns contiguous leaf indices starting at zero.
        # Reject a gap rather than building a path against a shifted tree.
        for expected, row in enumerate(deposits):
            if row["leaf_index"] is None or int(row["leaf_index"]) != expected:
                raise _error(
                    409,
                    "LEAF_INDEX_MISMATCH",
                    "Canonical deposits do not have contiguous leaf indices "
                    f"(expected {expected}, got {row['leaf_index']}).",
                )

        try:
            validated = validate_commitments([row["commitment"] for row in deposits])
        except CommitmentError as exc:
            raise _error(422, exc.code, str(exc)) from exc

        if target is None:
            raise _error(
                400,
                "INVALID_COMMITMENT",
                "Commitment is not a canonical BN254 field element (>= p).",
            )
        if target == 0:
            raise _error(400, "INVALID_COMMITMENT", "Commitment must be non-zero.")

        matches = [index for index, value in enumerate(validated) if value == target]
        if not matches:
            raise _error(
                404,
                "COMMITMENT_NOT_FOUND",
                "No canonical deposit for this commitment in the pool.",
            )
        leaf_index = matches[0]

        try:
            merkle_path = build_path(
                [row["commitment"] for row in deposits],
                leaf_index,
                depth=TREE_DEPTH,
            )
        except CommitmentError as exc:
            raise _error(422, exc.code, str(exc)) from exc

        latest_root = store.latest_event(
            chain_id=chain_id,
            contract_address=settings.contract_address,
            pool_id=pool_hex,
            event_type="RootUpdated",
        )
        body = envelope(chain_id, pool_hex, pool_key)
        body.update(
            {
                "commitment": normalized,
                "leaf_index": leaf_index,
                "leaf_count": merkle_path.leaf_count,
                "tree_depth": merkle_path.depth,
                "root": field_to_hex32(merkle_path.root),
                "path_elements": [
                    field_to_hex32(element) for element in merkle_path.path_elements
                ],
                "path_indices": list(merkle_path.path_indices),
                "root_block_number": None
                if latest_root is None
                else int(latest_root["block_number"]),
                "root_block_hash": None
                if latest_root is None
                else latest_root["block_hash"],
            }
        )
        return body

    @app.get("/pools/{pool_id}/roots")
    def roots(
        pool_id: str,
        limit: int = Query(1000, ge=1, le=1000),
    ) -> dict[str, Any]:
        chain_id, pool_hex, pool_key = resolve_pool(pool_id)
        items = store.list_events(
            chain_id=chain_id,
            contract_address=settings.contract_address,
            pool_id=pool_hex,
            event_type="RootUpdated",
            limit=limit,
        )
        latest = items[-1] if items else None
        body = envelope(chain_id, pool_hex, pool_key)
        body.update(
            {
                "current_root": None if latest is None else latest["root"],
                "current_root_block": None
                if latest is None
                else latest["block_number"],
                "items": items,
                "count": len(items),
            }
        )
        return body

    @app.get("/withdrawals/{nullifier}")
    def withdrawal(
        nullifier: str,
        pool_id: str | None = Query(
            None,
            description=(
                "Optional pool selector (short label or bytes32 hex). Use it when "
                "the same nullifier exists in more than one pool."
            ),
        ),
    ) -> dict[str, Any]:
        chain_id = require_chain_id()
        try:
            normalized = normalize_bytes32(nullifier)
        except ValueError as exc:
            raise _error(400, "INVALID_NULLIFIER", str(exc)) from exc

        pool_hex: str | None = None
        if pool_id is not None:
            try:
                pool_hex, _ = parse_pool_selector(pool_id)
            except ValueError as exc:
                raise _error(400, "INVALID_POOL_ID", str(exc)) from exc

        row = store.get_withdrawal(
            chain_id=chain_id,
            contract_address=settings.contract_address,
            nullifier=normalized,
            pool_id=pool_hex,
        )
        if row is None:
            raise _error(
                404,
                "WITHDRAWAL_NOT_FOUND",
                "No canonical withdrawal exists for this nullifier.",
            )
        result = dict(row)
        result.update(
            {
                "found": True,
                "mock_verifier": is_mock,
                "verifier_kind": verifier_kind,
                "disclaimer": disclaimer,
            }
        )
        return result

    return app
