from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_AMOUNT_RE = re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")
_WEI_RE = re.compile(r"^[0-9]{1,78}$")
_PROOF_RE = re.compile(r"^0x[0-9a-fA-F]+$")
_ZERO_ADDRESS = "0x" + "0" * 40

_SECRET_KEY_MARKERS = (
    "note",
    "passphrase",
    "secret",
    "mnemonic",
    "privatekey",
    "private_key",
    "preimage",
    "seedphrase",
    "seed_phrase",
)


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _reject_secret_keys(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            normalized = _normalize_key(key_text)
            if any(marker in normalized for marker in _SECRET_KEY_MARKERS):
                location = f"{path}.{key_text}" if path else key_text
                raise ValueError(
                    f"Field '{location}' is not accepted. "
                    "Client secret material must remain client-side."
                )
            _reject_secret_keys(child, f"{path}.{key_text}" if path else key_text)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_keys(child, f"{path}[{index}]")


def validate_address(value: str) -> str:
    if not isinstance(value, str) or not _ADDRESS_RE.match(value):
        raise ValueError(
            "address must be a 0x-prefixed 20-byte hex string"
        )
    return value


def validate_recipient_address(value: str) -> str:
    value = validate_address(value)
    if value.lower() == _ZERO_ADDRESS:
        raise ValueError("recipient must not be the zero address")
    return value


def validate_hex32(value: str) -> str:
    if not isinstance(value, str) or not _HEX32_RE.match(value):
        raise ValueError("value must be 0x-prefixed 32-byte hex")
    return value


def validate_amount(value: str) -> str:
    if not isinstance(value, str) or not _AMOUNT_RE.match(value):
        raise ValueError("amount must be a positive decimal string")
    return value


def validate_wei(value: str) -> str:
    if not isinstance(value, str) or not _WEI_RE.match(value):
        raise ValueError("value must be an unsigned integer string")
    return value


def validate_proof(value: str) -> str:
    if not isinstance(value, str) or not _PROOF_RE.match(value):
        raise ValueError("proof must be 0x-prefixed hexadecimal")
    hex_digits = len(value) - 2
    if hex_digits < 64 or hex_digits > 4096 or hex_digits % 2 != 0:
        raise ValueError("proof must be 32-2048 bytes of even-length hex")
    return value


Address = Annotated[str, AfterValidator(validate_address)]
RecipientAddress = Annotated[str, AfterValidator(validate_recipient_address)]
Hex32 = Annotated[str, AfterValidator(validate_hex32)]
AmountString = Annotated[str, AfterValidator(validate_amount)]
WeiString = Annotated[str, AfterValidator(validate_wei)]
ProofHex = Annotated[str, AfterValidator(validate_proof)]


class StrictModel(BaseModel):
    """All request models forbid unknown and secret-bearing fields."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_client_secrets(cls, data: Any) -> Any:
        _reject_secret_keys(data)
        return data


class DepositIntentRequest(StrictModel):
    pool_id: str = Field(min_length=1, max_length=64)
    depositor_address: Address
    amount: AmountString
    # Public commitment generated client-side. Optional so the client can defer
    # it to the mock chain call; it is never secret material.
    commitment: Hex32 | None = None


class MockDepositRequest(StrictModel):
    intent_id: str = Field(min_length=1, max_length=64)
    commitment: Hex32
    tx_hash: Hex32 | None = None


class LocalDepositRequest(StrictModel):
    """Dev-only local Anvil deposit. Only public 32-byte data is accepted."""

    intent_id: str = Field(min_length=1, max_length=64)
    commitment: Hex32


class LocalWithdrawalRequest(StrictModel):
    """Dev-only local Anvil withdrawal. Public proof/signals only.

    Field values are validated in the route so malformed proofs and public
    signals get stable ``INVALID_PROOF`` / ``INVALID_PUBLIC_SIGNALS`` codes
    instead of generic pydantic field errors. No note, witness or secret field
    is accepted.
    """

    quote_id: str = Field(min_length=1, max_length=64)
    # Generous caps: the route maps malformed values to INVALID_PROOF /
    # INVALID_PUBLIC_SIGNALS instead of generic pydantic length errors.
    proof: str = Field(min_length=1, max_length=8192)
    root: str = Field(min_length=1, max_length=256)
    nullifier: str = Field(min_length=1, max_length=256)
    recipient: str = Field(min_length=1, max_length=128)
    relayer_fee_wei: str = Field(min_length=1, max_length=256)


class WithdrawalQuoteRequest(StrictModel):
    pool_id: str = Field(min_length=1, max_length=64)
    recipient_address: RecipientAddress
    relayer_id: str = Field(min_length=1, max_length=64)


class PublicSignals(StrictModel):
    root: Hex32
    nullifier_hash: Hex32
    recipient: RecipientAddress
    fee_wei: WeiString


class WithdrawalSubmitRequest(StrictModel):
    pool_id: str = Field(min_length=1, max_length=64)
    quote_id: str = Field(min_length=1, max_length=64)
    proof: ProofHex
    public_signals: PublicSignals
    recipient_address: RecipientAddress


class PoolAdminActionRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=500)


class ComplianceReviewDecisionRequest(StrictModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=1, max_length=500)
    # Optional override; defaults to VEILPOOL_REVIEW_DECISION_TTL_SECONDS.
    expires_in_seconds: int | None = Field(
        default=None, ge=1, le=7 * 24 * 60 * 60
    )
    # Alternative absolute expiry. Only one of the two expiry fields is allowed.
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_expiry_choice(self) -> "ComplianceReviewDecisionRequest":
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        if self.expires_in_seconds is not None and self.expires_at is not None:
            raise ValueError(
                "Provide only one of expires_in_seconds or expires_at"
            )
        return self
