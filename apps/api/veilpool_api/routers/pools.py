from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_db, get_indexer_client, get_settings
from ..errors import ApiError
from ..indexer_client import IndexerClient, IndexerError
from ..local_chain import BN254_FIELD_MODULUS
from ..local_read import (
    LOCAL_CHAIN_SERVICE,
    LOCAL_POOL_IDS,
    apply_pool_detail_overlay,
    apply_pool_overlay,
    build_root_view,
    chain_data_status,
    indexer_health_view,
    load_snapshot,
    local_warning,
)
from ..models import Deposit, Pool
from ..presenters import deposit_view, pool_detail, pool_summary, root_view

router = APIRouter(tags=["pools"])

_HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def _get_pool(db: Session, pool_id: str) -> Pool:
    pool = db.get(Pool, pool_id)
    if pool is None:
        raise ApiError(404, "POOL_NOT_FOUND", "Unknown pool id.")
    return pool


def _mock_deposit_list(db: Session, pool: Pool, limit: int) -> list[dict]:
    deposits = list(
        db.execute(
            select(Deposit)
            .where(
                Deposit.pool_id == pool.id,
                Deposit.is_canonical.is_(True),
                Deposit.status == "confirmed",
            )
            .order_by(Deposit.block_number.asc(), Deposit.log_index.asc())
            .limit(limit)
        ).scalars()
    )
    return [deposit_view(db, deposit, pool.chain_id) for deposit in deposits]


@router.get("/pools")
def list_pools(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
):
    pools = list(
        db.execute(select(Pool).order_by(Pool.asset_symbol.asc(), Pool.id.asc())).scalars()
    )
    if settings.mode == "local":
        snapshot = load_snapshot(indexer, settings)
        items = [
            apply_pool_overlay(
                pool_summary(db, pool),
                pool,
                snapshot=snapshot,
                settings=settings,
            )
            for pool in pools
        ]
        health_view = indexer_health_view(
            settings, snapshot.health, snapshot.error
        )
        return {
            "items": items,
            "next_cursor": None,
            "mode": "local",
            "mock": False,
            "chain_source": "indexer",
            "chain_data_status": chain_data_status(snapshot),
            "chain_id": settings.chain_id,
            "contract_address": settings.contract_address,
            "indexed_block": health_view.get("indexed_block"),
            "tip_block": health_view.get("tip_block"),
            "lag": health_view.get("lag"),
            "indexer": health_view,
            "services": {"chain": LOCAL_CHAIN_SERVICE},
            "warning": (
                local_warning(settings)
                if snapshot.available
                else (
                    "Indexer unavailable: pool configuration is shown, but "
                    "chain-derived deposit/withdrawal counts and roots are "
                    "omitted rather than fabricated."
                )
            ),
        }
    return {
        "items": [pool_summary(db, pool) for pool in pools],
        "next_cursor": None,
        "mode": "mock",
        "mock": True,
        "chain_id": settings.chain_id,
        "disclaimer": (
            "MOCK MODE: testnet-only demo data. Anonymity set is an approximate "
            "unspent-deposit count."
        ),
    }


@router.get("/pools/{pool_id}")
def get_pool(
    pool_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
):
    pool = _get_pool(db, pool_id)
    if settings.mode == "local":
        snapshot = load_snapshot(indexer, settings)
        detail = apply_pool_detail_overlay(
            pool_summary(db, pool),
            pool,
            snapshot=snapshot,
            settings=settings,
        )
        detail["indexer"] = indexer_health_view(
            settings, snapshot.health, snapshot.error
        )
        return detail
    return pool_detail(db, pool)


@router.get("/pools/{pool_id}/root")
def get_pool_root(
    pool_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
):
    pool = _get_pool(db, pool_id)
    if settings.mode != "local":
        return root_view(db, pool)

    if pool.id not in LOCAL_POOL_IDS:
        raise ApiError(
            409,
            "POOL_RETIRED",
            "This pool is not configured for the local Anvil deployment.",
        )
    try:
        items = indexer.list_roots(
            pool.id, limit=max(1, settings.root_window_size)
        )
    except IndexerError as exc:
        return build_root_view(pool, None, exc)
    return build_root_view(pool, items, None)


