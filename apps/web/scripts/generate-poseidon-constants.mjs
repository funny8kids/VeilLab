#!/usr/bin/env node
// Generates the browser-local Poseidon constants used by src/lib/poseidon.ts.
//
// Source of truth:
//   circuits/node_modules/circomlibjs/src/poseidon_constants.json
//   (circomlibjs 0.1.7; the same parameters as circomlib 2.0.5 Poseidon)
//
// Only the state widths the web app uses are emitted:
//   Poseidon(3) -> t = 4  (Merkle nodes)
//   Poseidon(5) -> t = 6  (nullifier)
//   Poseidon(6) -> t = 7  (commitment)
//
// The constants are converted to canonical 0x-prefixed 32-byte field elements
// so the generated TypeScript does not contain a second, decimal encoding.
//
// Usage (from apps/web):
//   node scripts/generate-poseidon-constants.mjs
//   npm.cmd run generate:poseidon
//
// Do not edit src/lib/poseidonConstants.ts by hand.

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const FIELD_MODULUS =
  21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const N_ROUNDS_F = 8;
// circomlib/circomlibjs N_ROUNDS_P, indexed by t - 2 (t = inputs + 1).
const N_ROUNDS_P = [56, 57, 56, 60, 60, 63, 64, 63, 60, 66, 60, 65, 70, 60, 64, 68];

const STATE_WIDTHS = [4, 6, 7];

const scriptDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(scriptDir, "..");
const repoRoot = resolve(webRoot, "..", "..");
const sourcePath = resolve(
  repoRoot,
  "circuits",
  "node_modules",
  "circomlibjs",
  "src",
  "poseidon_constants.json",
);
const outputPath = resolve(webRoot, "src", "lib", "poseidonConstants.ts");

function hex32(value, label) {
  const parsed = BigInt(value);
  if (parsed < 0n || parsed >= FIELD_MODULUS) {
    throw new Error(`${label} is outside the BN254 scalar field`);
  }
  return `0x${parsed.toString(16).padStart(64, "0")}`;
}

function formatValues(values) {
  const lines = [];
  for (let index = 0; index < values.length; index += 4) {
    lines.push(
      `    ${values
        .slice(index, index + 4)
        .map((value) => `"${value}"`)
        .join(", ")},`,
    );
  }
  return lines.join("\n");
}

let sourceBytes;
try {
  sourceBytes = await readFile(sourcePath);
} catch {
  throw new Error(
    `Poseidon constants not found at ${sourcePath}. Run "npm.cmd install" in circuits/ first.`,
  );
}

const sourceHash = createHash("sha256").update(sourceBytes).digest("hex");
const raw = JSON.parse(sourceBytes.toString("utf8"));
if (!Array.isArray(raw?.C) || !Array.isArray(raw?.M)) {
  throw new Error("poseidon_constants.json does not contain C and M arrays.");
}

const cRows = {};
const mRows = {};

for (const t of STATE_WIDTHS) {
  const index = t - 2;
  const rounds = N_ROUNDS_F + N_ROUNDS_P[index];
  const sourceC = raw.C[index];
  const sourceM = raw.M[index];

  if (!Array.isArray(sourceC) || sourceC.length !== rounds * t) {
    throw new Error(
      `C[${index}] has ${sourceC?.length} values, expected ${rounds * t}.`,
    );
  }
  if (!Array.isArray(sourceM) || sourceM.length !== t) {
    throw new Error(`M[${index}] has ${sourceM?.length} rows, expected ${t}.`);
  }

  cRows[t] = sourceC.map((value, position) =>
    hex32(value, `C[${index}][${position}]`),
  );
  mRows[t] = sourceM.map((row, rowIndex) => {
    if (!Array.isArray(row) || row.length !== t) {
      throw new Error(`M[${index}][${rowIndex}] must have ${t} values.`);
    }
    return row.map((value, columnIndex) =>
      hex32(value, `M[${index}][${rowIndex}][${columnIndex}]`),
    );
  });
}

const lines = [
  "// AUTO-GENERATED FILE. Do not edit by hand.",
  "//",
  "// Poseidon round constants and MDS matrices for BN254, matching circomlib",
  "// 2.0.5 / circomlibjs. Generated from:",
  "//   circuits/node_modules/circomlibjs/src/poseidon_constants.json",
  `// Source SHA-256: ${sourceHash}`,
  "//",
  "// Included state widths:",
  "//   t = 4 -> Poseidon(3) (Merkle node hash)",
  "//   t = 6 -> Poseidon(5) (nullifier)",
  "//   t = 7 -> Poseidon(6) (commitment)",
  "//",
  "// Regenerate from apps/web with:",
  "//   npm.cmd run generate:poseidon",
  "",
  "export const POSEIDON_C: Readonly<Record<number, readonly string[]>> = {",
];

for (const t of STATE_WIDTHS) {
  lines.push(`  ${t}: [`, formatValues(cRows[t]), "  ],");
}
lines.push("};", "");

lines.push(
  "export const POSEIDON_M: Readonly<",
  "  Record<number, readonly (readonly string[])[]>",
  "> = {",
);
for (const t of STATE_WIDTHS) {
  lines.push(`  ${t}: [`);
  for (const row of mRows[t]) {
    lines.push("    [", formatValues(row), "    ],");
  }
  lines.push("  ],");
}
lines.push("};", "");

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, lines.join("\n"), "utf8");

console.log(
  `wrote ${outputPath} (${STATE_WIDTHS.map((t) => `t=${t}`).join(", ")})`,
);
console.log(`source sha256 ${sourceHash}`);
