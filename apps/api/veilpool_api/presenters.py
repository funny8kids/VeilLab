from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .amounts import format_wei
from .models import (
    Deposit,
    IndexerCursor,
    Pool,
    PoolRoot,
    Withdrawal,
    iso_z,
)
from .services.mock_chain import MOCK_STREAM, current_root


def _count_deposits(db: Session, pool_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Deposit)
            .where(
                Deposit.pool_id == pool_id,
                Deposit.is_canonical.is_(True),
                Deposit.status == "confirmed",
            )
        )
        or 0
    )


def _count_withdrawals(db: Session, pool_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Withdrawal)
            .where(
                Withdrawal.pool_id == pool_id,
                Withdrawal.is_canonical.is_(True),
                Withdrawal.status == "confirmed",
            )
        )
        or 0
    )


def _cursor_block(db: Session, chain_id: int) -> int:
    cursor = db.get(IndexerCursor, (chain_id, MOCK_STREAM))
    return int(cursor.last_block) if cursor else 0


def pool_summary(db: Session, pool: Pool) -> dict[str, Any]:
    deposits = _count_deposits(db, pool.id)
    withdrawals = _count_withdrawals(db, pool.id)
    unspent = max(deposits - withdrawals, 0)
    return {
        "id": pool.id,
        "chain_id": pool.chain_id,
        "asset": pool.asset_symbol,
        "denomination": format_wei(pool.denomination_wei, pool.asset_decimals),
        "denomination_wei": str(pool.denomination_wei),
        "maturity_seconds": pool.maturity_seconds,
        "protocol_fee_bps": pool.protocol_fee_bps,
        "anonymity_set": unspent,
        "liquidity_wei": str(unspent * pool.denomination_wei),
        "status": pool.status,
        "min_set_size": pool.min_set_size,
        "mock": True,
    }


def pool_detail(db: Session, pool: Pool) -> dict[str, Any]:
    summary = pool_summary(db, pool)
    summary.update(
        {
            "tree_depth": pool.tree_depth,
            "contract_address": pool.contract_address,
            "verifier_address": pool.verifier_address,
            "root": current_root(db, pool),
            "indexed_block": _cursor_block(db, pool.chain_id),
            "confirmations": 12,
            "finality": "mock",
            "asset_decimals": pool.asset_decimals,
        }
    )
    return summary


def root_view(
    db: Session, pool: Pool, *, history_limit: int = 5
) -> dict[str, Any]:
    root = current_root(db, pool)
    snapshots = list(
        db.execute(
            select(PoolRoot)
            .where(PoolRoot.pool_id == pool.id)
            .order_by(PoolRoot.block_number.desc())
            .limit(history_limit)
        ).scalars()
    )
    snapshots.reverse()
    history = []
    for index, snapshot in enumerate(snapshots):
        valid_until = (
            snapshots[index + 1].block_number
            if index + 1 < len(snapshots)
            else None
        )
        history.append(
            {
                "root": snapshot.root,
                "block_number": snapshot.block_number,
                "valid_until_block": valid_until,
            }
        )
    latest = snapshots[-1] if snapshots else None
    return {
        "root": root,
        "block_number": latest.block_number if latest else 0,
        "block_hash": latest.block_hash if latest else "0x" + "0" * 64,
        "root_history": history,
        "mock": True,
    }


def deposit_view(
    db: Session, deposit: Deposit, chain_id: int
) -> dict[str, Any]:
    cursor_block = _cursor_block(db, chain_id)
    confirmations = max(0, cursor_block - int(deposit.block_number) + 1)
    return {
        "tx_hash": deposit.tx_hash,
        "pool_id": deposit.pool_id,
        "status": deposit.status,
        "commitment": deposit.commitment,
        "leaf_index": deposit.leaf_index,
        "block_number": deposit.block_number,
        "block_hash": deposit.block_hash,
        "confirmations": confirmations,
        "indexed_at": iso_z(deposit.confirmed_at or deposit.created_at),
        "mock": True,
    }


def withdrawal_view(db: Session, withdrawal: Withdrawal, chain_id: int) -> dict[str, Any]:
    cursor_block = _cursor_block(db, chain_id)
    confirmations = 0
    if withdrawal.block_number is not None:
        confirmations = max(
            0, cursor_block - int(withdrawal.block_number) + 1
        )
    return {
        "id": withdrawal.id,
        "pool_id": withdrawal.pool_id,
        "status": withdrawal.status,
        "tx_hash": withdrawal.tx_hash,
        "block_number": withdrawal.block_number,
        "confirmations": confirmations,
        "nullifier_hash": withdrawal.nullifier_hash,
        "recipient_address": withdrawal.recipient_address,
        "relayer_id": withdrawal.relayer_id,
        "failure_code": withdrawal.failure_code,
        "created_at": iso_z(withdrawal.created_at),
        "confirmed_at": iso_z(withdrawal.confirmed_at),
        "mock": True,
    }
