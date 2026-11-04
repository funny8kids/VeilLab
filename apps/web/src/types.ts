export type DataMode = "live" | "partial" | "demo";

/** Chain mode reported by the API health endpoint. */
export type ApiMode = "mock" | "local";

export type PoolStatus = "active" | "paused" | "low_set" | string;

export interface Pool {
  id: string;
  chain_id: number;
  asset: string;
  denomination: string;
  denomination_wei?: string;
  maturity_seconds: number;
  protocol_fee_bps: number;
  anonymity_set: number;
  liquidity_wei?: string;
  status: PoolStatus;
  min_set_size?: number;
}

export type RelayerStatus = "online" | "degraded" | "offline" | string;

export interface Relayer {
  id: string;
  name: string;
  fee_bps: number;
  uptime_bps: number;
  latency_ms: number;
  supported_pools: string[];
  status: RelayerStatus;
}

export type ComplianceDecision = "allow" | "review" | "block";

export interface ComplianceResult {
  decision: ComplianceDecision;
  check_id?: string;
  expires_at?: string;
  reasons?: string[];
  risk_score?: number;
}

export interface CompliancePolicy {
  policy_version: string | number;
  sanctions_list_version?: string;
  updated_at?: string;
  daily_deposit_limit?: string;
  daily_withdrawal_limit?: string;
  per_transaction_limit?: string;
  review_sla_hours?: number;
  allowed_jurisdictions?: string[];
  blocked_jurisdictions?: string[];
  screening_sources?: string[];
}

export interface IndexerHealth {
  status?: string;
  state?: string;
  lag?: number;
  lag_blocks?: number;
  blocks_behind?: number;
  lag_seconds?: number;
  last_indexed_block?: number;
}

export interface HealthStatus {
  status?: string;
  mode?: string;
  mock?: boolean;
  chain_id?: number;
  version?: string;
  services?: {
    chain?: string;
    [service: string]: unknown;
  };
  indexer?: IndexerHealth;
  indexer_status?: string;
  indexer_lag_blocks?: number;
  indexer_lag_seconds?: number;
}

export interface DepositIntentResponse {
  intent_id: string;
  compliance?: ComplianceResult;
  deposit_contract?: string;
  denomination_wei?: string;
  protocol_fee_bps?: number;
  expires_at?: string;
}

export interface MockDepositRequest {
  intent_id: string;
  commitment: string;
}

export interface MockDepositResponse {
  tx_hash?: string;
  status?: string;
  block_number?: number;
  leaf_index?: number;
  commitment?: string;
}

export interface LocalDepositRequest {
  intent_id: string;
  commitment: string;
}

export interface LocalDepositResponse extends MockDepositResponse {
  intent_id?: string;
  local_chain?: string;
  contract_address?: string;
  denomination_wei?: string;
}

export interface LocalDepositInstruction {
  contractAddress?: string;
  denominationWei?: string;
  calldata?: string;
  instruction?: string;
}

export interface WithdrawalQuoteResponse {
  quote_id: string;
  relayer_id: string;
  relayer_fee_bps: number;
  relayer_fee_wei: string;
  gas_estimate_wei: string;
  recipient_receives_wei: string;
  expires_at: string;
  compliance?: ComplianceResult;
  submission_available?: boolean;
  submission_endpoint?: string;
  proof_encoding?: string;
  verifier_kind?: string;
  local_chain?: boolean;
  warning?: string;
  mock?: boolean;
}

/**
 * Public Merkle-path response from
 * GET /api/v1/pools/{pool_id}/path/{commitment}. The API proxies only these
 * public fields; no note or witness material is returned.
 */
export interface ProofPathResponse {
  chain_id?: number;
  contract_address?: string;
  /** Canonical bytes32 pool id as 0x hex. */
  pool_id?: string;
  pool_key?: string;
  commitment: string;
  leaf_index: number;
  leaf_count?: number;
  tree_depth: number;
  root: string;
  root_block_number?: number;
  root_block_hash?: string;
  path_elements: string[];
  path_indices: number[];
  canonical_only?: boolean;
  mock_verifier?: boolean;
}

/**
 * Local Anvil Groth16 withdrawal request. This is the full whitelist: the
 * browser sends only the proof and public signals, never the note or witness.
 */
export interface LocalWithdrawalRequest {
  quote_id: string;
  /** 0x-prefixed 256-byte ABI Groth16 proof. */
  proof: string;
  /** 0x-prefixed 32-byte Merkle root. */
  root: string;
  /** 0x-prefixed 32-byte Poseidon nullifier. */
  nullifier: string;
  recipient: string;
  relayer_fee_wei: string;
}

export interface LocalWithdrawalResponse {
  withdrawal_id?: string;
  pool_id?: string;
  status: string;
  tx_hash?: string;
  block_number?: number;
  block_hash?: string;
  nullifier?: string;
  recipient?: string;
  fee_wei?: string;
  local_chain?: string;
  chain_source?: string;
  confirmations?: number;
  finality?: string;
  verifier_kind?: string;
  proof_encoding?: string;
  mock?: boolean;
  warning?: string;
}

export interface WithdrawalSubmitResponse {
  withdrawal_id: string;
  status: string;
  tx_hash: string;
  relayer_id: string;
}

export interface PoolRootResponse {
  root: string;
  block_number?: number;
  block_hash?: string;
}

export interface PublicSignals {
  root: string;
  nullifier_hash: string;
  recipient: string;
  fee_wei: string;
}

export interface DepositIntentRequest {
  pool_id: string;
  depositor_address: string;
  amount: string;
  commitment: string;
}

export interface WithdrawalQuoteRequest {
  pool_id: string;
  recipient_address: string;
  relayer_id: string;
}

export interface WithdrawalSubmitRequest {
  pool_id: string;
  quote_id: string;
  proof: string;
  public_signals: PublicSignals;
  recipient_address: string;
}

export type LocalActivityStatus =
  | "submitted"
  | "pending"
  | "confirmed"
  | "matured"
  | "failed";

export interface LocalActivityRecord {
  id: string;
  kind: "deposit" | "withdrawal";
  poolId: string;
  asset: string;
  denomination: string;
  status: LocalActivityStatus;
  noteId: string;
  createdAt: string;
  matureAt?: string;
  commitment?: string;
  recipient?: string;
  relayerName?: string;
  txHash?: string;
  compliance?: ComplianceDecision;
  demo: boolean;
}

export interface VaultRecordMeta {
  id: string;
  poolId: string;
  asset: string;
  denomination: string;
  createdAt: string;
  backedUp: boolean;
  spent: boolean;
}

export interface VaultSummary {
  total: number;
  backedUp: number;
  unbacked: number;
}

export interface BackupEnvelope {
  type: "veilpool.note.backup";
  version: 1;
  createdAt: string;
  noteId: string;
  poolId: string;
  cipher: {
    kdf: "PBKDF2-SHA256";
    iterations: number;
    salt: string;
    iv: string;
    ciphertext: string;
  };
}

export interface VaultBackupEnvelope {
  type: "veilpool.vault.backup";
  version: 1;
  createdAt: string;
  notes: BackupEnvelope[];
}
