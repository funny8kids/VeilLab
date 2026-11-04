from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import __version__
from ..config import Settings
from ..deps import get_db, get_indexer_client, get_settings
from ..indexer_client import IndexerClient
from ..local_read import (
    LOCAL_CHAIN_SERVICE,
    MOCK_COMPLIANCE_SERVICE,
    indexer_health_view,
    load_health,
    local_mock_services,
    local_warning,
    verifier_kind_value,
    verifier_service_label,
)

router = APIRouter(tags=["health"])


def build_health(
    db: Session,
    settings: Settings,
    indexer: IndexerClient,
) -> dict:
    db.execute(text("SELECT 1"))
    if settings.mode == "local":
        health, error = load_health(indexer, settings)
        indexer_view = indexer_health_view(settings, health, error)
        available = health is not None
        healthy = bool(
            available
            and health.get("status") == "ok"
            and not health.get("last_error")
        )
        return {
            "status": "ok" if healthy else "degraded",
            "service": "veilpool-api",
            "version": __version__,
            "mode": "local",
            "mock": False,
            "testnet_only": True,
            "chain_id": settings.chain_id,
            "chain_source": "indexer",
            "chain_data_status": "available" if available else "unavailable",
            "contract_address": settings.contract_address,
            "database": (
                "sqlite"
                if settings.database_url.startswith("sqlite")
                else "other"
            ),
            "verifier_kind": verifier_kind_value(settings),
            "services": {
                "chain": LOCAL_CHAIN_SERVICE,
                "verifier": verifier_service_label(settings),
                "compliance": MOCK_COMPLIANCE_SERVICE,
            },
            "mock_services": local_mock_services(settings),
            "indexer": indexer_view,
            "warning": local_warning(settings),
            "disclaimer": (
                "LOCAL CHAIN. Public chain facts come from the local indexer; "
                "secret client material is never accepted by this API. "
                + (
                    "The configured verifier is a development Groth16 build, "
                    "not a production system."
                    if settings.local_verifier_kind == "groth16"
                    else "The configured verifier is MockVerifier and performs "
                    "no ZK verification."
                )
            ),
        }

    return {
        "status": "ok",
        "service": "veilpool-api",
        "version": __version__,
        "mode": "mock",
        "mock": True,
        "testnet_only": True,
        "chain_id": settings.chain_id,
        "database": (
            "sqlite" if settings.database_url.startswith("sqlite") else "other"
        ),
        "services": {
            "chain": "MOCK_CHAIN (SQLite-backed, no RPC)",
            "verifier": "MOCK_VERIFIER (shape-only, no ZK)",
            "compliance": "MOCK_FIXTURES (deterministic, not a sanctions provider)",
        },
        "mock_services": [
            "MOCK_CHAIN",
            "MOCK_VERIFIER",
            "MOCK_COMPLIANCE",
        ],
        "disclaimer": (
            "LOCAL DEMO / MOCK PROOF. No real funds, no real ZK, testnet only. "
            "Secret client material is never accepted by this API."
        ),
    }


@router.get("/health")
def health(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    indexer: IndexerClient = Depends(get_indexer_client),
):
    return build_health(db, settings, indexer)
