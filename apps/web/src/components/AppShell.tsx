import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useI18n, type MessageKey } from "../i18n";
import { useApp } from "../state/AppContext";
import { Badge, DataModeBadge, DemoBanner, Toast } from "./ui";
import { Icon, type IconName } from "./Icon";

interface NavItem {
  to: string;
  labelKey: MessageKey;
  icon: IconName;
}

const NAV_GROUPS: Array<{ labelKey: MessageKey; items: NavItem[] }> = [
  {
    labelKey: "nav.group.pool",
    items: [
      { to: "/overview", labelKey: "nav.overview", icon: "grid" },
      { to: "/deposit", labelKey: "nav.deposit", icon: "download" },
      { to: "/withdraw", labelKey: "nav.withdraw", icon: "upload" },
    ],
  },
  {
    labelKey: "nav.group.liquidity",
    items: [
      { to: "/pools", labelKey: "nav.pools", icon: "layers" },
      { to: "/activity", labelKey: "nav.activity", icon: "activity" },
      { to: "/relayers", labelKey: "nav.relayers", icon: "branch" },
    ],
  },
  {
    labelKey: "nav.group.trust",
    items: [
      { to: "/compliance", labelKey: "nav.compliance", icon: "shield-check" },
      { to: "/settings", labelKey: "nav.settings", icon: "settings" },
    ],
  },
];

const ROUTE_TITLES: Record<string, MessageKey> = {
  "/overview": "nav.overview",
  "/deposit": "nav.deposit",
  "/withdraw": "nav.withdraw",
  "/pools": "nav.pools",
  "/activity": "nav.activity",
  "/relayers": "nav.relayers",
  "/compliance": "nav.compliance",
  "/settings": "nav.settings",
};

export function AppShell() {
  const {
    theme,
    toggleTheme,
    dataMode,
    apiMode,
    loading,
    vaultLocked,
  } = useApp();
  const { lang, setLang, t } = useI18n();
  const location = useLocation();
  const titleKey = ROUTE_TITLES[location.pathname] ?? "nav.overview";

  useEffect(() => {
    document.title = `VeilPool · ${t(titleKey)}`;
  }, [t, titleKey]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [location.pathname]);

  useEffect(() => {
    const handlePointer = (event: PointerEvent) => {
      document.body.style.setProperty("--glow-x", `${event.clientX}px`);
      document.body.style.setProperty("--glow-y", `${event.clientY}px`);
    };
    window.addEventListener("pointermove", handlePointer, { passive: true });
    return () => window.removeEventListener("pointermove", handlePointer);
  }, []);

  const statusText = !apiMode
    ? t("shell.demoStatus")
    : dataMode === "partial"
      ? t("shell.partialStatus")
      : apiMode === "local"
        ? t("shell.localConnected")
        : t("shell.mockConnected");
  const statusTone = dataMode === "live" ? "ok" : "warn";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="logo" />
          </div>
          <div>
            <div className="brand-name">VeilLab</div>
            <span className="brand-sub">{t("brand.sub")}</span>
          </div>
        </div>

        <div className="workspace" aria-label={t("workspace.sub")}>
          <div className="workspace-avatar">VP</div>
          <div className="workspace-meta">
            <div className="workspace-name">VeilPool</div>
            <div className="workspace-sub">{t("workspace.sub")}</div>
          </div>
          <Badge
            tone={
              dataMode === "live" && apiMode !== "local" ? "ok" : "warn"
            }
            className="workspace-mode"
          >
            {!apiMode
              ? t("common.demo")
              : apiMode === "local"
                ? t("shell.workspace.anvil")
                : t("shell.workspace.mock")}
          </Badge>
        </div>

        <nav className="nav" aria-label="Primary">
          {NAV_GROUPS.map((group) => (
            <div key={group.labelKey}>
              <div className="nav-label">{t(group.labelKey)}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `nav-item${isActive ? " active" : ""}`
                  }
                >
                  <Icon name={item.icon} />
                  <span>{t(item.labelKey)}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="status-line">
            <span className={`dot ${statusTone}`} />
            <span>{loading ? t("common.loading") : statusText}</span>
          </div>
          <div className="version">{t("shell.version")}</div>
          <div className="footer-warning">{t("shell.footer")}</div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="crumbs">
            <span>VeilPool</span>
            <span className="sep">/</span>
            <strong>{t(titleKey)}</strong>
          </div>
          <div className="top-actions">
            {vaultLocked ? (
              <Badge tone="warn" dot>
                <Icon name="lock" />
                {t("shell.vaultLocked")}
              </Badge>
            ) : null}
            <DataModeBadge />
            <div
              className="seg"
              id="lang-toggle"
              role="group"
              aria-label={t("shell.language")}
            >
              <button
                type="button"
                className={lang === "en" ? "active" : ""}
                aria-pressed={lang === "en"}
                aria-label="English"
                onClick={() => setLang("en")}
              >
                EN
              </button>
              <button
                type="button"
                className={lang === "zh" ? "active" : ""}
                aria-pressed={lang === "zh"}
                aria-label="中文"
                onClick={() => setLang("zh")}
              >
                中
              </button>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={toggleTheme}
              aria-label={t("shell.theme")}
              title={t("shell.theme")}
            >
              <Icon
                name="sun"
                className={`toggle-icon sun${theme === "light" ? " current" : ""}`}
              />
              <Icon
                name="moon"
                className={`toggle-icon moon${theme === "dark" ? " current" : ""}`}
              />
            </button>
            <span className="badge testnet">
              <span className="dot" />
              {t("shell.testnet")}
            </span>
            <div className="avatar" title={t("shell.avatar")}>
              VP
            </div>
          </div>
        </header>

        <main className="content">
          <DemoBanner />
          <Outlet />
        </main>
      </div>
      <Toast />
    </div>
  );
}
