import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useI18n } from "../i18n";
import { useApp } from "../state/AppContext";
import { api, ApiError, shouldFallbackToDemo } from "../lib/api";
import {
  createDemoDepositIntent,
  DEMO_DEPOSITOR_ADDRESS,
} from "../lib/demoData";
import {
  buildDepositIntentRequest,
  buildLocalDepositRequest,
  buildMockDepositRequest,
  canConfirmDeposit,
  depositRoute,
  describeLocalDepositFailure,
  localDepositActivityStatus,
} from "../lib/deposit";
import {
  generateNoteForMode,
  noteModeForDeposit,
  zkNotesFlagEnabled,
  type VeilNote,
} from "../lib/note";
import { createNoteBackup, putNote } from "../lib/vault";
import { downloadTextFile, makeDemoTxHash } from "../lib/download";
import {
  activityStatusTone,
} from "../lib/activity";
import {
  countdown,
  denominationWei,
  formatAssetAmount,
  formatBps,
  formatInteger,
  formatMaturity,
  maturityTimeFromNow,
  poolLabel,
  protocolFeeWei,
} from "../lib/format";
import { decisionKey, decisionTone, localStatusKey } from "../lib/labels";
import { Icon } from "../components/Icon";
import {
  Badge,
  PageHead,
  StepBar,
  SummaryRow,
} from "../components/ui";
import { useNow } from "../hooks/useNow";
import type {
  ComplianceDecision,
  DepositIntentResponse,
  LocalActivityStatus,
  LocalDepositInstruction,
  LocalDepositResponse,
  MockDepositResponse,
  Pool,
} from "../types";

interface PendingIntent {
  intentId: string;
  commitment: string;
  maturityAt: string;
  demo: boolean;
  local: boolean;
  localSubmissionKey?: string;
  pool: Pool;
  noteId: string;
  compliance: ComplianceDecision;
}

interface DepositResult extends PendingIntent {
  txHash?: string;
  blockNumber?: number;
  status: LocalActivityStatus;
}

type LocalDepositPhase = "idle" | "submitting" | "unconfirmed" | "manual";

interface LocalDepositFailureView {
  code?: string;
  message?: string;
  txHash?: string;
}

function mockStatusToLocal(status: string | undefined): LocalActivityStatus {
  if (status === "failed") return "failed";
  if (status === "pending" || status === "submitted") return "pending";
  return "confirmed";
}

