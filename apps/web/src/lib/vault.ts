import type {
  BackupEnvelope,
  VaultBackupEnvelope,
  VaultRecordMeta,
  VaultSummary,
} from "../types";
import type { VeilNote } from "./note";
import { parseNote } from "./note";
import {
  bytesToBase64,
  decryptWithKey,
  decryptWithPassphrase,
  encryptWithKey,
  encryptWithPassphrase,
  importSessionKey,
  parseNoteBackup,
  parseVaultBackup,
  randomBytes,
} from "./crypto";

const VAULT_KEY = "veilpool.vault.v1";
const SESSION_KEY = "veilpool.vault.sessionkey";

interface StoredVaultRecord extends VaultRecordMeta {
  iv: string;
  ciphertext: string;
}

export interface VaultNoteEntry extends VaultRecordMeta {
  note: VeilNote;
}

export function unspentVaultNotes(
  entries: VaultNoteEntry[],
): VaultNoteEntry[] {
  return entries.filter((entry) => !entry.spent);
}

function getStorage(): Storage {
  if (typeof localStorage === "undefined") {
    throw new Error("Browser storage is unavailable.");
  }
  return localStorage;
}

function getSessionStorage(): Storage {
  if (typeof sessionStorage === "undefined") {
    throw new Error("Session storage is unavailable.");
  }
  return sessionStorage;
}

function readRecords(): StoredVaultRecord[] {
  try {
    const raw = getStorage().getItem(VAULT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as StoredVaultRecord[]) : [];
  } catch {
    return [];
  }
}

function writeRecords(records: StoredVaultRecord[]): void {
  getStorage().setItem(VAULT_KEY, JSON.stringify(records));
}

async function getVaultKey(create: boolean): Promise<CryptoKey> {
  const storage = getSessionStorage();
  let rawKey = storage.getItem(SESSION_KEY);
  if (!rawKey && create) {
    rawKey = bytesToBase64(randomBytes(32));
    storage.setItem(SESSION_KEY, rawKey);
  }
  if (!rawKey) {
    throw new Error(
      "The note vault is locked for this session. Import an encrypted backup to restore notes.",
    );
  }
  return importSessionKey(rawKey);
}

export function hasVaultSessionKey(): boolean {
  try {
    return Boolean(getSessionStorage().getItem(SESSION_KEY));
  } catch {
    return false;
  }
}

export async function putNote(note: VeilNote, backedUp = false): Promise<void> {
  const records = readRecords();
  const key = await getVaultKey(true);
  const encrypted = await encryptWithKey(note.token, key);
  const record: StoredVaultRecord = {
    id: note.payload.id,
    poolId: note.payload.poolId,
    asset: note.payload.asset,
    denomination: note.payload.denomination,
    createdAt: note.payload.createdAt,
    backedUp,
    spent: false,
    iv: encrypted.iv,
    ciphertext: encrypted.ciphertext,
  };
  const existing = records.findIndex((item) => item.id === note.payload.id);
  if (existing >= 0) {
    // Re-encrypt existing entries too. After a session lock the old ciphertext
    // is unreadable, so an import must be able to replace it with the new key.
    records[existing] = record;
  } else {
    records.push(record);
  }
  writeRecords(records);
}

