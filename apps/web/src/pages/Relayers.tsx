import { useNavigate } from "react-router-dom";
import { useI18n, type MessageKey } from "../i18n";
import { useApp } from "../state/AppContext";
import { DEMO_METRICS } from "../lib/demoData";
import { formatBps, formatUptime, poolLabel } from "../lib/format";
import { Icon } from "../components/Icon";
import { Badge, PageHead, Stat } from "../components/ui";
import type { Relayer } from "../types";

function relayerTag(relayer: Relayer, index: number): {
  key: "best" | "fast" | "community" | "new" | "slower" | "offline";
  tone: "ok" | "info" | "muted" | "warn" | "danger";
} {
  if (relayer.status === "offline") return { key: "offline", tone: "danger" };
  if (relayer.status === "degraded" || relayer.latency_ms > 100) {
    return { key: "slower", tone: "warn" };
  }
  if (index === 0) return { key: "best", tone: "ok" };
  if (relayer.latency_ms <= 40) return { key: "fast", tone: "info" };
  if (relayer.supported_pools.length >= 6) return { key: "community", tone: "muted" };
  return { key: "new", tone: "info" };
}

export function RelayersPage() {
  const { t } = useI18n();
  const { relayers, pools, notify } = useApp();
  const navigate = useNavigate();
  const poolMap = new Map(pools.map((pool) => [pool.id, poolLabel(pool)]));

  const online = relayers.filter((relayer) => relayer.status === "online");
  const avgFee = online.length
    ? Math.round(online.reduce((sum, relayer) => sum + relayer.fee_bps, 0) / online.length)
    : 0;
  const fastest = relayers.length
    ? Math.min(...relayers.map((relayer) => relayer.latency_ms))
    : 0;

  return (
    <section className="screen active" id="relayers">
      <PageHead
        eyebrow={t("relayers.eyebrow")}
        title={t("relayers.title")}
        subtitle={t("relayers.sub")}
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => notify(t("relayers.runToast"))}
          >
            <Icon name="plus" />
            {t("relayers.run")}
          </button>
        }
      />

      <div className="card stat-strip" style={{ marginBottom: 14 }}>
        <Stat
          label={t("relayers.available.title")}
          value={online.length}
          detail={t("relayers.online", { count: online.length })}
        />
        <Stat
          label={t("relayers.economics.avgFee")}
          value={formatBps(avgFee)}
          detail={t("common.fee")}
        />
        <Stat
          label={t("common.latency")}
          value={`${fastest}ms`}
          detail={t("relayers.stat.latencyDetail")}
        />
        <Stat
          label={t("relayers.economics.volume")}
          value={DEMO_METRICS.withdrawals_24h}
          detail={t("demo.sample")}
        />
      </div>

      <div className="grid main-grid">
        <div className="card span-8">
          <div className="card-h">
            <div className="card-title">{t("relayers.available.title")}</div>
            <div className="right">
              <Badge tone="ok" dot>
                {t("relayers.online", { count: online.length })}
              </Badge>
            </div>
          </div>
          <div className="card-b" style={{ paddingTop: 0 }}>
            {relayers.map((relayer, index) => {
              const tag = relayerTag(relayer, index);
              const supported = relayer.supported_pools
                .map((poolId) => poolMap.get(poolId))
                .filter(Boolean);
              return (
                <div
                  className="relayer-row"
                  key={relayer.id}
                  style={{ paddingTop: index === 0 ? 8 : undefined }}
                >
                  <div className="relayer-avatar">R{index + 1}</div>
                  <div className="relayer-main">
                    <div className="relayer-name">{relayer.name}</div>
                    <div className="relayer-sub">
                      {t("relayers.uptimeLatency", {
                        uptime: formatUptime(relayer.uptime_bps),
                        latency: relayer.latency_ms,
                      })}
                    </div>
                    <div className="relayer-pool-list">
                      {supported.slice(0, 4).map((pool) => (
                        <span className="chip" key={pool}>
                          {pool}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="relayer-metric">
                    {formatBps(relayer.fee_bps)}
                  </span>
                  <Badge tone={tag.tone} dot={tag.tone === "ok"}>
                    {t(`common.${tag.key}` as MessageKey)}
                  </Badge>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => navigate(`/withdraw?relayer=${relayer.id}`)}
                    disabled={
                      relayer.status === "offline" || relayer.status === "disabled"
                    }
                  >
                    {t("common.select")}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        <div className="span-4 settings-stack">
          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("relayers.model.title")}</div>
              <div className="right">
                <Badge tone="info">{t("relayers.model.nonCustodial")}</Badge>
              </div>
            </div>
            <div className="card-b">
              <div className="guard">
                <Icon name="lock" />
                <span>{t("relayers.model.1")}</span>
              </div>
              <div className="guard">
                <Icon name="lock" />
                <span>{t("relayers.model.2")}</span>
              </div>
              <div className="guard">
                <Icon name="lock" />
                <span>{t("relayers.model.3")}</span>
              </div>
              <div className="guard">
                <Icon name="lock" />
                <span>{t("relayers.model.4")}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("relayers.economics.title")}</div>
              <div className="right">
                <Badge tone="warn">{t("demo.badge")}</Badge>
              </div>
            </div>
            <div className="card-b pad">
              <div className="summary">
                <div className="summary-row">
                  <span>{t("relayers.economics.avgFee")}</span>
                  <span className="v">{formatBps(avgFee)}</span>
                </div>
                <div className="summary-row">
                  <span>{t("relayers.economics.volume")}</span>
                  <span className="v">{DEMO_METRICS.withdrawals_24h}</span>
                </div>
                <div className="summary-row">
                  <span>{t("relayers.economics.revenue")}</span>
                  <span className="v">$184.20</span>
                </div>
              </div>
              <div className="card-note" style={{ marginTop: 9 }}>
                {t("relayers.disclaimer")}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
