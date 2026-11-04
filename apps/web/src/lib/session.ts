export const AUTO_LOCK_MS = 15 * 60 * 1000;
export const AUTO_LOCK_CHECK_MS = 15 * 1000;

export function shouldAutoLock(
  lastActivityAt: number,
  now = Date.now(),
  timeoutMs = AUTO_LOCK_MS,
): boolean {
  if (!Number.isFinite(lastActivityAt) || lastActivityAt <= 0) return true;
  return now - lastActivityAt >= timeoutMs;
}

/**
 * A vault is locked only when it has notes that cannot be opened because the
 * random session key is gone. An empty vault has nothing to unlock.
 */
export function vaultIsLocked(
  sessionUnlocked: boolean,
  noteCount: number,
): boolean {
  return !sessionUnlocked && noteCount > 0;
}
