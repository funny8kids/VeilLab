"""Small JSON-RPC client for Anvil.

Only the methods needed by the indexer are implemented. ``httpx`` is used for
HTTP; tests inject an ``httpx.MockTransport`` so no Anvil process is required.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence

import httpx


class RpcError(RuntimeError):
    """JSON-RPC or transport failure."""


@dataclass(frozen=True)
class BlockHeader:
    number: int
    hash: str
    parent_hash: str
    timestamp: int

    @classmethod
    def from_rpc(cls, raw: dict[str, Any]) -> "BlockHeader":
        try:
            return cls(
                number=int(str(raw["number"]), 16),
                hash=str(raw["hash"]).lower(),
                parent_hash=str(raw["parentHash"]).lower(),
                timestamp=int(str(raw["timestamp"]), 16),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RpcError("malformed block header returned by RPC") from exc


def _hex_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 16)


class RpcClient:
    def __init__(
        self,
        url: str,
        *,
        timeout: float = 10.0,
        retries: int = 2,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url
        self.retries = retries
        self._client = client or httpx.Client(
            timeout=timeout, transport=transport
        )
        self._owns_client = client is None
        self._request_id = 0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "RpcClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(self, payload: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.post(self.url, json=payload)
                response.raise_for_status()
                body = response.json()
                if isinstance(body, list):
                    for item in body:
                        if "error" in item:
                            raise RpcError(
                                f"RPC error {item['error'].get('code')}: "
                                f"{item['error'].get('message')}"
                            )
                elif "error" in body:
                    raise RpcError(
                        f"RPC error {body['error'].get('code')}: "
                        f"{body['error'].get('message')}"
                    )
                return body
            except (httpx.HTTPError, ValueError, RpcError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(min(0.2 * (2**attempt), 2.0))
        raise RpcError(f"RPC request failed: {last_error}") from last_error

    def _call(self, method: str, params: Sequence[Any]) -> Any:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": list(params),
            }
        )
        if not isinstance(response, dict) or "result" not in response:
            raise RpcError(f"RPC response for {method} has no result")
        return response["result"]

    def chain_id(self) -> int:
        return _hex_int(self._call("eth_chainId", []))

    def block_number(self) -> int:
        return _hex_int(self._call("eth_blockNumber", []))

    def get_block(self, block: int | str) -> BlockHeader | None:
        tag = block if isinstance(block, str) else hex(block)
        raw = self._call("eth_getBlockByNumber", [tag, False])
        if raw is None:
            return None
        return BlockHeader.from_rpc(raw)

    def get_blocks(self, numbers: Sequence[int]) -> list[BlockHeader | None]:
        """Fetch headers in one JSON-RPC batch, preserving the input order."""

        if not numbers:
            return []
        payload = []
        ids: list[str] = []
        for number in numbers:
            request_id = f"block-{number}"
            ids.append(request_id)
            payload.append(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "eth_getBlockByNumber",
                    "params": [hex(number), False],
                }
            )
        response = self._post(payload)
        if not isinstance(response, list):
            raise RpcError("batched block request did not return a list")
        by_id = {str(item.get("id")): item for item in response}
        headers: list[BlockHeader | None] = []
        for request_id in ids:
            item = by_id.get(request_id)
            if item is None or "result" not in item:
                raise RpcError(f"missing batch response for {request_id}")
            raw = item["result"]
            headers.append(None if raw is None else BlockHeader.from_rpc(raw))
        return headers

    def get_logs(
        self,
        *,
        address: str,
        from_block: int,
        to_block: int,
        topics: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "address": address,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }
        if topics:
            params["topics"] = topics
        result = self._call("eth_getLogs", [params])
        if not isinstance(result, list):
            raise RpcError("eth_getLogs did not return a list")
        return result
