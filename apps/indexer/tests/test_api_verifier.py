from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chain_fixtures import C1, N1, chain_a
from fake_chain import FakeRpc
from veilpool_indexer.api import create_app
from veilpool_indexer.config import ConfigError
from veilpool_indexer.store import Store


@pytest.mark.parametrize(
    ("kind", "is_mock", "phrase"),
    [
        ("mock", True, "MOCK VERIFIER"),
        ("groth16", False, "GROTH16 VERIFIER"),
    ],
)
def test_verifier_kind_is_reflected_in_health_and_envelopes(
    settings, store, make_indexer, kind, is_mock, phrase
):
    configured = settings.with_overrides(verifier_kind=kind)
    indexer = make_indexer(FakeRpc(chain_a()))
    indexer.sync_once()
    client = TestClient(create_app(configured, store))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["verifier_kind"] == kind
    assert health.json()["mock_verifier"] is is_mock
    assert phrase in health.json()["disclaimer"]

    responses = [
        client.get("/pools"),
        client.get("/pools/pool_eth_01/deposits"),
        client.get("/pools/pool_eth_01/roots"),
        client.get(f"/pools/pool_eth_01/path/{C1}"),
        client.get(f"/withdrawals/{N1}"),
    ]
    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert body["verifier_kind"] == kind
        assert body["mock_verifier"] is is_mock
        assert phrase in body["disclaimer"]


def test_create_app_rejects_an_unknown_verifier_kind(settings, tmp_path):
    # Bypass Settings.validate to assert create_app fails fast as a second gate.
    from dataclasses import replace

    invalid = replace(settings, verifier_kind="bogus")
    store = Store(tmp_path / "invalid.db")
    store.initialize()
    with pytest.raises(ConfigError):
        create_app(invalid, store)
