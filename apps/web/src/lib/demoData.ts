import type {
  CompliancePolicy,
  DepositIntentResponse,
  Pool,
  Relayer,
  WithdrawalQuoteResponse,
} from "../types";

export const DEMO_POOLS: Pool[] = [
  {
    id: "pool_eth_01",
    chain_id: 11155111,
    asset: "ETH",
    denomination: "0.1",
    denomination_wei: "100000000000000000",
    maturity_seconds: 1800,
    protocol_fee_bps: 24,
    anonymity_set: 842,
    liquidity_wei: "1820000000000000000000000",
    status: "active",
    min_set_size: 100,
  },
  {
    id: "pool_eth_1",
    chain_id: 11155111,
    asset: "ETH",
    denomination: "1.0",
    denomination_wei: "1000000000000000000",
    maturity_seconds: 7200,
    protocol_fee_bps: 22,
    anonymity_set: 316,
    liquidity_wei: "1940000000000000000000000",
    status: "active",
    min_set_size: 100,
  },
  {
    id: "pool_eth_10",
    chain_id: 11155111,
    asset: "ETH",
    denomination: "10",
    denomination_wei: "10000000000000000000",
    maturity_seconds: 21600,
    protocol_fee_bps: 20,
    anonymity_set: 64,
    liquidity_wei: "440000000000000000000000",
    status: "active",
    min_set_size: 100,
  },
  {
    id: "pool_usdc_100",
    chain_id: 11155111,
    asset: "USDC",
    denomination: "100",
    denomination_wei: "100000000",
    maturity_seconds: 1800,
    protocol_fee_bps: 28,
    anonymity_set: 124,
    liquidity_wei: "380000000000",
    status: "active",
    min_set_size: 100,
  },
  {
    id: "pool_usdc_1000",
    chain_id: 11155111,
    asset: "USDC",
    denomination: "1000",
    denomination_wei: "1000000000",
    maturity_seconds: 7200,
    protocol_fee_bps: 25,
    anonymity_set: 48,
    liquidity_wei: "210000000000",
    status: "active",
    min_set_size: 100,
  },
  {
    id: "pool_btc_001",
    chain_id: 11155111,
    asset: "tBTC",
    denomination: "0.01",
    denomination_wei: "1000000",
    maturity_seconds: 7200,
    protocol_fee_bps: 30,
    anonymity_set: 22,
    liquidity_wei: "3000000",
    status: "active",
    min_set_size: 100,
  },
];

export const DEMO_RELAYERS: Relayer[] = [
  {
    id: "rel_01",
    name: "Relay-01",
    fee_bps: 24,
    uptime_bps: 9998,
    latency_ms: 38,
    supported_pools: [
      "pool_eth_01",
      "pool_eth_1",
      "pool_eth_10",
      "pool_usdc_100",
      "pool_usdc_1000",
    ],
    status: "online",
  },
  {
    id: "rel_02",
    name: "Relay-02",
    fee_bps: 30,
    uptime_bps: 9995,
    latency_ms: 21,
    supported_pools: ["pool_eth_01", "pool_eth_1", "pool_eth_10"],
    status: "online",
  },
  {
    id: "rel_03",
    name: "Relay-03",
    fee_bps: 35,
    uptime_bps: 9989,
    latency_ms: 64,
    supported_pools: DEMO_POOLS.map((pool) => pool.id),
    status: "online",
  },
  {
    id: "rel_04",
    name: "Relay-04",
    fee_bps: 28,
    uptime_bps: 9972,
    latency_ms: 92,
    supported_pools: ["pool_usdc_100", "pool_usdc_1000", "pool_btc_001"],
    status: "online",
  },
  {
    id: "rel_05",
    name: "Relay-05",
    fee_bps: 32,
    uptime_bps: 9980,
    latency_ms: 110,
    supported_pools: ["pool_btc_001", "pool_usdc_100"],
    status: "online",
  },
  {
    id: "rel_06",
    name: "Relay-06",
    fee_bps: 26,
    uptime_bps: 9965,
    latency_ms: 144,
    supported_pools: ["pool_eth_01", "pool_eth_1", "pool_eth_10"],
    status: "degraded",
  },
];

