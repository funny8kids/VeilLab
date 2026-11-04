from __future__ import annotations

from fastapi.testclient import TestClient

from chain_fixtures import C1, C2, N1, POOL_ETH_01, R2, RECIPIENT, chain_a
from fake_chain import FakeRpc
from veilpool_indexer.api import create_app
from veilpool_indexer.store import Store


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        found = {str(key).lower() for key in value}
        for item in value.values():
            found |= _keys(item)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found |= _keys(item)
        return found
    return set()


def _indexed_client(settings, store, make_indexer) -> TestClient:
    indexer = make_indexer(FakeRpc(chain_a()))
    indexer.sync_once()
    return TestClient(create_app(settings, store))


def test_health_and_read_endpoints(settings, store, make_indexer):
    client = _indexed_client(settings, store, make_indexer)

    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["service"] == "veilpool-indexer"
    assert body["chain_id"] == 31337
    assert body["contract_address"] == settings.contract_address
    assert body["indexed_block"] == 3
    assert body["tip_block"] == 3
    assert body["lag"] == 0
    assert body["mock_verifier"] is True
    assert body["testnet_only"] is True
    assert body["event_counts"]["Deposit"] == 2
    assert "MOCK VERIFIER" in body["disclaimer"]

    deposits = client.get("/pools/pool_eth_01/deposits")
    assert deposits.status_code == 200
    deposit_body = deposits.json()
    assert deposit_body["pool_id"] == POOL_ETH_01
    assert deposit_body["pool_key"] == "pool_eth_01"
    assert deposit_body["count"] == 2
    assert [item["commitment"] for item in deposit_body["items"]] == [C1, C2]
    first = deposit_body["items"][0]
    assert first["event_type"] == "Deposit"
    assert first["leaf_index"] == 0
    assert first["canonical"] is True
    assert first["block_number"] == 1
    assert first["block_hash"].startswith("0x")
    assert first["tx_hash"].startswith("0x")
    assert first["confirmations"] == 3
    assert first["finality"] == "final"

    # The raw bytes32 pool ID is accepted as well as the short label.
    raw = client.get(f"/pools/{POOL_ETH_01}/deposits")
    assert raw.status_code == 200
    assert raw.json()["pool_id"] == POOL_ETH_01

    roots = client.get("/pools/pool_eth_01/roots")
    assert roots.status_code == 200
    root_body = roots.json()
    assert root_body["count"] == 2
    assert root_body["current_root"] == R2
    assert root_body["current_root_block"] == 2
    assert root_body["items"][1]["root"] == R2

    withdrawal = client.get(f"/withdrawals/{N1}")
    assert withdrawal.status_code == 200
    withdrawal_body = withdrawal.json()
    assert withdrawal_body["found"] is True
    assert withdrawal_body["pool_id"] == POOL_ETH_01
    assert withdrawal_body["pool_key"] == "pool_eth_01"
    assert withdrawal_body["recipient"] == RECIPIENT
    assert withdrawal_body["fee_wei"] == "1000"
    assert withdrawal_body["block_number"] == 3

    scoped = client.get(f"/withdrawals/{N1}", params={"pool_id": "pool_eth_01"})
    assert scoped.status_code == 200
    wrong_pool = client.get(f"/withdrawals/{N1}", params={"pool_id": "pool_eth_1"})
    assert wrong_pool.status_code == 404
    assert wrong_pool.json()["detail"]["code"] == "WITHDRAWAL_NOT_FOUND"

    pools = client.get("/pools")
    assert pools.status_code == 200
    assert pools.json()["count"] == 1
    pool_item = pools.json()["items"][0]
    assert pool_item["pool_key"] == "pool_eth_01"
    assert pool_item["denomination_wei"] == "100000000000000000"
    assert pool_item["root_window"] == 64
    assert pool_item["maturity_seconds"] == 1800
    assert pool_item["deposits"] == 2
    assert pool_item["withdrawals"] == 1


def test_not_found_and_invalid_input(settings, store, make_indexer):
    client = _indexed_client(settings, store, make_indexer)

    missing_pool = client.get("/pools/pool_missing/deposits")
    assert missing_pool.status_code == 404
    assert missing_pool.json()["detail"]["code"] == "POOL_NOT_FOUND"

    missing_withdrawal = client.get("/withdrawals/0x" + "ee" * 32)
    assert missing_withdrawal.status_code == 404
    assert missing_withdrawal.json()["detail"]["code"] == "WITHDRAWAL_NOT_FOUND"

    invalid = client.get("/withdrawals/not-hex")
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "INVALID_NULLIFIER"


def test_api_before_first_sync_is_starting(settings, tmp_path):
    store = Store(tmp_path / "empty.db")
    store.initialize()
    client = TestClient(create_app(settings, store))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "starting"
    assert health.json()["chain_id"] is None

    pools = client.get("/pools")
    assert pools.status_code == 503
    assert pools.json()["detail"]["code"] == "INDEXER_NOT_READY"


def test_api_never_exposes_note_or_secret_keys(settings, store, make_indexer):
    client = _indexed_client(settings, store, make_indexer)
    forbidden = {
        "note",
        "notes",
        "secret",
        "nullifier_secret",
        "veilnote",
        "proof",
        "proof_bytes",
    }
    responses = [
        client.get("/health"),
        client.get("/pools"),
        client.get("/pools/pool_eth_01/deposits"),
        client.get("/pools/pool_eth_01/roots"),
        client.get(f"/pools/pool_eth_01/path/{C1}"),
        client.get(f"/withdrawals/{N1}"),
    ]
    for response in responses:
        assert response.status_code == 200
        assert _keys(response.json()).isdisjoint(forbidden)
