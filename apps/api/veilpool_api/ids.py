from __future__ import annotations

import os
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LOCK = threading.Lock()
_LAST_MS = -1
_LAST_RANDOM = -1
_RANDOM_BITS = 80
_RANDOM_MAX = (1 << _RANDOM_BITS) - 1


def _next_components() -> tuple[int, int]:
    """Monotonic millisecond/random pair (ULID spec monotonic factory)."""

    global _LAST_MS, _LAST_RANDOM
    now_ms = int(time.time() * 1000)
    with _LOCK:
        if now_ms > _LAST_MS:
            random_part = int.from_bytes(os.urandom(10), "big")
        else:
            now_ms = _LAST_MS
            random_part = _LAST_RANDOM + 1
            if random_part > _RANDOM_MAX:
                now_ms += 1
                random_part = 0
        _LAST_MS = now_ms
        _LAST_RANDOM = random_part
        return now_ms, random_part


def _ulid() -> str:
    timestamp, random_part = _next_components()
    value = ((timestamp & ((1 << 48) - 1)) << _RANDOM_BITS) | random_part
    chars: list[str] = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    """Create a prefixed, monotonic identifier such as ``dep_01J...``."""

    return f"{prefix}_{_ulid()}"
