import type { Pool } from "../types";

export function assetDecimals(asset: string): number {
  switch (asset.toUpperCase()) {
    case "USDC":
      return 6;
    case "TBTC":
      return 8;
    default:
      return 18;
  }
}

export function formatUnits(
  wei: string | undefined,
  decimals: number,
  maxFraction = 4,
): string {
  if (!wei) return "—";
  try {
    const value = BigInt(wei);
    const base = 10n ** BigInt(decimals);
    const whole = value / base;
    const fraction = value % base;
    const fractionText = fraction
      .toString()
      .padStart(decimals, "0")
      .slice(0, maxFraction)
      .replace(/0+$/, "");
    return fractionText ? `${whole}.${fractionText}` : whole.toString();
  } catch {
    return "—";
  }
}

export function formatAssetAmount(
  wei: string | undefined,
  asset: string,
  maxFraction = 4,
): string {
  const amount = formatUnits(wei, assetDecimals(asset), maxFraction);
  return amount === "—" ? amount : `${amount} ${asset}`;
}

export function formatCompact(value: number, lang: "en" | "zh" = "en"): string {
  return new Intl.NumberFormat(lang === "zh" ? "zh-CN" : "en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatInteger(value: number, lang: "en" | "zh" = "en"): string {
  return new Intl.NumberFormat(lang === "zh" ? "zh-CN" : "en-US").format(value);
}

export function formatBps(bps: number, digits = 2): string {
  return `${(bps / 100).toFixed(digits).replace(/\.?0+$/, "")}%`;
}

export function formatUptime(bps: number): string {
  return `${(bps / 100).toFixed(2)}%`;
}

export function formatMaturity(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

export function formatLocalTime(iso: string | undefined, lang: "en" | "zh"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatShortDate(iso: string | undefined, lang: "en" | "zh"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-GB", {
    dateStyle: "medium",
  }).format(date);
}

export function countdown(
  target: string | undefined,
  lang: "en" | "zh",
  nowMs = Date.now(),
): string {
  if (!target) return "—";
  const remaining = new Date(target).getTime() - nowMs;
  if (Number.isNaN(remaining)) return "—";
  if (remaining <= 0) return lang === "zh" ? "已成熟" : "matured";
  const totalMinutes = Math.ceil(remaining / 60000);
  if (totalMinutes < 60) {
    return lang === "zh" ? `${totalMinutes} 分钟` : `${totalMinutes} min`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (lang === "zh") return `${hours} 小时 ${minutes} 分钟`;
  return `${hours}h ${minutes}m`;
}

export function truncateMiddle(value: string, head = 8, tail = 6): string {
  if (value.length <= head + tail + 1) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

export function isEvmAddress(value: string): boolean {
  return /^0x[0-9a-fA-F]{40}$/.test(value.trim());
}

export function poolLabel(pool: Pool): string {
  return `${pool.asset} · ${pool.denomination}`;
}

export function denominationWei(pool: Pool): bigint {
  if (pool.denomination_wei) {
    try {
      return BigInt(pool.denomination_wei);
    } catch {
      /* Fall through to decimal conversion. */
    }
  }
  const decimals = assetDecimals(pool.asset);
  const [whole, fraction = ""] = pool.denomination.split(".");
  const padded = fraction.padEnd(decimals, "0").slice(0, decimals);
  return BigInt(`${whole || "0"}${padded}`);
}

export function protocolFeeWei(pool: Pool): string {
  const fee = (denominationWei(pool) * BigInt(pool.protocol_fee_bps)) / 10_000n;
  return fee.toString();
}


export function isLowSet(pool: Pool): boolean {
  const threshold = pool.min_set_size ?? 100;
  return pool.anonymity_set < threshold;
}

export function poolStatusTone(
  pool: Pool,
): "ok" | "warn" | "danger" | "info" {
  if (pool.status === "paused") return "danger";
  if (!pool.status || pool.status === "low_set" || isLowSet(pool)) return "warn";
  return "ok";
}

export function maturityTimeFromNow(seconds: number): string {
  return new Date(Date.now() + seconds * 1000).toISOString();
}

export function todayUsage(records: Array<{ createdAt: string }>): number {
  const today = new Date().toDateString();
  return records.filter((record) => new Date(record.createdAt).toDateString() === today)
    .length;
}
