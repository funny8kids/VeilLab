from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import Settings
from .database import ensure_database
from .errors import install_error_handlers
from .indexer_client import IndexerClient
from .local_chain import LocalRpcClient
from .local_read import (
    LOCAL_CHAIN_SERVICE,
    MOCK_COMPLIANCE_SERVICE,
    indexer_health_view,
    load_health,
    local_mock_services,
    local_warning,
    verifier_kind_value,
    verifier_service_label,
)
from .routers import (
    admin,
    compliance,
    deposits,
    health,
    local,
    pools,
    relayers,
    withdrawals,
)
from .security import (
    SecurityMiddleware,
    TokenBucketRateLimiter,
    rate_limits_from_settings,
)


def create_app(
    settings: Settings | None = None,
    *,
    indexer_client: IndexerClient | None = None,
    local_rpc_client: LocalRpcClient | None = None,
) -> FastAPI:
    configured = settings or Settings.from_env()
    configured.validate()

    local_mode = configured.mode == "local"
    if local_mode:
        indexer_client = indexer_client or IndexerClient(
            configured.indexer_url,
            timeout=configured.indexer_timeout_seconds,
        )
        local_rpc_client = local_rpc_client or LocalRpcClient(
            configured.local_rpc_url,
            timeout=configured.indexer_timeout_seconds,
        )
    else:
        indexer_client = None
        local_rpc_client = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = ensure_database(app)
        try:
            yield
        finally:
            database.dispose()
            app.state.db = None
            if indexer_client is not None:
                indexer_client.close()
            if local_rpc_client is not None:
                local_rpc_client.close()

    app = FastAPI(
        title=(
            "VeilPool API (LOCAL ANVIL)" if local_mode else "VeilPool API (MOCK)"
        ),
        version=__version__,
        description=(
            "Testnet/local-only VeilPool MVP. In local mode public chain facts "
            "come from the standalone indexer; the configured verifier is "
            + (
                "a development Groth16 Poseidon adapter (unaudited), not a "
                "production verifier"
                if configured.local_verifier_kind == "groth16"
                else "MockVerifier (shape-only, no ZK)"
            )
            + ", and the compliance provider is a fixture. Secret client "
            "material is never accepted."
            if local_mode
            else "Testnet-only VeilPool MVP. Chain, verifier and compliance "
            "services are explicitly mocked. Secret client material is never "
            "accepted."
        ),
        lifespan=lifespan,
    )
    app.state.settings = configured
    app.state.indexer_client = indexer_client
    app.state.local_rpc_client = local_rpc_client
    limiter = TokenBucketRateLimiter(
        rate_limits_from_settings(configured),
        window_seconds=configured.rate_limit_window_seconds,
    )
    app.state.rate_limiter = limiter

    # The demo web app runs on a different local port. There are no cookies or
    # ambient credentials in this MVP; auth, when enabled, uses a bearer token.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-VeilPool-Mode",
            "X-VeilPool-Mock",
            "Retry-After",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Scope",
            "WWW-Authenticate",
        ],
    )
    # Added after CORS so the security middleware is the outer user layer and
    # also decorates CORS/error responses with request and security headers.
    app.add_middleware(
        SecurityMiddleware,
        settings=configured,
        limiter=limiter,
    )

    install_error_handlers(app)

    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(pools.router, prefix=prefix)
    app.include_router(deposits.router, prefix=prefix)
    app.include_router(local.router, prefix=prefix)
    app.include_router(relayers.router, prefix=prefix)
    app.include_router(withdrawals.router, prefix=prefix)
    app.include_router(compliance.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)

    @app.get("/", tags=["meta"])
    def root(request: Request):
        if configured.mode == "local":
            health_data, error = load_health(
                request.app.state.indexer_client, configured
            )
            indexer_view = indexer_health_view(
                configured, health_data, error
            )
            return {
                "service": "veilpool-api",
                "version": __version__,
                "mode": "local",
                "mock": False,
                "testnet_only": True,
                "chain_id": configured.chain_id,
                "chain_source": "indexer",
                "chain_data_status": (
                    "available" if health_data is not None else "unavailable"
                ),
                "contract_address": configured.contract_address,
                "docs": "/docs",
                "openapi": "/openapi.json",
                "api_base": prefix,
                "verifier_kind": verifier_kind_value(configured),
                "services": {
                    "chain": LOCAL_CHAIN_SERVICE,
                    "verifier": verifier_service_label(configured),
                    "compliance": MOCK_COMPLIANCE_SERVICE,
                },
                "mock_services": local_mock_services(configured),
                "indexer": indexer_view,
                "warning": local_warning(configured),
            }
        return {
            "service": "veilpool-api",
            "version": __version__,
            "mode": "mock",
            "mock": True,
            "testnet_only": True,
            "chain_id": configured.chain_id,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "api_base": prefix,
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
            "warning": (
                "LOCAL DEMO / MOCK PROOF. No real funds, no real ZK, no real "
                "sanctions provider. Secret client material is never accepted."
            ),
        }

    return app


app = create_app()
