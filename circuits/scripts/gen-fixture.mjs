// Generates the deterministic test vector for the VeilPool membership circuit.
//
// TESTNET / SPIKE ONLY. This script uses circomlibjs, which must produce the same
// Poseidon values as circomlib's Poseidon template. Run `npm install` first.
//
// Usage: node scripts/gen-fixture.mjs

import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { buildPoseidon } from "circomlibjs";

const FIELD_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const DEPTH = 20;
const CHAIN_ID = 11155111n; // Sepolia
const DENOMINATION = 100000000000000000n; // 0.1 ETH in wei
const FEE = 100000000000000n; // 0.0001 ETH relayer fee
const RECIPIENT = 0x000000000000000000000000000000000000deadn;
const LEAF_INDEX = 5;
const TARGET_POOL_ID_TEXT = "pool_eth_01";

const DOMAIN_COMMITMENT = 0x7665696c706f6f6c2d636f6d6d69742d7631n;
const DOMAIN_NULLIFIER = 0x7665696c706f6f6c2d6e756c6c2d7631n;
const DOMAIN_NODE = 0x7665696c706f6f6c2d6d65726b6c652d7631n;

const poseidon = await buildPoseidon();
const F = poseidon.F;

function hash(inputs) {
  return F.toObject(poseidon(inputs));
}

function sha256Raw(label) {
  const digest = createHash("sha256").update(label, "utf8").digest("hex");
  return BigInt("0x" + digest);
}

function hex32(value) {
  return "0x" + value.toString(16).padStart(64, "0");
}

function decimal(value) {
  return value.toString(10);
}

// Canonical pool ID encoding: one zero byte, then the UTF-8 pool ID (max 31
// bytes), then zero padding. This guarantees the field element is < 2^248.
function encodePoolId(text) {
  const bytes = Buffer.from(text, "utf8");
  if (bytes.length > 31) throw new Error("pool id must be at most 31 UTF-8 bytes");
  const out = Buffer.alloc(32, 0);
  bytes.copy(out, 1);
  return BigInt("0x" + out.toString("hex"));
}

const poolId = encodePoolId(TARGET_POOL_ID_TEXT);

// Note secrets are 32 CSPRNG bytes. They are reduced modulo the BN254 scalar
// field before use in the circuit, because a uniform 256-bit value is not
// necessarily a canonical field element. The reduction is defined in the spec.
// Force the high byte of `secret` to 0xff so the fixture exercises the
// reduction path (the raw value is > the BN254 scalar field). The nullifier
// secret is left as a raw SHA-256 value and may or may not need reduction.
const secretBytes = sha256Raw("veilpool-spike-secret-v1") | (0xffn << 248n);
const nullifierSecretBytes = sha256Raw("veilpool-spike-nullifier-secret-v1");
const secret = secretBytes % FIELD_MODULUS;
const nullifierSecret = nullifierSecretBytes % FIELD_MODULUS;

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

// Empty subtree roots: zero[0] = 0, zero[i+1] = Poseidon(DOMAIN_NODE, zero[i], zero[i]).
const zero = [0n];
for (let level = 0; level < DEPTH; level++) {
  zero.push(hash([DOMAIN_NODE, zero[level], zero[level]]));
}

// Eight deterministic leaves; leaf 5 is the real note commitment. The other
// leaves are arbitrary field elements and are not spendable notes.
const leaves = [];
for (let i = 0; i < 8; i++) {
  leaves.push(i === LEAF_INDEX ? commitment : hash([0xdeadbeefn, BigInt(i)]));
}

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
let cursor = LEAF_INDEX;
for (let level = 0; level < DEPTH; level++) {
  const siblingIndex = cursor ^ 1;
  pathElements.push(levels[level][siblingIndex] ?? zero[level]);
  pathIndices.push(cursor & 1);
  cursor >>= 1;
}

// Sanity check: recompute the root from the path exactly as the circuit does.
let currentNode = commitment;
for (let level = 0; level < DEPTH; level++) {
  const isRight = pathIndices[level] === 1;
  const left = isRight ? pathElements[level] : currentNode;
  const right = isRight ? currentNode : pathElements[level];
  currentNode = hash([DOMAIN_NODE, left, right]);
}
if (currentNode !== root) {
  throw new Error("path does not recompute the expected root");
}

const circuitInput = {
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

const vector = {
  schema: "veilpool.zk.membership.v1",
  status: "spike-testnet-only-not-production",
  description:
    "Deterministic depth-20 Poseidon membership fixture. Public signals are listed in verifier order.",
  hash: {
    commitment: "Poseidon(6) over circomlib 2.0.5",
    nullifier: "Poseidon(5) over circomlib 2.0.5",
    merkleNode: "Poseidon(3) over circomlib 2.0.5",
  },
  domain: {
    commitment: hex32(DOMAIN_COMMITMENT),
    nullifier: hex32(DOMAIN_NULLIFIER),
    merkleNode: hex32(DOMAIN_NODE),
  },
  note: {
    chain_id: decimal(CHAIN_ID),
    pool_id_text: TARGET_POOL_ID_TEXT,
    pool_id: hex32(poolId),
    denomination: decimal(DENOMINATION),
    secret_bytes: hex32(secretBytes),
    secret_field: hex32(secret),
    nullifier_secret_bytes: hex32(nullifierSecretBytes),
    nullifier_secret_field: hex32(nullifierSecret),
    secret_encoding: "uint256(secret_bytes) mod BN254_SCALAR_FIELD",
    nullifier_secret_encoding: "uint256(nullifier_secret_bytes) mod BN254_SCALAR_FIELD",
  },
  derived: {
    commitment: hex32(commitment),
    nullifier: hex32(nullifier),
  },
  tree: {
    depth: DEPTH,
    leaf_index: LEAF_INDEX,
    leaves: leaves.map(hex32),
    path_elements: pathElements.map(hex32),
    path_indices: pathIndices,
    root: hex32(root),
  },
  public_signals: {
    order: ["chain_id", "pool_id", "root", "nullifier", "recipient", "fee"],
    values: {
      chain_id: decimal(CHAIN_ID),
      pool_id: hex32(poolId),
      root: hex32(root),
      nullifier: hex32(nullifier),
      recipient: "0x000000000000000000000000000000000000dead",
      fee: decimal(FEE),
    },
  },
  circuit_input: circuitInput,
};

await mkdir("build", { recursive: true });
await mkdir("test-vectors", { recursive: true });
await writeFile("build/input.json", JSON.stringify(circuitInput, null, 2) + "\n", "utf8");
// snarkjs expects decimal strings in public.json; keep the same encoding here.
const publicSignalValues = [CHAIN_ID, poolId, root, nullifier, RECIPIENT, FEE].map(decimal);
await writeFile("build/public.json", JSON.stringify(publicSignalValues, null, 2) + "\n", "utf8");
await writeFile("test-vectors/membership-v1.json", JSON.stringify(vector, null, 2) + "\n", "utf8");

console.log("commitment =", hex32(commitment));
console.log("nullifier  =", hex32(nullifier));
console.log("root       =", hex32(root));
console.log("leaf index =", LEAF_INDEX);
console.log("path bits  =", pathIndices.join(""));
console.log("wrote build/input.json, build/public.json, test-vectors/membership-v1.json");
