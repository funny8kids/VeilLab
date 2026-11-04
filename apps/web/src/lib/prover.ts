import type { LocalWithdrawalRequest, ProofPathResponse } from "../types";
import { api } from "./api";
import type { NotePayloadV2 } from "./note";
import {
  DOMAIN_COMMITMENT,
  DOMAIN_NODE,
  DOMAIN_NULLIFIER,
  fieldFromHex,
  hash3,
  hash5,
  hash6,
  poolIdToField,
} from "./poseidon";

/** Default public paths. Vite serves these from apps/web/public/zk/. */
export const ZK_ARTIFACT_URLS = {
  wasmUrl: "/zk/membership.wasm",
  zkeyUrl: "/zk/membership.zkey",
  vkeyUrl: "/zk/verification_key.json",
} as const;

export const TREE_DEPTH = 20;
const MAX_UINT64 = (1n << 64n) - 1n;
const MAX_UINT256 = (1n << 256n) - 1n;
const DECIMAL_UINT = /^(0|[1-9][0-9]*)$/;
const HEX_32 = /^0x[0-9a-fA-F]{64}$/;
const HEX_20 = /^0x[0-9a-fA-F]{40}$/;
const HEX_PROOF = /^0x[0-9a-fA-F]{512}$/;

export type ProverStage = "loading" | "proving" | "verifying" | "done";

export type ProverErrorCode =
  | "NOTE_NOT_V2"
  | "NOTE_INVALID"
  | "PATH_INVALID"
  | "INPUT_INVALID"
  | "ARTIFACT_MISSING"
  | "PROVE_FAILED"
  | "VERIFY_FAILED"
  | "SIGNAL_MISMATCH"
  | "WORKER_UNAVAILABLE"
  | "WORKER_FAILED";

export class ProverError extends Error {
  code: ProverErrorCode;

  constructor(code: ProverErrorCode, message: string) {
    super(message);
    this.name = "ProverError";
    this.code = code;
  }
}

export interface Groth16Proof {
  pi_a: string[];
  pi_b: string[][];
  pi_c: string[];
  protocol?: string;
  curve?: string;
}

/** Circom witness input. Every field element is a decimal string. */
export interface WitnessInput {
  chain_id: string;
  pool_id: string;
  root: string;
  nullifier: string;
  recipient: string;
  fee: string;
  secret: string;
  nullifier_secret: string;
  denomination: string;
  pathElements: string[];
  pathIndices: string[];
  [key: string]: string | string[];
}

export interface ProverProgress {
  stage: ProverStage;
}

export interface ProverWorkerRequest {
  type: "prove";
  input: WitnessInput;
  wasmUrl: string;
  zkeyUrl: string;
  vkeyUrl: string;
}

export interface ProverErrorData {
  code: ProverErrorCode;
  message: string;
}

export type ProverWorkerResponse =
  | { type: "progress"; stage: ProverStage }
  | {
      type: "done";
      proof: Groth16Proof;
      publicSignals: string[];
      durationMs: number;
      verified: boolean;
    }
  | { type: "error"; error: ProverErrorData };

export interface ProveWithdrawalInput {
  note: NotePayloadV2;
  path: ProofPathResponse;
  recipient: string;
  feeWei: string;
  wasmUrl?: string;
  zkeyUrl?: string;
  vkeyUrl?: string;
  onProgress?: (stage: ProverStage) => void;
}

export interface ProveWithdrawalResult {
  /** 0x-prefixed 256-byte ABI Groth16 proof. */
  proofHex: string;
  /** Six public signals in circuit order, as decimal strings. */
  publicSignals: string[];
  durationMs: number;
  verified: boolean;
}

function fail(code: ProverErrorCode, message: string): never {
  throw new ProverError(code, message);
}

function parseNoteField(value: string, label: string): bigint {
  try {
    return fieldFromHex(value);
  } catch {
    return fail("NOTE_INVALID", `The note ${label} is not canonical.`);
  }
}

function parsePathField(value: string, label: string): bigint {
  try {
    return fieldFromHex(value);
  } catch {
    return fail("PATH_INVALID", `The path ${label} is not canonical.`);
  }
}

