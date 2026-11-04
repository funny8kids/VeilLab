import { useNavigate } from "react-router-dom";
import { useI18n, type MessageKey } from "../i18n";
import { useApp } from "../state/AppContext";
import {
  formatBps,
  formatInteger,
  formatLocalTime,
  formatMaturity,
  poolLabel,
} from "../lib/format";
import { effectiveStatus } from "../lib/activity";
import { localStatusKey, poolStatusKey, poolStatusTone } from "../lib/labels";
import { assetClass, assetIconName, Icon } from "../components/Icon";
import { Badge, EmptyState, PageHead, Stat } from "../components/ui";
import type { LocalActivityStatus } from "../types";

const HOW_STEPS: Array<{ title: MessageKey; text: MessageKey }> = [
  { title: "overview.how.1.title", text: "overview.how.1.text" },
  { title: "overview.how.2.title", text: "overview.how.2.text" },
  { title: "overview.how.3.title", text: "overview.how.3.text" },
];

export function OverviewPage() {
  const { t, lang } = useI18n();
  const { pools, relayers, policy, activity } = useApp();
  const navigate = useNavigate();

  const activePools = pools.filter((pool) => pool.status !== "paused");
  const totalSet = pools.reduce((sum, pool) => sum + pool.anonymity_set, 0);
  const onlineRelayers = relayers.filter(
    (relayer) => relayer.status === "online" || relayer.status === "degraded",
  );
  const avgFee = onlineRelayers.length
    ? Math.round(
        onlineRelayers.reduce((sum, relayer) => sum + relayer.fee_bps, 0) /
          onlineRelayers.length,
      )
    : 0;

  const recent = activity.slice(0, 3);

  return (
    <section className="screen active" id="overview">
      <PageHead
        eyebrow={t("overview.eyebrow")}
        title={t("overview.title")}
        subtitle={t("overview.sub")}
        actions={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => navigate("/withdraw")}
            >
              <Icon name="upload" />
              {t("nav.withdraw")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate("/deposit")}
            >
              <Icon name="download" />
              {t("nav.deposit")}
            </button>
          </>
        }
      />

      <div className="card stat-strip">
        <Stat
          label={t("overview.stat.pools")}
          value={formatInteger(activePools.length, lang)}
          detail={t("overview.stat.poolsDetail", { count: pools.length })}
        />
        <Stat
          label={t("overview.stat.set")}
          value={formatInteger(totalSet, lang)}
          detail={t("overview.stat.setDetail")}
        />
        <Stat
          label={t("overview.stat.relayers")}
          value={formatInteger(onlineRelayers.length, lang)}
          detail={t("overview.stat.relayersDetail", {
            fee: formatBps(avgFee),
          })}
        />
        <Stat
          label={t("overview.stat.policy")}
          value={`v${policy.policy_version}`}
          unit={policy.sanctions_list_version}
          detail={t("overview.stat.policyDetail")}
        />
      </div>

      <div className="grid main-grid" style={{ marginBottom: 14 }}>
        <div className="card span-7">
          <div className="card-h">
            <div className="card-title">{t("overview.chart.title")}</div>
            <div className="card-sub">{t("overview.chart.sub")}</div>
            <div className="right">
              <Badge tone="info">{t("demo.illustrative")}</Badge>
              <Badge tone="ok" dot>
                {t("overview.chart.healthy")}
              </Badge>
            </div>
          </div>
          <div className="card-b">
            <div className="chart-kpi">
              <strong>{formatInteger(totalSet, lang)}</strong>
              <span>+18.4%</span>
              <span className="faint" style={{ fontSize: 9 }}>
                {t("overview.chart.members")}
              </span>
            </div>
            <div className="chart-wrap">
              <svg
                className="chart"
                viewBox="0 0 720 190"
                role="img"
                aria-label={t("overview.chart.title")}
              >
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="0%"
                      stopColor="var(--accent)"
                      stopOpacity=".18"
                    />
                    <stop
                      offset="100%"
                      stopColor="var(--accent)"
                      stopOpacity="0"
                    />
                  </linearGradient>
                </defs>
                <line className="gridline" x1="0" y1="40" x2="720" y2="40" />
                <line className="gridline" x1="0" y1="85" x2="720" y2="85" />
                <line className="gridline" x1="0" y1="130" x2="720" y2="130" />
                <line className="gridline" x1="0" y1="175" x2="720" y2="175" />
                <path
                  className="area"
                  d="M0,152 C40,148 58,140 90,134 C122,128 140,132 180,120 C220,108 240,114 280,100 C320,86 340,94 380,80 C420,66 442,72 480,60 C518,48 540,56 580,44 C620,32 650,40 690,24 L720,24 L720,190 L0,190 Z"
                />
                <path
                  className="line"
                  d="M0,152 C40,148 58,140 90,134 C122,128 140,132 180,120 C220,108 240,114 280,100 C320,86 340,94 380,80 C420,66 442,72 480,60 C518,48 540,56 580,44 C620,32 650,40 690,24"
                />
                <circle className="dot" cx="720" cy="24" r="4" />
                {[0, 1, 2, 3, 4, 5, 6, 7].map((index) => (
                  <text
                    key={index}
                    className="axis"
                    x={index === 7 ? 690 : index * 100}
                    y="188"
                  >
                    W{index + 1}
                  </text>
                ))}
              </svg>
            </div>
            <div className="chart-legend">
              <span>
                <i style={{ background: "var(--accent)" }} />
                {t("overview.chart.members")}
              </span>
              <span>{t("overview.chart.legend")}</span>
            </div>
            <div className="chart-static-note">
              {t("overview.chart.note")}
            </div>
          </div>
        </div>

        <div className="card span-5">
          <div className="card-h">
            <div className="card-title">{t("overview.compliance.title")}</div>
            <div className="right">
              <Badge tone="ok" dot>
                {t("overview.compliance.enforced")}
              </Badge>
            </div>
          </div>
          <div className="card-b pad">
            <div className="check-list">
              <div className="check">
                <Icon name="check" />
                <span>{t("overview.compliance.checkScreening")}</span>
              </div>
              <div className="check">
                <Icon name="check" />
                <span>{t("overview.compliance.checkLimits")}</span>
              </div>
              <div className="check">
                <Icon name="check" />
                <span>{t("overview.compliance.checkTestnet")}</span>
              </div>
              <div className="check">
                <Icon name="check" />
                <span>
                  {t("overview.compliance.checkPolicy", {
                    version: String(policy.policy_version),
                    list: policy.sanctions_list_version ?? "—",
                  })}
                </span>
              </div>
            </div>
            <div className="approve" style={{ marginTop: 13 }}>
              <div className="t">{t("overview.compliance.mode")}</div>
              <div className="v">{t("overview.compliance.modeText")}</div>
            </div>
            <button
              type="button"
              className="btn full-width"
              style={{ marginTop: 11 }}
              onClick={() => navigate("/compliance")}
            >
              {t("common.viewPolicy")}
            </button>
          </div>
        </div>
      </div>

      <div className="grid main-grid" style={{ marginBottom: 14 }}>
        <div className="card span-7">
          <div className="card-h">
            <div className="card-title">{t("overview.pools.title")}</div>
            <div className="right">
              <button
                type="button"
                className="link-btn"
                onClick={() => navigate("/pools")}
              >
                {t("overview.pools.viewAll")}
              </button>
            </div>
          </div>
          <div className="card-b" style={{ paddingTop: 0 }}>
            {pools.slice(0, 4).map((pool) => (
              <div className="row" key={pool.id} style={{ paddingTop: 8 }}>
                <div className={`asset-icon ${assetClass(pool.asset)}`}>
                  <Icon name={assetIconName(pool.asset)} />
                </div>
                <div className="row-main">
                  <div className="row-title">{poolLabel(pool)}</div>
                  <div className="row-sub">
                    {t("overview.pools.maturity", {
                      maturity: formatMaturity(pool.maturity_seconds),
                    })}
                  </div>
                </div>
                <span className="row-meta">
                  {formatInteger(pool.anonymity_set, lang)}{" "}
                  {t("common.anonymitySet")}
                </span>
                <Badge tone={poolStatusTone(pool)} dot>
                  {t(poolStatusKey(pool))}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        <div className="card span-5">
          <div className="card-h">
            <div className="card-title">{t("overview.activity.title")}</div>
            <div className="right">
              <Badge tone="muted">{t("common.privateToYou")}</Badge>
            </div>
          </div>
          <div className="card-b">
            {recent.length === 0 ? (
              <EmptyState
                title={t("overview.activity.emptyTitle")}
                body={t("overview.activity.empty")}
                action={
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => navigate("/deposit")}
                  >
                    <Icon name="download" />
                    {t("overview.activity.emptyCta")}
                  </button>
                }
              />
            ) : (
              <div className="timeline">
                {recent.map((record) => {
                  const status: LocalActivityStatus = effectiveStatus(record);
                  return (
                    <div className="tl-item" key={record.id}>
                      <span
                        className={`tl-dot ${
                          status === "failed"
                            ? "active"
                            : status === "pending" || status === "submitted"
                              ? "active"
                              : "done"
                        }`}
                      />
                      <div className="tl-title">
                        {record.kind === "deposit"
                          ? `${t("nav.deposit")} ${record.asset} · ${record.denomination}`
                          : `${t("nav.withdraw")} ${record.asset} · ${record.denomination}`}
                      </div>
                      <div className="tl-sub">
                        {record.noteId}
                        {record.relayerName ? ` · ${record.relayerName}` : ""} ·{" "}
                        {t(localStatusKey(status))}
                      </div>
                      <div className="tl-time">
                        {formatLocalTime(record.createdAt, lang)}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <div className="card-title">{t("overview.how.title")}</div>
          <div className="right">
            <Badge tone="info">{t("overview.how.steps")}</Badge>
          </div>
        </div>
        <div className="card-b">
          <div className="how-grid">
            {HOW_STEPS.map((step, index) => (
              <div className="how-step" key={step.title}>
                <div className="how-num">0{index + 1}</div>
                <div className="how-title">{t(step.title)}</div>
                <div className="how-text">{t(step.text)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
