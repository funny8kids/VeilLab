import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { IconSprite } from "./components/Icon";
import { PageHead } from "./components/ui";
import { useI18n } from "./i18n";
import { ActivityPage } from "./pages/Activity";
import { CompliancePage } from "./pages/Compliance";
import { DepositPage } from "./pages/Deposit";
import { OverviewPage } from "./pages/Overview";
import { PoolsPage } from "./pages/Pools";
import { RelayersPage } from "./pages/Relayers";
import { SettingsPage } from "./pages/Settings";
import { WithdrawPage } from "./pages/Withdraw";

function NotFoundPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  return (
    <section className="screen active">
      <PageHead
        eyebrow="VeilPool"
        title={t("notfound.title")}
        subtitle={t("notfound.body")}
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => navigate("/overview")}
          >
            {t("notfound.back")}
          </button>
        }
      />
    </section>
  );
}

export function App() {
  return (
    <>
      <IconSprite />
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/deposit" element={<DepositPage />} />
          <Route path="/withdraw" element={<WithdrawPage />} />
          <Route path="/pools" element={<PoolsPage />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/relayers" element={<RelayersPage />} />
          <Route path="/compliance" element={<CompliancePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </>
  );
}
