import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_POOLS } from "./demoData";
import { buildMockProof, generateNote } from "./note";
import { assertNoNoteMaterial } from "./privacy";
import { vaultIsLocked } from "./session";
import {
  buildPublicSignals,
  buildQuoteRequest,
  buildWithdrawalSubmitRequest,
} from "./withdraw";
import {
  createNoteBackup,
  exportVaultBackup,
  getNote,
  hasVaultSessionKey,
  importEncryptedBackup,
  importVaultBackup,
  listVaultMeta,
  listVaultNotes,
  lockVaultSession,
  markNoteSpent,
  putNote,
  unspentVaultNotes,
  vaultSummary,
} from "./vault";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

beforeEach(() => {
  vi.stubGlobal("localStorage", new MemoryStorage());
  vi.stubGlobal("sessionStorage", new MemoryStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("vault note retrieval", () => {
  it("stores, decrypts and lists a note for the withdraw picker", async () => {
    const note = await generateNote(DEMO_POOLS[0]);
    await putNote(note, false);

    const opened = await getNote(note.payload.id);
    expect(opened?.token).toBe(note.token);
    expect(opened?.nullifierHash).toBe(note.nullifierHash);

    const entries = await listVaultNotes();
    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({
      id: note.payload.id,
      poolId: note.payload.poolId,
      asset: note.payload.asset,
      denomination: note.payload.denomination,
      backedUp: false,
      spent: false,
    });
    expect(entries[0].note.token).toBe(note.token);
    expect(unspentVaultNotes(entries)).toHaveLength(1);

    expect(listVaultMeta()).toHaveLength(1);
    expect(vaultSummary()).toEqual({ total: 1, backedUp: 0, unbacked: 1 });
  });

  it("keeps the session key across a refresh and shows the import path after a lock", async () => {
    const note = await generateNote(DEMO_POOLS[0]);
    await putNote(note, true);

    // A page refresh re-reads sessionStorage, so the picker can still open the
    // note without asking for a passphrase.
    expect(hasVaultSessionKey()).toBe(true);
    expect(await listVaultNotes()).toHaveLength(1);

    lockVaultSession();

    // After a lock there is no password unlock path: the UI must offer the
    // encrypted backup import instead of a fake password form.
    expect(hasVaultSessionKey()).toBe(false);
    expect(vaultIsLocked(hasVaultSessionKey(), vaultSummary().total)).toBe(
      true,
    );
  });

  it("keeps spent notes out of the selectable unspent set", async () => {
    const note = await generateNote(DEMO_POOLS[0]);
    await putNote(note, true);
    markNoteSpent(note.payload.id);

    const entries = await listVaultNotes();
    expect(entries[0].backedUp).toBe(true);
    expect(entries[0].spent).toBe(true);
    expect(unspentVaultNotes(entries)).toHaveLength(0);
  });

  it("locks the session and restores notes only by importing an encrypted backup", async () => {
    const note = await generateNote(DEMO_POOLS[0]);
    await putNote(note, true);
    const backup = JSON.stringify(await exportVaultBackup("vault passphrase"));

    lockVaultSession();
    expect(hasVaultSessionKey()).toBe(false);
    await expect(getNote(note.payload.id)).rejects.toThrow(/locked/i);
    await expect(listVaultNotes()).rejects.toThrow(/locked/i);

    // There is no password unlock path: the random session key is gone until
    // an encrypted backup is opened and a new session is created.
    const imported = await importVaultBackup(backup, "vault passphrase");
    expect(imported).toBe(1);
    expect(hasVaultSessionKey()).toBe(true);
    expect((await getNote(note.payload.id))?.token).toBe(note.token);
  });

  it("restores a locked vault from a single-note encrypted backup", async () => {
    const note = await generateNote(DEMO_POOLS[0]);
    await putNote(note, true);
    const backup = JSON.stringify(await createNoteBackup(note, "note passphrase"));
    lockVaultSession();
    expect(hasVaultSessionKey()).toBe(false);

    const imported = await importEncryptedBackup(backup, "note passphrase");
    expect(imported).toEqual({ count: 1, kind: "note" });
    expect((await getNote(note.payload.id))?.token).toBe(note.token);
  });

  it("keeps a vault-selected note out of quote and withdrawal payloads", async () => {
    const note = await generateNote(DEMO_POOLS[0]);
    await putNote(note, true);
    const selected = await getNote(note.payload.id);
    expect(selected).not.toBeNull();
    if (!selected) return;

    const recipient = "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28";
    const quotePayload = buildQuoteRequest({
      poolId: selected.payload.poolId,
      recipientAddress: recipient,
      relayerId: "relayer_demo_1",
    });
    expect(JSON.stringify(quotePayload)).not.toContain(selected.token);
    expect(() => assertNoNoteMaterial(quotePayload)).not.toThrow();

    const root = `0x${"11".repeat(32)}`;
    const proof = await buildMockProof({
      poolId: selected.payload.poolId,
      nullifierHash: selected.nullifierHash,
      root,
      recipient,
    });
    const payload = buildWithdrawalSubmitRequest({
      poolId: selected.payload.poolId,
      quoteId: "quote_demo_1",
      proof,
      publicSignals: buildPublicSignals({
        root,
        nullifierHash: selected.nullifierHash,
        recipient,
        feeWei: "240000000000000",
      }),
      recipientAddress: recipient,
    });
    const body = JSON.stringify(payload);
    expect(body).not.toContain(selected.token);
    expect(body).not.toContain(selected.payload.secret);
    expect(body).not.toContain(selected.payload.nullifierSecret);
    expect(payload).not.toHaveProperty("note");
    expect(() => assertNoNoteMaterial(payload)).not.toThrow();
  });
});
