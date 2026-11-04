from __future__ import annotations

from sqlalchemy import select

from support import (
    create_intent,
    blocked_address,
    normal_address,
    review_address,
)
from veilpool_api.models import CompliancePolicy


def test_blocked_depositor(client):
    response = create_intent(client, depositor=blocked_address())
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "COMPLIANCE_BLOCKED"
    assert body["reasons"] == ["SANCTIONS_MATCH"]
    assert body["check_id"].startswith("cmp_")


def test_review_depositor(client):
    response = create_intent(client, depositor=review_address())
    assert response.status_code == 202
    body = response.json()
    assert body["code"] == "COMPLIANCE_REVIEW"
    assert body["decision"] == "review"
    assert body["review_id"].startswith("cmp_")
    assert body["compliance"]["reasons"] == ["WATCHLIST_REVIEW"]


def test_blocked_recipient_quote(client):
    response = client.post(
        "/api/v1/withdrawals/quote",
        json={
            "pool_id": "pool_eth_01",
            "recipient_address": blocked_address(2),
            "relayer_id": "rel_01",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "COMPLIANCE_BLOCKED"


def test_review_recipient_quote(client):
    response = client.post(
        "/api/v1/withdrawals/quote",
        json={
            "pool_id": "pool_eth_01",
            "recipient_address": review_address(2),
            "relayer_id": "rel_01",
        },
    )
    assert response.status_code == 202
    assert response.json()["code"] == "COMPLIANCE_REVIEW"


def test_per_transaction_limit(client):
    with client.app.state.db.session() as session:
        policy = session.execute(select(CompliancePolicy)).scalar_one()
        policy.per_tx_limit = 1
        session.commit()

    response = create_intent(client, depositor=normal_address(10))
    assert response.status_code == 403
    assert response.json()["code"] == "COMPLIANCE_BLOCKED"
    assert response.json()["reasons"] == ["LIMIT_PER_TX"]


def test_daily_limit_boundary(client):
    with client.app.state.db.session() as session:
        policy = session.execute(select(CompliancePolicy)).scalar_one()
        policy.per_tx_limit = 10**30
        policy.daily_deposit_limit = 100_000_000_000_000_000
        session.commit()

    depositor = normal_address(11)
    first = create_intent(client, depositor=depositor)
    assert first.status_code == 200, first.text

    second = create_intent(client, depositor=depositor)
    assert second.status_code == 403
    assert second.json()["reasons"] == ["LIMIT_DAILY"]


def test_compliance_policy_public_summary(client):
    response = client.get("/api/v1/compliance/policy")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["mock"] is True
    assert body["provider"] == "mock-fixture-v1"
    assert "per_tx_limit_wei" in body
    assert body["review_sla_hours"] == 24
