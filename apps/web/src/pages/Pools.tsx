import { useNavigate } from "react-router-dom";
import { useI18n, type MessageKey } from "../i18n";
import { useApp } from "../state/AppContext";
import {
  formatBps,
  formatCompact,
  formatInteger,
  formatMaturity,
  formatUnits,
  isLowSet,
  poolLabel,
} from "../lib/format";
import { poolStatusKey, poolStatusTone } from "../lib/labels";
import { assetClass, assetIconName, Icon } from "../components/Icon";
import { Badge, PageHead } from "../components/ui";
import type { Pool } from "../types";

function liquidityLabel(pool: Pool, lang: "en" | "zh"): string {
  if (!pool.liquidity_wei) return "—";
  const decimals = pool.asset === "USDC" ? 6 : pool.asset === "tBTC" ? 8 : 18;
  const formatted = formatUnits(pool.liquidity_wei, decimals, 4);
  const units = Number(formatted);
  if (Number.isNaN(units)) return "—";
  return units >= 1000
    ? `${formatCompact(units, lang)} ${pool.asset}`
    : `${formatted} ${pool.asset}`;
}

const RULES: Array<{ title: MessageKey; text: MessageKey }> = [
  { title: "pools.rules.fixed", text: "pools.rules.fixedText" },
  { title: "pools.rules.maturity", text: "pools.rules.maturityText" },
  { title: "pools.rules.compliance", text: "pools.rules.complianceText" },
];

export function PoolsPage() {
  const { t, lang } = useI18n();
  const { pools, refreshData, loading } = useApp();
  const navigate = useNavigate();

  return (
    <section className="screen active" id="pools">
      <PageHead
        eyebrow={t("pools.eyebrow")}
        title={t("pools.title")}
        subtitle={t("pools.sub")}
        actions={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => void refreshData()}
              disabled={loading}
            >
              <Icon name="refresh" />
              {loading ? t("common.loading") : t("common.refresh")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate("/deposit")}
            >
              <Icon name="plus" />
              {t("nav.deposit")}
            </button>
          </>
        }
      />

      <div className="pool-grid" style={{ marginBottom: 14 }}>
        {pools.map((pool) => (
          <div className="card pool-card" key={pool.id}>
            <div className="pool-top">
              <div className={`asset-icon ${assetClass(pool.asset)}`}>
                <Icon name={assetIconName(pool.asset)} />
              </div>
              <div>
                <div className="pool-name">{poolLabel(pool)}</div>
                <div className="pool-sub">
                  {t("pools.maturity", {
                    time: formatMaturity(pool.maturity_seconds),
                  })}
                </div>
              </div>
              <Badge tone={poolStatusTone(pool)} dot className="pool-badge">
                {t(poolStatusKey(pool))}
              </Badge>
            </div>

            <div className="pool-metrics">
              <div className="pool-metric">
                <div className="v">{formatInteger(pool.anonymity_set, lang)}</div>
                <div className="l">{t("pools.metric.set")}</div>
              </div>
              <div className="pool-metric">
                <div className="v">{formatBps(pool.protocol_fee_bps)}</div>
                <div className="l">{t("pools.metric.fee")}</div>
              </div>
              <div className="pool-metric">
                <div className="v">{liquidityLabel(pool, lang)}</div>
                <div className="l">{t("pools.metric.liquidity")}</div>
              </div>
              <div className="pool-metric">
                <div className="v">
                  {pool.denomination} {pool.asset}
                </div>
                <div className="l">{t("pools.metric.denomination")}</div>
              </div>
            </div>

            {isLowSet(pool) ? (
              <div className="inline-alert warn" style={{ marginTop: 0 }}>
                <Icon name="alert" />
                <span>{t("pools.lowSetWarning")}</span>
              </div>
            ) : null}

            <div className="pool-foot">
              <button
                type="button"
                className="btn btn-sm"
                style={{ flex: 1 }}
                onClick={() => navigate(`/deposit?pool=${pool.id}`)}
              >
                {t("pools.deposit")}
              </button>
              <button
                type="button"
                className="btn btn-sm"
                style={{ flex: 1 }}
                onClick={() => navigate(`/withdraw?pool=${pool.id}`)}
              >
                {t("pools.withdraw")}
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-h">
          <div className="card-title">{t("pools.rules.title")}</div>
          <div className="right">
            <Badge tone="info">{t("pools.rules.fixed")}</Badge>
          </div>
        </div>
        <div className="card-b">
          <div className="how-grid">
            {RULES.map((rule) => (
              <div className="how-step" key={rule.title}>
                <div className="how-title">{t(rule.title)}</div>
                <div className="how-text">{t(rule.text)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
