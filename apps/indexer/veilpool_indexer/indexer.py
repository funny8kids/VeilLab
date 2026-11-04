"""Polling indexer with common-ancestor reorg handling."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Sequence

from .config import FORBIDDEN_MAINNET_CHAIN_IDS, Settings
from .events import EVENT_TOPICS, DecodedEvent, decode_log
from .rpc import BlockHeader, RpcClient
from .store import Store

LOGGER = logging.getLogger("veilpool_indexer")

# The topic filter is an OR-list of the five required events plus PoolCreated.
# PoolCreated is used only for pool discovery/metadata.
TOPIC_FILTER = [[*EVENT_TOPICS.values()]]


class ChainIdError(RuntimeError):
    """The RPC chain ID is not an explicitly allowed local/testnet chain."""


class ReorgTooDeep(RuntimeError):
    """A reorg exceeded INDEXER_MAX_REORG_DEPTH; refuse to guess."""


class ScanError(RuntimeError):
    """The RPC returned an inconsistent block range."""


@dataclass(frozen=True)
class SyncResult:
    chain_id: int
    tip_block: int
    indexed_block: int
    scanned_blocks: int
    events_indexed: int
    reorg: bool
    ancestor_block: int | None
    previous_last_block: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "tip_block": self.tip_block,
            "indexed_block": self.indexed_block,
            "scanned_blocks": self.scanned_blocks,
            "events_indexed": self.events_indexed,
            "reorg": self.reorg,
            "ancestor_block": self.ancestor_block,
            "previous_last_block": self.previous_last_block,
        }


class Indexer:
    def __init__(self, settings: Settings, rpc: RpcClient, store: Store) -> None:
        self.settings = settings
        self.rpc = rpc
        self.store = store

    # ------------------------------------------------------------------
    # Chain and cursor setup
    # ------------------------------------------------------------------

    def verify_chain(self) -> int:
        """Read the RPC chain ID and fail closed unless it is allow-listed."""

        actual = self.rpc.chain_id()
        if actual in FORBIDDEN_MAINNET_CHAIN_IDS:
            raise ChainIdError(
                f"RPC chain ID {actual} is a known mainnet; this indexer is local-only"
            )
        if actual not in self.settings.allowed_chain_ids:
            allowed = ", ".join(str(item) for item in sorted(self.settings.allowed_chain_ids))
            raise ChainIdError(
                f"RPC chain ID {actual} is not allow-listed ({allowed}). "
                "Refusing to index."
            )
        stored = self.store.get_meta("chain_id")
        if stored is not None and int(stored) != actual:
            raise ChainIdError(
                f"indexer.db already holds chain_id={stored}; RPC reports {actual}. "
                "Use a different INDEXER_DB."
            )
        self.store.set_meta("chain_id", str(actual))
        return actual

    def _ensure_cursor(self, chain_id: int) -> dict[str, Any]:
        address = self.settings.contract_address
        cursor = self.store.get_cursor(chain_id, address)
        if cursor is not None:
            return cursor

        # The synthetic base block has no trusted hash. Skipping the parent
        # check for the first scanned block lets the indexer recover if the
        # configured start block itself was reorged before first sync.
        base_block = self.settings.start_block - 1
        self.store.set_cursor(chain_id, address, base_block, None)
        cursor = self.store.get_cursor(chain_id, address)
        assert cursor is not None
        return cursor

    # ------------------------------------------------------------------
    # Reorg handling
    # ------------------------------------------------------------------

    def _find_common_ancestor(
        self,
        *,
        chain_id: int,
        cursor: dict[str, Any],
        tip: int,
    ) -> tuple[int, str | None]:
        """Walk back from the current tip until a stored header hash matches.

        The stored canonical header table is populated for every scanned block,
        so this is a real common-ancestor search, not a fixed rollback window.
        The walk is bounded by ``INDEXER_MAX_REORG_DEPTH`` to fail closed on a
        pathological reorg.
        """

        last_block = int(cursor["last_block"])
        block = min(last_block, tip)
        lowest = self.settings.start_block

        while block >= lowest:
            if last_block - block > self.settings.max_reorg_depth:
                raise ReorgTooDeep(
                    f"no common ancestor within {self.settings.max_reorg_depth} blocks "
                    f"below {last_block}"
                )
            current = self.rpc.get_block(block)
            stored = self.store.get_canonical_block(chain_id, block)
            if (
                current is not None
                and stored is not None
                and current.hash.lower() == str(stored["block_hash"]).lower()
            ):
                return block, current.hash
            block -= 1

        # The reorg reaches below the configured start block. Roll back to the
        # synthetic block before the scan window and replay from start_block.
        return self.settings.start_block - 1, None

    def _check_reorg(
        self,
        *,
        chain_id: int,
        cursor: dict[str, Any],
        tip: int,
    ) -> dict[str, Any] | None:
        last_block = int(cursor["last_block"])
        if last_block < self.settings.start_block:
            return None

        last_hash = cursor.get("last_block_hash")
        if last_hash is None:
            current = self.rpc.get_block(last_block)
            if current is not None:
                self.store.set_cursor(chain_id, self.settings.contract_address, last_block, current.hash)
                return None
            needs_reorg = True
        else:
            needs_reorg = last_block > tip
            if not needs_reorg:
                current = self.rpc.get_block(last_block)
                needs_reorg = current is None or current.hash.lower() != str(last_hash).lower()

        if not needs_reorg:
            return None

        ancestor, ancestor_hash = self._find_common_ancestor(
            chain_id=chain_id, cursor=cursor, tip=tip
        )
        self.store.rollback_to(
            chain_id=chain_id,
            contract_address=self.settings.contract_address,
            ancestor_block=ancestor,
            ancestor_hash=ancestor_hash,
            previous_last_block=last_block,
            new_tip=tip,
        )
        return {
            "previous_last_block": last_block,
            "ancestor_block": ancestor,
            "new_tip": tip,
        }

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def sync_once(self) -> SyncResult:
        chain_id = self.verify_chain()
        self.store.set_meta(
            "finality_confirmations", str(self.settings.finality_confirmations)
        )
        address = self.settings.contract_address

        cursor = self._ensure_cursor(chain_id)
        tip = self.rpc.block_number()
        self.store.record_tip(tip)

        reorg = self._check_reorg(chain_id=chain_id, cursor=cursor, tip=tip)
        if reorg is not None:
            LOGGER.warning(
                "reorg detected: previous_last_block=%s ancestor=%s new_tip=%s",
                reorg["previous_last_block"],
                reorg["ancestor_block"],
                reorg["new_tip"],
            )
            updated = self.store.get_cursor(chain_id, address)
            assert updated is not None
            cursor = updated

        scanned_blocks = 0
        events_indexed = 0

        while int(cursor["last_block"]) < tip:
            from_block = max(
                int(cursor["last_block"]) + 1,
                self.settings.start_block,
            )
            if from_block > tip:
                break
            to_block = min(from_block + self.settings.batch_size - 1, tip)

            headers = self._fetch_headers(from_block, to_block)
            self._validate_headers(cursor, headers)

            logs = self.rpc.get_logs(
                address=address,
                from_block=from_block,
                to_block=to_block,
                topics=TOPIC_FILTER,
            )
            decoded = self._decode_logs(headers, logs, chain_id)
            last_header = headers[-1]
            assert last_header is not None

            self.store.apply_scan(
                chain_id=chain_id,
                contract_address=address,
                headers=headers,  # type: ignore[arg-type]
                events=decoded,
                last_block=last_header.number,
                last_block_hash=last_header.hash,
            )
            cursor = self.store.get_cursor(chain_id, address)
            assert cursor is not None

            scanned_blocks += len(headers)
            events_indexed += len(decoded)
            LOGGER.info(
                "indexed blocks %s-%s (%s events, %s logs)",
                from_block,
                to_block,
                len(decoded),
                len(logs),
            )

        self.store.delete_meta("last_error")
        return SyncResult(
            chain_id=chain_id,
            tip_block=tip,
            indexed_block=int(cursor["last_block"]),
            scanned_blocks=scanned_blocks,
            events_indexed=events_indexed,
            reorg=reorg is not None,
            ancestor_block=None if reorg is None else int(reorg["ancestor_block"]),
            previous_last_block=None
            if reorg is None
            else int(reorg["previous_last_block"]),
        )

    def _fetch_headers(
        self, from_block: int, to_block: int
    ) -> list[BlockHeader]:
        headers = self.rpc.get_blocks(list(range(from_block, to_block + 1)))
        if any(header is None for header in headers):
            missing = [
                from_block + index
                for index, header in enumerate(headers)
                if header is None
            ]
            raise ScanError(f"RPC returned no header for blocks {missing[:5]}")
        result = [header for header in headers if header is not None]
        for offset, header in enumerate(result):
            expected_number = from_block + offset
            if header.number != expected_number:
                raise ScanError(
                    f"header number mismatch: expected {expected_number}, got {header.number}"
                )
        return result

    def _validate_headers(
        self, cursor: dict[str, Any], headers: Sequence[BlockHeader]
    ) -> None:
        expected_parent = cursor.get("last_block_hash")
        for header in headers:
            if expected_parent is not None and header.parent_hash.lower() != str(
                expected_parent
            ).lower():
                raise ScanError(
                    "block range is not connected to the indexed chain "
                    f"at {header.number}; parent={header.parent_hash} "
                    f"expected={expected_parent}. Retry after reorg detection."
                )
            expected_parent = header.hash

    def _decode_logs(
        self,
        headers: Sequence[BlockHeader],
        logs: Sequence[dict[str, Any]],
        chain_id: int,
    ) -> list[DecodedEvent]:
        by_number = {header.number: header for header in headers}
        decoded: list[DecodedEvent] = []
        for log in logs:
            try:
                block_number = int(str(log["blockNumber"]), 16)
            except (KeyError, TypeError, ValueError) as exc:
                raise ScanError("log is missing a valid blockNumber") from exc
            header = by_number.get(block_number)
            if header is None:
                raise ScanError(
                    f"log for block {block_number} is outside the requested range"
                )
            event = decode_log(log, header, chain_id=chain_id)
            if event is not None:
                if event.contract_address != self.settings.contract_address.lower():
                    raise ScanError(
                        "RPC returned a log from an unexpected contract address "
                        f"{event.contract_address}"
                    )
                decoded.append(event)
        decoded.sort(key=lambda item: (item.block_number, item.log_index))
        return decoded

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    def sync_forever(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                result = self.sync_once()
                LOGGER.info(
                    "sync ok chain=%s tip=%s indexed=%s reorg=%s",
                    result.chain_id,
                    result.tip_block,
                    result.indexed_block,
                    result.reorg,
                )
            except ChainIdError as exc:
                self.store.set_meta("last_error", f"CHAIN_ID: {exc}")
                LOGGER.critical("fatal chain ID error: %s", exc)
                return
            except ReorgTooDeep as exc:
                self.store.set_meta("last_error", f"REORG_TOO_DEEP: {exc}")
                LOGGER.critical("fatal reorg error: %s", exc)
                return
            except Exception as exc:  # noqa: BLE001 - service loop boundary
                self.store.set_meta("last_error", f"{type(exc).__name__}: {exc}")
                LOGGER.exception("indexer poll failed")
            stop_event.wait(self.settings.poll_interval)
