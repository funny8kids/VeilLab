// Copies the local Circom/Groth16 artifacts into the web app's public folder
// so the browser prover can load them without a server-side proving call.
//
// TESTNET / SPIKE ONLY. The zkey is a single-machine development setup, not a
// ceremony. Run this only for a local demo.
//
// Usage: node scripts/export-web-artifacts.mjs

import { cp, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..");
const source = path.join(repo, "circuits", "build");
const target = path.join(repo, "apps", "web", "public", "zk");

const artifacts = [
  ["membership_js/membership.wasm", "membership.wasm"],
  ["membership_0001.zkey", "membership.zkey"],
  ["verification_key.json", "verification_key.json"],
];

await mkdir(target, { recursive: true });

for (const [from, to] of artifacts) {
  const fromPath = path.join(source, from);
  const toPath = path.join(target, to);
  await stat(fromPath).catch(() => {
    throw new Error(
      `Missing ${fromPath}. Compile the circuit and create the final zkey first (see circuits/README.md).`,
    );
  });
  await cp(fromPath, toPath);
  const size = (await stat(toPath)).size;
  console.log(`copied ${to} (${(size / 1024 / 1024).toFixed(1)} MiB)`);
}

console.log(`web ZK artifacts ready in ${target}`);
console.log("These files are local demo artifacts. Do not deploy them as production keys.");
