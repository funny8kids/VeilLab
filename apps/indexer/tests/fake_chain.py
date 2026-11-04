"""A tiny deterministic Anvil-like JSON-RPC fixture.

No Anvil, Foundry or network access is required. It implements the exact subset
of JSON-RPC used by the indexer: chain id, block number, block headers and logs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from veilpool_indexer.events import EVENT_TOPICS

CONTRACT_ADDRESS = "0x" + "11" * 20
GENESIS_HASH = "0x" + "00" * 32
BASE_TIMESTAMP = 1_700_000_000


def pool_id(label: str) -> str:
    raw = label.encode("utf-8")
    assert len(raw) <= 32
    return "0x" + raw.hex().ljust(64, "0")


POOL_ETH_01 = pool_id("pool_eth_01")
POOL_ETH_1 = pool_id("pool_eth_1")
POOL_ETH_10 = pool_id("pool_eth_10")


def _bytes32(value: str) -> str:
    raw = value.lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    return raw.rjust(64, "0")


def _uint(value: int) -> str:
    return f"{value:064x}"


def _address(value: str) -> str:
    return value.lower().replace("0x", "").rjust(64, "0")


def _string(value: str) -> str:
    raw = value.encode("utf-8")
    padded = raw.hex().ljust(((len(raw) + 31) // 32) * 64, "0") if raw else ""
    return _uint(32) + _uint(len(raw)) + padded


def encode_event(event_type: str, pool: str, **kwargs: Any) -> tuple[list[str], str]:
    topic = EVENT_TOPICS[event_type]
    topics = [topic, pool]
    if event_type == "Deposit":
        data = (
            _bytes32(kwargs["commitment"])
            + _uint(int(kwargs.get("leaf_index", 0)))
            + _uint(int(kwargs.get("timestamp", BASE_TIMESTAMP)))
        )
    elif event_type == "Withdrawal":
        data = (
            _bytes32(kwargs["nullifier"])
            + _address(kwargs["recipient"])
            + _uint(int(kwargs.get("fee", 0)))
            + _uint(int(kwargs.get("timestamp", BASE_TIMESTAMP)))
        )
    elif event_type == "RootUpdated":
        data = _bytes32(kwargs["root"]) + _uint(int(kwargs.get("leaf_index", 0)))
    elif event_type == "PoolPaused":
        data = _string(kwargs.get("reason", "demo pause"))
    elif event_type == "PoolResumed":
        data = ""
    elif event_type == "PoolCreated":
        data = (
            _uint(int(kwargs["denomination"]))
            + _uint(int(kwargs["root_window"]))
            + _uint(int(kwargs["maturity"]))
        )
    else:  # pragma: no cover - fixture misuse
        raise ValueError(f"unsupported event {event_type}")
    return topics, "0x" + data


@dataclass
class FakeChain:
    chain_id: int = 31337
    blocks: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def tip(self) -> int:
        return max(self.blocks) if self.blocks else 0


def block(
    *events: tuple[str, dict[str, Any]],
    salt: str | None = None,
    timestamp: int | None = None,
    pool: str = POOL_ETH_01,
) -> dict[str, Any]:
    """Describe a block's VeilPool events for ``build_chain``."""

    return {
        "salt": salt,
        "timestamp": timestamp,
        "pool": pool,
        "events": list(events),
    }


def build_chain(
    specs: list[dict[str, Any]],
    *,
    chain_id: int = 31337,
    genesis_hash: str = GENESIS_HASH,
) -> FakeChain:
    chain = FakeChain(chain_id=chain_id)
    parent = genesis_hash
    for number, spec in enumerate(specs, start=1):
        salt = spec.get("salt") or f"block-{number}"
        events = spec["events"]
        tx_hashes = [
            "0x"
            + hashlib.sha256(f"tx:{number}:{index}:{salt}".encode("utf-8")).hexdigest()
            for index in range(len(events))
        ]
        material = json.dumps(
            {
                "number": number,
                "parent": parent,
                "salt": salt,
                "pool": spec.get("pool", POOL_ETH_01),
                "events": events,
            },
            sort_keys=True,
            default=str,
        )
        block_hash = "0x" + hashlib.sha256(material.encode("utf-8")).hexdigest()
        timestamp = int(spec.get("timestamp") or BASE_TIMESTAMP + number * 12)

        logs = []
        for log_index, (event_type, kwargs) in enumerate(events):
            topics, data = encode_event(
                event_type, spec.get("pool", POOL_ETH_01), **kwargs
            )
            logs.append(
                {
                    "address": CONTRACT_ADDRESS,
                    "topics": topics,
                    "data": data,
                    "blockNumber": hex(number),
                    "blockHash": block_hash,
                    "transactionHash": tx_hashes[log_index],
                    "transactionIndex": "0x0",
                    "logIndex": hex(log_index),
                    "removed": False,
                }
            )
        chain.blocks[number] = {
            "number": hex(number),
            "hash": block_hash,
            "parentHash": parent,
            "timestamp": hex(timestamp),
            "transactions": [],
            "logs": logs,
        }
        parent = block_hash
    return chain


class FakeRpc:
    """Mutable fake RPC. Swap ``chain`` to simulate a reorg."""

    def __init__(self, chain: FakeChain) -> None:
        self.chain = chain
        self.calls: list[dict[str, Any]] = []

    def set_chain(self, chain: FakeChain) -> None:
        self.chain = chain

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle_request)

    def _handle_request(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if isinstance(payload, list):
            return httpx.Response(200, json=[self._handle_one(item) for item in payload])
        return httpx.Response(200, json=self._handle_one(payload))

    def _handle_one(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or []
        try:
            if method == "eth_chainId":
                result: Any = hex(self.chain.chain_id)
            elif method == "eth_blockNumber":
                result = hex(self.chain.tip)
            elif method == "eth_getBlockByNumber":
                tag = params[0]
                number = self.chain.tip if tag == "latest" else int(tag, 16)
                raw = self.chain.blocks.get(number)
                result = (
                    None
                    if raw is None
                    else {
                        "number": raw["number"],
                        "hash": raw["hash"],
                        "parentHash": raw["parentHash"],
                        "timestamp": raw["timestamp"],
                    }
                )
            elif method == "eth_getLogs":
                result = self._logs(params[0])
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"unsupported method {method}"},
                }
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:  # pragma: no cover - fixture error path
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    def _logs(self, flt: dict[str, Any]) -> list[dict[str, Any]]:
        address = str(flt["address"]).lower()
        from_block = int(str(flt["fromBlock"]), 16)
        to_block = int(str(flt["toBlock"]), 16)
        topics_filter = flt.get("topics") or []
        allowed_topics: set[str] | None = None
        if topics_filter:
            first = topics_filter[0]
            if isinstance(first, list):
                allowed_topics = {str(item).lower() for item in first}
            elif first is not None:
                allowed_topics = {str(first).lower()}

        result: list[dict[str, Any]] = []
        for number in range(from_block, to_block + 1):
            raw = self.chain.blocks.get(number)
            if raw is None:
                continue
            for log in raw["logs"]:
                if str(log["address"]).lower() != address:
                    continue
                if allowed_topics is not None and log["topics"][0] not in allowed_topics:
                    continue
                result.append(dict(log))
        return result
