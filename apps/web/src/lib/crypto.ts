import type { BackupEnvelope, VaultBackupEnvelope } from "../types";

const PBKDF2_ITERATIONS = 210_000;

export class BackupError extends Error {
  code: "PASSPHRASE_TOO_SHORT" | "DECRYPT_FAILED" | "BACKUP_INVALID";

  constructor(code: BackupError["code"], message: string) {
    super(message);
    this.name = "BackupError";
    this.code = code;
  }
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

export function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytes;
}

function assertPassphrase(passphrase: string): void {
  if (passphrase.trim().length < 8) {
    throw new BackupError(
      "PASSPHRASE_TOO_SHORT",
      "Use a backup passphrase with at least 8 characters.",
    );
  }
}

async function derivePassphraseKey(
  passphrase: string,
  salt: Uint8Array,
  iterations: number,
): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: salt as unknown as BufferSource,
      iterations,
      hash: "SHA-256",
    },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function encryptWithPassphrase(
  plaintext: string,
  passphrase: string,
): Promise<BackupEnvelope["cipher"]> {
  assertPassphrase(passphrase);
  const salt = randomBytes(16);
  const iv = randomBytes(12);
  const key = await derivePassphraseKey(passphrase, salt, PBKDF2_ITERATIONS);
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as unknown as BufferSource },
    key,
    new TextEncoder().encode(plaintext),
  );

  return {
    kdf: "PBKDF2-SHA256",
    iterations: PBKDF2_ITERATIONS,
    salt: bytesToBase64(salt),
    iv: bytesToBase64(iv),
    ciphertext: bytesToBase64(new Uint8Array(ciphertext)),
  };
}

export async function decryptWithPassphrase(
  cipher: BackupEnvelope["cipher"],
  passphrase: string,
): Promise<string> {
  assertPassphrase(passphrase);
  let plaintext: ArrayBuffer;
  try {
    const salt = base64ToBytes(cipher.salt);
    const iv = base64ToBytes(cipher.iv);
    const key = await derivePassphraseKey(
      passphrase,
      salt,
      cipher.iterations || PBKDF2_ITERATIONS,
    );
    plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: iv as unknown as BufferSource },
      key,
      base64ToBytes(cipher.ciphertext) as unknown as BufferSource,
    );
  } catch {
    throw new BackupError(
      "DECRYPT_FAILED",
      "The backup could not be decrypted. Check the passphrase.",
    );
  }
  return new TextDecoder().decode(plaintext);
}

export async function importSessionKey(rawKey: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    base64ToBytes(rawKey) as unknown as BufferSource,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function encryptWithKey(
  plaintext: string,
  key: CryptoKey,
): Promise<{ iv: string; ciphertext: string }> {
  const iv = randomBytes(12);
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv as unknown as BufferSource },
    key,
    new TextEncoder().encode(plaintext),
  );
  return {
    iv: bytesToBase64(iv),
    ciphertext: bytesToBase64(new Uint8Array(ciphertext)),
  };
}

export async function decryptWithKey(
  ciphertext: string,
  iv: string,
  key: CryptoKey,
): Promise<string> {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64ToBytes(iv) as unknown as BufferSource },
    key,
    base64ToBytes(ciphertext) as unknown as BufferSource,
  );
  return new TextDecoder().decode(plaintext);
}

export function parseNoteBackup(raw: string): BackupEnvelope {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new BackupError("BACKUP_INVALID", "The backup file is not valid JSON.");
  }
  const envelope = parsed as Partial<BackupEnvelope>;
  if (
    !envelope ||
    envelope.type !== "veilpool.note.backup" ||
    envelope.version !== 1 ||
    !envelope.cipher ||
    envelope.cipher.kdf !== "PBKDF2-SHA256" ||
    typeof envelope.cipher.ciphertext !== "string"
  ) {
    throw new BackupError("BACKUP_INVALID", "The backup file has an unknown format.");
  }
  return envelope as BackupEnvelope;
}

export function parseVaultBackup(raw: string): VaultBackupEnvelope {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new BackupError("BACKUP_INVALID", "The backup file is not valid JSON.");
  }
  const envelope = parsed as Partial<VaultBackupEnvelope>;
  if (
    !envelope ||
    envelope.type !== "veilpool.vault.backup" ||
    envelope.version !== 1 ||
    !Array.isArray(envelope.notes)
  ) {
    throw new BackupError("BACKUP_INVALID", "The vault backup has an unknown format.");
  }
  return envelope as VaultBackupEnvelope;
}
