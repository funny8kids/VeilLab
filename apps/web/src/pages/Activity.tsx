import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useI18n } from "../i18n";
import { useApp } from "../state/AppContext";
import {
  activityStatusTone,
  countByKind,
  effectiveStatus,
  exportActivity,
} from "../lib/activity";
import { listVaultMeta } from "../lib/vault";
import { downloadTextFile } from "../lib/download";
import { formatLocalTime } from "../lib/format";
import { localStatusKey } from "../lib/labels";
import { Icon } from "../components/Icon";
import { Badge, EmptyState, PageHead } from "../components/ui";
import type { LocalActivityRecord } from "../types";

type Tab = "all" | "deposits" | "withdrawals";

function activityTitle(record: LocalActivityRecord, lang: "en" | "zh"): string {
  const action =
    record.kind === "deposit"
      ? lang === "zh"
        ? "存入"
        : "Deposit"
      : lang === "zh"
        ? "提取"
        : "Withdraw";
  return `${action} ${record.asset} · ${record.denomination}`;
}

export function ActivityPage() {
  const { t, lang } = useI18n();
  const { activity, vault, notify } = useApp();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("all");

  const counts = countByKind(activity);
  const filtered = useMemo(() => {
    if (tab === "deposits") {
      return activity.filter((record) => record.kind === "deposit");
    }
    if (tab === "withdrawals") {
      return activity.filter((record) => record.kind === "withdrawal");
    }
    return activity;
  }, [activity, tab]);

  const unbacked = listVaultMeta().filter(
    (record) => !record.backedUp && !record.spent,
  );

  const handleExport = () => {
    downloadTextFile(
      `veilpool-activity-${new Date().toISOString().slice(0, 10)}.json`,
      exportActivity(activity),
    );
    notify(t("activity.exported"));
  };

  return (
    <section className="screen active" id="activity">
      <PageHead
        eyebrow={t("activity.eyebrow")}
        title={t("activity.title")}
        subtitle={t("activity.sub")}
        actions={
          <>
            <button type="button" className="btn" onClick={handleExport}>
              <Icon name="download" />
              {t("activity.export")}
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

      <div className="tabs" role="tablist" aria-label={t("activity.title")}>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "all"}
          className={`tab${tab === "all" ? " active" : ""}`}
          onClick={() => setTab("all")}
        >
          {t("activity.tabs.all")}
          <span className="count">{activity.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "deposits"}
          className={`tab${tab === "deposits" ? " active" : ""}`}
          onClick={() => setTab("deposits")}
        >
          {t("activity.tabs.deposits")}
          <span className="count">{counts.deposits}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "withdrawals"}
          className={`tab${tab === "withdrawals" ? " active" : ""}`}
          onClick={() => setTab("withdrawals")}
        >
          {t("activity.tabs.withdrawals")}
          <span className="count">{counts.withdrawals}</span>
        </button>
      </div>

      <div className="grid main-grid">
        <div className="card span-8">
          <div className="card-h">
            <div className="card-title">{t("activity.list.title")}</div>
            <div className="right">
              <Badge tone="muted">{t("common.localSync")}</Badge>
            </div>
          </div>
          <div className="card-b" style={{ paddingTop: 0 }}>
            {filtered.length === 0 ? (
              <EmptyState
                title={t("activity.empty.title")}
                body={t("activity.empty.body")}
                action={
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => navigate("/deposit")}
                  >
                    <Icon name="download" />
                    {t("activity.empty.cta")}
                  </button>
                }
              />
            ) : (
              filtered.map((record) => {
                const status = effectiveStatus(record);
                return (
                  <div className="row" key={record.id} style={{ paddingTop: 8 }}>
                    <div
                      className={`activity-icon ${
                        record.kind === "deposit" ? "in" : "out"
                      }`}
                    >
                      <Icon
                        name={record.kind === "deposit" ? "download" : "upload"}
                      />
                    </div>
                    <div className="row-main">
                      <div className="row-title">
                        {activityTitle(record, lang)}
                      </div>
                      <div className="row-sub">
                        {record.noteId} ·{" "}
                        {formatLocalTime(record.createdAt, lang)}
                        {record.relayerName ? ` · ${record.relayerName}` : ""}
                      </div>
                    </div>
                    <div className="activity-meta">
                      {record.demo ? (
                        <Badge tone="warn">{t("activity.demoRow")}</Badge>
                      ) : null}
                      <Badge tone={activityStatusTone(status)} dot>
                        {t(localStatusKey(status))}
                      </Badge>
                      <span className="row-meta">
                        {record.denomination} {record.asset}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="span-4 settings-stack">
          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("activity.backup.title")}</div>
              <div className="right">
                {unbacked.length > 0 ? (
                  <Badge tone="warn" dot>
                    {t("activity.backup.unbacked", { count: unbacked.length })}
                  </Badge>
                ) : (
                  <Badge tone="ok">
                    {vault.total > 0
                      ? t("common.backedUp")
                      : t("common.none")}
                  </Badge>
                )}
              </div>
            </div>
            <div className="card-b pad">
              {vault.total === 0 ? (
                <div className="card-note">{t("activity.backup.none")}</div>
              ) : (
                <div className="card-note">
                  {unbacked.length > 0
                    ? t("activity.backup.text", { noteId: unbacked[0].id })
                    : t("settings.backup.ready")}
                </div>
              )}
              <button
                type="button"
                className="btn full-width"
                style={{ marginTop: 10 }}
                onClick={() => navigate("/settings")}
                disabled={vault.total === 0}
              >
                <Icon name="download" />
                {t("activity.backup.export")}
              </button>
            </div>
          </div>

          <div className="card">
            <div className="card-h">
              <div className="card-title">{t("activity.privacy.title")}</div>
              <div className="right">
                <Badge tone="ok" dot>
                  {t("common.localOnly")}
                </Badge>
              </div>
            </div>
            <div className="card-b">
              <div className="check-list">
                <div className="check">
                  <Icon name="check" />
                  <span>{t("activity.privacy.local")}</span>
                </div>
                <div className="check">
                  <Icon name="check" />
                  <span>{t("activity.privacy.noGraph")}</span>
                </div>
                <div className="check">
                  <Icon name="check" />
                  <span>{t("activity.privacy.timing")}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
