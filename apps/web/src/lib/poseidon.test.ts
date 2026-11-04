import { describe, expect, it } from "vitest";
import fixture from "../../../../circuits/test-vectors/membership-v1.json";
import {
  DOMAIN_COMMITMENT,
  DOMAIN_NODE,
  DOMAIN_NULLIFIER,
  FIELD_MODULUS,
  fieldFromHex,
  fieldToHex32,
  hash3,
  hash5,
  hash6,
  poolIdToField,
} from "./poseidon";

const note = fixture.note;
const derived = fixture.derived;
const tree = fixture.tree;

function field(value: string): bigint {
  return fieldFromHex(value);
}

describe("Poseidon over BN254 (circomlib 2.0.5 vectors)", () => {
  it("derives the fixture commitment with Poseidon(6)", () => {
    const commitment = hash6(
      DOMAIN_COMMITMENT,
      BigInt(note.chain_id),
      poolIdToField(note.pool_id_text),
      BigInt(note.denomination),
      field(note.secret_field),
      field(note.nullifier_secret_field),
    );
    expect(fieldToHex32(commitment)).toBe(derived.commitment);
  });

  it("derives the fixture nullifier with Poseidon(5)", () => {
    const nullifier = hash5(
      DOMAIN_NULLIFIER,
      BigInt(note.chain_id),
      poolIdToField(note.pool_id_text),
      field(derived.commitment),
      field(note.nullifier_secret_field),
    );
    expect(fieldToHex32(nullifier)).toBe(derived.nullifier);
  });

  it("matches the contract fixture zero hash and a second hash3 vector", () => {
    // Values from contracts/test/fixtures/MembershipFixture.sol
    // (ZERO_HASH_1 / HASH3_1_2), themselves generated from circomlibjs.
    expect(hash3(DOMAIN_NODE, 0n, 0n)).toBe(
      19297664213524364827530168733089889066243044099228990808041851126107503287279n,
    );
    expect(hash3(DOMAIN_NODE, 1n, 2n)).toBe(
      5830195650075994963675649032911499390080883489520484897565959462076137715718n,
    );
  });

  it("recomputes the fixture 8-leaf tree root and empty subtree zeros", () => {
    const depth = tree.depth;
    const zero: bigint[] = [0n];
    for (let level = 0; level < depth; level += 1) {
      zero.push(hash3(DOMAIN_NODE, zero[level], zero[level]));
    }

    const levels: bigint[][] = [tree.leaves.map(field)];
    for (let level = 0; level < depth; level += 1) {
      const previous = levels[level];
      const next: bigint[] = [];
      for (let index = 0; index < Math.ceil(previous.length / 2); index += 1) {
        const left = previous[2 * index] ?? zero[level];
        const right = previous[2 * index + 1] ?? zero[level];
        next.push(hash3(DOMAIN_NODE, left, right));
      }
      levels.push(next);
    }

    expect(fieldToHex32(levels[depth][0])).toBe(tree.root);
  });

  it("recomputes the fixture root from its path elements and indices", () => {
    expect(tree.path_elements).toHaveLength(tree.depth);
    expect(tree.path_indices).toHaveLength(tree.depth);

    let current = field(tree.leaves[tree.leaf_index]);
    expect(fieldToHex32(current)).toBe(derived.commitment);

    for (let level = 0; level < tree.depth; level += 1) {
      const sibling = field(tree.path_elements[level]);
      const isRight = tree.path_indices[level] === 1;
      const left = isRight ? sibling : current;
      const right = isRight ? current : sibling;
      current = hash3(DOMAIN_NODE, left, right);
    }

    expect(fieldToHex32(current)).toBe(tree.root);
  });

  it("encodes the canonical pool id exactly as the circuit fixture", () => {
    expect(fieldToHex32(poolIdToField(note.pool_id_text))).toBe(note.pool_id);
    expect(poolIdToField("pool_eth_01")).toBe(
      198655969066724116100767858592150160576042375226781091767425152450098626560n,
    );
  });

  it("rejects empty, NUL, and over-long pool ids", () => {
    expect(() => poolIdToField("")).toThrow();
    expect(() => poolIdToField("pool\u0000id")).toThrow();
    expect(() => poolIdToField("p".repeat(32))).toThrow();
  });

  it("keeps field conversions canonical", () => {
    expect(fieldFromHex(derived.commitment)).toBe(
      BigInt(derived.commitment),
    );
    expect(fieldToHex32(fieldFromHex("0x01"))).toBe(
      `0x${"0".repeat(63)}1`,
    );
    expect(() =>
      fieldFromHex(`0x${FIELD_MODULUS.toString(16)}`),
    ).toThrow(/canonical/);
    expect(() => fieldToHex32(FIELD_MODULUS)).toThrow(/outside/);
    expect(() => fieldToHex32(-1n)).toThrow(/outside/);
  });
});
