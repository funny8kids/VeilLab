import { describe, expect, it } from "vitest";
import fixture from "../../../../circuits/test-vectors/membership-v1.json";
import { DEMO_POOLS } from "./demoData";
import { buildDepositIntentRequest } from "./deposit";
import {
  NoteError,
  NOTE_PREFIX_V2,
  generateNote,
  generateNoteForMode,
  generateNoteV2,
  noteModeForDeposit,
  parseNote,
  zkNotesFlagEnabled,
  type NotePayloadV2,
} from "./note";
import {
  DOMAIN_COMMITMENT,
  DOMAIN_NULLIFIER,
  fieldFromHex,
  fieldToHex32,
  hash5,
  hash6,
  poolIdToField,
} from "./poseidon";
import { NoteLeakError, assertNoNoteMaterial } from "./privacy";

const POOL = DEMO_POOLS[0];
const CHAIN_ID = 31337;

function encodeToken(payload: unknown): string {
  let binary = "";
  for (const byte of new TextEncoder().encode(JSON.stringify(payload))) {
    binary += String.fromCharCode(byte);
  }
  const encoded = btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
  return `${NOTE_PREFIX_V2}${encoded}`;
}

function fixtureV2Payload(): NotePayloadV2 {
  const note = fixture.note;
  return {
    v: 2,
    id: "note_1234abcd",
    chainId: Number(note.chain_id),
    poolId: note.pool_id_text,
    poolIdField: fieldToHex32(poolIdToField(note.pool_id_text)),
    asset: "ETH",
    denomination: "0.1",
    denominationWei: note.denomination,
    secret: note.secret_field,
    nullifierSecret: note.nullifier_secret_field,
    commitment: fixture.derived.commitment,
    nullifier: fixture.derived.nullifier,
    createdAt: "2026-11-03T00:00:00.000Z",
  };
}

