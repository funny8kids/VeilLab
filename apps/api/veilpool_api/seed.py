from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .ids import new_id
from .merkle import merkle_root
from .models import (
    CompliancePolicy,
    IndexerCursor,
    Pool,
    PoolRoot,
    Relayer,
    utcnow,
)
from .services.mock_chain import MOCK_STREAM, mock_block_hash

_SEED_POOLS = (
    {
        "id": "pool_eth_01",
        "asset": "ETH",
        "decimals": 18,
        "denomination": "0.1",
        "maturity": 1800,
        "fee_bps": 24,
    },
    {
        "id": "pool_eth_1",
        "asset": "ETH",
        "decimals": 18,
        "denomination": "1",
        "maturity": 7200,
        "fee_bps": 22,
    },
    {
        "id": "pool_eth_10",
        "asset": "ETH",
        "decimals": 18,
        "denomination": "10",
        "maturity": 21600,
        "fee_bps": 20,
    },
    {
        "id": "pool_usdc_100",
        "asset": "USDC",
        "decimals": 6,
        "denomination": "100",
        "maturity": 1800,
        "fee_bps": 28,
    },
    {
        "id": "pool_usdc_1000",
        "asset": "USDC",
        "decimals": 6,
        "denomination": "1000",
        "maturity": 7200,
        "fee_bps": 25,
    },
    {
        "id": "pool_btc_001",
        "asset": "tBTC",
        "decimals": 18,
        "denomination": "0.01",
        "maturity": 7200,
        "fee_bps": 30,
    },
)


def _denomination_wei(amount: str, decimals: int) -> int:
    from .amounts import parse_amount_to_wei

    return parse_amount_to_wei(amount, decimals)


def _address(seed: str) -> str:
    return "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]


_LOCAL_POOL_IDS = frozenset({"pool_eth_01", "pool_eth_1", "pool_eth_10"})


def _seed_pools(db: Session, settings: Settings) -> list[Pool]:
    pools: list[Pool] = []
    configured = (
        tuple(item for item in _SEED_POOLS if item["id"] in _LOCAL_POOL_IDS)
        if settings.mode == "local"
        else _SEED_POOLS
    )
    if settings.mode == "local":
        # A database previously seeded in mock mode may still contain the
        # USDC/tBTC rows. Keep them readable but mark them retired; they have
        # no deployed contract in the ETH-only local Anvil slice.
        retired = db.execute(
            select(Pool).where(Pool.id.notin_(sorted(_LOCAL_POOL_IDS)))
        ).scalars()
        for pool in retired:
            if pool.status != "retired":
                pool.status = "retired"
                pool.updated_at = utcnow()

    for item in configured:
        pool = db.get(Pool, item["id"])
        if pool is None:
            is_local = settings.mode == "local"
            maturity = (
                settings.local_maturity_seconds
                if is_local and settings.local_maturity_seconds is not None
                else (
                    settings.mock_maturity_seconds
                    if settings.mock_maturity_seconds is not None
                    else item["maturity"]
                )
            )
            pool = Pool(
                id=item["id"],
                chain_id=settings.chain_id,
                asset_symbol=item["asset"],
                asset_decimals=item["decimals"],
                denomination_wei=_denomination_wei(
                    item["denomination"], item["decimals"]
                ),
                tree_depth=20,
                maturity_seconds=maturity,
                protocol_fee_bps=item["fee_bps"],
                contract_address=(
                    settings.contract_address.lower()
                    if is_local
                    else _address(f"contract:{item['id']}")
                ),
                verifier_address=(
                    "" if is_local else _address(f"verifier:{item['id']}")
                ),
                status="active",
                min_set_size=100,
            )
            db.add(pool)
            db.flush()
        elif settings.mode == "local":
            # Reconfigure in place when switching an existing demo database to
            # local mode. The same VeilPool contract hosts all three ETH pools.
            pool.chain_id = settings.chain_id
            pool.contract_address = settings.contract_address.lower()
            pool.verifier_address = ""
            if settings.local_maturity_seconds is not None:
                pool.maturity_seconds = settings.local_maturity_seconds
            pool.status = "active"
            pool.updated_at = utcnow()
        pools.append(pool)

        if settings.mode == "mock":
            has_root = db.execute(
                select(PoolRoot.id).where(PoolRoot.pool_id == pool.id).limit(1)
            ).scalar_one_or_none()
            if has_root is None:
                db.add(
                    PoolRoot(
                        id=new_id("rt"),
                        pool_id=pool.id,
                        root=merkle_root([], pool.tree_depth),
                        block_number=settings.mock_start_block,
                        block_hash=mock_block_hash(
                            settings.chain_id, settings.mock_start_block
                        ),
                    )
                )
    return pools


