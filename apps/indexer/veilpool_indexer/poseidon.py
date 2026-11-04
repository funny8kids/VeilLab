"""Pure-Python Poseidon(3) over BN254, matching circomlib 2.0.5.

The membership circuit uses ``Poseidon(3)`` with the state layout
``[0, a0, a1, a2]``, eight full rounds and 56 partial rounds. The domain tag is
not hard-coded into this module: the caller supplies it as the first input.
For VeilPool Merkle nodes that means::

    node = hash3(DOMAIN_NODE, left, right)

The round constants are generated from the circomlibjs reference table by
``apps/indexer/scripts/gen_poseidon_constants.py``; see
``poseidon_constants.py`` for provenance.

This is intentionally a straightforward reference implementation, not a
constant-time or optimized prover backend. It is suitable for the local indexer
and small test trees.
"""

from __future__ import annotations

import re

from .poseidon_constants import C4, M4, ROUNDS_F, ROUNDS_P, WIDTH

# BN254 scalar field modulus used by circom/snarkjs and circomlib.
FIELD_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617

# "veilpool-merkle-v1" as a big-endian integer. Public constant, not a secret.
DOMAIN_NODE = 0x7665696C706F6F6C2D6D65726B6C652D7631

_HEX_RE = re.compile(r"^(?:0[xX])?[0-9a-fA-F]{1,64}$")

if WIDTH != 4 or ROUNDS_F != 8 or ROUNDS_P != 56:
    raise RuntimeError("poseidon_constants.py does not describe Poseidon(3)")


def _require_field(value: int, name: str = "value") -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer field element")
    if value < 0 or value >= FIELD_MODULUS:
        raise ValueError(f"{name} is outside the BN254 scalar field")
    return value


def field_from_hex(value: str) -> int:
    """Parse a 0x-prefixed (or bare) hex string as a canonical field element.

    Raises ``ValueError`` for malformed input and for values ``>= p``. The
    zero value is a valid field element here; callers that require a non-zero
    commitment must check it separately.
    """

    if not isinstance(value, str):
        raise ValueError("field element must be a hex string")
    raw = value.strip()
    if not _HEX_RE.match(raw):
        raise ValueError("not a 1-32 byte hexadecimal value")
    digits = raw[2:] if raw[:2].lower() == "0x" else raw
    number = int(digits, 16)
    if number >= FIELD_MODULUS:
        raise ValueError("value is not a canonical BN254 field element (>= p)")
    return number


def field_to_hex32(value: int) -> str:
    """Encode a canonical field element as a 32-byte, 0x-prefixed hex string."""

    _require_field(value)
    return "0x" + format(value, "064x")


def _pow5(value: int) -> int:
    return pow(value, 5, FIELD_MODULUS)


def hash3(a0: int, a1: int, a2: int) -> int:
    """Return Poseidon(3) over BN254 for three field elements.

    The state starts as ``[0, a0, a1, a2]``. Round constants are applied to all
    state words; the S-box is applied to every word in the first and last four
    full rounds and only to ``state[0]`` in the 56 partial rounds. The MDS
    matrix is row-major.
    """

    state = [
        0,
        _require_field(a0, "a0"),
        _require_field(a1, "a1"),
        _require_field(a2, "a2"),
    ]

    for round_index in range(ROUNDS_F + ROUNDS_P):
        offset = round_index * WIDTH
        state = [
            (state[index] + C4[offset + index]) % FIELD_MODULUS
            for index in range(WIDTH)
        ]

        full_round = round_index < ROUNDS_F // 2 or round_index >= (
            ROUNDS_F // 2 + ROUNDS_P
        )
        if full_round:
            state = [_pow5(value) for value in state]
        else:
            state[0] = _pow5(state[0])

        state = [
            sum(M4[row][column] * state[column] for column in range(WIDTH))
            % FIELD_MODULUS
            for row in range(WIDTH)
        ]

    return state[0]
