from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_db, get_settings
from ..errors import ApiError
from ..services.compliance import latest_policy, policy_view

router = APIRouter(tags=["compliance"])


@router.get("/compliance/policy")
def get_compliance_policy(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    policy = latest_policy(db)
    if policy is None:
        raise ApiError(
            404, "POLICY_NOT_FOUND", "No compliance policy is configured."
        )
    return policy_view(policy, settings)
