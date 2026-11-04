from __future__ import annotations

import hashlib
import json
import urllib.parse
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from support import (
    ADMIN_HEADERS,
    DEFAULT_PROOF,
    assert_no_secret_keys,
    commitment,
    create_intent,
    new_key,
    normal_address,
)
from veilpool_api.config import Settings
from veilpool_api.indexer_client import PUBLIC_PATH_FIELDS, IndexerClient
from veilpool_api.local_chain import (
    DEPOSIT_SELECTOR,
    WITHDRAW_SELECTOR,
    LocalRpcClient,
    encode_deposit_calldata,
    encode_withdraw_calldata,
)
from veilpool_api.main import create_app
from veilpool_api.models import (
    Deposit,
    DepositIntent,
    LocalDepositBroadcast,
    LocalWithdrawalBroadcast,
    Nullifier,
    Withdrawal,
    WithdrawalQuote,
    utcnow,
)

CONTRACT = "0x" + "a1" * 20
FROM_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
COMMITMENT = "0x" + hashlib.sha256(b"local-commitment-1").hexdigest()
OTHER_COMMITMENT = "0x" + hashlib.sha256(b"local-commitment-2").hexdigest()
TX_HASH = "0x" + hashlib.sha256(b"local-tx-1").hexdigest()
BLOCK_HASH = "0x" + hashlib.sha256(b"local-block-11").hexdigest()
CURRENT_ROOT = "0x" + hashlib.sha256(b"local-root").hexdigest()
EXTERNAL_TX = "0x" + hashlib.sha256(b"external-tx").hexdigest()
EXTERNAL_COMMITMENT = "0x" + hashlib.sha256(b"external-commitment").hexdigest()
WITHDRAWAL_TX = "0x" + hashlib.sha256(b"local-withdrawal-tx").hexdigest()
WITHDRAWAL_BLOCK_HASH = "0x" + hashlib.sha256(b"local-withdrawal-block").hexdigest()
WITHDRAWAL_NULLIFIER = "0x" + hashlib.sha256(b"local-nullifier").hexdigest()
GROTH16_PROOF = "0x" + "11" * 256
PATH_COMMITMENT = "0x" + "00" * 31 + "05"


def pool_hex(label: str) -> str:
    return "0x" + label.encode("ascii").hex().ljust(64, "0")


def deposit_item(
    *,
    pool_key: str = "pool_eth_01",
    commitment: str = EXTERNAL_COMMITMENT,
    tx_hash: str = EXTERNAL_TX,
    leaf_index: int = 0,
    block_number: int = 11,
    log_index: int = 1,
) -> dict[str, Any]:
    return {
        "chain_id": 31337,
        "contract_address": CONTRACT,
        "event_type": "Deposit",
        "pool_id": pool_hex(pool_key),
        "pool_key": pool_key,
        "commitment": commitment,
        "leaf_index": leaf_index,
        "tx_hash": tx_hash,
        "block_number": block_number,
        "block_hash": BLOCK_HASH,
        "block_timestamp": 1_700_000_011,
        "log_index": log_index,
        "nullifier": None,
        "recipient": None,
        "canonical": True,
        "confirmations": 4,
        "finality": "final",
        "indexed_at": "2026-11-03T12:00:00.000Z",
        "note": "never-proxy-this",
        "secret": "never-proxy-this-either",
    }


def root_item(
    *,
    pool_key: str = "pool_eth_01",
    root: str = CURRENT_ROOT,
    block_number: int = 10,
    log_index: int = 2,
) -> dict[str, Any]:
    return {
        "chain_id": 31337,
        "contract_address": CONTRACT,
        "event_type": "RootUpdated",
        "pool_id": pool_hex(pool_key),
        "pool_key": pool_key,
        "root": root,
        "leaf_index": 0,
        "tx_hash": EXTERNAL_TX,
        "block_number": block_number,
        "block_hash": BLOCK_HASH,
        "block_timestamp": 1_700_000_010,
        "log_index": log_index,
        "canonical": True,
        "confirmations": 5,
        "finality": "final",
        "indexed_at": "2026-11-03T12:00:00.000Z",
        "note": "never-proxy-this",
    }


def withdrawal_item(
    *,
    pool_key: str = "pool_eth_01",
    nullifier: str = WITHDRAWAL_NULLIFIER,
    recipient: str = normal_address(2),
    fee_wei: str = "240000000000000",
    tx_hash: str = WITHDRAWAL_TX,
    block_number: int = 14,
    log_index: int = 0,
) -> dict[str, Any]:
    return {
        "chain_id": 31337,
        "contract_address": CONTRACT,
        "event_type": "Withdrawal",
        "pool_id": pool_hex(pool_key),
        "pool_key": pool_key,
        "commitment": None,
        "nullifier": nullifier,
        "recipient": recipient,
        "fee_wei": fee_wei,
        "tx_hash": tx_hash,
        "block_number": block_number,
        "block_hash": WITHDRAWAL_BLOCK_HASH,
        "block_timestamp": 1_700_000_014,
        "log_index": log_index,
        "canonical": True,
        "confirmations": 1,
        "finality": "final",
        "indexed_at": "2026-11-03T12:00:01.000Z",
        "note": "never-proxy-this",
        "secret": "never-proxy-this-either",
    }


def path_item(
    *,
    pool_key: str = "pool_eth_01",
    commitment: str = PATH_COMMITMENT,
    leaf_index: int = 5,
    leaf_count: int = 10,
    tree_depth: int = 3,
    root: str = CURRENT_ROOT,
) -> dict[str, Any]:
    return {
        "chain_id": 31337,
        "contract_address": CONTRACT,
        "pool_id": pool_hex(pool_key),
        "pool_key": pool_key,
        "commitment": commitment,
        "leaf_index": leaf_index,
        "leaf_count": leaf_count,
        "tree_depth": tree_depth,
        "root": root,
        "root_block_number": 10,
        "root_block_hash": BLOCK_HASH,
        "path_elements": ["0x" + "00" * 32] * tree_depth,
        "path_indices": ([1, 0, 1][:tree_depth] + [0] * tree_depth)[
            :tree_depth
        ],
        "canonical_only": True,
        "mock_verifier": False,
        "note": "never-proxy-this",
        "secret": "never-proxy-this-either",
    }


def pool_item(
    pool_key: str,
    *,
    deposits: int = 0,
    withdrawals: int = 0,
    roots: int = 0,
    current_root: str | None = None,
    current_root_block: int | None = None,
    paused: bool = False,
) -> dict[str, Any]:
    return {
        "pool_id": pool_hex(pool_key),
        "pool_key": pool_key,
        "deposits": deposits,
        "withdrawals": withdrawals,
        "roots": roots,
        "current_root": current_root,
        "current_root_block": current_root_block,
        "paused": paused,
    }


