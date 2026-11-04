from __future__ import annotations

from decimal import Decimal, InvalidOperation

MAX_AMOUNT_DIGITS = 78


def parse_amount_to_wei(value: str, decimals: int) -> int:
    """Convert a decimal amount string to exact integer base units.

    Floats never enter this path. Non-integral base units are rejected rather
    than rounded.
    """

    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount is not a valid decimal string") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be greater than zero")
    scale = Decimal(10) ** decimals
    raw = amount * scale
    if raw != raw.to_integral_value():
        raise ValueError(
            f"amount has more than {decimals} decimal places for this asset"
        )
    result = int(raw)
    if result <= 0:
        raise ValueError("amount must be greater than zero")
    if len(str(result)) > MAX_AMOUNT_DIGITS:
        raise ValueError("amount is out of range")
    return result


def format_wei(value: int, decimals: int) -> str:
    """Format base units as a compact decimal string (no float math)."""

    amount = Decimal(value) / (Decimal(10) ** decimals)
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def split_fee(amount_wei: int, fee_bps: int) -> int:
    return amount_wei * fee_bps // 10_000
