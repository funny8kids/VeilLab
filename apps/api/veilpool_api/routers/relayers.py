from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..errors import ApiError
from ..models import Relayer, iso_z

router = APIRouter(tags=["relayers"])


def _view(relayer: Relayer) -> dict:
    return {
        "id": relayer.id,
        "name": relayer.name,
        "fee_bps": relayer.fee_bps,
        "uptime_bps": relayer.uptime_bps,
        "latency_ms": relayer.latency_ms,
        "supported_pools": list(relayer.supported_pools or []),
        "status": relayer.status,
        "compliance_status": relayer.compliance_status,
        "last_heartbeat": iso_z(relayer.last_heartbeat),
        "mock": True,
    }


@router.get("/relayers")
def list_relayers(db: Session = Depends(get_db)):
    relayers = list(
        db.execute(select(Relayer).order_by(Relayer.id.asc())).scalars()
    )
    return {
        "items": [_view(relayer) for relayer in relayers],
        "next_cursor": None,
        "mode": "mock",
        "mock": True,
        "disclaimer": "MOCK relayers: no network traffic or real fee settlement.",
    }


@router.get("/relayers/{relayer_id}")
def get_relayer(relayer_id: str, db: Session = Depends(get_db)):
    relayer = db.get(Relayer, relayer_id)
    if relayer is None:
        raise ApiError(404, "RELAYER_NOT_FOUND", "Unknown relayer id.")
    return _view(relayer)