/**
 * The API's path `pool_id` is the deploy label, i.e. the same `bytes32` used on
 * chain: UTF-8(pool_id) || zero padding. That value can be >= the BN254
 * modulus, so it must not go through the field parser.
 */
function parseBytes32(value: string, label: string): bigint {
  if (typeof value !== "string" || !HEX_32.test(value)) {
    return fail("PATH_INVALID", `The path ${label} must be a bytes32 hex value.`);
  }
  return BigInt(value);
}

function parseDecimal(
  value: string,
  label: string,
  max: bigint,
  allowZero: boolean,
): bigint {
  if (typeof value !== "string" || !DECIMAL_UINT.test(value)) {
    return fail("INPUT_INVALID", `${label} must be a decimal integer string.`);
  }
  const parsed = BigInt(value);
  if ((!allowZero && parsed === 0n) || parsed > max) {
    return fail("INPUT_INVALID", `${label} is outside the allowed range.`);
  }
  return parsed;
}

function parseRecipient(value: string): bigint {
  const trimmed = value.trim().toLowerCase();
  if (!HEX_20.test(trimmed)) {
    return fail("INPUT_INVALID", "The recipient is not a 20-byte address.");
  }
  const parsed = BigInt(trimmed);
  if (parsed === 0n) {
    return fail("INPUT_INVALID", "The recipient must be non-zero.");
  }
  return parsed;
}

function leafIndexBits(leafIndex: number): number[] {
  if (!Number.isSafeInteger(leafIndex) || leafIndex < 0) {
    return fail("PATH_INVALID", "The path leaf index is invalid.");
  }
  const bits: number[] = [];
  let remaining = leafIndex;
  for (let level = 0; level < TREE_DEPTH; level += 1) {
    bits.push(remaining % 2);
    remaining = Math.floor(remaining / 2);
  }
  if (remaining !== 0) {
    return fail("PATH_INVALID", "The path leaf index exceeds the tree depth.");
  }
  return bits;
}

function merkleRoot(
  commitment: bigint,
  elements: readonly bigint[],
  indices: readonly number[],
): bigint {
  let current = commitment;
  for (let level = 0; level < TREE_DEPTH; level += 1) {
    const sibling = elements[level];
    const currentIsLeft = indices[level] === 0;
    current = hash3(
      DOMAIN_NODE,
      currentIsLeft ? current : sibling,
      currentIsLeft ? sibling : current,
    );
  }
  return current;
}

/**
 * Builds the exact Circom witness for the membership circuit.
 *
 * Public inputs: chain_id, pool_id (field), root, nullifier, recipient, fee.
 * Private inputs: secret, nullifier_secret, denomination, pathElements,
 * pathIndices. All values are decimal strings for snarkjs.
 *
 * The note is validated against its own commitment/nullifier, and the supplied
 * path is re-hashed locally. The witness never leaves the browser.
 */
