import { useRef, useState } from "react";
import { useI18n } from "../i18n";
import { useApp } from "../state/AppContext";
import { downloadTextFile } from "../lib/download";
import {
  INDEXER_LAG_WARN_BLOCKS,
  INDEXER_LAG_WARN_SECONDS,
  indexerLagIsHigh,
  summarizeHealth,
} from "../lib/health";
import { exportVaultBackup, importEncryptedBackup } from "../lib/vault";
import { Icon } from "../components/Icon";
import { Badge, PageHead } from "../components/ui";

export function SettingsPage() {
  const { t, lang, setLang } = useI18n();
  const {
    theme,
    setTheme,
    vault,
    pools,
    policy,
    dataMode,
    apiMode,
    health,
    authConfigured,
    apiBaseUrl,
    sessionUnlocked,
    vaultLocked,
    lockVault,
    clearLocalData,
    reloadLocalData,
    notify,
  } = useApp();
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [importFile, setImportFile] = useState<string | null>(null);
  const [importName, setImportName] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const vaultStateLabel =
    vault.total === 0
      ? t("settings.backup.empty")
      : sessionUnlocked
        ? t("settings.backup.ready")
        : t("settings.backup.locked");

  const healthSummary = summarizeHealth(health);
  const localChain = apiMode === "local";
  const lagHigh = indexerLagIsHigh(healthSummary);
  const apiModeLabel = !apiMode
    ? t("settings.api.demo")
    : apiMode === "local"
      ? t("settings.api.anvilLocal")
      : t("settings.api.mockChain");
  const apiModeBadge = !apiMode
    ? t("shell.mode.demo")
    : apiMode === "local"
      ? t("shell.mode.anvilLocal")
      : t("shell.mode.mockChain");
  const apiModeNote = !apiMode
    ? t("settings.api.demoNote")
    : dataMode === "partial"
      ? t("settings.api.partialNote")
      : apiMode === "local"
        ? t("settings.api.localNote")
        : t("settings.api.mockNote");
  const lagLabel =
    healthSummary.indexerLagBlocks !== null
      ? t("settings.api.lagBlocks", {
          count: healthSummary.indexerLagBlocks,
        })
      : healthSummary.indexerLagSeconds !== null
        ? t("settings.api.lagSeconds", {
            count: healthSummary.indexerLagSeconds,
          })
        : t("common.notAvailable");
  const lagValueHigh =
    (healthSummary.indexerLagBlocks !== null &&
      healthSummary.indexerLagBlocks >= INDEXER_LAG_WARN_BLOCKS) ||
    (healthSummary.indexerLagSeconds !== null &&
      healthSummary.indexerLagSeconds >= INDEXER_LAG_WARN_SECONDS);

  const requirePassphrase = (): boolean => {
    if (passphrase.trim().length < 8) {
      notify(t("settings.backup.required"));
      return false;
    }
    return true;
  };

  const handleExportVault = async () => {
    if (vault.total === 0) {
      notify(t("toast.vaultEmpty"));
      return;
    }
    if (!requirePassphrase()) return;
    setBusy(true);
    try {
      const backup = await exportVaultBackup(passphrase);
      downloadTextFile(
        `veilpool-vault-${new Date().toISOString().slice(0, 10)}.json`,
        JSON.stringify(backup, null, 2),
      );
      notify(t("settings.backup.downloaded"));
      setPassphrase("");
    } catch {
      notify(t("toast.genericError"));
    } finally {
      setBusy(false);
    }
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      setImportFile(await file.text());
      setImportName(file.name);
    } catch {
      notify(t("toast.genericError"));
    }
  };

  const handleImport = async () => {
    if (!importFile) {
      notify(t("settings.backup.chooseFile"));
      return;
    }
    if (!requirePassphrase()) return;
    setBusy(true);
    try {
      const result = await importEncryptedBackup(importFile, passphrase);
      reloadLocalData();
      notify(t("settings.backup.imported", { count: result.count }));
      setPassphrase("");
      setImportFile(null);
      setImportName("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch {
      notify(t("settings.backup.importFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleLockNow = () => {
    lockVault();
    notify(t("settings.session.lockedNow"));
  };

  const handleClear = () => {
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    clearLocalData();
    setConfirmClear(false);
    notify(t("settings.danger.cleared"));
  };

  return (
    <section className="screen active" id="settings">
      <PageHead
        eyebrow={t("settings.eyebrow")}
        title={t("settings.title")}
        subtitle={t("settings.sub")}
        actions={
          <span className="badge testnet">
            <span className="dot" />
            {t("shell.testnet")}
          </span>
        }
      />

      <div className="grid main-grid">
        <div className="span-8 settings-stack">
          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("settings.network.title")}</div>
              <div className="right">
                <Badge tone="ok" dot>{t("settings.network.testnet")}</Badge>
              </div>
            </div>
            <div className="card-b pad">
              <div className="choice-grid">
                <div
                  className={`choice${localChain ? "" : " active"}`}
                  style={localChain ? { opacity: 0.55, cursor: "default" } : undefined}
                >
                  <div className="t">{t("settings.network.sepolia")}</div>
                  <div className="s">
                    11155111 ·{" "}
                    {localChain
                      ? t("settings.network.notConfigured")
                      : t("settings.network.current")}
                  </div>
                </div>
                <div
                  className={`choice${localChain ? " active" : ""}`}
                  style={
                    localChain
                      ? undefined
                      : { opacity: 0.55, cursor: "default" }
                  }
                >
                  <div className="t">{t("settings.network.anvil")}</div>
                  <div className="s">
                    {healthSummary.chainId ?? 31337} ·{" "}
                    {localChain
                      ? t("settings.network.current")
                      : t("settings.network.notConfigured")}
                  </div>
                </div>
              </div>
              <div className="card-note" style={{ marginTop: 9 }}>
                {t("settings.network.note")}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("settings.backup.title")}</div>
              <div className="right">
                {vault.unbacked > 0 ? (
                  <Badge tone="warn" dot>
                    {t("settings.backup.count", { count: vault.unbacked })}
                  </Badge>
                ) : (
                  <Badge tone="ok">
                    {vault.total > 0
                      ? t("common.backedUp")
                      : t("settings.backup.empty")}
                  </Badge>
                )}
              </div>
            </div>
            <div className="card-b pad">
              <div className="summary">
                <div className="summary-row">
                  <span>{t("settings.backup.backedUp")}</span>
                  <span className="v">{vault.backedUp}</span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.backup.unbacked")}</span>
                  <span className={`v${vault.unbacked > 0 ? " warn" : ""}`}>
                    {vault.unbacked}
                  </span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.backup.total")}</span>
                  <span className="v">{vault.total}</span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.backup.lastBackup")}</span>
                  <span
                    className={`v${
                      vault.total > 0 && sessionUnlocked ? " ok" : ""
                    }`}
                  >
                    {vaultStateLabel}
                  </span>
                </div>
              </div>

              {!sessionUnlocked && vault.total > 0 ? (
                <div className="inline-alert warn" style={{ marginTop: 10 }}>
                  <Icon name="alert" />
                  <span>{t("settings.backup.lockedHelp")}</span>
                </div>
              ) : null}

              <div className="card-note" style={{ marginTop: 10 }}>
                {t("settings.backup.help")}
              </div>

              <div className="backup-controls">
                <div className="field">
                  <label htmlFor="vault-passphrase">{t("common.passphrase")}</label>
                  <input
                    id="vault-passphrase"
                    className="input"
                    type="password"
                    autoComplete="new-password"
                    value={passphrase}
                    onChange={(event) => setPassphrase(event.target.value)}
                    placeholder={t("common.passphrasePlaceholder")}
                  />
                  <div className="backup-hint">{t("common.passphraseHint")}</div>
                </div>
                <div className="backup-row">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void handleExportVault()}
                    disabled={busy || vault.total === 0}
                  >
                    <Icon name="download" />
                    {t("settings.backup.export")}
                  </button>
                </div>
                <div className="backup-row" style={{ marginTop: 8 }}>
                  <label className="btn btn-sm file-label" htmlFor="vault-import">
                    <Icon name="upload" />
                    <span className="truncate">
                      {importName || t("settings.backup.chooseFileLabel")}
                    </span>
                  </label>
                  <input
                    id="vault-import"
                    ref={fileInputRef}
                    className="sr-only"
                    type="file"
                    accept=".json,application/json"
                    onChange={(event) => void handleFile(event.target.files?.[0])}
                  />
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => void handleImport()}
                    disabled={busy || !importFile}
                  >
                    <Icon name="upload" />
                    {t("settings.backup.import")}
                  </button>
                </div>
              </div>

              <div className="inline-alert warn" style={{ marginTop: 10 }}>
                <Icon name="alert" />
                <span>{t("settings.backup.warning")}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("settings.session.title")}</div>
              <div className="right">
                <Badge
                  tone={sessionUnlocked ? "ok" : vaultLocked ? "warn" : "muted"}
                  dot={sessionUnlocked || vaultLocked}
                >
                  {sessionUnlocked
                    ? t("settings.session.unlocked")
                    : vaultLocked
                      ? t("settings.session.locked")
                      : t("settings.session.noSession")}
                </Badge>
              </div>
            </div>
            <div className="card-b">
              <div className="check-list">
                <div className="check">
                  <Icon name="check" />
                  <span>{t("settings.session.1")}</span>
                </div>
                <div className="check">
                  <Icon name="check" />
                  <span>{t("settings.session.2")}</span>
                </div>
                <div className="check">
                  <Icon name="check" />
                  <span>{t("settings.session.3")}</span>
                </div>
                <div className="check">
                  <Icon name="check" />
                  <span>{t("settings.session.4")}</span>
                </div>
                <div className="check">
                  <Icon name="clock" />
                  <span>{t("settings.session.autoLock")}</span>
                </div>
                <div className="check warn">
                  <Icon name="alert" />
                  <span>{t("settings.session.autoLockWarning")}</span>
                </div>
              </div>
              <button
                type="button"
                className="btn btn-sm"
                style={{ marginTop: 10 }}
                onClick={handleLockNow}
                disabled={!sessionUnlocked}
              >
                <Icon name="lock" />
                {t("settings.session.lockNow")}
              </button>
            </div>
          </div>
        </div>

        <div className="span-4 settings-stack">
          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("settings.api.title")}</div>
              <div className="right">
                <Badge
                  tone={
                    !apiMode
                      ? "warn"
                      : apiMode === "local"
                        ? "warn"
                        : "info"
                  }
                  dot
                >
                  {apiModeBadge}
                </Badge>
              </div>
            </div>
            <div className="card-b pad">
              <div className="summary">
                <div className="summary-row">
                  <span>{t("settings.api.baseUrl")}</span>
                  <span
                    className="v mono-block"
                    style={{ maxWidth: 260, textAlign: "right" }}
                  >
                    {apiBaseUrl}
                  </span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.api.auth")}</span>
                  <span className="v">
                    <Badge tone={authConfigured ? "ok" : "muted"}>
                      {authConfigured
                        ? t("settings.api.tokenConfigured")
                        : t("settings.api.noToken")}
                    </Badge>
                  </span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.api.mode")}</span>
                  <span className="v">{apiModeLabel}</span>
                </div>
                {localChain ? (
                  <>
                    {healthSummary.chainId !== null ? (
                      <div className="summary-row">
                        <span>{t("settings.api.chainId")}</span>
                        <span className="v">{healthSummary.chainId}</span>
                      </div>
                    ) : null}
                    {healthSummary.chainService ? (
                      <div className="summary-row">
                        <span>{t("settings.api.chainService")}</span>
                        <span
                          className="v mono-block"
                          style={{ maxWidth: 260, textAlign: "right" }}
                        >
                          {healthSummary.chainService}
                        </span>
                      </div>
                    ) : null}
                    <div className="summary-row">
                      <span>{t("settings.api.indexer")}</span>
                      <span className={`v${lagHigh ? " warn" : ""}`}>
                        {healthSummary.indexerStatus ??
                          t("common.notAvailable")}
                      </span>
                    </div>
                    <div className="summary-row">
                      <span>{t("settings.api.indexerLag")}</span>
                      <span className={`v${lagHigh ? " warn" : ""}`}>
                        {lagLabel}
                      </span>
                    </div>
                    <div className="summary-row">
                      <span>{t("withdraw.title")}</span>
                      <span className="v warn">
                        {t("settings.api.localWithdrawNote")}
                      </span>
                    </div>
                  </>
                ) : null}
              </div>

              {localChain && lagHigh ? (
                <div className="inline-alert warn" style={{ marginTop: 10 }}>
                  <Icon name="alert" />
                  <span>
                    {lagValueHigh
                      ? t("settings.api.lagHigh", { lag: lagLabel })
                      : t("settings.api.indexerWarning", {
                          status:
                            healthSummary.indexerStatus ??
                            t("common.notAvailable"),
                        })}
                  </span>
                </div>
              ) : null}

              <div className="card-note" style={{ marginTop: 9 }}>
                {apiModeNote}
              </div>
              <div className="card-note" style={{ marginTop: 5 }}>
                {t("settings.api.tokenNote")}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("settings.interface.title")}</div>
            </div>
            <div className="card-b pad">
              <div className="summary">
                <div className="summary-row">
                  <span>{t("settings.interface.theme")}</span>
                  <span className="v">
                    {theme === "dark"
                      ? t("settings.interface.dark")
                      : t("settings.interface.light")}
                  </span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.interface.language")}</span>
                  <span className="v">
                    {lang === "zh"
                      ? t("settings.interface.chinese")
                      : t("settings.interface.english")}
                  </span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.interface.testnet")}</span>
                  <span className="v">{t("settings.interface.always")}</span>
                </div>
              </div>
              <div className="field" style={{ marginTop: 11, marginBottom: 8 }}>
                <label>{t("settings.interface.theme")}</label>
                <div className="seg-wide" role="group" aria-label={t("settings.interface.theme")}>
                  <button
                    type="button"
                    className={theme === "dark" ? "active" : ""}
                    aria-pressed={theme === "dark"}
                    onClick={() => setTheme("dark")}
                  >
                    <Icon name="moon" /> {t("settings.interface.dark")}
                  </button>
                  <button
                    type="button"
                    className={theme === "light" ? "active" : ""}
                    aria-pressed={theme === "light"}
                    onClick={() => setTheme("light")}
                  >
                    <Icon name="sun" /> {t("settings.interface.light")}
                  </button>
                </div>
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <label>{t("settings.interface.language")}</label>
                <div className="seg-wide" role="group" aria-label={t("settings.interface.language")}>
                  <button
                    type="button"
                    className={lang === "en" ? "active" : ""}
                    aria-pressed={lang === "en"}
                    onClick={() => setLang("en")}
                  >
                    EN
                  </button>
                  <button
                    type="button"
                    className={lang === "zh" ? "active" : ""}
                    aria-pressed={lang === "zh"}
                    onClick={() => setLang("zh")}
                  >
                    中文
                  </button>
                </div>
              </div>
              <div className="card-note" style={{ marginTop: 9 }}>
                {t("settings.interface.note")}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("settings.about.title")}</div>
            </div>
            <div className="card-b pad">
              <div className="summary">
                <div className="summary-row">
                  <span>{t("settings.about.version")}</span>
                  <span className="v">v0.1.0</span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.about.environment")}</span>
                  <span className="v">
                    {localChain
                      ? t("settings.about.environment.local")
                      : !apiMode
                        ? t("settings.about.environment.demo")
                        : t("settings.about.environment.mock")}
                  </span>
                </div>
                <div className="summary-row">
                  <span>{t("settings.about.pools")}</span>
                  <span className="v">{pools.length}</span>
                </div>
                <div className="summary-row">
                  <span>{t("compliance.stat.policy")}</span>
                  <span className="v">v{policy.policy_version}</span>
                </div>
              </div>
              <div className="card-note" style={{ marginTop: 9 }}>
                {t("settings.about.text")}
              </div>
            </div>
          </div>

          <div className="card danger-zone">
            <div className="card-h">
              <div className="card-title">{t("settings.danger.title")}</div>
              <div className="right">
                <Badge tone="danger">{t("settings.danger.irreversible")}</Badge>
              </div>
            </div>
            <div className="card-b pad">
              <div className="card-note">{t("settings.danger.text")}</div>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                style={{ marginTop: 9 }}
                onClick={handleClear}
              >
                {confirmClear
                  ? t("settings.danger.confirm")
                  : t("settings.danger.clear")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
