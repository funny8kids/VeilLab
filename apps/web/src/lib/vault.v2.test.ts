import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEMO_POOLS } from "./demoData";
import { generateNote, generateNoteV2 } from "./note";
import {
  createNoteBackup,
  exportVaultBackup,
  getNote,
  importEncryptedBackup,
  importVaultBackup,
  listVaultMeta,
  listVaultNotes,
  lockVaultSession,
  markNoteBackedUp,
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

describe("vault with note v2", () => {
  it("stores, decrypts and lists a v2 note for the picker", async () => {
    const note = await generateNoteV2(DEMO_POOLS[0], 31337);
    await putNote(note, false);

    const opened = await getNote(note.payload.id);
    expect(opened?.token).toBe(note.token);
    expect(opened?.payload.v).toBe(2);
    expect(opened?.payload.commitment).toBe(note.payload.commitment);
    expect(opened?.nullifierHash).toBe(note.payload.nullifier);

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
    expect(unspentVaultNotes(entries)).toHaveLength(1);
    expect(vaultSummary()).toEqual({ total: 1, backedUp: 0, unbacked: 1 });
  });

  it("exports and restores v2 notes through the encrypted vault backup", async () => {
    const note = await generateNoteV2(DEMO_POOLS[0], 31337);
    await putNote(note, true);
    markNoteBackedUp(note.payload.id);
    expect(listVaultMeta()[0].backedUp).toBe(true);

    const backup = JSON.stringify(await exportVaultBackup("v2 vault passphrase"));
    lockVaultSession();
    await expect(listVaultNotes()).rejects.toThrow(/locked/i);

    const imported = await importVaultBackup(backup, "v2 vault passphrase");
    expect(imported).toBe(1);

    const restored = await getNote(note.payload.id);
    expect(restored?.payload.v).toBe(2);
    if (restored?.payload.v !== 2) throw new Error("unreachable");
    expect(restored.payload.commitment).toBe(note.payload.commitment);
    expect(restored.payload.nullifier).toBe(note.payload.nullifier);
    expect(restored.token).toBe(note.token);
  });

  it("imports a single v2 note backup after the vault is locked", async () => {
    const note = await generateNoteV2(DEMO_POOLS[0], 31337);
    await putNote(note, true);
    const backup = JSON.stringify(
      await createNoteBackup(note, "v2 note passphrase"),
    );
    lockVaultSession();

    const imported = await importEncryptedBackup(backup, "v2 note passphrase");
    expect(imported).toEqual({ count: 1, kind: "note" });
    const restored = await getNote(note.payload.id);
    expect(restored?.payload.v).toBe(2);
    expect(restored?.payload.commitment).toBe(note.payload.commitment);
  });

  it("keeps legacy v1 and v2 notes side by side", async () => {
    const legacy = await generateNote(DEMO_POOLS[0]);
    const circuitCompatible = await generateNoteV2(DEMO_POOLS[0], 31337);
    await putNote(legacy, true);
    await putNote(circuitCompatible, true);

    const entries = await listVaultNotes();
    expect(entries).toHaveLength(2);
    const versions = entries
      .map((entry) => entry.note.payload.v)
      .sort((left, right) => left - right);
    expect(versions).toEqual([1, 2]);

    expect((await getNote(legacy.payload.id))?.payload.v).toBe(1);
    expect((await getNote(circuitCompatible.payload.id))?.payload.v).toBe(2);
  });
});
