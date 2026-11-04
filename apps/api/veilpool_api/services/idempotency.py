from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import IdempotencyRecord


def fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find(db: Session, scope: str, key: str) -> IdempotencyRecord | None:
    return db.get(IdempotencyRecord, (scope, key))


def check_replay(
    db: Session,
    *,
    scope: str,
    key: str,
    payload: dict[str, Any],
) -> IdempotencyRecord | None:
    record = find(db, scope, key)
    if record is None:
        return None
    if record.request_hash != fingerprint(payload):
        raise ApiError(
            409,
            "IDEMPOTENCY_MISMATCH",
            "This Idempotency-Key was already used with a different request body.",
        )
    return record


def replay(record: IdempotencyRecord) -> JSONResponse:
    return JSONResponse(status_code=record.status_code, content=record.response_json)


def remember(
    db: Session,
    *,
    scope: str,
    key: str,
    payload: dict[str, Any],
    status_code: int,
    response: dict[str, Any],
    resource_type: str,
    resource_id: str | None,
) -> IdempotencyRecord:
    record = IdempotencyRecord(
        scope=scope,
        key=key,
        request_hash=fingerprint(payload),
        status_code=status_code,
        response_json=response,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.add(record)
    db.flush()
    return record


def find_by_resource(
    db: Session, *, scope: str, resource_id: str
) -> IdempotencyRecord | None:
    return db.execute(
        select(IdempotencyRecord)
        .where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.resource_id == resource_id,
        )
        .limit(1)
    ).scalar_one_or_none()
