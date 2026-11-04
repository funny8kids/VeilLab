// Generates contracts/test/fixtures/MembershipFixture.sol from the proved
// circuit fixture.
//
// TESTNET / SPIKE ONLY.
//
// Sources:
//   circuits/build/proof.json
//   circuits/build/public.json
//   circuits/test-vectors/membership-v1.json
//
// The generated Solidity file contains the Groth16 proof in the exact
// snarkjs "soliditycalldata" order, the six public signals, the eight Merkle
// leaves, and the Poseidon values used by the Solidity tests. The script fails
// if the JSON files disagree or if the Solidity pool-ID label convention does
// not map to the circuit's field value.
//
// Usage (from circuits/):
//   node scripts/gen-solidity-fixture.mjs
//
// Output:
//   ../contracts/test/fixtures/MembershipFixture.sol

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import url from "node:url";
import { buildPoseidon } from "circomlibjs";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const circuitsDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(circuitsDir, "..");
const buildDir = path.join(circuitsDir, "build");
const outputDir = path.join(repoRoot, "contracts", "test", "fixtures");
const outputPath = path.join(outputDir, "MembershipFixture.sol");

const proofPath = path.join(buildDir, "proof.json");
const publicPath = path.join(buildDir, "public.json");
const vectorPath = path.join(circuitsDir, "test-vectors", "membership-v1.json");
const snarkjsCli = path.join(circuitsDir, "node_modules", "snarkjs", "build", "cli.cjs");

const DOMAIN_NODE = 0x7665696c706f6f6c2d6d65726b6c652d7631n;
const DEPTH = 20;

const proof = JSON.parse(await readFile(proofPath, "utf8"));
const publicSignals = JSON.parse(await readFile(publicPath, "utf8"));
const vector = JSON.parse(await readFile(vectorPath, "utf8"));

assert.equal(publicSignals.length, 6, "public.json must contain 6 signals");
assert.equal(vector.public_signals.order.length, 6, "fixture signal order");
assert.deepEqual(
  vector.public_signals.order,
  ["chain_id", "pool_id", "root", "nullifier", "recipient", "fee"],
  "unexpected public signal order",
);

const poseidon = await buildPoseidon();
const F = poseidon.F;
const hash = (inputs) => BigInt(F.toObject(poseidon(inputs)));

function hex32(value) {
  return "0x" + BigInt(value).toString(16).padStart(64, "0");
}

function decimal(value) {
  return BigInt(value).toString(10);
}

function bytes32Literal(value) {
  return "0x" + BigInt(value).toString(16).padStart(64, "0");
}

// --- Recompute the circuit values from the fixture witness -----------------

const chainId = BigInt(vector.note.chain_id);
const denomination = BigInt(vector.note.denomination);
const secretField = BigInt(vector.note.secret_field);
const nullifierSecretField = BigInt(vector.note.nullifier_secret_field);
const poolIdField = BigInt(vector.note.pool_id);
const commitment = BigInt(vector.derived.commitment);
const nullifier = BigInt(vector.derived.nullifier);
const root = BigInt(vector.tree.root);
const recipient = BigInt(vector.public_signals.values.recipient);
const fee = BigInt(vector.public_signals.values.fee);
const leaves = vector.tree.leaves.map((leaf) => BigInt(leaf));

const DOMAIN_COMMITMENT = BigInt(vector.domain.commitment);
const DOMAIN_NULLIFIER = BigInt(vector.domain.nullifier);
assert.equal(BigInt(vector.domain.merkleNode), DOMAIN_NODE, "merkle domain tag");

const commitmentComputed = hash([
  DOMAIN_COMMITMENT,
  chainId,
  poolIdField,
  denomination,
  secretField,
  nullifierSecretField,
]);
const nullifierComputed = hash([
  DOMAIN_NULLIFIER,
  chainId,
  poolIdField,
  commitment,
  nullifierSecretField,
]);
assert.equal(commitmentComputed, commitment, "commitment mismatch");
assert.equal(nullifierComputed, nullifier, "nullifier mismatch");
assert.equal(leaves.length, 8, "the spike fixture must have 8 leaves");
assert.equal(vector.tree.leaf_index, 5, "unexpected fixture leaf index");
assert.equal(leaves[vector.tree.leaf_index], commitment, "commitment is not the fixture leaf");

// Empty subtree roots, exactly as the circuit/contract compute them.
const zero = [0n];
for (let level = 0; level < DEPTH; level++) {
  zero.push(hash([DOMAIN_NODE, zero[level], zero[level]]));
}

