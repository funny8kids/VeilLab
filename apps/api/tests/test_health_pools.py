from __future__ import annotations

from support import assert_no_secret_keys

EXPECTED = {
    "pool_eth_01": ("ETH", "0.1", "100000000000000000"),
    "pool_eth_1": ("ETH", "1", "1000000000000000000"),
    "pool_eth_10": ("ETH", "10", "10000000000000000000"),
    "pool_usdc_100": ("USDC", "100", "100000000"),
    "pool_usdc_1000": ("USDC", "1000", "1000000000"),
    "pool_btc_001": ("tBTC", "0.01", "10000000000000000"),
}


def test_health_and_root_are_labeled_mock(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert body["mock"] is True
    assert body["testnet_only"] is True
    assert body["chain_id"] == 11155111
    assert "MOCK_CHAIN" in body["services"]["chain"]
    assert "MOCK_VERIFIER" in body["services"]["verifier"]

    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["mock"] is True
    assert "MOCK PROOF" in root.json()["warning"]


def test_six_seeded_pools(client):
    response = client.get("/api/v1/pools")
    assert response.status_code == 200
    body = response.json()
    assert body["mock"] is True
    assert len(body["items"]) == 6
    by_id = {item["id"]: item for item in body["items"]}
    assert set(by_id) == set(EXPECTED)
    for pool_id, (asset, denomination, denomination_wei) in EXPECTED.items():
        item = by_id[pool_id]
        assert item["asset"] == asset
        assert item["denomination"] == denomination
        assert item["denomination_wei"] == denomination_wei
        assert item["chain_id"] == 11155111
        assert item["status"] == "active"
        assert item["mock"] is True


def test_pool_detail_and_root(client):
    detail = client.get("/api/v1/pools/pool_eth_01")
    assert detail.status_code == 200
    body = detail.json()
    assert body["tree_depth"] == 20
    assert body["contract_address"].startswith("0x")
    assert body["verifier_address"].startswith("0x")
    assert body["finality"] == "mock"
    assert body["root"].startswith("0x")
    assert len(body["root"]) == 66

    root = client.get("/api/v1/pools/pool_eth_01/root")
    assert root.status_code == 200
    root_body = root.json()
    assert root_body["root"] == body["root"]
    assert root_body["root_history"]
    assert root_body["root_history"][-1]["root"] == root_body["root"]


def test_unknown_pool_is_404(client):
    response = client.get("/api/v1/pools/pool_missing")
    assert response.status_code == 404
    assert response.json()["code"] == "POOL_NOT_FOUND"
    assert response.headers["content-type"].startswith("application/problem+json")


def test_notes_endpoint_is_not_exposed(client):
    response = client.get("/api/v1/notes")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.headers["content-type"].startswith("application/problem+json")


def test_public_payloads_have_no_secret_fields(client):
    paths = [
        "/",
        "/api/v1/health",
        "/api/v1/pools",
        "/api/v1/pools/pool_eth_01",
        "/api/v1/pools/pool_eth_01/root",
        "/api/v1/relayers",
        "/api/v1/relayers/rel_01",
        "/api/v1/compliance/policy",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert_no_secret_keys(response.json(), path)