class FakeIndexer:
    def __init__(
        self,
        *,
        deposit_items: dict[str, list[dict[str, Any]]] | None = None,
        root_items: dict[str, list[dict[str, Any]]] | None = None,
        pool_items: list[dict[str, Any]] | None = None,
        health: dict[str, Any] | None = None,
        withdrawal_items: dict[str, dict[str, Any]] | None = None,
        path_items: dict[str, dict[str, Any]] | None = None,
        path_errors: dict[str, tuple[int, str]] | None = None,
    ) -> None:
        self.down = False
        self.deposit_items = deposit_items or {}
        self.root_items = root_items or {}
        self.withdrawal_items = withdrawal_items or {}
        self.path_items = path_items or {}
        self.path_errors = path_errors or {}
        self.pool_items = pool_items or [
            pool_item(
                "pool_eth_01",
                deposits=2,
                withdrawals=1,
                roots=2,
                current_root=CURRENT_ROOT,
                current_root_block=10,
            ),
            pool_item("pool_eth_1"),
            pool_item("pool_eth_10"),
        ]
        self.health_payload = health or {
            "status": "ok",
            "service": "veilpool-indexer",
            "mode": "local-chain",
            "mock_verifier": True,
            "testnet_only": True,
            "chain_id": 31337,
            "contract_address": CONTRACT,
            "indexed_block": 12,
            "tip_block": 14,
            "lag": 2,
            "finality_confirmations": 1,
            "last_synced_at": "2026-11-03T12:00:00.000Z",
            "last_error": None,
            "reorgs": 0,
            "event_counts": {"Deposit": 2, "RootUpdated": 2},
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json=self.health_payload)
        if path == "/pools":
            return httpx.Response(
                200,
                json={
                    "items": self.pool_items,
                    "count": len(self.pool_items),
                    "chain_id": 31337,
                    "contract_address": CONTRACT,
                    "canonical_only": True,
                    "mock_verifier": True,
                },
            )
        parts = [urllib.parse.unquote(part) for part in path.strip("/").split("/")]
        if len(parts) == 2 and parts[0] == "withdrawals":
            nullifier = parts[1].lower()
            item = self.withdrawal_items.get(nullifier)
            if item is None:
                return httpx.Response(
                    404,
                    json={
                        "detail": {
                            "code": "WITHDRAWAL_NOT_FOUND",
                            "message": "No canonical withdrawal for nullifier.",
                        }
                    },
                )
            return httpx.Response(200, json=item)
        if len(parts) == 4 and parts[0] == "pools" and parts[2] == "path":
            commitment = parts[3].lower()
            error = self.path_errors.get(commitment)
            if error is not None:
                status, code = error
                return httpx.Response(
                    status,
                    json={
                        "detail": {
                            "code": code,
                            "message": "Path request rejected.",
                        }
                    },
                )
            item = self.path_items.get(commitment)
            if item is None:
                return httpx.Response(
                    404,
                    json={
                        "detail": {
                            "code": "COMMITMENT_NOT_FOUND",
                            "message": "No canonical deposit for commitment.",
                        }
                    },
                )
            return httpx.Response(200, json=item)
        if len(parts) == 3 and parts[0] == "pools" and parts[2] in {
            "deposits",
            "roots",
        }:
            pool_key = parts[1]
            if parts[2] == "deposits":
                items = self.deposit_items.get(pool_key)
                if items is None:
                    return httpx.Response(
                        404,
                        json={
                            "detail": {
                                "code": "POOL_NOT_FOUND",
                                "message": "No canonical events for this pool.",
                            }
                        },
                    )
                return httpx.Response(
                    200,
                    json={
                        "chain_id": 31337,
                        "contract_address": CONTRACT,
                        "pool_id": pool_hex(pool_key),
                        "pool_key": pool_key,
                        "canonical_only": True,
                        "items": items,
                        "count": len(items),
                        "next_cursor": None,
                    },
                )
            items = self.root_items.get(pool_key, [])
            return httpx.Response(
                200,
                json={
                    "chain_id": 31337,
                    "contract_address": CONTRACT,
                    "pool_id": pool_hex(pool_key),
                    "pool_key": pool_key,
                    "current_root": items[-1]["root"] if items else None,
                    "items": items,
                    "count": len(items),
                },
            )
        return httpx.Response(404, json={"detail": "not found"})


class FakeRpc:
    def __init__(
        self,
        *,
        indexer: FakeIndexer | None = None,
        tx_hash: str = TX_HASH,
        add_deposit: bool = True,
        add_withdrawal: bool = False,
        withdrawal: dict[str, Any] | None = None,
        receipt_status: int = 1,
        receipt_present: bool = True,
    ) -> None:
        self.indexer = indexer
        self.tx_hash = tx_hash
        self.add_deposit = add_deposit
        self.add_withdrawal = add_withdrawal
        self.withdrawal = withdrawal or {}
        self.calls: list[dict[str, Any]] = []
        self.receipt_calls: list[dict[str, Any]] = []
        self.receipt = (
            {
                "transactionHash": tx_hash,
                "status": hex(receipt_status),
                "blockNumber": "0xe",
                "blockHash": WITHDRAWAL_BLOCK_HASH,
                "gasUsed": "0x52f8",
            }
            if receipt_present
            else None
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "eth_getTransactionReceipt":
            self.receipt_calls.append(body)
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": self.receipt,
                },
            )
        self.calls.append(body)
        assert body["method"] == "eth_sendTransaction"
        if self.add_withdrawal and self.indexer is not None:
            item = withdrawal_item(
                tx_hash=self.tx_hash,
                **self.withdrawal,
            )
            self.indexer.withdrawal_items[item["nullifier"].lower()] = item
        elif self.add_deposit and self.indexer is not None:
            self.indexer.deposit_items["pool_eth_01"] = [
                deposit_item(
                    commitment=COMMITMENT,
                    tx_hash=self.tx_hash,
                    block_number=11,
                )
            ]
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": self.tx_hash,
            },
        )


def local_settings(tmp_path: Path, **overrides: Any) -> Settings:
    base = dict(
        mode="local",
        database_url=f"sqlite:///{(tmp_path / 'local.db').as_posix()}",
        admin_token="dev-admin",
        chain_id=31337,
        contract_address=CONTRACT,
        indexer_url="http://127.0.0.1:8100",
        indexer_timeout_seconds=0.5,
        local_rpc_url="http://127.0.0.1:8545",
        local_from_address=FROM_ADDRESS,
        local_auto_deposit=True,
        local_deposit_timeout_seconds=0.0,
        local_auto_withdraw=False,
        local_withdrawal_timeout_seconds=0.0,
        local_verifier_kind="mock",
        intent_ttl_seconds=600,
        quote_ttl_seconds=300,
        compliance_ttl_seconds=300,
        root_window_size=20,
        compliance_hash_salt="test-salt",
        mock_start_block=6_000_000,
        mock_maturity_seconds=0,
    )
    base.update(overrides)
    return Settings(**base)


