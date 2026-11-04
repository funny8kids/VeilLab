from __future__ import annotations

from fastapi.testclient import TestClient

from chain_fixtures import C1, C2, POOL_ETH_01, R1, R2, chain_a
from fake_chain import FakeRpc, block, build_chain
from veilpool_indexer.api import create_app
from veilpool_indexer.merkle import build_path, zero_hashes
from veilpool_indexer.poseidon import FIELD_MODULUS, field_to_hex32

NON_CANONICAL_COMMITMENT = "0x" + format(FIELD_MODULUS, "064x")
POOL_CREATED = {
    "denomination": 10**17,
    "root_window": 64,
    "maturity": 1800,
}


def _indexed_client(settings, store, make_indexer, chain=None) -> TestClient:
    indexer = make_indexer(FakeRpc(chain if chain is not None else chain_a()))
    indexer.sync_once()
    return TestClient(create_app(settings, store))


def _path(client: TestClient, commitment: str, pool: str = "pool_eth_01"):
    return client.get(f"/pools/{pool}/path/{commitment}")


def test_path_for_canonical_deposit(settings, store, make_indexer):
    client = _indexed_client(settings, store, make_indexer)
    expected = build_path([C1, C2], 0)

    response = _path(client, C1)
    assert response.status_code == 200
    body = response.json()

    assert body["chain_id"] == 31337
    assert body["contract_address"] == settings.contract_address
    assert body["pool_id"] == POOL_ETH_01
    assert body["pool_key"] == "pool_eth_01"
    assert body["commitment"] == C1
    assert body["leaf_index"] == 0
    assert body["leaf_count"] == 2
    assert body["tree_depth"] == 20
    assert body["root"] == field_to_hex32(expected.root)
    assert body["path_elements"] == [
        field_to_hex32(value) for value in expected.path_elements
    ]
    assert body["path_indices"] == list(expected.path_indices)
    assert body["canonical_only"] is True
    assert body["mock_verifier"] is True
    assert body["verifier_kind"] == "mock"
    assert "MOCK VERIFIER" in body["disclaimer"]

    roots = store.list_events(
        chain_id=31337,
        contract_address=settings.contract_address,
        pool_id=POOL_ETH_01,
        event_type="RootUpdated",
    )
    assert body["root_block_number"] == 2
    assert body["root_block_hash"] == roots[-1]["block_hash"]

    # Commitment lookup is case-insensitive and accepts the raw pool ID.
    upper = _path(client, "0x" + C1[2:].upper(), pool=POOL_ETH_01)
    assert upper.status_code == 200
    assert upper.json()["leaf_index"] == body["leaf_index"]
    assert upper.json()["root"] == body["root"]


def test_path_unknown_commitment(settings, store, make_indexer):
    client = _indexed_client(settings, store, make_indexer)

    response = _path(client, field_to_hex32(0xDEADBEEF))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "COMMITMENT_NOT_FOUND"


def test_path_invalid_commitment(settings, store, make_indexer):
    client = _indexed_client(settings, store, make_indexer)

    for value in (
        "not-hex",
        "0x" + format(FIELD_MODULUS, "064x"),
        "0x" + "11" * 33,
        "0x" + "00" * 32,
    ):
        response = _path(client, value)
        assert response.status_code == 400, value
        assert response.json()["detail"]["code"] == "INVALID_COMMITMENT"


def test_path_non_canonical_stored_commitment(settings, store, make_indexer):
    chain = build_chain(
        [
            block(
                ("PoolCreated", POOL_CREATED),
                (
                    "Deposit",
                    {
                        "commitment": C1,
                        "leaf_index": 0,
                        "timestamp": 1_700_000_000,
                    },
                ),
                ("RootUpdated", {"root": R1, "leaf_index": 0}),
                salt="bad-leaf-0",
                timestamp=1_700_000_012,
            ),
            block(
                (
                    "Deposit",
                    {
                        "commitment": NON_CANONICAL_COMMITMENT,
                        "leaf_index": 1,
                        "timestamp": 1_700_000_001,
                    },
                ),
                ("RootUpdated", {"root": R2, "leaf_index": 1}),
                salt="bad-leaf-1",
                timestamp=1_700_000_024,
            ),
        ]
    )
    client = _indexed_client(settings, store, make_indexer, chain)

    for requested in (C1, NON_CANONICAL_COMMITMENT):
        response = _path(client, requested)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "NON_CANONICAL_COMMITMENT"
        assert "leaf 1" in detail["message"]


def test_path_single_leaf_has_zero_siblings(settings, store, make_indexer):
    chain = build_chain(
        [
            block(
                ("PoolCreated", POOL_CREATED),
                (
                    "Deposit",
                    {
                        "commitment": C1,
                        "leaf_index": 0,
                        "timestamp": 1_700_000_000,
                    },
                ),
                ("RootUpdated", {"root": R1, "leaf_index": 0}),
                salt="single-leaf",
                timestamp=1_700_000_012,
            )
        ]
    )
    client = _indexed_client(settings, store, make_indexer, chain)
    expected = build_path([C1], 0)

    response = _path(client, C1)
    assert response.status_code == 200
    body = response.json()
    assert body["leaf_index"] == 0
    assert body["leaf_count"] == 1
    assert body["root"] == field_to_hex32(expected.root)
    assert body["path_elements"] == [
        field_to_hex32(value) for value in zero_hashes(20)[:20]
    ]
    assert body["path_elements"][0] == field_to_hex32(0)
    assert body["path_indices"] == [0] * 20


def test_path_pool_not_found(settings, store, make_indexer):
    client = _indexed_client(settings, store, make_indexer)

    response = _path(client, C1, pool="pool_missing")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "POOL_NOT_FOUND"


def test_path_empty_pool(settings, store, make_indexer):
    chain = build_chain(
        [
            block(
                ("PoolCreated", POOL_CREATED),
                salt="empty-pool",
                timestamp=1_700_000_012,
            )
        ]
    )
    client = _indexed_client(settings, store, make_indexer, chain)

    response = _path(client, field_to_hex32(1))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "POOL_EMPTY"


def test_path_without_root_event_has_null_root_metadata(settings, store, make_indexer):
    chain = build_chain(
        [
            block(
                ("PoolCreated", POOL_CREATED),
                (
                    "Deposit",
                    {
                        "commitment": C1,
                        "leaf_index": 0,
                        "timestamp": 1_700_000_000,
                    },
                ),
                salt="deposit-only",
                timestamp=1_700_000_012,
            )
        ]
    )
    client = _indexed_client(settings, store, make_indexer, chain)

    response = _path(client, C1)
    assert response.status_code == 200
    body = response.json()
    assert body["root_block_number"] is None
    assert body["root_block_hash"] is None
