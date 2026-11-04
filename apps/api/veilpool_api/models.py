from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from .database import Base


class Wei(TypeDecorator):
    """Exact unsigned integer token amount.

    SQLite stores this as text to avoid floating-point precision loss for
    uint256-scale values; PostgreSQL uses NUMERIC(78, 0).
    """

    impl = Numeric(78, 0)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # noqa: ANN001
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(78))
        return dialect.type_descriptor(Numeric(78, 0))

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        return str(int(value)) if dialect.name == "sqlite" else int(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001
        if value is None:
            return None
        return int(value)


def utcnow() -> datetime:
    """Naive UTC timestamp; SQLite stores timestamps without a timezone."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat() + "Z"


class Pool(Base):
    __tablename__ = "pools"
    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "asset_symbol",
            "denomination_wei",
            name="uq_pools_chain_asset_denomination",
        ),
        CheckConstraint(
            "status IN ('active','paused','retired')", name="ck_pools_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    denomination_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    tree_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    maturity_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_address: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_address: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    min_set_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (
        Index(
            "uq_deposits_canonical_event",
            "tx_hash",
            "log_index",
            unique=True,
            sqlite_where=text("is_canonical = 1"),
            postgresql_where=text("is_canonical"),
        ),
        Index(
            "uq_deposits_canonical_leaf",
            "pool_id",
            "leaf_index",
            unique=True,
            sqlite_where=text("is_canonical = 1"),
            postgresql_where=text("is_canonical"),
        ),
        Index("ix_deposits_pool_block", "pool_id", "block_number"),
        Index("ix_deposits_commitment", "commitment"),
        CheckConstraint(
            "status IN ('pending','confirmed','reorged')",
            name="ck_deposits_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pool_id: Mapped[str] = mapped_column(
        ForeignKey("pools.id"), nullable=False, index=True
    )
    commitment: Mapped[str] = mapped_column(String(66), nullable=False)
    leaf_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    depositor_address: Mapped[str | None] = mapped_column(String(64))
    compliance_check_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    is_canonical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DepositIntent(Base):
    __tablename__ = "deposit_intents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','consumed','expired','blocked')",
            name="ck_deposit_intents_status",
        ),
        Index(
            "ix_deposit_intents_pending_expiry",
            "expires_at",
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id"), nullable=False)
    address_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    commitment: Mapped[str | None] = mapped_column(String(66))
    compliance_check_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class LocalDepositBroadcast(Base):
    """Public record of an Anvil deposit broadcast.

    It keeps a repeated call from sending a second transaction after a timeout
    and stores no note material: only the intent id, commitment and tx hash.
    """

    __tablename__ = "local_deposit_broadcasts"

    intent_id: Mapped[str] = mapped_column(
        ForeignKey("deposit_intents.id"), primary_key=True
    )
    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id"), nullable=False)
    commitment: Mapped[str] = mapped_column(String(66), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class LocalWithdrawalBroadcast(Base):
    """Public record of an Anvil withdrawal broadcast.

    It keeps a repeated call from sending a second transaction after a timeout
    and stores no proof, witness or note material: only the quote id, the
    public pool/nullifier/recipient/fee fields and the transaction hash.
    """

    __tablename__ = "local_withdrawal_broadcasts"

    quote_id: Mapped[str] = mapped_column(
        ForeignKey("withdrawal_quotes.id"), primary_key=True
    )
    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id"), nullable=False)
    nullifier_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False, unique=True)
    recipient_address: Mapped[str] = mapped_column(String(64), nullable=False)
    relayer_fee_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    # Digest only: proof bytes are never persisted. The digest makes a replay
    # with a different proof distinguishable from a true idempotent replay.
    proof_sha256: Mapped[str | None] = mapped_column(String(66))
    withdrawal_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    __table_args__ = (
        Index(
            "uq_withdrawals_canonical_nullifier",
            "pool_id",
            "nullifier_hash",
            unique=True,
            sqlite_where=text("is_canonical = 1"),
            postgresql_where=text("is_canonical"),
        ),
        Index(
            "uq_withdrawals_canonical_event",
            "tx_hash",
            "log_index",
            unique=True,
            sqlite_where=text("is_canonical = 1"),
            postgresql_where=text("is_canonical"),
        ),
        Index("ix_withdrawals_pool_block", "pool_id", "block_number"),
        Index("ix_withdrawals_status", "status", "created_at"),
        CheckConstraint(
            "status IN ('proof_ready','submitted','confirmed','failed','reorged')",
            name="ck_withdrawals_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id"), nullable=False)
    nullifier_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    recipient_address: Mapped[str | None] = mapped_column(String(64))
    relayer_id: Mapped[str | None] = mapped_column(ForeignKey("relayers.id"))
    tx_hash: Mapped[str | None] = mapped_column(String(66))
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    block_hash: Mapped[str | None] = mapped_column(String(66))
    log_index: Mapped[int | None] = mapped_column(Integer)
    protocol_fee_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    relayer_fee_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    gas_cost_wei: Mapped[int | None] = mapped_column(Wei)
    compliance_check_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted")
    is_canonical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Nullifier(Base):
    __tablename__ = "nullifiers"

    pool_id: Mapped[str] = mapped_column(
        ForeignKey("pools.id"), primary_key=True
    )
    nullifier_hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    withdrawal_id: Mapped[str] = mapped_column(
        ForeignKey("withdrawals.id"), nullable=False
    )
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Relayer(Base):
    __tablename__ = "relayers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('online','degraded','offline','disabled')",
            name="ck_relayers_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    supported_pools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="online")
    uptime_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime)
    compliance_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class CompliancePolicy(Base):
    __tablename__ = "compliance_policies"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    sanctions_source: Mapped[str] = mapped_column(String(120), nullable=False)
    sanctions_version: Mapped[str] = mapped_column(String(120), nullable=False)
    blocked_jurisdictions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    daily_deposit_limit: Mapped[int] = mapped_column(Wei, nullable=False)
    daily_withdraw_limit: Mapped[int] = mapped_column(Wei, nullable=False)
    per_tx_limit: Mapped[int] = mapped_column(Wei, nullable=False)
    review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    review_sla_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('deposit','withdrawal','relayer')",
            name="ck_compliance_checks_subject_type",
        ),
        CheckConstraint(
            "decision IN ('allow','review','block')",
            name="ck_compliance_checks_decision",
        ),
        Index(
            "ix_compliance_review",
            "decision",
            "created_at",
            sqlite_where=text("decision = 'review'"),
            postgresql_where=text("decision = 'review'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    address_hash: Mapped[str | None] = mapped_column(String(80))
    pool_id: Mapped[str | None] = mapped_column(String(64))
    amount_wei: Mapped[int | None] = mapped_column(Wei)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class WithdrawalQuote(Base):
    __tablename__ = "withdrawal_quotes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','submitted','expired')",
            name="ck_withdrawal_quotes_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id"), nullable=False)
    relayer_id: Mapped[str] = mapped_column(ForeignKey("relayers.id"), nullable=False)
    recipient_address: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    protocol_fee_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    relayer_fee_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    gas_estimate_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    recipient_receives_wei: Mapped[int] = mapped_column(Wei, nullable=False)
    compliance_check_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class PoolRoot(Base):
    __tablename__ = "pool_roots"
    __table_args__ = (
        UniqueConstraint("pool_id", "block_number", name="uq_pool_roots_pool_block"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pool_id: Mapped[str] = mapped_column(ForeignKey("pools.id"), nullable=False)
    root: Mapped[str] = mapped_column(String(66), nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class IndexerCursor(Base):
    __tablename__ = "indexer_cursors"

    chain_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    project_id: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(128))
    trace_id: Mapped[str | None] = mapped_column(String(128))
    meta: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    prev_hash: Mapped[str | None] = mapped_column(String(66))
    hash: Mapped[str] = mapped_column(String(66), nullable=False)
