import type {
  ApiMode,
  DataMode,
  LocalActivityRecord,
  Pool,
  PublicSignals,
  Relayer,
  WithdrawalQuoteRequest,
  WithdrawalSubmitRequest,
} from "../types";
import { denominationWei } from "./format";

export type DepositGateState = "missing" | "maturing" | "matured";

export function noteDepositGate(
  activity: LocalActivityRecord[],
  noteId: string,
  nowMs = Date.now(),
): { state: DepositGateState; record: LocalActivityRecord | null; matureAt: number | null } {
  const record =
    activity.find(
      (item) =>
        item.kind === "deposit" &&
        item.noteId === noteId &&
        item.status !== "failed",
    ) ?? null;
  if (!record) return { state: "missing", record: null, matureAt: null };
  if (!record.matureAt) return { state: "matured", record, matureAt: null };
  const matureAt = new Date(record.matureAt).getTime();
  return {
    state: matureAt <= nowMs ? "matured" : "maturing",
    record,
    matureAt,
  };
}

export const DEMO_GAS_ESTIMATE_WEI = "310000000000000";

export function calculateDemoAmounts(
  pool: Pool,
  relayerFeeBps: number,
): {
  denominationWei: string;
  relayerFeeWei: string;
  gasEstimateWei: string;
  recipientReceivesWei: string;
} {
  const denomination = denominationWei(pool);
  const relayerFee = (denomination * BigInt(relayerFeeBps)) / 10_000n;
  return {
    denominationWei: denomination.toString(),
    relayerFeeWei: relayerFee.toString(),
    gasEstimateWei: DEMO_GAS_ESTIMATE_WEI,
    recipientReceivesWei: (denomination - relayerFee).toString(),
  };
}

export function relayerSupportsPool(relayer: Relayer, poolId: string): boolean {
  return relayer.supported_pools.includes(poolId);
}

export function relayerAvailable(relayer: Relayer, poolId: string): boolean {
  return (
    relayerSupportsPool(relayer, poolId) &&
    relayer.status !== "offline" &&
    relayer.status !== "disabled"
  );
}

export function bestRelayer(
  relayers: Relayer[],
  poolId: string,
): Relayer | undefined {
  const compatible = relayers
    .filter((relayer) => relayerAvailable(relayer, poolId))
    .sort((left, right) => left.fee_bps - right.fee_bps);
  return compatible[0];
}

export function buildQuoteRequest(input: {
  poolId: string;
  recipientAddress: string;
  relayerId: string;
}): WithdrawalQuoteRequest {
  return {
    pool_id: input.poolId,
    recipient_address: input.recipientAddress.trim(),
    relayer_id: input.relayerId,
  };
}

export function buildPublicSignals(input: {
  root: string;
  nullifierHash: string;
  recipient: string;
  feeWei: string;
}): PublicSignals {
  return {
    root: input.root,
    nullifier_hash: input.nullifierHash,
    recipient: input.recipient.trim(),
    fee_wei: input.feeWei,
  };
}

export function buildWithdrawalSubmitRequest(input: {
  poolId: string;
  quoteId: string;
  proof: string;
  publicSignals: PublicSignals;
  recipientAddress: string;
}): WithdrawalSubmitRequest {
  // Whitelisted proof + public signals only. The note is never part of this shape.
  return {
    pool_id: input.poolId,
    quote_id: input.quoteId,
    proof: input.proof,
    public_signals: input.publicSignals,
    recipient_address: input.recipientAddress.trim(),
  };
}

export interface WithdrawGateInput {
  noteParsed: boolean;
  depositReady: boolean;
  recipientValid: boolean;
  relayerSelected: boolean;
  quoteReady: boolean;
  busy: boolean;
}

export function canRequestQuote(
  input: Omit<WithdrawGateInput, "quoteReady">,
): boolean {
  return (
    input.noteParsed &&
    input.depositReady &&
    input.recipientValid &&
    input.relayerSelected &&
    !input.busy
  );
}

export function canSubmitWithdrawal(input: WithdrawGateInput): boolean {
  return (
    input.noteParsed &&
    input.depositReady &&
    input.recipientValid &&
    input.relayerSelected &&
    input.quoteReady &&
    !input.busy
  );
}

export type WithdrawalSubmitMode =
  | "demo"
  | "api"
  | "local"
  | "local-disabled";

/**
 * Local Anvil mode is authoritative: when its quote reports
 * submission_available:true, the browser proves in a worker and submits the
 * proof to /local/withdrawals. It must never route to the mock endpoint or
 * simulate a successful withdrawal. When the API reports submission as
 * unavailable, local submission stays disabled.
 */
export function withdrawalSubmitMode(
  apiMode: ApiMode | null,
  dataMode: DataMode,
  quoteDemo: boolean,
  submissionAvailable = true,
): WithdrawalSubmitMode {
  if (apiMode === "local") {
    return submissionAvailable ? "local" : "local-disabled";
  }
  if (dataMode === "demo" || quoteDemo) return "demo";
  return "api";
}

/**
 * The quote's submission_available flag is authoritative for every mode. A
 * local quote that opts in selects the real browser-proof path; it never falls
 * back to the mock withdrawal route.
 */
export function withdrawalIsBlocked(
  apiMode: ApiMode | null,
  dataMode: DataMode,
  quoteDemo: boolean,
  submissionAvailable: boolean,
): boolean {
  return (
    !submissionAvailable ||
    withdrawalSubmitMode(
      apiMode,
      dataMode,
      quoteDemo,
      submissionAvailable,
    ) === "local-disabled"
  );
}

export function quoteExpired(expiresAt: string | undefined): boolean {
  if (!expiresAt) return false;
  return new Date(expiresAt).getTime() <= Date.now();
}