@contextmanager
def local_client(
    tmp_path: Path,
    fake: FakeIndexer,
    rpc: FakeRpc | None = None,
    **overrides: Any,
) -> Iterator[tuple[TestClient, Any]]:
    settings = local_settings(tmp_path, **overrides)
    indexer_client = IndexerClient(
        settings.indexer_url,
        timeout=settings.indexer_timeout_seconds,
        transport=httpx.MockTransport(fake.handler),
    )
    rpc = rpc or FakeRpc()
    local_rpc_client = LocalRpcClient(
        settings.local_rpc_url,
        timeout=settings.indexer_timeout_seconds,
        transport=httpx.MockTransport(rpc.handler),
    )
    app = create_app(
        settings,
        indexer_client=indexer_client,
        local_rpc_client=local_rpc_client,
    )
    with TestClient(app) as client:
        yield client, app


def test_selector_and_calldata_are_one_public_word():
    assert DEPOSIT_SELECTOR == "0xb214faa5"
    calldata = encode_deposit_calldata(COMMITMENT)
    assert calldata == DEPOSIT_SELECTOR + COMMITMENT[2:]
    assert len(calldata) == 2 + 8 + 64
    with pytest.raises(ValueError):
        encode_deposit_calldata("0xdeadbeef")


def test_withdraw_selector_and_abi_calldata_vector():
    assert WITHDRAW_SELECTOR == "0xc890dc66"
    recipient = normal_address(2)
    calldata = encode_withdraw_calldata(
        GROTH16_PROOF,
        CURRENT_ROOT,
        WITHDRAWAL_NULLIFIER,
        recipient,
        "240000000000000",
        "pool_eth_01",
    )
    # 4-byte selector + 15 ABI words: six head words, bytes length, 8 proof
    # words. The proof is a dynamic bytes argument with tail offset 0x20.
    assert len(calldata) == 970
    assert calldata.startswith(WITHDRAW_SELECTOR)
    words = [
        calldata[10 + index * 64 : 10 + (index + 1) * 64]
        for index in range(15)
    ]
    assert words[0] == f"{192:064x}"
    assert words[1] == CURRENT_ROOT[2:]
    assert words[2] == WITHDRAWAL_NULLIFIER[2:]
    assert words[3] == f"{int(recipient, 16):064x}"
    assert words[4] == f"{240000000000000:064x}"
    assert words[5] == "pool_eth_01".encode("ascii").hex().ljust(64, "0")
    assert words[6] == f"{256:064x}"
    assert "".join(words[7:]) == GROTH16_PROOF[2:]

    with pytest.raises(ValueError):
        encode_withdraw_calldata(
            "0x" + "11" * 128,
            CURRENT_ROOT,
            WITHDRAWAL_NULLIFIER,
            recipient,
            1,
            "pool_eth_01",
        )


def test_local_health_root_and_pools_overlay(tmp_path):
    fake = FakeIndexer()
    with local_client(tmp_path, fake) as (client, _app):
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        body = health.json()
        assert body["mode"] == "local"
        assert body["mock"] is False
        assert body["status"] == "ok"
        assert body["chain_id"] == 31337
        assert body["chain_data_status"] == "available"
        assert "INDEXER" in body["services"]["chain"]
        assert body["indexer"]["status"] == "ok"
        assert body["indexer"]["lag"] == 2
        assert body["indexer"]["last_error"] is None
        assert "MOCK_CHAIN" not in body["mock_services"]
        assert health.headers["x-veilpool-mode"] == "local"
        assert health.headers["x-veilpool-mock"] == "false"
        assert_no_secret_keys(body)

        root = client.get("/")
        assert root.status_code == 200
        root_body = root.json()
        assert root_body["mode"] == "local"
        assert root_body["mock"] is False
        assert root_body["indexer"]["status"] == "ok"
        assert "MOCK_CHAIN" not in root_body["mock_services"]

        pools = client.get("/api/v1/pools")
        assert pools.status_code == 200
        pools_body = pools.json()
        assert pools_body["mode"] == "local"
        assert pools_body["mock"] is False
        assert pools_body["chain_data_status"] == "available"
        assert pools_body["indexed_block"] == 12
        assert pools_body["lag"] == 2
        by_id = {item["id"]: item for item in pools_body["items"]}
        assert set(by_id) == {"pool_eth_01", "pool_eth_1", "pool_eth_10"}
        eth01 = by_id["pool_eth_01"]
        assert eth01["deposits"] == 2
        assert eth01["withdrawals"] == 1
        assert eth01["anonymity_set"] == 1
        assert eth01["current_root"] == CURRENT_ROOT
        assert eth01["indexed_block"] == 12
        assert eth01["lag"] == 2
        assert eth01["chain_source"] == "indexer"
        assert eth01["chain_data_status"] == "available"
        assert eth01["mock"] is False
        assert eth01["contract_address"] == CONTRACT
        assert_no_secret_keys(pools_body)

        detail = client.get("/api/v1/pools/pool_eth_01")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["root"] == CURRENT_ROOT
        assert detail_body["current_root"] == CURRENT_ROOT
        assert detail_body["indexed_block"] == 12
        assert detail_body["lag"] == 2
        assert detail_body["chain_data_status"] == "available"
        assert detail_body["confirmations"] == 5
        assert detail_body["finality"] == "final"
        assert detail_body["indexer"]["lag"] == 2


def test_local_deposit_list_proxies_public_fields_and_empty_is_ok(tmp_path):
    fake = FakeIndexer(
        deposit_items={
            "pool_eth_01": [deposit_item()],
            "pool_eth_1": [],
        }
    )
    with local_client(tmp_path, fake) as (client, _app):
        response = client.get("/api/v1/pools/pool_eth_01/deposits")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["chain_source"] == "indexer"
        assert body["local_chain"] == "ANVIL"
        assert body["mock"] is False
        assert body["count"] == 1
        item = body["items"][0]
        assert item["commitment"] == EXTERNAL_COMMITMENT
        assert item["tx_hash"] == EXTERNAL_TX
        assert item["leaf_index"] == 0
        assert item["log_index"] == 1
        assert item["block_timestamp"] == 1_700_000_011
        assert item["pool_key"] == "pool_eth_01"
        assert item["chain_source"] == "indexer"
        assert item["mock"] is False
        assert "note" not in item
        assert "secret" not in item
        assert "never-proxy-this" not in response.text
        assert_no_secret_keys(body)

        empty = client.get("/api/v1/pools/pool_eth_1/deposits")
        assert empty.status_code == 200, empty.text
        assert empty.json()["items"] == []

        # The indexer returns 404 when it has no canonical events for a known
        # pool; that is still an empty list, not an API error.
        no_events = client.get("/api/v1/pools/pool_eth_10/deposits")
        assert no_events.status_code == 200, no_events.text
        assert no_events.json()["items"] == []


