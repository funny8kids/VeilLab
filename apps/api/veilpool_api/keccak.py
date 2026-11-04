"""Minimal Keccak-256 for the local deposit ABI selector.

Only public data is hashed here: the fixed signature ``deposit(bytes32)``. A
pure-Python implementation keeps the API dependency-free; the code is not a
general-purpose crypto library.
"""

from __future__ import annotations

_MASK_64 = (1 << 64) - 1
_RATE_BYTES = 136  # Keccak-256 rate

_ROUND_CONSTANTS = (
    0x0000000000000001,
    0x0000000000008082,
    0x800000000000808A,
    0x8000000080008000,
    0x000000000000808B,
    0x0000000080000001,
    0x8000000080008081,
    0x8000000000008009,
    0x000000000000008A,
    0x0000000000000088,
    0x0000000080008009,
    0x000000008000000A,
    0x000000008000808B,
    0x800000000000008B,
    0x8000000000008089,
    0x8000000000008003,
    0x8000000000008002,
    0x8000000000000080,
    0x000000000000800A,
    0x800000008000000A,
    0x8000000080008081,
    0x8000000000008080,
    0x0000000080000001,
    0x8000000080008008,
)

_ROTATION_OFFSETS = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rotl(value: int, shift: int) -> int:
    if shift == 0:
        return value & _MASK_64
    return ((value << shift) | (value >> (64 - shift))) & _MASK_64


def _keccak_f(state: list[int]) -> None:
    for round_constant in _ROUND_CONSTANTS:
        # Theta
        columns = [
            state[x]
            ^ state[x + 5]
            ^ state[x + 10]
            ^ state[x + 15]
            ^ state[x + 20]
            for x in range(5)
        ]
        deltas = [
            columns[(x - 1) % 5] ^ _rotl(columns[(x + 1) % 5], 1)
            for x in range(5)
        ]
        for x in range(5):
            for y in range(0, 25, 5):
                state[x + y] ^= deltas[x]

        # Rho + Pi
        permuted = [0] * 25
        for x in range(5):
            for y in range(5):
                target = y + 5 * ((2 * x + 3 * y) % 5)
                permuted[target] = _rotl(
                    state[x + 5 * y], _ROTATION_OFFSETS[x][y]
                )

        # Chi
        for x in range(5):
            for y in range(5):
                cell = x + 5 * y
                state[cell] = (
                    permuted[cell]
                    ^ ((~permuted[(x + 1) % 5 + 5 * y]) & permuted[(x + 2) % 5 + 5 * y])
                ) & _MASK_64

        # Iota
        state[0] ^= round_constant


def keccak_256(data: bytes) -> bytes:
    """Return the 32-byte Keccak-256 digest of ``data``."""

    payload = bytearray(data)
    padding_length = _RATE_BYTES - (len(payload) % _RATE_BYTES)
    if padding_length == 1:
        padding_length = _RATE_BYTES
    payload.extend(b"\x00" * padding_length)
    payload[len(data)] ^= 0x01
    payload[-1] ^= 0x80

    state = [0] * 25
    for offset in range(0, len(payload), _RATE_BYTES):
        block = payload[offset : offset + _RATE_BYTES]
        for lane in range(_RATE_BYTES // 8):
            state[lane] ^= int.from_bytes(
                block[lane * 8 : lane * 8 + 8], "little"
            )
        _keccak_f(state)

    digest = b"".join(lane.to_bytes(8, "little") for lane in state)
    return digest[:32]
