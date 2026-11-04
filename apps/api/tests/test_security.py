from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

from fastapi.testclient import TestClient

from support import (
    ADMIN_HEADERS,
    AMOUNT,
    POOL,
    create_deposit,
    create_intent,
    create_quote,
    intent_payload,
    new_key,
    normal_address,
    nullifier,
    submit_withdrawal,
)
from veilpool_api.config import Settings
from veilpool_api.main import create_app

PUBLIC_PATHS = (
    "/api/v1/health",
    "/api/v1/pools",
    f"/api/v1/pools/{POOL}",
    f"/api/v1/pools/{POOL}/root",
    "/api/v1/relayers",
    "/api/v1/relayers/rel_01",
    "/api/v1/compliance/policy",
)


@contextmanager
def client_with(settings: Settings, **overrides):
    with TestClient(create_app(replace(settings, **overrides))) as client:
        yield client


def _intent_request(client: TestClient, *, token: str | None = None, address: str | None = None):
    headers = {"Idempotency-Key": new_key()}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        "/api/v1/deposits/intent",
        json=intent_payload(depositor=address or normal_address(1)),
        headers=headers,
    )


def test_auth_off_by_default_keeps_demo_flows_open(client):
    assert client.app.state.settings.require_auth is False

    intent = create_intent(client)
    assert intent.status_code == 200, intent.text

    quote = create_quote(client)
    assert quote.status_code == 200, quote.text

    # Non-public read endpoints work without auth in local demo mode.
    unknown = client.get("/api/v1/withdrawals/wdr_missing")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "WITHDRAWAL_NOT_FOUND"


def test_auth_enabled_keeps_public_endpoints_public(settings):
    with client_with(settings, require_auth=True, api_token="test-api-token") as client:
        for path in PUBLIC_PATHS:
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"


def test_auth_enabled_requires_valid_bearer(settings):
    with client_with(settings, require_auth=True, api_token="test-api-token") as client:
        missing = _intent_request(client)
        assert missing.status_code == 401
        assert missing.json()["code"] == "AUTH_REQUIRED"
        assert missing.headers["www-authenticate"] == "Bearer"
        assert missing.headers["cache-control"] == "no-store"
        assert missing.headers["x-content-type-options"] == "nosniff"

        wrong = _intent_request(client, token="wrong-token")
        assert wrong.status_code == 401
        assert wrong.json()["code"] == "AUTH_REQUIRED"

        basic = client.post(
            "/api/v1/deposits/intent",
            json=intent_payload(),
            headers={
                "Idempotency-Key": new_key(),
                "Authorization": "Basic dXNlcjpwYXNz",
            },
        )
        assert basic.status_code == 401
        assert basic.json()["code"] == "AUTH_REQUIRED"

        valid = _intent_request(client, token="test-api-token")
        assert valid.status_code == 200, valid.text
        assert valid.headers["cache-control"] == "no-store"

    with client_with(settings, require_auth=True, api_token="test-api-token") as client:
        quote_missing = create_quote(client)
        assert quote_missing.status_code == 401
        assert quote_missing.json()["code"] == "AUTH_REQUIRED"

        quote_valid = client.post(
            "/api/v1/withdrawals/quote",
            json={
                "pool_id": POOL,
                "recipient_address": normal_address(3),
                "relayer_id": "rel_01",
            },
            headers={"Authorization": "Bearer test-api-token"},
        )
        assert quote_valid.status_code == 200, quote_valid.text


def test_auth_enabled_admin_requires_bearer_and_admin_token(settings):
    bearer = {"Authorization": "Bearer test-api-token"}
    with client_with(settings, require_auth=True, api_token="test-api-token") as client:
        no_bearer = client.post(
            f"/api/v1/admin/pools/{POOL}/pause",
            json={"reason": "test"},
            headers=ADMIN_HEADERS,
        )
        assert no_bearer.status_code == 401
        assert no_bearer.json()["code"] == "AUTH_REQUIRED"

        no_admin = client.post(
            f"/api/v1/admin/pools/{POOL}/pause",
            json={"reason": "test"},
            headers=bearer,
        )
        assert no_admin.status_code == 401
        assert no_admin.json()["code"] == "ADMIN_UNAUTHORIZED"

        both = client.post(
            f"/api/v1/admin/pools/{POOL}/pause",
            json={"reason": "test"},
            headers={**bearer, **ADMIN_HEADERS},
        )
        assert both.status_code == 200, both.text
        assert both.json()["status"] == "paused"
        assert both.headers["cache-control"] == "no-store"

        reviews = client.get(
            "/api/v1/admin/compliance/reviews",
            headers={**bearer, **ADMIN_HEADERS},
        )
        assert reviews.status_code == 200, reviews.text