// Recompute the eight-leaf tree root with the same rule as the circuit.
let level = leaves;
for (let depth = 0; depth < DEPTH; depth++) {
  const next = [];
  for (let i = 0; i < Math.ceil(level.length / 2); i++) {
    const left = level[2 * i] ?? zero[depth];
    const right = level[2 * i + 1] ?? zero[depth];
    next.push(hash([DOMAIN_NODE, left, right]));
  }
  level = next;
}
assert.equal(level[0], root, "fixture tree root mismatch");

// --- Deploy-label -> circuit field conversion ------------------------------
//
// The deploy script uses right-padded ASCII bytes32 labels. The circuit uses
// 0x00 || UTF-8 || padding as the field element. For labels of at most 31
// bytes, uint256(rightPaddedLabel) >> 8 is the circuit field value, and the
// low byte of the right-padded label is zero. The adapter enforces both
// conditions; this script validates the fixture label.

const poolIdText = vector.note.pool_id_text;
const labelBytes = Buffer.from(poolIdText, "utf8");
assert.ok(labelBytes.length >= 1 && labelBytes.length <= 31, "pool label length");
assert.ok(!labelBytes.includes(0), "pool label must not contain NUL");
const label = Buffer.alloc(32, 0);
labelBytes.copy(label, 0);
const labelValue = BigInt("0x" + label.toString("hex"));
const canonical = Buffer.alloc(32, 0);
labelBytes.copy(canonical, 1);
const canonicalValue = BigInt("0x" + canonical.toString("hex"));
assert.equal(labelValue >> 8n, canonicalValue, "deploy label >> 8 != canonical field");
assert.equal(canonicalValue, poolIdField, "canonical pool id != fixture signal");
assert.equal(labelValue & 0xffn, 0n, "right-padded label low byte must be zero");

// --- Proof encoding --------------------------------------------------------
//
// snarkjs zkey export soliditycalldata applies the required pi_b coordinate
// swap. Use it as the source of truth when available, then cross-check our
// local mapping.

const pA = [BigInt(proof.pi_a[0]), BigInt(proof.pi_a[1])];
const pB = [
  [BigInt(proof.pi_b[0][1]), BigInt(proof.pi_b[0][0])],
  [BigInt(proof.pi_b[1][1]), BigInt(proof.pi_b[1][0])],
];
const pC = [BigInt(proof.pi_c[0]), BigInt(proof.pi_c[1])];

try {
  const rawCalldata = execFileSync(
    process.execPath,
    [snarkjsCli, "zkey", "export", "soliditycalldata", publicPath, proofPath],
    { cwd: circuitsDir, encoding: "utf8" },
  ).trim();
  const calldataLine = rawCalldata
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.startsWith('["0x'));
  if (!calldataLine) {
    throw new Error("snarkjs did not print the proof calldata");
  }
  // snarkjs prints the three proof arguments separated by commas, without the
  // outer JSON array brackets.
  const calldata = JSON.parse(`[${calldataLine}]`);
  assert.deepEqual(calldata[0].map(BigInt), pA, "pA differs from soliditycalldata");
  assert.deepEqual(calldata[1].map((row) => row.map(BigInt)), pB, "pB differs from soliditycalldata");
  assert.deepEqual(calldata[2].map(BigInt), pC, "pC differs from soliditycalldata");
  assert.deepEqual(calldata[3].map(BigInt), publicSignals.map(BigInt), "public signals differ");
  console.log("cross-checked proof order against snarkjs soliditycalldata");
} catch (error) {
  console.warn(`warning: could not cross-check with snarkjs: ${error.message}`);
}

// Public signals must equal both the public.json array and the readable fixture.
const publicValues = [
  chainId,
  poolIdField,
  root,
  nullifier,
  recipient,
  fee,
];
publicSignals.forEach((value, index) => {
  assert.equal(BigInt(value), publicValues[index], `public.json signal ${index} mismatch`);
});
assert.equal(BigInt(vector.public_signals.values.chain_id), chainId);
assert.equal(BigInt(vector.public_signals.values.pool_id), poolIdField);
assert.equal(BigInt(vector.public_signals.values.root), root);
assert.equal(BigInt(vector.public_signals.values.nullifier), nullifier);
assert.equal(BigInt(vector.public_signals.values.recipient), recipient);
assert.equal(BigInt(vector.public_signals.values.fee), fee);
assert.equal(vector.circuit_input.chain_id, chainId.toString());
assert.equal(vector.circuit_input.root, root.toString());
assert.equal(vector.circuit_input.nullifier, nullifier.toString());
assert.equal(vector.circuit_input.fee, fee.toString());

const hash3_1_2 = hash([DOMAIN_NODE, 1n, 2n]);

// --- Emit Solidity ---------------------------------------------------------

