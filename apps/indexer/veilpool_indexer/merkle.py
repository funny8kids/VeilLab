"""Depth-20 Poseidon Merkle tree and path builder.

Conventions match ``circuits/circuits/membership.circom`` and
``circuits/test-vectors/membership-v1.json`` exactly:

* ``zero[0] = 0`` and ``zero[i+1] = Poseidon(DOMAIN_NODE, zero[i], zero[i])``;
* leaves are the pool's canonical deposit commitments in leaf-index order;
* ``node = Poseidon(DOMAIN_NODE, left, right)``;
* ``path_indices[i] = 0`` means the current node is the left child;
* ``path_indices[0]`` is the least significant bit of the leaf index.

The tree is rebuilt from the indexer's canonical deposits on demand. It stores
no note, secret or witness data.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

from .poseidon import DOMAIN_NODE, FIELD_MODULUS, field_from_hex, hash3

TREE_DEPTH = 20
MAX_LEAVES = 1 << TREE_DEPTH


class CommitmentError(ValueError):
    """A stored commitment cannot be a leaf in the Poseidon tree."""

    def __init__(self, code: str, message: str, *, leaf_index: int | None = None):
        super().__init__(message)
        self.code = code
        self.leaf_index = leaf_index


@dataclass(frozen=True)
class MerklePath:
    root: int
    leaf_index: int
    leaf_count: int
    depth: int
    path_elements: tuple[int, ...]
    path_indices: tuple[int, ...]


@lru_cache(maxsize=None)
def zero_hashes(depth: int = TREE_DEPTH) -> tuple[int, ...]:
    """Return ``zero[0..depth]`` inclusive (``depth + 1`` values)."""

    if depth < 0:
        raise ValueError("tree depth must be non-negative")
    values = [0]
    for _ in range(depth):
        values.append(hash3(DOMAIN_NODE, values[-1], values[-1]))
    return tuple(values)


def hash_node(left: int, right: int) -> int:
    return hash3(DOMAIN_NODE, left, right)


def canonical_field(value: str | int, *, name: str = "field element") -> int:
    """Validate a canonical field element; zero is allowed."""

    try:
        if isinstance(value, str):
            return field_from_hex(value)
        if isinstance(value, int) and not isinstance(value, bool):
            if value < 0 or value >= FIELD_MODULUS:
                raise ValueError("value is outside the BN254 scalar field")
            return value
        raise ValueError("value must be a hex string or integer")
    except (TypeError, ValueError) as exc:
        raise CommitmentError(
            "NON_CANONICAL_COMMITMENT",
            f"{name} is not a canonical BN254 field element: {exc}",
        ) from exc


def canonical_commitment(value: str | int, *, leaf_index: int | None = None) -> int:
    """Validate one commitment as a non-zero canonical field element."""

    try:
        number = canonical_field(value, name="commitment")
    except CommitmentError as exc:
        detail = (
            f"Stored commitment at leaf {leaf_index} is not a canonical BN254 "
            "field element"
            if leaf_index is not None
            else "Commitment is not a canonical BN254 field element"
        )
        raise CommitmentError(
            "NON_CANONICAL_COMMITMENT", detail, leaf_index=leaf_index
        ) from exc

    if number == 0:
        detail = (
            f"Stored commitment at leaf {leaf_index} is zero"
            if leaf_index is not None
            else "Commitment must be non-zero"
        )
        raise CommitmentError("ZERO_COMMITMENT", detail, leaf_index=leaf_index)
    return number


def validate_commitments(commitments: Sequence[str | int]) -> list[int]:
    """Validate all leaves in order and return their field values."""

    return [
        canonical_commitment(value, leaf_index=index)
        for index, value in enumerate(commitments)
    ]


def _levels_for(leaves: Sequence[int], depth: int) -> list[tuple[int, ...]]:
    zero = zero_hashes(depth)
    levels: list[tuple[int, ...]] = [tuple(leaves)]
    for level in range(depth):
        previous = levels[-1]
        empty = zero[level]
        following: list[int] = []
        for index in range(0, len(previous), 2):
            left = previous[index]
            right = previous[index + 1] if index + 1 < len(previous) else empty
            following.append(hash_node(left, right))
        levels.append(tuple(following))
    return levels


def build_path(
    commitments: Sequence[str | int],
    leaf_index: int,
    *,
    depth: int = TREE_DEPTH,
) -> MerklePath:
    """Build the depth-``depth`` path for one leaf.

    ``commitments`` must already be ordered by on-chain leaf index. Every value
    is validated before hashing so a non-canonical stored commitment fails
    closed instead of being truncated modulo ``p``.
    """

    if not isinstance(leaf_index, int) or isinstance(leaf_index, bool):
        raise ValueError("leaf_index must be an integer")
    if not 0 <= leaf_index < len(commitments):
        raise IndexError("leaf_index is outside the commitment list")
    if len(commitments) > (1 << depth):
        raise ValueError(f"tree has more than 2^{depth} leaves")

    leaves = validate_commitments(commitments)
    levels = _levels_for(leaves, depth)
    zero = zero_hashes(depth)

    path_elements: list[int] = []
    path_indices: list[int] = []
    cursor = leaf_index
    for level in range(depth):
        sibling = cursor ^ 1
        siblings = levels[level]
        path_elements.append(
            siblings[sibling] if sibling < len(siblings) else zero[level]
        )
        path_indices.append(cursor & 1)
        cursor >>= 1

    return MerklePath(
        root=levels[depth][0],
        leaf_index=leaf_index,
        leaf_count=len(leaves),
        depth=depth,
        path_elements=tuple(path_elements),
        path_indices=tuple(path_indices),
    )


def root_from_path(
    leaf: int,
    path_elements: Sequence[int],
    path_indices: Sequence[int],
) -> int:
    """Recompute the root exactly as the circuit does; used by tests/clients."""

    if len(path_elements) != len(path_indices):
        raise ValueError("path_elements and path_indices must have the same length")
    current = canonical_commitment(leaf)
    for element, direction in zip(path_elements, path_indices):
        if direction not in (0, 1):
            raise ValueError("path index must be 0 or 1")
        sibling = canonical_field(element, name="path element")
        left, right = (current, sibling) if direction == 0 else (sibling, current)
        current = hash_node(left, right)
    return current
