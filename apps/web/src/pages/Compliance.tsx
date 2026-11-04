import { useI18n } from "../i18n";
import { useApp } from "../state/AppContext";
import { DEMO_DECISIONS, DEMO_METRICS } from "../lib/demoData";
import { downloadTextFile } from "../lib/download";
import {
  formatLocalTime,
  formatShortDate,
  formatInteger,
} from "../lib/format";
import { decisionKey, decisionTone } from "../lib/labels";
import { Icon } from "../components/Icon";
import { Badge, PageHead, Stat } from "../components/ui";
import type { ComplianceDecision } from "../types";

interface RecentCheck {
  id: string;
  kind: "deposit" | "withdrawal";
  label: string;
  decision: ComplianceDecision;
  reasonCode?: string;
  at?: string;
  sample: boolean;
}

function formatLimit(value: string | undefined, lang: "en" | "zh"): string {
  if (!value) return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return `${new Intl.NumberFormat(lang === "zh" ? "zh-CN" : "en-US").format(parsed)} tUSD`;
}

export function CompliancePage() {
  const { t, lang } = useI18n();
  const { policy, activity, notify } = useApp();

  const localChecks: RecentCheck[] = activity
    .filter((record) => record.compliance)
    .slice(0, 4)
    .map((record) => ({
      id: record.id,
      kind: record.kind,
      label: `${record.asset} · ${record.denomination}`,
      decision: record.compliance as ComplianceDecision,
      reasonCode:
        record.compliance === "allow"
          ? "SCREENING_PASS"
          : record.compliance === "review"
            ? "VELOCITY_REVIEW"
            : "SANCTIONS_MATCH",
      at: record.createdAt,
      sample: record.demo,
    }));

  const recentChecks: RecentCheck[] =
    localChecks.length > 0
      ? localChecks
      : DEMO_DECISIONS.map((decision) => ({
          id: decision.id,
          kind: decision.kind,
          label: decision.label,
          decision: decision.decision,
          reasonCode: decision.reasonCode,
          at: decision.at,
          sample: true,
        }));

  const handleExport = () => {
    downloadTextFile(
      `veilpool-compliance-${new Date().toISOString().slice(0, 10)}.json`,
      JSON.stringify(
        {
          type: "veilpool.compliance.export",
          version: 1,
          exportedAt: new Date().toISOString(),
          policy,
          localChecks: localChecks.length > 0 ? localChecks : [],
          note: "Local demo export. No secret notes are included.",
        },
        null,
        2,
      ),
    );
    notify(t("compliance.exported"));
  };

  return (
    <section className="screen active" id="compliance">
      <PageHead
        eyebrow={t("compliance.eyebrow")}
        title={t("compliance.title")}
        subtitle={t("compliance.sub")}
        actions={
          <>
            <Badge tone="ok" dot>
              {t("overview.compliance.enforced")}
            </Badge>
            <button type="button" className="btn" onClick={handleExport}>
              <Icon name="doc" />
              {t("compliance.export")}
            </button>
          </>
        }
      />

      <div className="warning compliance-warning">
        <Icon name="alert" />
        <div>
          <strong>{t("compliance.warning.title")}</strong>{" "}
          <span>{t("compliance.warning.body")}</span>
        </div>
        <div className="right badge testnet">
          {t("common.mainnetUnavailable")}
        </div>
      </div>

      <div className="card stat-strip" style={{ paddingTop: 15, paddingBottom: 15 }}>
        <Stat
          label={t("compliance.stat.policy")}
          value={`v${policy.policy_version}`}
          detail={t("overview.compliance.enforced")}
          tone="ok"
          compact
        />
        <Stat
          label={t("compliance.stat.list")}
          value={policy.sanctions_list_version ?? "—"}
          detail={t("common.sampleData")}
          compact
        />
        <Stat
          label={t("compliance.stat.depositLimit")}
          value={formatLimit(policy.daily_deposit_limit, lang)}
          detail={t("compliance.stat.deposits24h", {
            count: formatInteger(DEMO_METRICS.deposits_24h, lang),
          })}
          compact
        />
        <Stat
          label={t("compliance.stat.reviewSla")}
          value={
            policy.review_sla_hours
              ? t("compliance.stat.hours", {
                  hours: String(policy.review_sla_hours),
                })
              : "—"
          }
          detail={t("compliance.stat.allowedJurisdictions", {
            count: policy.allowed_jurisdictions?.length ?? 0,
          })}
          compact
        />
      </div>

      <div className="grid main-grid" style={{ marginBottom: 14 }}>
        <div className="card span-7">
          <div className="card-h">
            <div className="card-title">{t("compliance.risk.title")}</div>
            <div className="right">
              <Badge tone="ok" dot>
                {t("compliance.risk.active")}
              </Badge>
            </div>
          </div>
          <div className="card-b">
            <div className="check-list">
              <div className="check">
                <Icon name="check" />
                <span>{t("compliance.risk.1")}</span>
              </div>
              <div className="check">
                <Icon name="check" />
                <span>{t("compliance.risk.2")}</span>
              </div>
              <div className="check">
                <Icon name="check" />
                <span>{t("compliance.risk.3")}</span>
              </div>
              <div className="check">
                <Icon name="check" />
                <span>{t("compliance.risk.4")}</span>
              </div>
              <div className="check warn">
                <Icon name="alert" />
                <span>{t("compliance.risk.5")}</span>
              </div>
            </div>

            <div className="grid g-2" style={{ marginTop: 14 }}>
              <div className="how-step">
                <div className="how-title">{t("compliance.risk.depositTitle")}</div>
                <div className="how-text">{t("compliance.risk.depositText")}</div>
              </div>
              <div className="how-step">
                <div className="how-title">{t("compliance.risk.withdrawTitle")}</div>
                <div className="how-text">{t("compliance.risk.withdrawText")}</div>
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              <div className="stat-label" style={{ marginBottom: 7 }}>
                {t("compliance.limits.title")}{" "}
                <span className="faint">· {t("compliance.limits.sample")}</span>
              </div>
              <div className="progress-row" style={{ marginBottom: 8 }}>
                <span className="row-sub" style={{ width: 92 }}>{t("compliance.limits.dailyDeposit")}</span>
                <div className="progress"><i style={{ width: "72%" }} /></div>
                <span className="row-meta">72%</span>
              </div>
              <div className="progress-row" style={{ marginBottom: 8 }}>
                <span className="row-sub" style={{ width: 92 }}>{t("compliance.limits.dailyWithdrawal")}</span>
                <div className="progress"><i style={{ width: "41%" }} /></div>
                <span className="row-meta">41%</span>
              </div>
              <div className="progress-row">
                <span className="row-sub" style={{ width: 92 }}>{t("compliance.limits.perTx")}</span>
                <div className="progress"><i style={{ width: "100%" }} /></div>
                <span className="row-meta">{formatLimit(policy.per_transaction_limit, lang)}</span>
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              <div className="stat-label" style={{ marginBottom: 6 }}>{t("compliance.sources.title")}</div>
              <div className="chip-row">
                {(policy.screening_sources ?? []).map((source) => (
                  <span className="chip" key={source}>{source}</span>
                ))}
                {(policy.allowed_jurisdictions ?? []).slice(0, 4).map((code) => (
                  <span className="chip accent" key={code}>{code}</span>
                ))}
              </div>
            </div>
            <div className="sample-note">{t("compliance.limits.note")}</div>
          </div>
        </div>

        <div className="span-5 settings-stack">
          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("compliance.recent.title")}</div>
              <div className="right">
                <Badge tone="muted">{t("compliance.recent.automated")}</Badge>
                {localChecks.length === 0 ? (
                  <Badge tone="warn">{t("demo.sample")}</Badge>
                ) : null}
              </div>
            </div>
            <div className="card-b" style={{ paddingTop: 0 }}>
              {recentChecks.map((check, index) => (
                <div className="row" key={check.id} style={{ paddingTop: index === 0 ? 6 : undefined }}>
                  <div className="row-main">
                    <div className="row-title">
                      {check.kind === "deposit" ? t("nav.deposit") : t("nav.withdraw")} · {check.label}
                    </div>
                    <div className="row-sub">
                      {check.reasonCode} · {formatLocalTime(check.at, lang)}
                    </div>
                  </div>
                  {check.sample ? <Badge tone="warn">{t("demo.sample")}</Badge> : null}
                  <Badge tone={decisionTone(check.decision)}>
                    {t(decisionKey(check.decision))}
                  </Badge>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("compliance.audit.title")}</div>
              <div className="right">
                <Badge tone="ok" dot>{t("compliance.audit.immutable")}</Badge>
              </div>
            </div>
            <div className="card-b">
              <div className="timeline">
                <div className="tl-item">
                  <span className="tl-dot done" />
                  <div className="tl-title">{t("compliance.audit.policy")}</div>
                  <div className="tl-sub">
                    {t("compliance.audit.policyText", {
                      version: String(policy.policy_version),
                    })}
                  </div>
                  <div className="tl-time">
                    {formatShortDate(policy.updated_at, lang)}
                  </div>
                </div>
                <div className="tl-item">
                  <span className="tl-dot done" />
                  <div className="tl-title">{t("compliance.audit.list")}</div>
                  <div className="tl-sub">
                    {t("compliance.audit.listText", {
                      version: policy.sanctions_list_version ?? "—",
                    })}
                  </div>
                  <div className="tl-time">
                    {formatShortDate(policy.updated_at, lang)}
                  </div>
                </div>
                <div className="tl-item">
                  <span className="tl-dot done" />
                  <div className="tl-title">{t("compliance.audit.sla")}</div>
                  <div className="tl-sub">
                    {t("compliance.audit.slaText", {
                      hours: String(policy.review_sla_hours ?? "—"),
                    })}
                  </div>
                  <div className="tl-time">
                    {formatShortDate(policy.updated_at, lang)}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <div className="card-title">{t("compliance.decisions.title")}</div>
          <div className="right">
            <Badge tone="info">{t("compliance.recent.automated")}</Badge>
          </div>
        </div>
        <div className="card-b">
          <div className="decision-grid">
            {(
              [
                {
                  tone: "allow",
                  title: "compliance.decisions.allowTitle",
                  text: "compliance.decisions.allowText",
                  code: "compliance.decisions.allowCode",
                },
                {
                  tone: "review",
                  title: "compliance.decisions.reviewTitle",
                  text: "compliance.decisions.reviewText",
                  code: "compliance.decisions.reviewCode",
                },
                {
                  tone: "block",
                  title: "compliance.decisions.blockTitle",
                  text: "compliance.decisions.blockText",
                  code: "compliance.decisions.blockCode",
                },
              ] as const
            ).map((state) => (
              <div className={`decision-card ${state.tone}`} key={state.tone}>
                <div className={`decision-head ${state.tone}`}>
                  <span className="dot" />
                  {t(state.title)}
                </div>
                <div className="decision-text">{t(state.text)}</div>
                <div className="decision-code">{t(state.code)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
