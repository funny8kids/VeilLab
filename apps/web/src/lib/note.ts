import type { Pool } from "../types";
import { denominationWei } from "./format";
import {
  DOMAIN_COMMITMENT,
  DOMAIN_NULLIFIER,
  FIELD_MODULUS,
  fieldFromHex,
  fieldToHex32,
  hash5,
  hash6,
  poolIdToField,
} from "./poseidon";

export const NOTE_PREFIX = "veilnote1";
export const NOTE_PREFIX_V2 = "veilnote2";

export type NoteErrorCode = "NOTE_INVALID" | "NOTE_CHECKSUM" | "NOTE_VERSION";

export class NoteError extends Error {
  code: NoteErrorCode;

  constructor(code: NoteErrorCode, message: string) {
    super(message);
    this.name = "NoteError";
    this.code = code;
  }
}

/** Legacy demo/mock note. Its commitment is SHA-256, not circuit-compatible. */
export interface NotePayloadV1 {
  v: 1;
  id: string;
  poolId: string;
  asset: string;
  denomination: string;
  secret: string;
  nullifierSecret: string;
  commitment: string;
  createdAt: string;
}

/**
 * Circuit-compatible note. Every 0x field value is a canonical BN254 scalar.
 * `secret` and `nullifierSecret` are the CSPRNG values already reduced mod p.
 */
export interface NotePayloadV2 {
  v: 2;
  id: string;
  chainId: number;
  poolId: string;
  /** 0x00 || UTF-8(poolId) || zero padding, as a 32-byte field element. */
  poolIdField: string;
  asset: string;
  denomination: string;
  /** Decimal wei string used in the commitment. */
  denominationWei: string;
  /** 0x 32-byte field element. */
  secret: string;
  /** 0x 32-byte field element. */
  nullifierSecret: string;
  /** Poseidon(6) commitment, 0x 32-byte field element. */
  commitment: string;
  /** Poseidon(5) nullifier, 0x 32-byte field element. */
  nullifier: string;
  createdAt: string;
}

export type NotePayload = NotePayloadV1 | NotePayloadV2;

export interface VeilNote<P extends NotePayload = NotePayload> {
  token: string;
  payload: P;
  /**
   * For v1 this is the legacy SHA-256 nullifier hash. For v2 it is the
   * circuit's Poseidon nullifier.
   */
  nullifierHash: string;
}

export type NoteMode = "v1" | "v2";

const HEX_32 = /^[0-9a-f]{64}$/i;
const HEX_FIELD = /^0x[0-9a-f]{64}$/i;
const HEX_HASH = /^0x[0-9a-f]{64}$/i;
const NOTE_ID = /^note_[0-9a-z]{8,24}$/i;
const DECIMAL_WEI = /^(0|[1-9][0-9]*)$/;
const MAX_UINT64 = (1n << 64n) - 1n;

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function base64UrlToBytes(value: string): Uint8Array {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function randomHex(byteLength = 32): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return bytesToHex(bytes);
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return bytesToHex(new Uint8Array(digest));
}

export async function deriveCommitment(
  poolId: string,
  secret: string,
  nullifierSecret: string,
  denomination: string,
): Promise<string> {
  return `0x${await sha256Hex(
    `veilpool:commitment:v1|${poolId}|${denomination}|${secret}|${nullifierSecret}`,
  )}`;
}

export async function deriveNullifierHash(
  poolId: string,
  nullifierSecret: string,
): Promise<string> {
  return `0x${await sha256Hex(`veilpool:nullifier:v1|${poolId}|${nullifierSecret}`)}`;
}

/** Legacy mock/demo note. Do not use this for local-chain or circuit mode. */
export async function generateNote(
  pool: Pool,
): Promise<VeilNote<NotePayloadV1>> {
  const secret = randomHex(32);
  const nullifierSecret = randomHex(32);
  const commitment = await deriveCommitment(
    pool.id,
    secret,
    nullifierSecret,
    pool.denomination,
  );
  const nullifierHash = await deriveNullifierHash(pool.id, nullifierSecret);

  const payload: NotePayloadV1 = {
    v: 1,
    id: `note_${randomHex(4)}`,
    poolId: pool.id,
    asset: pool.asset,
    denomination: pool.denomination,
    secret,
    nullifierSecret,
    commitment,
    createdAt: new Date().toISOString(),
  };
  const token = `${NOTE_PREFIX}${bytesToBase64Url(
    new TextEncoder().encode(JSON.stringify(payload)),
  )}`;

  return { token, payload, nullifierHash };
}

function randomFieldElement(): bigint {
  let value = 0n;
  while (value === 0n) {
    value = BigInt(`0x${randomHex(32)}`) % FIELD_MODULUS;
  }
  return value;
}

function assertChainId(chainId: number): number {
  if (
    typeof chainId !== "number" ||
    !Number.isSafeInteger(chainId) ||
    chainId < 0
  ) {
    throw new Error("A note v2 chain id must be a non-negative safe integer.");
  }
  return chainId;
}

