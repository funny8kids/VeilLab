import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, API_BASE_URL, isApiTokenConfigured } from "../lib/api";
import { DEMO_POLICY, DEMO_POOLS, DEMO_RELAYERS } from "../lib/demoData";
import { healthStatusIsFailure, summarizeHealth } from "../lib/health";
import {
  addActivity as persistActivity,
  clearActivity as clearPersistedActivity,
  readActivity,
} from "../lib/activity";
import {
  clearVault,
  hasVaultSessionKey,
  lockVaultSession,
  markNoteBackedUp,
  markNoteSpent,
  vaultSummary,
} from "../lib/vault";
import {
  AUTO_LOCK_CHECK_MS,
  shouldAutoLock,
  vaultIsLocked,
} from "../lib/session";
import type {
  ApiMode,
  CompliancePolicy,
  DataMode,
  HealthStatus,
  LocalActivityRecord,
  Pool,
  Relayer,
  VaultSummary,
} from "../types";

export type Theme = "dark" | "light";

const THEME_KEY = "veilpool.theme";

interface ToastState {
  id: number;
  message: string;
}

interface AppContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  pools: Pool[];
  relayers: Relayer[];
  policy: CompliancePolicy;
  dataMode: DataMode;
  apiMode: ApiMode | null;
  health: HealthStatus | null;
  authConfigured: boolean;
  apiError: string | null;
  loading: boolean;
  refreshData: () => Promise<void>;
  activity: LocalActivityRecord[];
  vault: VaultSummary;
  sessionUnlocked: boolean;
  vaultLocked: boolean;
  lockVault: () => void;
  recordActivity: (record: LocalActivityRecord) => void;
  markVaultBackedUp: (noteId: string) => void;
  markVaultSpent: (noteId: string) => void;
  clearLocalData: () => void;
  reloadLocalData: () => void;
  toast: ToastState | null;
  notify: (message: string) => void;
  apiBaseUrl: string;
}

const AppContext = createContext<AppContextValue | null>(null);

function readInitialTheme(): Theme {
  if (typeof window !== "undefined") {
    const requested = new URLSearchParams(window.location.search).get("theme");
    if (requested === "light" || requested === "dark") return requested;
  }
  if (typeof localStorage !== "undefined") {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
  }
  return "dark";
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "The API could not be reached.";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkHealthWithRetry(attempts = 3): Promise<HealthStatus> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const health = await api.health();
      if (healthStatusIsFailure(health?.status)) {
        throw new Error(`API health reports "${health.status}".`);
      }
      return health;
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) {
        await delay(600 * (attempt + 1));
      }
    }
  }
  throw lastError ?? new Error("The API health check failed.");
}

