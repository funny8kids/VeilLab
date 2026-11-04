from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ApiError
from ..ids import new_id
from ..models import (
    AuditLog,
    ComplianceCheck,
    CompliancePolicy,
    Pool,
    iso_z,
    utcnow,
)
from .audit import append_audit

MOCK_PROVIDER = "mock-fixture-v1"
REVIEW_APPROVED = "REVIEW_APPROVED"
REVIEW_REJECTED = "REVIEW_REJECTED"


def hash_address(settings: Settings, address: str) -> str:
    value = f"{settings.compliance_hash_salt}:{address.strip().lower()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def latest_policy(db: Session) -> CompliancePolicy | None:
    return db.execute(
        select(CompliancePolicy).order_by(CompliancePolicy.version.desc()).limit(1)
    ).scalar_one_or_none()


def _daily_used(
    db: Session, *, subject_type: str, address_hash: str, since: datetime
) -> int:
    rows = db.execute(
        select(ComplianceCheck.amount_wei).where(
            ComplianceCheck.subject_type == subject_type,
            ComplianceCheck.address_hash == address_hash,
            ComplianceCheck.decision == "allow",
            # A review approval is a gate, not a transaction. The retried
            # intent/quote creates its own allow check that counts once.
            ComplianceCheck.reviewed_at.is_(None),
            ComplianceCheck.created_at >= since,
        )
    ).scalars()
    return sum(int(value or 0) for value in rows)


def _active_review_decision(
    db: Session,
    *,
    subject_type: str,
    address_hash: str,
    pool_id: str,
    amount_wei: int,
    now: datetime,
) -> ComplianceCheck | None:
    """Latest unexpired human decision bound to this exact action shape.

    Review approvals and rejections are stored on the original
    ``ComplianceCheck`` row. They only apply to the same subject type, address
    hash, pool and amount, and stop applying at ``expires_at``.
    """

    return db.execute(
        select(ComplianceCheck)
        .where(
            ComplianceCheck.subject_type == subject_type,
            ComplianceCheck.address_hash == address_hash,
            ComplianceCheck.pool_id == pool_id,
            ComplianceCheck.amount_wei == amount_wei,
            ComplianceCheck.reviewed_at.is_not(None),
            ComplianceCheck.decision.in_(("allow", "block")),
            ComplianceCheck.expires_at.is_not(None),
            ComplianceCheck.expires_at > now,
        )
        .order_by(
            ComplianceCheck.reviewed_at.desc(), ComplianceCheck.id.desc()
        )
        .limit(1)
    ).scalar_one_or_none()


def screen_action(
    db: Session,
    settings: Settings,
    *,
    subject_type: str,
    subject_ref: str,
    address: str,
    pool: Pool,
    amount_wei: int,
    request_id: str | None = None,
) -> ComplianceCheck:
    """Run the deterministic mock compliance fixture.

    Rules:
    - block when the normalized address starts with ``0xbad``
    - review when it starts with ``0xdead``
    - block over the per-transaction limit
    - block when the address would exceed the daily subject limit

    A human review decision is a time-bounded override only for the exact
    subject type, address hash, pool and amount. Approvals let a retried flow
    proceed; rejections block it. Hard blocks (sanctions fixture, limits) are
    never overridden by a review.

    Decisions expire. The caller must check ``expires_at`` before reuse.
    """

    policy = latest_policy(db)
    now = utcnow()
    address_hash = hash_address(settings, address)
    reasons: list[str] = []
    decision = "allow"
    risk_score = 4
    review_source_id: str | None = None

    if policy is None:
        decision = "block"
        risk_score = 100
        reasons = ["POLICY_UNAVAILABLE"]
        policy_version = 0
        daily_limit = 0
        per_tx_limit = 0
        expires_at = now
    else:
        policy_version = policy.version
        daily_limit = (
            policy.daily_deposit_limit
            if subject_type == "deposit"
            else policy.daily_withdraw_limit
        )
        per_tx_limit = policy.per_tx_limit
        expires_at = now + timedelta(seconds=settings.compliance_ttl_seconds)
        normalized = address.strip().lower()
        if normalized.startswith("0xbad"):
            decision = "block"
            risk_score = 100
            reasons = ["SANCTIONS_MATCH"]
        elif amount_wei > per_tx_limit:
            decision = "block"
            risk_score = 80
            reasons = ["LIMIT_PER_TX"]
        else:
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            used = _daily_used(
                db,
                subject_type=subject_type,
                address_hash=address_hash,
                since=start_of_day,
            )
            if used + amount_wei > daily_limit:
                decision = "block"
                risk_score = 75
                reasons = ["LIMIT_DAILY"]
            elif normalized.startswith("0xdead"):
                previous = _active_review_decision(
                    db,
                    subject_type=subject_type,
                    address_hash=address_hash,
                    pool_id=pool.id,
                    amount_wei=amount_wei,
                    now=now,
                )
                if previous is None:
                    decision = "review"
                    risk_score = 72
                    reasons = ["WATCHLIST_REVIEW"]
                else:
                    review_source_id = previous.id
                    risk_score = previous.risk_score or 72
                    if previous.decision == "allow":
                        decision = "allow"
                        reasons = [REVIEW_APPROVED]
                    else:
                        decision = "block"
                        reasons = [REVIEW_REJECTED]
                    if previous.expires_at is not None:
                        expires_at = min(expires_at, previous.expires_at)

    if policy is not None and decision == "review":
        # A review item lives for the policy review SLA, not the shorter
        # automated decision TTL. The decision itself gets a new expiry when
        # an operator approves or rejects it.
        expires_at = now + timedelta(
            hours=max(1, int(policy.review_sla_hours or 24))
        )

    check = ComplianceCheck(
        id=new_id("cmp"),
        subject_type=subject_type,
        subject_ref=subject_ref,
        address_hash=address_hash,
        pool_id=pool.id,
        amount_wei=amount_wei,
        provider=MOCK_PROVIDER,
        policy_version=policy_version,
        decision=decision,
        risk_score=risk_score,
        reasons=reasons,
        expires_at=expires_at,
    )
    db.add(check)
    db.flush()

    metadata = {
        "policy_version": policy_version,
        "risk_score": risk_score,
        "pool_id": pool.id,
        "amount_wei": str(amount_wei),
        "address_hash": address_hash,
    }
    if review_source_id is not None:
        metadata["review_id"] = review_source_id
    append_audit(
        db,
        action=f"compliance.{subject_type}.{decision}",
        resource_type="compliance_check",
        resource_id=check.id,
        actor_type="service",
        actor_id="compliance-mock",
        decision=decision,
        reason=",".join(reasons) if reasons else "policy_allow",
        request_id=request_id,
        metadata=metadata,
    )
    return check