export const DEMO_POLICY: CompliancePolicy = {
  policy_version: 7,
  sanctions_list_version: "2026-10-30",
  updated_at: "2026-10-31T09:00:00Z",
  daily_deposit_limit: "10000",
  daily_withdrawal_limit: "5000",
  per_transaction_limit: "10000",
  review_sla_hours: 24,
  allowed_jurisdictions: ["US", "GB", "DE", "SG", "JP", "CA"],
  blocked_jurisdictions: ["IR", "KP", "SY", "CU"],
  screening_sources: ["OFAC SDN", "EU Consolidated", "UN", "Chain analytics"],
};

export interface DemoDecision {
  id: string;
  kind: "deposit" | "withdrawal";
  label: string;
  decision: "allow" | "review" | "block";
  reasonCode?: string;
  at: string;
}

export const DEMO_DECISIONS: DemoDecision[] = [
  {
    id: "cmp_demo_01",
    kind: "deposit",
    label: "ETH · 0.1",
    decision: "allow",
    reasonCode: "SCREENING_PASS",
    at: "2026-11-02T10:02:00Z",
  },
  {
    id: "cmp_demo_02",
    kind: "withdrawal",
    label: "ETH · 1.0",
    decision: "allow",
    reasonCode: "SCREENING_PASS",
    at: "2026-11-02T09:46:00Z",
  },
  {
    id: "cmp_demo_03",
    kind: "withdrawal",
    label: "USDC · 100",
    decision: "block",
    reasonCode: "SANCTIONS_MATCH",
    at: "2026-11-02T09:41:00Z",
  },
  {
    id: "cmp_demo_04",
    kind: "deposit",
    label: "ETH · 10",
    decision: "review",
    reasonCode: "VELOCITY_REVIEW",
    at: "2026-11-01T18:22:00Z",
  },
];

export const DEMO_METRICS = {
  volume_24h: "182K",
  deposits_24h: 42,
  withdrawals_24h: 31,
  avg_fee_bps: 28,
  integrity: "demo",
};

export const DEMO_DEPOSIT_CONTRACT =
  "0x7a3f9c2d8e1b4a6f0c5d9e2b7a1f3c8d6e4b0a29";

export const DEMO_DEPOSITOR_ADDRESS =
  "0x4d2a8f1c7e9b3a6d0f5c8e2b7a1d4f6c9e3b0a28";

export const DEMO_ROOT =
  "0x79a4e5d034f1bb7b0aa10f0c7b8d9c9df8b3e38cb3f4e2a84c9c9f0d6e2b7a11";

export function createDemoDepositIntent(
  pool: Pool,
  commitment: string,
): DepositIntentResponse {
  const suffix = commitment.slice(2, 10) || "demo";
  return {
    intent_id: `dep_demo_${suffix}`,
    compliance: {
      decision: "allow",
      check_id: `cmp_demo_${suffix}`,
      expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
    },
    deposit_contract: DEMO_DEPOSIT_CONTRACT,
    denomination_wei: pool.denomination_wei,
    protocol_fee_bps: pool.protocol_fee_bps,
    expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
  };
}

export function createDemoQuote(
  pool: Pool,
  relayer: Relayer,
  recipientReceivesWei: string,
  relayerFeeWei: string,
  gasEstimateWei: string,
): WithdrawalQuoteResponse {
  return {
    quote_id: `q_demo_${pool.id.slice(-4)}_${Date.now().toString(36)}`,
    relayer_id: relayer.id,
    relayer_fee_bps: relayer.fee_bps,
    relayer_fee_wei: relayerFeeWei,
    gas_estimate_wei: gasEstimateWei,
    recipient_receives_wei: recipientReceivesWei,
    expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
    compliance: {
      decision: "allow",
      check_id: `cmp_demo_${Date.now().toString(36)}`,
      expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
    },
  };
}