/**
 * Generates a circuit-compatible note v2:
 *   commitment = Poseidon6(DOMAIN_COMMITMENT, chain_id, pool_id_field,
 *                           denomination_wei, secret, nullifier_secret)
 *   nullifier  = Poseidon5(DOMAIN_NULLIFIER, chain_id, pool_id_field,
 *                           commitment, nullifier_secret)
 */
export async function generateNoteV2(
  pool: Pool,
  chainId: number,
): Promise<VeilNote<NotePayloadV2>> {
  const normalizedChainId = assertChainId(chainId);
  const poolField = poolIdToField(pool.id);
  const amount = denominationWei(pool);
  if (amount <= 0n || amount > MAX_UINT64) {
    throw new Error("The pool denomination must fit in a non-zero uint64.");
  }

  const secret = randomFieldElement();
  const nullifierSecret = randomFieldElement();
  const commitment = hash6(
    DOMAIN_COMMITMENT,
    BigInt(normalizedChainId),
    poolField,
    amount,
    secret,
    nullifierSecret,
  );
  if (commitment === 0n) {
    throw new Error("The generated commitment is zero; regenerate the note.");
  }
  const nullifier = hash5(
    DOMAIN_NULLIFIER,
    BigInt(normalizedChainId),
    poolField,
    commitment,
    nullifierSecret,
  );

  const payload: NotePayloadV2 = {
    v: 2,
    id: `note_${randomHex(4)}`,
    chainId: normalizedChainId,
    poolId: pool.id,
    poolIdField: fieldToHex32(poolField),
    asset: pool.asset,
    denomination: pool.denomination,
    denominationWei: amount.toString(),
    secret: fieldToHex32(secret),
    nullifierSecret: fieldToHex32(nullifierSecret),
    commitment: fieldToHex32(commitment),
    nullifier: fieldToHex32(nullifier),
    createdAt: new Date().toISOString(),
  };
  const token = `${NOTE_PREFIX_V2}${bytesToBase64Url(
    new TextEncoder().encode(JSON.stringify(payload)),
  )}`;

  return { token, payload, nullifierHash: payload.nullifier };
}

export function noteModeForDeposit(input: {
  local: boolean;
  zkNotes: boolean;
}): NoteMode {
  return input.local || input.zkNotes ? "v2" : "v1";
}

export function zkNotesFlagEnabled(
  value: string | undefined = import.meta.env.VITE_ZK_NOTES,
): boolean {
  return typeof value === "string" && value.trim().toLowerCase() === "true";
}

export async function generateNoteForMode(
  pool: Pool,
  chainId: number,
  mode: NoteMode,
): Promise<VeilNote> {
  return mode === "v2" ? generateNoteV2(pool, chainId) : generateNote(pool);
}

function noteField(value: string, label: string): bigint {
  try {
    return fieldFromHex(value);
  } catch {
    throw new NoteError(
      "NOTE_INVALID",
      `The note ${label} is not a canonical field element.`,
    );
  }
}

function validateV1(
  payload: Partial<NotePayloadV1>,
): asserts payload is NotePayloadV1 {
  if (
    typeof payload.id !== "string" ||
    !NOTE_ID.test(payload.id) ||
    typeof payload.poolId !== "string" ||
    typeof payload.asset !== "string" ||
    typeof payload.denomination !== "string" ||
    typeof payload.secret !== "string" ||
    !HEX_32.test(payload.secret) ||
    typeof payload.nullifierSecret !== "string" ||
    !HEX_32.test(payload.nullifierSecret) ||
    typeof payload.commitment !== "string" ||
    !HEX_HASH.test(payload.commitment) ||
    typeof payload.createdAt !== "string"
  ) {
    throw new NoteError("NOTE_INVALID", "The note is missing required fields.");
  }
}

function validateV2(
  payload: Partial<NotePayloadV2>,
): asserts payload is NotePayloadV2 {
  if (
    typeof payload.id !== "string" ||
    !NOTE_ID.test(payload.id) ||
    typeof payload.chainId !== "number" ||
    !Number.isSafeInteger(payload.chainId) ||
    payload.chainId < 0 ||
    typeof payload.poolId !== "string" ||
    !payload.poolId ||
    typeof payload.poolIdField !== "string" ||
    !HEX_FIELD.test(payload.poolIdField) ||
    typeof payload.asset !== "string" ||
    typeof payload.denomination !== "string" ||
    typeof payload.denominationWei !== "string" ||
    !DECIMAL_WEI.test(payload.denominationWei) ||
    typeof payload.secret !== "string" ||
    !HEX_FIELD.test(payload.secret) ||
    typeof payload.nullifierSecret !== "string" ||
    !HEX_FIELD.test(payload.nullifierSecret) ||
    typeof payload.commitment !== "string" ||
    !HEX_FIELD.test(payload.commitment) ||
    typeof payload.nullifier !== "string" ||
    !HEX_FIELD.test(payload.nullifier) ||
    typeof payload.createdAt !== "string"
  ) {
    throw new NoteError("NOTE_INVALID", "The note is missing required fields.");
  }
}

