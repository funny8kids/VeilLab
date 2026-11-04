// Negative verification checks for the VeilPool membership circuit spike.
//
// Requires build/proof.json, build/public.json and build/verification_key.json
// from the commands in circuits/README.md.
//
// Usage: node scripts/verify-negative.mjs

import { readFile } from "node:fs/promises";
import { groth16 } from "snarkjs";

const proof = JSON.parse(await readFile("build/proof.json", "utf8"));
const publicSignals = JSON.parse(await readFile("build/public.json", "utf8"));
const vk = JSON.parse(await readFile("build/verification_key.json", "utf8"));

const FIELD_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function setSignal(signals, index, value) {
  const copy = clone(signals);
  copy[index] = value.toString(10);
  return copy;
}

async function verifyOrReject(candidateProof, candidateSignals) {
  try {
    return await groth16.verify(vk, candidateSignals, candidateProof);
  } catch {
    return false;
  }
}

const cases = [];
async function expect(label, expected, candidateProof, candidateSignals) {
  const actual = await verifyOrReject(candidateProof, candidateSignals);
  cases.push({ label, expected, actual, pass: actual === expected });
}

// Baseline: the untampered proof and public signals must verify.
await expect("baseline", true, proof, publicSignals);

// Public-signal tampering. Each must fail because the proof is bound to all six.
await expect("wrong chain_id", false, proof, setSignal(publicSignals, 0, BigInt(publicSignals[0]) + 1n));
await expect("wrong pool_id", false, proof, setSignal(publicSignals, 1, BigInt(publicSignals[1]) ^ 1n));
await expect("wrong root", false, proof, setSignal(publicSignals, 2, BigInt(publicSignals[2]) ^ 1n));
await expect("wrong nullifier", false, proof, setSignal(publicSignals, 3, BigInt(publicSignals[3]) ^ 1n));
await expect("wrong recipient", false, proof, setSignal(publicSignals, 4, BigInt(publicSignals[4]) + 1n));
await expect("wrong fee", false, proof, setSignal(publicSignals, 5, BigInt(publicSignals[5]) + 1n));

// Swapping two public signals must also fail.
const swapped = clone(publicSignals);
[swapped[2], swapped[3]] = [swapped[3], swapped[2]];
await expect("swapped root/nullifier", false, proof, swapped);

// A public signal outside the BN254 scalar field is rejected by the verifier.
await expect(
  "root >= field modulus",
  false,
  proof,
  setSignal(publicSignals, 2, FIELD_MODULUS),
);

// Proof tampering: change one G1 coordinate.
const tamperedProof = clone(proof);
tamperedProof.pi_a[0] = (BigInt(tamperedProof.pi_a[0]) + 1n).toString(10);
await expect("tampered proof (a.x + 1)", false, tamperedProof, publicSignals);

// Truncated proof (160-byte MockVerifier shape is not a Groth16 proof).
const truncatedProof = clone(proof);
truncatedProof.pi_c = [truncatedProof.pi_c[0]];
await expect("truncated proof", false, truncatedProof, publicSignals);

for (const item of cases) {
  const status = item.pass ? "PASS" : "FAIL";
  console.log(`${status}  ${item.label}: expected=${item.expected} actual=${item.actual}`);
}

const failed = cases.filter((item) => !item.pass);
if (failed.length > 0) {
  console.error(`${failed.length} negative check(s) failed`);
  process.exit(1);
}
console.log(`all ${cases.length} negative checks passed`);
process.exit(0);
