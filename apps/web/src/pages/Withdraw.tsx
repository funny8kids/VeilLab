import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useI18n } from "../i18n";
import { useApp } from "../state/AppContext";
import { api, ApiError, shouldFallbackToDemo } from "../lib/api";
import {
  createDemoQuote,
  DEMO_ROOT,
} from "../lib/demoData";
import { makeDemoTxHash } from "../lib/download";
import {
  activityStatusTone,
} from "../lib/activity";
import {
  formatAssetAmount,
  formatBps,
  formatInteger,
  formatLocalTime,
  isEvmAddress,
  poolLabel,
  truncateMiddle,
} from "../lib/format";
import { decisionKey, decisionTone, localStatusKey } from "../lib/labels";
import {
  buildMockProof,
  parseNote,
  type NotePayloadV2,
  type VeilNote,
} from "../lib/note";
import {
  buildLocalWithdrawalRequest,
  ProverError,
  proveWithdrawal,
  type ProverStage,
} from "../lib/prover";
import {
  getNote,
  listVaultNotes,
  unspentVaultNotes,
  type VaultNoteEntry,
} from "../lib/vault";
import {
  bestRelayer,
  buildPublicSignals,
  buildQuoteRequest,
  buildWithdrawalSubmitRequest,
  calculateDemoAmounts,
  canRequestQuote,
  canSubmitWithdrawal,
  noteDepositGate,
  relayerAvailable,
  relayerSupportsPool,
  withdrawalIsBlocked,
  withdrawalSubmitMode,
} from "../lib/withdraw";
import { Icon } from "../components/Icon";
import {
  Badge,
  MockTag,
  PageHead,
  StepBar,
  SummaryRow,
} from "../components/ui";
import { useNow } from "../hooks/useNow";
import type {
  ComplianceDecision,
  LocalActivityStatus,
  Pool,
  Relayer,
  WithdrawalQuoteResponse,
  WithdrawalSubmitResponse,
} from "../types";

type ParseState = "idle" | "parsing" | "valid" | "invalid";

interface QuoteView {
  quoteId: string;
  relayerFeeWei: string;
  gasEstimateWei: string;
  receivesWei: string;
  expiresAt: string;
  compliance: ComplianceDecision;
  demo: boolean;
  submissionAvailable: boolean;
  warning?: string;
}

interface WithdrawResult {
  withdrawalId: string;
  txHash: string;
  status: LocalActivityStatus;
  demo: boolean;
  local?: boolean;
  relayerName: string;
  pool: Pool;
  recipient: string;
  nullifierHash: string;
  compliance: ComplianceDecision;
  noteId: string;
  proof?: string;
  blockNumber?: number;
  feeWei?: string;
  proofDurationMs?: number;
  localChain?: string;
  verifierKind?: string;
}

const LOCAL_PHASE_STEPS = [
  "path",
  "loading",
  "proving",
  "verifying",
  "submitting",
  "confirmed",
] as const;

type LocalWithdrawPhase = "idle" | (typeof LOCAL_PHASE_STEPS)[number];

function phaseMessageKey(
  phase: (typeof LOCAL_PHASE_STEPS)[number],
):
  | "withdraw.local.phase.path"
  | "withdraw.local.phase.loading"
  | "withdraw.local.phase.proving"
  | "withdraw.local.phase.verifying"
  | "withdraw.local.phase.submitting"
  | "withdraw.local.phase.confirmed" {
  switch (phase) {
    case "path":
      return "withdraw.local.phase.path";
    case "loading":
      return "withdraw.local.phase.loading";
    case "proving":
      return "withdraw.local.phase.proving";
    case "verifying":
      return "withdraw.local.phase.verifying";
    case "submitting":
      return "withdraw.local.phase.submitting";
    case "confirmed":
      return "withdraw.local.phase.confirmed";
  }
}

function formatDurationMs(ms: number): string {
  return `${(Math.max(0, ms) / 1000).toFixed(1)}s`;
}

function relayerShortName(relayer: Relayer): string {
  return relayer.name;
}

