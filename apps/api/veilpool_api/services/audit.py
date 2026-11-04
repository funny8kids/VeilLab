from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ids import new_id
from ..models import AuditLog, iso_z, utcnow


def append_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    actor_type: str,
    actor_id: str | None = None,
    resource_id: str | None = None,
    decision: str | None = None,
    reason: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append a hash-chained audit row.

    There is no update/delete path in the application. SQLite deployments also
    install triggers that reject UPDATE/DELETE on ``audit_log``.
    """

    previous = db.execute(
        select(AuditLog)
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    occurred_at = utcnow()
    meta = metadata or {}
    payload = {
        "occurred_at": iso_z(occurred_at),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "decision": decision,
        "reason": reason,
        "request_id": request_id,
        "trace_id": trace_id,
        "metadata": meta,
        "prev_hash": previous.hash if previous else None,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()
    row = AuditLog(
        id=new_id("aud"),
        occurred_at=occurred_at,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        reason=reason,
        request_id=request_id,
        trace_id=trace_id,
        meta=meta,
        prev_hash=previous.hash if previous else None,
        hash=digest,
    )
    db.add(row)
    db.flush()
    return row