def require_allowed(
    check: ComplianceCheck | None, *, expected_amount_wei: int | None = None
) -> ComplianceCheck:
    if check is None:
        raise ApiError(403, "COMPLIANCE_BLOCKED", "A compliance decision is required.")
    if check.decision == "block":
        raise ApiError(
            403,
            "COMPLIANCE_BLOCKED",
            "The request was blocked by the mock compliance policy.",
            extra={
                "check_id": check.id,
                "reasons": check.reasons,
                "policy_version": check.policy_version,
            },
        )
    if check.decision == "review":
        raise ApiError(
            202,
            "COMPLIANCE_REVIEW",
            "Manual review is required before this request can proceed.",
            extra={"check_id": check.id, "review_id": check.id},
        )
    expires_at = check.expires_at
    if expires_at is None or expires_at <= utcnow():
        raise ApiError(
            409,
            "COMPLIANCE_EXPIRED",
            "The compliance decision has expired. Request a new decision.",
            extra={"check_id": check.id},
        )
    if expected_amount_wei is not None and int(check.amount_wei or 0) != int(
        expected_amount_wei
    ):
        raise ApiError(
            409,
            "COMPLIANCE_EXPIRED",
            "The compliance decision is bound to a different amount.",
            extra={"check_id": check.id},
        )
    return check


def compliance_view(check: ComplianceCheck) -> dict[str, Any]:
    return {
        "decision": check.decision,
        "check_id": check.id,
        "risk_score": check.risk_score,
        "reasons": list(check.reasons or []),
        "policy_version": check.policy_version,
        "expires_at": iso_z(check.expires_at),
        "mock": True,
    }


def policy_view(policy: CompliancePolicy, settings: Settings) -> dict[str, Any]:
    return {
        "version": policy.version,
        # Display aliases used by the demo web client. Enforcement uses the
        # exact *_wei fields below.
        "policy_version": policy.version,
        "sanctions_list_version": policy.sanctions_version,
        "updated_at": iso_z(policy.effective_at),
        "daily_deposit_limit": "10000",
        "daily_withdrawal_limit": "10000",
        "per_transaction_limit": "5000",
        "allowed_jurisdictions": ["US", "GB", "DE", "SG", "JP", "CA"],
        "screening_sources": [
            "OFAC SDN (mock snapshot)",
            "EU Consolidated (mock snapshot)",
            "UN (mock snapshot)",
        ],
        "sanctions_source": policy.sanctions_source,
        "sanctions_version": policy.sanctions_version,
        "blocked_jurisdictions": list(policy.blocked_jurisdictions or []),
        "daily_deposit_limit_wei": str(policy.daily_deposit_limit),
        "daily_withdraw_limit_wei": str(policy.daily_withdraw_limit),
        "per_tx_limit_wei": str(policy.per_tx_limit),
        "review_required": policy.review_required,
        "review_sla_hours": policy.review_sla_hours,
        "decision_ttl_seconds": settings.compliance_ttl_seconds,
        "effective_at": iso_z(policy.effective_at),
        "provider": MOCK_PROVIDER,
        "mock": True,
        "disclaimer": (
            "MOCK COMPLIANCE: deterministic local fixtures, not a sanctions provider. "
            "Testnet only. Secret client material is never accepted."
        ),
    }


def review_status(check: ComplianceCheck) -> str:
    if check.reviewed_at is None and check.decision == "review":
        return "pending"
    return "approved" if check.decision == "allow" else "rejected"