export function WithdrawPage() {
  const { t, lang } = useI18n();
  const {
    pools,
    relayers,
    activity,
    dataMode,
    apiMode,
    vault,
    sessionUnlocked,
    vaultLocked,
    recordActivity,
    markVaultSpent,
    notify,
  } = useApp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const now = useNow(15_000);
  const parseSequence = useRef(0);

  const requestedRelayer = searchParams.get("relayer");
  const [relayerId, setRelayerId] = useState(requestedRelayer ?? "");
  const [noteInput, setNoteInput] = useState("");
  const [parsedNote, setParsedNote] = useState<VeilNote | null>(null);
  const [parseState, setParseState] = useState<ParseState>("idle");
  const [parseError, setParseError] = useState<string | null>(null);
  const [recipient, setRecipient] = useState("");
  const [quote, setQuote] = useState<QuoteView | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proof, setProof] = useState<string | null>(null);
  const [result, setResult] = useState<WithdrawResult | null>(null);
  const [localPhase, setLocalPhase] = useState<LocalWithdrawPhase>("idle");
  const [proofStartedAt, setProofStartedAt] = useState<number | null>(null);
  const [liveProofMs, setLiveProofMs] = useState(0);
  const [proofDurationMs, setProofDurationMs] = useState<number | null>(null);
  const [vaultOpen, setVaultOpen] = useState(false);
  const [vaultLoading, setVaultLoading] = useState(false);
  const [vaultEntries, setVaultEntries] = useState<VaultNoteEntry[]>([]);
  const [vaultError, setVaultError] = useState<string | null>(null);
  const [vaultSelection, setVaultSelection] = useState<VeilNote | null>(null);

  const pool = useMemo(
    () =>
      parsedNote
        ? pools.find((item) => item.id === parsedNote.payload.poolId) ?? null
        : null,
    [pools, parsedNote],
  );
  const selectedRelayer = useMemo(
    () => relayers.find((item) => item.id === relayerId) ?? null,
    [relayers, relayerId],
  );
  const selectedRelayerOk = Boolean(
    selectedRelayer &&
      pool &&
      relayerAvailable(selectedRelayer, pool.id),
  );
  const recipientValid = isEvmAddress(recipient);
  const depositGate = useMemo(
    () =>
      parsedNote
        ? noteDepositGate(activity, parsedNote.payload.id, now)
        : { state: "missing" as const, record: null, matureAt: null },
    [activity, parsedNote, now],
  );
  const depositReady = depositGate.state === "matured";
  const quoteIsExpired = quote
    ? new Date(quote.expiresAt).getTime() <= now
    : false;
  const quoteReady = Boolean(
    quote &&
      !quoteIsExpired &&
      quote.compliance === "allow",
  );
  const busy = quoting || submitting;
  const localMode = apiMode === "local";
  const submitMode = withdrawalSubmitMode(
    apiMode,
    dataMode,
    quote?.demo ?? false,
    quote?.submissionAvailable !== false,
  );
  const withdrawalsDisabled = withdrawalIsBlocked(
    apiMode,
    dataMode,
    quote?.demo ?? false,
    quote?.submissionAvailable !== false,
  );
  const noteNeedsV2 = Boolean(
    localMode && parsedNote && parsedNote.payload.v !== 2,
  );

  const bestCompatible = pool ? bestRelayer(relayers, pool.id) : undefined;

  useEffect(() => {
    if (proofStartedAt === null) return;
    const timer = window.setInterval(() => {
      setLiveProofMs(performance.now() - proofStartedAt);
    }, 200);
    return () => window.clearInterval(timer);
  }, [proofStartedAt]);

  useEffect(() => {
    if (!pool) return;
    const current = relayers.find((item) => item.id === relayerId);
    if (!current || !relayerAvailable(current, pool.id)) {
      const best = bestRelayer(relayers, pool.id);
      if (best) setRelayerId(best.id);
    }
  }, [pool, relayers, relayerId]);

  useEffect(() => {
    if (!vaultOpen) return;
    if (!sessionUnlocked) {
      setVaultEntries([]);
      setVaultLoading(false);
      setVaultError(null);
      return;
    }
    let cancelled = false;
    setVaultLoading(true);
    setVaultError(null);
    void listVaultNotes()
      .then((entries) => {
        if (cancelled) return;
        setVaultEntries(unspentVaultNotes(entries));
      })
      .catch(() => {
        if (cancelled) return;
        setVaultEntries([]);
        setVaultError(t("withdraw.vault.loadFailed"));
      })
      .finally(() => {
        if (!cancelled) setVaultLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [vaultOpen, sessionUnlocked, vault, t]);

  useEffect(() => {
    if (!vaultLocked) return;
    // A locked vault must not leave decrypted note material in this screen.
    setVaultSelection(null);
    setParsedNote(null);
    setParseState("idle");
    setParseError(null);
    setNoteInput("");
    setQuote(null);
    setProof(null);
    setError(null);
    setLocalPhase("idle");
    setProofStartedAt(null);
    setLiveProofMs(0);
    setProofDurationMs(null);
  }, [vaultLocked]);

  const resetLocalProgress = () => {
    setLocalPhase("idle");
    setProofStartedAt(null);
    setLiveProofMs(0);
    setProofDurationMs(null);
  };

  const invalidateQuote = () => {
    setQuote(null);
    setProof(null);
    setError(null);
    resetLocalProgress();
  };

  const handleNoteInput = (value: string) => {
    setVaultSelection(null);
    setNoteInput(value);
    invalidateQuote();
    setResult(null);
    const sequence = parseSequence.current + 1;
    parseSequence.current = sequence;

    if (!value.trim()) {
      setParsedNote(null);
      setParseState("idle");
      setParseError(null);
      return;
    }

    setParseState("parsing");
    setParseError(null);
    setParsedNote(null);

    void (async () => {
      try {
        const note = await parseNote(value);
        if (parseSequence.current !== sequence) return;
        if (!pools.some((item) => item.id === note.payload.poolId)) {
          setParsedNote(null);
          setParseState("invalid");
          setParseError(t("withdraw.note.unknownPool"));
          return;
        }
        setParsedNote(note);
        setParseState("valid");
        setParseError(null);
      } catch {
        if (parseSequence.current !== sequence) return;
        setParsedNote(null);
        setParseState("invalid");
        setParseError(t("withdraw.note.invalid"));
      }
    })();
  };

  const handleVaultSelect = async (entry: VaultNoteEntry) => {
    setVaultError(null);
    try {
      const note = await getNote(entry.id);
      if (!note) {
        setVaultError(t("withdraw.vault.missing"));
        return;
      }
      if (!pools.some((item) => item.id === note.payload.poolId)) {
        setVaultError(t("withdraw.note.unknownPool"));
        return;
      }
      parseSequence.current += 1;
      invalidateQuote();
      setResult(null);
      setNoteInput("");
      setVaultSelection(note);
      setParsedNote(note);
      setParseState("valid");
      setParseError(null);
      setVaultOpen(false);
    } catch {
      setVaultError(t("withdraw.vault.openFailed"));
    }
  };

  const handleClearVaultSelection = () => {
    setVaultSelection(null);
    setNoteInput("");
    setParsedNote(null);
    setParseState("idle");
    setParseError(null);
    invalidateQuote();
    setResult(null);
  };

  const handleRecipientChange = (value: string) => {
    setRecipient(value);
    invalidateQuote();
  };

  const handleRelayerChange = (id: string) => {
    setRelayerId(id);
    invalidateQuote();
  };

  const describeError = (requestError: unknown): string => {
    if (requestError instanceof ApiError) {
      const suffix = requestError.code
        ? ` (${requestError.code})`
        : ` (${requestError.status})`;
      if (requestError.status === 403) {
        return `${t("withdraw.compliance.block")}${suffix}`;
      }
      if (requestError.code === "NULLIFIER_SPENT") {
        return `${t("withdraw.error.nullifier")}${suffix}`;
      }
      if (requestError.code === "QUOTE_EXPIRED") {
        return `${t("withdraw.error.quoteExpired")}${suffix}`;
      }
      if (requestError.code === "PROOF_INVALID") {
        return `${t("withdraw.error.proof")}${suffix}`;
      }
      if (
        requestError.code === "RELAYER_OFFLINE" ||
        requestError.status === 503
      ) {
        return `${t("withdraw.error.relayerOffline")}${suffix}`;
      }
      return `${t("withdraw.error.api")}${suffix}`;
    }
    return t("withdraw.error.unknown");
  };

  const describeLocalWithdrawError = (requestError: unknown): string => {
    if (requestError instanceof ProverError) {
      switch (requestError.code) {
        case "ARTIFACT_MISSING":
          return t("withdraw.local.artifactsMissing");
        case "NOTE_NOT_V2":
          return t("withdraw.local.v1Note");
        case "PATH_INVALID":
          return t("withdraw.local.pathInvalid");
        case "VERIFY_FAILED":
          return t("withdraw.local.verifyFailed");
        case "SIGNAL_MISMATCH":
          return t("withdraw.local.signalMismatch");
        case "WORKER_UNAVAILABLE":
        case "WORKER_FAILED":
          return t("withdraw.local.workerFailed");
        default:
          return `${t("withdraw.local.proveFailed")} (${requestError.code})`;
      }
    }
    if (requestError instanceof ApiError) {
      const suffix = requestError.code
        ? ` (${requestError.code})`
        : ` (${requestError.status})`;
      switch (requestError.code) {
        case "COMMITMENT_NOT_FOUND":
          return `${t("withdraw.local.pathMissing")}${suffix}`;
        case "INDEXER_UNAVAILABLE":
        case "INDEXER_TIMEOUT":
          return `${t("withdraw.local.indexerUnavailable")}${suffix}`;
        case "NULLIFIER_SPENT":
          return `${t("withdraw.error.nullifier")}${suffix}`;
        case "ROOT_STALE":
        case "UNKNOWN_ROOT":
          return `${t("withdraw.local.rootStale")}${suffix}`;
        case "QUOTE_EXPIRED":
          return `${t("withdraw.error.quoteExpired")}${suffix}`;
        case "QUOTE_CONSUMED":
          return `${t("withdraw.local.quoteConsumed")}${suffix}`;
        case "LOCAL_WITHDRAWAL_DISABLED":
          return `${t("withdraw.local.disabledByApi")}${suffix}`;
        case "INVALID_PROOF":
        case "INVALID_PUBLIC_SIGNALS":
          return `${t("withdraw.local.invalidProof")}${suffix}`;
        case "PROOF_INVALID":
          return `${t("withdraw.error.proof")}${suffix}`;
        default:
          return `${t("withdraw.error.api")}${suffix}`;
      }
    }
    return t("withdraw.error.unknown");
  };

  const handleLocalWithdrawal = async () => {
    if (!parsedNote || parsedNote.payload.v !== 2) {
      setError(t("withdraw.local.v1Note"));
      return;
    }
    if (
      !pool ||
      !depositReady ||
      !selectedRelayer ||
      !selectedRelayerOk ||
      !quote ||
      !quoteReady ||
      !recipientValid
    ) {
      setError(gateHint() ?? t("withdraw.error.unknown"));
      return;
    }

    const note: NotePayloadV2 = parsedNote.payload;
    const startedAt = performance.now();
    setSubmitting(true);
    setError(null);
    setProof(null);
    resetLocalProgress();
    setProofStartedAt(startedAt);
    setLocalPhase("path");

    try {
      const path = await api.proofPath(pool.id, note.commitment);

      setLocalPhase("loading");
      const proven = await proveWithdrawal({
        note,
        path,
        recipient,
        feeWei: quote.relayerFeeWei,
        onProgress: (stage: ProverStage) => {
          if (stage !== "done") setLocalPhase(stage);
        },
      });
      setProofDurationMs(proven.durationMs);
      setProofStartedAt(null);

      setLocalPhase("submitting");
      const request = buildLocalWithdrawalRequest({
        quoteId: quote.quoteId,
        proof: proven.proofHex,
        root: path.root,
        nullifier: note.nullifier,
        recipient,
        feeWei: quote.relayerFeeWei,
      });
      const response = await api.submitLocalWithdrawal(request);

      if (
        (response.status ?? "").toLowerCase() !== "confirmed" ||
        !response.tx_hash
      ) {
        setLocalPhase("idle");
        setError(t("withdraw.local.notConfirmed"));
        return;
      }

      const nullifier = response.nullifier ?? note.nullifier;
      const feeWei = response.fee_wei ?? quote.relayerFeeWei;
      const noteId = note.id;
      recordActivity({
        id: crypto.randomUUID(),
        kind: "withdrawal",
        poolId: pool.id,
        asset: pool.asset,
        denomination: pool.denomination,
        status: "confirmed",
        noteId,
        createdAt: new Date().toISOString(),
        recipient,
        relayerName: selectedRelayer.name,
        txHash: response.tx_hash,
        compliance: quote.compliance,
        demo: false,
      });
      markVaultSpent(noteId);
      setLocalPhase("confirmed");
      setResult({
        withdrawalId: response.withdrawal_id ?? "—",
        txHash: response.tx_hash,
        status: "confirmed",
        demo: false,
        local: true,
        relayerName: relayerShortName(selectedRelayer),
        pool,
        recipient,
        nullifierHash: nullifier,
        compliance: quote.compliance,
        noteId,
        blockNumber: response.block_number,
        feeWei,
        proofDurationMs: proven.durationMs,
        localChain: response.local_chain ?? "ANVIL",
        verifierKind: response.verifier_kind ?? "groth16-poseidon",
      });
      setNoteInput("");
      setVaultSelection(null);
      setParsedNote(null);
      setParseState("idle");
      setParseError(null);
      setQuote(null);
      setProof(null);
      setError(null);
      notify(t("withdraw.success.cleared"));
    } catch (requestError) {
      setLocalPhase("idle");
      setError(describeLocalWithdrawError(requestError));
    } finally {
      setSubmitting(false);
      setProofStartedAt(null);
    }
  };

  const gateHint = (): string | null => {
    if (!parsedNote) return t("withdraw.error.noteRequired");
    if (localMode && parsedNote.payload.v !== 2) {
      return t("withdraw.local.v1Note");
    }
    if (depositGate.state === "missing") {
      return t("withdraw.error.depositMissing");
    }
    if (depositGate.state === "maturing") {
      return t("withdraw.error.maturity");
    }
    if (!recipientValid) return t("withdraw.error.address");
    if (!selectedRelayer || !selectedRelayerOk) {
      return t("withdraw.error.relayer");
    }
    if (!quote) return t("withdraw.error.quote");
    if (quote.compliance === "review") {
      return t("withdraw.compliance.review");
    }
    if (quote.compliance === "block") {
      return t("withdraw.compliance.block");
    }
    if (quoteIsExpired) return t("withdraw.error.quoteExpired");
    return null;
  };

  const handleQuote = async () => {
    if (!parsedNote || !pool || !selectedRelayer || !selectedRelayerOk) {
      setError(gateHint() ?? t("withdraw.error.unknown"));
      return;
    }
    if (!depositReady) {
      setError(gateHint() ?? t("withdraw.error.maturity"));
      return;
    }
    if (!recipientValid) {
      setError(t("withdraw.error.address"));
      return;
    }

    setQuoting(true);
    setError(null);
    setProof(null);
    const payload = buildQuoteRequest({
      poolId: pool.id,
      recipientAddress: recipient,
      relayerId: selectedRelayer.id,
    });

    try {
      let response: WithdrawalQuoteResponse;
      // Local Anvil mode is authoritative: never substitute a demo quote or a
      // mock withdrawal path there, even if the API request fails.
      let demo = dataMode === "demo" && !localMode;
      if (demo) {
        const amounts = calculateDemoAmounts(pool, selectedRelayer.fee_bps);
        response = createDemoQuote(
          pool,
          selectedRelayer,
          amounts.recipientReceivesWei,
          amounts.relayerFeeWei,
          amounts.gasEstimateWei,
        );
      } else {
        try {
          response = await api.createWithdrawalQuote(payload);
        } catch (requestError) {
          if (localMode || !shouldFallbackToDemo(requestError)) {
            throw requestError;
          }
          const amounts = calculateDemoAmounts(pool, selectedRelayer.fee_bps);
          response = createDemoQuote(
            pool,
            selectedRelayer,
            amounts.recipientReceivesWei,
            amounts.relayerFeeWei,
            amounts.gasEstimateWei,
          );
          demo = true;
        }
      }

      const compliance: ComplianceDecision =
        response.compliance?.decision === "review" ||
        response.compliance?.decision === "block"
          ? response.compliance.decision
          : "allow";

      setQuote({
        quoteId: response.quote_id,
        relayerFeeWei: response.relayer_fee_wei,
        gasEstimateWei: response.gas_estimate_wei,
        receivesWei: response.recipient_receives_wei,
        expiresAt: response.expires_at,
        compliance,
        demo,
        submissionAvailable: response.submission_available !== false,
        warning: response.warning,
      });
      if (compliance === "block") {
        setError(t("withdraw.compliance.block"));
      }
    } catch (requestError) {
      setError(describeError(requestError));
    } finally {
      setQuoting(false);
    }
  };

  const handleSubmit = async () => {
    if (
      !parsedNote ||
      !pool ||
      !depositReady ||
      !selectedRelayer ||
      !selectedRelayerOk ||
      !quote ||
      !quoteReady ||
      !recipientValid
    ) {
      setError(gateHint() ?? t("withdraw.error.unknown"));
      return;
    }

    if (withdrawalsDisabled) {
      // Do not contact the mock withdrawal route or simulate a local success.
      setError(
        localMode
          ? t("withdraw.local.disabledBody")
          : t("withdraw.unavailable.body"),
      );
      return;
    }

    if (submitMode === "local") {
      // Real browser-local Groth16 path. This branch never falls back to mock.
      await handleLocalWithdrawal();
      return;
    }

    setSubmitting(true);
    setError(null);
    let demo = quote.demo;

    try {
      let root = DEMO_ROOT;
      if (dataMode !== "demo") {
        try {
          const rootResponse = await api.poolRoot(pool.id);
          root = rootResponse.root;
        } catch (rootError) {
          if (!shouldFallbackToDemo(rootError)) throw rootError;
          root = DEMO_ROOT;
          demo = true;
        }
      }

      const mockProof = await buildMockProof({
        poolId: pool.id,
        nullifierHash: parsedNote.nullifierHash,
        root,
        recipient,
      });
      setProof(mockProof);

      const publicSignals = buildPublicSignals({
        root,
        nullifierHash: parsedNote.nullifierHash,
        recipient,
        feeWei: quote.relayerFeeWei,
      });
      const payload = buildWithdrawalSubmitRequest({
        poolId: pool.id,
        quoteId: quote.quoteId,
        proof: mockProof,
        publicSignals,
        recipientAddress: recipient,
      });

      let response: WithdrawalSubmitResponse;
      if (demo || dataMode === "demo") {
        demo = true;
        response = {
          withdrawal_id: `wdr_demo_${quote.quoteId.slice(-8)}`,
          status: "submitted",
          tx_hash: makeDemoTxHash(
            `${parsedNote.nullifierHash}|${quote.quoteId}|${recipient}`,
          ),
          relayer_id: selectedRelayer.id,
        };
      } else {
        try {
          response = await api.submitWithdrawal(
            payload,
            crypto.randomUUID(),
          );
        } catch (requestError) {
          if (!shouldFallbackToDemo(requestError)) throw requestError;
          demo = true;
          response = {
            withdrawal_id: `wdr_demo_${quote.quoteId.slice(-8)}`,
            status: "submitted",
            tx_hash: makeDemoTxHash(
              `${parsedNote.nullifierHash}|${quote.quoteId}|${recipient}`,
            ),
            relayer_id: selectedRelayer.id,
          };
        }
      }

      const status: LocalActivityStatus =
        response.status === "confirmed"
          ? "confirmed"
          : response.status === "failed"
            ? "failed"
            : "submitted";

      const noteId = parsedNote.payload.id;
      recordActivity({
        id: crypto.randomUUID(),
        kind: "withdrawal",
        poolId: pool.id,
        asset: pool.asset,
        denomination: pool.denomination,
        status,
        noteId,
        createdAt: new Date().toISOString(),
        recipient,
        relayerName: selectedRelayer.name,
        txHash: response.tx_hash,
        compliance: quote.compliance,
        demo,
      });
      markVaultSpent(noteId);
      setResult({
        withdrawalId: response.withdrawal_id,
        txHash: response.tx_hash,
        status,
        demo,
        relayerName: relayerShortName(selectedRelayer),
        pool,
        recipient,
        nullifierHash: parsedNote.nullifierHash,
        compliance: quote.compliance,
        noteId,
        proof: mockProof,
      });
      setNoteInput("");
      setVaultSelection(null);
      setParsedNote(null);
      setParseState("idle");
      setParseError(null);
      setQuote(null);
      setProof(null);
      setError(null);
      notify(t("withdraw.success.cleared"));
    } catch (requestError) {
      setError(describeError(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  const resetWithdrawal = () => {
    setResult(null);
    setNoteInput("");
    setVaultSelection(null);
    setVaultOpen(false);
    setParsedNote(null);
    setParseState("idle");
    setParseError(null);
    setRecipient("");
    setQuote(null);
    setProof(null);
    setError(null);
    setSubmitting(false);
    setQuoting(false);
    resetLocalProgress();
  };

  const step = result ? 4 : quote ? 3 : selectedRelayer && parsedNote ? 2 : 1;
  const localPhaseIndex =
    localPhase === "idle" ? -1 : LOCAL_PHASE_STEPS.indexOf(localPhase);

  const previewAmounts = useMemo(() => {
    if (!pool || !selectedRelayer) return null;
    return calculateDemoAmounts(pool, selectedRelayer.fee_bps);
  }, [pool, selectedRelayer]);

  if (result) {
    return (
      <section className="screen active" id="withdraw">
        <PageHead
          eyebrow={t("withdraw.eyebrow")}
          title={t("withdraw.title")}
          subtitle={t("withdraw.sub")}
          actions={
            <span className="badge testnet">
              <span className="dot" />
              {t("shell.testnet")}
            </span>
          }
        />
        <StepBar
          current={4}
          steps={[
            t("withdraw.step.note"),
            t("withdraw.step.relayer"),
            t("withdraw.step.proof"),
            t("withdraw.step.receive"),
          ]}
        />
        <div className="grid main-grid">
          <div className="card span-7">
            <div className="card-h">
              <div className="result-card-title">
                <div className="card-title">
                  {result.local
                    ? t("withdraw.success.localTitle")
                    : t("withdraw.success.title")}
                </div>
                {result.local ? (
                  <Badge tone="violet">{t("withdraw.proof.zkBadge")}</Badge>
                ) : (
                  <MockTag />
                )}
                <Badge
                  tone={result.demo || result.local ? "warn" : "info"}
                  dot
                >
                  {result.demo
                    ? t("shell.mode.demo")
                    : result.local
                      ? t("shell.mode.anvilLocal")
                      : t("shell.mode.mockChain")}
                </Badge>
              </div>
              <div className="right">
                <Badge tone={decisionTone(result.compliance)}>
                  {t(decisionKey(result.compliance))}
                </Badge>
              </div>
            </div>
            <div className="card-b pad">
              <div className="result-panel">
                <div className="result-hero">
                  <div className="result-icon">
                    <Icon name="check" />
                  </div>
                  <div>
                    <div className="result-title">
                      {poolLabel(result.pool)} ·{" "}
                      {t(localStatusKey(result.status))}
                    </div>
                    <div className="result-sub">
                      {result.local
                        ? t("withdraw.success.localBody")
                        : t("withdraw.success.body")}
                    </div>
                  </div>
                </div>

                <div className="result-row">
                  <span>{t("withdraw.success.withdrawalId")}</span>
                  <span className="v">{result.withdrawalId}</span>
                </div>
                <div className="result-row">
                  <span>{t("common.txHash")}</span>
                  <span className="v">{result.txHash}</span>
                </div>
                {result.local && result.blockNumber !== undefined ? (
                  <div className="result-row">
                    <span>{t("withdraw.success.block")}</span>
                    <span className="v">{result.blockNumber}</span>
                  </div>
                ) : null}
                <div className="result-row">
                  <span>{t("common.pool")}</span>
                  <span className="v">{poolLabel(result.pool)}</span>
                </div>
                <div className="result-row">
                  <span>{t("common.amount")}</span>
                  <span className="v">
                    {result.pool.denomination} {result.pool.asset}
                  </span>
                </div>
                <div className="result-row">
                  <span>{t("common.relayer")}</span>
                  <span className="v">{result.relayerName}</span>
                </div>
                <div className="result-row">
                  <span>{t("withdraw.recipient.label")}</span>
                  <span className="v">{truncateMiddle(result.recipient, 12, 10)}</span>
                </div>
                <div className="result-row">
                  <span>{t("withdraw.result.nullifier")}</span>
                  <span className="v">{truncateMiddle(result.nullifierHash, 14, 10)}</span>
                </div>
                <div className="result-row">
                  <span>{t("common.noteId")}</span>
                  <span className="v">{result.noteId}</span>
                </div>
                {result.local ? (
                  <div className="result-row">
                    <span>{t("common.relayerFee")}</span>
                    <span className="v">
                      {formatAssetAmount(result.feeWei, result.pool.asset, 6)}
                    </span>
                  </div>
                ) : null}
                <div className="result-row">
                  <span>{t("common.status")}</span>
                  <span className="v">
                    <Badge tone={activityStatusTone(result.status)} dot>
                      {t(localStatusKey(result.status))}
                    </Badge>
                  </span>
                </div>
                {result.local ? (
                  <>
                    <div className="result-row">
                      <span>{t("withdraw.success.localChain")}</span>
                      <span className="v">
                        <Badge tone="warn" dot>
                          {result.localChain ?? "ANVIL"}
                        </Badge>
                      </span>
                    </div>
                    <div className="result-row">
                      <span>{t("withdraw.success.proofTime")}</span>
                      <span className="v">
                        {result.proofDurationMs !== undefined
                          ? formatDurationMs(result.proofDurationMs)
                          : "—"}
                      </span>
                    </div>
                    <div className="result-row">
                      <span>{t("withdraw.success.verifier")}</span>
                      <span className="v">{result.verifierKind ?? "—"}</span>
                    </div>
                  </>
                ) : result.proof ? (
                  <div className="result-row">
                    <span>{t("withdraw.proof.title")}</span>
                    <span className="v">
                      {truncateMiddle(result.proof, 14, 10)}
                    </span>
                  </div>
                ) : null}

                <div className="inline-alert info" style={{ marginTop: 12 }}>
                  <Icon name="lock" />
                  <span>
                    {result.local
                      ? t("withdraw.result.localSent")
                      : t("withdraw.result.sent")}
                  </span>
                </div>

                <div className="result-actions">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => navigate("/activity")}
                  >
                    <Icon name="activity" />
                    {t("common.viewActivity")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={resetWithdrawal}
                  >
                    <Icon name="plus" />
                    {t("common.newWithdrawal")}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="span-5 settings-stack">
            <div className="card">
              <div className="card-h">
                <div className="card-title">{t("withdraw.safety.title")}</div>
                <div className="right">
                  <Badge tone="danger" dot>{t("common.important")}</Badge>
                </div>
              </div>
              <div className="card-b">
                <div className="note-warning">
                  <Icon name="alert" />
                  <span>{t("withdraw.safety.body")}</span>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-h">
                <div className="card-title">{t("activity.backup.title")}</div>
                <div className="right">
                  <Badge tone="muted">{t("common.localOnly")}</Badge>
                </div>
              </div>
              <div className="card-b pad">
                <div className="card-note">{t("withdraw.success.cleared")}</div>
                <button
                  type="button"
                  className="btn full-width"
                  style={{ marginTop: 10 }}
                  onClick={() => navigate("/activity")}
                >
                  <Icon name="activity" />
                  {t("common.viewActivity")}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="screen active" id="withdraw">
      <PageHead
        eyebrow={t("withdraw.eyebrow")}
        title={t("withdraw.title")}
        subtitle={t("withdraw.sub")}
        actions={
          <span className="badge testnet">
            <span className="dot" />
            {t("shell.testnet")}
          </span>
        }
      />

      <StepBar
        current={step}
        steps={[
          t("withdraw.step.note"),
          t("withdraw.step.relayer"),
          t("withdraw.step.proof"),
          t("withdraw.step.receive"),
        ]}
      />

      {localMode ? (
        <div className="inline-alert warn" style={{ marginBottom: 14 }}>
          <Icon name="alert" />
          <div className="alert-copy">
            <strong>{t("withdraw.local.title")}</strong>
            <div>{t("withdraw.local.body")}</div>
            <div className="card-note">{t("withdraw.local.safe")}</div>
          </div>
        </div>
      ) : null}

      <div className="grid main-grid">
        <div className="card span-7">
          <div className="card-h">
            <div className="card-title">{t("withdraw.details.title")}</div>
            <div className="right">
              <Badge tone="info" dot>{t("withdraw.localOnly")}</Badge>
            </div>
          </div>
          <div className="card-b">
            <div className="field">
              <div className="vault-field-head">
                <label>{t("withdraw.vault.title")}</label>
                <div className="vault-field-actions">
                  <Badge
                    tone={vaultLocked ? "warn" : vault.total > 0 ? "ok" : "muted"}
                  >
                    {vaultLocked
                      ? t("settings.session.locked")
                      : vault.total > 0
                        ? t("withdraw.vault.available", { count: vault.total })
                        : t("withdraw.vault.emptyBadge")}
                  </Badge>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => {
                      setVaultError(null);
                      setVaultOpen((open) => !open);
                    }}
                  >
                    <Icon name="key" />
                    {vaultOpen
                      ? t("withdraw.vault.hide")
                      : t("withdraw.vault.choose")}
                  </button>
                </div>
              </div>
              <div className="card-note" style={{ marginTop: 5 }}>
                {t("withdraw.vault.helper")}
              </div>

              {vaultLocked ? (
                <>
                  <div className="inline-alert warn" style={{ marginTop: 8 }}>
                    <Icon name="lock" />
                    <span>{t("withdraw.vault.lockedHelp")}</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm"
                    style={{ marginTop: 7 }}
                    onClick={() => navigate("/settings")}
                  >
                    <Icon name="upload" />
                    {t("withdraw.vault.importBackup")}
                  </button>
                </>
              ) : null}

              {vaultOpen && !vaultLocked ? (
                <div className="vault-note-list">
                  {vaultLoading ? (
                    <div className="parse-state">
                      <Icon name="clock" />
                      <span>{t("withdraw.vault.loading")}</span>
                    </div>
                  ) : null}
                  {vaultError ? (
                    <div className="parse-state bad">
                      <Icon name="alert" />
                      <span>{vaultError}</span>
                    </div>
                  ) : null}
                  {!vaultLoading &&
                  !vaultError &&
                  vaultEntries.length === 0 ? (
                    <div className="card-note">
                      {vault.total > 0
                        ? t("withdraw.vault.noUnspent")
                        : t("withdraw.vault.empty")}
                    </div>
                  ) : null}
                  {vaultEntries.map((entry) => {
                    const entryPool =
                      pools.find((item) => item.id === entry.poolId) ?? null;
                    const selected =
                      vaultSelection?.payload.id === entry.id;
                    return (
                      <button
                        type="button"
                        key={entry.id}
                        className={`vault-note-row${selected ? " selected" : ""}`}
                        onClick={() => void handleVaultSelect(entry)}
                        aria-pressed={selected}
                      >
                        <span className="vault-note-main">
                          <span className="vault-note-title">
                            {entryPool
                              ? poolLabel(entryPool)
                              : `${entry.asset} · ${entry.denomination}`}
                          </span>
                          <span className="vault-note-sub">
                            {entry.id} ·{" "}
                            {formatLocalTime(entry.createdAt, lang)}
                          </span>
                        </span>
                        <span className="vault-note-meta">
                          <Badge tone={entry.backedUp ? "ok" : "warn"}>
                            {entry.backedUp
                              ? t("common.backedUp")
                              : t("common.unbacked")}
                          </Badge>
                          {selected ? (
                            <Badge tone="info">
                              {t("withdraw.vault.selected")}
                            </Badge>
                          ) : null}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="secret-note">{t("withdraw.note.label")}</label>
              <textarea
                id="secret-note"
                className="textarea"
                value={
                  vaultSelection
                    ? t("withdraw.vault.masked")
                    : noteInput
                }
                onChange={(event) => handleNoteInput(event.target.value)}
                placeholder={t("withdraw.note.placeholder")}
                spellCheck={false}
                autoComplete="off"
                readOnly={Boolean(vaultSelection)}
              />
              <div className="card-note" style={{ marginTop: 5 }}>
                {vaultSelection
                  ? t("withdraw.vault.selectedHelp")
                  : t("withdraw.note.helper")}
              </div>
              {vaultSelection ? (
                <div className="parse-state ok">
                  <Icon name="check-circle" />
                  <span>
                    {t("withdraw.vault.selectedHint", {
                      noteId: vaultSelection.payload.id,
                    })}
                  </span>
                  <button
                    type="button"
                    className="link-btn"
                    onClick={handleClearVaultSelection}
                  >
                    {t("withdraw.vault.clear")}
                  </button>
                </div>
              ) : null}
              {parseState === "parsing" ? (
                <div className="parse-state">
                  <Icon name="clock" />
                  <span>{t("withdraw.note.parsing")}</span>
                </div>
              ) : null}
              {parseState === "valid" && parsedNote && pool ? (
                noteNeedsV2 ? (
                  <div className="parse-state bad">
                    <Icon name="alert" />
                    <span>{t("withdraw.local.v1Note")}</span>
                  </div>
                ) : (
                  <div className="parse-state ok">
                    <Icon name="check-circle" />
                    <span>
                      {t("withdraw.note.valid", { pool: poolLabel(pool) })}
                    </span>
                  </div>
                )
              ) : null}
              {parseState === "invalid" ? (
                <div className="parse-state bad">
                  <Icon name="alert" />
                  <span>{parseError ?? t("withdraw.note.invalid")}</span>
                </div>
              ) : null}
            </div>

            <div className="field">
              <label htmlFor="recipient-address">
                {t("withdraw.recipient.label")}
              </label>
              <input
                id="recipient-address"
                className="input"
                value={recipient}
                onChange={(event) => handleRecipientChange(event.target.value)}
                placeholder={t("withdraw.recipient.placeholder")}
                spellCheck={false}
                autoComplete="off"
              />
              <div className="card-note" style={{ marginTop: 5 }}>
                {t("withdraw.recipient.helper")}
              </div>
              {recipient.length > 0 && !recipientValid ? (
                <div className="parse-state bad">
                  <Icon name="alert" />
                  <span>{t("withdraw.recipient.invalid")}</span>
                </div>
              ) : null}
            </div>

            <div className="field">
              <label>{t("withdraw.relayer.label")}</label>
              {relayers.map((relayer, index) => {
                const available = pool
                  ? relayerAvailable(relayer, pool.id)
                  : relayer.status !== "offline" &&
                    relayer.status !== "disabled";
                const supports = pool
                  ? relayerSupportsPool(relayer, pool.id)
                  : true;
                const selected = relayer.id === relayerId;
                const isBest = pool
                  ? bestCompatible?.id === relayer.id
                  : index === 0;
                return (
                  <button
                    type="button"
                    key={relayer.id}
                    className={`relayer-row relayer-choice${
                      selected ? " selected" : ""
                    }${!available ? " disabled" : ""}`}
                    onClick={() => handleRelayerChange(relayer.id)}
                    disabled={!available}
                    aria-pressed={selected}
                  >
                    <span className="relayer-avatar">R{index + 1}</span>
                    <span className="relayer-main">
                      <span className="relayer-name">{relayer.name}</span>
                      <span className="relayer-sub">
                        {formatBps(relayer.fee_bps)} ·{" "}
                        {formatBps(relayer.uptime_bps)} {t("common.uptime")} ·{" "}
                        {relayer.latency_ms}ms
                      </span>
                    </span>
                    <span className="relayer-metric">
                      {formatBps(relayer.fee_bps)}
                    </span>
                    {isBest && available ? (
                      <Badge tone="ok" dot>{t("common.best")}</Badge>
                    ) : null}
                    {!supports ? (
                      <Badge tone="warn">{t("withdraw.relayer.incompatible")}</Badge>
                    ) : !available ? (
                      <Badge tone="danger">{t("withdraw.relayer.offline")}</Badge>
                    ) : selected ? (
                      <Badge tone="info">{t("withdraw.relayer.selected")}</Badge>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="span-5 settings-stack">
          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("withdraw.summary.title")}</div>
              <div className="right">
                {quote?.demo ? (
                  <Badge tone="warn">{t("demo.badge")}</Badge>
                ) : null}
                {quote ? (
                  <Badge tone={decisionTone(quote.compliance)}>
                    {t(decisionKey(quote.compliance))}
                  </Badge>
                ) : (
                  <Badge tone="muted">{t("demo.illustrative")}</Badge>
                )}
              </div>
            </div>
            <div className="card-b pad">
              <div className="summary">
                <SummaryRow
                  label={t("common.pool")}
                  value={pool ? poolLabel(pool) : "—"}
                />
                <SummaryRow
                  label={t("common.amount")}
                  value={
                    pool ? `${pool.denomination} ${pool.asset}` : "—"
                  }
                />
                <SummaryRow
                  label={t("withdraw.deposit.label")}
                  value={
                    depositGate.state === "missing"
                      ? t("withdraw.deposit.missing")
                      : depositGate.state === "maturing"
                        ? t("withdraw.deposit.maturing")
                        : t("withdraw.deposit.matured")
                  }
                />
                <SummaryRow
                  label={t("common.relayerFee")}
                  value={
                    pool && selectedRelayer
                      ? formatAssetAmount(
                          quote?.relayerFeeWei ??
                            previewAmounts?.relayerFeeWei,
                          pool.asset,
                          6,
                        )
                      : "—"
                  }
                />
                <SummaryRow
                  label={t("common.networkFee")}
                  value={formatAssetAmount(
                    quote?.gasEstimateWei ?? previewAmounts?.gasEstimateWei,
                    "ETH",
                    6,
                  )}
                />
                <SummaryRow
                  label={t("common.youReceive")}
                  value={
                    pool && selectedRelayer
                      ? formatAssetAmount(
                          quote?.receivesWei ??
                            previewAmounts?.recipientReceivesWei,
                          pool.asset,
                          6,
                        )
                      : "—"
                  }
                  total
                />
                <SummaryRow
                  label={t("common.anonymitySet")}
                  value={
                    pool ? formatInteger(pool.anonymity_set, lang) : "—"
                  }
                />
              </div>

              <div className="approve quote-compliance">
                <div className="t">{t("withdraw.compliance.title")}</div>
                <div className="v">
                  {quote
                    ? quote.compliance === "allow"
                      ? t("withdraw.compliance.allow")
                      : quote.compliance === "review"
                        ? t("withdraw.compliance.review")
                        : t("withdraw.compliance.block")
                    : t("withdraw.compliance.awaiting")}
                </div>
              </div>

              {quote && !quoteIsExpired ? (
                <div className="card-note" style={{ marginTop: 7 }}>
                  {t("withdraw.summary.quoteLocked", {
                    time: formatLocalTime(quote.expiresAt, lang),
                  })}
                </div>
              ) : quoteIsExpired ? (
                <div className="inline-alert warn">
                  <Icon name="alert" />
                  <span>{t("withdraw.quote.expired")}</span>
                </div>
              ) : (
                <div className="card-note" style={{ marginTop: 7 }}>
                  {t("withdraw.summary.estimate")}
                </div>
              )}

              {error ? (
                <div className="inline-alert">
                  <Icon name="alert" />
                  <span>{error}</span>
                </div>
              ) : null}

              {withdrawalsDisabled &&
              quote &&
              !quoteIsExpired &&
              quote.compliance === "allow" ? (
                <>
                  <div className="inline-alert warn" style={{ marginTop: 10 }}>
                    <Icon name="alert" />
                    <div className="alert-copy">
                      <strong>
                        {localMode
                          ? t("withdraw.local.disabledTitle")
                          : t("withdraw.unavailable.title")}
                      </strong>
                      <div>
                        {localMode
                          ? t("withdraw.local.disabledBody")
                          : t("withdraw.unavailable.body")}
                      </div>
                      {quote.warning ? (
                        <div className="card-note">{quote.warning}</div>
                      ) : null}
                      <div className="card-note">
                        {t("withdraw.local.safe")}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary full-width"
                    style={{ marginTop: 10 }}
                    disabled
                  >
                    <Icon name="lock" />
                    {localMode
                      ? t("withdraw.local.disabledButton")
                      : t("withdraw.unavailable.button")}
                  </button>
                </>
              ) : quote && !quoteIsExpired && quote.compliance === "allow" ? (
                <button
                  type="button"
                  className="btn btn-primary full-width"
                  style={{ marginTop: 10 }}
                  onClick={() => void handleSubmit()}
                  disabled={
                    submitting ||
                    noteNeedsV2 ||
                    !canSubmitWithdrawal({
                      noteParsed: Boolean(parsedNote),
                      depositReady,
                      recipientValid,
                      relayerSelected: selectedRelayerOk,
                      quoteReady,
                      busy,
                    })
                  }
                >
                  <Icon name="shield-check" />
                  {localMode
                    ? t("withdraw.local.proveButton")
                    : submitting
                      ? t("withdraw.submitting")
                      : t("withdraw.submit")}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary full-width"
                  style={{ marginTop: 10 }}
                  onClick={() => void handleQuote()}
                  disabled={
                    quoting ||
                    noteNeedsV2 ||
                    !canRequestQuote({
                      noteParsed: Boolean(parsedNote),
                      depositReady,
                      recipientValid,
                      relayerSelected: selectedRelayerOk,
                      busy,
                    })
                  }
                >
                  <Icon name="shield-check" />
                  {quoting
                    ? t("withdraw.quote.quoting")
                    : quoteIsExpired
                      ? t("withdraw.quote.refresh")
                      : quote
                        ? t("withdraw.quote.refresh")
                        : t("withdraw.quote.button")}
                </button>
              )}

              {quote &&
              !quoteIsExpired &&
              quote.compliance === "allow" ? (
                <button
                  type="button"
                  className="btn btn-sm full-width"
                  style={{ marginTop: 7 }}
                  onClick={() => void handleQuote()}
                  disabled={busy}
                >
                  <Icon name="refresh" />
                  {t("withdraw.quote.refresh")}
                </button>
              ) : null}

              <div className="card-note" style={{ marginTop: 9 }}>
                {gateHint() ?? t("withdraw.relayerNote")}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("withdraw.proof.title")}</div>
              <div className="right">
                {localMode ? (
                  <Badge tone="violet">{t("withdraw.proof.zkBadge")}</Badge>
                ) : (
                  <MockTag />
                )}
              </div>
            </div>
            <div className="card-b">
              <div className="card-note">
                {localMode
                  ? t("withdraw.proof.localBody")
                  : t("withdraw.proof.body")}
              </div>

              {localMode && localPhase !== "idle" ? (
                <div style={{ marginTop: 10 }}>
                  {LOCAL_PHASE_STEPS.map((phase, index) => (
                    <div
                      key={phase}
                      className={`parse-state${
                        index < localPhaseIndex ? " ok" : ""
                      }`}
                    >
                      <Icon
                        name={
                          index < localPhaseIndex
                            ? "check-circle"
                            : "clock"
                        }
                      />
                      <span>{t(phaseMessageKey(phase))}</span>
                    </div>
                  ))}
                </div>
              ) : null}

              {localMode && proofDurationMs !== null ? (
                <div className="card-note" style={{ marginTop: 8 }}>
                  {t("withdraw.local.proofTime", {
                    time: formatDurationMs(proofDurationMs),
                  })}
                </div>
              ) : localMode && submitting && liveProofMs > 0 ? (
                <div className="card-note" style={{ marginTop: 8 }}>
                  {t("withdraw.local.elapsed", {
                    time: formatDurationMs(liveProofMs),
                  })}
                </div>
              ) : null}

              {!localMode && proof ? (
                <div className="backup-ok">
                  <Icon name="check-circle" />
                  {t("withdraw.proof.ready")}
                </div>
              ) : null}
              {localMode && !submitting && proofDurationMs === null ? (
                <div className="card-note" style={{ marginTop: 8 }}>
                  {t("withdraw.local.neverLeaves")}
                </div>
              ) : null}
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("withdraw.safety.title")}</div>
              <div className="right">
                <Badge tone="danger" dot>{t("common.important")}</Badge>
              </div>
            </div>
            <div className="card-b">
              <div className="note-warning">
                <Icon name="alert" />
                <span>{t("withdraw.safety.body")}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
