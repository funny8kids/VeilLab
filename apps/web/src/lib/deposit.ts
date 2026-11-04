import type {
  ApiMode,
  DataMode,
  DepositIntentRequest,
  LocalActivityStatus,
  LocalDepositInstruction,
  LocalDepositRequest,
  MockDepositRequest,
} from "../types";
import { ApiError } from "./api";

export type DepositRoute = "demo" | "mock" | "local";

export function depositRoute(
  apiMode: ApiMode | null,
  dataMode: DataMode,
): DepositRoute {
  // apiMode is null only while health is unknown or the API is unreachable.
  // Once health reports a mode we trust it even if resource loading is still
  // in progress, so a local API is never mistaken for the demo fixture path.
  if (apiMode === "local") return "local";
  if (apiMode === "mock") return "mock";
  return dataMode === "demo" ? "demo" : "mock";
}

export interface DepositGateInput {
  notePresent: boolean;
  backupConfirmed: boolean;
  submitting?: boolean;
}

/**
 * Product boundary: a deposit cannot be confirmed until a note exists and the
 * user has explicitly confirmed they saved a backup.
 */
export function canConfirmDeposit(input: DepositGateInput): boolean {
  return input.notePresent && input.backupConfirmed && !input.submitting;
}

export function buildDepositIntentRequest(input: {
  poolId: string;
  depositorAddress: string;
  amount: string;
  commitment: string;
}): DepositIntentRequest {
  // Whitelisted object: no note, secret or nullifier material can enter here.
  return {
    pool_id: input.poolId,
    depositor_address: input.depositorAddress.trim(),
    amount: input.amount,
    commitment: input.commitment,
  };
}

export function buildMockDepositRequest(input: {
  intentId: string;
  commitment: string;
}): MockDepositRequest {
  // The mock on-chain event needs the public commitment, never the note.
  return {
    intent_id: input.intentId,
    commitment: input.commitment,
  };
}

export function buildLocalDepositRequest(input: {
  intentId: string;
  commitment: string;
}): LocalDepositRequest {
  // The local Anvil route also receives only the public intent id and commitment.
  return {
    intent_id: input.intentId,
    commitment: input.commitment,
  };
}

export type LocalDepositFailure =
  | { kind: "disabled"; instruction: LocalDepositInstruction }
  | {
      kind: "unconfirmed";
      retryable: boolean;
      txHash?: string;
      code?: string;
      message: string;
    };

function readDetailString(
  details: Record<string, unknown> | undefined,
  keys: string[],
): string | undefined {
  if (!details) return undefined;
  for (const key of keys) {
    const value = details[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return undefined;
}

/**
 * Maps a local-chain deposit error to an honest UI state. A 409 with manual
 * calldata instructions is not a success, and a timeout is not confirmation.
 */
export function describeLocalDepositFailure(
  error: unknown,
): LocalDepositFailure {
  if (!(error instanceof ApiError)) {
    return {
      kind: "unconfirmed",
      retryable: false,
      message:
        error instanceof Error ? error.message : "The local deposit failed.",
    };
  }

  const details =
    error.details && typeof error.details === "object"
      ? error.details
      : undefined;
  const code =
    error.code ??
    readDetailString(details, ["code", "error_code"]);
  const contractAddress = readDetailString(details, [
    "contract_address",
    "contractAddress",
  ]);
  const denominationWei = readDetailString(details, [
    "denomination_wei",
    "denominationWei",
  ]);
  const calldata = readDetailString(details, ["calldata", "data"]);
  const instruction = readDetailString(details, [
    "instruction",
    "instructions",
  ]);
  const disabled =
    code === "LOCAL_DEPOSIT_DISABLED" ||
    (error.status === 409 &&
      Boolean(contractAddress && (calldata || instruction)));

  if (disabled) {
    return {
      kind: "disabled",
      instruction: {
        contractAddress,
        denominationWei,
        calldata,
        instruction,
      },
    };
  }

  const txHash = readDetailString(details, ["tx_hash", "txHash"]);
  const retryable =
    error.status === 502 ||
    error.status === 503 ||
    error.status === 504 ||
    code === "INDEXER_CONFIRMATION_TIMEOUT";

  return {
    kind: "unconfirmed",
    retryable,
    txHash,
    code,
    message: error.message,
  };
}

/**
 * Local deposits may be pending while the indexer catches up. "confirmed" is
 * only used after the caller has verified that the response carried a tx hash.
 */
export function localDepositActivityStatus(
  status: string | undefined,
): LocalActivityStatus {
  const normalized = (status ?? "").toLowerCase();
  if (
    normalized === "failed" ||
    normalized === "reverted" ||
    normalized === "dropped" ||
    normalized === "error"
  ) {
    return "failed";
  }
  if (
    normalized === "pending" ||
    normalized === "submitted" ||
    normalized === "queued" ||
    normalized === "mempool"
  ) {
    return "pending";
  }
  if (
    !normalized ||
    normalized === "confirmed" ||
    normalized === "success" ||
    normalized === "mined" ||
    normalized === "finalized"
  ) {
    return "confirmed";
  }
  // Unknown statuses stay pending until the API reports an explicit confirmation.
  return "pending";
}