export function DepositPage() {
  const { t, lang } = useI18n();
  const {
    pools,
    dataMode,
    apiMode,
    health,
    recordActivity,
    markVaultBackedUp,
    reloadLocalData,
    notify,
  } = useApp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const now = useNow(30_000);

  const requestedPool = searchParams.get("pool");
  const [selectedPoolId, setSelectedPoolId] = useState<string>(() => {
    if (requestedPool && pools.some((pool) => pool.id === requestedPool)) {
      return requestedPool;
    }
    return pools[0]?.id ?? "";
  });
  const selectedPool = useMemo(
    () =>
      pools.find((pool) => pool.id === selectedPoolId) ??
      pools[0] ??
      null,
    [pools, selectedPoolId],
  );

  const [note, setNote] = useState<VeilNote | null>(null);
  const [generating, setGenerating] = useState(false);
  const [vaultSaved, setVaultSaved] = useState(false);
  const [vaultWarning, setVaultWarning] = useState<string | null>(null);
  const [backupConfirmed, setBackupConfirmed] = useState(false);
  const [backupExported, setBackupExported] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [passphraseError, setPassphraseError] = useState<string | null>(null);
  const [backupBusy, setBackupBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingIntent, setPendingIntent] = useState<PendingIntent | null>(null);
  const [result, setResult] = useState<DepositResult | null>(null);
  const [localPhase, setLocalPhase] = useState<LocalDepositPhase>("idle");
  const [localFailure, setLocalFailure] =
    useState<LocalDepositFailureView | null>(null);
  const [manualInstruction, setManualInstruction] =
    useState<LocalDepositInstruction | null>(null);

  const route = depositRoute(apiMode, dataMode);
  const localMode = route === "local";
  // Local Anvil mode needs a circuit-compatible Poseidon commitment. The
  // VITE_ZK_NOTES flag opts the mock/demo path into the same note format.
  const noteMode = noteModeForDeposit({
    local: localMode,
    zkNotes: zkNotesFlagEnabled(),
  });
  const chainId =
    typeof health?.chain_id === "number" &&
    Number.isSafeInteger(health.chain_id) &&
    health.chain_id >= 0
      ? health.chain_id
      : 31337;
  const step = result ? 4 : submitting || pendingIntent ? 3 : note ? 2 : 1;

  const canConfirm =
    Boolean(selectedPool) &&
    canConfirmDeposit({
      notePresent: Boolean(note) && (vaultSaved || backupExported),
      backupConfirmed,
      submitting,
    });

  const handleGenerate = async () => {
    if (!selectedPool) return;
    setGenerating(true);
    setError(null);
    setVaultWarning(null);
    setResult(null);
    setPendingIntent(null);
    setLocalPhase("idle");
    setLocalFailure(null);
    setManualInstruction(null);
    setBackupConfirmed(false);
    setBackupExported(false);
    setPassphrase("");
    setPassphraseError(null);
    try {
      const generated = await generateNoteForMode(
        selectedPool,
        chainId,
        noteMode,
      );
      setNote(generated);
      setVaultSaved(false);
      try {
        await putNote(generated);
        setVaultSaved(true);
        reloadLocalData();
      } catch {
        setVaultWarning(t("deposit.note.vaultFailed"));
      }
    } catch {
      setError(t("deposit.error.generic"));
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = async () => {
    if (!note) return;
    try {
      await navigator.clipboard.writeText(note.token);
      notify(t("toast.copy"));
    } catch {
      notify(t("deposit.note.copyFailed"));
    }
  };

  const copyText = async (value: string, message: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      notify(message);
    } catch {
      notify(t("toast.copyFailed"));
    }
  };

  const handleDownloadBackup = async () => {
    if (!note) return;
    if (passphrase.trim().length < 8) {
      setPassphraseError(t("common.passphraseShort"));
      return;
    }
    setBackupBusy(true);
    setPassphraseError(null);
    try {
      const envelope = await createNoteBackup(note, passphrase);
      downloadTextFile(
        `veilpool-note-${note.payload.id}.json`,
        JSON.stringify(envelope, null, 2),
      );
      setBackupExported(true);
      markVaultBackedUp(note.payload.id);
      notify(t("deposit.note.backupDownloaded"));
    } catch {
      setPassphraseError(t("deposit.note.backupFailed"));
    } finally {
      setBackupBusy(false);
    }
  };

  const finalizeDeposit = (
    pending: PendingIntent,
    txHash: string | undefined,
    status: LocalActivityStatus,
    blockNumber?: number,
  ) => {
    recordActivity({
      id: crypto.randomUUID(),
      kind: "deposit",
      poolId: pending.pool.id,
      asset: pending.pool.asset,
      denomination: pending.pool.denomination,
      status,
      noteId: pending.noteId,
      createdAt: new Date().toISOString(),
      matureAt: pending.maturityAt,
      commitment: pending.commitment,
      compliance: pending.compliance,
      demo: pending.demo,
      txHash,
    });
    if (backupConfirmed) {
      markVaultBackedUp(pending.noteId);
    }
    setResult({ ...pending, txHash, status, blockNumber });
    setNote(null);
    setPendingIntent(null);
    setLocalPhase("idle");
    setLocalFailure(null);
    setManualInstruction(null);
    setBackupConfirmed(false);
    setBackupExported(false);
    setPassphrase("");
    setVaultWarning(null);
    setError(null);
  };

  const handleConfirm = async () => {
    if (!selectedPool || !note || !canConfirm) return;
    setSubmitting(true);
    setError(null);
    setLocalFailure(null);
    setManualInstruction(null);

    try {
      let pending = pendingIntent;

      if (!pending) {
        const payload = buildDepositIntentRequest({
          poolId: selectedPool.id,
          depositorAddress: DEMO_DEPOSITOR_ADDRESS,
          amount: selectedPool.denomination,
          commitment: note.payload.commitment,
        });
        let response: DepositIntentResponse;
        let demo = false;
        let local = false;

        if (route === "demo") {
          response = createDemoDepositIntent(selectedPool, payload.commitment);
          demo = true;
        } else if (route === "local") {
          // Local mode never falls back to a simulated demo success.
          local = true;
          response = await api.createDepositIntent(
            payload,
            crypto.randomUUID(),
          );
        } else {
          try {
            response = await api.createDepositIntent(
              payload,
              crypto.randomUUID(),
            );
          } catch (requestError) {
            if (!shouldFallbackToDemo(requestError)) throw requestError;
            response = createDemoDepositIntent(selectedPool, payload.commitment);
            demo = true;
          }
        }

        const compliance: ComplianceDecision =
          response.compliance?.decision === "block" ||
          response.compliance?.decision === "review"
            ? response.compliance.decision
            : "allow";

        if (compliance === "block") {
          setError(
            `${t("deposit.error.blocked")}${
              response.compliance?.check_id
                ? ` · ${response.compliance.check_id}`
                : ""
            }`,
          );
          return;
        }
        if (compliance === "review") {
          setError(
            `${t("deposit.error.review")}${
              response.compliance?.check_id
                ? ` · ${response.compliance.check_id}`
                : ""
            }`,
          );
          return;
        }

        pending = {
          intentId: response.intent_id,
          commitment: note.payload.commitment,
          maturityAt: maturityTimeFromNow(selectedPool.maturity_seconds),
          demo,
          local,
          localSubmissionKey: local ? crypto.randomUUID() : undefined,
          pool: selectedPool,
          noteId: note.payload.id,
          compliance,
        };
        setPendingIntent(pending);
      }

      if (pending.demo) {
        finalizeDeposit(
          pending,
          makeDemoTxHash(
            `${pending.intentId}|${pending.commitment}|${Date.now()}`,
          ),
          "confirmed",
        );
        return;
      }

      if (pending.local) {
        setLocalPhase("submitting");
        let localDeposit: LocalDepositResponse;
        try {
          localDeposit = await api.recordLocalDeposit(
            buildLocalDepositRequest({
              intentId: pending.intentId,
              commitment: pending.commitment,
            }),
            pending.localSubmissionKey ?? crypto.randomUUID(),
          );
        } catch (localError) {
          const failure = describeLocalDepositFailure(localError);
          if (failure.kind === "disabled") {
            setLocalPhase("manual");
            setManualInstruction(failure.instruction);
            return;
          }
          setLocalPhase("unconfirmed");
          setLocalFailure({
            code: failure.code,
            message: failure.message,
            txHash: failure.txHash,
          });
          return;
        }

        const localStatus = localDepositActivityStatus(localDeposit.status);
        if (!localDeposit.tx_hash || localStatus === "failed") {
          setLocalPhase("unconfirmed");
          setLocalFailure({
            message:
              localStatus === "failed"
                ? t("deposit.local.notConfirmed")
                : t("deposit.local.noTxHash"),
            txHash: localDeposit.tx_hash,
          });
          return;
        }

        // A tx hash is required before local activity may become confirmed.
        finalizeDeposit(
          pending,
          localDeposit.tx_hash,
          localStatus,
          localDeposit.block_number,
        );
        return;
      }

      let mockDeposit: MockDepositResponse;
      try {
        mockDeposit = await api.recordMockDeposit(
          buildMockDepositRequest({
            intentId: pending.intentId,
            commitment: pending.commitment,
          }),
          crypto.randomUUID(),
        );
      } catch (mockError) {
        const suffix =
          mockError instanceof ApiError
            ? ` (${mockError.code ?? mockError.status})`
            : "";
        setError(`${t("deposit.error.mock")}${suffix}`);
        return;
      }

      const mockStatus = (mockDeposit.status ?? "").toLowerCase();
      if (mockStatus === "failed") {
        setError(t("deposit.error.mockRejected"));
        return;
      }

      finalizeDeposit(
        pending,
        mockDeposit.tx_hash,
        mockStatusToLocal(mockStatus),
      );
    } catch (requestError) {
      if (requestError instanceof ApiError) {
        const suffix = requestError.code
          ? ` (${requestError.code})`
          : ` (${requestError.status})`;
        setError(
          requestError.status === 403
            ? `${t("deposit.error.blocked")}${suffix}`
            : `${t("deposit.error.api")}${suffix}`,
        );
      } else {
        setError(t("deposit.error.generic"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const resetDeposit = () => {
    setResult(null);
    setNote(null);
    setPendingIntent(null);
    setLocalPhase("idle");
    setLocalFailure(null);
    setManualInstruction(null);
    setVaultSaved(false);
    setVaultWarning(null);
    setBackupConfirmed(false);
    setBackupExported(false);
    setPassphrase("");
    setPassphraseError(null);
    setError(null);
  };

  const feeWei = selectedPool ? protocolFeeWei(selectedPool) : "0";
  const payWei =
    selectedPool && feeWei !== "0"
      ? (denominationWei(selectedPool) + BigInt(feeWei)).toString()
      : selectedPool?.denomination_wei;

  if (!selectedPool) {
    return (
      <section className="screen active" id="deposit">
        <PageHead
          eyebrow={t("deposit.eyebrow")}
          title={t("deposit.title")}
          subtitle={t("deposit.sub")}
        />
        <div className="card">
          <div className="card-b pad">
            <div className="empty-state">
              <div className="empty-title">{t("common.loading")}</div>
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="screen active" id="deposit">
      <PageHead
        eyebrow={t("deposit.eyebrow")}
        title={t("deposit.title")}
        subtitle={t("deposit.sub")}
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
          t("deposit.step.pool"),
          t("deposit.step.note"),
          t("deposit.step.confirm"),
          t("deposit.step.maturity"),
        ]}
      />

      {result ? (
        <div className="grid main-grid">
          <div className="card span-7">
            <div className="card-h">
              <div className="result-card-title">
                <div className="card-title">
                  {result.local
                    ? result.status === "confirmed"
                      ? t("deposit.local.resultTitle")
                      : t("deposit.local.resultPending")
                    : result.status === "pending"
                      ? t("deposit.success.pendingTitle")
                      : t("deposit.success.title")}
                </div>
                <Badge tone="violet">
                  {result.local ? t("deposit.local.badge") : t("deposit.mock")}
                </Badge>
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
                        ? t("deposit.local.successBody")
                        : t("deposit.success.body")}
                    </div>
                  </div>
                </div>

                <div className="result-row">
                  <span>{t("deposit.intentId")}</span>
                  <span className="v">{result.intentId}</span>
                </div>
                {result.txHash ? (
                  <div className="result-row">
                    <span>{t("common.txHash")}</span>
                    <span className="v">{result.txHash}</span>
                  </div>
                ) : null}
                {result.local && result.blockNumber !== undefined ? (
                  <div className="result-row">
                    <span>{t("deposit.local.block")}</span>
                    <span className="v">{result.blockNumber}</span>
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
                  <span>{t("common.commitment")}</span>
                  <span className="v">{result.commitment}</span>
                </div>
                <div className="result-row">
                  <span>{t("common.anonymitySet")}</span>
                  <span className="v">
                    {formatInteger(result.pool.anonymity_set, lang)}
                  </span>
                </div>
                <div className="result-row">
                  <span>{t("common.maturity")}</span>
                  <span className="v">
                    <Badge tone="info">{formatMaturity(result.pool.maturity_seconds)}</Badge>
                  </span>
                </div>

                <div className="countdown">
                  <Icon name="clock" />
                  {countdown(result.maturityAt, lang, now) ===
                  t("deposit.success.matureNow")
                    ? t("deposit.success.matureNow")
                    : t("deposit.success.maturityIn", {
                        time: countdown(result.maturityAt, lang, now),
                      })}
                </div>

                <div className="inline-alert info" style={{ marginTop: 12 }}>
                  <Icon name="lock" />
                  <span>{t("deposit.result.noteHidden")}</span>
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
                    onClick={resetDeposit}
                  >
                    <Icon name="plus" />
                    {t("deposit.success.new")}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="span-5 settings-stack">
            <div className="card">
              <div className="card-h">
                <div className="card-title">{t("deposit.tips.title")}</div>
                <div className="right">
                  <Badge tone="info">{t("common.important")}</Badge>
                </div>
              </div>
              <div className="card-b">
                <div className="guard">
                  <Icon name="lock" />
                  <span>{t("deposit.tips.1")}</span>
                </div>
                <div className="guard">
                  <Icon name="lock" />
                  <span>{t("deposit.tips.2")}</span>
                </div>
                <div className="guard">
                  <Icon name="lock" />
                  <span>{t("deposit.tips.3")}</span>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card-h">
                <div className="card-title">{t("activity.backup.title")}</div>
              </div>
              <div className="card-b pad">
                <div className="card-note">{t("deposit.result.noteHidden")}</div>
                <button
                  type="button"
                  className="btn full-width"
                  style={{ marginTop: 10 }}
                  onClick={() => navigate("/settings")}
                >
                  <Icon name="key" />
                  {t("settings.backup.export")}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="grid main-grid">
          <div className="card span-7">
            <div className="card-h">
              <div className="card-title">{t("deposit.select.title")}</div>
              <div className="right">
                <Badge tone="ok" dot>
                  {t("deposit.select.compliance")}
                </Badge>
              </div>
            </div>
            <div className="card-b">
              <div className="choice-grid">
                {pools.map((pool) => (
                  <button
                    type="button"
                    className={`choice${
                      pool.id === selectedPool.id ? " active" : ""
                    }`}
                    key={pool.id}
                    onClick={() => setSelectedPoolId(pool.id)}
                    disabled={Boolean(note)}
                    aria-pressed={pool.id === selectedPool.id}
                  >
                    <div className="t">{poolLabel(pool)}</div>
                    <div className="s">
                      {t("deposit.select.choice", {
                        count: formatInteger(pool.anonymity_set, lang),
                        maturity: formatMaturity(pool.maturity_seconds),
                      })}
                    </div>
                  </button>
                ))}
              </div>

              <div className="field" style={{ marginTop: 15 }}>
                <label htmlFor="deposit-amount">{t("deposit.amount")}</label>
                <div className="input-row">
                  <input
                    id="deposit-amount"
                    className="input"
                    style={{ flex: 1 }}
                    value={selectedPool.denomination}
                    readOnly
                  />
                  <span className="input-suffix">{selectedPool.asset}</span>
                </div>
                <div className="card-note" style={{ marginTop: 5 }}>
                  {t("deposit.fixedNote")}
                </div>
              </div>

              {!note ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleGenerate()}
                  disabled={generating}
                >
                  <Icon name="key" />
                  {generating ? t("deposit.note.generating") : t("deposit.note.generate")}
                </button>
              ) : (
                <div className="field" style={{ marginTop: 14 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      marginBottom: 6,
                    }}
                  >
                    <label style={{ margin: 0 }}>{t("deposit.note.title")}</label>
                    <Badge tone="warn" className="note-once">
                      {t("deposit.note.once")}
                    </Badge>
                  </div>
                  <div className="note-box">{note.token}</div>
                  <div className="note-warning" style={{ marginTop: 8 }}>
                    <Icon name="alert" />
                    <span>{t("deposit.note.warning")}</span>
                  </div>
                  <div className="card-note" style={{ marginTop: 7 }}>
                    {t("deposit.note.onlyTime")}
                  </div>
                  <div className="note-actions">
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => void handleCopy()}
                    >
                      <Icon name="copy" />
                      {t("deposit.note.copy")}
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => void handleGenerate()}
                      disabled={generating || backupBusy}
                    >
                      <Icon name="refresh" />
                      {t("deposit.note.replace")}
                    </button>
                  </div>

                  <div className="backup-controls">
                    <div className="field">
                      <label htmlFor="note-backup-passphrase">
                        {t("common.passphrase")}
                      </label>
                      <input
                        id="note-backup-passphrase"
                        className="input"
                        type="password"
                        autoComplete="new-password"
                        value={passphrase}
                        onChange={(event) => setPassphrase(event.target.value)}
                        placeholder={t("common.passphrasePlaceholder")}
                      />
                      <div className="backup-hint">{t("common.passphraseHint")}</div>
                    </div>
                    <div className="backup-export">
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() => void handleDownloadBackup()}
                        disabled={backupBusy}
                      >
                        <Icon name="download" />
                        {t("deposit.note.download")}
                      </button>
                    </div>
                    {passphraseError ? (
                      <div className="inline-alert" style={{ marginTop: 8 }}>
                        <Icon name="alert" />
                        <span>{passphraseError}</span>
                      </div>
                    ) : null}
                    {backupExported ? (
                      <div className="backup-ok">
                        <Icon name="check-circle" />
                        {t("deposit.note.backupDownloaded")}
                      </div>
                    ) : null}
                  </div>

                  {vaultWarning ? (
                    <div className="inline-alert warn">
                      <Icon name="alert" />
                      <span>{vaultWarning}</span>
                    </div>
                  ) : null}
                </div>
              )}

              <div className="field" style={{ marginTop: 14 }}>
                <label>{t("deposit.address")}</label>
                <div className="address-box">{DEMO_DEPOSITOR_ADDRESS}</div>
                <div className="card-note" style={{ marginTop: 5 }}>
                  {t("deposit.address.demo")} · {t("deposit.address.note")}
                </div>
              </div>
            </div>
          </div>

          <div className="span-5 settings-stack">
            <div className="card">
              <div className="card-h">
                <div className="card-title">{t("deposit.summary.title")}</div>
                <div className="right">
                  <Badge tone="info">{formatBps(selectedPool.protocol_fee_bps)}</Badge>
                </div>
              </div>
              <div className="card-b pad">
                <div className="summary">
                  <SummaryRow
                    label={t("common.pool")}
                    value={poolLabel(selectedPool)}
                  />
                  <SummaryRow
                    label={t("common.amount")}
                    value={`${selectedPool.denomination} ${selectedPool.asset}`}
                  />
                  <SummaryRow
                    label={t("common.protocolFee")}
                    value={formatAssetAmount(feeWei, selectedPool.asset)}
                  />
                  <SummaryRow
                    label={t("common.maturity")}
                    value={formatMaturity(selectedPool.maturity_seconds)}
                  />
                  <SummaryRow
                    label={t("common.anonymitySet")}
                    value={formatInteger(selectedPool.anonymity_set, lang)}
                  />
                  <SummaryRow
                    label={t("common.youPay")}
                    value={formatAssetAmount(payWei, selectedPool.asset)}
                    total
                  />
                </div>

                {pendingIntent ? (
                  <div className="inline-alert warn" style={{ marginTop: 10 }}>
                    <Icon name="clock" />
                    <span>
                      {pendingIntent.local
                        ? t("deposit.local.pendingIntent", {
                            id: pendingIntent.intentId,
                          })
                        : t("deposit.pendingIntent", {
                            id: pendingIntent.intentId,
                          })}
                    </span>
                  </div>
                ) : null}

                {localPhase === "submitting" ? (
                  <div className="inline-alert info" style={{ marginTop: 10 }}>
                    <Icon name="clock" />
                    <span>{t("deposit.local.submittingHint")}</span>
                  </div>
                ) : null}

                {localPhase === "unconfirmed" ? (
                  <div className="inline-alert warn" style={{ marginTop: 10 }}>
                    <Icon name="alert" />
                    <div className="alert-copy">
                      <strong>{t("deposit.local.notConfirmedTitle")}</strong>
                      <div>
                        {localFailure?.message ??
                          t("deposit.local.notConfirmed")}
                      </div>
                      {localFailure?.txHash ? (
                        <div className="mono-block">
                          {t("deposit.local.txHash", {
                            hash: localFailure.txHash,
                          })}
                        </div>
                      ) : null}
                      {localFailure?.code ? (
                        <div className="card-note">
                          {t("deposit.local.code")}: {localFailure.code}
                        </div>
                      ) : null}
                      <div className="card-note">
                        {t("deposit.local.retryNote")}
                      </div>
                    </div>
                  </div>
                ) : null}

                {localPhase === "manual" && manualInstruction ? (
                  <div className="inline-alert warn" style={{ marginTop: 10 }}>
                    <Icon name="alert" />
                    <div className="alert-copy">
                      <strong>{t("deposit.local.disabledTitle")}</strong>
                      <div>{t("deposit.local.disabledBody")}</div>
                      <div className="card-note">
                        {t("deposit.local.manualHint")}
                      </div>

                      {manualInstruction.contractAddress ? (
                        <div className="field" style={{ marginTop: 8 }}>
                          <label>{t("deposit.local.contract")}</label>
                          <div className="note-box">
                            {manualInstruction.contractAddress}
                          </div>
                          <button
                            type="button"
                            className="btn btn-sm"
                            style={{ marginTop: 6 }}
                            onClick={() =>
                              void copyText(
                                manualInstruction?.contractAddress ?? "",
                                t("toast.copy"),
                              )
                            }
                          >
                            <Icon name="copy" />
                            {t("deposit.local.copyContract")}
                          </button>
                        </div>
                      ) : null}

                      {manualInstruction.denominationWei ? (
                        <div className="field" style={{ marginTop: 8 }}>
                          <label>{t("deposit.local.denomination")}</label>
                          <div className="note-box">
                            {manualInstruction.denominationWei}
                          </div>
                        </div>
                      ) : null}

                      {manualInstruction.calldata ? (
                        <div className="field" style={{ marginTop: 8 }}>
                          <label>{t("deposit.local.calldata")}</label>
                          <div className="note-box">
                            {manualInstruction.calldata}
                          </div>
                          <button
                            type="button"
                            className="btn btn-sm"
                            style={{ marginTop: 6 }}
                            onClick={() =>
                              void copyText(
                                manualInstruction?.calldata ?? "",
                                t("toast.copy"),
                              )
                            }
                          >
                            <Icon name="copy" />
                            {t("deposit.local.copyCalldata")}
                          </button>
                        </div>
                      ) : null}

                      {manualInstruction.instruction ? (
                        <div className="field" style={{ marginTop: 8 }}>
                          <label>{t("deposit.local.instruction")}</label>
                          <div
                            className="note-box"
                            style={{ whiteSpace: "pre-wrap" }}
                          >
                            {manualInstruction.instruction}
                          </div>
                          <button
                            type="button"
                            className="btn btn-sm"
                            style={{ marginTop: 6 }}
                            onClick={() =>
                              void copyText(
                                manualInstruction?.instruction ?? "",
                                t("toast.copy"),
                              )
                            }
                          >
                            <Icon name="copy" />
                            {t("deposit.local.copyInstruction")}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}

                {error ? (
                  <div className="inline-alert">
                    <Icon name="alert" />
                    <span>{error}</span>
                  </div>
                ) : null}

                <label
                  className={`check gate-check${
                    backupConfirmed ? " ready" : ""
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={backupConfirmed}
                    onChange={(event) =>
                      setBackupConfirmed(event.target.checked)
                    }
                    disabled={!note || submitting}
                  />
                  <span>{t("deposit.gate")}</span>
                </label>

                <button
                  type="button"
                  className="btn btn-primary full-width"
                  onClick={() => void handleConfirm()}
                  disabled={!canConfirm}
                >
                  <Icon name="shield-check" />
                  {submitting
                    ? localPhase === "submitting"
                      ? t("deposit.local.submitting")
                      : pendingIntent
                        ? t("deposit.retryingMock")
                        : t("deposit.confirming")
                    : pendingIntent
                      ? pendingIntent.local
                        ? t("deposit.local.retry")
                        : t("deposit.retryMock")
                      : localMode
                        ? t("deposit.confirmLocal")
                        : t("deposit.confirm")}
                </button>

                <div className="card-note" style={{ marginTop: 9 }}>
                  {note
                    ? backupConfirmed
                      ? t("deposit.postNote")
                      : t("deposit.gateHint")
                    : t("deposit.note.required")}
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-h">
                <div className="card-title">{t("deposit.tips.title")}</div>
                <div className="right">
                  <Badge tone="info">{t("common.important")}</Badge>
                </div>
              </div>
              <div className="card-b">
                <div className="guard">
                  <Icon name="lock" />
                  <span>{t("deposit.tips.1")}</span>
                </div>
                <div className="guard">
                  <Icon name="lock" />
                  <span>{t("deposit.tips.2")}</span>
                </div>
                <div className="guard">
                  <Icon name="lock" />
                  <span>{t("deposit.tips.3")}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
