from __future__ import annotations

import pytest

from veilpool_api.config import Settings

_RELEVANT_ENV = (
    "VEILPOOL_MODE",
    "VEILPOOL_CHAIN_ID",
    "VEILPOOL_CONTRACT_ADDRESS",
    "VEILPOOL_INDEXER_URL",
    "VEILPOOL_INDEXER_TIMEOUT_SECONDS",
    "VEILPOOL_LOCAL_RPC_URL",
    "VEILPOOL_LOCAL_FROM_ADDRESS",
    "VEILPOOL_LOCAL_AUTO_DEPOSIT",
    "VEILPOOL_LOCAL_DEPOSIT_TIMEOUT_SECONDS",
    "VEILPOOL_LOCAL_AUTO_WITHDRAW",
    "VEILPOOL_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS",
    "VEILPOOL_LOCAL_VERIFIER_KIND",
    "VEILPOOL_LOCAL_MATURITY_SECONDS",
    "VEILPOOL_REQUIRE_AUTH",
    "VEILPOOL_API_TOKEN",
    "VEILPOOL_DEV_BEARER_TOKEN",
    "VEILPOOL_BEARER_TOKEN",
    "VEILPOOL_AUTH_TOKEN",
    "VEILPOOL_RATE_LIMIT_ENABLED",
    "VEILPOOL_RATE_LIMIT_WINDOW_SECONDS",
    "VEILPOOL_RATE_LIMIT_DEPOSIT_INTENT",
    "VEILPOOL_RATE_LIMIT_WITHDRAWAL_QUOTE",
    "VEILPOOL_RATE_LIMIT_WITHDRAWAL_SUBMIT",
    "VEILPOOL_RATE_LIMIT_COMPLIANCE",
    "VEILPOOL_RATE_LIMIT_ADMIN",
    "VEILPOOL_RATE_LIMIT_LOCAL_DEPOSIT",
    "VEILPOOL_RATE_LIMIT_LOCAL_WITHDRAWAL",
    "VEILPOOL_RATE_LIMIT_POOL_PATH",
    "VEILPOOL_MAX_BODY_BYTES",
    "VEILPOOL_REVIEW_DECISION_TTL_SECONDS",
)


def test_security_env_defaults_keep_local_demo_open(monkeypatch):
    for name in _RELEVANT_ENV:
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()
    assert settings.require_auth is False
    assert settings.api_token == "dev-api-token"
    assert settings.rate_limit_enabled is True
    assert settings.max_body_bytes == 64 * 1024
    settings.validate()