@router.get("/pools/{pool_id}/path/{commitment}")
def get_pool_path(
    pool_id: str,
    commitment: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
):
    """Proxy a public Merkle membership path from the local indexer.

    This is a read-only local-mode endpoint so the browser prover does not
    call the indexer cross-origin. Only public path fields are forwarded; a
    note, witness, secret or proof is never accepted or returned.
    """

    if settings.mode != "local":
        raise ApiError(
            404,
            "LOCAL_ONLY",
            "Merkle paths are only available in local Anvil mode.",
        )
    pool = _get_pool(db, pool_id)
    if pool.id not in LOCAL_POOL_IDS:
        raise ApiError(
            409,
            "POOL_RETIRED",
            "This pool is not configured for the local Anvil deployment.",
        )

    normalized = commitment.strip().lower()
    if not _HEX32_RE.match(normalized):
        raise ApiError(
            400,
            "INVALID_COMMITMENT",
            "commitment must be 0x-prefixed 32-byte hex.",
        )
    if int(normalized, 16) >= BN254_FIELD_MODULUS:
        raise ApiError(
            422,
            "NON_CANONICAL_COMMITMENT",
            "commitment is not a canonical BN254 field element.",
        )

    try:
        return indexer.get_path(pool.id, normalized)
    except IndexerError as exc:
        raise ApiError(
            exc.status_code,
            exc.code,
            exc.detail,
            extra={
                "pool_id": pool.id,
                "chain_source": "indexer",
                "chain_data_status": (
                    "unavailable"
                    if exc.code == "INDEXER_UNAVAILABLE"
                    else "available"
                ),
            },
        ) from exc


@router.get("/pools/{pool_id}/deposits")
def list_pool_deposits(
    pool_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
):
    """List canonical deposits.

    Mock mode reads the local SQLite mock chain. Local mode proxies the
    standalone indexer's canonical event list with public fields only.
    """

    pool = _get_pool(db, pool_id)
    if settings.mode == "mock":
        items = _mock_deposit_list(db, pool, limit)
        return {
            "items": items,
            "count": len(items),
            "next_cursor": None,
            "pool_id": pool.id,
            "pool_key": None,
            "chain_id": settings.chain_id,
            "chain_source": "mock",
            "chain_data_status": "available",
            "mock": True,
            "limit": limit,
        }

    if pool.id not in LOCAL_POOL_IDS:
        raise ApiError(
            409,
            "POOL_RETIRED",
            "This pool is not configured for the local Anvil deployment.",
        )
    try:
        items = indexer.list_deposits(pool.id, limit=limit)
    except IndexerError as exc:
        raise ApiError(
            exc.status_code,
            exc.code,
            exc.detail,
            extra={
                "pool_id": pool.id,
                "chain_source": "indexer",
                "chain_data_status": "unavailable",
            },
        ) from exc
    for item in items:
        item["api_pool_id"] = pool.id
        if not item.get("pool_key"):
            item["pool_key"] = pool.id
    return {
        "items": items,
        "count": len(items),
        "next_cursor": None,
        "pool_id": pool.id,
        "pool_key": pool.id,
        "chain_id": settings.chain_id,
        "contract_address": settings.contract_address,
        "canonical_only": True,
        "chain_source": "indexer",
        "chain_data_status": "available",
        "local_chain": "ANVIL",
        "mock": False,
        "limit": limit,
    }


@router.get("/pools/{pool_id}/deposits/{tx_hash}")
def get_deposit(
    pool_id: str,
    tx_hash: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
):
    pool = _get_pool(db, pool_id)
    deposit = db.execute(
        select(Deposit)
        .where(
            Deposit.pool_id == pool.id,
            Deposit.tx_hash == tx_hash.lower(),
            Deposit.is_canonical.is_(True),
        )
        .order_by(Deposit.block_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if deposit is not None:
        view = deposit_view(db, deposit, pool.chain_id)
        if settings.mode == "local":
            view.update(
                {
                    "mock": False,
                    "chain_source": "indexer",
                    "local_chain": "ANVIL",
                }
            )
            try:
                health = indexer.health()
                tip = health.get("tip_block")
                threshold = int(health.get("finality_confirmations") or 1)
                if tip is None:
                    view["confirmations"] = None
                    view["finality"] = "unknown"
                else:
                    confirmations = max(
                        0, int(tip) - int(deposit.block_number) + 1
                    )
                    view["confirmations"] = confirmations
                    view["finality"] = (
                        "final"
                        if confirmations >= threshold
                        else "optimistic"
                    )
            except IndexerError:
                view["confirmations"] = None
                view["finality"] = "unknown"
        return view

    if settings.mode == "local" and pool.id in LOCAL_POOL_IDS:
        try:
            items = indexer.list_deposits(pool.id, limit=1000)
        except IndexerError as exc:
            raise ApiError(
                exc.status_code,
                exc.code,
                exc.detail,
                extra={"chain_data_status": "unavailable"},
            ) from exc
        for item in items:
            if item["tx_hash"] == tx_hash.lower():
                return {
                    "tx_hash": item["tx_hash"],
                    "pool_id": pool.id,
                    "status": "confirmed",
                    "commitment": item["commitment"],
                    "leaf_index": item["leaf_index"],
                    "block_number": item["block_number"],
                    "block_hash": item["block_hash"],
                    "log_index": item["log_index"],
                    "block_timestamp": item["block_timestamp"],
                    "confirmations": item.get("confirmations"),
                    "finality": item.get("finality"),
                    "indexed_at": item.get("indexed_at"),
                    "mock": False,
                    "chain_source": "indexer",
                    "local_chain": "ANVIL",
                }

    raise ApiError(
        404,
        "DEPOSIT_NOT_FOUND",
        "No canonical deposit is indexed for this pool and transaction hash.",
    )
