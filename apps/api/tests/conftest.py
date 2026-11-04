from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = Path(__file__).resolve().parent
for path in (str(API_ROOT), str(TESTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from veilpool_api.config import Settings
from veilpool_api.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "veilpool-test.db"
    return Settings(
        mode="mock",
        database_url=f"sqlite:///{database_path.as_posix()}",
        admin_token="dev-admin",
        chain_id=11155111,
        intent_ttl_seconds=600,
        quote_ttl_seconds=300,
        compliance_ttl_seconds=300,
        root_window_size=20,
        compliance_hash_salt="test-salt",
        mock_start_block=6_000_000,
        mock_maturity_seconds=0,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
