from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from support import (
    AMOUNT,
    POOL,
    assert_no_secret_keys,
    commitment,
    create_deposit,
    create_intent,
    intent_payload,
    new_key,
    normal_address,
)
from veilpool_api.models import DepositIntent, utcnow


def test_exact_denomination_enforced(client):
    high = create_intent(client, amount="0.2")
    assert high.status_code == 422
    assert high.json()["code"] == "AMOUNT_MISMATCH"

    low = create_intent(client, amount="0.05")
    assert low.status_code == 422
    assert low.json()["code"] == "AMOUNT_MISMATCH"

    exact = create_intent(client, amount="0.1")
    assert exact.status_code == 200
    assert exact.json()["denomination_wei"] == "100000000000000000"

    usdc = create_intent(
        client, pool_id="pool_usdc_100", amount="100.0"
    )
    assert usdc.status_code == 200
    assert usdc.json()["denomination_wei"] == "100000000"

    wrong_usdc = create_intent(
        client, pool_id="pool_usdc_100", amount="99"
    )
    assert wrong_usdc.status_code == 422
    assert wrong_usdc.json()["code"] == "AMOUNT_MISMATCH"


def test_note_and_unknown_fields_are_rejected(client):
    secret = "note-v1:super-secret-value"
    payload = intent_payload()
    payload["note"] = secret
    response = client.post(
        "/api/v1/deposits/intent",
        json=payload,
        headers={"Idempotency-Key": new_key()},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert secret not in response.text
    assert "note" in response.text.lower()

    unknown = intent_payload()
    unknown["backup_blob"] = "whatever"
    response = client.post(
        "/api/v1/deposits/intent",
        json=unknown,
        headers={"Idempotency-Key": new_key()},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

    nested = {
        "intent_id": "dep_missing",
        "commitment": commitment("nested"),
        "secret_note": secret,
    }
    response = client.post("/api/v1/mock/deposits", json=nested)
    assert response.status_code == 422
    assert secret not in response.text


def test_deposit_intent_accepts_public_commitment(client):
    payload = intent_payload(depositor=normal_address(8))
    payload["commitment"] = commitment("intent-commitment")
    response = client.post(
        "/api/v1/deposits/intent",
        json=payload,
        headers={"Idempotency-Key": new_key()},
    )
    assert response.status_code == 200, response.text
    assert response.json()["commitment"] == commitment("intent-commitment")

    mismatch = client.post(
        "/api/v1/mock/deposits",
        json={
            "intent_id": response.json()["intent_id"],
            "commitment": commitment("different-commitment"),
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "COMMITMENT_MISMATCH"


def test_deposit_intent_is_idempotent(client):
    key = new_key()
    first = client.post(
        "/api/v1/deposits/intent",
        json=intent_payload(depositor=normal_address(9)),
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/deposits/intent",
        json=intent_payload(depositor=normal_address(9)),
        headers={"Idempotency-Key": key},
    )
    assert second.status_code == 200
    assert second.json()["intent_id"] == first.json()["intent_id"]
    assert second.json()["compliance"]["check_id"] == first.json()["compliance"][
        "check_id"
    ]


def test_mock_deposit_flow(client):
    before = client.get(f"/api/v1/pools/{POOL}/root").json()["root"]
    flow = create_deposit(client)
    deposit = flow["deposit"]

    assert deposit["status"] == "confirmed"
    assert deposit["leaf_index"] == 0
    assert deposit["commitment"] == commitment("deposit-1")
    assert deposit["mock"] is True

    after = client.get(f"/api/v1/pools/{POOL}/root").json()
    assert after["root"] != before
    assert len(after["root_history"]) >= 2

    lookup = client.get(f"/api/v1/pools/{POOL}/deposits/{deposit['tx_hash']}")
    assert lookup.status_code == 200
    assert lookup.json()["commitment"] == deposit["commitment"]
    assert lookup.json()["status"] == "confirmed"
    assert_no_secret_keys(lookup.json())

    replay = client.post(
        "/api/v1/mock/deposits",
        json={
            "intent_id": flow["intent"]["intent_id"],
            "commitment": commitment("deposit-1"),
        },
    )
    assert replay.status_code == 409
    assert replay.json()["code"] == "INTENT_CONSUMED"


def test_expired_intent_is_rejected(client):
    intent_response = create_intent(client)
    assert intent_response.status_code == 200
    intent_id = intent_response.json()["intent_id"]

    with client.app.state.db.session() as session:
        intent = session.get(DepositIntent, intent_id)
        intent.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()

    response = client.post(
        "/api/v1/mock/deposits",
        json={
            "intent_id": intent_id,
            "commitment": commitment("expired"),
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "INTENT_EXPIRED"

    with client.app.state.db.session() as session:
        assert session.get(DepositIntent, intent_id).status == "expired"


def test_deposit_lookup_unknown_transaction(client):
    response = client.get(f"/api/v1/pools/{POOL}/deposits/0x{'1' * 64}")
    assert response.status_code == 404
    assert response.json()["code"] == "DEPOSIT_NOT_FOUND"


def test_mock_deposit_list_remains_db_backed(client):
    flow = create_deposit(client)
    response = client.get(f"/api/v1/pools/{POOL}/deposits")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chain_source"] == "mock"
    assert body["mock"] is True
    assert body["count"] == 1
    assert body["items"][0]["tx_hash"] == flow["deposit"]["tx_hash"]
    assert body["items"][0]["commitment"] == flow["deposit"]["commitment"]
    assert body["items"][0]["pool_id"] == POOL