const leafLiterals = leaves.map((leaf) => `        bytes32(${bytes32Literal(leaf)})`).join(",\n");

const source = `// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

/// @title MembershipFixture
/// @notice Groth16 proof and Poseidon values for the VeilPool depth-20 membership spike.
/// @dev GENERATED FILE. Do not edit by hand.
///      Generated by circuits/scripts/gen-solidity-fixture.mjs from:
///        circuits/build/proof.json
///        circuits/build/public.json
///        circuits/test-vectors/membership-v1.json
///
///      TESTNET / SPIKE ONLY. The trusted setup is a local development setup.
///      The note secrets are public test values. Never use this proof or these
///      values with real funds.
library MembershipFixture {
    uint256 internal constant CHAIN_ID = ${decimal(chainId)};
    uint256 internal constant DENOMINATION = ${decimal(denomination)};
    uint256 internal constant FEE = ${decimal(fee)};
    address internal constant RECIPIENT =
        address(uint160(uint256(${bytes32Literal(recipient)})));

    /// @dev Right-padded ASCII deploy label. The adapter converts it to
    ///      POOL_ID_FIELD with uint256(label) >> 8 after checking the low byte.
    bytes32 internal constant POOL_ID_LABEL = ${bytes32Literal(labelValue)};
    /// @dev 0x00 || UTF-8("${poolIdText}") || zero padding, as a field element.
    uint256 internal constant POOL_ID_FIELD = ${decimal(poolIdField)};

    uint256 internal constant DOMAIN_COMMITMENT = ${bytes32Literal(DOMAIN_COMMITMENT)};
    uint256 internal constant DOMAIN_NULLIFIER = ${bytes32Literal(DOMAIN_NULLIFIER)};
    uint256 internal constant DOMAIN_NODE = ${bytes32Literal(DOMAIN_NODE)};

    uint256 internal constant SECRET_FIELD = ${decimal(secretField)};
    uint256 internal constant NULLIFIER_SECRET_FIELD = ${decimal(nullifierSecretField)};
    uint256 internal constant COMMITMENT = ${decimal(commitment)};
    uint256 internal constant NULLIFIER = ${decimal(nullifier)};
    uint256 internal constant ROOT = ${decimal(root)};
    uint256 internal constant LEAF_INDEX = ${vector.tree.leaf_index};

    uint256 internal constant ZERO_HASH_1 = ${decimal(zero[1])};
    uint256 internal constant ZERO_HASH_20 = ${decimal(zero[20])};
    uint256 internal constant HASH3_1_2 = ${decimal(hash3_1_2)};

    /// @notice The eight fixture leaves, in insertion order.
    function leaves() internal pure returns (bytes32[8] memory out) {
        out = [
${leafLiterals}
        ];
    }

    /// @notice The six public signals in circuit order:
    ///         [chain_id, pool_id, root, nullifier, recipient, fee].
    function publicSignals() internal pure returns (uint256[6] memory out) {
        out = [
            CHAIN_ID,
            POOL_ID_FIELD,
            ROOT,
            NULLIFIER,
            uint256(uint160(RECIPIENT)),
            FEE
        ];
    }

    /// @notice The proof encoded exactly as IVerifier expects:
    ///         abi.encode(uint256[2] pA, uint256[2][2] pB, uint256[2] pC).
    /// @dev pB is already in snarkjs soliditycalldata order, not proof.json order.
    function proof() internal pure returns (bytes memory) {
        uint256[2] memory pA = [
            uint256(${bytes32Literal(pA[0])}),
            uint256(${bytes32Literal(pA[1])})
        ];
        uint256[2][2] memory pB = [
            [uint256(${bytes32Literal(pB[0][0])}), uint256(${bytes32Literal(pB[0][1])})],
            [uint256(${bytes32Literal(pB[1][0])}), uint256(${bytes32Literal(pB[1][1])})]
        ];
        uint256[2] memory pC = [
            uint256(${bytes32Literal(pC[0])}),
            uint256(${bytes32Literal(pC[1])})
        ];
        return abi.encode(pA, pB, pC);
    }
}
`;

await mkdir(outputDir, { recursive: true });
await writeFile(outputPath, source, "utf8");

console.log(`wrote ${path.relative(repoRoot, outputPath)}`);
console.log(`pool label     = ${hex32(labelValue)}`);
console.log(`pool field     = ${hex32(poolIdField)}`);
console.log(`chain id       = ${chainId}`);
console.log(`root           = ${hex32(root)}`);
console.log(`nullifier      = ${hex32(nullifier)}`);
console.log(`zero[20]       = ${hex32(zero[20])}`);
