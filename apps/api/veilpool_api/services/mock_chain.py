from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ApiError
from ..ids import new_id
from ..merkle import merkle_root
from ..models import (
    Deposit,
    DepositIntent,
    IndexerCursor,
    Nullifier,
    Pool,
    PoolRoot,
    Withdrawal,
    WithdrawalQuote,
    utcnow,
)
from .audit import append_audit

MOCK_STREAM = "mock_chain"
MOCK_CHAIN_LABEL = "MOCK_CHAIN"


def mock_block_hash(chain_id: int, block_number: int) -> str:
    return "0x" + hashlib.sha256(
        f"veilpool-mock-block:{chain_id}:{block_number}".encode("utf-8")
    ).hexdigest()


def _cursor(db: Session, settings: Settings) -> IndexerCursor:
    cursor = db.get(IndexerCursor, (settings.chain_id, MOCK_STREAM))
    if cursor is None:
        cursor = IndexerCursor(
            chain_id=settings.chain_id,
            stream=MOCK_STREAM,
            last_block=settings.mock_start_block,
            last_hash=mock_block_hash(settings.chain_id, settings.mock_start_block),
        )
        db.add(cursor)
        db.flush()
    return cursor


def _next_block(db: Session, settings: Settings) -> tuple[int, str]:
    cursor = _cursor(db, settings)
    block_number = int(cursor.last_block) + 1
    block_hash = mock_block_hash(settings.chain_id, block_number)
    cursor.last_block = block_number
    cursor.last_hash = block_hash
    cursor.updated_at = utcnow()
    db.flush()
    return block_number, block_hash


def current_root(db: Session, pool: Pool) -> str:
    commitments = list(
        db.execute(
            select(Deposit.commitment)
            .where(
                Deposit.pool_id == pool.id,
                Deposit.is_canonical.is_(True),
                Deposit.status == "confirmed",
            )
            .order_by(Deposit.leaf_index.asc())
        ).scalars()
    )
    return merkle_root(commitments, pool.tree_depth)


class MockChain:
    """SQLite-backed chain simulator for local demo mode.

    It records synthetic but structurally realistic deposit/withdrawal events.
    No RPC, signing or broadcast happens anywhere.
    """

    name = MOCK_CHAIN_LABEL

    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def record_deposit(
        self,
        *,
        pool: Pool,
        intent: DepositIntent,
        commitment: str,
        tx_hash: str | None,
        request_id: str | None = None,
    ) -> Deposit:
        if self.settings.mode != "mock":
            raise ApiError(404, "MOCK_ONLY", "Mock chain is disabled.")

        if tx_hash is not None:
            existing = self.db.execute(
                select(Deposit).where(Deposit.tx_hash == tx_hash).limit(1)
            ).scalar_one_or_none()
            if existing is not None:
                raise ApiError(
                    409,
                    "DUPLICATE_TX",
                    "This mock transaction hash is already indexed.",
                )

        block_number, block_hash = _next_block(self.db, self.settings)
        if tx_hash is None:
            tx_hash = "0x" + hashlib.sha256(
                f"veilpool-mock-deposit:{intent.id}:{block_number}".encode("utf-8")
            ).hexdigest()
        leaf_index = int(
            self.db.scalar(
                select(func.count())
                .select_from(Deposit)
                .where(
                    Deposit.pool_id == pool.id,
                    Deposit.is_canonical.is_(True),
                )
            )
            or 0
        )
        now = utcnow()
        deposit = Deposit(
            id=new_id("dep"),
            pool_id=pool.id,
            commitment=commitment.lower(),
            leaf_index=leaf_index,
            tx_hash=tx_hash.lower(),
            block_number=block_number,
            block_hash=block_hash,
            log_index=0,
            depositor_address=None,
            compliance_check_id=intent.compliance_check_id,
            status="confirmed",
            is_canonical=True,
            confirmed_at=now,
            created_at=now,
        )
        self.db.add(deposit)
        intent.status = "consumed"
        self.db.flush()

        root = current_root(self.db, pool)
        self.db.add(
            PoolRoot(
                id=new_id("rt"),
                pool_id=pool.id,
                root=root,
                block_number=block_number,
                block_hash=block_hash,
                created_at=now,
            )
        )
        append_audit(
            self.db,
            action="deposit.mock_chain_recorded",
            resource_type="deposit",
            resource_id=deposit.id,
            actor_type="mock_chain",
            actor_id=MOCK_CHAIN_LABEL,
            decision="confirmed",
            request_id=request_id,
            metadata={
                "pool_id": pool.id,
                "tx_hash": deposit.tx_hash,
                "leaf_index": leaf_index,
                "commitment": deposit.commitment,
                "chain_id": self.settings.chain_id,
                "mock": True,
            },
        )
        return deposit

    def record_withdrawal(
        self,
        *,
        withdrawal: Withdrawal,
        quote: WithdrawalQuote,
        request_id: str | None = None,
    ) -> Withdrawal:
        if self.settings.mode != "mock":
            raise ApiError(404, "MOCK_ONLY", "Mock chain is disabled.")

        block_number, block_hash = _next_block(self.db, self.settings)
        tx_hash = "0x" + hashlib.sha256(
            f"veilpool-mock-withdrawal:{withdrawal.id}:{block_number}".encode("utf-8")
        ).hexdigest()
        now = utcnow()

        existing = self.db.get(
            Nullifier, (withdrawal.pool_id, withdrawal.nullifier_hash)
        )
        if existing is not None:
            raise ApiError(
                409,
                "NULLIFIER_SPENT",
                "This nullifier is already spent in this pool.",
            )

        withdrawal.status = "confirmed"
        withdrawal.tx_hash = tx_hash
        withdrawal.block_number = block_number
        withdrawal.block_hash = block_hash
        withdrawal.log_index = 0
        withdrawal.confirmed_at = now
        withdrawal.gas_cost_wei = quote.gas_estimate_wei
        withdrawal.is_canonical = True
        quote.status = "submitted"

        self.db.add(
            Nullifier(
                pool_id=withdrawal.pool_id,
                nullifier_hash=withdrawal.nullifier_hash,
                withdrawal_id=withdrawal.id,
                block_number=block_number,
                spent_at=now,
            )
        )
        self.db.flush()
        append_audit(
            self.db,
            action="withdrawal.mock_chain_recorded",
            resource_type="withdrawal",
            resource_id=withdrawal.id,
            actor_type="mock_chain",
            actor_id=MOCK_CHAIN_LABEL,
            decision="confirmed",
            request_id=request_id,
            metadata={
                "pool_id": withdrawal.pool_id,
                "tx_hash": tx_hash,
                "nullifier_hash": withdrawal.nullifier_hash,
                "chain_id": self.settings.chain_id,
                "mock": True,
            },
        )
        return withdrawal
