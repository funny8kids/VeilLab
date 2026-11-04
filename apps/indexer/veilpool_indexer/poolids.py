"""Pool identifier helpers.

The contract stores pool IDs as ``bytes32``. The existing mock API uses short
human-readable IDs such as ``pool_eth_01``. The deployment script encodes those
short IDs as right-padded ASCII bytes32 values so the indexer can expose both
forms without a database mapping.
"""

from __future__ import annotations

import re

_HEX32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_HEX_RE = re.compile(r"^0x[0-9a-fA-F]+$")


def normalize_bytes32(value: str) -> str:
    """Normalize a 32-byte hex value; raise ValueError for malformed input."""

    raw = value.strip()
    if not raw.startswith("0x"):
        raw = "0x" + raw
    if not _HEX_RE.match(raw):
        raise ValueError("not a hex value")
    digits = raw[2:]
    if len(digits) > 64:
        raise ValueError("value is longer than 32 bytes")
    return "0x" + digits.rjust(64, "0").lower()


def pool_id_to_bytes32(value: str) -> str:
    """Convert a label or hex pool ID into a 32-byte hex pool ID.

    ``pool_eth_01`` -> ``0x706f6f6c5f6574685f3031`` plus zero padding.
    """

    raw = value.strip()
    if _HEX32_RE.match(raw):
        return raw.lower()
    if raw.startswith("0x") and _HEX_RE.match(raw):
        return normalize_bytes32(raw)
    encoded = raw.encode("utf-8")
    if not encoded or len(encoded) > 32:
        raise ValueError("pool label must be 1-32 UTF-8 bytes")
    return "0x" + encoded.hex().ljust(64, "0")


def bytes32_to_pool_key(value: str) -> str | None:
    """Decode a right-padded ASCII bytes32 pool ID into its short label.

    Returns ``None`` when the bytes are not printable ASCII (for example, a
    keccak256 pool ID).
    """

    try:
        hex_value = normalize_bytes32(value)
    except ValueError:
        return None
    raw = bytes.fromhex(hex_value[2:]).rstrip(b"\x00")
    if not raw:
        return None
    try:
        label = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if not label or any(ord(char) < 0x20 or ord(char) > 0x7E for char in label):
        return None
    return label


def parse_pool_selector(value: str) -> tuple[str, str | None]:
    """Return ``(bytes32 hex, optional label)`` for an API path value."""

    raw = value.strip()
    if _HEX32_RE.match(raw):
        return raw.lower(), bytes32_to_pool_key(raw)
    if raw.startswith("0x") and _HEX_RE.match(raw):
        normalized = normalize_bytes32(raw)
        return normalized, bytes32_to_pool_key(normalized)
    return pool_id_to_bytes32(raw), raw
