import type { MessageKey } from "../i18n";
import type {
  ComplianceDecision,
  LocalActivityStatus,
  Pool,
  RelayerStatus,
} from "../types";
import { isLowSet } from "./format";

export function localStatusKey(status: LocalActivityStatus): MessageKey {
  switch (status) {
    case "submitted":
      return "common.submitted";
    case "pending":
      return "common.pending";
    case "confirmed":
      return "common.confirmed";
    case "matured":
      return "common.matured";
    case "failed":
      return "common.failed";
    default:
      return "common.pending";
  }
}

export function decisionKey(decision: ComplianceDecision): MessageKey {
  switch (decision) {
    case "allow":
      return "common.allow";
    case "review":
      return "common.review";
    default:
      return "common.block";
  }
}

export function decisionTone(
  decision: ComplianceDecision,
): "ok" | "warn" | "danger" {
  if (decision === "allow") return "ok";
  if (decision === "review") return "warn";
  return "danger";
}

export function poolStatusKey(pool: Pool): MessageKey {
  if (pool.status === "paused") return "common.paused";
  if (isLowSet(pool)) return "common.lowSet";
  return "common.active";
}

export function poolStatusTone(pool: Pool): "ok" | "warn" | "danger" {
  if (pool.status === "paused") return "danger";
  if (isLowSet(pool)) return "warn";
  return "ok";
}

export function relayerStatusKey(status: RelayerStatus): MessageKey {
  if (status === "offline" || status === "disabled") return "common.offline";
  if (status === "degraded") return "common.degraded";
  return "common.online";
}

export function relayerStatusTone(status: RelayerStatus): "ok" | "warn" | "danger" {
  if (status === "offline" || status === "disabled") return "danger";
  if (status === "degraded") return "warn";
  return "ok";
}
