from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi.testclient import TestClient

POOL = "pool_eth_01"
AMOUNT = "0.1"
DEFAULT_PROOF = "0x" + "ab" * 128
ADMIN_HEADERS = {"X-Admin-Token": "dev-admin"}


def normal_address(seed: int = 1) -> str:
    return "0x" + f"{seed:040x}"[-40:]


def blocked_address(seed: int = 1) -> str:
    return "0xbad" + f"{seed:037x}"


def review_address(seed: int = 1) -> str:
    return "0xdead" + f"{seed:036x}"


def commitment(seed: str = "commitment") -> str:
    return "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def nullifier(seed: str = "nullifier") -> str:
    return "0x" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def new_key() -> str:
    return str(uuid.uuid4())


def intent_payload(
    *,
    pool_id: str = POOL,
    amount: str = AMOUNT,
    depositor: str | None = None,
) -> dict[str, Any]:
    return {
        "pool_id": pool_id,
        "depositor_address": depositor or normal_address(1),
        "amount": amount,
    }


def create_intent(
    client: TestClient,
    *,
    pool_id: str = POOL,
    amount: str = AMOUNT,
    depositor: str | None = None,
    key: str | None = None,
):
    return client.post(
        "/api/v1/deposits/intent",
        json=intent_payload(pool_id=pool_id, amount=amount, depositor=depositor),
        headers={"Idempotency-Key": key or new_key()},
    )


def create_deposit(
    client: TestClient,
    *,
    pool_id: str = POOL,
    amount: str = AMOUNT,
    depositor: str | None = None,
    commitment_seed: str = "deposit-1",
):
    intent_response = create_intent(
        client, pool_id=pool_id, amount=amount, depositor=depositor
    )
    assert intent_response.status_code == 200, intent_response.text
    intent = intent_response.json()
    deposit_response = client.post(
        "/api/v1/mock/deposits",
        json={
            "intent_id": intent["intent_id"],
            "commitment": commitment(commitment_seed),
        },
    )
    assert deposit_response.status_code == 201, deposit_response.text
    return {"intent": intent, "deposit": deposit_response.json()}


def create_quote(
    client: TestClient,
    *,
    pool_id: str = POOL,
    recipient: str | None = None,
    relayer_id: str = "rel_01",
):
    return client.post(
        "/api/v1/withdrawals/quote",
        json={
            "pool_id": pool_id,
            "recipient_address": recipient or normal_address(2),
            "relayer_id": relayer_id,
        },
    )


def submit_payload(
    client: TestClient,
    *,
    quote: dict[str, Any],
    nullifier_hash: str,
    recipient: str | None = None,
    root: str | None = None,
    fee_wei: str | None = None,
    proof: str = DEFAULT_PROOF,
) -> dict[str, Any]:
    recipient = recipient or normal_address(2)
    if root is None:
        root = client.get(
            f"/api/v1/pools/{quote['pool_id']}/root"
        ).json()["root"]
    return {
        "pool_id": quote["pool_id"],
        "quote_id": quote["quote_id"],
        "proof": proof,
        "public_signals": {
            "root": root,
            "nullifier_hash": nullifier_hash,
            "recipient": recipient,
            "fee_wei": fee_wei or quote["relayer_fee_wei"],
        },
        "recipient_address": recipient,
    }


def submit_withdrawal(
    client: TestClient,
    *,
    quote: dict[str, Any],
    nullifier_hash: str,
    recipient: str | None = None,
    key: str | None = None,
    **kwargs: Any,
):
    return client.post(
        "/api/v1/withdrawals/submit",
        json=submit_payload(
            client,
            quote=quote,
            nullifier_hash=nullifier_hash,
            recipient=recipient,
            **kwargs,
        ),
        headers={"Idempotency-Key": key or new_key()},
    )


def create_withdrawal(
    client: TestClient,
    *,
    deposit: bool = True,
    recipient: str | None = None,
    nullifier_hash: str | None = None,
):
    if deposit:
        create_deposit(client)
    quote_response = create_quote(client, recipient=recipient)
    assert quote_response.status_code == 200, quote_response.text
    quote = quote_response.json()
    nullifier_hash = nullifier_hash or nullifier("withdrawal-1")
    submit_response = submit_withdrawal(
        client, quote=quote, nullifier_hash=nullifier_hash, recipient=recipient
    )
    assert submit_response.status_code == 202, submit_response.text
    return {
        "quote": quote,
        "submit": submit_response.json(),
        "nullifier": nullifier_hash,
    }


def assert_no_secret_keys(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            for marker in ("note", "passphrase", "secret", "mnemonic"):
                assert marker not in lowered, f"secret-like key at {path}.{key}"
            assert_no_secret_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_secret_keys(child, f"{path}[{index}]")
