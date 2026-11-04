export type IconName =
  | "logo"
  | "grid"
  | "download"
  | "upload"
  | "layers"
  | "activity"
  | "branch"
  | "shield"
  | "settings"
  | "search"
  | "plus"
  | "check"
  | "check-circle"
  | "alert"
  | "lock"
  | "doc"
  | "clock"
  | "key"
  | "refresh"
  | "chevron"
  | "x"
  | "sun"
  | "moon"
  | "shield-check"
  | "copy"
  | "eth"
  | "usdc"
  | "btc";

export function Icon({
  name,
  className,
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg className={className ? `ico ${className}` : "ico"} aria-hidden="true">
      <use href={`#i-${name}`} />
    </svg>
  );
}

export function IconSprite() {
  return (
    <svg
      aria-hidden="true"
      style={{ position: "absolute", width: 0, height: 0, overflow: "hidden" }}
    >
      <symbol id="i-logo" viewBox="0 0 24 24">
        <path d="M12 2.7 20 7.2v9.6L12 21.3 4 16.8V7.2z" />
        <path d="M8.4 8.5 12 15.1l3.6-6.6" />
        <circle cx="12" cy="17.7" r=".8" fill="currentColor" stroke="none" />
      </symbol>
      <symbol id="i-grid" viewBox="0 0 24 24">
        <rect x="3.5" y="3.5" width="7" height="7" rx="2" />
        <rect x="13.5" y="3.5" width="7" height="7" rx="2" className="f" />
        <rect x="3.5" y="13.5" width="7" height="7" rx="2" />
        <rect x="13.5" y="13.5" width="7" height="7" rx="2" />
      </symbol>
      <symbol id="i-download" viewBox="0 0 24 24">
        <path d="M12 3.5v10.4" />
        <path d="m8.1 10 3.9 3.9 3.9-3.9" />
        <path d="M4.5 16.5v2.1a1.9 1.9 0 0 0 1.9 1.9h11.2a1.9 1.9 0 0 0 1.9-1.9v-2.1" />
      </symbol>
      <symbol id="i-upload" viewBox="0 0 24 24">
        <path d="M12 20.5V10.1" />
        <path d="m8.1 14 3.9-3.9 3.9 3.9" />
        <path d="M4.5 7.5V5.4a1.9 1.9 0 0 1 1.9-1.9h11.2a1.9 1.9 0 0 1 1.9 1.9v2.1" />
      </symbol>
      <symbol id="i-layers" viewBox="0 0 24 24">
        <path className="f" d="m12 3.1 8.3 4.4L12 11.9 3.7 7.5z" />
        <path d="m12 3.1 8.3 4.4L12 11.9 3.7 7.5z" />
        <path d="m4.1 12.1 7.9 4.2 7.9-4.2" />
        <path d="m4.1 16.4 7.9 4.2 7.9-4.2" />
      </symbol>
      <symbol id="i-activity" viewBox="0 0 24 24">
        <path d="M3.5 12h3.1l2.2-6.4 4.4 12.8 2.2-6.4h5.1" />
        <circle cx="18.5" cy="12" r="1.1" className="f" />
      </symbol>
      <symbol id="i-branch" viewBox="0 0 24 24">
        <circle cx="6" cy="5.2" r="2" />
        <circle cx="18" cy="7.2" r="2" />
        <circle cx="6" cy="18.8" r="2" />
        <path d="M6 7.2v9.6M8 11h4.6a5.4 5.4 0 0 0 5.4-3.8" />
      </symbol>
      <symbol id="i-shield" viewBox="0 0 24 24">
        <path className="f" d="M12 3.2 19 6.2v5.4c0 4.3-2.8 7.5-7 9.4-4.2-1.9-7-5.1-7-9.4V6.2z" />
        <path d="M12 3.2 19 6.2v5.4c0 4.3-2.8 7.5-7 9.4-4.2-1.9-7-5.1-7-9.4V6.2z" />
      </symbol>
      <symbol id="i-settings" viewBox="0 0 24 24">
        <path d="M4 7.5h9.2M17.2 7.5h2.8M4 16.5h2.8M10.8 16.5H20" />
        <circle cx="15" cy="7.5" r="2.2" />
        <circle cx="8.6" cy="16.5" r="2.2" />
      </symbol>
      <symbol id="i-search" viewBox="0 0 24 24">
        <circle cx="10.6" cy="10.6" r="6.4" />
        <path d="m15.2 15.2 5.3 5.3" />
      </symbol>
      <symbol id="i-plus" viewBox="0 0 24 24">
        <path d="M12 4.8v14.4M4.8 12h14.4" />
      </symbol>
      <symbol id="i-check" viewBox="0 0 24 24">
        <path d="m4.8 12.4 4.8 4.8L19.2 6.8" />
      </symbol>
      <symbol id="i-check-circle" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" />
        <path d="m8.1 12.2 2.6 2.6 5.2-5.6" />
      </symbol>
      <symbol id="i-alert" viewBox="0 0 24 24">
        <path d="M10.3 3.9 2.7 17.1A2 2 0 0 0 4.4 20h15.2a2 2 0 0 0 1.7-2.9L13.7 3.9a2 2 0 0 0-3.4 0z" />
        <path d="M12 9v4.2M12 16.7v.2" />
      </symbol>
      <symbol id="i-lock" viewBox="0 0 24 24">
        <rect x="4.8" y="10" width="14.4" height="10.8" rx="2.4" />
        <path d="M8.2 10V7.2a3.8 3.8 0 0 1 7.6 0V10" />
        <path d="M12 14v3" />
      </symbol>
      <symbol id="i-doc" viewBox="0 0 24 24">
        <path d="M6.2 3.2h7.6l4 4v13.6H6.2z" />
        <path d="M13.8 3.2v4.6h4.2M9 12h6M9 16h6" />
      </symbol>
      <symbol id="i-clock" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.2v5.1l3.5 2" />
      </symbol>
      <symbol id="i-key" viewBox="0 0 24 24">
        <circle cx="8.2" cy="12" r="3.8" />
        <path d="M12 12h8.2M17 12v3.2M19.8 12v2.2" />
      </symbol>
      <symbol id="i-refresh" viewBox="0 0 24 24">
        <path d="M19.8 11a7.9 7.9 0 1 0-1.4 6.4" />
        <path d="M19.8 5.2V11h-5.8" />
      </symbol>
      <symbol id="i-chevron" viewBox="0 0 24 24">
        <path d="m7 9.2 5 5 5-5" />
      </symbol>
      <symbol id="i-x" viewBox="0 0 24 24">
        <path d="M6.2 6.2 17.8 17.8M17.8 6.2 6.2 17.8" />
      </symbol>
      <symbol id="i-sun" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2.6v2M12 19.4v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.6 12h2M19.4 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </symbol>
      <symbol id="i-moon" viewBox="0 0 24 24">
        <path d="M20 14.4A8.4 8.4 0 0 1 9.6 4 8.4 8.4 0 1 0 20 14.4z" />
      </symbol>
      <symbol id="i-shield-check" viewBox="0 0 24 24">
        <path className="f" d="M12 3.2 19 6.2v5.4c0 4.3-2.8 7.5-7 9.4-4.2-1.9-7-5.1-7-9.4V6.2z" />
        <path d="M12 3.2 19 6.2v5.4c0 4.3-2.8 7.5-7 9.4-4.2-1.9-7-5.1-7-9.4V6.2z" />
        <path d="m8.9 12 2.1 2.1 4.2-4.5" />
      </symbol>
      <symbol id="i-copy" viewBox="0 0 24 24">
        <rect x="8.2" y="8.2" width="11.6" height="11.6" rx="2.2" />
        <path d="M15.8 8.2V6.2a2.2 2.2 0 0 0-2.2-2.2H6.2A2.2 2.2 0 0 0 4 6.2v7.4a2.2 2.2 0 0 0 2.2 2.2h2" />
      </symbol>
      <symbol id="i-eth" viewBox="0 0 24 24">
        <path className="f" d="M12 2.8 6 12.1l6 3.6 6-3.6z" />
        <path d="M12 2.8 6 12.1l6 3.6 6-3.6z" />
        <path d="m6 13.3 6 8 6-8" />
      </symbol>
      <symbol id="i-usdc" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 6.5v11M14.6 8.9c-.6-.6-1.5-.9-2.6-.9-1.5 0-2.6.7-2.6 1.9 0 2.8 5.4 1.4 5.4 4.3 0 1.2-1.1 2-2.7 2-1.3 0-2.3-.4-3-1.1" />
      </symbol>
      <symbol id="i-btc" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" />
        <path d="M9.5 7.4h4a2.2 2.2 0 0 1 0 4.4h-4zM9.5 11.8h4.6a2.2 2.2 0 0 1 0 4.4H9.5zM10.8 5.8v12.4M13.2 5.8v12.4" />
      </symbol>
    </svg>
  );
}

export function assetIconName(asset: string): IconName {
  const normalized = asset.toUpperCase();
  if (normalized === "USDC") return "usdc";
  if (normalized === "TBTC" || normalized === "BTC") return "btc";
  return "eth";
}

export function assetClass(asset: string): string {
  const normalized = asset.toUpperCase();
  if (normalized === "USDC") return "usdc";
  if (normalized === "TBTC" || normalized === "BTC") return "btc";
  return "eth";
}
