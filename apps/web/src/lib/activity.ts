import type { LocalActivityRecord, LocalActivityStatus } from "../types";

const ACTIVITY_KEY = "veilpool.activity.v1";
const MAX_RECORDS = 100;

function storageAvailable(): boolean {
  return typeof localStorage !== "undefined";
}

export function readActivity(): LocalActivityRecord[] {
  if (!storageAvailable()) return [];
  try {
    const raw = localStorage.getItem(ACTIVITY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as LocalActivityRecord[])
      .filter((record) => record && typeof record.id === "string")
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
  } catch {
    return [];
  }
}

export function addActivity(record: LocalActivityRecord): LocalActivityRecord[] {
  if (!storageAvailable()) return [record];
  const next = [record, ...readActivity()].slice(0, MAX_RECORDS);
  localStorage.setItem(ACTIVITY_KEY, JSON.stringify(next));
  return next;
}

export function removeActivity(id: string): LocalActivityRecord[] {
  if (!storageAvailable()) return [];
  const next = readActivity().filter((record) => record.id !== id);
  localStorage.setItem(ACTIVITY_KEY, JSON.stringify(next));
  return next;
}

export function clearActivity(): void {
  if (!storageAvailable()) return;
  localStorage.removeItem(ACTIVITY_KEY);
}

export function effectiveStatus(
  record: LocalActivityRecord,
  now = Date.now(),
): LocalActivityStatus {
  if (
    record.kind === "deposit" &&
    record.status === "confirmed" &&
    record.matureAt &&
    new Date(record.matureAt).getTime() <= now
  ) {
    return "matured";
  }
  return record.status;
}

export function activityStatusTone(
  status: LocalActivityStatus,
): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (status) {
    case "confirmed":
    case "matured":
      return "ok";
    case "pending":
    case "submitted":
      return "warn";
    case "failed":
      return "danger";
    default:
      return "muted";
  }
}

export function exportActivity(records: LocalActivityRecord[]): string {
  return JSON.stringify(
    {
      type: "veilpool.local-activity.export",
      version: 1,
      exportedAt: new Date().toISOString(),
      warning:
        "Local browser history only. Contains no secret notes. Deposits and withdrawals are intentionally not linked by the server.",
      activity: records,
      vault: undefined,
    },
    null,
    2,
  );
}

export function countByKind(
  records: LocalActivityRecord[],
): { deposits: number; withdrawals: number } {
  return {
    deposits: records.filter((record) => record.kind === "deposit").length,
    withdrawals: records.filter((record) => record.kind === "withdrawal").length,
  };
}