async function parseV1(
  token: string,
  decoded: unknown,
): Promise<VeilNote<NotePayloadV1>> {
  if (!decoded || typeof decoded !== "object") {
    throw new NoteError("NOTE_INVALID", "The note payload is missing.");
  }
  const payload = decoded as Partial<NotePayloadV1>;
  if (payload.v !== 1) {
    throw new NoteError("NOTE_VERSION", "This note version is not supported.");
  }
  validateV1(payload);

  const expectedCommitment = await deriveCommitment(
    payload.poolId,
    payload.secret,
    payload.nullifierSecret,
    payload.denomination,
  );
  if (expectedCommitment.toLowerCase() !== payload.commitment.toLowerCase()) {
    throw new NoteError(
      "NOTE_CHECKSUM",
      "The note commitment does not match its contents.",
    );
  }

  const nullifierHash = await deriveNullifierHash(
    payload.poolId,
    payload.nullifierSecret,
  );

  return { token, payload, nullifierHash };
}

function parseV2(token: string, decoded: unknown): VeilNote<NotePayloadV2> {
  if (!decoded || typeof decoded !== "object") {
    throw new NoteError("NOTE_INVALID", "The note payload is missing.");
  }
  const payload = decoded as Partial<NotePayloadV2>;
  if (payload.v !== 2) {
    throw new NoteError("NOTE_VERSION", "This note version is not supported.");
  }
  validateV2(payload);

  const amount = BigInt(payload.denominationWei);
  if (amount <= 0n || amount > MAX_UINT64) {
    throw new NoteError(
      "NOTE_INVALID",
      "The note denomination is outside the circuit range.",
    );
  }

  const poolField = noteField(payload.poolIdField, "pool id field");
  let expectedPoolField: bigint;
  try {
    expectedPoolField = poolIdToField(payload.poolId);
  } catch {
    throw new NoteError(
      "NOTE_INVALID",
      "The note pool id cannot be encoded for the circuit.",
    );
  }
  if (poolField !== expectedPoolField) {
    throw new NoteError(
      "NOTE_CHECKSUM",
      "The note pool id field does not match its pool id.",
    );
  }

  const secret = noteField(payload.secret, "secret");
  const nullifierSecret = noteField(
    payload.nullifierSecret,
    "nullifier secret",
  );
  if (secret === 0n || nullifierSecret === 0n) {
    throw new NoteError("NOTE_INVALID", "The note secrets must be non-zero.");
  }

  const commitment = noteField(payload.commitment, "commitment");
  const expectedCommitment = hash6(
    DOMAIN_COMMITMENT,
    BigInt(payload.chainId),
    poolField,
    amount,
    secret,
    nullifierSecret,
  );
  if (expectedCommitment !== commitment) {
    throw new NoteError(
      "NOTE_CHECKSUM",
      "The note commitment does not match its contents.",
    );
  }

  const nullifier = noteField(payload.nullifier, "nullifier");
  const expectedNullifier = hash5(
    DOMAIN_NULLIFIER,
    BigInt(payload.chainId),
    poolField,
    commitment,
    nullifierSecret,
  );
  if (expectedNullifier !== nullifier) {
    throw new NoteError(
      "NOTE_CHECKSUM",
      "The note nullifier does not match its contents.",
    );
  }

  return {
    token,
    payload,
    nullifierHash: fieldToHex32(nullifier),
  };
}

/**
 * Accepts both note formats. v1 remains the legacy mock/demo format; v2 is the
 * circuit-compatible Poseidon format used in local Anvil/ZK-note mode.
 */
export async function parseNote(rawToken: string): Promise<VeilNote> {
  const token = rawToken.trim().replace(/\s+/g, "");
  const isV2 = token.startsWith(NOTE_PREFIX_V2);
  const prefix = isV2 ? NOTE_PREFIX_V2 : NOTE_PREFIX;
  if (!isV2 && !token.startsWith(NOTE_PREFIX)) {
    throw new NoteError("NOTE_INVALID", "This is not a VeilPool secret note.");
  }

  let decoded: unknown;
  try {
    const payloadText = new TextDecoder().decode(
      base64UrlToBytes(token.slice(prefix.length)),
    );
    decoded = JSON.parse(payloadText);
  } catch {
    throw new NoteError("NOTE_INVALID", "The note encoding is invalid.");
  }

  return isV2 ? parseV2(token, decoded) : parseV1(token, decoded);
}

export async function buildMockProof(input: {
  poolId: string;
  nullifierHash: string;
  root: string;
  recipient: string;
}): Promise<string> {
  // Deliberately not a zk proof. It is a deterministic public-signal hash so the
  // demo API has a stable proof-shaped value to exercise.
  const digest = await sha256Hex(
    `veilpool:mock-proof:v1|${input.poolId}|${input.nullifierHash}|${input.root}|${input.recipient.toLowerCase()}`,
  );
  return `0x${digest}`;
}

export function showCommitment(commitment: string): string {
  return commitment.length > 18
    ? `${commitment.slice(0, 10)}…${commitment.slice(-8)}`
    : commitment;
}
