from __future__ import annotations

from support import (
    create_deposit,
    create_quote,
    intent_payload,
    new_key,
    nullifier,
    submit_payload,
    submit_withdrawal,
)


def test_deposit_intent_idempotency_mismatch(client):
    key = new_key()
    first = client.post(
        "/api/v1/deposits/intent",
        json=intent_payload(pool_id="pool_eth_01", amount="0.1"),
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/deposits/intent",
        json=intent_payload(pool_id="pool_eth_1", amount="1"),
        headers={"Idempotency-Key": key},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_MISMATCH"


def test_withdrawal_submit_idempotency_mismatch(client):
    create_deposit(client)
    quote = create_quote(client).json()
    key = new_key()

    first = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("idem-mismatch"),
        key=key,
    )
    assert first.status_code == 202, first.text

    mismatched = submit_withdrawal(
        client,
        quote=quote,
        nullifier_hash=nullifier("idem-mismatch"),
        key=key,
        proof="0x" + "cd" * 128,
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["code"] == "IDEMPOTENCY_MISMATCH"


def test_idempotency_key_is_required(client):
    response = client.post(
        "/api/v1/deposits/intent",
        json=intent_payload(),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    create_deposit(client)
    quote = create_quote(client).json()
    payload = submit_payload(
        client,
        quote=quote,
        nullifier_hash=nullifier("missing-key"),
    )
    response = client.post("/api/v1/withdrawals/submit", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
