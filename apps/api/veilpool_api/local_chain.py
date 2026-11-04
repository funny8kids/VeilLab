"""Local Anvil JSON-RPC bridge for ``POST /api/v1/local/deposits``.

Anvil owns the unlocked development key. The API never accepts, stores or logs
a private key: it only asks Anvil to send a transaction from the configured
Anvil account. Everything in this module is public chain data.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from .indexer_client import IndexerClient, IndexerError
from .keccak import keccak_256

LOCAL_CHAIN_ID = 31337
LOCAL_CHAIN_LABEL = "ANVIL"
DEPOSIT_SIGNATURE = "deposit(bytes32)"
DEPOSIT_SELECTOR = "0x" + keccak_256(DEPOSIT_SIGNATURE.encode("ascii"))[:4].hex()
WITHDRAW_SIGNATURE = "withdraw(bytes,bytes32,bytes32,address,uint256,bytes32)"
WITHDRAW_SELECTOR = "0x" + keccak_256(WITHDRAW_SIGNATURE.encode("ascii"))[:4].hex()
GROTH16_PROOF_BYTES = 256
GROTH16_PROOF_ENCODING = "abi(uint256[2],uint256[2][2],uint256[2])"
# BN254 scalar field modulus used by the Poseidon/Groth16 local deployment.
BN254_FIELD_MODULUS = (
    21888242871839275222246405745257275088548364400416034343698204186575808495617
)

_HEX20_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_HEX256_RE = re.compile(r"^0x[0-9a-fA-F]{512}$")
_HEX_RE = re.compile(r"^0x[0-9a-fA-F]*$")
_MAX_UINT256 = (1 << 256) - 1


class LocalRpcError(Exception):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        status_code: int = 502,
        rpc_code: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.rpc_code = rpc_code


class IndexerMismatch(Exception):
    """The indexer returned a deposit for our tx with different public fields."""


def encode_deposit_calldata(commitment: str) -> str:
    """Encode ``deposit(bytes32 commitment)`` with exactly one public word.

    Only a 0x-prefixed 32-byte commitment is accepted. There is no place for a
    note, passphrase, secret or raw proof input in this calldata.
    """

    if not isinstance(commitment, str) or not _HEX32_RE.match(commitment):
        raise ValueError("commitment must be 0x-prefixed 32-byte hex")
    normalized = commitment.lower()
    if len(bytes.fromhex(normalized[2:])) != 32:
        raise ValueError("commitment must be exactly 32 bytes")
    calldata = DEPOSIT_SELECTOR + normalized[2:]
    if len(calldata) != 2 + 8 + 64:
        raise ValueError("encoded deposit calldata is not exactly 36 bytes")
    return calldata


def normalize_proof(proof: str) -> str:
    """Validate the exact 256-byte Groth16 ``soliditycalldata`` encoding."""

    if not isinstance(proof, str) or not _HEX256_RE.match(proof):
        raise ValueError(
            "proof must be exactly 256 bytes (0x-prefixed, 512 hex characters)"
        )
    normalized = proof.lower()
    if len(bytes.fromhex(normalized[2:])) != GROTH16_PROOF_BYTES:
        raise ValueError("proof must be exactly 256 bytes")
    return normalized


def normalize_hex32(value: str, *, name: str = "value") -> str:
    if not isinstance(value, str) or not _HEX32_RE.match(value):
        raise ValueError(f"{name} must be 0x-prefixed 32-byte hex")
    return value.lower()


def normalize_address(value: str, *, name: str = "recipient") -> str:
    if not isinstance(value, str) or not _HEX20_RE.match(value):
        raise ValueError(f"{name} must be 0x-prefixed 20-byte hex")
    normalized = value.lower()
    if normalized == "0x" + "0" * 40:
        raise ValueError(f"{name} must not be the zero address")
    return normalized


def encode_pool_id(pool_id: str) -> str:
    """Encode a short pool label as a right-padded ASCII bytes32.

    This is the convention used by the local deployment scripts and the
    Groth16 adapter: ``pool_eth_01`` becomes
    ``0x706f6f6c5f6574685f3031`` followed by zero padding.
    """

    if not isinstance(pool_id, str):
        raise ValueError("pool_id must be a string")
    raw = pool_id.strip().encode("utf-8")
    if not raw or len(raw) > 32 or b"\x00" in raw:
        raise ValueError("pool_id must be 1-32 UTF-8 bytes without NUL")
    return "0x" + raw.hex().ljust(64, "0")


def _receipt_quantity(
    value: Any, field: str, *, optional: bool = False
) -> int | None:
    if value is None:
        if optional:
            return None
        raise LocalRpcError(
            "LOCAL_RPC_BAD_RESPONSE",
            f"The local Anvil RPC receipt is missing '{field}'.",
            status_code=502,
        )
    if isinstance(value, bool):
        raise LocalRpcError(
            "LOCAL_RPC_BAD_RESPONSE",
            f"The local Anvil RPC receipt field '{field}' is invalid.",
            status_code=502,
        )
    if isinstance(value, int):
        if value < 0:
            raise LocalRpcError(
                "LOCAL_RPC_BAD_RESPONSE",
                f"The local Anvil RPC receipt field '{field}' is invalid.",
                status_code=502,
            )
        return value
    if isinstance(value, str) and re.match(r"^0x[0-9a-fA-F]+$", value):
        return int(value, 16)
    raise LocalRpcError(
        "LOCAL_RPC_BAD_RESPONSE",
        f"The local Anvil RPC receipt field '{field}' is invalid.",
        status_code=502,
    )


def _word(value: int) -> str:
    if value < 0 or value > _MAX_UINT256:
        raise ValueError("value does not fit in a uint256 word")
    return f"{value:064x}"


def encode_withdraw_calldata(
    proof: str,
    root: str,
    nullifier: str,
    recipient: str,
    relayer_fee: int,
    pool_id: str,
) -> str:
    """Encode ``withdraw(bytes,bytes32,bytes32,address,uint256,bytes32)``.

    The proof is a 256-byte Groth16 ``soliditycalldata`` blob. It is a dynamic
    ``bytes`` argument, so the ABI head carries an offset and the tail carries
    a length word plus the eight proof words. No note or witness field exists
    in this calldata.
    """

    normalized_proof = normalize_proof(proof)
    normalized_root = normalize_hex32(root, name="root")
    normalized_nullifier = normalize_hex32(nullifier, name="nullifier")
    normalized_recipient = normalize_address(recipient)
    normalized_pool = encode_pool_id(pool_id)
    if isinstance(relayer_fee, bool):
        raise ValueError("relayer_fee must be an unsigned integer")
    try:
        fee = int(relayer_fee)
    except (TypeError, ValueError) as exc:
        raise ValueError("relayer_fee must be an unsigned integer") from exc
    if fee < 0:
        raise ValueError("relayer_fee must be zero or positive")

    calldata = (
        WITHDRAW_SELECTOR
        # The head has six static words (5 static args + the dynamic offset),
        # so the proof tail starts at byte 192 (0xc0), not 32.
        + _word(6 * 32)
        + normalized_root[2:]
        + normalized_nullifier[2:]
        + _word(int(normalized_recipient, 16))
        + _word(fee)
        + normalized_pool[2:]
        + _word(GROTH16_PROOF_BYTES)
        + normalized_proof[2:]
    )
    # 4-byte selector + 6 head words + length word + 8 proof words.
    if len(calldata) != 2 + 8 + 64 * 15:
        raise ValueError("encoded withdrawal calldata is not 484 bytes")
    return calldata


class LocalRpcClient:
    """Minimal JSON-RPC client. Only ``eth_sendTransaction`` is exposed."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 3.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            headers={"Content-Type": "application/json"},
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, params: list[Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        try:
            response = self._client.post(self.url, json=payload)
        except httpx.TimeoutException as exc:
            raise LocalRpcError(
                "LOCAL_RPC_TIMEOUT",
                "The local Anvil RPC request timed out.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalRpcError(
                "LOCAL_RPC_UNAVAILABLE",
                "The local Anvil RPC is unavailable.",
                status_code=503,
            ) from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise LocalRpcError(
                "LOCAL_RPC_BAD_RESPONSE",
                f"The local Anvil RPC returned HTTP {response.status_code}.",
                status_code=502,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise LocalRpcError(
                "LOCAL_RPC_BAD_RESPONSE",
                "The local Anvil RPC returned a non-JSON response.",
                status_code=502,
            ) from exc
        if not isinstance(body, dict):
            raise LocalRpcError(
                "LOCAL_RPC_BAD_RESPONSE",
                "The local Anvil RPC returned an unexpected payload.",
                status_code=502,
            )
        error = body.get("error")
        if error is not None:
            rpc_code = None
            message = "The local Anvil RPC rejected the transaction."
            if isinstance(error, dict):
                rpc_code = error.get("code")
                if isinstance(error.get("message"), str):
                    message = (
                        "The local Anvil RPC rejected the transaction: "
                        + error["message"][:200]
                    )
            raise LocalRpcError(
                "LOCAL_RPC_ERROR",
                message,
                status_code=502,
                rpc_code=rpc_code if isinstance(rpc_code, int) else None,
            )
        return body.get("result")

    def send_transaction(
        self,
        *,
        from_address: str,
        to_address: str,
        value_wei: int,
        data: str,
    ) -> str:
        if not _HEX20_RE.match(from_address or ""):
            raise LocalRpcError(
                "LOCAL_RPC_BAD_REQUEST",
                "The configured local sender is not a 20-byte address.",
                status_code=500,
            )
        if not _HEX20_RE.match(to_address or ""):
            raise LocalRpcError(
                "LOCAL_RPC_BAD_REQUEST",
                "The configured contract address is not a 20-byte address.",
                status_code=500,
            )
        if value_wei < 0:
            raise LocalRpcError(
                "LOCAL_RPC_BAD_REQUEST",
                "The deposit value must be zero or positive.",
                status_code=500,
            )
        if not _HEX_RE.match(data or "") or len(data) % 2 != 0:
            raise LocalRpcError(
                "LOCAL_RPC_BAD_REQUEST",
                "Deposit calldata must be even-length 0x hex.",
                status_code=500,
            )
        transaction = {
            "from": from_address,
            "to": to_address,
            "value": hex(value_wei),
            "data": data,
        }
        result = self._call("eth_sendTransaction", [transaction])
        if not isinstance(result, str) or not _HEX32_RE.match(result):
            raise LocalRpcError(
                "LOCAL_RPC_BAD_RESPONSE",
                "The local Anvil RPC did not return a 32-byte transaction hash.",
                status_code=502,
            )
        return result.lower()

    def get_transaction_receipt(self, tx_hash: str) -> dict[str, Any] | None:
        """Return a small public receipt view, or ``None`` if not mined yet."""

        if not _HEX32_RE.match(tx_hash or ""):
            raise LocalRpcError(
                "LOCAL_RPC_BAD_REQUEST",
                "The transaction hash must be 0x-prefixed 32-byte hex.",
                status_code=500,
            )
        result = self._call("eth_getTransactionReceipt", [tx_hash.lower()])
        if result is None:
            return None
        if not isinstance(result, dict):
            raise LocalRpcError(
                "LOCAL_RPC_BAD_RESPONSE",
                "The local Anvil RPC returned an unexpected receipt payload.",
                status_code=502,
            )
        status = _receipt_quantity(result.get("status"), "status")
        if status not in {0, 1}:
            raise LocalRpcError(
                "LOCAL_RPC_BAD_RESPONSE",
                "The local Anvil RPC returned an invalid receipt status.",
                status_code=502,
            )
        return {
            "tx_hash": tx_hash.lower(),
            "status": status,
            "block_number": _receipt_quantity(
                result.get("blockNumber"), "blockNumber", optional=True
            ),
            "block_hash": (
                result["blockHash"].lower()
                if isinstance(result.get("blockHash"), str)
                and _HEX32_RE.match(result["blockHash"])
                else None
            ),
            "gas_used": _receipt_quantity(
                result.get("gasUsed"), "gasUsed", optional=True
            ),
        }


def wait_for_indexed_deposit(
    indexer: IndexerClient,
    pool_id: str,
    *,
    tx_hash: str,
    commitment: str,
    timeout_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    interval_seconds: float = 0.25,
) -> tuple[dict[str, Any] | None, IndexerError | None]:
    """Poll the indexer for our tx up to ``timeout_seconds``.

    Returns ``(deposit, last_error)``. ``deposit`` is ``None`` on timeout. A
    deposit for the same tx with a different commitment raises
    :class:`IndexerMismatch` so the caller can return 502 without consuming the
    intent.
    """

    deadline = monotonic() + max(0.0, float(timeout_seconds))
    last_error: IndexerError | None = None
    while True:
        try:
            items = indexer.list_deposits(pool_id, limit=1000)
            last_error = None
            for item in items:
                if item["tx_hash"].lower() != tx_hash.lower():
                    continue
                if item["commitment"].lower() != commitment.lower():
                    raise IndexerMismatch(
                        "The indexer returned a different commitment for the "
                        "broadcast transaction."
                    )
                return item, None
        except IndexerMismatch:
            raise
        except IndexerError as exc:
            last_error = exc

        remaining = deadline - monotonic()
        if remaining <= 0:
            return None, last_error
        sleep(min(max(0.05, interval_seconds), remaining))


def wait_for_transaction_receipt(
    rpc: "LocalRpcClient",
    tx_hash: str,
    *,
    timeout_seconds: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    interval_seconds: float = 0.1,
) -> dict[str, Any] | None:
    """Short receipt poll so an immediate revert is reported, not a timeout."""

    deadline = monotonic() + max(0.0, float(timeout_seconds))
    while True:
        receipt = rpc.get_transaction_receipt(tx_hash)
        if receipt is not None:
            return receipt
        remaining = deadline - monotonic()
        if remaining <= 0:
            return None
        sleep(min(max(0.05, interval_seconds), remaining))


def wait_for_indexed_withdrawal(
    indexer: IndexerClient,
    pool_id: str,
    *,
    tx_hash: str,
    nullifier: str,
    recipient: str,
    relayer_fee_wei: int,
    timeout_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    interval_seconds: float = 0.25,
) -> tuple[dict[str, Any] | None, IndexerError | None]:
    """Poll the indexer for our withdrawal up to ``timeout_seconds``.

    Returns ``(withdrawal, last_error)``. ``withdrawal`` is ``None`` on
    timeout. A withdrawal for the same nullifier with different public fields
    raises :class:`IndexerMismatch` so the caller can return 502 without
    consuming the quote.
    """

    deadline = monotonic() + max(0.0, float(timeout_seconds))
    last_error: IndexerError | None = None
    while True:
        try:
            item = indexer.get_withdrawal(nullifier, pool_id=pool_id)
            last_error = None
            if item is not None:
                if item["tx_hash"].lower() != tx_hash.lower():
                    raise IndexerMismatch(
                        "The indexer returned a different transaction for the "
                        "broadcast nullifier."
                    )
                if item["nullifier"].lower() != nullifier.lower():
                    raise IndexerMismatch(
                        "The indexer returned a different nullifier."
                    )
                if item["recipient"].lower() != recipient.lower():
                    raise IndexerMismatch(
                        "The indexed withdrawal has a different recipient."
                    )
                if int(item["fee_wei"]) != int(relayer_fee_wei):
                    raise IndexerMismatch(
                        "The indexed withdrawal has a different relayer fee."
                    )
                if item.get("pool_key") not in {None, pool_id}:
                    raise IndexerMismatch(
                        "The indexed withdrawal belongs to a different pool."
                    )
                return item, None
        except IndexerMismatch:
            raise
        except IndexerError as exc:
            last_error = exc

        remaining = deadline - monotonic()
        if remaining <= 0:
            return None, last_error
        sleep(min(max(0.05, interval_seconds), remaining))
