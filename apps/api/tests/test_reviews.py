from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from support import (
    ADMIN_HEADERS,
    assert_no_secret_keys,
    commitment,
    create_deposit,
    create_intent,
    create_quote,
    nullifier,
    review_address,
    submit_withdrawal,
)
from veilpool_api.models import AuditLog, ComplianceCheck, utcnow


def _create_review(client, *, depositor: str | None = None, recipient: str | None = None):
    if depositor is not None:
        response = create_intent(client, depositor=depositor)
    else:
        response = create_quote(client, recipient=recipient)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["code"] == "COMPLIANCE_REVIEW"
    assert body["review_id"].startswith("cmp_")
    return body["review_id"]


def _decide(client, review_id: str, decision: str, *, reason: str = "manual review", **extra):
    return client.post(
        f"/api/v1/admin/compliance/reviews/{review_id}/decision",
        json={"decision": decision, "reason": reason, **extra},
        headers=ADMIN_HEADERS,
    )


def test_review_queue_lists_pending_without_raw_address_or_secret_fields(client):
    address = review_address(41)
    review_id = _create_review(client, depositor=address)

    response = client.get(
        "/api/v1/admin/compliance/reviews", headers=ADMIN_HEADERS
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] >= 1
    item = next(item for item in body["items"] if item["review_id"] == review_id)
    assert item["status"] == "pending"
    assert item["subject_type"] == "deposit"
    assert item["reason_codes"] == ["WATCHLIST_REVIEW"]
    assert item["reviewer"] is None
    assert item["mock"] is True
    assert address.lower() not in response.text
    assert_no_secret_keys(body)

    # Admin authentication is still required.
    unauthorized = client.get("/api/v1/admin/compliance/reviews")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "ADMIN_UNAUTHORIZED"


def test_approved_review_unblocks_retried_deposit_and_is_audited(client):
    address = review_address(42)
    review_id = _create_review(client, depositor=address)

    decision = _decide(
        client,
        review_id,
        "approve",
        reason="false positive cleared",
        expires_in_seconds=3600,
    )
    assert decision.status_code == 200, decision.text
    body = decision.json()
    assert body["status"] == "approved"
    assert body["decision"] == "allow"
    assert body["reviewed_by"] == "admin-token"
    assert body["reason"] == "false positive cleared"
    assert body["audited"] is True
    assert body["expires_at"]

    # The retried flow uses the same public address fields; no note is needed.
    retry = create_intent(client, depositor=address)
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["compliance"]["decision"] == "allow"
    assert "REVIEW_APPROVED" in retry_body["compliance"]["reasons"]
    assert_no_secret_keys(retry_body)

    deposit = client.post(
        "/api/v1/mock/deposits",
        json={
            "intent_id": retry_body["intent_id"],
            "commitment": commitment("approved-review-deposit"),
        },
    )
    assert deposit.status_code == 201, deposit.text
    assert deposit.json()["status"] == "confirmed"

    pending = client.get(
        "/api/v1/admin/compliance/reviews", headers=ADMIN_HEADERS
    ).json()
    assert all(item["review_id"] != review_id for item in pending["items"])

    approved = client.get(
        "/api/v1/admin/compliance/reviews?status=approved",
        headers=ADMIN_HEADERS,
    ).json()
    approved_item = next(
        item for item in approved["items"] if item["review_id"] == review_id
    )
    assert approved_item["reason"] == "false positive cleared"

    with client.app.state.db.session() as session:
        rows = list(
            session.execute(
                select(AuditLog)
                .where(AuditLog.action == "compliance.review.approved")
                .order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc())
            ).scalars()
        )
        assert len(rows) == 1
        assert rows[0].actor_type == "admin"
        assert rows[0].resource_id == review_id
        assert rows[0].decision == "allow"
        assert rows[0].reason == "false positive cleared"
        assert rows[0].meta["review_id"] == review_id
        previous = None
        for row in session.execute(
            select(AuditLog).order_by(
                AuditLog.occurred_at.asc(), AuditLog.id.asc()
            )
        ).scalars():
            assert row.prev_hash == previous
            previous = row.hash


def test_approved_review_unblocks_retried_withdrawal(client):
    create_deposit(client)
    address = review_address(43)
    review_id = _create_review(client, recipient=address)

    decision = _decide(client, review_id, "approve", reason="cleared by operator")
    assert decision.status_code == 200, decision.text

    retry_quote = create_quote(client, recipient=address)
    assert retry_quote.status_code == 200, retry_quote.text
    quote = retry_quote.json()
    assert quote["compliance"]["decision"] == "allow"

    submitted = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("approved-review-withdrawal"),
        recipient=address,
    )
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["chain_status"] == "confirmed"


