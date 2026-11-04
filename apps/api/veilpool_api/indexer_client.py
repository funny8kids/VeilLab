"""HTTP client for the standalone VeilPool indexer.

The indexer is a public-chain read model. This client only forwards the public
fields listed in ``PUBLIC_DEPOSIT_FIELDS``; unknown indexer fields (including
anything note-like) are dropped. There is no retry loop that could hide a down
indexer: transport failures are mapped to stable errors immediately.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

_HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_HEX20_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

PUBLIC_DEPOSIT_FIELDS = (
    "chain_id",
    "contract_address",
    "event_type",
    "pool_id",
    "pool_key",
    "commitment",
    "leaf_index",
    "tx_hash",
    "block_number",
    "block_hash",
    "block_timestamp",
    "log_index",
    "canonical",
    "confirmations",
    "finality",
    "indexed_at",
)

PUBLIC_ROOT_FIELDS = (
    "chain_id",
    "contract_address",
    "event_type",
    "pool_id",
    "pool_key",
    "root",
    "leaf_index",
    "tx_hash",
    "block_number",
    "block_hash",
    "block_timestamp",
    "log_index",
    "canonical",
    "confirmations",
    "finality",
    "indexed_at",
)

# Withdrawal events expose only public chain facts. There is deliberately no
# proof, witness or note field in this allow-list.
PUBLIC_WITHDRAWAL_FIELDS = (
    "chain_id",
    "contract_address",
    "event_type",
    "pool_id",
    "pool_key",
    "nullifier",
    "recipient",
    "fee_wei",
    "tx_hash",
    "block_number",
    "block_hash",
    "block_timestamp",
    "log_index",
    "canonical",
    "confirmations",
    "finality",
    "indexed_at",
)

# Merkle-path proxy allow-list. Path elements and indices are public membership
# data; no note preimage, secret or proof is forwarded.
PUBLIC_PATH_FIELDS = (
    "chain_id",
    "contract_address",
    "pool_id",
    "pool_key",
    "commitment",
    "leaf_index",
    "leaf_count",
    "tree_depth",
    "root",
    "root_block_number",
    "root_block_hash",
    "path_elements",
    "path_indices",
    "canonical_only",
    "mock_verifier",
)


class IndexerError(Exception):
    """Stable indexer failure mapped by the API layer.

    ``code`` is one of ``INDEXER_UNAVAILABLE``, ``INDEXER_TIMEOUT``,
    ``INDEXER_BAD_RESPONSE`` or ``INDEXER_MISMATCH``. ``status_code`` is the
    HTTP status the API should use when it surfaces the error.
    """

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        status_code: int = 503,
        indexer_code: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.indexer_code = indexer_code


def _bad_response(detail: str) -> IndexerError:
    return IndexerError(
        "INDEXER_BAD_RESPONSE", detail, status_code=502
    )


def _as_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise _bad_response(f"Indexer field '{field}' is not an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise _bad_response(
            f"Indexer field '{field}' is not an integer."
        ) from exc


def _as_hex32(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HEX32_RE.match(value):
        raise _bad_response(
            f"Indexer field '{field}' is not 0x-prefixed 32-byte hex."
        )
    return value.lower()


def _as_optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, field)


def _as_wei(value: Any, field: str) -> str:
    if isinstance(value, bool):
        raise _bad_response(f"Indexer field '{field}' is not an unsigned integer.")
    if isinstance(value, int):
        if value < 0:
            raise _bad_response(
                f"Indexer field '{field}' is not an unsigned integer."
            )
        return str(value)
    if isinstance(value, str) and value.isdigit():
        return str(int(value))
    raise _bad_response(f"Indexer field '{field}' is not an unsigned integer.")


def _public_deposit(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _bad_response("Indexer deposit item is not an object.")
    commitment = _as_hex32(item.get("commitment"), "commitment")
    tx_hash = _as_hex32(item.get("tx_hash"), "tx_hash")
    block_hash = _as_hex32(item.get("block_hash"), "block_hash")
    pool_id = _as_hex32(item.get("pool_id"), "pool_id")
    pool_key = item.get("pool_key")
    if pool_key is not None and not isinstance(pool_key, str):
        raise _bad_response("Indexer field 'pool_key' is not a string.")
    contract_address = item.get("contract_address")
    if contract_address is not None and not (
        isinstance(contract_address, str)
        and _HEX20_RE.match(contract_address)
    ):
        raise _bad_response(
            "Indexer field 'contract_address' is not a 20-byte address."
        )
    return {
        "chain_id": _as_int(item.get("chain_id"), "chain_id"),
        "contract_address": (
            contract_address.lower() if contract_address else None
        ),
        "event_type": "Deposit",
        "pool_id": pool_id,
        "pool_key": pool_key,
        "commitment": commitment,
        "leaf_index": _as_int(item.get("leaf_index"), "leaf_index"),
        "tx_hash": tx_hash,
        "block_number": _as_int(item.get("block_number"), "block_number"),
        "block_hash": block_hash,
        "block_timestamp": _as_int(
            item.get("block_timestamp"), "block_timestamp"
        ),
        "log_index": _as_int(item.get("log_index"), "log_index"),
        "canonical": bool(item.get("canonical", True)),
        "confirmations": _as_optional_int(
            item.get("confirmations"), "confirmations"
        ),
        "finality": item.get("finality") or "unknown",
        "indexed_at": item.get("indexed_at"),
        "chain_source": "indexer",
        "mock": False,
    }


def _public_root(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _bad_response("Indexer root item is not an object.")
    root = _as_hex32(item.get("root"), "root")
    tx_hash = _as_hex32(item.get("tx_hash"), "tx_hash")
    block_hash = _as_hex32(item.get("block_hash"), "block_hash")
    pool_id = _as_hex32(item.get("pool_id"), "pool_id")
    pool_key = item.get("pool_key")
    if pool_key is not None and not isinstance(pool_key, str):
        raise _bad_response("Indexer field 'pool_key' is not a string.")
    return {
        "chain_id": _as_int(item.get("chain_id"), "chain_id"),
        "pool_id": pool_id,
        "pool_key": pool_key,
        "event_type": "RootUpdated",
        "root": root,
        "leaf_index": _as_optional_int(item.get("leaf_index"), "leaf_index"),
        "tx_hash": tx_hash,
        "block_number": _as_int(item.get("block_number"), "block_number"),
        "block_hash": block_hash,
        "block_timestamp": _as_int(
            item.get("block_timestamp"), "block_timestamp"
        ),
        "log_index": _as_int(item.get("log_index"), "log_index"),
        "canonical": bool(item.get("canonical", True)),
        "confirmations": _as_optional_int(
            item.get("confirmations"), "confirmations"
        ),
        "finality": item.get("finality") or "unknown",
        "indexed_at": item.get("indexed_at"),
        "chain_source": "indexer",
        "mock": False,
    }


def _public_withdrawal(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _bad_response("Indexer withdrawal item is not an object.")
    pool_key = item.get("pool_key")
    if pool_key is not None and not isinstance(pool_key, str):
        raise _bad_response("Indexer field 'pool_key' is not a string.")
    contract_address = item.get("contract_address")
    if contract_address is not None and not (
        isinstance(contract_address, str)
        and _HEX20_RE.match(contract_address)
    ):
        raise _bad_response(
            "Indexer field 'contract_address' is not a 20-byte address."
        )
    recipient = item.get("recipient")
    if not isinstance(recipient, str) or not _HEX20_RE.match(recipient):
        raise _bad_response(
            "Indexer field 'recipient' is not a 20-byte address."
        )
    return {
        "chain_id": _as_int(item.get("chain_id"), "chain_id"),
        "contract_address": (
            contract_address.lower() if contract_address else None
        ),
        "event_type": "Withdrawal",
        "pool_id": _as_hex32(item.get("pool_id"), "pool_id"),
        "pool_key": pool_key,
        "nullifier": _as_hex32(item.get("nullifier"), "nullifier"),
        "recipient": recipient.lower(),
        "fee_wei": _as_wei(item.get("fee_wei"), "fee_wei"),
        "tx_hash": _as_hex32(item.get("tx_hash"), "tx_hash"),
        "block_number": _as_int(item.get("block_number"), "block_number"),
        "block_hash": _as_hex32(item.get("block_hash"), "block_hash"),
        "block_timestamp": _as_int(
            item.get("block_timestamp"), "block_timestamp"
        ),
        "log_index": _as_int(item.get("log_index"), "log_index"),
        "canonical": bool(item.get("canonical", True)),
        "confirmations": _as_optional_int(
            item.get("confirmations"), "confirmations"
        ),
        "finality": item.get("finality") or "unknown",
        "indexed_at": item.get("indexed_at"),
        "chain_source": "indexer",
        "mock": False,
    }


def _public_path(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _bad_response("Indexer path item is not an object.")
    tree_depth = _as_int(item.get("tree_depth"), "tree_depth")
    leaf_index = _as_int(item.get("leaf_index"), "leaf_index")
    leaf_count = _as_int(item.get("leaf_count"), "leaf_count")
    if tree_depth <= 0 or tree_depth > 64:
        raise _bad_response("Indexer field 'tree_depth' is out of range.")
    if leaf_index < 0 or leaf_count <= 0 or leaf_index >= leaf_count:
        raise _bad_response("Indexer path leaf bounds are invalid.")

    elements = item.get("path_elements")
    indices = item.get("path_indices")
    if not isinstance(elements, list) or not isinstance(indices, list):
        raise _bad_response("Indexer path elements/indices are missing.")
    if len(elements) != tree_depth or len(indices) != tree_depth:
        raise _bad_response(
            "Indexer path element count does not match tree_depth."
        )
    path_elements = [_as_hex32(value, "path_elements") for value in elements]
    path_indices: list[int] = []
    for value in indices:
        if isinstance(value, bool):
            raise _bad_response("Indexer path index is not 0 or 1.")
        try:
            bit = int(value)
        except (TypeError, ValueError) as exc:
            raise _bad_response("Indexer path index is not 0 or 1.") from exc
        if bit not in {0, 1}:
            raise _bad_response("Indexer path index is not 0 or 1.")
        path_indices.append(bit)

    pool_key = item.get("pool_key")
    if pool_key is not None and not isinstance(pool_key, str):
        raise _bad_response("Indexer field 'pool_key' is not a string.")
    contract_address = item.get("contract_address")
    if contract_address is not None and not (
        isinstance(contract_address, str)
        and _HEX20_RE.match(contract_address)
    ):
        raise _bad_response(
            "Indexer field 'contract_address' is not a 20-byte address."
        )

    return {
        "chain_id": _as_int(item.get("chain_id"), "chain_id"),
        "contract_address": (
            contract_address.lower() if contract_address else None
        ),
        "pool_id": _as_hex32(item.get("pool_id"), "pool_id"),
        "pool_key": pool_key,
        "commitment": _as_hex32(item.get("commitment"), "commitment"),
        "leaf_index": leaf_index,
        "leaf_count": leaf_count,
        "tree_depth": tree_depth,
        "root": _as_hex32(item.get("root"), "root"),
        "root_block_number": _as_optional_int(
            item.get("root_block_number"), "root_block_number"
        ),
        "root_block_hash": _as_hex32(
            item.get("root_block_hash"), "root_block_hash"
        ),
        "path_elements": path_elements,
        "path_indices": path_indices,
        "canonical_only": bool(item.get("canonical_only", True)),
        "mock_verifier": bool(item.get("mock_verifier", False)),
    }


def _public_pool(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _bad_response("Indexer pool item is not an object.")
    pool_key = item.get("pool_key")
    if pool_key is not None and not isinstance(pool_key, str):
        raise _bad_response("Indexer field 'pool_key' is not a string.")
    current_root = item.get("current_root")
    if current_root is not None:
        current_root = _as_hex32(current_root, "current_root")
    return {
        "pool_id": _as_hex32(item.get("pool_id"), "pool_id"),
        "pool_key": pool_key,
        "deposits": _as_int(item.get("deposits"), "deposits"),
        "withdrawals": _as_int(item.get("withdrawals"), "withdrawals"),
        "roots": _as_int(item.get("roots"), "roots"),
        "current_root": current_root,
        "current_root_block": _as_optional_int(
            item.get("current_root_block"), "current_root_block"
        ),
        "paused": bool(item.get("paused", False)),
    }


class IndexerClient:
    """Small synchronous client used from FastAPI's threadpool."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 3.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            headers={"Accept": "application/json"},
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        allow_not_found: bool = False,
        error_map: dict[int, tuple[str, str, int]] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{self.base_url}{path}"
        try:
            response = self._client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise IndexerError(
                "INDEXER_TIMEOUT",
                "The VeilPool indexer request timed out.",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise IndexerError(
                "INDEXER_UNAVAILABLE",
                "The VeilPool indexer is unavailable.",
                status_code=503,
            ) from exc

        if error_map and response.status_code in error_map:
            code, detail, status_code = error_map[response.status_code]
            raise IndexerError(
                code,
                detail,
                status_code=status_code,
                indexer_code=f"HTTP_{response.status_code}",
            )
        if response.status_code == 404 and allow_not_found:
            return None
        if response.status_code == 503:
            indexer_code = None
            try:
                detail = response.json().get("detail")
                if isinstance(detail, dict):
                    indexer_code = detail.get("code")
            except ValueError:
                pass
            raise IndexerError(
                "INDEXER_UNAVAILABLE",
                "The VeilPool indexer is not ready.",
                status_code=503,
                indexer_code=indexer_code,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise IndexerError(
                "INDEXER_BAD_RESPONSE",
                f"The VeilPool indexer returned HTTP {response.status_code}.",
                status_code=502,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise _bad_response(
                "The VeilPool indexer returned a non-JSON response."
            ) from exc
        if not isinstance(payload, dict):
            raise _bad_response(
                "The VeilPool indexer returned an unexpected payload."
            )
        return payload

    def health(self) -> dict[str, Any]:
        payload = self._request("/health")
        assert payload is not None
        chain_id = payload.get("chain_id")
        if chain_id is None:
            raise IndexerError(
                "INDEXER_UNAVAILABLE",
                "The VeilPool indexer has not verified a chain yet.",
                status_code=503,
                indexer_code="INDEXER_NOT_READY",
            )
        _as_int(chain_id, "chain_id")
        return payload

    def pools(self) -> list[dict[str, Any]]:
        payload = self._request("/pools")
        assert payload is not None
        items = payload.get("items")
        if not isinstance(items, list):
            raise _bad_response("Indexer response has no pool items.")
        return [_public_pool(item) for item in items]

    def list_deposits(
        self, pool_id: str, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        clamped = max(1, min(int(limit), 1000))
        payload = self._request(
            f"/pools/{pool_id}/deposits",
            params={"limit": clamped},
            allow_not_found=True,
        )
        if payload is None:
            # The indexer returns 404 when no canonical events exist for a
            # known pool. That is an empty result, not a failure.
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            raise _bad_response("Indexer response has no deposit items.")
        return [_public_deposit(item) for item in items]

    def list_roots(
        self, pool_id: str, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        return self.get_roots(pool_id, limit=limit)["items"]

    def get_roots(
        self, pool_id: str, *, limit: int = 1000
    ) -> dict[str, Any]:
        """Return the current root and root history for a pool."""

        clamped = max(1, min(int(limit), 1000))
        payload = self._request(
            f"/pools/{pool_id}/roots",
            params={"limit": clamped},
            allow_not_found=True,
        )
        if payload is None:
            return {"current_root": None, "current_root_block": None, "items": []}
        items = payload.get("items")
        if not isinstance(items, list):
            raise _bad_response("Indexer response has no root items.")
        parsed_items = [_public_root(item) for item in items]
        current_root = payload.get("current_root")
        if current_root is not None:
            current_root = _as_hex32(current_root, "current_root")
        elif parsed_items:
            current_root = parsed_items[-1]["root"]
        return {
            "current_root": current_root,
            "current_root_block": _as_optional_int(
                payload.get("current_root_block"), "current_root_block"
            ),
            "items": parsed_items,
        }

    def get_withdrawal(
        self, nullifier: str, pool_id: str | None = None
    ) -> dict[str, Any] | None:
        """Return one canonical withdrawal by nullifier, or None on 404."""

        params = {"pool_id": pool_id} if pool_id is not None else None
        payload = self._request(
            f"/withdrawals/{nullifier}",
            params=params,
            allow_not_found=True,
        )
        if payload is None:
            return None
        return _public_withdrawal(payload)

    def get_path(self, pool_id: str, commitment: str) -> dict[str, Any]:
        """Proxy one canonical Merkle path with public fields only."""

        payload = self._request(
            f"/pools/{pool_id}/path/{commitment}",
            error_map={
                404: (
                    "COMMITMENT_NOT_FOUND",
                    "No canonical deposit matches this commitment.",
                    404,
                ),
                400: (
                    "INVALID_COMMITMENT",
                    "The indexer rejected the commitment path parameter.",
                    400,
                ),
                422: (
                    "NON_CANONICAL_COMMITMENT",
                    "The commitment is not a canonical field element.",
                    422,
                ),
                503: (
                    "INDEXER_UNAVAILABLE",
                    "The VeilPool indexer is not ready.",
                    503,
                ),
            },
        )
        assert payload is not None
        if isinstance(payload.get("path"), dict):
            payload = payload["path"]
        return _public_path(payload)
