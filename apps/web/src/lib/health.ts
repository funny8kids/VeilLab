import type { ApiMode, HealthStatus } from "../types";

export const INDEXER_LAG_WARN_BLOCKS = 12;
export const INDEXER_LAG_WARN_SECONDS = 120;

export interface HealthSummary {
  apiMode: ApiMode;
  chainId: number | null;
  chainService: string | null;
  indexerStatus: string | null;
  indexerLagBlocks: number | null;
  indexerLagSeconds: number | null;
  lastIndexedBlock: number | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (
      typeof value === "string" &&
      value.trim() &&
      Number.isFinite(Number(value))
    ) {
      return Number(value);
    }
  }
  return null;
}

/**
 * Health mode is the source of truth for how the UI labels the API:
 * "mock" for the in-memory chain, "local" for the Anvil + indexer stack.
 * A legacy health response without a mode is treated as mock.
 */
const HEALTH_FAILURE_STATES = new Set([
  "error",
  "failed",
  "down",
  "unavailable",
  "offline",
  "unhealthy",
]);

/**
 * "degraded" and "warning" still mean the API is reachable; the indexer panel
 * can explain the degraded state. Only hard failure states trigger demo mode.
 */
export function healthStatusIsFailure(status: string | undefined): boolean {
  return status
    ? HEALTH_FAILURE_STATES.has(status.trim().toLowerCase())
    : false;
}

export function resolveApiMode(
  health: HealthStatus | null | undefined,
): ApiMode {
  if (!health) return "mock";
  const explicit = (health.mode ?? "").toLowerCase();
  if (explicit === "local" || explicit === "anvil") return "local";
  if (explicit === "mock") return "mock";
  if (health.mock === false) return "local";
  return "mock";
}

export function summarizeHealth(
  health: HealthStatus | null | undefined,
): HealthSummary {
  const record = asRecord(health);
  const indexer = asRecord(record?.indexer);
  const services = asRecord(record?.services);

  return {
    apiMode: resolveApiMode(health),
    chainId: firstNumber(record?.chain_id, record?.chainId),
    chainService: firstString(services?.chain),
    indexerStatus: firstString(
      indexer?.status,
      indexer?.state,
      record?.indexer_status,
    ),
    indexerLagBlocks: firstNumber(
      indexer?.lag_blocks,
      indexer?.blocks_behind,
      indexer?.lag,
      record?.indexer_lag_blocks,
    ),
    indexerLagSeconds: firstNumber(
      indexer?.lag_seconds,
      record?.indexer_lag_seconds,
    ),
    lastIndexedBlock: firstNumber(
      indexer?.last_indexed_block,
      record?.last_indexed_block,
    ),
  };
}

const INDEXER_WARN_STATES = new Set([
  "stalled",
  "error",
  "offline",
  "unavailable",
  "unreachable",
  "degraded",
  "lagging",
]);

export function indexerLagIsHigh(summary: HealthSummary): boolean {
  if (
    summary.indexerLagBlocks !== null &&
    summary.indexerLagBlocks >= INDEXER_LAG_WARN_BLOCKS
  ) {
    return true;
  }
  if (
    summary.indexerLagSeconds !== null &&
    summary.indexerLagSeconds >= INDEXER_LAG_WARN_SECONDS
  ) {
    return true;
  }
  return summary.indexerStatus
    ? INDEXER_WARN_STATES.has(summary.indexerStatus.toLowerCase())
    : false;
}
