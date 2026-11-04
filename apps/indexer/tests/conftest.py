from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
for candidate in (ROOT, TESTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from fake_chain import CONTRACT_ADDRESS  # noqa: E402
from veilpool_indexer.config import Settings  # noqa: E402
from veilpool_indexer.indexer import Indexer  # noqa: E402
from veilpool_indexer.rpc import RpcClient  # noqa: E402
from veilpool_indexer.store import Store  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        rpc_url="http://fake-anvil.invalid:8545",
        contract_address=CONTRACT_ADDRESS,
        database_path=tmp_path / "indexer.db",
        start_block=1,
        batch_size=2,
        poll_interval=0.01,
        max_reorg_depth=10,
        finality_confirmations=1,
        rpc_retries=0,
    ).validate()


@pytest.fixture
def store(settings: Settings) -> Store:
    value = Store(settings.database_path)
    value.initialize()
    return value


@pytest.fixture
def rpc_factory(settings: Settings):
    clients: list[tuple[RpcClient, httpx.Client]] = []

    def make(fake) -> RpcClient:
        http_client = httpx.Client(transport=fake.transport(), timeout=5.0)
        rpc = RpcClient(
            settings.rpc_url,
            client=http_client,
            retries=0,
        )
        clients.append((rpc, http_client))
        return rpc

    yield make
    for rpc, http_client in clients:
        rpc.close()
        http_client.close()


@pytest.fixture
def make_indexer(settings: Settings, store: Store, rpc_factory):
    def build(fake) -> Indexer:
        return Indexer(settings, rpc_factory(fake), store)

    return build
