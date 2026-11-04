from __future__ import annotations

import hashlib

import httpx
import pytest

from veilpool_api.indexer_client import IndexerClient, IndexerError

CONTRACT = "0x" + "a1" * 20
TX_HASH = "0x" + hashlib.sha256(b"indexer-tx").hexdigest()
COMMITMENT = "0x" + hashlib.sha256(b"indexer-commitment").hexdigest()
BLOCK_HASH = "0x" + hashlib.sha256(b"indexer-block").hexdigest()
ROOT = "0x" + hashlib.sha256(b"indexer-root").hexdigest()


def client_for(handler) -> IndexerClient:
    return IndexerClient(
        "http://127.0.0.1:8100",
        timeout=0.2,
        transport=httpx.MockTransport(handler),
    )


def test_transport_failure_is_explicit_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = client_for(handler)
    try:
        with pytest.raises(IndexerError) as exc_info:
            client.health()
        assert exc_info.value.code == "INDEXER_UNAVAILABLE"
        assert exc_info.value.status_code == 503
    finally:
        client.close()


def test_timeout_is_explicit_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = client_for(handler)
    try:
        with pytest.raises(IndexerError) as exc_info:
            client.health()
        assert exc_info.value.code == "INDEXER_TIMEOUT"
        assert exc_info.value.status_code == 504
    finally:
        client.close()


def test_non_json_is_bad_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = client_for(handler)
    try:
        with pytest.raises(IndexerError) as exc_info:
            client.health()
        assert exc_info.value.code == "INDEXER_BAD_RESPONSE"
        assert exc_info.value.status_code == 502
    finally:
        client.close()


def test_not_ready_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "detail": {
                    "code": "INDEXER_NOT_READY",
                    "message": "not ready",
                }
            },
        )

    client = client_for(handler)
    try:
        with pytest.raises(IndexerError) as exc_info:
            client.health()
        assert exc_info.value.code == "INDEXER_UNAVAILABLE"
        assert exc_info.value.indexer_code == "INDEXER_NOT_READY"
    finally:
        client.close()


def test_no_events_404_is_empty_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pools/pool_eth_01/deposits"
        return httpx.Response(
            404,
            json={
                "detail": {
                    "code": "POOL_NOT_FOUND",
                    "message": "No canonical events for this pool.",
                }
            },
        )

    client = client_for(handler)
    try:
        assert client.list_deposits("pool_eth_01") == []
    finally:
        client.close()


def test_deposit_proxy_drops_unknown_and_note_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "chain_id": 31337,
                "contract_address": CONTRACT,
                "pool_id": "0x" + b"pool_eth_01".hex().ljust(64, "0"),
                "pool_key": "pool_eth_01",
                "canonical_only": True,
                "items": [
                    {
                        "chain_id": 31337,
                        "contract_address": CONTRACT,
                        "event_type": "Deposit",
                        "pool_id": (
                            "0x" + b"pool_eth_01".hex().ljust(64, "0")
                        ),
                        "pool_key": "pool_eth_01",
                        "commitment": COMMITMENT,
                        "leaf_index": 0,
                        "tx_hash": TX_HASH,
                        "block_number": 11,
                        "block_hash": BLOCK_HASH,
                        "block_timestamp": 1_700_000_011,
                        "log_index": 1,
                        "canonical": True,
                        "confirmations": 2,
                        "finality": "final",
                        "indexed_at": "2026-11-03T12:00:00.000Z",
                        "note": "secret-note",
                        "secret": "secret-value",
                        "preimage": "secret-preimage",
                    }
                ],
                "count": 1,
                "next_cursor": None,
            },
        )

    client = client_for(handler)
    try:
        items = client.list_deposits("pool_eth_01")
        assert len(items) == 1
        item = items[0]
        assert item["commitment"] == COMMITMENT
        assert item["tx_hash"] == TX_HASH
        assert item["chain_source"] == "indexer"
        assert item["mock"] is False
        assert "note" not in item
        assert "secret" not in item
        assert "preimage" not in item
        assert "secret-note" not in str(item)
    finally:
        client.close()


def test_malformed_deposit_is_bad_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "content": "not-a-deposit",
                    }
                ],
                "count": 1,
            },
        )

    client = client_for(handler)
    try:
        with pytest.raises(IndexerError) as exc_info:
            client.list_deposits("pool_eth_01")
        assert exc_info.value.code == "INDEXER_BAD_RESPONSE"
    finally:
        client.close()


def test_root_proxy_uses_public_fields_only():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "chain_id": 31337,
                        "pool_id": (
                            "0x" + b"pool_eth_01".hex().ljust(64, "0")
                        ),
                        "pool_key": "pool_eth_01",
                        "event_type": "RootUpdated",
                        "root": ROOT,
                        "leaf_index": 0,
                        "tx_hash": TX_HASH,
                        "block_number": 10,
                        "block_hash": BLOCK_HASH,
                        "block_timestamp": 1_700_000_010,
                        "log_index": 2,
                        "canonical": True,
                        "confirmations": 3,
                        "finality": "final",
                        "indexed_at": "2026-11-03T12:00:00.000Z",
                        "note": "drop-me",
                    }
                ],
                "count": 1,
            },
        )

    client = client_for(handler)
    try:
        items = client.list_roots("pool_eth_01")
        assert items[0]["root"] == ROOT
        assert "note" not in items[0]
    finally:
        client.close()
