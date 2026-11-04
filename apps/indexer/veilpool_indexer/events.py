"""Minimal ABI decoding for the VeilPool events.

The indexer deliberately does not depend on web3.py. Event signatures are
constant and the data layouts are small, so decoding is done here with explicit
word reads. Topic zero hashes are hard-coded and covered by tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .poolids import bytes32_to_pool_key, normalize_bytes32
from .rpc import BlockHeader

# keccak256 of the canonical event signatures in contracts/src/VeilPool.sol.
EVENT_TOPICS: dict[str, str] = {
    "Deposit": "0x35a268a90c41b0181a3b58b12063b25c3597e0d085532dfff38eaf88e946c30e",
    "Withdrawal": "0x50f7605661b92a36081a675fa4fb8ba18ccae0c0e065b12d23e8b29130e04208",
    "RootUpdated": "0xcdad51d1d27b433fdb6cbd1aefd9c7e059b11604ee1c1343b50bea6f6662cf84",
    "PoolPaused": "0x1c9c6b0f29e5f6fae1beda37920eb7180a0f01c699d1c84ad174ae3779d865ee",
    "PoolResumed": "0x866727027fd8d356b14c6faca42691c1a883c7199ea85ca402332f002fe80631",
    # Extra metadata event. It is indexed for discovery and is not one of the
    # five events required for the deposit/withdraw/root state machine.
    "PoolCreated": "0xe693a69a0b3c425d0853fd7d21540e9957c8e992218c14c706b6cd28f4b5d2b7",
}

TOPIC0_TO_TYPE = {topic: name for name, topic in EVENT_TOPICS.items()}


class EventDecodeError(ValueError):
    """Raised when a matching log cannot be decoded safely."""


@dataclass(frozen=True)
class DecodedEvent:
    event_type: str
    contract_address: str
    chain_id: int
    block_number: int
    block_hash: str
    block_timestamp: int
    log_index: int
    tx_hash: str
    pool_id: str
    pool_key: str | None
    commitment: str | None = None
    nullifier: str | None = None
    root: str | None = None
    leaf_index: int | None = None
    recipient: str | None = None
    fee_wei: str | None = None
    reason: str | None = None
    denomination_wei: str | None = None
    root_window: int | None = None
    maturity_seconds: int | None = None
    removed: bool = False

    def as_db_row(self, indexed_at: str) -> dict[str, Any]:
        row = asdict(self)
        row["canonical"] = 0 if self.removed else 1
        row["indexed_at"] = indexed_at
        return row


def _strip_hex(value: str) -> str:
    raw = value.lower()
    return raw[2:] if raw.startswith("0x") else raw


def _word(data: str, index: int) -> str:
    start = index * 64
    end = start + 64
    if len(data) < end:
        raise EventDecodeError("event data is shorter than the declared fields")
    return data[start:end]


def _as_uint(word: str) -> int:
    return int(word, 16)


def _as_log_index(value: object) -> int:
    text = str(value)
    if text.startswith("0x"):
        return int(text, 16)
    return int(text)


def _as_bytes32(word: str) -> str:
    return "0x" + word.lower()


def _as_address(word: str) -> str:
    return "0x" + word.lower()[-40:]


def _dynamic_string(data: str, offset_word_index: int) -> str:
    offset = _as_uint(_word(data, offset_word_index))
    start = offset * 2
    length_word = data[start : start + 64]
    if len(length_word) != 64:
        raise EventDecodeError("truncated dynamic string length")
    length = int(length_word, 16)
    payload = data[start + 64 : start + 64 + length * 2]
    if len(payload) != length * 2:
        raise EventDecodeError("truncated dynamic string payload")
    try:
        return bytes.fromhex(payload).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EventDecodeError("event string is not UTF-8") from exc


def decode_log(log: dict[str, Any], header: BlockHeader, chain_id: int) -> DecodedEvent | None:
    """Decode one ``eth_getLogs`` result.

    Returns ``None`` for unrelated logs. Raises ``EventDecodeError`` for a log
    that claims to be a VeilPool event but has malformed topics or data, so the
    indexer fails closed instead of storing a partial event.
    """

    topics = log.get("topics") or []
    if not topics:
        return None
    topic0 = str(topics[0]).lower()
    event_type = TOPIC0_TO_TYPE.get(topic0)
    if event_type is None:
        return None
    if len(topics) < 2:
        raise EventDecodeError(f"{event_type} log has no indexed poolId topic")

    pool_id = normalize_bytes32(str(topics[1]))
    data = _strip_hex(str(log.get("data") or "0x"))
    if len(data) % 64 != 0:
        raise EventDecodeError(f"{event_type} data is not word-aligned")

    log_block_hash = str(log.get("blockHash") or header.hash).lower()
    if log_block_hash != header.hash.lower():
        raise EventDecodeError("log blockHash does not match the supplied block header")

    contract_address = str(log.get("address") or "").lower()
    if len(contract_address) != 42 or not contract_address.startswith("0x"):
        raise EventDecodeError("log is missing a valid contract address")
    tx_hash = str(log.get("transactionHash") or "").lower()
    if len(tx_hash) != 66 or not tx_hash.startswith("0x"):
        raise EventDecodeError("log is missing a valid transactionHash")

    fields: dict[str, Any] = {}
    if event_type == "Deposit":
        fields = {
            "commitment": _as_bytes32(_word(data, 0)),
            "leaf_index": _as_uint(_word(data, 1)),
        }
    elif event_type == "Withdrawal":
        fields = {
            "nullifier": _as_bytes32(_word(data, 0)),
            "recipient": _as_address(_word(data, 1)),
            "fee_wei": str(_as_uint(_word(data, 2))),
        }
    elif event_type == "RootUpdated":
        fields = {
            "root": _as_bytes32(_word(data, 0)),
            "leaf_index": _as_uint(_word(data, 1)),
        }
    elif event_type == "PoolPaused":
        fields = {"reason": _dynamic_string(data, 0)}
    elif event_type == "PoolResumed":
        if data:
            raise EventDecodeError("PoolResumed must not have data fields")
    elif event_type == "PoolCreated":
        fields = {
            "denomination_wei": str(_as_uint(_word(data, 0))),
            "root_window": _as_uint(_word(data, 1)),
            "maturity_seconds": _as_uint(_word(data, 2)),
        }

    return DecodedEvent(
        event_type=event_type,
        contract_address=contract_address,
        chain_id=chain_id,
        block_number=header.number,
        block_hash=header.hash.lower(),
        block_timestamp=header.timestamp,
        log_index=_as_log_index(log.get("logIndex", "0x0")),
        tx_hash=tx_hash,
        pool_id=pool_id,
        pool_key=bytes32_to_pool_key(pool_id),
        removed=bool(log.get("removed", False)),
        **fields,
    )