def test_indexer_down_is_not_fabricated(tmp_path):
    fake = FakeIndexer()
    fake.down = True
    with local_client(tmp_path, fake) as (client, _app):
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        body = health.json()
        assert body["mode"] == "local"
        assert body["mock"] is False
        assert body["status"] == "degraded"
        assert body["chain_data_status"] == "unavailable"
        assert body["indexer"]["status"] == "unavailable"
        assert body["indexer"]["lag"] is None
        assert body["indexer"]["last_error"]

        pools = client.get("/api/v1/pools")
        assert pools.status_code == 200
        pools_body = pools.json()
        assert pools_body["chain_data_status"] == "unavailable"
        for item in pools_body["items"]:
            assert item["chain_data_status"] == "unavailable"
            assert item["anonymity_set"] is None
            assert item["liquidity_wei"] is None
            assert "deposits" not in item
            assert "withdrawals" not in item
            assert "warning" in item

        detail = client.get("/api/v1/pools/pool_eth_01").json()
        assert detail["chain_data_status"] == "unavailable"
        assert detail["root"] is None
        assert detail["anonymity_set"] is None
        assert detail["indexed_block"] is None

        deposits = client.get("/api/v1/pools/pool_eth_01/deposits")
        assert deposits.status_code == 503
        assert deposits.json()["code"] == "INDEXER_UNAVAILABLE"

        root = client.get("/")
        assert root.status_code == 200
        assert root.json()["chain_data_status"] == "unavailable"
        assert root.json()["indexer"]["status"] == "unavailable"


def test_local_seed_retires_mock_only_pools_in_shared_database(tmp_path):
    database_path = tmp_path / "shared.db"
    mock_settings = Settings(
        mode="mock",
        database_url=f"sqlite:///{database_path.as_posix()}",
        chain_id=11155111,
        compliance_hash_salt="test-salt",
        mock_maturity_seconds=0,
    )
    with TestClient(create_app(mock_settings)) as mock_client:
        assert len(mock_client.get("/api/v1/pools").json()["items"]) == 6

    fake = FakeIndexer()
    with local_client(
        tmp_path,
        fake,
        database_url=f"sqlite:///{database_path.as_posix()}",
    ) as (client, _app):
        items = client.get("/api/v1/pools").json()["items"]
        by_id = {item["id"]: item for item in items}
        assert set(by_id) == {
            "pool_eth_01",
            "pool_eth_1",
            "pool_eth_10",
            "pool_usdc_100",
            "pool_usdc_1000",
            "pool_btc_001",
        }
        for pool_id in ("pool_eth_01", "pool_eth_1", "pool_eth_10"):
            assert by_id[pool_id]["status"] == "active"
            assert by_id[pool_id]["chain_id"] == 31337
            assert by_id[pool_id]["contract_address"] == CONTRACT
        for pool_id in ("pool_usdc_100", "pool_usdc_1000", "pool_btc_001"):
            assert by_id[pool_id]["status"] == "retired"
            assert by_id[pool_id]["chain_data_status"] == "not_configured"
            assert by_id[pool_id]["anonymity_set"] is None


def test_local_deposit_happy_path_and_idempotent_replay(tmp_path):
    fake = FakeIndexer()
    rpc = FakeRpc(indexer=fake)
    with local_client(tmp_path, fake, rpc) as (client, app):
        intent_response = create_intent(client)
        assert intent_response.status_code == 200, intent_response.text
        intent = intent_response.json()
        assert intent["mock"] is False
        assert intent["local_chain"] is True
        assert intent["next_step"] == "POST /api/v1/local/deposits"
        assert "warning" in intent
        assert "mock_chain" not in intent

        response = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": intent["intent_id"], "commitment": COMMITMENT},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["local_chain"] == "ANVIL"
        assert body["chain_source"] == "indexer"
        assert body["mock"] is False
        assert body["tx_hash"] == TX_HASH
        assert body["block_number"] == 11
        assert body["block_hash"] == BLOCK_HASH
        assert body["leaf_index"] == 0
        assert body["commitment"] == COMMITMENT
        assert body["status"] == "confirmed"
        assert body["pool_id"] == "pool_eth_01"
        assert body["intent_id"] == intent["intent_id"]
        assert body["indexer_lag"] == 2
        assert body["confirmations"] == 4
        assert_no_secret_keys(body)

        assert len(rpc.calls) == 1
        transaction = rpc.calls[0]["params"][0]
        assert transaction["from"] == FROM_ADDRESS
        assert transaction["to"] == CONTRACT
        assert int(transaction["value"], 16) == 100_000_000_000_000_000
        assert transaction["data"] == (
            "0xb214faa5" + COMMITMENT[2:]
        )
        assert "private" not in json.dumps(rpc.calls[0]).lower()
        assert "note" not in json.dumps(rpc.calls[0]).lower()

        with app.state.db.session() as session:
            stored_intent = session.get(DepositIntent, intent["intent_id"])
            assert stored_intent.status == "consumed"
            # Deposits are keyed by their own id; at least one canonical row
            # must exist for this tx.
            rows = list(
                session.query(Deposit).filter(Deposit.tx_hash == TX_HASH).all()
            )
            assert len(rows) == 1
            assert rows[0].leaf_index == 0
            assert rows[0].status == "confirmed"
            assert rows[0].is_canonical is True

        replay = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": intent["intent_id"], "commitment": COMMITMENT},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["tx_hash"] == TX_HASH
        assert replay.json()["block_number"] == 11
        assert replay.json()["local_chain"] == "ANVIL"
        assert len(rpc.calls) == 1

        wrong_commitment = client.post(
            "/api/v1/local/deposits",
            json={
                "intent_id": intent["intent_id"],
                "commitment": OTHER_COMMITMENT,
            },
        )
        assert wrong_commitment.status_code == 409
        assert wrong_commitment.json()["code"] == "COMMITMENT_MISMATCH"


def test_auto_deposit_disabled_returns_calldata_without_tx(tmp_path):
    fake = FakeIndexer()
    rpc = FakeRpc(indexer=fake)
    with local_client(
        tmp_path, fake, rpc, local_auto_deposit=False
    ) as (client, app):
        intent = create_intent(client).json()
        response = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": intent["intent_id"], "commitment": COMMITMENT},
        )
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "LOCAL_DEPOSIT_DISABLED"
        assert body["contract_address"] == CONTRACT
        assert body["denomination_wei"] == "100000000000000000"
        assert body["calldata"] == "0xb214faa5" + COMMITMENT[2:]
        assert body["instruction"] == "submit the deposit from your own wallet"
        assert "tx_hash" not in body
        assert rpc.calls == []
        with app.state.db.session() as session:
            assert (
                session.get(DepositIntent, intent["intent_id"]).status
                == "pending"
            )