def review_decision_reason(
    db: Session, review_id: str
) -> str | None:
    """Operator reason from the latest review-decision audit row."""

    return db.execute(
        select(AuditLog.reason)
        .where(
            AuditLog.resource_type == "compliance_check",
            AuditLog.resource_id == review_id,
            AuditLog.action.in_(
                ("compliance.review.approved", "compliance.review.rejected")
            ),
        )
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def review_view(
    check: ComplianceCheck, *, decision_reason: str | None = None
) -> dict[str, Any]:
    """Admin review item. Contains no raw address, note or proof material."""

    now = utcnow()
    reasons = list(check.reasons or [])
    return {
        "id": check.id,
        "review_id": check.id,
        "subject_type": check.subject_type,
        "subject_ref": check.subject_ref,
        "pool_id": check.pool_id,
        "amount_wei": (
            str(check.amount_wei) if check.amount_wei is not None else None
        ),
        "risk_score": check.risk_score,
        "reason_codes": reasons,
        "reasons": reasons,
        "reason": decision_reason,
        "decision_reason": decision_reason,
        "provider": check.provider,
        "policy_version": check.policy_version,
        "requested_at": iso_z(check.created_at),
        "created_at": iso_z(check.created_at),
        "age_seconds": max(0, int((now - check.created_at).total_seconds())),
        "expires_at": iso_z(check.expires_at),
        "expired": bool(
            check.expires_at is not None and check.expires_at <= now
        ),
        "status": review_status(check),
        "decision": check.decision,
        "reviewer": check.reviewed_by,
        "reviewed_by": check.reviewed_by,
        "reviewed_at": iso_z(check.reviewed_at),
        "mock": True,
    }


def list_reviews(
    db: Session, *, status: str = "pending", limit: int = 50
) -> list[ComplianceCheck]:
    statement = select(ComplianceCheck)
    if status == "pending":
        statement = statement.where(
            ComplianceCheck.decision == "review",
            ComplianceCheck.reviewed_at.is_(None),
        )
    elif status == "approved":
        statement = statement.where(
            ComplianceCheck.decision == "allow",
            ComplianceCheck.reviewed_at.is_not(None),
        )
    elif status == "rejected":
        statement = statement.where(
            ComplianceCheck.decision == "block",
            ComplianceCheck.reviewed_at.is_not(None),
        )
    elif status == "all":
        statement = statement.where(
            or_(
                ComplianceCheck.decision == "review",
                ComplianceCheck.reviewed_at.is_not(None),
            )
        )
    return list(
        db.execute(
            statement.order_by(
                ComplianceCheck.created_at.asc(), ComplianceCheck.id.asc()
            ).limit(limit)
        ).scalars()
    )


def decide_review(
    db: Session,
    settings: Settings,
    *,
    review_id: str,
    decision: str,
    reason: str,
    expires_in_seconds: int | None = None,
    expires_at_override: datetime | None = None,
    request_id: str | None = None,
) -> ComplianceCheck:
    """Approve or reject a manual review and append an audit record.

    Approving flips the check to ``allow`` for the decision lifetime; retried
    deposit/withdraw flows for the same subject, address hash, pool and amount
    can then proceed. Rejecting flips it to ``block`` for the same lifetime.
    """

    check = db.get(ComplianceCheck, review_id)
    if check is None:
        raise ApiError(
            404, "REVIEW_NOT_FOUND", "Unknown compliance review id."
        )
    if check.reviewed_at is not None:
        raise ApiError(
            409,
            "REVIEW_ALREADY_DECIDED",
            "This compliance review has already been decided.",
        )
    if check.decision != "review":
        raise ApiError(
            404, "REVIEW_NOT_FOUND", "Unknown compliance review id."
        )

    ttl = (
        expires_in_seconds
        if expires_in_seconds is not None
        else settings.review_decision_ttl_seconds
    )
    now = utcnow()
    expires_at = (
        expires_at_override
        if expires_at_override is not None
        else now + timedelta(seconds=ttl)
    )
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    if expires_at <= now:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "The review decision expiry must be in the future.",
        )
    approved = decision == "approve"
    marker = REVIEW_APPROVED if approved else REVIEW_REJECTED

    check.decision = "allow" if approved else "block"
    check.reviewed_by = "admin-token"
    check.reviewed_at = now
    check.expires_at = expires_at
    reasons = list(check.reasons or [])
    if marker not in reasons:
        reasons.append(marker)
    check.reasons = reasons
    db.flush()

    append_audit(
        db,
        action=f"compliance.review.{'approved' if approved else 'rejected'}",
        resource_type="compliance_check",
        resource_id=check.id,
        actor_type="admin",
        actor_id="admin-token",
        decision=check.decision,
        reason=reason,
        request_id=request_id,
        metadata={
            "review_id": check.id,
            "subject_type": check.subject_type,
            "subject_ref": check.subject_ref,
            "pool_id": check.pool_id,
            "amount_wei": (
                str(check.amount_wei)
                if check.amount_wei is not None
                else None
            ),
            "policy_version": check.policy_version,
            "expires_at": iso_z(expires_at),
            "mock": True,
        },
    )
    return check
