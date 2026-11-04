const FORBIDDEN_KEYS = new Set([
  "note",
  "secret",
  "note_token",
  "nullifiersecret",
  "nullifier_secret",
  "note_id",
]);

export class NoteLeakError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NoteLeakError";
  }
}

/**
 * Last line of defence for every request body. The UI never sends a note, but a
 * future refactor should fail loudly rather than leak note material.
 */
export function assertNoNoteMaterial(payload: unknown): void {
  const serialized = JSON.stringify(payload);
  if (serialized.includes("veilnote1") || serialized.includes("veilnote2")) {
    throw new NoteLeakError("Refusing to send a request containing a secret note.");
  }

  const visit = (value: unknown): void => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    for (const [key, child] of Object.entries(value)) {
      if (FORBIDDEN_KEYS.has(key.toLowerCase())) {
        throw new NoteLeakError(
          `Refusing to send a request containing the field "${key}".`,
        );
      }
      visit(child);
    }
  };

  visit(payload);
}