def test_confirmation_timeout_keeps_intent_pending_and_reuses_tx(tmp_path):
    fake = FakeIndexer()
    rpc = FakeRpc(indexer=None)
    with local_client(
        tmp_path, fake, rpc, local_deposit_timeout_seconds=0.0
    ) as (client, app):
        intent = create_intent(client).json()
        response = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": intent["intent_id"], "commitment": COMMITMENT},
        )
        assert response.status_code == 504, response.text
        body = response.json()
        assert body["code"] == "INDEXER_CONFIRMATION_TIMEOUT"
        assert body["tx_hash"] == TX_HASH
        assert body["local_chain"] == "ANVIL"
        assert body["status"] == "submitted"
        with app.state.db.session() as session:
            assert (
                session.get(DepositIntent, intent["intent_id"]).status
                == "pending"
            )
            broadcast = session.get(
                LocalDepositBroadcast, intent["intent_id"]
            )
            assert broadcast is not None
            assert broadcast.tx_hash == TX_HASH

        retry = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": intent["intent_id"], "commitment": COMMITMENT},
        )
        assert retry.status_code == 504
        assert retry.json()["tx_hash"] == TX_HASH
        assert len(rpc.calls) == 1


def test_indexer_mismatch_returns_502_and_does_not_consume(tmp_path):
    fake = FakeIndexer(
        deposit_items={
            "pool_eth_01": [
                deposit_item(commitment=OTHER_COMMITMENT, tx_hash=TX_HASH)
            ]
        }
    )
    rpc = FakeRpc(indexer=None)
    with local_client(tmp_path, fake, rpc) as (client, app):
        intent = create_intent(client).json()
        response = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": intent["intent_id"], "commitment": COMMITMENT},
        )
        assert response.status_code == 502, response.text
        assert response.json()["code"] == "INDEXER_MISMATCH"
        with app.state.db.session() as session:
            assert (
                session.get(DepositIntent, intent["intent_id"]).status
                == "pending"
            )


def test_local_mode_refuses_mock_chain_writes(tmp_path):
    fake = FakeIndexer()
    with local_client(tmp_path, fake) as (client, _app):
        intent = create_intent(client).json()

        mock_deposit = client.post(
            "/api/v1/mock/deposits",
            json={
                "intent_id": intent["intent_id"],
                "commitment": COMMITMENT,
            },
        )
        assert mock_deposit.status_code == 404
        assert mock_deposit.json()["code"] == "MOCK_ONLY"

        submit = client.post(
            "/api/v1/withdrawals/submit",
            json={
                "pool_id": "pool_eth_01",
                "quote_id": "q_missing",
                "proof": DEFAULT_PROOF,
                "public_signals": {
                    "root": CURRENT_ROOT,
                    "nullifier_hash": "0x" + "1" * 64,
                    "recipient": normal_address(2),
                    "fee_wei": "1",
                },
                "recipient_address": normal_address(2),
            },
            headers={"Idempotency-Key": new_key()},
        )
        assert submit.status_code == 409
        assert submit.json()["code"] == "MOCK_ONLY"

        quote = client.post(
            "/api/v1/withdrawals/quote",
            json={
                "pool_id": "pool_eth_01",
                "recipient_address": normal_address(3),
                "relayer_id": "rel_01",
            },
        )
        assert quote.status_code == 200, quote.text
        assert quote.json()["mock"] is False
        assert quote.json()["submission_available"] is False

        pause = client.post(
            "/api/v1/admin/pools/pool_eth_01/pause",
            json={"reason": "must not write mock state"},
            headers=ADMIN_HEADERS,
        )
        assert pause.status_code == 409
        assert pause.json()["code"] == "MOCK_ONLY"


