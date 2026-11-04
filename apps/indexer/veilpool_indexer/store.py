"""SQLite persistence for normalized chain events.

The same database can be read by the HTTP API while the poller writes. SQLite
WAL mode and a single writer keep the local demo simple; this is not a
production indexer database.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from .events import DecodedEvent
from .rpc import BlockHeader

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cursors (
    chain_id INTEGER NOT NULL,
    contract_address TEXT NOT NULL,
    last_block INTEGER NOT NULL,
    last_block_hash TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chain_id, contract_address)
);

CREATE TABLE IF NOT EXISTS blocks (
    chain_id INTEGER NOT NULL,
    block_number INTEGER NOT NULL,
    block_hash TEXT NOT NULL,
    parent_hash TEXT NOT NULL,
    block_timestamp INTEGER NOT NULL,
    canonical INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chain_id, block_number, block_hash)
);
CREATE INDEX IF NOT EXISTS ix_blocks_canonical
    ON blocks (chain_id, block_number, canonical);

CREATE TABLE IF NOT EXISTS events (
    chain_id INTEGER NOT NULL,
    contract_address TEXT NOT NULL,
    event_type TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    block_hash TEXT NOT NULL,
    block_timestamp INTEGER NOT NULL,
    log_index INTEGER NOT NULL,
    tx_hash TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    pool_key TEXT,
    commitment TEXT,
    nullifier TEXT,
    root TEXT,
    leaf_index INTEGER,
    recipient TEXT,
    fee_wei TEXT,
    reason TEXT,
    denomination_wei TEXT,
    root_window INTEGER,
    maturity_seconds INTEGER,
    canonical INTEGER NOT NULL DEFAULT 1,
    removed INTEGER NOT NULL DEFAULT 0,
    indexed_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_event
    ON events (chain_id, tx_hash, log_index);
CREATE INDEX IF NOT EXISTS ix_events_pool_block
    ON events (chain_id, contract_address, pool_id, canonical, block_number, log_index);
CREATE INDEX IF NOT EXISTS ix_events_nullifier
    ON events (chain_id, contract_address, nullifier, canonical);
CREATE INDEX IF NOT EXISTS ix_events_type
    ON events (chain_id, contract_address, event_type, canonical);

CREATE TABLE IF NOT EXISTS reorgs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id INTEGER NOT NULL,
    contract_address TEXT NOT NULL,
    previous_last_block INTEGER NOT NULL,
    ancestor_block INTEGER NOT NULL,
    new_tip INTEGER NOT NULL,
    detected_at TEXT NOT NULL
);
"""

_EVENT_COLUMNS = (
    "chain_id",
    "contract_address",
    "event_type",
    "block_number",
    "block_hash",
    "block_timestamp",
    "log_index",
    "tx_hash",
    "pool_id",
    "pool_key",
    "commitment",
    "nullifier",
    "root",
    "leaf_index",
    "recipient",
    "fee_wei",
    "reason",
    "denomination_wei",
    "root_window",
    "maturity_seconds",
    "canonical",
    "removed",
    "indexed_at",
)