export function buildWitnessInput(
  note: NotePayloadV2,
  path: ProofPathResponse,
  recipient: string,
  feeWei: string,
): WitnessInput {
  if (!note || note.v !== 2) {
    return fail(
      "NOTE_NOT_V2",
      "This note is not a ZK note. Regenerate it in local mode.",
    );
  }

  if (
    !Number.isSafeInteger(note.chainId) ||
    note.chainId < 0 ||
    BigInt(note.chainId) > MAX_UINT64
  ) {
    return fail("NOTE_INVALID", "The note chain id is outside uint64.");
  }
  const chainId = BigInt(note.chainId);

  let expectedPoolField: bigint;
  try {
    expectedPoolField = poolIdToField(note.poolId);
  } catch {
    return fail("NOTE_INVALID", "The note pool id cannot be encoded.");
  }
  const poolIdField = parseNoteField(note.poolIdField, "pool id field");
  if (poolIdField !== expectedPoolField) {
    return fail(
      "NOTE_INVALID",
      "The note pool id field does not match its pool id.",
    );
  }

  const denomination = parseDecimal(
    note.denominationWei,
    "The note denomination",
    MAX_UINT64,
    false,
  );
  const secret = parseNoteField(note.secret, "secret");
  const nullifierSecret = parseNoteField(
    note.nullifierSecret,
    "nullifier secret",
  );
  if (secret === 0n || nullifierSecret === 0n) {
    return fail("NOTE_INVALID", "The note secrets must be non-zero.");
  }

  const commitment = parseNoteField(note.commitment, "commitment");
  const expectedCommitment = hash6(
    DOMAIN_COMMITMENT,
    chainId,
    poolIdField,
    denomination,
    secret,
    nullifierSecret,
  );
  if (commitment !== expectedCommitment) {
    return fail(
      "NOTE_INVALID",
      "The note commitment does not match its contents.",
    );
  }

  const nullifier = parseNoteField(note.nullifier, "nullifier");
  const expectedNullifier = hash5(
    DOMAIN_NULLIFIER,
    chainId,
    poolIdField,
    commitment,
    nullifierSecret,
  );
  if (nullifier !== expectedNullifier) {
    return fail(
      "NOTE_INVALID",
      "The note nullifier does not match its contents.",
    );
  }

  if (!path || !Array.isArray(path.path_elements) || !Array.isArray(path.path_indices)) {
    return fail("PATH_INVALID", "The Merkle path is missing.");
  }
  if (path.tree_depth !== TREE_DEPTH) {
    return fail("PATH_INVALID", `The Merkle path depth must be ${TREE_DEPTH}.`);
  }
  if (
    path.path_elements.length !== TREE_DEPTH ||
    path.path_indices.length !== TREE_DEPTH
  ) {
    return fail("PATH_INVALID", `The Merkle path must have ${TREE_DEPTH} levels.`);
  }

  const pathCommitment = parsePathField(path.commitment, "commitment");
  if (pathCommitment !== commitment) {
    return fail(
      "PATH_INVALID",
      "The Merkle path commitment does not match the note.",
    );
  }

  if (
    path.chain_id !== undefined &&
    (!Number.isSafeInteger(path.chain_id) ||
      path.chain_id < 0 ||
      BigInt(path.chain_id) !== chainId)
  ) {
    return fail("PATH_INVALID", "The Merkle path chain id does not match the note.");
  }

  // The live API returns both `pool_key` ("pool_eth_01") and `pool_id` as the
  // right-padded deploy label (0x706f6f6c...0000), which is NOT the circuit's
  // zero-prefixed field (0x00706f6f...). Prefer the text key. When it is
  // absent, accept the deploy label only if shifting out its zero low byte
  // reproduces the note's field. Also tolerate an API that already returns the
  // canonical zero-prefixed field.
  if (typeof path.pool_key === "string" && path.pool_key.length > 0) {
    if (path.pool_key !== note.poolId) {
      return fail(
        "PATH_INVALID",
        "The Merkle path pool key does not match the note.",
      );
    }
  } else if (path.pool_id !== undefined) {
    const pathPoolId = parseBytes32(path.pool_id, "pool id");
    const isCanonicalField = pathPoolId === poolIdField;
    const isDeployLabel =
      (pathPoolId & 0xffn) === 0n && pathPoolId >> 8n === poolIdField;
    if (!isCanonicalField && !isDeployLabel) {
      return fail(
        "PATH_INVALID",
        "The Merkle path pool id does not match the note.",
      );
    }
  }

  const pathIndices = path.path_indices.map((value) => {
    if (value !== 0 && value !== 1) {
      return fail("PATH_INVALID", "The Merkle path indices must be 0 or 1.");
    }
    return value;
  });
  if (path.leaf_index !== undefined) {
    const expectedBits = leafIndexBits(path.leaf_index);
    if (expectedBits.some((bit, level) => bit !== pathIndices[level])) {
      return fail(
        "PATH_INVALID",
        "The Merkle path indices do not match the leaf index.",
      );
    }
  }

  const pathElements = path.path_elements.map((value, level) =>
    parsePathField(value, `element ${level}`),
  );
  const root = parsePathField(path.root, "root");
  const computedRoot = merkleRoot(commitment, pathElements, pathIndices);
  if (computedRoot !== root) {
    return fail(
      "PATH_INVALID",
      "The supplied Merkle path does not produce the supplied root.",
    );
  }

  const recipientField = parseRecipient(recipient);
  const fee = parseDecimal(feeWei, "The relayer fee", MAX_UINT64, true);

  return {
    chain_id: chainId.toString(),
    pool_id: poolIdField.toString(),
    root: root.toString(),
    nullifier: nullifier.toString(),
    recipient: recipientField.toString(),
    fee: fee.toString(),
    secret: secret.toString(),
    nullifier_secret: nullifierSecret.toString(),
    denomination: denomination.toString(),
    pathElements: pathElements.map((value) => value.toString()),
    pathIndices: pathIndices.map((value) => value.toString()),
  };
}

