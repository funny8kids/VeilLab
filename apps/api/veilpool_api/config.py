from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_CHAIN_ID = 11155111  # Sepolia
LOCAL_CHAIN_ID = 31337
ALLOWED_TESTNET_CHAIN_IDS = {11155111, LOCAL_CHAIN_ID}
# Local mode is an Anvil-only vertical slice. Mainnet must be impossible, not
# merely discouraged; these IDs are rejected in every mode.
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
DEFAULT_MAX_BODY_BYTES = 64 * 1024
DEFAULT_INDEXER_URL = "http://127.0.0.1:8100"
DEFAULT_INDEXER_TIMEOUT_SECONDS = 3.0
DEFAULT_LOCAL_RPC_URL = "http://127.0.0.1:8545"
DEFAULT_LOCAL_FROM_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
DEFAULT_LOCAL_DEPOSIT_TIMEOUT_SECONDS = 15.0
DEFAULT_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS = 20.0
LOCAL_VERIFIER_KINDS = frozenset({"mock", "groth16"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - configuration error path
        raise ValueError(f"{name} must be an integer") from exc


def _env_optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - configuration error path
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - configuration error path
        raise ValueError(f"{name} must be a number") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false)")  # pragma: no cover


def _validate_loopback_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{name} must not contain credentials")
    host = parsed.hostname.lower()
    if host not in _LOOPBACK_HOSTS:
        raise ValueError(
            f"{name} must point at a loopback host "
            "(127.0.0.1, localhost or ::1). Local Anvil mode never uses a "
            "remote or mainnet RPC."
        )


def _validate_eth_address(name: str, value: str) -> None:
    if not _ADDRESS_RE.match(value or ""):
        raise ValueError(f"{name} must be a 0x-prefixed 20-byte address")


@dataclass(frozen=True)
class Settings:
    mode: str = "mock"
    database_url: str = "sqlite:///./veilpool.db"
    admin_token: str = "dev-admin"
    chain_id: int = DEFAULT_CHAIN_ID

    intent_ttl_seconds: int = 600
    quote_ttl_seconds: int = 300
    compliance_ttl_seconds: int = 300
    root_window_size: int = 20

    compliance_hash_salt: str = "veilpool-dev-salt"
    mock_start_block: int = 6_000_000
    mock_maturity_seconds: int | None = None
    # Local spike only: override the seeded ETH pool maturity to match the
    # deployed contract (e.g. 0 for the Poseidon proof pool). Never a product default.
    local_maturity_seconds: int | None = None

    # Local Anvil mode. These values are ignored in mock mode, except that the
    # loopback rules are still enforced whenever local mode is selected.
    contract_address: str = ""
    indexer_url: str = DEFAULT_INDEXER_URL
    indexer_timeout_seconds: float = DEFAULT_INDEXER_TIMEOUT_SECONDS
    local_rpc_url: str = DEFAULT_LOCAL_RPC_URL
    local_from_address: str = DEFAULT_LOCAL_FROM_ADDRESS
    local_auto_deposit: bool = False
    local_deposit_timeout_seconds: float = DEFAULT_LOCAL_DEPOSIT_TIMEOUT_SECONDS
    # Dev-only Anvil withdrawal bridge. Off by default for safety: without it
    # the API returns explicit calldata for the caller's own wallet.
    local_auto_withdraw: bool = False
    local_withdrawal_timeout_seconds: float = (
        DEFAULT_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS
    )
    # "mock" keeps the existing MockVerifier labels. "groth16" is for a local
    # VeilPoolPoseidon + Groth16VerifierAdapter deployment and must never claim
    # production ZK verification (the development zkey is unaudited).
    local_verifier_kind: str = "mock"

    # Local-demo auth: off by default so the web demo keeps working unchanged.
    # When enabled, every non-public endpoint requires the dev bearer token.
    require_auth: bool = False
    api_token: str = "dev-api-token"

    # In-memory token buckets. Set a limit to 0 to disable that scope.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_deposit_intent: int = 10
    rate_limit_withdrawal_quote: int = 10
    rate_limit_withdrawal_submit: int = 5
    rate_limit_compliance: int = 30
    rate_limit_admin: int = 60
    rate_limit_local_deposit: int = 5
    rate_limit_local_withdrawal: int = 5
    rate_limit_pool_path: int = 30

    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    review_decision_ttl_seconds: int = 24 * 60 * 60

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mode=os.getenv("VEILPOOL_MODE", "mock").strip().lower() or "mock",
            database_url=os.getenv("DATABASE_URL", "sqlite:///./veilpool.db"),
            admin_token=os.getenv("VEILPOOL_ADMIN_TOKEN", "dev-admin"),
            chain_id=_env_int("VEILPOOL_CHAIN_ID", DEFAULT_CHAIN_ID),
            intent_ttl_seconds=_env_int("VEILPOOL_INTENT_TTL_SECONDS", 600),
            quote_ttl_seconds=_env_int("VEILPOOL_QUOTE_TTL_SECONDS", 300),
            compliance_ttl_seconds=_env_int(
                "VEILPOOL_COMPLIANCE_TTL_SECONDS", 300
            ),
            root_window_size=_env_int("VEILPOOL_ROOT_WINDOW_SIZE", 20),
            compliance_hash_salt=os.getenv(
                "VEILPOOL_COMPLIANCE_HASH_SALT", "veilpool-dev-salt"
            ),
            mock_start_block=_env_int("VEILPOOL_MOCK_START_BLOCK", 6_000_000),
            mock_maturity_seconds=_env_optional_int(
                "VEILPOOL_MOCK_MATURITY_SECONDS"
            ),
            local_maturity_seconds=_env_optional_int(
                "VEILPOOL_LOCAL_MATURITY_SECONDS"
            ),
            contract_address=os.getenv("VEILPOOL_CONTRACT_ADDRESS", "").strip(),
            indexer_url=os.getenv(
                "VEILPOOL_INDEXER_URL", DEFAULT_INDEXER_URL
            ).strip(),
            indexer_timeout_seconds=_env_float(
                "VEILPOOL_INDEXER_TIMEOUT_SECONDS",
                DEFAULT_INDEXER_TIMEOUT_SECONDS,
            ),
            local_rpc_url=os.getenv(
                "VEILPOOL_LOCAL_RPC_URL", DEFAULT_LOCAL_RPC_URL
            ).strip(),
            local_from_address=os.getenv(
                "VEILPOOL_LOCAL_FROM_ADDRESS", DEFAULT_LOCAL_FROM_ADDRESS
            ).strip(),
            local_auto_deposit=_env_bool("VEILPOOL_LOCAL_AUTO_DEPOSIT", False),
            local_deposit_timeout_seconds=_env_float(
                "VEILPOOL_LOCAL_DEPOSIT_TIMEOUT_SECONDS",
                DEFAULT_LOCAL_DEPOSIT_TIMEOUT_SECONDS,
            ),
            local_auto_withdraw=_env_bool(
                "VEILPOOL_LOCAL_AUTO_WITHDRAW", False
            ),
            local_withdrawal_timeout_seconds=_env_float(
                "VEILPOOL_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS",
                DEFAULT_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS,
            ),
            local_verifier_kind=(
                os.getenv("VEILPOOL_LOCAL_VERIFIER_KIND", "mock").strip().lower()
                or "mock"
            ),
            require_auth=_env_bool("VEILPOOL_REQUIRE_AUTH", False),
            # VEILPOOL_API_TOKEN is the documented name. The other names are
            # accepted as compatibility aliases for local tooling.
            api_token=(
                os.getenv("VEILPOOL_API_TOKEN")
                or os.getenv("VEILPOOL_DEV_BEARER_TOKEN")
                or os.getenv("VEILPOOL_BEARER_TOKEN")
                or os.getenv("VEILPOOL_AUTH_TOKEN")
                or "dev-api-token"
            ),
            rate_limit_enabled=_env_bool("VEILPOOL_RATE_LIMIT_ENABLED", True),
            rate_limit_window_seconds=_env_int(
                "VEILPOOL_RATE_LIMIT_WINDOW_SECONDS", 60
            ),
            rate_limit_deposit_intent=_env_int(
                "VEILPOOL_RATE_LIMIT_DEPOSIT_INTENT", 10
            ),
            rate_limit_withdrawal_quote=_env_int(
                "VEILPOOL_RATE_LIMIT_WITHDRAWAL_QUOTE", 10
            ),
            rate_limit_withdrawal_submit=_env_int(
                "VEILPOOL_RATE_LIMIT_WITHDRAWAL_SUBMIT", 5
            ),
            rate_limit_compliance=_env_int(
                "VEILPOOL_RATE_LIMIT_COMPLIANCE", 30
            ),
            rate_limit_admin=_env_int("VEILPOOL_RATE_LIMIT_ADMIN", 60),
            rate_limit_local_deposit=_env_int(
                "VEILPOOL_RATE_LIMIT_LOCAL_DEPOSIT", 5
            ),
            rate_limit_local_withdrawal=_env_int(
                "VEILPOOL_RATE_LIMIT_LOCAL_WITHDRAWAL", 5
            ),
            rate_limit_pool_path=_env_int(
                "VEILPOOL_RATE_LIMIT_POOL_PATH", 30
            ),
            max_body_bytes=_env_int(
                "VEILPOOL_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES
            ),
            review_decision_ttl_seconds=_env_int(
                "VEILPOOL_REVIEW_DECISION_TTL_SECONDS", 24 * 60 * 60
            ),
        )

    def validate(self) -> None:
        if self.mode not in {"mock", "local"}:
            raise ValueError(
                "VEILPOOL_MODE must be 'mock' or 'local'. No mainnet or "
                "real-chain mode is shipped."
            )
        if self.chain_id in FORBIDDEN_MAINNET_CHAIN_IDS:
            raise ValueError(
                f"VEILPOOL_CHAIN_ID={self.chain_id} is a mainnet chain id and "
                "is never allowed."
            )
        if self.mode == "local":
            if self.chain_id != LOCAL_CHAIN_ID:
                raise ValueError(
                    "VEILPOOL_MODE=local requires VEILPOOL_CHAIN_ID=31337 "
                    "(Anvil). Other chain ids, including testnets, are rejected."
                )
            if not self.contract_address:
                raise ValueError(
                    "VEILPOOL_CONTRACT_ADDRESS is required when "
                    "VEILPOOL_MODE=local."
                )
            _validate_eth_address(
                "VEILPOOL_CONTRACT_ADDRESS", self.contract_address
            )
            _validate_loopback_url("VEILPOOL_INDEXER_URL", self.indexer_url)
            _validate_loopback_url(
                "VEILPOOL_LOCAL_RPC_URL", self.local_rpc_url
            )
            _validate_eth_address(
                "VEILPOOL_LOCAL_FROM_ADDRESS", self.local_from_address
            )
        elif self.chain_id not in ALLOWED_TESTNET_CHAIN_IDS:
            raise ValueError(
                f"VEILPOOL_CHAIN_ID={self.chain_id} is not an allowed testnet "
                "chain. Mainnet and unknown chains are rejected."
            )
        if self.indexer_timeout_seconds <= 0:
            raise ValueError("VEILPOOL_INDEXER_TIMEOUT_SECONDS must be positive")
        if self.local_deposit_timeout_seconds < 0:
            raise ValueError(
                "VEILPOOL_LOCAL_DEPOSIT_TIMEOUT_SECONDS must be zero or positive"
            )
        if self.local_withdrawal_timeout_seconds < 0:
            raise ValueError(
                "VEILPOOL_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS must be zero or positive"
            )
        if self.local_verifier_kind not in LOCAL_VERIFIER_KINDS:
            raise ValueError(
                "VEILPOOL_LOCAL_VERIFIER_KIND must be 'mock' or 'groth16'."
            )
        if self.intent_ttl_seconds < 0:
            raise ValueError("VEILPOOL_INTENT_TTL_SECONDS must be zero or positive")
        if self.quote_ttl_seconds < 0:
            raise ValueError("VEILPOOL_QUOTE_TTL_SECONDS must be zero or positive")
        if self.compliance_ttl_seconds < 0:
            raise ValueError(
                "VEILPOOL_COMPLIANCE_TTL_SECONDS must be zero or positive"
            )
        if self.require_auth and not self.api_token.strip():
            raise ValueError(
                "VEILPOOL_API_TOKEN must not be empty when VEILPOOL_REQUIRE_AUTH=true"
            )
        if self.rate_limit_window_seconds <= 0:
            raise ValueError(
                "VEILPOOL_RATE_LIMIT_WINDOW_SECONDS must be positive"
            )
        for name, value in (
            (
                "VEILPOOL_RATE_LIMIT_DEPOSIT_INTENT",
                self.rate_limit_deposit_intent,
            ),
            (
                "VEILPOOL_RATE_LIMIT_WITHDRAWAL_QUOTE",
                self.rate_limit_withdrawal_quote,
            ),
            (
                "VEILPOOL_RATE_LIMIT_WITHDRAWAL_SUBMIT",
                self.rate_limit_withdrawal_submit,
            ),
            ("VEILPOOL_RATE_LIMIT_COMPLIANCE", self.rate_limit_compliance),
            ("VEILPOOL_RATE_LIMIT_ADMIN", self.rate_limit_admin),
            (
                "VEILPOOL_RATE_LIMIT_LOCAL_DEPOSIT",
                self.rate_limit_local_deposit,
            ),
            (
                "VEILPOOL_RATE_LIMIT_LOCAL_WITHDRAWAL",
                self.rate_limit_local_withdrawal,
            ),
            (
                "VEILPOOL_RATE_LIMIT_POOL_PATH",
                self.rate_limit_pool_path,
            ),
        ):
            if value < 0:
                raise ValueError(f"{name} must be zero or positive")
        if self.max_body_bytes <= 0:
            raise ValueError("VEILPOOL_MAX_BODY_BYTES must be positive")
        if self.review_decision_ttl_seconds <= 0:
            raise ValueError(
                "VEILPOOL_REVIEW_DECISION_TTL_SECONDS must be positive"
            )
        if self.local_maturity_seconds is not None and self.local_maturity_seconds < 0:
            raise ValueError(
                "VEILPOOL_LOCAL_MATURITY_SECONDS must be zero or positive"
            )
