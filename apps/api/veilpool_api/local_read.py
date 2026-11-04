"""Local-mode read-model overlays built from the standalone indexer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings
from .indexer_client import IndexerClient, IndexerError

LOCAL_POOL_IDS = frozenset({"pool_eth_01", "pool_eth_1", "pool_eth_10"})
LOCAL_CHAIN_SERVICE = "INDEXER (local Anvil chain, read-only public events)"
MOCK_VERIFIER_SERVICE = "MOCK_VERIFIER (shape-only, no ZK)"
GROTH16_VERIFIER_SERVICE = "GROTH16_POSEIDON (development zkey, unaudited)"
GROTH16_VERIFIER_KIND = "groth16-poseidon"
MOCK_COMPLIANCE_SERVICE = (
    "MOCK_FIXTURES (deterministic, not a sanctions provider)"
)
LOCAL_WARNING = (
    "LOCAL ANVIL CHAIN / MOCK VERIFIER. This mode reads public events from a "
    "local Anvil chain. The on-chain verifier is MockVerifier and performs no "
    "ZK verification. No real funds, no real privacy, local/testnet only."
)
GROTH16_WARNING = (
    "LOCAL ANVIL CHAIN / DEVELOPMENT GROTH16. The configured verifier kind is "
    "GROTH16_POSEIDON, but its zkey and adapter are a development spike and "
    "are unaudited. This is not a production non-custodial relayer, provides "
    "no anonymity guarantee, and must not be used with real funds."
)


def verifier_kind_value(settings: Settings) -> str:
    """Stable API label for the configured local verifier."""

    return (
        GROTH16_VERIFIER_KIND
        if settings.local_verifier_kind == "groth16"
        else "mock"
    )


def verifier_service_label(settings: Settings) -> str:
    return (
        GROTH16_VERIFIER_SERVICE
        if settings.local_verifier_kind == "groth16"
        else MOCK_VERIFIER_SERVICE
    )


def local_mock_services(settings: Settings) -> list[str]:
    # A real Groth16 adapter is not a mock service. Only the compliance
    # fixture remains explicitly mocked in that configuration.
    if settings.local_verifier_kind == "groth16":
        return ["MOCK_COMPLIANCE"]
    return ["MOCK_VERIFIER", "MOCK_COMPLIANCE"]


def local_warning(settings: Settings) -> str:
    return (
        GROTH16_WARNING
        if settings.local_verifier_kind == "groth16"
        else LOCAL_WARNING
    )


@dataclass(frozen=True)
class LocalSnapshot:
    health: dict[str, Any] | None
    pools: dict[str, dict[str, Any]] | None
    error: IndexerError | None

    @property
    def available(self) -> bool:
        return self.health is not None and self.pools is not None


def _validate_health(settings: Settings, health: dict[str, Any]) -> None:
    if int(health.get("chain_id") or 0) != settings.chain_id:
        raise IndexerError(
            "INDEXER_MISMATCH",
            "The indexer is reading a different chain than VEILPOOL_CHAIN_ID.",
            status_code=502,
        )
    contract = health.get("contract_address")
    if (
        isinstance(contract, str)
        and settings.contract_address
        and contract.lower() != settings.contract_address.lower()
    ):
        raise IndexerError(
            "INDEXER_MISMATCH",
            "The indexer is reading a different contract than "
            "VEILPOOL_CONTRACT_ADDRESS.",
            status_code=502,
        )


def load_health(
    client: IndexerClient, settings: Settings
) -> tuple[dict[str, Any] | None, IndexerError | None]:
    try:
        health = client.health()
        _validate_health(settings, health)
        return health, None
    except IndexerError as exc:
        return None, exc


def load_snapshot(
    client: IndexerClient, settings: Settings
) -> LocalSnapshot:
    health, error = load_health(client, settings)
    if error is not None:
        return LocalSnapshot(health=None, pools=None, error=error)
    assert health is not None
    try:
        items = client.pools()
    except IndexerError as exc:
        return LocalSnapshot(health=None, pools=None, error=exc)
    by_key = {
        item["pool_key"]: item
        for item in items
        if isinstance(item.get("pool_key"), str)
    }
    return LocalSnapshot(health=health, pools=by_key, error=None)


def indexer_health_view(
    settings: Settings,
    health: dict[str, Any] | None,
    error: IndexerError | None,
) -> dict[str, Any]:
    if health is None:
        return {
            "status": "unavailable",
            "url": settings.indexer_url,
            "chain_id": None,
            "contract_address": settings.contract_address,
            "indexed_block": None,
            "tip_block": None,
            "lag": None,
            "last_error": error.detail if error else "Indexer unavailable.",
            "error_code": error.code if error else "INDEXER_UNAVAILABLE",
        }
    return {
        "status": health.get("status", "ok"),
        "url": settings.indexer_url,
        "chain_id": health.get("chain_id"),
        "contract_address": health.get("contract_address"),
        "indexed_block": health.get("indexed_block"),
        "tip_block": health.get("tip_block"),
        "lag": health.get("lag"),
        "finality_confirmations": health.get("finality_confirmations"),
        "last_synced_at": health.get("last_synced_at"),
        "last_error": health.get("last_error"),
        "reorgs": health.get("reorgs"),
        "event_counts": health.get("event_counts") or {},
        "error_code": None,
    }


def chain_data_status(snapshot: LocalSnapshot) -> str:
    return "available" if snapshot.available else "unavailable"


def apply_pool_overlay(
    summary: dict[str, Any],
    pool: Any,
    *,
    snapshot: LocalSnapshot,
    settings: Settings,
) -> dict[str, Any]:
    """Overlay indexer facts without inventing counts when it is down."""

    summary["mock"] = False
    summary["chain_source"] = "indexer"

    if pool.id not in LOCAL_POOL_IDS:
        summary["status"] = "retired"
        summary["chain_data_status"] = "not_configured"
        summary["anonymity_set"] = None
        summary["liquidity_wei"] = None
        summary["current_root"] = None
        summary["indexed_block"] = None
        summary["lag"] = None
        summary["warning"] = (
            "Only the three ETH pools are configured in local Anvil mode. "
            "USDC/tBTC pools are mock-only and retired here."
        )
        return summary

    if not snapshot.available:
        summary["chain_data_status"] = "unavailable"
        summary["anonymity_set"] = None
        summary["liquidity_wei"] = None
        summary["current_root"] = None
        summary["indexed_block"] = None
        summary["lag"] = None
        summary["warning"] = (
            "Indexer unavailable: chain-derived counts and roots are not "
            "shown. Pool configuration comes from the local database."
        )
        if snapshot.error is not None:
            summary["indexer_error"] = {
                "code": snapshot.error.code,
                "detail": snapshot.error.detail,
            }
        return summary

    assert snapshot.health is not None
    assert snapshot.pools is not None
    item = snapshot.pools.get(pool.id)
    if item is None:
        deposits = 0
        withdrawals = 0
        current_root = None
        current_root_block = None
        paused = False
        summary["chain_data_note"] = (
            "No canonical events are indexed for this pool yet."
        )
    else:
        deposits = int(item["deposits"])
        withdrawals = int(item["withdrawals"])
        current_root = item.get("current_root")
        current_root_block = item.get("current_root_block")
        paused = bool(item.get("paused"))
    unspent = max(deposits - withdrawals, 0)
    summary.update(
        {
            "chain_data_status": "available",
            "deposits": deposits,
            "withdrawals": withdrawals,
            "anonymity_set": unspent,
            "liquidity_wei": str(unspent * int(pool.denomination_wei)),
            "current_root": current_root,
            "current_root_block": current_root_block,
            "indexed_block": snapshot.health.get("indexed_block"),
            "tip_block": snapshot.health.get("tip_block"),
            "lag": snapshot.health.get("lag"),
            "chain_status": "paused" if paused else "active",
            "contract_address": settings.contract_address.lower(),
            "indexer_status": snapshot.health.get("status"),
        }
    )
    if paused:
        summary["status"] = "paused"
    return summary


def apply_pool_detail_overlay(
    summary: dict[str, Any],
    pool: Any,
    *,
    snapshot: LocalSnapshot,
    settings: Settings,
) -> dict[str, Any]:
    summary = apply_pool_overlay(
        summary, pool, snapshot=snapshot, settings=settings
    )
    summary["tree_depth"] = pool.tree_depth
    summary["asset_decimals"] = pool.asset_decimals
    summary["contract_address"] = (
        settings.contract_address.lower()
        if pool.id in LOCAL_POOL_IDS
        else None
    )
    summary["verifier_address"] = None
    if snapshot.available:
        assert snapshot.health is not None
        summary["root"] = summary.get("current_root")
        root_block = summary.get("current_root_block")
        tip = snapshot.health.get("tip_block")
        threshold = int(snapshot.health.get("finality_confirmations") or 1)
        if root_block is None or tip is None:
            confirmations = None
            finality = "unknown"
        else:
            confirmations = max(0, int(tip) - int(root_block) + 1)
            finality = "final" if confirmations >= threshold else "optimistic"
        summary["confirmations"] = confirmations
        summary["finality"] = finality
    else:
        summary["root"] = None
        summary["confirmations"] = None
        summary["finality"] = "unknown"
    return summary


def build_root_view(
    pool: Any,
    items: list[dict[str, Any]] | None,
    error: IndexerError | None,
) -> dict[str, Any]:
    if error is not None:
        return {
            "pool_id": pool.id,
            "root": None,
            "block_number": None,
            "block_hash": None,
            "root_history": [],
            "chain_source": "indexer",
            "chain_data_status": "unavailable",
            "mock": False,
            "warning": (
                "Indexer unavailable: the canonical root history is not "
                "shown."
            ),
            "indexer_error": {"code": error.code, "detail": error.detail},
        }

    items = items or []
    history: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        history.append(
            {
                "root": item["root"],
                "block_number": item["block_number"],
                "valid_until_block": (
                    items[index + 1]["block_number"]
                    if index + 1 < len(items)
                    else None
                ),
            }
        )
    latest = items[-1] if items else None
    view: dict[str, Any] = {
        "pool_id": pool.id,
        "root": latest["root"] if latest else None,
        "block_number": latest["block_number"] if latest else None,
        "block_hash": latest["block_hash"] if latest else None,
        "root_history": history,
        "chain_source": "indexer",
        "chain_data_status": "available",
        "mock": False,
    }
    if latest is None:
        view["chain_data_note"] = (
            "No canonical RootUpdated events are indexed for this pool yet."
        )
    return view