def test_rejected_review_blocks_retried_flow(client):
    address = review_address(44)
    review_id = _create_review(client, depositor=address)

    decision = _decide(client, review_id, "reject", reason="confirmed watchlist hit")
    assert decision.status_code == 200, decision.text
    body = decision.json()
    assert body["status"] == "rejected"
    assert body["decision"] == "block"
    assert body["reason"] == "confirmed watchlist hit"

    retry = create_intent(client, depositor=address)
    assert retry.status_code == 403
    assert retry.json()["code"] == "COMPLIANCE_BLOCKED"
    assert retry.json()["reasons"] == ["REVIEW_REJECTED"]

    with client.app.state.db.session() as session:
        row = session.execute(
            select(AuditLog).where(
                AuditLog.action == "compliance.review.rejected"
            )
        ).scalar_one()
        assert row.decision == "block"
        assert row.reason == "confirmed watchlist hit"


def test_review_decision_expires_and_flow_needs_new_review(client):
    address = review_address(45)
    review_id = _create_review(client, depositor=address)
    decision = _decide(
        client,
        review_id,
        "approve",
        reason="short approval",
        expires_in_seconds=1,
    )
    assert decision.status_code == 200, decision.text

    with client.app.state.db.session() as session:
        check = session.get(ComplianceCheck, review_id)
        check.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()

    retry = create_intent(client, depositor=address)
    assert retry.status_code == 202
    assert retry.json()["code"] == "COMPLIANCE_REVIEW"
    assert retry.json()["review_id"] != review_id


def test_review_decision_validation_and_admin_auth(client):
    address = review_address(46)
    review_id = _create_review(client, depositor=address)

    unauthorized = client.post(
        f"/api/v1/admin/compliance/reviews/{review_id}/decision",
        json={"decision": "approve", "reason": "no token"},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "ADMIN_UNAUTHORIZED"

    missing_reason = client.post(
        f"/api/v1/admin/compliance/reviews/{review_id}/decision",
        json={"decision": "approve"},
        headers=ADMIN_HEADERS,
    )
    assert missing_reason.status_code == 422
    assert missing_reason.json()["code"] == "VALIDATION_ERROR"

    blank_reason = client.post(
        f"/api/v1/admin/compliance/reviews/{review_id}/decision",
        json={"decision": "approve", "reason": "   "},
        headers=ADMIN_HEADERS,
    )
    assert blank_reason.status_code == 422
    assert blank_reason.json()["code"] == "VALIDATION_ERROR"

    bad_decision = _decide(client, review_id, "maybe", reason="invalid")
    assert bad_decision.status_code == 422
    assert bad_decision.json()["code"] == "VALIDATION_ERROR"

    unknown = _decide(client, "cmp_missing", "approve", reason="unknown")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "REVIEW_NOT_FOUND"

    secret = "note-v1:super-secret"
    note_field = client.post(
        f"/api/v1/admin/compliance/reviews/{review_id}/decision",
        json={
            "decision": "approve",
            "reason": "should fail",
            "note": secret,
        },
        headers=ADMIN_HEADERS,
    )
    assert note_field.status_code == 422
    assert secret not in note_field.text

    first = _decide(client, review_id, "approve", reason="valid decision")
    assert first.status_code == 200, first.text
    second = _decide(client, review_id, "reject", reason="double decision")
    assert second.status_code == 409
    assert second.json()["code"] == "REVIEW_ALREADY_DECIDED"


def test_review_decision_accepts_absolute_expiry(client):
    review_id = _create_review(client, depositor=review_address(47))
    expiry = (utcnow() + timedelta(hours=1)).isoformat() + "Z"
    response = _decide(
        client,
        review_id,
        "approve",
        reason="absolute expiry",
        expires_at=expiry,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["expires_at"]

    conflicting = {
        "decision": "approve",
        "reason": "two expiries",
        "expires_in_seconds": 60,
        "expires_at": expiry,
    }
    review_id = _create_review(client, depositor=review_address(48))
    response = client.post(
        f"/api/v1/admin/compliance/reviews/{review_id}/decision",
        json=conflicting,
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_review_list_rejects_invalid_status_filter(client):
    response = client.get(
        "/api/v1/admin/compliance/reviews?status=unknown",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