def test_local_deposit_endpoint_is_local_only_and_rejects_note_fields(tmp_path):
    fake = FakeIndexer()
    with local_client(tmp_path, fake) as (client, _app):
        secret = "note-v1:local-secret"
        response = client.post(
            "/api/v1/local/deposits",
            json={
                "intent_id": "dep_missing",
                "commitment": COMMITMENT,
                "note": secret,
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
        assert secret not in response.text

        bad_commitment = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": "dep_missing", "commitment": "0xdeadbeef"},
        )
        assert bad_commitment.status_code == 422
        assert bad_commitment.json()["code"] == "VALIDATION_ERROR"


def test_local_deposit_requires_auth_when_enabled(tmp_path):
    fake = FakeIndexer()
    with local_client(
        tmp_path,
        fake,
        require_auth=True,
        api_token="local-api-token",
    ) as (client, _app):
        payload = {"intent_id": "dep_missing", "commitment": COMMITMENT}
        response = client.post("/api/v1/local/deposits", json=payload)
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH_REQUIRED"

        authorized = client.post(
            "/api/v1/local/deposits",
            json=payload,
            headers={"Authorization": "Bearer local-api-token"},
        )
        assert authorized.status_code == 404
        assert authorized.json()["code"] == "INTENT_NOT_FOUND"


def test_local_deposit_rate_limit_scope(tmp_path):
    fake = FakeIndexer()
    with local_client(
        tmp_path,
        fake,
        local_auto_deposit=False,
        rate_limit_local_deposit=1,
    ) as (client, _app):
        intent = create_intent(client)
        assert intent.status_code == 200
        payload = {
            "intent_id": intent.json()["intent_id"],
            "commitment": COMMITMENT,
        }
        first = client.post("/api/v1/local/deposits", json=payload)
        assert first.status_code == 409
        assert first.json()["code"] == "LOCAL_DEPOSIT_DISABLED"
        assert first.headers["x-ratelimit-scope"] == "local_deposit"
        second = client.post("/api/v1/local/deposits", json=payload)
        assert second.status_code == 429
        assert second.json()["code"] == "RATE_LIMITED"
        assert second.headers["x-ratelimit-scope"] == "local_deposit"


def local_quote(client: TestClient, *, recipient: str | None = None) -> dict:
    response = client.post(
        "/api/v1/withdrawals/quote",
        json={
            "pool_id": "pool_eth_01",
            "recipient_address": recipient or normal_address(2),
            "relayer_id": "rel_01",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def local_withdrawal_payload(
    quote: dict,
    *,
    proof: str = GROTH16_PROOF,
    root: str = CURRENT_ROOT,
    nullifier: str = WITHDRAWAL_NULLIFIER,
    recipient: str | None = None,
    fee_wei: str | None = None,
) -> dict:
    return {
        "quote_id": quote["quote_id"],
        "proof": proof,
        "root": root,
        "nullifier": nullifier,
        "recipient": recipient or normal_address(2),
        "relayer_fee_wei": fee_wei or quote["relayer_fee_wei"],
    }


def test_withdraw_calldata_matches_known_abi_vector():
    # Literal vector matching `cast calldata "withdraw(bytes,bytes32,bytes32,
    # address,uint256,bytes32)"`: selector, head offset 0xc0, five static
    # args, bytes length 0x100, then eight proof words. This catches the common
    # mistake of using 0x20 when the head is six words long.
    proof = "0x" + "ab" * 256
    recipient = "0x" + "00" * 18 + "dead"
    expected = (
        "0xc890dc66"
        + "0" * 62
        + "c0"
        + "11" * 32  # root word
        + "22" * 32  # nullifier word
        + "0" * 60
        + "dead"  # recipient word
        + f"{100000000000000:064x}"
        + "706f6f6c5f6574685f3031"
        + "0" * 42  # right-padded "pool_eth_01"
        + f"{256:064x}"
        + "ab" * 256
    )
    encoded = encode_withdraw_calldata(
        proof,
        "0x" + "11" * 32,
        "0x" + "22" * 32,
        recipient,
        100_000_000_000_000,
        "pool_eth_01",
    )
    assert encoded == expected
    assert len(encoded) == 970


def test_local_withdrawal_happy_path_and_idempotent_replay(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(
        indexer=fake,
        tx_hash=WITHDRAWAL_TX,
        add_deposit=False,
        add_withdrawal=True,
    )
    with local_client(
        tmp_path,
        fake,
        rpc,
        local_auto_withdraw=True,
        local_verifier_kind="groth16",
    ) as (client, app):
        quote = local_quote(client)
        assert quote["local_chain"] is True
        assert quote["submission_available"] is True
        assert quote["verifier_kind"] == "groth16-poseidon"
        assert quote["proof_encoding"] == (
            "abi(uint256[2],uint256[2][2],uint256[2])"
        )
        assert "unaudited" in quote["warning"]
        rpc.withdrawal = {
            "nullifier": WITHDRAWAL_NULLIFIER,
            "recipient": normal_address(2),
            "fee_wei": quote["relayer_fee_wei"],
        }

        payload = local_withdrawal_payload(quote)
        response = client.post("/api/v1/local/withdrawals", json=payload)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["withdrawal_id"].startswith("wdr_")
        assert body["pool_id"] == "pool_eth_01"
        assert body["status"] == "confirmed"
        assert body["tx_hash"] == WITHDRAWAL_TX
        assert body["block_number"] == 14
        assert body["block_hash"] == WITHDRAWAL_BLOCK_HASH
        assert body["nullifier"] == WITHDRAWAL_NULLIFIER
        assert body["recipient"] == normal_address(2)
        assert body["fee_wei"] == quote["relayer_fee_wei"]
        assert body["confirmations"] == 1
        assert body["finality"] == "final"
        assert body["local_chain"] == "ANVIL"
        assert body["chain_source"] == "indexer"
        assert body["verifier_kind"] == "groth16-poseidon"
        assert body["mock"] is False
        assert GROTH16_PROOF not in response.text
        assert_no_secret_keys(body)

        assert len(rpc.calls) == 1
        transaction = rpc.calls[0]["params"][0]
        assert transaction["from"] == FROM_ADDRESS
        assert transaction["to"] == CONTRACT
        assert int(transaction["value"], 16) == 0
        assert transaction["data"] == encode_withdraw_calldata(
            GROTH16_PROOF,
            CURRENT_ROOT,
            WITHDRAWAL_NULLIFIER,
            normal_address(2),
            int(quote["relayer_fee_wei"]),
            "pool_eth_01",
        )

        with app.state.db.session() as session:
            stored = session.get(Withdrawal, body["withdrawal_id"])
            assert stored.status == "confirmed"
            assert stored.is_canonical is True
            assert stored.tx_hash == WITHDRAWAL_TX
            assert session.get(
                Nullifier, ("pool_eth_01", WITHDRAWAL_NULLIFIER)
            ) is not None
            stored_quote = session.get(WithdrawalQuote, quote["quote_id"])
            assert stored_quote.status == "submitted"
            broadcast = session.get(
                LocalWithdrawalBroadcast, quote["quote_id"]
            )
            assert broadcast.tx_hash == WITHDRAWAL_TX
            assert broadcast.proof_sha256 is not None
            assert GROTH16_PROOF[2:] not in broadcast.proof_sha256

        replay = client.post("/api/v1/local/withdrawals", json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json()["withdrawal_id"] == body["withdrawal_id"]
        assert len(rpc.calls) == 1

        different_proof = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(
                quote, proof="0x" + "22" * 256
            ),
        )
        assert different_proof.status_code == 409
        assert different_proof.json()["code"] == "QUOTE_CONSUMED"

        different_nullifier = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(
                quote,
                nullifier="0x" + "33" * 32,
            ),
        )
        assert different_nullifier.status_code == 409
        assert different_nullifier.json()["code"] == "QUOTE_CONSUMED"
        assert len(rpc.calls) == 1


def test_local_withdrawal_timeout_leaves_quote_usable_and_reuses_tx(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(
        indexer=fake,
        tx_hash=WITHDRAWAL_TX,
        add_deposit=False,
        add_withdrawal=False,
    )
    with local_client(
        tmp_path,
        fake,
        rpc,
        local_auto_withdraw=True,
        local_withdrawal_timeout_seconds=0.0,
    ) as (client, app):
        quote = local_quote(client)
        payload = local_withdrawal_payload(quote)

        first = client.post("/api/v1/local/withdrawals", json=payload)
        assert first.status_code == 504, first.text
        assert first.json()["code"] == "INDEXER_CONFIRMATION_TIMEOUT"
        assert first.json()["tx_hash"] == WITHDRAWAL_TX
        assert first.json()["status"] == "submitted"
        with app.state.db.session() as session:
            assert (
                session.get(WithdrawalQuote, quote["quote_id"]).status
                == "active"
            )
            assert (
                session.get(
                    LocalWithdrawalBroadcast, quote["quote_id"]
                ).withdrawal_id
                is None
            )

        retry = client.post("/api/v1/local/withdrawals", json=payload)
        assert retry.status_code == 504
        assert retry.json()["tx_hash"] == WITHDRAWAL_TX
        assert len(rpc.calls) == 1

        fake.withdrawal_items[WITHDRAWAL_NULLIFIER] = withdrawal_item(
            fee_wei=quote["relayer_fee_wei"]
        )
        confirmed = client.post("/api/v1/local/withdrawals", json=payload)
        assert confirmed.status_code == 201, confirmed.text
        assert confirmed.json()["tx_hash"] == WITHDRAWAL_TX
        assert len(rpc.calls) == 1


def test_local_withdrawal_reverted_receipt_is_clear_502_and_quote_stays_usable(
    tmp_path,
):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(
        indexer=fake,
        tx_hash=WITHDRAWAL_TX,
        add_deposit=False,
        add_withdrawal=False,
        receipt_status=0,
    )
    with local_client(
        tmp_path,
        fake,
        rpc,
        local_auto_withdraw=True,
        local_verifier_kind="groth16",
    ) as (client, app):
        quote = local_quote(client)
        payload = local_withdrawal_payload(quote)
        response = client.post("/api/v1/local/withdrawals", json=payload)
        assert response.status_code == 502, response.text
        body = response.json()
        assert body["code"] == "WITHDRAWAL_REVERTED"
        assert body["tx_hash"] == WITHDRAWAL_TX
        assert body["status"] == "reverted"
        assert body["block_number"] == 14
        assert body["gas_used"] == 0x52F8
        assert "0x" + "11" * 256 not in response.text
        assert len(rpc.calls) == 1
        assert len(rpc.receipt_calls) == 1

        with app.state.db.session() as session:
            assert (
                session.get(WithdrawalQuote, quote["quote_id"]).status
                == "active"
            )
            assert (
                session.get(LocalWithdrawalBroadcast, quote["quote_id"])
                is None
            )
            assert (
                session.query(Withdrawal)
                .filter(Withdrawal.nullifier_hash == WITHDRAWAL_NULLIFIER)
                .count()
                == 0
            )

        # A corrected proof/root can reuse the quote because the revert did
        # not consume it and the failed broadcast row was removed.
        rpc.receipt["status"] = "0x1"
        rpc.add_withdrawal = True
        rpc.withdrawal = {
            "nullifier": WITHDRAWAL_NULLIFIER,
            "recipient": normal_address(2),
            "fee_wei": quote["relayer_fee_wei"],
        }
        retry = client.post("/api/v1/local/withdrawals", json=payload)
        assert retry.status_code == 201, retry.text
        assert retry.json()["tx_hash"] == WITHDRAWAL_TX
        assert len(rpc.calls) == 2


def test_local_withdrawal_disabled_returns_calldata_without_tx(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(indexer=fake, add_deposit=False)
    with local_client(
        tmp_path,
        fake,
        rpc,
        local_auto_withdraw=False,
        local_verifier_kind="groth16",
    ) as (client, app):
        quote = local_quote(client)
        assert quote["submission_available"] is False
        response = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(quote),
        )
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "LOCAL_WITHDRAWAL_DISABLED"
        assert body["contract_address"] == CONTRACT
        assert body["calldata"] == encode_withdraw_calldata(
            GROTH16_PROOF,
            CURRENT_ROOT,
            WITHDRAWAL_NULLIFIER,
            normal_address(2),
            int(quote["relayer_fee_wei"]),
            "pool_eth_01",
        )
        assert body["instruction"] == (
            "submit the withdrawal from your own wallet"
        )
        assert body["local_chain"] == "ANVIL"
        assert body["verifier_kind"] == "groth16-poseidon"
        assert rpc.calls == []
        with app.state.db.session() as session:
            assert (
                session.get(WithdrawalQuote, quote["quote_id"]).status
                == "active"
            )
            assert (
                session.get(LocalWithdrawalBroadcast, quote["quote_id"])
                is None
            )


def test_local_withdrawal_quote_validation_and_signal_mismatch(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(indexer=fake, add_deposit=False)
    with local_client(
        tmp_path, fake, rpc, local_auto_withdraw=True
    ) as (client, app):
        missing = client.post(
            "/api/v1/local/withdrawals",
            json={
                "quote_id": "q_missing",
                "proof": GROTH16_PROOF,
                "root": CURRENT_ROOT,
                "nullifier": WITHDRAWAL_NULLIFIER,
                "recipient": normal_address(2),
                "relayer_fee_wei": "1",
            },
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "QUOTE_NOT_FOUND"

        quote = local_quote(client)
        wrong_recipient = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(
                quote, recipient=normal_address(9)
            ),
        )
        assert wrong_recipient.status_code == 422
        assert wrong_recipient.json()["code"] == "INVALID_PUBLIC_SIGNALS"
        assert wrong_recipient.json()["field"] == "recipient"

        wrong_fee = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(quote, fee_wei="1"),
        )
        assert wrong_fee.status_code == 422
        assert wrong_fee.json()["code"] == "INVALID_PUBLIC_SIGNALS"
        assert wrong_fee.json()["field"] == "relayer_fee_wei"
        assert rpc.calls == []

        with app.state.db.session() as session:
            row = session.get(WithdrawalQuote, quote["quote_id"])
            row.expires_at = utcnow() - timedelta(seconds=1)
            session.commit()
        expired = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(quote),
        )
        assert expired.status_code == 409
        assert expired.json()["code"] == "QUOTE_EXPIRED"
        with app.state.db.session() as session:
            assert (
                session.get(WithdrawalQuote, quote["quote_id"]).status
                == "expired"
            )


def test_local_withdrawal_malformed_proof_and_public_signals(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(indexer=fake, add_deposit=False)
    with local_client(
        tmp_path, fake, rpc, local_auto_withdraw=True
    ) as (client, _app):
        quote = local_quote(client)
        short_proof = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(
                quote, proof="0x" + "11" * 128
            ),
        )
        assert short_proof.status_code == 422
        assert short_proof.json()["code"] == "INVALID_PROOF"
        assert GROTH16_PROOF not in short_proof.text

        oversized_proof = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(
                quote, proof="0x" + "11" * 257
            ),
        )
        assert oversized_proof.status_code == 422
        assert oversized_proof.json()["code"] == "INVALID_PROOF"

        bad_root = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(quote, root="0x1234"),
        )
        assert bad_root.status_code == 422
        assert bad_root.json()["code"] == "INVALID_PUBLIC_SIGNALS"

        bad_recipient = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(
                quote, recipient="0x1234"
            ),
        )
        assert bad_recipient.status_code == 422
        assert bad_recipient.json()["code"] == "INVALID_PUBLIC_SIGNALS"
        assert rpc.calls == []