export function publicSignalsFromWitness(input: WitnessInput): string[] {
  return [
    input.chain_id,
    input.pool_id,
    input.root,
    input.nullifier,
    input.recipient,
    input.fee,
  ];
}

function proofCoordinate(value: unknown, label: string): string {
  if (typeof value !== "string" && typeof value !== "number") {
    return fail("INPUT_INVALID", `The proof ${label} is missing.`);
  }
  const text = String(value).trim();
  if (!/^(0x[0-9a-fA-F]+|[0-9]+)$/.test(text)) {
    return fail("INPUT_INVALID", `The proof ${label} is not an integer.`);
  }
  const parsed = BigInt(text);
  if (parsed < 0n || parsed > MAX_UINT256) {
    return fail("INPUT_INVALID", `The proof ${label} is outside uint256.`);
  }
  return parsed.toString(16).padStart(64, "0");
}

/**
 * Encodes a snarkjs Groth16 proof as the verifier's 256-byte ABI layout:
 * a.x || a.y || b00 || b01 || b10 || b11 || c.x || c.y.
 *
 * The pB coordinates are swapped exactly like `snarkjs zkey export
 * soliditycalldata` (and the local-proof-hex fixture):
 * b00 = pi_b[0][1], b01 = pi_b[0][0], b10 = pi_b[1][1], b11 = pi_b[1][0].
 */
export function encodeProofHex(proof: Groth16Proof): string {
  if (
    !proof ||
    !Array.isArray(proof.pi_a) ||
    !Array.isArray(proof.pi_b) ||
    !Array.isArray(proof.pi_c) ||
    proof.pi_a.length < 2 ||
    proof.pi_b.length < 2 ||
    !Array.isArray(proof.pi_b[0]) ||
    !Array.isArray(proof.pi_b[1]) ||
    proof.pi_b[0].length < 2 ||
    proof.pi_b[1].length < 2 ||
    proof.pi_c.length < 2
  ) {
    return fail("INPUT_INVALID", "The Groth16 proof is malformed.");
  }

  const words = [
    proofCoordinate(proof.pi_a[0], "a.x"),
    proofCoordinate(proof.pi_a[1], "a.y"),
    proofCoordinate(proof.pi_b[0][1], "b00"),
    proofCoordinate(proof.pi_b[0][0], "b01"),
    proofCoordinate(proof.pi_b[1][1], "b10"),
    proofCoordinate(proof.pi_b[1][0], "b11"),
    proofCoordinate(proof.pi_c[0], "c.x"),
    proofCoordinate(proof.pi_c[1], "c.y"),
  ];
  return `0x${words.join("")}`;
}

function signalsMatch(actual: string[], expected: string[]): boolean {
  if (actual.length !== expected.length) return false;
  return actual.every((value, index) => {
    try {
      return BigInt(value) === BigInt(expected[index]);
    } catch {
      return false;
    }
  });
}

/**
 * Runs the local Groth16 proof in a dedicated Web Worker and returns only the
 * encoded proof and public signals. The note and witness stay in the worker.
 */
