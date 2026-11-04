"""Environment-backed configuration for the local-chain indexer.

Only local/testnet chains are accepted. The service intentionally rejects known
mainnet chain IDs even if they are supplied through the allow-list environment
variable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_RPC_URL = "http://127.0.0.1:8545"
DEFAULT_CHAIN_ID = 31337
DEFAULT_PORT = 8100
DEFAULT_VERIFIER_KIND = "mock"
VERIFIER_KINDS = frozenset({"mock", "groth16"})

# This service is a local vertical-slice tool, not a public indexer. These chain
# IDs are never accepted.
FORBIDDEN_MAINNET_CHAIN_IDS = frozenset(
    {
        1,  # Ethereum
        10,  # Optimism
        56,  # BNB Chain
        100,  # Gnosis
        137,  # Polygon
        250,  # Fantom
        324,  # zkSync Era
        1101,  # Polygon zkEVM
        8453,  # Base
        42161,  # Arbitrum One
        43114,  # Avalanche C-Chain
        59144,  # Linea
        534352,  # Scroll
    }
)

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class ConfigError(ValueError):
    """Raised when indexer configuration is unsafe or malformed."""


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        if default is None:
            raise ConfigError(f"{name} is required")
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def _parse_chain_ids(raw: str) -> frozenset[int]:
    chain_ids: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            chain_ids.add(int(item))
        except ValueError as exc:
            raise ConfigError(
                "INDEXER_ALLOWED_CHAIN_IDS must be a comma-separated list of integers"
            ) from exc
    if not chain_ids:
        raise ConfigError("INDEXER_ALLOWED_CHAIN_IDS must not be empty")
    forbidden = chain_ids & FORBIDDEN_MAINNET_CHAIN_IDS
    if forbidden:
        raise ConfigError(
            "Mainnet chain IDs are not allowed for this local indexer: "
            + ", ".join(str(item) for item in sorted(forbidden))
        )
    return frozenset(chain_ids)


def _validate_rpc_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError("ANVIL_RPC_URL must be an http(s) URL")
    return value


def _validate_address(value: str) -> str:
    if not _ADDRESS_RE.match(value):
        raise ConfigError("VEILPOOL_ADDRESS must be a 20-byte 0x-prefixed address")
    normalized = value.lower()
    if normalized == "0x" + "00" * 20:
        raise ConfigError("VEILPOOL_ADDRESS must not be the zero address")
    return normalized


@dataclass(frozen=True)
class Settings:
    """Runtime settings for one local chain and one VeilPool deployment."""

    rpc_url: str = DEFAULT_RPC_URL
    contract_address: str = ""
    database_path: Path = Path("indexer.db")
    start_block: int = 0
    batch_size: int = 500
    poll_interval: float = 2.0
    max_reorg_depth: int = 512
    finality_confirmations: int = 1
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    allowed_chain_ids: frozenset[int] = frozenset({DEFAULT_CHAIN_ID})
    rpc_timeout: float = 10.0
    rpc_retries: int = 2
    verifier_kind: str = DEFAULT_VERIFIER_KIND

    def validate(self) -> "Settings":
        if self.start_block < 0:
            raise ConfigError("INDEXER_START_BLOCK must be zero or positive")
        if not 1 <= self.batch_size <= 10_000:
            raise ConfigError("INDEXER_BATCH_SIZE must be between 1 and 10000")
        if self.poll_interval <= 0:
            raise ConfigError("INDEXER_POLL_SECONDS must be positive")
        if self.max_reorg_depth < 1:
            raise ConfigError("INDEXER_MAX_REORG_DEPTH must be positive")
        if self.finality_confirmations < 1:
            raise ConfigError("INDEXER_FINALITY_CONFIRMATIONS must be positive")
        if not 1 <= self.port <= 65535:
            raise ConfigError("INDEXER_PORT must be between 1 and 65535")
        if self.rpc_timeout <= 0:
            raise ConfigError("INDEXER_RPC_TIMEOUT must be positive")
        if self.rpc_retries < 0:
            raise ConfigError("INDEXER_RPC_RETRIES must be zero or positive")
        if not self.allowed_chain_ids:
            raise ConfigError("INDEXER_ALLOWED_CHAIN_IDS must not be empty")
        forbidden = self.allowed_chain_ids & FORBIDDEN_MAINNET_CHAIN_IDS
        if forbidden:
            raise ConfigError(
                "Mainnet chain IDs are not allowed for this local indexer: "
                + ", ".join(str(item) for item in sorted(forbidden))
            )
        verifier_kind = self.verifier_kind.strip().lower()
        if verifier_kind not in VERIFIER_KINDS:
            raise ConfigError(
                "INDEXER_VERIFIER_KIND must be one of: "
                + ", ".join(sorted(VERIFIER_KINDS))
            )
        return replace(
            self,
            rpc_url=_validate_rpc_url(self.rpc_url),
            contract_address=_validate_address(self.contract_address),
            database_path=Path(self.database_path),
            verifier_kind=verifier_kind,
        )

    @classmethod
    def from_env(cls, *, validate: bool = True) -> "Settings":
        settings = cls(
            rpc_url=_env("ANVIL_RPC_URL", DEFAULT_RPC_URL),
            contract_address=_env("VEILPOOL_ADDRESS", ""),
            database_path=Path(_env("INDEXER_DB", "indexer.db")),
            start_block=_env_int("INDEXER_START_BLOCK", 0),
            batch_size=_env_int("INDEXER_BATCH_SIZE", 500),
            poll_interval=_env_float("INDEXER_POLL_SECONDS", 2.0),
            max_reorg_depth=_env_int("INDEXER_MAX_REORG_DEPTH", 512),
            finality_confirmations=_env_int("INDEXER_FINALITY_CONFIRMATIONS", 1),
            host=_env("INDEXER_HOST", "127.0.0.1"),
            port=_env_int("INDEXER_PORT", DEFAULT_PORT),
            allowed_chain_ids=_parse_chain_ids(
                _env("INDEXER_ALLOWED_CHAIN_IDS", str(DEFAULT_CHAIN_ID))
            ),
            rpc_timeout=_env_float("INDEXER_RPC_TIMEOUT", 10.0),
            rpc_retries=_env_int("INDEXER_RPC_RETRIES", 2),
            verifier_kind=_env("INDEXER_VERIFIER_KIND", DEFAULT_VERIFIER_KIND),
        )
        return settings.validate() if validate else settings

    def with_overrides(self, **kwargs: object) -> "Settings":
        """Return a validated copy with explicit CLI overrides applied."""

        return replace(self, **kwargs).validate()
