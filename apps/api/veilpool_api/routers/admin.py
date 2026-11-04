from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_db, get_request_id, get_settings, require_admin
from ..errors import ApiError
from ..models import Pool, iso_z, utcnow
from ..schemas import (
    ComplianceReviewDecisionRequest,
    PoolAdminActionRequest,
)
from ..services.audit import append_audit
from ..services.compliance import (
    decide_review,
    list_reviews,
    review_decision_reason,
    review_view,
)

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


def _action(
    pool_id: str,
    target_status: str,
    body: PoolAdminActionRequest | None,
    db: Session,
    settings: Settings,
    request_id: str,
):
    if settings.mode != "mock":
        raise ApiError(
            409,
            "MOCK_ONLY",
            (
                "Admin pause/resume writes mock chain state and is disabled "
                "in local mode. Use the deployed contract owner instead."
            ),
        )
    pool = db.get(Pool, pool_id)
    if pool is None:
        raise ApiError(404, "POOL_NOT_FOUND", "Unknown pool id.")
    reason = "operator request"
    if body is not None and body.reason is not None and body.reason.strip():
        reason = body.reason.strip()
    pool.status = target_status
    pool.updated_at = utcnow()
    append_audit(
        db,
        action=f"pool.{'pause' if target_status == 'paused' else 'resume'}",
        resource_type="pool",
        resource_id=pool.id,
        actor_type="admin",
        actor_id="admin-token",
        decision="allow",
        reason=reason,
        request_id=request_id,
        metadata={"new_status": target_status, "mock": True},
    )
    db.commit()
    return {
        "id": pool.id,
        "status": pool.status,
        "reason": reason,
        "audited": True,
        "updated_at": iso_z(pool.updated_at),
        "mock": True,
    }


@router.post("/admin/pools/{pool_id}/pause")
def pause_pool(
    pool_id: str,
    body: PoolAdminActionRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    return _action(pool_id, "paused", body, db, settings, request_id)


@router.post("/admin/pools/{pool_id}/resume")
def resume_pool(
    pool_id: str,
    body: PoolAdminActionRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    return _action(pool_id, "active", body, db, settings, request_id)


@router.get("/admin/compliance/reviews")
def compliance_reviews(
    status: str = Query(
        default="pending",
        pattern="^(pending|approved|rejected|all)$",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    reviews = list_reviews(db, status=status, limit=limit)
    items = []
    for review in reviews:
        reason = (
            review_decision_reason(db, review.id)
            if review.reviewed_at is not None
            else None
        )
        items.append(review_view(review, decision_reason=reason))
    return {
        "items": items,
        "count": len(items),
        "next_cursor": None,
        "mock": True,
    }


@router.post("/admin/compliance/reviews/{review_id}/decision")
def decide_compliance_review(
    review_id: str,
    body: ComplianceReviewDecisionRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    review = decide_review(
        db,
        settings,
        review_id=review_id,
        decision=body.decision,
        reason=body.reason.strip(),
        expires_in_seconds=body.expires_in_seconds,
        expires_at_override=body.expires_at,
        request_id=request_id,
    )
    db.commit()
    return {
        **review_view(
            review, decision_reason=body.reason.strip()
        ),
        "audited": True,
        "mock": True,
    }
