"""Shared deterministic chain fixtures for indexer and API tests."""

from __future__ import annotations

from fake_chain import POOL_ETH_01, block, build_chain

# Canonical BN254 field elements: the leading 0x01 byte keeps each value below
# p (~0x3064...), as required by the Poseidon Merkle path endpoint. The final
# byte makes the four commitments distinct.
C1 = "0x01" + "a1" * 31
C2 = "0x01" + "a2" * 31
C3 = "0x01" + "a3" * 31
C4 = "0x01" + "a4" * 31
R1 = "0x" + "b1" * 32
R2 = "0x" + "b2" * 32
R3 = "0x" + "b3" * 32
R4 = "0x" + "b4" * 32
N1 = "0x" + "c1" * 32
RECIPIENT = "0x" + "d1" * 20


def _deposit(commitment: str, leaf_index: int, root: str) -> tuple[tuple, tuple]:
    return (
        (
            "Deposit",
            {
                "commitment": commitment,
                "leaf_index": leaf_index,
                "timestamp": 1_700_000_000 + leaf_index,
            },
        ),
        ("RootUpdated", {"root": root, "leaf_index": leaf_index}),
    )


def block_one() -> dict:
    deposit, root = _deposit(C1, 0, R1)
    return block(
        (
            "PoolCreated",
            {"denomination": 10**17, "root_window": 64, "maturity": 1800},
        ),
        deposit,
        root,
        salt="shared-a1",
        timestamp=1_700_000_012,
    )


def chain_a():
    deposit2, root2 = _deposit(C2, 1, R2)
    return build_chain(
        [
            block_one(),
            block(
                deposit2,
                root2,
                ("PoolPaused", {"reason": "maintenance"}),
                salt="a2",
                timestamp=1_700_000_024,
            ),
            block(
                ("PoolResumed", {}),
                (
                    "Withdrawal",
                    {
                        "nullifier": N1,
                        "recipient": RECIPIENT,
                        "fee": 1000,
                        "timestamp": 1_700_000_036,
                    },
                ),
                salt="a3",
                timestamp=1_700_000_036,
            ),
        ]
    )


def chain_b():
    deposit3, root3 = _deposit(C3, 1, R3)
    deposit4, root4 = _deposit(C4, 2, R4)
    return build_chain(
        [
            block_one(),
            block(deposit3, root3, salt="b2", timestamp=1_700_000_024),
            block(
                deposit4,
                root4,
                ("PoolPaused", {"reason": "reorg pause"}),
                salt="b3",
                timestamp=1_700_000_036,
            ),
        ]
    )


__all__ = [
    "C1",
    "C2",
    "C3",
    "C4",
    "POOL_ETH_01",
    "R1",
    "R2",
    "R3",
    "R4",
    "N1",
    "RECIPIENT",
    "block_one",
    "chain_a",
    "chain_b",
]
