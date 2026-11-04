from __future__ import annotations

import pytest

from veilpool_indexer.merkle import (
    CommitmentError,
    build_path,
    canonical_commitment,
    root_from_path,
    zero_hashes,
)
from veilpool_indexer.poseidon import FIELD_MODULUS, field_to_hex32


def test_single_leaf_path_uses_zero_siblings():
    commitment = field_to_hex32(0x12345)
    path = build_path([commitment], 0)

    assert path.leaf_count == 1
    assert path.leaf_index == 0
    assert list(path.path_indices) == [0] * 20
    assert list(path.path_elements) == list(zero_hashes(20)[:20])
    assert path.root == root_from_path(
        int(commitment, 16), path.path_elements, path.path_indices
    )


def test_non_canonical_and_zero_commitments_are_rejected():
    # Build a value >= p without relying on field_to_hex32, which rejects it.
    non_canonical = "0x" + format(FIELD_MODULUS, "064x")

    with pytest.raises(CommitmentError) as non_canonical_error:
        build_path([non_canonical], 0)
    assert non_canonical_error.value.code == "NON_CANONICAL_COMMITMENT"

    with pytest.raises(CommitmentError) as zero_error:
        canonical_commitment("0x" + "00" * 32)
    assert zero_error.value.code == "ZERO_COMMITMENT"


def test_commitment_must_be_nonzero_for_leaves_but_zero_path_elements_are_valid():
    leaf = field_to_hex32(7)
    path = build_path([leaf], 0)
    # A single-leaf tree has zero siblings; those are valid field elements.
    assert path.path_elements[0] == 0
    assert root_from_path(int(leaf, 16), path.path_elements, path.path_indices) == path.root
