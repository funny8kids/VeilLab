from __future__ import annotations

from datetime import timedelta

from support import (
    DEFAULT_PROOF,
    POOL,
    create_deposit,
    create_quote,
    create_withdrawal,
    new_key,
    normal_address,
    nullifier,
    submit_payload,
    submit_withdrawal,
)
from veilpool_api.models import ComplianceCheck, WithdrawalQuote, utcnow


def test_withdrawal_flow_and_public_status(client):
    flow = create_withdrawal(client)
    withdrawal_id = flow["submit"]["withdrawal_id"]

    response = client.get(f"/api/v1/withdrawals/{withdrawal_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["tx_hash"].startswith("0x")
    assert body["nullifier_hash"] == flow["nullifier"]
    assert body["recipient_address"] == normal_address(2)
    assert body["mock"] is True

    by_nullifier = client.get(
        f"/api/v1/withdrawals/by-nullifier/{flow['nullifier']}"
    )
    assert by_nullifier.status_code == 200
    assert by_nullifier.json()["id"] == withdrawal_id


def test_double_spend_rejected(client):
    first = create_withdrawal(client, nullifier_hash=nullifier("same-nullifier"))
    assert first["submit"]["status"] == "submitted"
    assert first["submit"]["chain_status"] == "confirmed"

    second_quote_response = create_quote(client)
    assert second_quote_response.status_code == 200
    second = submit_withdrawal(
        client,
        quote=second_quote_response.json(),
        nullifier_hash=nullifier("same-nullifier"),
    )
    assert second.status_code == 409
    assert second.json()["code"] == "NULLIFIER_SPENT"


def test_quote_expiry_rejected(client):
    create_deposit(client)
    quote_response = create_quote(client)
    assert quote_response.status_code == 200
    quote = quote_response.json()

    with client.app.state.db.session() as session:
        row = session.get(WithdrawalQuote, quote["quote_id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()

    response = submit_withdrawal(
        client, quote=quote, nullifier_hash=nullifier("expired-quote")
    )
    assert response.status_code == 409
    assert response.json()["code"] == "QUOTE_EXPIRED"

    with client.app.state.db.session() as session:
        assert session.get(WithdrawalQuote, quote["quote_id"]).status == "expired"


def test_compliance_decision_expiry_rejected(client):
    create_deposit(client)
    quote_response = create_quote(client)
    assert quote_response.status_code == 200
    quote = quote_response.json()

    with client.app.state.db.session() as session:
        check = session.get(ComplianceCheck, quote["compliance"]["check_id"])
        check.expires_at = utcnow() - timedelta(seconds=1)
        row = session.get(WithdrawalQuote, quote["quote_id"])
        row.expires_at = utcnow() + timedelta(seconds=300)
        session.commit()

    response = submit_withdrawal(
        client, quote=quote, nullifier_hash=nullifier("expired-check")
    )
    assert response.status_code == 409
    assert response.json()["code"] == "COMPLIANCE_EXPIRED"


def test_stale_root_rejected(client):
    create_deposit(client)
    quote_response = create_quote(client)
    assert quote_response.status_code == 200
    quote = quote_response.json()

    response = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("stale-root"),
        root="0x" + "9" * 64,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ROOT_STALE"


def test_fee_mismatch_rejected(client):
    create_deposit(client)
    quote_response = create_quote(client)
    assert quote_response.status_code == 200
    quote = quote_response.json()

    response = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("fee-mismatch"),
        fee_wei="1",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PROOF_INVALID"


def test_invalid_proof_shape_rejected(client):
    create_deposit(client)
    quote_response = create_quote(client)
    assert quote_response.status_code == 200
    quote = quote_response.json()
    payload = submit_payload(
        client,
        quote=quote,
        nullifier_hash=nullifier("bad-proof"),
        proof="0x12",
    )
    response = client.post(
        "/api/v1/withdrawals/submit",
        json=payload,
        headers={"Idempotency-Key": new_key()},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_submit_is_idempotent(client):
    create_deposit(client)
    quote_response = create_quote(client)
    quote = quote_response.json()
    key = new_key()

    first = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("idem-submit"),
        key=key,
    )
    assert first.status_code == 202
    second = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("idem-submit"),
        key=key,
    )
    assert second.status_code == 202
    assert second.json()["withdrawal_id"] == first.json()["withdrawal_id"]
    assert second.json()["tx_hash"] == first.json()["tx_hash"]


def test_unknown_withdrawal_is_404(client):
    response = client.get("/api/v1/withdrawals/wdr_missing")
    assert response.status_code == 404
    assert response.json()["code"] == "WITHDRAWAL_NOT_FOUND"


def test_proof_must_be_hex(client):
    create_deposit(client)
    quote_response = create_quote(client)
    quote = quote_response.json()
    response = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("hex"),
        proof="not-hex",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
