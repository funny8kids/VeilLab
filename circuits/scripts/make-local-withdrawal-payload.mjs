// Builds the JSON body for POST /api/v1/local/withdrawals from the local
// chain-31337 proof fixture.
//
// Usage:
//   $env:VEILPOOL_QUOTE_ID = "quote_..."
//   $env:VEILPOOL_LOCAL_FEE = "240000000000000"
//   $env:VEILPOOL_LOCAL_RECIPIENT = "0x000000000000000000000000000000000000dead"
//   node scripts/make-local-withdrawal-payload.mjs
//
// The generated file is local test data. It contains only public proof data,
// never the note secrets or witness.

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const build = path.resolve(here, "..", "build");

const proof = JSON.parse(
  await readFile(path.join(build, "local-proof-hex.json"), "utf8"),
);
const expected = JSON.parse(
  await readFile(path.join(build, "local-expected.json"), "utf8"),
);

const quoteId = process.env.VEILPOOL_QUOTE_ID;
if (!quoteId) throw new Error("VEILPOOL_QUOTE_ID is required");

const recipient =
  process.env.VEILPOOL_LOCAL_RECIPIENT || expected.recipient;
const fee = process.env.VEILPOOL_LOCAL_FEE || expected.fee_wei;

const body = {
  quote_id: quoteId,
  proof: proof.proof,
  root: expected.root,
  nullifier: expected.nullifier,
  recipient,
  relayer_fee_wei: fee,
};

await writeFile(
  path.join(build, "local-withdrawal-request.json"),
  JSON.stringify(body, null, 2),
);
console.log("wrote build/local-withdrawal-request.json");
console.log(JSON.stringify(body, null, 2));