export async function proveWithdrawal(
  input: ProveWithdrawalInput,
): Promise<ProveWithdrawalResult> {
  const witness = buildWitnessInput(
    input.note,
    input.path,
    input.recipient,
    input.feeWei,
  );
  const expectedSignals = publicSignalsFromWitness(witness);
  const startedAt = performance.now();

  if (typeof Worker === "undefined") {
    return fail(
      "WORKER_UNAVAILABLE",
      "This browser does not provide Web Workers.",
    );
  }

  let worker: Worker;
  try {
    worker = new Worker(new URL("../workers/prover.worker.ts", import.meta.url), {
      type: "module",
      name: "veilpool-groth16-prover",
    });
  } catch {
    return fail("WORKER_UNAVAILABLE", "The prover worker could not be started.");
  }

  try {
    const result = await new Promise<Extract<ProverWorkerResponse, { type: "done" }>>(
      (resolve, reject) => {
        worker.onmessage = (event: MessageEvent<ProverWorkerResponse>) => {
          const message = event.data;
          if (!message) return;
          if (message.type === "progress") {
            input.onProgress?.(message.stage);
            return;
          }
          if (message.type === "error") {
            reject(
              new ProverError(message.error.code, message.error.message),
            );
            return;
          }
          if (message.type === "done") {
            resolve(message);
          }
        };
        worker.onerror = () => {
          reject(
            new ProverError("WORKER_FAILED", "The local prover worker failed."),
          );
        };
        worker.onmessageerror = () => {
          reject(
            new ProverError(
              "WORKER_FAILED",
              "The prover worker returned an unreadable message.",
            ),
          );
        };

        worker.postMessage({
          type: "prove",
          input: witness,
          wasmUrl: input.wasmUrl || ZK_ARTIFACT_URLS.wasmUrl,
          zkeyUrl: input.zkeyUrl || ZK_ARTIFACT_URLS.zkeyUrl,
          vkeyUrl: input.vkeyUrl || ZK_ARTIFACT_URLS.vkeyUrl,
        } satisfies ProverWorkerRequest);
      },
    );

    if (!result.verified) {
      return fail(
        "VERIFY_FAILED",
        "The generated proof did not verify against the local verification key.",
      );
    }
    if (!signalsMatch(result.publicSignals, expectedSignals)) {
      return fail(
        "SIGNAL_MISMATCH",
        "The prover returned public signals that do not match the witness.",
      );
    }

    const proofHex = encodeProofHex(result.proof);
    const durationMs =
      Number.isFinite(result.durationMs) && result.durationMs >= 0
        ? result.durationMs
        : performance.now() - startedAt;
    input.onProgress?.("done");
    return {
      proofHex,
      publicSignals: result.publicSignals,
      durationMs,
      verified: true,
    };
  } finally {
    worker.terminate();
  }
}

/** Fetches the public Merkle path through the API proxy. */
export function proofPath(
  poolId: string,
  commitment: string,
): Promise<ProofPathResponse> {
  return api.proofPath(poolId, commitment);
}

/**
 * Builds the local withdrawal body from an explicit whitelist. Extra properties
 * on the input object are ignored; no note or witness field can be included.
 */
export function buildLocalWithdrawalRequest(input: {
  quoteId: string;
  proof: string;
  root: string;
  nullifier: string;
  recipient: string;
  feeWei: string;
}): LocalWithdrawalRequest {
  if (typeof input.quoteId !== "string" || input.quoteId.trim().length === 0) {
    return fail("INPUT_INVALID", "A quote id is required.");
  }
  if (!HEX_PROOF.test(input.proof)) {
    return fail("INPUT_INVALID", "The proof must be 256 bytes of 0x hex.");
  }
  if (!HEX_32.test(input.root) || !HEX_32.test(input.nullifier)) {
    return fail(
      "INPUT_INVALID",
      "The root and nullifier must be 32-byte 0x hex values.",
    );
  }
  const recipient = input.recipient.trim().toLowerCase();
  if (!HEX_20.test(recipient)) {
    return fail("INPUT_INVALID", "The recipient is not a 20-byte address.");
  }
  parseDecimal(input.feeWei, "The relayer fee", MAX_UINT64, true);

  return {
    quote_id: input.quoteId,
    proof: input.proof,
    root: input.root,
    nullifier: input.nullifier,
    recipient,
    relayer_fee_wei: input.feeWei,
  };
}