_EVENT_UPDATE_COLUMNS = tuple(
    column
    for column in _EVENT_COLUMNS
    if column not in {"chain_id", "tx_hash", "log_index"}
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _writer(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._reader() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.commit()

    # ------------------------------------------------------------------
    # Meta and cursors
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        with self._reader() as connection:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        with self._writer() as connection:
            connection.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def delete_meta(self, key: str) -> None:
        with self._writer() as connection:
            connection.execute("DELETE FROM meta WHERE key = ?", (key,))

    def get_cursor(self, chain_id: int, contract_address: str) -> dict[str, Any] | None:
        with self._reader() as connection:
            row = connection.execute(
                "SELECT * FROM cursors WHERE chain_id = ? AND contract_address = ?",
                (chain_id, contract_address.lower()),
            ).fetchone()
        return None if row is None else dict(row)

    def set_cursor(
        self,
        chain_id: int,
        contract_address: str,
        last_block: int,
        last_block_hash: str | None,
    ) -> None:
        with self._writer() as connection:
            self._set_cursor(
                connection,
                chain_id,
                contract_address,
                last_block,
                last_block_hash,
            )

    @staticmethod
    def _set_cursor(
        connection: sqlite3.Connection,
        chain_id: int,
        contract_address: str,
        last_block: int,
        last_block_hash: str | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO cursors
                (chain_id, contract_address, last_block, last_block_hash, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chain_id, contract_address) DO UPDATE SET
                last_block = excluded.last_block,
                last_block_hash = excluded.last_block_hash,
                updated_at = excluded.updated_at
            """,
            (
                chain_id,
                contract_address.lower(),
                last_block,
                last_block_hash,
                utcnow(),
            ),
        )

    def get_canonical_block(
        self, chain_id: int, block_number: int
    ) -> dict[str, Any] | None:
        with self._reader() as connection:
            row = connection.execute(
                "SELECT * FROM blocks WHERE chain_id = ? AND block_number = ? "
                "AND canonical = 1 ORDER BY updated_at DESC LIMIT 1",
                (chain_id, block_number),
            ).fetchone()
        return None if row is None else dict(row)

    # ------------------------------------------------------------------
    # Scan write path
    # ------------------------------------------------------------------

    def apply_scan(
        self,
        *,
        chain_id: int,
        contract_address: str,
        headers: Sequence[BlockHeader],
        events: Sequence[DecodedEvent],
        last_block: int,
        last_block_hash: str,
    ) -> None:
        """Atomically store headers, events and the new cursor."""

        now = utcnow()
        address = contract_address.lower()
        with self._writer() as connection:
            for header in headers:
                connection.execute(
                    "UPDATE blocks SET canonical = 0, updated_at = ? "
                    "WHERE chain_id = ? AND block_number = ? AND block_hash <> ? "
                    "AND canonical = 1",
                    (now, chain_id, header.number, header.hash),
                )
                # Defensive: if this block number changed, old events at the
                # same height must not remain canonical even if a caller has
                # not yet run the explicit reorg rollback.
                connection.execute(
                    "UPDATE events SET canonical = 0 "
                    "WHERE chain_id = ? AND contract_address = ? "
                    "AND block_number = ? AND block_hash <> ? AND canonical = 1",
                    (chain_id, address, header.number, header.hash),
                )
                connection.execute(
                    """
                    INSERT INTO blocks
                        (chain_id, block_number, block_hash, parent_hash,
                         block_timestamp, canonical, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(chain_id, block_number, block_hash) DO UPDATE SET
                        parent_hash = excluded.parent_hash,
                        block_timestamp = excluded.block_timestamp,
                        canonical = 1,
                        updated_at = excluded.updated_at
                    """,
                    (
                        chain_id,
                        header.number,
                        header.hash,
                        header.parent_hash,
                        header.timestamp,
                        now,
                    ),
                )

            for event in events:
                row = event.as_db_row(now)
                columns = ", ".join(_EVENT_COLUMNS)
                placeholders = ", ".join("?" for _ in _EVENT_COLUMNS)
                updates = ", ".join(
                    f"{column} = excluded.{column}" for column in _EVENT_UPDATE_COLUMNS
                )
                connection.execute(
                    f"INSERT INTO events ({columns}) VALUES ({placeholders}) "
                    f"ON CONFLICT(chain_id, tx_hash, log_index) DO UPDATE SET {updates}",
                    tuple(row[column] for column in _EVENT_COLUMNS),
                )

            self._set_cursor(
                connection,
                chain_id,
                address,
                last_block,
                last_block_hash,
            )

    def rollback_to(
        self,
        *,
        chain_id: int,
        contract_address: str,
        ancestor_block: int,
        ancestor_hash: str | None,
        previous_last_block: int,
        new_tip: int,
    ) -> None:
        """Roll back canonical rows above the common ancestor and audit it."""

        address = contract_address.lower()
        now = utcnow()
        with self._writer() as connection:
            connection.execute(
                "UPDATE events SET canonical = 0 "
                "WHERE chain_id = ? AND contract_address = ? "
                "AND block_number > ? AND canonical = 1",
                (chain_id, address, ancestor_block),
            )
            connection.execute(
                "UPDATE blocks SET canonical = 0, updated_at = ? "
                "WHERE chain_id = ? AND block_number > ? AND canonical = 1",
                (now, chain_id, ancestor_block),
            )
            self._set_cursor(
                connection,
                chain_id,
                address,
                ancestor_block,
                ancestor_hash,
            )
            connection.execute(
                """
                INSERT INTO reorgs
                    (chain_id, contract_address, previous_last_block,
                     ancestor_block, new_tip, detected_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chain_id,
                    address,
                    previous_last_block,
                    ancestor_block,
                    new_tip,
                    now,
                ),
            )

    def record_tip(self, tip_block: int) -> None:
        self.set_meta("tip_block", str(tip_block))
        self.set_meta("last_synced_at", utcnow())

    # ------------------------------------------------------------------
    # API read path
    # ------------------------------------------------------------------

    def event_counts(self, chain_id: int, contract_address: str) -> dict[str, int]:
        with self._reader() as connection:
            rows = connection.execute(
                "SELECT event_type, COUNT(*) AS count FROM events "
                "WHERE chain_id = ? AND contract_address = ? AND canonical = 1 "
                "GROUP BY event_type",
                (chain_id, contract_address.lower()),
            ).fetchall()
        return {str(row["event_type"]): int(row["count"]) for row in rows}

    def reorg_count(self) -> int:
        with self._reader() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM reorgs").fetchone()
        return 0 if row is None else int(row["count"])

    def known_pool(
        self,
        chain_id: int,
        contract_address: str,
        pool_id: str,
        pool_key: str | None,
    ) -> bool:
        sql = (
            "SELECT 1 FROM events WHERE chain_id = ? AND contract_address = ? "
            "AND canonical = 1 AND pool_id = ?"
        )
        params: list[Any] = [chain_id, contract_address.lower(), pool_id]
        if pool_key is not None:
            sql += " UNION SELECT 1 FROM events WHERE chain_id = ? "
            sql += "AND contract_address = ? AND canonical = 1 AND pool_key = ?"
            params.extend([chain_id, contract_address.lower(), pool_key])
        sql += " LIMIT 1"
        with self._reader() as connection:
            row = connection.execute(sql, params).fetchone()
        return row is not None

    def list_events(
        self,
        *,
        chain_id: int,
        contract_address: str,
        pool_id: str,
        event_type: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        tip_block, threshold = self._tip_and_threshold()
        with self._reader() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE chain_id = ? AND contract_address = ? "
                "AND pool_id = ? AND event_type = ? AND canonical = 1 "
                "ORDER BY block_number ASC, log_index ASC LIMIT ?",
                (chain_id, contract_address.lower(), pool_id, event_type, limit),
            ).fetchall()
        return [
            self._event_view(row, tip_block=tip_block, threshold=threshold)
            for row in rows
        ]

    def list_pool_deposits(
        self,
        *,
        chain_id: int,
        contract_address: str,
        pool_id: str,
    ) -> list[dict[str, Any]]:
        """Return all canonical deposits in on-chain leaf-index order.

        The Merkle path endpoint rebuilds the tree from this list on demand.
        There is no arbitrary row cap: a truncated deposit list would silently
        produce the wrong root.
        """

        with self._reader() as connection:
            rows = connection.execute(
                "SELECT commitment, leaf_index, block_number, block_hash, "
                "log_index, tx_hash FROM events "
                "WHERE chain_id = ? AND contract_address = ? AND pool_id = ? "
                "AND event_type = 'Deposit' AND canonical = 1 "
                "ORDER BY leaf_index IS NULL, leaf_index ASC, "
                "block_number ASC, log_index ASC",
                (chain_id, contract_address.lower(), pool_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_event(
        self,
        *,
        chain_id: int,
        contract_address: str,
        pool_id: str,
        event_type: str,
    ) -> dict[str, Any] | None:
        """Return the newest canonical event row of one type, if any."""

        with self._reader() as connection:
            row = connection.execute(
                "SELECT * FROM events WHERE chain_id = ? AND contract_address = ? "
                "AND pool_id = ? AND event_type = ? AND canonical = 1 "
                "ORDER BY block_number DESC, log_index DESC LIMIT 1",
                (chain_id, contract_address.lower(), pool_id, event_type),
            ).fetchone()
        return None if row is None else dict(row)

    def get_withdrawal(
        self,
        *,
        chain_id: int,
        contract_address: str,
        nullifier: str,
        pool_id: str | None = None,
    ) -> dict[str, Any] | None:
        tip_block, threshold = self._tip_and_threshold()
        sql = (
            "SELECT * FROM events WHERE chain_id = ? AND contract_address = ? "
            "AND nullifier = ? AND event_type = 'Withdrawal' AND canonical = 1"
        )
        params: list[Any] = [chain_id, contract_address.lower(), nullifier]
        if pool_id is not None:
            sql += " AND pool_id = ?"
            params.append(pool_id.lower())
        sql += " ORDER BY block_number DESC, log_index DESC LIMIT 1"
        with self._reader() as connection:
            row = connection.execute(sql, params).fetchone()
        return (
            None
            if row is None
            else self._event_view(row, tip_block=tip_block, threshold=threshold)
        )

    def _tip_and_threshold(self) -> tuple[int | None, int]:
        tip = self.get_meta("tip_block")
        threshold = self.get_meta("finality_confirmations")
        return (
            None if tip is None else int(tip),
            1 if threshold is None else int(threshold),
        )

    def list_pools(self, chain_id: int, contract_address: str) -> list[dict[str, Any]]:
        address = contract_address.lower()
        with self._reader() as connection:
            rows = connection.execute(
                """
                SELECT pool_id,
                       MAX(pool_key) AS pool_key,
                       SUM(CASE WHEN event_type = 'Deposit' AND canonical = 1
                                THEN 1 ELSE 0 END) AS deposits,
                       SUM(CASE WHEN event_type = 'Withdrawal' AND canonical = 1
                                THEN 1 ELSE 0 END) AS withdrawals,
                       SUM(CASE WHEN event_type = 'RootUpdated' AND canonical = 1
                                THEN 1 ELSE 0 END) AS roots
                FROM events
                WHERE chain_id = ? AND contract_address = ? AND canonical = 1
                GROUP BY pool_id
                ORDER BY pool_id
                """,
                (chain_id, address),
            ).fetchall()

            result: list[dict[str, Any]] = []
            for row in rows:
                current = connection.execute(
                    "SELECT root, block_number, block_timestamp FROM events "
                    "WHERE chain_id = ? AND contract_address = ? AND pool_id = ? "
                    "AND event_type = 'RootUpdated' AND canonical = 1 "
                    "ORDER BY block_number DESC, log_index DESC LIMIT 1",
                    (chain_id, address, row["pool_id"]),
                ).fetchone()
                created = connection.execute(
                    "SELECT denomination_wei, root_window, maturity_seconds, "
                    "block_number FROM events "
                    "WHERE chain_id = ? AND contract_address = ? AND pool_id = ? "
                    "AND event_type = 'PoolCreated' AND canonical = 1 "
                    "ORDER BY block_number DESC, log_index DESC LIMIT 1",
                    (chain_id, address, row["pool_id"]),
                ).fetchone()
                last_pause = connection.execute(
                    "SELECT block_number, log_index FROM events "
                    "WHERE chain_id = ? AND contract_address = ? AND pool_id = ? "
                    "AND event_type = 'PoolPaused' AND canonical = 1 "
                    "ORDER BY block_number DESC, log_index DESC LIMIT 1",
                    (chain_id, address, row["pool_id"]),
                ).fetchone()
                last_resume = connection.execute(
                    "SELECT block_number, log_index FROM events "
                    "WHERE chain_id = ? AND contract_address = ? AND pool_id = ? "
                    "AND event_type = 'PoolResumed' AND canonical = 1 "
                    "ORDER BY block_number DESC, log_index DESC LIMIT 1",
                    (chain_id, address, row["pool_id"]),
                ).fetchone()
                paused = False
                if last_pause is not None:
                    paused = last_resume is None or (
                        (int(last_pause["block_number"]), int(last_pause["log_index"]))
                        > (int(last_resume["block_number"]), int(last_resume["log_index"]))
                    )
                result.append(
                    {
                        "pool_id": row["pool_id"],
                        "pool_key": row["pool_key"],
                        "denomination_wei": None
                        if created is None
                        else created["denomination_wei"],
                        "root_window": None
                        if created is None
                        else int(created["root_window"]),
                        "maturity_seconds": None
                        if created is None
                        else int(created["maturity_seconds"]),
                        "created_block": None
                        if created is None
                        else int(created["block_number"]),
                        "deposits": int(row["deposits"] or 0),
                        "withdrawals": int(row["withdrawals"] or 0),
                        "roots": int(row["roots"] or 0),
                        "current_root": None if current is None else current["root"],
                        "current_root_block": None
                        if current is None
                        else int(current["block_number"]),
                        "paused": paused,
                    }
                )
        return result

    def _event_view(
        self,
        row: sqlite3.Row,
        *,
        tip_block: int | None,
        threshold: int,
    ) -> dict[str, Any]:
        confirmations = (
            None
            if tip_block is None
            else max(0, tip_block - int(row["block_number"]) + 1)
        )
        finality = "unknown"
        if confirmations is not None:
            finality = "final" if confirmations >= threshold else "optimistic"
        return {
            "chain_id": int(row["chain_id"]),
            "contract_address": row["contract_address"],
            "event_type": row["event_type"],
            "pool_id": row["pool_id"],
            "pool_key": row["pool_key"],
            "block_number": int(row["block_number"]),
            "block_hash": row["block_hash"],
            "block_timestamp": int(row["block_timestamp"]),
            "log_index": int(row["log_index"]),
            "tx_hash": row["tx_hash"],
            "commitment": row["commitment"],
            "nullifier": row["nullifier"],
            "root": row["root"],
            "leaf_index": None if row["leaf_index"] is None else int(row["leaf_index"]),
            "recipient": row["recipient"],
            "fee_wei": row["fee_wei"],
            "reason": row["reason"],
            "denomination_wei": row["denomination_wei"],
            "root_window": None
            if row["root_window"] is None
            else int(row["root_window"]),
            "maturity_seconds": None
            if row["maturity_seconds"] is None
            else int(row["maturity_seconds"]),
            "canonical": bool(row["canonical"]),
            "confirmations": confirmations,
            "finality": finality,
            "indexed_at": row["indexed_at"],
        }