def test_auth_enabled_still_rejects_note_fields(settings):
    secret = "note-v1:do-not-accept"
    payload = intent_payload()
    payload["note"] = secret
    with client_with(settings, require_auth=True, api_token="test-api-token") as client:
        response = client.post(
            "/api/v1/deposits/intent",
            json=payload,
            headers={
                "Idempotency-Key": new_key(),
                "Authorization": "Bearer test-api-token",
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert secret not in response.text


def test_rate_limit_deposit_intent(settings):
    with client_with(settings, rate_limit_deposit_intent=1) as client:
        first = create_intent(client)
        assert first.status_code == 200, first.text
        assert first.headers["x-ratelimit-limit"] == "1"
        assert first.headers["x-ratelimit-scope"] == "deposit_intent"

        second = create_intent(client)
        assert second.status_code == 429
        body = second.json()
        assert body["code"] == "RATE_LIMITED"
        assert body["status"] == 429
        assert int(second.headers["retry-after"]) >= 1
        assert second.headers["x-ratelimit-remaining"] == "0"
        assert second.headers["cache-control"] == "no-store"


def test_rate_limit_withdrawal_quote_and_submit(settings):
    with client_with(
        settings,
        rate_limit_withdrawal_quote=1,
        rate_limit_withdrawal_submit=1,
    ) as client:
        create_deposit(client)

        first_quote = create_quote(client)
        assert first_quote.status_code == 200, first_quote.text
        second_quote = create_quote(client)
        assert second_quote.status_code == 429
        assert second_quote.json()["code"] == "RATE_LIMITED"

    with client_with(
        settings,
        rate_limit_withdrawal_quote=10,
        rate_limit_withdrawal_submit=1,
    ) as client:
        create_deposit(client)
        quote = create_quote(client)
        assert quote.status_code == 200, quote.text

        first_submit = submit_withdrawal(
            client,
            quote=quote.json(),
            nullifier_hash=nullifier("rate-limit-submit"),
        )
        assert first_submit.status_code == 202, first_submit.text

        second_submit = submit_withdrawal(
            client,
            quote=quote.json(),
            nullifier_hash=nullifier("rate-limit-submit"),
        )
        assert second_submit.status_code == 429
        assert second_submit.json()["code"] == "RATE_LIMITED"


def test_rate_limit_compliance_policy(settings):
    with client_with(settings, rate_limit_compliance=2) as client:
        assert client.get("/api/v1/compliance/policy").status_code == 200
        assert client.get("/api/v1/compliance/policy").status_code == 200
        limited = client.get("/api/v1/compliance/policy")
        assert limited.status_code == 429
        assert limited.json()["code"] == "RATE_LIMITED"
        assert limited.headers["x-ratelimit-scope"] == "compliance"


def test_rate_limit_can_be_disabled(settings):
    with client_with(
        settings,
        rate_limit_enabled=False,
        rate_limit_deposit_intent=1,
    ) as client:
        assert create_intent(client).status_code == 200
        assert create_intent(client).status_code == 200


def test_body_size_limit(settings):
    huge = {
        "pool_id": POOL,
        "depositor_address": normal_address(1),
        "amount": AMOUNT,
        "padding": "x" * (70 * 1024),
    }
    with client_with(settings) as client:
        response = client.post(
            "/api/v1/deposits/intent",
            json=huge,
            headers={"Idempotency-Key": new_key()},
        )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


def test_body_size_limit_for_chunked_requests(settings):
    def chunks():
        for _ in range(8):
            yield b"x" * 64

    with client_with(settings, max_body_bytes=128) as client:
        response = client.post(
            "/api/v1/deposits/intent",
            content=chunks(),
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": new_key(),
            },
        )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


def test_security_headers_on_public_and_sensitive_responses(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["referrer-policy"] == "no-referrer"

    intent = create_intent(client)
    assert intent.status_code == 200
    assert intent.headers["cache-control"] == "no-store"
    assert intent.headers["x-content-type-options"] == "nosniff"
    assert intent.headers["referrer-policy"] == "no-referrer"


def test_deposit_after_rate_limit_still_works_in_new_app(settings):
    # A second app instance gets a fresh in-memory bucket store.
    with client_with(settings, rate_limit_deposit_intent=1) as first_client:
        assert create_intent(first_client).status_code == 200
        assert create_intent(first_client).status_code == 429
    with client_with(settings, rate_limit_deposit_intent=1) as second_client:
        assert create_intent(second_client).status_code == 200
