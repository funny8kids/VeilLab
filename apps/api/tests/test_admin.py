from __future__ import annotations

from sqlalchemy import select

from support import (
    ADMIN_HEADERS,
    POOL,
    create_deposit,
    create_intent,
    create_quote,
    new_key,
    normal_address,
    nullifier,
    submit_withdrawal,
)
from veilpool_api.models import AuditLog


def test_pause_and_resume_are_audited(client):
    pause = client.post(
        f"/api/v1/admin/pools/{POOL}/pause",
        json={"reason": "maintenance window"},
        headers=ADMIN_HEADERS,
    )
    assert pause.status_code == 200, pause.text
    assert pause.json()["status"] == "paused"
    assert pause.json()["audited"] is True

    paused_pool = client.get(f"/api/v1/pools/{POOL}")
    assert paused_pool.json()["status"] == "paused"

    blocked_intent = create_intent(client)
    assert blocked_intent.status_code == 409
    assert blocked_intent.json()["code"] == "POOL_PAUSED"

    blocked_quote = create_quote(client)
    assert blocked_quote.status_code == 409
    assert blocked_quote.json()["code"] == "POOL_PAUSED"

    resume = client.post(
        f"/api/v1/admin/pools/{POOL}/resume",
        json={},
        headers=ADMIN_HEADERS,
    )
    assert resume.status_code == 200
    assert resume.json()["status"] == "active"
    assert client.get(f"/api/v1/pools/{POOL}").json()["status"] == "active"

    with client.app.state.db.session() as session:
        rows = list(
            session.execute(
                select(AuditLog)
                .where(AuditLog.action.in_(["pool.pause", "pool.resume"]))
                .order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc())
            ).scalars()
        )
    assert [row.action for row in rows] == ["pool.pause", "pool.resume"]
    assert rows[0].reason == "maintenance window"
    previous_hash = None
    for row in rows:
        assert row.prev_hash == previous_hash
        previous_hash = row.hash


def test_admin_requires_token(client):
    response = client.post(
        f"/api/v1/admin/pools/{POOL}/pause",
        json={"reason": "unauthorized"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "ADMIN_UNAUTHORIZED"

    wrong = client.post(
        f"/api/v1/admin/pools/{POOL}/pause",
        json={"reason": "wrong"},
        headers={"X-Admin-Token": "nope"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "ADMIN_UNAUTHORIZED"


def test_pause_blocks_submit_mid_flow(client):
    create_deposit(client)
    quote_response = create_quote(client)
    assert quote_response.status_code == 200
    quote = quote_response.json()

    pause = client.post(
        f"/api/v1/admin/pools/{POOL}/pause",
        json={"reason": "paused before submit"},
        headers=ADMIN_HEADERS,
    )
    assert pause.status_code == 200

    response = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("paused-mid-flow"),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "POOL_PAUSED"


def test_audit_log_is_hash_chained(client):
    create_intent(client, depositor=normal_address(21))
    create_intent(client, depositor=normal_address(22))
    with client.app.state.db.session() as session:
        rows = list(
            session.execute(
                select(AuditLog).order_by(
                    AuditLog.occurred_at.asc(), AuditLog.id.asc()
                )
            ).scalars()
        )
    assert len(rows) >= 2
    previous_hash = None
    for row in rows:
        assert row.prev_hash == previous_hash
        assert len(row.hash) == 64
        previous_hash = row.hash


def test_admin_pause_unknown_pool(client):
    response = client.post(
        "/api/v1/admin/pools/pool_missing/pause",
        json={"reason": "x"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "POOL_NOT_FOUND"
