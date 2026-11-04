from __future__ import annotations

import sqlite3

import pytest

from chain_fixtures import (
    C1,
    C2,
    C3,
    C4,
    N1,
    POOL_ETH_01,
    R1,
    R2,
    R3,
    R4,
    RECIPIENT,
    block_one,
    chain_a,
    chain_b,
)
from fake_chain import FakeRpc, build_chain
from veilpool_indexer.indexer import ChainIdError, ReorgTooDeep
from veilpool_indexer.store import Store


def _events(store: Store, settings, event_type: str, pool_id: str = POOL_ETH_01):
    return store.list_events(
        chain_id=int(store.get_meta("chain_id")),
        contract_address=settings.contract_address,
        pool_id=pool_id,
        event_type=event_type,
    )


def test_indexes_events_and_is_idempotent(settings, store, make_indexer):
    indexer = make_indexer(FakeRpc(chain_a()))

    result = indexer.sync_once()
    assert result.chain_id == 31337
    assert result.tip_block == 3
    assert result.indexed_block == 3
    assert result.scanned_blocks == 3
    assert result.events_indexed == 8
    assert result.reorg is False

    deposits = _events(store, settings, "Deposit")
    assert [item["commitment"] for item in deposits] == [C1, C2]
    assert [item["leaf_index"] for item in deposits] == [0, 1]
    assert all(item["canonical"] is True for item in deposits)

    roots = _events(store, settings, "RootUpdated")
    assert [item["root"] for item in roots] == [R1, R2]

    pauses = _events(store, settings, "PoolPaused")
    assert len(pauses) == 1
    assert pauses[0]["reason"] == "maintenance"

    withdrawal = store.get_withdrawal(
        chain_id=int(store.get_meta("chain_id")),
        contract_address=settings.contract_address,
        nullifier=N1,
    )
    assert withdrawal is not None
    assert withdrawal["recipient"] == RECIPIENT
    assert withdrawal["fee_wei"] == "1000"

    # A second poll must not duplicate rows.
    second = indexer.sync_once()
    assert second.scanned_blocks == 0
    assert second.events_indexed == 0
    assert len(_events(store, settings, "Deposit")) == 2


def test_reorg_rolls_back_to_common_ancestor_and_replays(
    settings, store, make_indexer, tmp_path
):
    settings = settings.with_overrides(database_path=tmp_path / "reorg.db")
    store = Store(settings.database_path)
    store.initialize()
    fake = FakeRpc(chain_a())
    indexer = make_indexer(fake)
    indexer.settings = settings
    indexer.store = store
    first = indexer.sync_once()
    assert first.indexed_block == 3

    fake.set_chain(chain_b())
    result = indexer.sync_once()
    assert result.reorg is True
    assert result.ancestor_block == 1
    assert result.previous_last_block == 3
    assert result.scanned_blocks == 2
    assert result.indexed_block == 3

    deposits = _events(store, settings, "Deposit")
    assert [item["commitment"] for item in deposits] == [C1, C3, C4]

    roots = _events(store, settings, "RootUpdated")
    assert [item["root"] for item in roots] == [R1, R3, R4]

    old_withdrawal = store.get_withdrawal(
        chain_id=int(store.get_meta("chain_id")),
        contract_address=settings.contract_address,
        nullifier=N1,
    )
    assert old_withdrawal is None

    pauses = _events(store, settings, "PoolPaused")
    assert [item["reason"] for item in pauses] == ["reorg pause"]
    assert store.reorg_count() == 1

    with sqlite3.connect(settings.database_path) as connection:
        reorged = connection.execute(
            "SELECT COUNT(*) FROM events WHERE canonical = 0"
        ).fetchone()[0]
    assert reorged >= 3


def test_deep_reorg_fails_closed(settings, store, make_indexer):
    settings = settings.with_overrides(max_reorg_depth=1, database_path=store.path)
    store = Store(settings.database_path)
    store.initialize()
    fake = FakeRpc(chain_a())
    indexer = make_indexer(fake)
    indexer.settings = settings
    indexer.store = store
    indexer.sync_once()

    fake.set_chain(build_chain([block_one()]))
    with pytest.raises(ReorgTooDeep):
        indexer.sync_once()


def test_wrong_chain_id_is_rejected(settings, store, make_indexer):
    chain = build_chain([block_one()], chain_id=1)
    indexer = make_indexer(FakeRpc(chain))
    with pytest.raises(ChainIdError):
        indexer.sync_once()
    assert store.get_meta("chain_id") is None
    assert store.event_counts(1, settings.contract_address) == {}
