// Witness-level negative checks for the VeilPool membership circuit spike.
//
// A malformed witness must fail inside the circuit, not merely at the verifier.
// Requires build/membership_js/membership.wasm and build/input.json.
//
// Usage: node scripts/witness-negative.mjs

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const cli = "node_modules/snarkjs/build/cli.cjs";
const wasm = "build/membership_js/membership.wasm";
const baseInput = JSON.parse(await readFile("build/input.json", "utf8"));

await mkdir("build/negatives", { recursive: true });

function altered(mutate) {
  const copy = JSON.parse(JSON.stringify(baseInput));
  mutate(copy);
  return copy;
}

const cases = [
  ["baseline witness", (x) => x, true],
  ["wrong secret", (x) => (x.secret = (BigInt(x.secret) + 1n).toString()), false],
  ["wrong root", (x) => (x.root = (BigInt(x.root) + 1n).toString()), false],
  ["wrong nullifier", (x) => (x.nullifier = (BigInt(x.nullifier) + 1n).toString()), false],
  ["path index = 2", (x) => (x.pathIndices[0] = "2"), false],
  ["wrong path element", (x) => (x.pathElements[0] = (BigInt(x.pathElements[0]) ^ 1n).toString()), false],
  ["fee = 2^64", (x) => (x.fee = (1n << 64n).toString()), false],
  ["recipient = 2^160", (x) => (x.recipient = (1n << 160n).toString()), false],
  ["pool_id = 2^248", (x) => (x.pool_id = (1n << 248n).toString()), false],
  ["chain_id = 2^64", (x) => (x.chain_id = (1n << 64n).toString()), false],
  ["denomination = 0", (x) => (x.denomination = "0"), false],
];

const results = [];
for (const [label, mutate, shouldSucceed] of cases) {
  const slug = label.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  const inputPath = `build/negatives/${slug}.json`;
  const witnessPath = `build/negatives/${slug}.wtns`;
  await writeFile(inputPath, JSON.stringify(altered(mutate), null, 2) + "\n", "utf8");

  const run = spawnSync(
    process.execPath,
    [cli, "wtns", "calculate", wasm, inputPath, witnessPath],
    { encoding: "utf8" },
  );
  const succeeded = run.status === 0;
  results.push({ label, shouldSucceed, succeeded, pass: succeeded === shouldSucceed });
}

for (const item of results) {
  const status = item.pass ? "PASS" : "FAIL";
  console.log(
    `${status}  ${item.label}: expected=${item.shouldSucceed ? "accept" : "reject"} actual=${item.succeeded ? "accept" : "reject"}`,
  );
}

const failed = results.filter((item) => !item.pass);
if (failed.length > 0) {
  console.error(`${failed.length} witness negative check(s) failed`);
  process.exit(1);
}
console.log(`all ${results.length} witness negative checks passed`);
process.exit(0);
