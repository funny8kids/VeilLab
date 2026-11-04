from __future__ import annotations

import pytest

from fake_chain import CONTRACT_ADDRESS
from veilpool_indexer.config import ConfigError, Settings
from veilpool_indexer.poolids import (
    bytes32_to_pool_key,
    parse_pool_selector,
    pool_id_to_bytes32,
)


def test_mainnet_chain_ids_are_rejected():
    with pytest.raises(ConfigError):
        Settings(
            contract_address=CONTRACT_ADDRESS,
            allowed_chain_ids=frozenset({1}),
        ).validate()

    with pytest.raises(ConfigError):
        Settings(
            contract_address="0x" + "00" * 20,
        ).validate()


def test_pool_id_label_round_trip():
    encoded = pool_id_to_bytes32("pool_eth_01")
    assert encoded == "0x" + b"pool_eth_01".hex().ljust(64, "0")
    assert bytes32_to_pool_key(encoded) == "pool_eth_01"

    resolved_hex, label = parse_pool_selector("pool_eth_01")
    assert resolved_hex == encoded
    assert label == "pool_eth_01"

    raw_hex, raw_label = parse_pool_selector(encoded)
    assert raw_hex == encoded
    assert raw_label == "pool_eth_01"


def test_verifier_kind_defaults_to_mock_and_is_validated():
    base = Settings(contract_address=CONTRACT_ADDRESS)
    assert base.verifier_kind == "mock"
    assert base.validate().verifier_kind == "mock"

    assert (
        Settings(
            contract_address=CONTRACT_ADDRESS, verifier_kind="GROTH16"
        ).validate().verifier_kind
        == "groth16"
    )
    with pytest.raises(ConfigError, match="INDEXER_VERIFIER_KIND"):
        Settings(
            contract_address=CONTRACT_ADDRESS, verifier_kind="bogus"
        ).validate()


def test_verifier_kind_from_env(monkeypatch):
    monkeypatch.setenv("VEILPOOL_ADDRESS", CONTRACT_ADDRESS)
    monkeypatch.setenv("INDEXER_VERIFIER_KIND", "groth16")
    assert Settings.from_env().verifier_kind == "groth16"

    monkeypatch.setenv("INDEXER_VERIFIER_KIND", "bogus")
    with pytest.raises(ConfigError, match="INDEXER_VERIFIER_KIND"):
        Settings.from_env()
