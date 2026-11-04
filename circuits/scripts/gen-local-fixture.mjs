// Generates a deterministic single-leaf proof fixture for local Anvil testing.
//
// This is NOT the canonical test vector and it does not replace
// `gen-fixture.mjs`. It produces a note whose commitment can be deposited as
// leaf 0 on a fresh local `VeilPoolPoseidon` pool, plus the witness input for
// the existing development zkey.
//
// Usage:
//   node scripts/gen-local-fixture.mjs
//   node node_modules/snarkjs/build/cli.cjs wtns calculate \
//     build/membership_js/membership.wasm build/local-input.json build/local.wtns
//   node node_modules/snarkjs/build/cli.cjs groth16 prove \
//     build/membership_0001.zkey build/local.wtns build/local-proof.json build/local-public.json
//   node node_modules/snarkjs/build/cli.cjs groth16 verify \
//     build/verification_key.json build/local-public.json build/local-proof.json

import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildPoseidon } from "circomlibjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..");
const build = path.join(repoRoot, "build");

const FIELD_MODULUS =
  21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const DEPTH = 20;
const CHAIN_ID = BigInt(process.env.VEILPOOL_LOCAL_CHAIN_ID || "31337");
const DENOMINATION = BigInt(
  process.env.VEILPOOL_LOCAL_DENOMINATION || "100000000000000000",
); // 0.1 ETH
const FEE = BigInt(process.env.VEILPOOL_LOCAL_FEE || "100000000000000"); // 0.0001 ETH
const RECIPIENT = BigInt(
  process.env.VEILPOOL_LOCAL_RECIPIENT || "0x000000000000000000000000000000000000dead",
);
const POOL_ID_TEXT = process.env.VEILPOOL_LOCAL_POOL_ID || "pool_eth_01";
const SECRET_SEED = process.env.VEILPOOL_LOCAL_SECRET_SEED || "v1";
const PRIOR_LEAVES = (process.env.VEILPOOL_LOCAL_PRIOR_LEAVES || "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const DOMAIN_COMMITMENT = 0x7665696c706f6f6c2d636f6d6d69742d7631n;
const DOMAIN_NULLIFIER = 0x7665696c706f6f6c2d6e756c6c2d7631n;
const DOMAIN_NODE = 0x7665696c706f6f6c2d6d65726b6c652d7631n;

const poseidon = await buildPoseidon();
const F = poseidon.F;

function hash(inputs) {
  return F.toObject(poseidon(inputs));
}

function sha256Raw(label) {
  return BigInt(
    "0x" + createHash("sha256").update(label, "utf8").digest("hex"),
  );
}

function hex32(value) {
  return "0x" + value.toString(16).padStart(64, "0");
}

function decimal(value) {
  return value.toString(10);
}

function encodePoolId(text) {
  const bytes = Buffer.from(text, "utf8");
  if (bytes.length === 0 || bytes.length > 31) {
    throw new Error("pool id must be 1..31 UTF-8 bytes");
  }
  const out = Buffer.alloc(32, 0);
  bytes.copy(out, 1);
  return BigInt("0x" + out.toString("hex"));
}

const poolId = encodePoolId(POOL_ID_TEXT);
const secret =
  sha256Raw(`veilpool-local-proof-secret-${SECRET_SEED}`) % FIELD_MODULUS;
const nullifierSecret =
  sha256Raw(`veilpool-local-proof-nullifier-secret-${SECRET_SEED}`) %
  FIELD_MODULUS;

const commitment = hash([
  DOMAIN_COMMITMENT,
  CHAIN_ID,
  poolId,
  DENOMINATION,
  secret,
  nullifierSecret,
]);
const nullifier = hash([
  DOMAIN_NULLIFIER,
  CHAIN_ID,
  poolId,
  commitment,
  nullifierSecret,
]);

const zero = [0n];
for (let level = 0; level < DEPTH; level++) {
  zero.push(hash([DOMAIN_NODE, zero[level], zero[level]]));
}

// Default: one leaf at index 0. Optional prior leaves append after the
// existing tree so a local pool with earlier deposits can be extended.
const prior = PRIOR_LEAVES.map((value) => BigInt(value));
const leafIndex = prior.length;
const leaves = [...prior, commitment];
const levels = [leaves];
for (let level = 0; level < DEPTH; level++) {
  const previous = levels[level];
  const next = [];
  const count = Math.ceil(previous.length / 2);
  for (let i = 0; i < count; i++) {
    const left = previous[2 * i] ?? zero[level];
    const right = previous[2 * i + 1] ?? zero[level];
    next.push(hash([DOMAIN_NODE, left, right]));
  }
  levels.push(next);
}
const root = levels[DEPTH][0];

const pathElements = [];
const pathIndices = [];
let cursor = leafIndex;
for (let level = 0; level < DEPTH; level++) {
  const siblingIndex = cursor ^ 1;
  pathElements.push(levels[level][siblingIndex] ?? zero[level]);
  pathIndices.push(cursor & 1);
  cursor >>= 1;
}

const input = {
  chain_id: decimal(CHAIN_ID),
  pool_id: decimal(poolId),
  root: decimal(root),
  nullifier: decimal(nullifier),
  recipient: decimal(RECIPIENT),
  fee: decimal(FEE),
  secret: decimal(secret),
  nullifier_secret: decimal(nullifierSecret),
  denomination: decimal(DENOMINATION),
  pathElements: pathElements.map(decimal),
  pathIndices: pathIndices.map(String),
};

const expected = {
  schema: "veilpool.zk.local-fixture.v1",
  status: "spike-testnet-only-not-production",
  chain_id: decimal(CHAIN_ID),
  pool_id_text: POOL_ID_TEXT,
  pool_id_label: "0x" + Buffer.from(POOL_ID_TEXT).toString("hex").padEnd(64, "0"),
  pool_id_field: hex32(poolId),
  denomination_wei: decimal(DENOMINATION),
  fee_wei: decimal(FEE),
  recipient: "0x000000000000000000000000000000000000dead",
  commitment: hex32(commitment),
  nullifier: hex32(nullifier),
  root: hex32(root),
  leaf_index: leafIndex,
  leaf_count: leaves.length,
  prior_leaves: prior.map(hex32),
  tree_depth: DEPTH,
  path_elements: pathElements.map(hex32),
  path_indices: pathIndices,
  note: {
    secret: hex32(secret),
    nullifier_secret: hex32(nullifierSecret),
  },
};

await mkdir(build, { recursive: true });
await writeFile(
  path.join(build, "local-input.json"),
  JSON.stringify(input, null, 2),
);
await writeFile(
  path.join(build, "local-expected.json"),
  JSON.stringify(expected, null, 2),
);

console.log("wrote build/local-input.json and build/local-expected.json");
console.log("commitment:", expected.commitment);
console.log("root:", expected.root);
console.log("nullifier:", expected.nullifier);
console.log("next: run wtns calculate / groth16 prove (see script header)");