function normalizePolicy(raw: CompliancePolicy): CompliancePolicy {
  return {
    policy_version: raw.policy_version ?? "—",
    sanctions_list_version: raw.sanctions_list_version,
    updated_at: raw.updated_at,
    daily_deposit_limit: raw.daily_deposit_limit,
    daily_withdrawal_limit: raw.daily_withdrawal_limit,
    per_transaction_limit: raw.per_transaction_limit,
    review_sla_hours: raw.review_sla_hours,
    allowed_jurisdictions: raw.allowed_jurisdictions ?? [],
    blocked_jurisdictions: raw.blocked_jurisdictions ?? [],
    screening_sources: raw.screening_sources ?? [],
  };
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitialTheme);
  const [pools, setPools] = useState<Pool[]>(DEMO_POOLS);
  const [relayers, setRelayers] = useState<Relayer[]>(DEMO_RELAYERS);
  const [policy, setPolicy] = useState<CompliancePolicy>(DEMO_POLICY);
  const [dataMode, setDataMode] = useState<DataMode>("demo");
  const [apiMode, setApiMode] = useState<ApiMode | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activity, setActivity] = useState<LocalActivityRecord[]>(readActivity);
  const [vault, setVault] = useState<VaultSummary>(vaultSummary);
  const [sessionUnlocked, setSessionUnlocked] = useState<boolean>(
    hasVaultSessionKey,
  );
  const [toast, setToast] = useState<ToastState | null>(null);
  const toastTimer = useRef<number | null>(null);
  const toastCounter = useRef(0);
  const lastActivity = useRef(Date.now());
  const refreshInFlight = useRef(false);
  const refreshSequence = useRef(0);
  const lastSilentRefresh = useRef(0);

  const vaultLocked = vaultIsLocked(sessionUnlocked, vault.total);
  const authConfigured = isApiTokenConfigured();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* Preferences are optional. */
    }
  }, [theme]);

  useEffect(() => {
    return () => {
      if (toastTimer.current !== null) {
        window.clearTimeout(toastTimer.current);
      }
    };
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  const notify = useCallback((message: string) => {
    if (toastTimer.current !== null) {
      window.clearTimeout(toastTimer.current);
    }
    toastCounter.current += 1;
    setToast({ id: toastCounter.current, message });
    toastTimer.current = window.setTimeout(() => setToast(null), 2800);
  }, []);

  const loadData = useCallback(async (silent: boolean) => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    const sequence = refreshSequence.current + 1;
    refreshSequence.current = sequence;
    if (!silent) setLoading(true);
    setApiError(null);

    try {
      let healthStatus: HealthStatus;
      try {
        healthStatus = await checkHealthWithRetry();
      } catch (error) {
        if (sequence !== refreshSequence.current) return;
        setPools(DEMO_POOLS);
        setRelayers(DEMO_RELAYERS);
        setPolicy(DEMO_POLICY);
        setDataMode("demo");
        setHealth(null);
        setApiMode(null);
        setApiError(errorMessage(error));
        return;
      }

      if (sequence !== refreshSequence.current) return;
      setHealth(healthStatus);
      setApiMode(summarizeHealth(healthStatus).apiMode);

      const [poolsResult, relayersResult, policyResult] =
        await Promise.allSettled([api.pools(), api.relayers(), api.policy()]);

      if (sequence !== refreshSequence.current) return;

      let partial = false;
      let lastError: unknown = null;

      if (
        poolsResult.status === "fulfilled" &&
        poolsResult.value.length > 0
      ) {
        setPools(poolsResult.value);
      } else {
        setPools(DEMO_POOLS);
        partial = true;
        if (poolsResult.status === "rejected") lastError = poolsResult.reason;
      }

      if (
        relayersResult.status === "fulfilled" &&
        relayersResult.value.length > 0
      ) {
        setRelayers(relayersResult.value);
      } else {
        setRelayers(DEMO_RELAYERS);
        partial = true;
        if (relayersResult.status === "rejected") {
          lastError = relayersResult.reason;
        }
      }

      if (policyResult.status === "fulfilled" && policyResult.value) {
        setPolicy(normalizePolicy(policyResult.value));
      } else {
        setPolicy(DEMO_POLICY);
        partial = true;
        if (policyResult.status === "rejected") lastError = policyResult.reason;
      }

      // Full API data requires health plus every core resource. A missing or
      // empty response keeps the affected panels in labelled demo mode.
      setDataMode(partial ? "partial" : "live");
      setApiError(partial && lastError ? errorMessage(lastError) : null);
    } finally {
      refreshInFlight.current = false;
      if (!silent) setLoading(false);
    }
  }, []);

  const refreshData = useCallback(async () => {
    await loadData(false);
  }, [loadData]);

  useEffect(() => {
    void loadData(false);
  }, [loadData]);

  // Revalidate on focus and retry failed health checks while the app is in
  // demo/partial mode. Both paths are silent so they do not flash the UI.
  useEffect(() => {
    const revalidate = () => {
      const now = Date.now();
      if (now - lastSilentRefresh.current < 5_000) return;
      lastSilentRefresh.current = now;
      void loadData(true);
    };
    const handleFocus = () => revalidate();
    window.addEventListener("focus", handleFocus);
    const timer = window.setInterval(() => {
      if (dataMode !== "live" && document.visibilityState === "visible") {
        revalidate();
      }
    }, 30_000);
    return () => {
      window.removeEventListener("focus", handleFocus);
      window.clearInterval(timer);
    };
  }, [loadData, dataMode]);

  const lockVault = useCallback(() => {
    lockVaultSession();
    setSessionUnlocked(false);
  }, []);

  useEffect(() => {
    if (!sessionUnlocked) return;
    lastActivity.current = Date.now();

    const markActivity = () => {
      lastActivity.current = Date.now();
    };
    const events = [
      "pointerdown",
      "mousemove",
      "keydown",
      "wheel",
      "touchstart",
      "scroll",
    ] as const;
    for (const event of events) {
      window.addEventListener(event, markActivity, { passive: true });
    }

    const timer = window.setInterval(() => {
      if (shouldAutoLock(lastActivity.current)) {
        lockVault();
      }
    }, AUTO_LOCK_CHECK_MS);

    return () => {
      window.clearInterval(timer);
      for (const event of events) {
        window.removeEventListener(event, markActivity);
      }
    };
  }, [sessionUnlocked, lockVault]);

  const recordActivity = useCallback((record: LocalActivityRecord) => {
    setActivity(persistActivity(record));
  }, []);

  const markVaultBackedUp = useCallback((noteId: string) => {
    markNoteBackedUp(noteId);
    setVault(vaultSummary());
  }, []);

  const markVaultSpent = useCallback((noteId: string) => {
    markNoteSpent(noteId);
    setVault(vaultSummary());
  }, []);

  const reloadLocalData = useCallback(() => {
    setActivity(readActivity());
    setVault(vaultSummary());
    setSessionUnlocked(hasVaultSessionKey());
  }, []);

  const clearLocalData = useCallback(() => {
    clearPersistedActivity();
    clearVault();
    setActivity([]);
    setVault(vaultSummary());
    setSessionUnlocked(false);
  }, []);

  const value = useMemo<AppContextValue>(
    () => ({
      theme,
      toggleTheme,
      setTheme,
      pools,
      relayers,
      policy,
      dataMode,
      apiMode,
      health,
      authConfigured,
      apiError,
      loading,
      refreshData,
      activity,
      vault,
      sessionUnlocked,
      vaultLocked,
      lockVault,
      recordActivity,
      markVaultBackedUp,
      markVaultSpent,
      clearLocalData,
      reloadLocalData,
      toast,
      notify,
      apiBaseUrl: API_BASE_URL,
    }),
    [
      theme,
      toggleTheme,
      setTheme,
      pools,
      relayers,
      policy,
      dataMode,
      apiMode,
      health,
      authConfigured,
      apiError,
      loading,
      refreshData,
      activity,
      vault,
      sessionUnlocked,
      vaultLocked,
      lockVault,
      recordActivity,
      markVaultBackedUp,
      markVaultSpent,
      clearLocalData,
      reloadLocalData,
      toast,
      notify,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside AppProvider");
  return value;
}
