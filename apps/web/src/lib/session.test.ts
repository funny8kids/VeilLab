import { describe, expect, it } from "vitest";
import {
  AUTO_LOCK_MS,
  shouldAutoLock,
  vaultIsLocked,
} from "./session";

describe("vault auto-lock", () => {
  it("does not lock before 15 minutes of inactivity", () => {
    const lastActivity = 1_000_000;
    expect(
      shouldAutoLock(lastActivity, lastActivity + AUTO_LOCK_MS - 1),
    ).toBe(false);
  });

  it("locks at 15 minutes of inactivity", () => {
    const lastActivity = 1_000_000;
    expect(shouldAutoLock(lastActivity, lastActivity + AUTO_LOCK_MS)).toBe(true);
  });

  it("treats a missing activity timestamp as inactive", () => {
    expect(shouldAutoLock(0, 1_000_000)).toBe(true);
  });

  it("shows a locked state only when notes exist without a session key", () => {
    expect(vaultIsLocked(false, 2)).toBe(true);
    expect(vaultIsLocked(false, 0)).toBe(false);
    expect(vaultIsLocked(true, 2)).toBe(false);
  });
});