def test_local_withdrawal_root_stale_and_unknown(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(indexer=fake, add_deposit=False)
    with local_client(
        tmp_path, fake, rpc, local_auto_withdraw=True
    ) as (client, _app):
        quote = local_quote(client)
        stale = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(
                quote, root="0x" + "9" * 64
            ),
        )
        assert stale.status_code == 409
        body = stale.json()
        assert body["code"] == "ROOT_STALE"
        assert body["current_root"] == CURRENT_ROOT
        assert body["ready_roots"] == [CURRENT_ROOT]
        assert GROTH16_PROOF not in stale.text
        assert rpc.calls == []

    empty = FakeIndexer(root_items={})
    with local_client(
        tmp_path,
        empty,
        FakeRpc(indexer=empty, add_deposit=False),
        local_auto_withdraw=True,
    ) as (client, _app):
        quote = local_quote(client)
        unknown = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(quote),
        )
        assert unknown.status_code == 409
        assert unknown.json()["code"] == "UNKNOWN_ROOT"
        assert unknown.json()["ready_roots"] == []


def test_local_withdrawal_nullifier_already_spent(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    rpc = FakeRpc(indexer=fake, add_deposit=False)
    with local_client(
        tmp_path, fake, rpc, local_auto_withdraw=True
    ) as (client, _app):
        quote = local_quote(client)
        fake.withdrawal_items[WITHDRAWAL_NULLIFIER] = withdrawal_item(
            fee_wei=quote["relayer_fee_wei"]
        )
        response = client.post(
            "/api/v1/local/withdrawals",
            json=local_withdrawal_payload(quote),
        )
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "NULLIFIER_SPENT"
        assert body["withdrawal"]["tx_hash"] == WITHDRAWAL_TX
        assert body["withdrawal"]["nullifier"] == WITHDRAWAL_NULLIFIER
        assert "note" not in body["withdrawal"]
        assert "secret" not in body["withdrawal"]
        assert rpc.calls == []


def test_local_withdrawal_rate_limit_scope(tmp_path):
    fake = FakeIndexer(root_items={"pool_eth_01": [root_item()]})
    with local_client(
        tmp_path,
        fake,
        local_auto_withdraw=False,
        rate_limit_local_withdrawal=1,
    ) as (client, _app):
        quote = local_quote(client)
        payload = local_withdrawal_payload(quote)
        first = client.post("/api/v1/local/withdrawals", json=payload)
        assert first.status_code == 409
        assert first.json()["code"] == "LOCAL_WITHDRAWAL_DISABLED"
        assert first.headers["x-ratelimit-scope"] == "local_withdrawal"
        assert first.headers["cache-control"] == "no-store"
        second = client.post("/api/v1/local/withdrawals", json=payload)
        assert second.status_code == 429
        assert second.json()["code"] == "RATE_LIMITED"
        assert second.headers["x-ratelimit-scope"] == "local_withdrawal"


def test_local_withdrawal_is_local_only(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/local/withdrawals",
            json={
                "quote_id": "q_missing",
                "proof": GROTH16_PROOF,
                "root": CURRENT_ROOT,
                "nullifier": WITHDRAWAL_NULLIFIER,
                "recipient": normal_address(2),
                "relayer_fee_wei": "1",
            },
        )
        assert response.status_code == 404
        assert response.json()["code"] == "LOCAL_ONLY"


def test_local_path_proxy_forwards_public_fields(tmp_path):
    fake = FakeIndexer(
        path_items={PATH_COMMITMENT: path_item()},
    )
    with local_client(tmp_path, fake) as (client, _app):
        response = client.get(
            f"/api/v1/pools/pool_eth_01/path/{PATH_COMMITMENT}"
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == set(PUBLIC_PATH_FIELDS)
        assert body["commitment"] == PATH_COMMITMENT
        assert body["leaf_index"] == 5
        assert body["leaf_count"] == 10
        assert body["tree_depth"] == 3
        assert body["path_elements"] == ["0x" + "00" * 32] * 3
        assert body["path_indices"] == [1, 0, 1]
        assert body["root"] == CURRENT_ROOT
        assert body["mock_verifier"] is False
        assert "note" not in body
        assert "secret" not in body
        assert "never-proxy-this" not in response.text
        assert response.headers["x-ratelimit-scope"] == "pool_path"


def test_local_path_proxy_error_mapping(tmp_path):
    fake = FakeIndexer(
        path_items={PATH_COMMITMENT: path_item()},
    )
    with local_client(tmp_path, fake) as (client, _app):
        missing = client.get(
            f"/api/v1/pools/pool_eth_01/path/0x{'07' * 32}"
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "COMMITMENT_NOT_FOUND"

        invalid = client.get(
            "/api/v1/pools/pool_eth_01/path/0x1234"
        )
        assert invalid.status_code == 400
        assert invalid.json()["code"] == "INVALID_COMMITMENT"

        non_canonical = client.get(
            f"/api/v1/pools/pool_eth_01/path/0x{'f' * 64}"
        )
        assert non_canonical.status_code == 422
        assert non_canonical.json()["code"] == "NON_CANONICAL_COMMITMENT"

        fake.path_errors[PATH_COMMITMENT] = (
            400,
            "INVALID_COMMITMENT",
        )
        passthrough = client.get(
            f"/api/v1/pools/pool_eth_01/path/{PATH_COMMITMENT}"
        )
        assert passthrough.status_code == 400
        assert passthrough.json()["code"] == "INVALID_COMMITMENT"

        fake.down = True
        down = client.get(
            f"/api/v1/pools/pool_eth_01/path/{PATH_COMMITMENT}"
        )
        assert down.status_code == 503
        assert down.json()["code"] == "INDEXER_UNAVAILABLE"


def test_local_path_proxy_is_local_only(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/pools/pool_eth_01/path/{PATH_COMMITMENT}"
        )
        assert response.status_code == 404
        assert response.json()["code"] == "LOCAL_ONLY"


def test_local_verifier_kind_labels_mock_and_groth16(tmp_path):
    fake = FakeIndexer()
    with local_client(
        tmp_path, fake, local_verifier_kind="mock"
    ) as (client, _app):
        health = client.get("/api/v1/health").json()
        assert health["verifier_kind"] == "mock"
        assert health["services"]["verifier"] == (
            "MOCK_VERIFIER (shape-only, no ZK)"
        )
        assert "MOCK_VERIFIER" in health["mock_services"]
        assert "MOCK VERIFIER" in health["warning"]

    with local_client(
        tmp_path, fake, local_verifier_kind="groth16"
    ) as (client, _app):
        health = client.get("/api/v1/health").json()
        assert health["verifier_kind"] == "groth16-poseidon"
        assert health["services"]["verifier"] == (
            "GROTH16_POSEIDON (development zkey, unaudited)"
        )
        assert "MOCK_VERIFIER" not in health["mock_services"]
        assert health["mock_services"] == ["MOCK_COMPLIANCE"]
        assert "unaudited" in health["warning"]
        assert "production" in health["warning"]

        root = client.get("/").json()
        assert root["verifier_kind"] == "groth16-poseidon"
        assert "MOCK_VERIFIER" not in root["mock_services"]
        assert "MOCK_VERIFIER" not in root["services"]["verifier"]

        quote = local_quote(client)
        assert quote["verifier_kind"] == "groth16-poseidon"
        assert quote["proof_verifier"] == "GROTH16_POSEIDON"


def test_mock_mode_is_unchanged_and_never_uses_an_indexer(settings):
    app = create_app(settings)
    assert app.state.indexer_client is None
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        body = health.json()
        assert body["mode"] == "mock"
        assert body["mock"] is True
        assert "MOCK_CHAIN" in body["services"]["chain"]
        assert "MOCK_CHAIN" in body["mock_services"]
        assert "indexer" not in body
        assert health.headers["x-veilpool-mock"] == "true"

        pools = client.get("/api/v1/pools").json()
        assert pools["mode"] == "mock"
        assert pools["mock"] is True
        assert len(pools["items"]) == 6

        local_only = client.post(
            "/api/v1/local/deposits",
            json={"intent_id": "dep_missing", "commitment": COMMITMENT},
        )
        assert local_only.status_code == 404
        assert local_only.json()["code"] == "LOCAL_ONLY"
