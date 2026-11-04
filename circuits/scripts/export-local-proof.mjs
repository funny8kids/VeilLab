// Converts a snarkjs proof into the 256-byte ABI encoding expected by
// `Groth16VerifierAdapter` / `IVerifier`.
//
// The adapter expects:
//   abi.encode(uint256[2] pA, uint256[2][2] pB, uint256[2] pC)
//
// snarkjs's Solidity verifier swaps the two coordinates inside each pB pair;
// this script follows `snarkjs zkey export soliditycalldata` ordering.
//
// TESTNET / SPIKE ONLY. The development zkey is not a ceremony.

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const build = path.resolve(here, "..", "build");

const proof = JSON.parse(await readFile(path.join(build, "local-proof.json"), "utf8"));
const publicSignals = JSON.parse(
  await readFile(path.join(build, "local-public.json"), "utf8"),
);

function word(value) {
  const bigint = BigInt(value);
  if (bigint < 0n) throw new Error("negative field element");
  return bigint.toString(16).padStart(64, "0");
}

const pA = [proof.pi_a[0], proof.pi_a[1]];
const pB = [
  [proof.pi_b[0][1], proof.pi_b[0][0]],
  [proof.pi_b[1][1], proof.pi_b[1][0]],
];
const pC = [proof.pi_c[0], proof.pi_c[1]];

const words = [...pA, ...pB.flat(), ...pC];
const encoded = "0x" + words.map(word).join("");
if (encoded.length !== 2 + 64 * 8) {
  throw new Error("encoded proof is not 256 bytes");
}

const result = {
  schema: "veilpool.zk.local-proof.v1",
  warning: "development zkey; local spike only; not audited",
  proof: encoded,
  public_signals: publicSignals,
  proof_length_bytes: 256,
};

await writeFile(
  path.join(build, "local-proof-hex.json"),
  JSON.stringify(result, null, 2),
);
console.log("wrote build/local-proof-hex.json");
console.log("proof bytes:", encoded.length / 2 - 1);
console.log("public signals:", publicSignals.join(", "));
