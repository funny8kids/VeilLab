// Produces the canonical (RFC 8785-style) form of the test vector.
//
// The data model contains only strings, booleans, integers and arrays, so a
// recursive lexicographic key sort plus JSON.stringify is sufficient here.
//
// Usage: node scripts/canonicalize.mjs

import { readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const inputPath = "test-vectors/membership-v1.json";
const outputPath = "test-vectors/membership-v1.canonical.json";
const hashPath = "test-vectors/membership-v1.canonical.sha256";

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = sortKeys(value[key]);
    return out;
  }
  return value;
}

const vector = JSON.parse(await readFile(inputPath, "utf8"));
const canonical = JSON.stringify(sortKeys(vector));
const digest = createHash("sha256").update(canonical, "utf8").digest("hex");

await writeFile(outputPath, canonical, "utf8");
await writeFile(hashPath, digest + "\n", "utf8");
console.log(`wrote ${outputPath}`);
console.log(`sha256(canonical) = ${digest}`);
