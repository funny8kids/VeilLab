import { describe, expect, it } from "vitest";
import {
  decryptWithPassphrase,
  encryptWithPassphrase,
} from "./crypto";

describe("encrypted note backup", () => {
  it("round-trips a note backup with the correct passphrase", async () => {
    const cipher = await encryptWithPassphrase(
      JSON.stringify({ token: "veilnote1test" }),
      "correct horse battery",
    );
    const plaintext = await decryptWithPassphrase(
      cipher,
      "correct horse battery",
    );
    expect(plaintext).toContain("veilnote1test");
    expect(cipher.ciphertext).not.toContain("veilnote1test");
  });

  it("rejects a short passphrase", async () => {
    await expect(encryptWithPassphrase("secret", "short")).rejects.toThrow();
  });

  it("fails with the wrong passphrase", async () => {
    const cipher = await encryptWithPassphrase("secret", "long enough pass");
    await expect(
      decryptWithPassphrase(cipher, "different pass"),
    ).rejects.toThrow();
  });
});