def _seed_relayers(db: Session, pools: list[Pool]) -> None:
    all_pools = [pool.id for pool in pools]
    now = utcnow()
    eth_pools = ["pool_eth_01", "pool_eth_1", "pool_eth_10"]
    usdc_pools = ["pool_usdc_100", "pool_usdc_1000"]
    definitions = (
        {
            "id": "rel_01",
            "name": "Relay-01",
            "endpoint": "mock://relayer/01",
            "fee_bps": 24,
            "supported_pools": [*eth_pools, *usdc_pools],
            "status": "online",
            "uptime_bps": 9998,
            "latency_ms": 38,
            "last_heartbeat": now,
        },
        {
            "id": "rel_02",
            "name": "Relay-02",
            "endpoint": "mock://relayer/02",
            "fee_bps": 30,
            "supported_pools": list(eth_pools),
            "status": "online",
            "uptime_bps": 9995,
            "latency_ms": 21,
            "last_heartbeat": now,
        },
        {
            "id": "rel_03",
            "name": "Relay-03",
            "endpoint": "mock://relayer/03",
            "fee_bps": 35,
            "supported_pools": list(all_pools),
            "status": "online",
            "uptime_bps": 9989,
            "latency_ms": 64,
            "last_heartbeat": now,
        },
        {
            "id": "rel_04",
            "name": "Relay-04",
            "endpoint": "mock://relayer/04",
            "fee_bps": 28,
            "supported_pools": [*usdc_pools, "pool_btc_001"],
            "status": "online",
            "uptime_bps": 9972,
            "latency_ms": 92,
            "last_heartbeat": now,
        },
        {
            "id": "rel_05",
            "name": "Relay-05",
            "endpoint": "mock://relayer/05",
            "fee_bps": 32,
            "supported_pools": ["pool_btc_001", "pool_usdc_100"],
            "status": "online",
            "uptime_bps": 9980,
            "latency_ms": 110,
            "last_heartbeat": now,
        },
        {
            "id": "rel_06",
            "name": "Relay-06",
            "endpoint": "mock://relayer/06",
            "fee_bps": 26,
            "supported_pools": list(eth_pools),
            "status": "degraded",
            "uptime_bps": 9965,
            "latency_ms": 144,
            "last_heartbeat": now,
        },
    )
    for definition in definitions:
        if db.get(Relayer, definition["id"]) is None:
            db.add(
                Relayer(
                    **definition,
                    compliance_status="allowed-mock",
                    created_at=now,
                )
            )


def _seed_policy(db: Session) -> None:
    existing = db.execute(select(CompliancePolicy.version).limit(1)).scalar_one_or_none()
    if existing is not None:
        return
    # Mock limits are expressed in base units of the pool asset. They are set
    # high enough for every seeded testnet denomination; tests can lower them.
    db.add(
        CompliancePolicy(
            version=1,
            sanctions_source="mock-fixture",
            sanctions_version="testnet-2026-11-03",
            blocked_jurisdictions=["KP", "IR", "SY"],
            daily_deposit_limit=1_000_000_000_000_000_000_000,
            daily_withdraw_limit=1_000_000_000_000_000_000_000,
            per_tx_limit=100_000_000_000_000_000_000,
            review_required=True,
            review_sla_hours=24,
            effective_at=utcnow(),
        )
    )


def _seed_cursor(db: Session, settings: Settings) -> None:
    if settings.mode != "mock":
        return
    cursor = db.get(IndexerCursor, (settings.chain_id, MOCK_STREAM))
    if cursor is None:
        db.add(
            IndexerCursor(
                chain_id=settings.chain_id,
                stream=MOCK_STREAM,
                last_block=settings.mock_start_block,
                last_hash=mock_block_hash(
                    settings.chain_id, settings.mock_start_block
                ),
            )
        )


def seed_database(db: Session, settings: Settings) -> None:
    pools = _seed_pools(db, settings)
    _seed_relayers(db, pools)
    _seed_policy(db)
    _seed_cursor(db, settings)
    db.flush()
