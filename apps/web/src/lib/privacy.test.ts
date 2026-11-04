import { describe, expect, it } from "vitest";
import { DEMO_POOLS } from "./demoData";
import { buildDepositIntentRequest, buildMockDepositRequest } from "./deposit";
import {
  buildMockProof,
  generateNote,
  parseNote,
  type VeilNote,
} from "./note";
import {
  NoteLeakError,
  assertNoNoteMaterial,
} from "./privacy";
import {
  buildPublicSignals,
  buildWithdrawalSubmitRequest,
} from "./withdraw";

async function makeNote(): Promise<VeilNote> {
  return generateNote(DEMO_POOLS[0]);
}

function serialized(value: unknown): string {
  return JSON.stringify(value);
}

function decodeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  return new TextDecoder().decode(
    Uint8Array.from(atob(padded), (char) => char.charCodeAt(0)),
  );
}

function encodeBase64Url(value: string): string {
  let binary = "";
  for (const byte of new TextEncoder().encode(value)) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

describe("note handling", () => {
  it("round-trips a generated note and verifies its commitment", async () => {
    const note = await makeNote();
    const parsed = await parseNote(note.token);
    expect(parsed.payload.id).toBe(note.payload.id);
    expect(parsed.payload.commitment).toBe(note.payload.commitment);
    expect(parsed.nullifierHash).toBe(note.nullifierHash);
    expect(note.token.startsWith("veilnote1")).toBe(true);
  });

  it("rejects a tampered note payload", async () => {
    const note = await makeNote();
    const encoded = note.token.slice("veilnote1".length);
    const payload = JSON.parse(decodeBase64Url(encoded)) as Record<
      string,
      unknown
    >;
    payload.secret = "ab".repeat(32);
    const tampered = `veilnote1${encodeBase64Url(JSON.stringify(payload))}`;
    await expect(parseNote(tampered)).rejects.toThrow();
  });
});

describe("API payload boundary", () => {
  it("never puts the note or its secrets in deposit intent JSON", async () => {
    const note = await makeNote();
    const payload = buildDepositIntentRequest({
      poolId: note.payload.poolId,
      depositorAddress: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
      amount: note.payload.denomination,
      commitment: note.payload.commitment,
    });
    const body = serialized(payload);
    expect(body).not.toContain(note.token);
    expect(body).not.toContain(note.payload.secret);
    expect(body).not.toContain(note.payload.nullifierSecret);
    expect(payload).not.toHaveProperty("note");
    expect(payload).not.toHaveProperty("secret");
    expect(() => assertNoNoteMaterial(payload)).not.toThrow();
  });

  it("sends the commitment to the mock deposit endpoint without the note", async () => {
    const note = await makeNote();
    const payload = buildMockDepositRequest({
      intentId: "dep_test_001",
      commitment: note.payload.commitment,
    });
    const body = serialized(payload);
    expect(payload).toEqual({
      intent_id: "dep_test_001",
      commitment: note.payload.commitment,
    });
    expect(body).toContain(note.payload.commitment);
    expect(body).not.toContain(note.token);
    expect(body).not.toContain(note.payload.secret);
    expect(body).not.toContain(note.payload.nullifierSecret);
    expect(payload).not.toHaveProperty("note");
    expect(() => assertNoNoteMaterial(payload)).not.toThrow();
  });

  it("never puts the note or its secrets in withdrawal submit JSON", async () => {    const note = await makeNote();
    const root = `0x${"11".repeat(32)}`;
    const proof = await buildMockProof({
      poolId: note.payload.poolId,
      nullifierHash: note.nullifierHash,
      root,
      recipient: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
    });
    const publicSignals = buildPublicSignals({
      root,
      nullifierHash: note.nullifierHash,
      recipient: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
      feeWei: "240000000000000",
    });
    const payload = buildWithdrawalSubmitRequest({
      poolId: note.payload.poolId,
      quoteId: "q_test",
      proof,
      publicSignals,
      recipientAddress: "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28",
    });
    const body = serialized(payload);
    expect(body).not.toContain(note.token);
    expect(body).not.toContain(note.payload.secret);
    expect(body).not.toContain(note.payload.nullifierSecret);
    expect(payload.public_signals.nullifier_hash).toBe(note.nullifierHash);
    expect(() => assertNoNoteMaterial(payload)).not.toThrow();
  });

  it("fails closed if a caller tries to send a note-shaped payload", async () => {
    const note = await makeNote();
    expect(() =>
      assertNoNoteMaterial({ pool_id: note.payload.poolId, note: note.token }),
    ).toThrow(NoteLeakError);
    expect(() =>
      assertNoNoteMaterial({ pool_id: note.payload.poolId, secret: note.payload.secret }),
    ).toThrow(NoteLeakError);
  });
});
