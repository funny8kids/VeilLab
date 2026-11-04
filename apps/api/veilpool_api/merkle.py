from __future__ import annotations

import hashlib
from collections.abc import Sequence


def _hash_leaf(commitment: str) -> bytes:
    raw = bytes.fromhex(commitment[2:] if commitment.startswith("0x") else commitment)
    if len(raw) != 32:
        raise ValueError("commitment must be 32 bytes")
    return hashlib.sha256(b"\x00" + raw).digest()


def _hash_pair(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _zero_hashes(depth: int) -> list[bytes]:
    zeros = [b"\x00" * 32]
    for _ in range(depth):
        zeros.append(_hash_pair(zeros[-1], zeros[-1]))
    return zeros


def merkle_root(commitments: Sequence[str], depth: int = 20) -> str:
    """Deterministic mock Merkle root for a fixed-depth binary tree.

    This is not a production Merkle tree implementation; it exists so the mock
    API can expose a stable root for the demo flow. Leaves are ordered by
    on-chain leaf index.
    """

    if depth <= 0 or depth > 32:
        raise ValueError("tree depth out of range")
    leaves = [_hash_leaf(item) for item in commitments]
    zeros = _zero_hashes(depth)

    def subtree(level: int, start: int) -> bytes:
        if start >= len(leaves):
            return zeros[level]
        if level == 0:
            return leaves[start]
        half = 1 << (level - 1)
        return _hash_pair(
            subtree(level - 1, start),
            subtree(level - 1, start + half),
        )

    root = subtree(depth, 0)
    return "0x" + root.hex()