describe("note v2", () => {
  it("generates the circuit commitment and nullifier from CSPRNG fields", async () => {
    const note = await generateNoteV2(POOL, CHAIN_ID);
    expect(note.token.startsWith(NOTE_PREFIX_V2)).toBe(true);
    expect(note.payload.v).toBe(2);
    expect(note.payload.chainId).toBe(CHAIN_ID);
    expect(note.payload.poolId).toBe(POOL.id);
    expect(note.payload.poolIdField).toBe(
      fieldToHex32(poolIdToField(POOL.id)),
    );
    expect(note.payload.denominationWei).toBe(POOL.denomination_wei);
    expect(note.payload.secret).not.toBe(`0x${"0".repeat(64)}`);
    expect(note.payload.nullifierSecret).not.toBe(`0x${"0".repeat(64)}`);

    const commitment = hash6(
      DOMAIN_COMMITMENT,
      BigInt(CHAIN_ID),
      fieldFromHex(note.payload.poolIdField),
      BigInt(note.payload.denominationWei),
      fieldFromHex(note.payload.secret),
      fieldFromHex(note.payload.nullifierSecret),
    );
    expect(note.payload.commitment).toBe(fieldToHex32(commitment));
    expect(note.nullifierHash).toBe(note.payload.nullifier);

    const nullifier = hash5(
      DOMAIN_NULLIFIER,
      BigInt(CHAIN_ID),
      fieldFromHex(note.payload.poolIdField),
      commitment,
      fieldFromHex(note.payload.nullifierSecret),
    );
    expect(note.payload.nullifier).toBe(fieldToHex32(nullifier));
  });

  it("round-trips a generated v2 note and verifies both hashes", async () => {
    const note = await generateNoteV2(POOL, 11155111);
    const parsed = await parseNote(note.token);
    expect(parsed.payload.v).toBe(2);
    expect(parsed.token).toBe(note.token);
    expect(parsed.payload).toEqual(note.payload);
    expect(parsed.nullifierHash).toBe(note.payload.nullifier);
  });

  it("parses the exact circuit fixture as a v2 note", async () => {
    const payload = fixtureV2Payload();
    const parsed = await parseNote(encodeToken(payload));
    expect(parsed.payload.v).toBe(2);
    if (parsed.payload.v !== 2) throw new Error("unreachable");
    expect(parsed.payload.commitment).toBe(fixture.derived.commitment);
    expect(parsed.payload.nullifier).toBe(fixture.derived.nullifier);
    expect(parsed.nullifierHash).toBe(fixture.derived.nullifier);
  });

  it("rejects a tampered v2 commitment or nullifier", async () => {
    const commitment = fixtureV2Payload();
    commitment.commitment = `0x${"11".repeat(32)}`;
    await expect(parseNote(encodeToken(commitment))).rejects.toMatchObject({
      code: "NOTE_CHECKSUM",
    });

    const nullifier = fixtureV2Payload();
    nullifier.nullifier = `0x${"22".repeat(32)}`;
    await expect(parseNote(encodeToken(nullifier))).rejects.toMatchObject({
      code: "NOTE_CHECKSUM",
    });

    const badPoolField = fixtureV2Payload();
    badPoolField.poolIdField = fieldToHex32(poolIdToField("other_pool"));
    await expect(parseNote(encodeToken(badPoolField))).rejects.toBeInstanceOf(
      NoteError,
    );
  });

  it("rejects an unsupported version while keeping v1 parsing intact", async () => {
    const v1 = await generateNote(POOL);
    const parsedV1 = await parseNote(v1.token);
    expect(parsedV1.payload.v).toBe(1);
    expect(parsedV1.payload.commitment).toBe(v1.payload.commitment);

    const v3 = { ...fixtureV2Payload(), v: 3 };
    await expect(parseNote(encodeToken(v3))).rejects.toMatchObject({
      code: "NOTE_VERSION",
    });
  });

  it("chooses v2 for local/ZK mode and v1 for mock/demo mode", async () => {
    expect(noteModeForDeposit({ local: true, zkNotes: false })).toBe("v2");
    expect(noteModeForDeposit({ local: false, zkNotes: true })).toBe("v2");
    expect(noteModeForDeposit({ local: false, zkNotes: false })).toBe("v1");

    expect(zkNotesFlagEnabled("true")).toBe(true);
    expect(zkNotesFlagEnabled(" TRUE ")).toBe(true);
    expect(zkNotesFlagEnabled("false")).toBe(false);
    expect(zkNotesFlagEnabled(undefined)).toBe(false);

    const localNote = await generateNoteForMode(POOL, CHAIN_ID, "v2");
    expect(localNote.payload.v).toBe(2);
    expect(localNote.token.startsWith("veilnote2")).toBe(true);

    const mockNote = await generateNoteForMode(POOL, CHAIN_ID, "v1");
    expect(mockNote.payload.v).toBe(1);
    expect(mockNote.token.startsWith("veilnote1")).toBe(true);
  });

  it("puts only the v2 commitment in the deposit intent payload", async () => {
    const note = await generateNoteForMode(POOL, CHAIN_ID, "v2");
    const payload = buildDepositIntentRequest({
      poolId: note.payload.poolId,
      depositorAddress: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
      amount: note.payload.denomination,
      commitment: note.payload.commitment,
    });

    expect(payload.commitment).toBe(note.payload.commitment);
    const body = JSON.stringify(payload);
    expect(body).not.toContain(note.token);
    expect(body).not.toContain(note.payload.secret);
    expect(body).not.toContain(note.payload.nullifierSecret);
    expect(payload).not.toHaveProperty("note");
    expect(() => assertNoNoteMaterial(payload)).not.toThrow();
  });

  it("treats a v2 note token as note material in the last-line guard", async () => {
    const note = await generateNoteV2(POOL, CHAIN_ID);
    expect(() => assertNoNoteMaterial({ note: note.token })).toThrow(
      NoteLeakError,
    );
    expect(() =>
      assertNoNoteMaterial({ nullifier_secret: note.payload.nullifierSecret }),
    ).toThrow(NoteLeakError);
  });

  it("rejects invalid chain ids and an invalid pool id", async () => {
    await expect(generateNoteV2(POOL, -1)).rejects.toThrow();
    await expect(generateNoteV2(POOL, 1.5)).rejects.toThrow();
    await expect(
      generateNoteV2({ ...POOL, id: "p".repeat(32) }, CHAIN_ID),
    ).rejects.toThrow();
  });
});