export function listVaultMeta(): VaultRecordMeta[] {
  return readRecords()
    .map((record) => ({
      id: record.id,
      poolId: record.poolId,
      asset: record.asset,
      denomination: record.denomination,
      createdAt: record.createdAt,
      backedUp: Boolean(record.backedUp),
      spent: Boolean(record.spent),
    }))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

export async function getNote(noteId: string): Promise<VeilNote | null> {
  const record = readRecords().find((item) => item.id === noteId);
  if (!record) return null;
  const key = await getVaultKey(false);
  const token = await decryptWithKey(record.ciphertext, record.iv, key);
  const note = await parseNote(token);
  if (note.payload.id !== noteId) {
    throw new Error("The vault record does not match its note id.");
  }
  return note;
}

export async function listVaultNotes(): Promise<VaultNoteEntry[]> {
  const records = readRecords();
  if (records.length === 0) return [];
  const key = await getVaultKey(false);
  const entries: VaultNoteEntry[] = [];
  for (const record of records) {
    try {
      const token = await decryptWithKey(record.ciphertext, record.iv, key);
      const note = await parseNote(token);
      if (note.payload.id !== record.id) continue;
      entries.push({
        id: record.id,
        poolId: record.poolId,
        asset: record.asset,
        denomination: record.denomination,
        createdAt: record.createdAt,
        backedUp: Boolean(record.backedUp),
        spent: Boolean(record.spent),
        note,
      });
    } catch {
      // A record encrypted under a discarded session key is unreadable. Skip
      // it so one stale entry cannot block the remaining notes.
    }
  }
  return entries.sort((left, right) =>
    right.createdAt.localeCompare(left.createdAt),
  );
}

export function lockVaultSession(): void {
  try {
    getSessionStorage().removeItem(SESSION_KEY);
  } catch {
    /* The session is already unavailable. */
  }
}

export function vaultSummary(): VaultSummary {
  const records = listVaultMeta();
  const backedUp = records.filter((record) => record.backedUp).length;
  return {
    total: records.length,
    backedUp,
    unbacked: records.filter((record) => !record.backedUp && !record.spent).length,
  };
}

export function markNoteBackedUp(noteId: string): void {
  const records = readRecords();
  let changed = false;
  for (const record of records) {
    if (record.id === noteId && !record.backedUp) {
      record.backedUp = true;
      changed = true;
    }
  }
  if (changed) writeRecords(records);
}

export function markNoteSpent(noteId: string): void {
  const records = readRecords();
  let changed = false;
  for (const record of records) {
    if (record.id === noteId && !record.spent) {
      record.spent = true;
      changed = true;
    }
  }
  if (changed) writeRecords(records);
}

export function removeNote(noteId: string): void {
  writeRecords(readRecords().filter((record) => record.id !== noteId));
}

export function clearVault(): void {
  try {
    getStorage().removeItem(VAULT_KEY);
    getSessionStorage().removeItem(SESSION_KEY);
  } catch {
    /* Nothing to clear. */
  }
}

export async function createNoteBackup(
  note: VeilNote,
  passphrase: string,
): Promise<BackupEnvelope> {
  const plaintext = JSON.stringify({
    token: note.token,
    noteId: note.payload.id,
    poolId: note.payload.poolId,
    createdAt: new Date().toISOString(),
  });
  return {
    type: "veilpool.note.backup",
    version: 1,
    createdAt: new Date().toISOString(),
    noteId: note.payload.id,
    poolId: note.payload.poolId,
    cipher: await encryptWithPassphrase(plaintext, passphrase),
  };
}

export async function readNoteBackup(
  raw: string,
  passphrase: string,
): Promise<VeilNote> {
  const envelope = parseNoteBackup(raw);
  const plaintext = await decryptWithPassphrase(envelope.cipher, passphrase);
  let decoded: unknown;
  try {
    decoded = JSON.parse(plaintext);
  } catch {
    throw new Error("The backup payload is damaged.");
  }
  const record = decoded as { token?: string; noteId?: string };
  if (!record.token || typeof record.token !== "string") {
    throw new Error("The backup does not contain a note.");
  }
  const note = await parseNote(record.token);
  if (record.noteId && note.payload.id !== record.noteId) {
    throw new Error("The backup note id does not match its contents.");
  }
  return note;
}

export async function exportVaultBackup(
  passphrase: string,
): Promise<VaultBackupEnvelope> {
  const records = readRecords();
  if (records.length === 0) {
    throw new Error("There are no notes in the local vault.");
  }
  const key = await getVaultKey(false);
  const notes: BackupEnvelope[] = [];
  for (const record of records) {
    const token = await decryptWithKey(record.ciphertext, record.iv, key);
    const note = await parseNote(token);
    notes.push(await createNoteBackup(note, passphrase));
  }
  return {
    type: "veilpool.vault.backup",
    version: 1,
    createdAt: new Date().toISOString(),
    notes,
  };
}

export type EncryptedBackupKind = "vault" | "note";

export function detectEncryptedBackup(raw: string): EncryptedBackupKind | null {
  try {
    const parsed = JSON.parse(raw) as { type?: string };
    if (parsed?.type === "veilpool.vault.backup") return "vault";
    if (parsed?.type === "veilpool.note.backup") return "note";
    return null;
  } catch {
    return null;
  }
}

export async function importNoteBackup(
  raw: string,
  passphrase: string,
): Promise<number> {
  const note = await readNoteBackup(raw, passphrase);
  if (!hasVaultSessionKey()) {
    // Unlocking with a single-note backup also starts a new session; stale
    // records from the discarded key cannot be opened and must not block it.
    writeRecords([]);
  }
  await putNote(note, true);
  return 1;
}

export async function importEncryptedBackup(
  raw: string,
  passphrase: string,
): Promise<{ count: number; kind: EncryptedBackupKind }> {
  const kind = detectEncryptedBackup(raw);
  if (kind === "note") {
    return { count: await importNoteBackup(raw, passphrase), kind };
  }
  if (kind === "vault") {
    return { count: await importVaultBackup(raw, passphrase), kind };
  }
  throw new Error("This file is not a VeilPool encrypted backup.");
}

export async function importVaultBackup(
  raw: string,
  passphrase: string,
): Promise<number> {
  const envelope = parseVaultBackup(raw);
  const locked = !hasVaultSessionKey();
  const notes: VeilNote[] = [];
  for (const backup of envelope.notes) {
    const plaintext = await decryptWithPassphrase(backup.cipher, passphrase);
    const decoded = JSON.parse(plaintext) as { token?: string; noteId?: string };
    if (!decoded.token) continue;
    const note = await parseNote(decoded.token);
    if (decoded.noteId && decoded.noteId !== note.payload.id) continue;
    notes.push(note);
  }
  if (notes.length === 0) {
    throw new Error("No notes could be imported from this backup.");
  }
  if (locked) {
    // A locked vault has no recoverable session key. Importing a backup starts
    // a new session; old ciphertext that is not part of the backup is dead.
    writeRecords([]);
  }
  for (const note of notes) {
    await putNote(note, true);
  }
  return notes.length;
}

export function vaultStorageIsAvailable(): boolean {
  try {
    const probe = "veilpool.storage.probe";
    getStorage().setItem(probe, "1");
    getStorage().removeItem(probe);
    return true;
  } catch {
    return false;
  }
}