def test_security_env_overrides(monkeypatch):
    for name in _RELEVANT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VEILPOOL_REQUIRE_AUTH", "true")
    monkeypatch.setenv("VEILPOOL_API_TOKEN", "env-api-token")
    monkeypatch.setenv("VEILPOOL_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("VEILPOOL_RATE_LIMIT_DEPOSIT_INTENT", "2")
    monkeypatch.setenv("VEILPOOL_RATE_LIMIT_WITHDRAWAL_SUBMIT", "3")
    monkeypatch.setenv("VEILPOOL_MAX_BODY_BYTES", "1024")
    monkeypatch.setenv("VEILPOOL_REVIEW_DECISION_TTL_SECONDS", "120")

    settings = Settings.from_env()
    assert settings.require_auth is True
    assert settings.api_token == "env-api-token"
    assert settings.rate_limit_enabled is False
    assert settings.rate_limit_deposit_intent == 2
    assert settings.rate_limit_withdrawal_submit == 3
    assert settings.max_body_bytes == 1024
    assert settings.review_decision_ttl_seconds == 120
    settings.validate()


_LOCAL_CONTRACT = "0x" + "ab" * 20


def _local_settings(**overrides):
    values = {
        "mode": "local",
        "chain_id": 31337,
        "contract_address": _LOCAL_CONTRACT,
        "indexer_url": "http://127.0.0.1:8100",
        "local_rpc_url": "http://127.0.0.1:8545",
    }
    values.update(overrides)
    return Settings(**values)


def test_local_config_requires_anvil_chain_and_loopback_urls():
    _local_settings().validate()
    _local_settings(indexer_url="http://localhost:8100").validate()
    _local_settings(local_rpc_url="http://[::1]:8545").validate()

    with pytest.raises(ValueError, match="31337"):
        _local_settings(chain_id=11155111).validate()
    with pytest.raises(ValueError, match="mainnet"):
        _local_settings(chain_id=1).validate()
    with pytest.raises(ValueError, match="loopback"):
        _local_settings(indexer_url="http://10.0.0.5:8100").validate()
    with pytest.raises(ValueError, match="loopback"):
        _local_settings(local_rpc_url="https://mainnet.example.com").validate()
    with pytest.raises(ValueError, match="credentials"):
        _local_settings(
            indexer_url="http://user:pass@127.0.0.1:8100"
        ).validate()


def test_local_config_requires_contract_address():
    with pytest.raises(ValueError, match="VEILPOOL_CONTRACT_ADDRESS"):
        _local_settings(contract_address="").validate()
    with pytest.raises(ValueError, match="20-byte"):
        _local_settings(contract_address="0x1234").validate()


def test_local_maturity_override_is_validated():
    _local_settings(local_maturity_seconds=0).validate()
    _local_settings(local_maturity_seconds=1800).validate()
    with pytest.raises(ValueError, match="LOCAL_MATURITY"):
        _local_settings(local_maturity_seconds=-1).validate()


def test_local_env_is_fail_closed(monkeypatch):
    for name in _RELEVANT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VEILPOOL_MODE", "local")
    monkeypatch.setenv("VEILPOOL_CHAIN_ID", "31337")

    with pytest.raises(ValueError, match="VEILPOOL_CONTRACT_ADDRESS"):
        Settings.from_env().validate()

    monkeypatch.setenv("VEILPOOL_CONTRACT_ADDRESS", _LOCAL_CONTRACT)
    monkeypatch.setenv("VEILPOOL_INDEXER_URL", "http://127.0.0.1:8100")
    monkeypatch.setenv("VEILPOOL_LOCAL_RPC_URL", "http://127.0.0.1:8545")
    monkeypatch.setenv("VEILPOOL_LOCAL_AUTO_DEPOSIT", "true")
    monkeypatch.setenv("VEILPOOL_LOCAL_DEPOSIT_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("VEILPOOL_LOCAL_AUTO_WITHDRAW", "true")
    monkeypatch.setenv("VEILPOOL_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS", "9.5")
    monkeypatch.setenv("VEILPOOL_LOCAL_VERIFIER_KIND", "groth16")
    monkeypatch.setenv("VEILPOOL_RATE_LIMIT_LOCAL_DEPOSIT", "3")
    monkeypatch.setenv("VEILPOOL_RATE_LIMIT_LOCAL_WITHDRAWAL", "4")
    monkeypatch.setenv("VEILPOOL_RATE_LIMIT_POOL_PATH", "12")
    settings = Settings.from_env()
    settings.validate()
    assert settings.mode == "local"
    assert settings.chain_id == 31337
    assert settings.local_auto_deposit is True
    assert settings.local_deposit_timeout_seconds == 2.5
    assert settings.local_auto_withdraw is True
    assert settings.local_withdrawal_timeout_seconds == 9.5
    assert settings.local_verifier_kind == "groth16"
    assert settings.rate_limit_local_deposit == 3
    assert settings.rate_limit_local_withdrawal == 4
    assert settings.rate_limit_pool_path == 12


def test_local_verifier_kind_rejects_unknown_values():
    _local_settings(local_verifier_kind="groth16").validate()
    _local_settings(local_verifier_kind="mock").validate()
    with pytest.raises(ValueError, match="VEILPOOL_LOCAL_VERIFIER_KIND"):
        _local_settings(local_verifier_kind="plonk").validate()
    with pytest.raises(ValueError, match="WITHDRAWAL_TIMEOUT"):
        _local_settings(local_withdrawal_timeout_seconds=-1).validate()


def test_mock_mode_still_rejects_unknown_modes(monkeypatch):
    for name in _RELEVANT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VEILPOOL_MODE", "mainnet")
    with pytest.raises(ValueError, match="mock"):
        Settings.from_env().validate()


def test_local_startup_fails_closed_on_bad_configuration():
    from veilpool_api.main import create_app

    with pytest.raises(ValueError):
        create_app(_local_settings(chain_id=11155111))
    with pytest.raises(ValueError):
        create_app(_local_settings(local_rpc_url="https://mainnet.example.com"))
    with pytest.raises(ValueError):
        create_app(_local_settings(contract_address=""))
