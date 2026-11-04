from __future__ import annotations

import hmac
from collections.abc import Iterator

from fastapi import Header, Request
from sqlalchemy.orm import Session

from .config import Settings
from .database import Database, ensure_database
from .errors import ApiError
from .indexer_client import IndexerClient
from .local_chain import LocalRpcClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_indexer_client(request: Request) -> IndexerClient | None:
    return request.app.state.indexer_client


def get_local_rpc_client(request: Request) -> LocalRpcClient | None:
    return request.app.state.local_rpc_client


def get_database(request: Request) -> Database:
    return ensure_database(request.app)


def get_db(request: Request) -> Iterator[Session]:
    database: Database = ensure_database(request.app)
    session = database.session()
    try:
        yield session
    finally:
        session.close()


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")


def require_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if idempotency_key is None or not idempotency_key.strip():
        raise ApiError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "The Idempotency-Key header is required for this endpoint.",
        )
    key = idempotency_key.strip()
    if len(key) > 128:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Idempotency-Key must be at most 128 characters.",
        )
    return key


def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    settings: Settings = request.app.state.settings
    supplied = x_admin_token or ""
    if not hmac.compare_digest(
        supplied.encode("utf-8"), settings.admin_token.encode("utf-8")
    ):
        raise ApiError(
            401,
            "ADMIN_UNAUTHORIZED",
            "A valid X-Admin-Token header is required.",
        )
