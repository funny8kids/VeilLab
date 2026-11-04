import type { ReactNode } from "react";
import { useI18n } from "../i18n";
import { useApp } from "../state/AppContext";
import { Icon } from "./Icon";

export function Badge({
  tone = "muted",
  dot = false,
  children,
  className = "",
}: {
  tone?: "ok" | "warn" | "danger" | "info" | "muted" | "testnet" | "violet";
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`badge ${tone} ${className}`.trim()}>
      {dot ? <span className="dot" /> : null}
      {children}
    </span>
  );
}

export function PageHead({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p className="page-sub">{subtitle}</p>
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  );
}

export function Stat({
  label,
  value,
  unit,
  detail,
  tone,
  compact = false,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  detail?: ReactNode;
  tone?: "ok" | "warn" | "danger";
  compact?: boolean;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-row">
        <div
          className="stat-value"
          style={{
            ...(tone ? { color: `var(--${tone})` } : {}),
            ...(compact ? { fontSize: 20, letterSpacing: "-.03em" } : {}),
          }}
        >
          {value}
          {unit ? <small>{unit}</small> : null}
        </div>
      </div>
      {detail ? <div className="stat-delta">{detail}</div> : null}
    </div>
  );
}

export function SummaryRow({
  label,
  value,
  total = false,
}: {
  label: string;
  value: ReactNode;
  total?: boolean;
}) {
  return (
    <div className={`summary-row${total ? " total" : ""}`}>
      <span>{label}</span>
      <span className="v">{value}</span>
    </div>
  );
}

export function StepBar({
  steps,
  current,
}: {
  steps: string[];
  current: number;
}) {
  return (
    <div className="stepbar" aria-label="Progress">
      {steps.map((step, index) => {
        const number = index + 1;
        const state =
          number === current ? "active" : number < current ? "done" : "";
        return (
          <div key={step} style={{ display: "contents" }}>
            <div className={`step ${state}`.trim()}>
              <b>{state === "done" ? <Icon name="check" /> : number}</b>
              <span>{step}</span>
            </div>
            {index < steps.length - 1 ? <span className="step-sep" /> : null}
          </div>
        );
      })}
    </div>
  );
}

export function EmptyState({
  icon = "activity",
  title,
  body,
  action,
}: {
  icon?: "activity" | "layers" | "lock" | "doc";
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon name={icon} />
      </div>
      <div className="empty-title">{title}</div>
      <p className="empty-body">{body}</p>
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function DataModeBadge() {
  const { dataMode, apiMode, loading } = useApp();
  const { t } = useI18n();
  if (loading) {
    return (
      <Badge tone="muted" dot>
        {t("shell.checkingApi")}
      </Badge>
    );
  }
  if (!apiMode) {
    return (
      <Badge tone="warn" dot>
        {t("shell.mode.demo")}
      </Badge>
    );
  }
  return (
    <>
      <Badge tone={apiMode === "local" ? "warn" : "info"} dot>
        {apiMode === "local"
          ? t("shell.mode.anvilLocal")
          : t("shell.mode.mockChain")}
      </Badge>
      {dataMode === "partial" ? (
        <Badge tone="warn">{t("shell.partialApi")}</Badge>
      ) : null}
    </>
  );
}

export function DemoTag() {
  const { t } = useI18n();
  return <Badge tone="warn">{t("demo.badge")}</Badge>;
}

export function MockTag() {
  const { t } = useI18n();
  return <Badge tone="violet">{t("common.mock")}</Badge>;
}

export function Toast() {
  const { toast } = useApp();
  return (
    <div
      className={`toast${toast ? " show" : ""}`}
      role="status"
      aria-live="polite"
    >
      {toast?.message ?? ""}
    </div>
  );
}

export function DemoBanner() {
  const { dataMode, apiError, apiBaseUrl, refreshData, loading } = useApp();
  const { t } = useI18n();
  if (dataMode === "live") return null;

  return (
    <div className={`demo-banner ${dataMode}`}>
      <div className="demo-banner-icon">
        <Icon name="alert" />
      </div>
      <div className="demo-banner-copy">
        <strong>
          {dataMode === "partial"
            ? t("demo.banner.partialTitle")
            : t("demo.banner.demoTitle")}
        </strong>
        {dataMode === "demo" ? (
          <span>{t("demo.banner.demoBody", { url: apiBaseUrl })}</span>
        ) : null}
        {apiError ? <span className="demo-reason">{t("demo.banner.error", { reason: apiError })}</span> : null}
      </div>
      <button
        type="button"
        className="btn btn-sm"
        onClick={() => void refreshData()}
        disabled={loading}
      >
        <Icon name="refresh" />
        {t("demo.banner.retry")}
      </button>
    </div>
  );
}
