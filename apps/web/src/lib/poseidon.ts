import { POSEIDON_C, POSEIDON_M } from "./poseidonConstants";

/**
 * BN254 scalar field modulus (the field used by circom/snarkjs and circomlib's
 * Poseidon). All values here are canonical field elements in [0, p).
 */
export const FIELD_MODULUS =
  21888242871839275222246405745257275088548364400416034343698204186575808495617n;

/** ASCII "veilpool-commit-v1" as a big-endian field element. */
export const DOMAIN_COMMITMENT =
  0x7665696c706f6f6c2d636f6d6d69742d7631n;
/** ASCII "veilpool-null-v1" as a big-endian field element. */
export const DOMAIN_NULLIFIER = 0x7665696c706f6f6c2d6e756c6c2d7631n;
/** ASCII "veilpool-merkle-v1" as a big-endian field element. */
export const DOMAIN_NODE = 0x7665696c706f6f6c2d6d65726b6c652d7631n;

const N_ROUNDS_F = 8;

function toBigIntConstants(
  source: Readonly<Record<number, readonly string[]>>,
): Map<number, readonly bigint[]> {
  return new Map(
    Object.entries(source).map(([width, values]) => [
      Number(width),
      values.map((value) => BigInt(value)),
    ]),
  );
}

function toBigIntMatrix(
  source: Readonly<Record<number, readonly (readonly string[])[]>>,
): Map<number, readonly (readonly bigint[])[]> {
  return new Map(
    Object.entries(source).map(([width, rows]) => [
      Number(width),
      rows.map((row) => row.map((value) => BigInt(value))),
    ]),
  );
}

// Parsed once at module load; the hash loop stays pure BigInt arithmetic.
const ROUND_CONSTANTS = toBigIntConstants(POSEIDON_C);
const MDS_MATRICES = toBigIntMatrix(POSEIDON_M);

export function fieldMod(value: bigint): bigint {
  const reduced = value % FIELD_MODULUS;
  return reduced < 0n ? reduced + FIELD_MODULUS : reduced;
}

/**
 * Parses a hex field element. Accepts an optional 0x prefix and 1-64 hex
 * digits, and rejects values outside the BN254 scalar field. This is the
 * canonical check used by note v2; it does not reduce modulo p silently.
 */
export function fieldFromHex(value: string): bigint {
  if (typeof value !== "string") {
    throw new TypeError("A field element must be a hex string.");
  }
  const trimmed = value.trim();
  if (!/^(?:0x)?[0-9a-fA-F]{1,64}$/.test(trimmed)) {
    throw new Error("A field element must be 1-64 hex digits.");
  }
  const parsed = BigInt(
    trimmed.startsWith("0x") || trimmed.startsWith("0X")
      ? trimmed
      : `0x${trimmed}`,
  );
  if (parsed >= FIELD_MODULUS) {
    throw new Error("The field element is not canonical (it is >= p).");
  }
  return parsed;
}

/** Encodes a canonical BN254 field element as a 0x-prefixed 32-byte hex value. */
export function fieldToHex32(value: bigint): string {
  if (typeof value !== "bigint") {
    throw new TypeError("A field element must be a bigint.");
  }
  if (value < 0n || value >= FIELD_MODULUS) {
    throw new RangeError("The field element is outside [0, p).");
  }
  return `0x${value.toString(16).padStart(64, "0")}`;
}

/**
 * Canonical pool-id encoding from the circuit spec:
 *   0x00 || UTF-8(pool_id_text) || zero padding to 32 bytes.
 * The leading zero keeps the value below 2^248 (and therefore below p).
 */
export function poolIdToField(poolId: string): bigint {
  if (typeof poolId !== "string" || poolId.length === 0) {
    throw new Error("A pool id must be a non-empty string.");
  }
  const bytes = new TextEncoder().encode(poolId);
  if (bytes.length > 31) {
    throw new Error("A pool id must be at most 31 UTF-8 bytes for note v2.");
  }
  if (bytes.includes(0)) {
    throw new Error("A pool id must not contain a NUL byte.");
  }
  let value = 0n;
  for (const byte of bytes) {
    value = (value << 8n) | BigInt(byte);
  }
  // Right-pad the UTF-8 label to the 31 bytes after the leading 0x00. For an
  // 11-byte label this puts the text at the high end of the 31-byte region,
  // exactly like 0x00 || label || 20 zero bytes.
  return value << (8n * BigInt(31 - bytes.length));
}

function pow5(value: bigint): bigint {
  const squared = (value * value) % FIELD_MODULUS;
  return (((squared * squared) % FIELD_MODULUS) * value) % FIELD_MODULUS;
}

/**
 * circomlib 2.0.5 Poseidon permutation for 1-6 inputs (state width 2-7).
 * Inputs are reduced modulo p, matching the field arithmetic in the circuit.
 */
function poseidon(inputs: readonly bigint[]): bigint {
  if (inputs.length < 1 || inputs.length > 6) {
    throw new Error("Poseidon supports between 1 and 6 inputs here.");
  }
  const width = inputs.length + 1;
  const constants = ROUND_CONSTANTS.get(width);
  const matrix = MDS_MATRICES.get(width);
  if (!constants || !matrix) {
    throw new Error(`Poseidon(${inputs.length}) is not supported.`);
  }
  const partialRounds = constants.length / width - N_ROUNDS_F;
  if (!Number.isInteger(partialRounds) || partialRounds <= 0) {
    throw new Error("The Poseidon constants have an invalid length.");
  }

  let state: bigint[] = new Array<bigint>(width);
  state[0] = 0n;
  for (let index = 0; index < inputs.length; index += 1) {
    state[index + 1] = fieldMod(inputs[index]);
  }

  const halfFullRounds = N_ROUNDS_F / 2;
  const totalRounds = N_ROUNDS_F + partialRounds;
  for (let round = 0; round < totalRounds; round += 1) {
    const offset = round * width;
    for (let index = 0; index < width; index += 1) {
      state[index] = fieldMod(state[index] + constants[offset + index]);
    }

    if (round < halfFullRounds || round >= halfFullRounds + partialRounds) {
      for (let index = 0; index < width; index += 1) {
        state[index] = pow5(state[index]);
      }
    } else {
      state[0] = pow5(state[0]);
    }

    const next: bigint[] = new Array<bigint>(width);
    for (let row = 0; row < width; row += 1) {
      let sum = 0n;
      const coefficients = matrix[row];
      for (let column = 0; column < width; column += 1) {
        sum = fieldMod(sum + coefficients[column] * state[column]);
      }
      next[row] = sum;
    }
    state = next;
  }

  return state[0];
}

/** Poseidon(3), used for the domain-separated Merkle node hash. */
export function hash3(a: bigint, b: bigint, c: bigint): bigint {
  return poseidon([a, b, c]);
}

/** Poseidon(5), used for the note nullifier. */
export function hash5(
  a: bigint,
  b: bigint,
  c: bigint,
  d: bigint,
  e: bigint,
): bigint {
  return poseidon([a, b, c, d, e]);
}

/** Poseidon(6), used for the note commitment. */
export function hash6(
  a: bigint,
  b: bigint,
  c: bigint,
  d: bigint,
  e: bigint,
  f: bigint,
): bigint {
  return poseidon([a, b, c, d, e, f]);
}
