from __future__ import annotations

import json
from pathlib import Path

import pytest

from veilpool_indexer.merkle import build_path, root_from_path, zero_hashes
from veilpool_indexer.poseidon import (
    DOMAIN_NODE,
    FIELD_MODULUS,
    field_from_hex,
    field_to_hex32,
    hash3,
)

VECTOR_PATH = (
    Path(__file__).resolve().parents[3]
    / "circuits"
    / "test-vectors"
    / "membership-v1.json"
)


def _load_vector() -> dict:
    if not VECTOR_PATH.is_file():
        pytest.skip(f"circuit fixture not available: {VECTOR_PATH}")
    return json.loads(VECTOR_PATH.read_text(encoding="utf-8"))


def test_hash3_matches_circomlib_zero_hash():
    # Poseidon(DOMAIN_NODE, 0, 0), cross-checked against circomlibjs 2.0.5.
    expected = (
        "0x2aaa1743f271f195750639c14815c9f0c9bc8c6d9daede64e4b393ade6cf5bef"
    )
    assert field_to_hex32(hash3(DOMAIN_NODE, 0, 0)) == expected
    assert zero_hashes(1)[1] == int(expected, 16)


def test_fixture_merkle_root_and_path_match_exactly():
    vector = _load_vector()
    tree = vector["tree"]
    path = build_path(tree["leaves"], tree["leaf_index"])

    assert path.leaf_index == tree["leaf_index"] == 5
    assert path.leaf_count == len(tree["leaves"]) == 8
    assert path.depth == tree["depth"] == 20
    assert field_to_hex32(path.root) == tree["root"]
    assert [field_to_hex32(value) for value in path.path_elements] == tree[
        "path_elements"
    ]
    assert list(path.path_indices) == tree["path_indices"]

    # Verify the path exactly as the circuit does.
    leaf = int(tree["leaves"][tree["leaf_index"]], 16)
    assert field_to_hex32(root_from_path(leaf, path.path_elements, path.path_indices)) == tree[
        "root"
    ]

    # With eight leaves, levels 3..19 have a missing right sibling, so the
    # fixture's remaining path elements are the zero-subtree chain.
    zeros = zero_hashes(20)
    assert list(path.path_elements[3:]) == list(zeros[3:20])


def test_field_helpers_and_range_checks():
    value = 0x123456789ABCDEF
    assert field_from_hex(field_to_hex32(value)) == value
    assert field_from_hex("123456789abcdef") == value
    assert field_from_hex("0x" + format(value, "064x")) == value

    with pytest.raises(ValueError):
        field_from_hex("0x" + format(FIELD_MODULUS, "064x"))
    with pytest.raises(ValueError):
        field_from_hex("not-hex")
    with pytest.raises(ValueError):
        field_to_hex32(FIELD_MODULUS)
    with pytest.raises(ValueError):
        hash3(FIELD_MODULUS, 0, 0)
