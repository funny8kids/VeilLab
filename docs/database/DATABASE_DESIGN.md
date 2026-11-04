# Database Design

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [ERD](ERD.md) · [DATA_LIFECYCLE](DATA_LIFECYCLE.md) · [ADR-005](../adr/ADR-005-DATA-STORAGE.md)

---

## 1. Storage responsibilities

| Store | Role | Source of truth for |
| --- | --- | --- |
| PostgreSQL | Transactional business data | Identity, projects, protocols, experiments, findings, wallets, policies, jobs, audit, outbox |
| ClickHouse | Append-heavy analytical data | Chain blocks, transactions, logs, token transfers, aggregates |
| MinIO | Content-addressed objects | Raw sources, artifacts, datasets, reports, plugins, backups |
| Redis | Ephemeral coordination | Cache, queues, locks, rate limits, revocation sets |

Rules:

- PostgreSQL is the system of record for business state.
- ClickHouse is derived from raw chain data and can be rebuilt.
- MinIO objects are immutable by hash; metadata lives in PostgreSQL.
- Redis is never the only copy of durable state.

---

## 2. Conventions

| Concern | Convention |
| --- | --- |
| Schema names | Singular: `identity`, `system`, `protocol`, `research`, `zk`, `privacy`, `security`, `veilguard`, `agent`, `chain` |
| Table names | Plural snake_case |
| Primary key | `id text` = prefix + ULID, e.g. `exp_01JB8Z...` |
| Foreign key | `<entity>_id`, same type as referenced PK |
| Timestamps | `timestamptz`, UTC, `created_at` / `updated_at` |
| Optimistic locking | `version integer NOT NULL DEFAULT 1` on mutable aggregate roots |
| Soft delete | `deleted_at timestamptz` only where recovery/audit requires it |
| Enums | `text` + `CHECK` constraint, not PostgreSQL enums |
| JSON | `jsonb` for metadata/extensions only; core fields are typed columns |
| EVM address | lowercase `text`, `CHECK (address ~ '^0x[0-9a-f]{40}$')` |
| Hash | lowercase `text`, `CHECK (hash ~ '^0x[0-9a-f]{64}$')` or `sha256:<hex>` for objects |
| Amount | `numeric(78,0)` in wei; never floating point |
| Boolean | `boolean NOT NULL DEFAULT false` |
| Tenant key | `project_id` on every tenant-owned table; `workspace_id` where needed |
| Naming | `pk_`, `fk_`, `uq_`, `ck_`, `ix_` prefixes; max 63 chars |
| Comments | Every table and non-obvious column has a `COMMENT ON` |

### ID prefixes

| Prefix | Entity | Prefix | Entity |
| --- | --- | --- | --- |
| `usr_` | user | `prj_` | project |
| `wsp_` | workspace | `role_` | role |
| `pat_` | personal access token | `cap_` | capability grant |
| `proto_` | protocol | `pver_` | protocol version |
| `study_` | research study | `exp_` | experiment |
| `ever_` | experiment version | `run_` | experiment run |
| `ds_` | dataset | `dsv_` | dataset version |
| `rep_` | report | `rver_` | report version |
| `cir_` | circuit | `cbld_` | circuit build |
| `prf_` | proof run | `fnd_` | security finding |
| `asm_` | assessment | `wlt_` | wallet |
| `pol_` | wallet policy | `txr_` | transaction request |
| `sim_` | simulation | `apr_` | approval |
| `tx_` | transaction | `agt_` | agent |
| `task_` | agent task | `job_` | job |
| `evt_` | event | `inc_` | incident |

---

## 3. PostgreSQL schemas

### 3.1 `identity`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `users` | `id`, `email citext`, `display_name`, `password_hash`, `status`, `totp_secret_ref`, `last_login_at`, `created_at`, `updated_at` | `uq_users_email`; status check |
| `user_identities` | `id`, `user_id`, `provider`, `subject`, `created_at` | `uq_user_identities_provider_subject`; FK user |
| `sessions` | `id`, `user_id`, `token_hash`, `expires_at`, `last_seen_at`, `ip inet`, `user_agent`, `revoked_at` | index `(user_id, expires_at)`; token hash unique |
| `api_tokens` | `id`, `user_id`, `name`, `token_hash`, `scopes text[]`, `project_id`, `expires_at`, `last_used_at`, `revoked_at` | unique token hash; index `(user_id)` |
| `service_accounts` | `id`, `project_id`, `name`, `status`, `created_at` | unique `(project_id, name)` |
| `workspaces` | `id`, `name`, `slug`, `owner_id`, `status`, `created_at` | unique slug |
| `workspace_members` | `workspace_id`, `user_id`, `role`, `created_at` | PK `(workspace_id, user_id)`; role check |
| `projects` | `id`, `workspace_id`, `name`, `slug`, `description`, `status`, `quota jsonb`, `created_at` | unique `(workspace_id, slug)` |
| `project_members` | `project_id`, `user_id`, `role`, `created_at` | PK `(project_id, user_id)`; role check |
| `roles` | `id`, `scope`, `name`, `permissions text[]`, `is_system` | unique `(scope, name)` |
| `capability_grants` | `id`, `subject_type`, `subject_id`, `project_id`, `capabilities text[]`, `resource_scope jsonb`, `issued_by`, `approval_ref`, `jti`, `issued_at`, `expires_at`, `revoked_at` | unique `jti`; index `(subject_type, subject_id, expires_at)` |
| `invitations` | `id`, `workspace_id`, `email`, `role`, `token_hash`, `expires_at`, `accepted_at` | unique pending `(workspace_id, email)` |

Notes:

- `email` uses `citext` or a normalized lower-case column with a unique index.
- `capability_grants` is the durable record; the JWT is a signed projection with a short TTL.
- Sessions and PATs store only hashes, never raw tokens.

### 3.2 `system`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `jobs` | `id`, `project_id`, `type`, `queue`, `status`, `priority`, `payload jsonb`, `payload_ref`, `idempotency_key`, `attempts`, `max_attempts`, `scheduled_at`, `started_at`, `finished_at`, `lease_owner`, `lease_expires_at`, `error_code`, `error_detail`, `trace_id`, `created_by`, `created_at`, `updated_at` | partial unique `(type, idempotency_key)` where not null; index `(queue, status, scheduled_at)` |
| `job_attempts` | `id`, `job_id`, `attempt`, `worker_id`, `status`, `started_at`, `finished_at`, `error_code` | unique `(job_id, attempt)` |
| `outbox` | see [EVENT_ARCHITECTURE](../architecture/EVENT_ARCHITECTURE.md) | index unpublished |
| `outbox_dlq` | `id`, `event_id`, `type`, `payload`, `error`, `attempts`, `moved_at` | index `(moved_at)` |
| `consumer_inbox` | `consumer`, `event_id`, `received_at` | PK `(consumer, event_id)` |
| `audit_log` | `id`, `occurred_at`, `actor_type`, `actor_id`, `on_behalf_of`, `action`, `resource_type`, `resource_id`, `project_id`, `decision`, `reason`, `capability`, `request_id`, `trace_id`, `source_ip`, `metadata jsonb`, `prev_hash`, `hash` | append-only grants; index `(project_id, occurred_at desc)`, `(actor_id, occurred_at desc)` |
| `plugins` | `id`, `plugin_id`, `version`, `type`, `digest`, `manifest jsonb`, `status`, `signature_ref`, `installed_by`, `installed_at`, `enabled_at` | unique `(plugin_id, version, digest)` |
| `plugin_permissions` | `plugin_id`, `version`, `project_id`, `capability`, `granted_by`, `granted_at`, `expires_at` | PK `(plugin_id, version, project_id, capability)` |
| `settings` | `key`, `value jsonb`, `updated_by`, `updated_at` | PK key |
| `feature_flags` | `key`, `enabled`, `description`, `updated_by`, `updated_at` | PK key |
| `secret_refs` | `id`, `provider`, `path`, `purpose`, `owner`, `rotation_due_at`, `created_at` | unique `(provider, path)` |
| `idempotency_keys` | `scope`, `key`, `request_hash`, `response_ref`, `created_at`, `expires_at` | PK `(scope, key)` |
| `event_subscriptions` | `id`, `consumer`, `stream`, `filter jsonb`, `status`, `created_at` | unique `(consumer, stream)` |

### 3.3 `protocol`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `protocols` | `id`, `slug`, `name`, `category`, `website`, `repo_url`, `status`, `summary`, `created_by`, `created_at`, `updated_at` | unique slug; index `(status, updated_at desc)` |
| `protocol_versions` | `id`, `protocol_id`, `version`, `source_commit`, `released_at`, `status`, `metadata jsonb` | unique `(protocol_id, version)` |
| `protocol_profiles` | `id`, `protocol_id`, `version_id`, `architecture`, `cryptography`, `dependencies_summary`, `trust_assumptions`, `admin_permissions`, `upgrade_model`, `content jsonb`, `reviewed_by`, `published_at` | one published profile per version |
| `protocol_sources` | `id`, `protocol_id`, `source_type`, `url`, `fetched_at`, `content_hash`, `raw_ref`, `metadata jsonb` | index `(protocol_id, source_type)` |
| `protocol_dependencies` | `id`, `protocol_id`, `version_id`, `ecosystem`, `package`, `version_range`, `license`, `hash` | unique `(version_id, ecosystem, package)` |
| `protocol_audits` | `id`, `protocol_id`, `version_id`, `auditor`, `report_url`, `published_at`, `scope`, `status` | index `(protocol_id)` |

### 3.4 `research`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `studies` | `id`, `project_id`, `title`, `question`, `status`, `protocol_id`, `owner_id`, `created_at`, `updated_at` | index `(project_id, status, updated_at desc)` |
| `experiments` | `id`, `project_id`, `study_id`, `name`, `type`, `status`, `current_version`, `created_by`, `created_at`, `updated_at` | index `(project_id, status)` |
| `experiment_versions` | `id`, `experiment_id`, `version`, `definition jsonb`, `definition_hash`, `adapter`, `adapter_version`, `created_by`, `created_at` | unique `(experiment_id, version)`; unique `(experiment_id, definition_hash)` |
| `experiment_runs` | `id`, `experiment_id`, `version_id`, `attempt`, `status`, `runner_id`, `job_id`, `started_at`, `finished_at`, `manifest_ref`, `manifest_hash`, `verification_status`, `failure_code`, `trace_id` | unique `(experiment_id, attempt)`; index `(status, started_at)` |
| `run_artifacts` | `id`, `run_id`, `kind`, `path`, `sha256`, `size_bytes`, `media_type`, `created_at` | unique `(run_id, path)` |
| `run_verifications` | `id`, `run_id`, `verifier`, `verifier_version`, `status`, `checks jsonb`, `log_ref`, `verified_at` | index `(run_id, verified_at desc)` |
| `datasets` | `id`, `project_id`, `name`, `description`, `visibility`, `created_by`, `created_at` | unique `(project_id, name)` |
| `dataset_versions` | `id`, `dataset_id`, `version`, `status`, `manifest_ref`, `content_hash`, `size_bytes`, `created_at` | unique `(dataset_id, version)` |
| `dataset_files` | `id`, `dataset_version_id`, `path`, `sha256`, `size_bytes`, `media_type` | unique `(dataset_version_id, path)` |
| `reports` | `id`, `project_id`, `study_id`, `title`, `status`, `current_version`, `created_by`, `created_at` | index `(project_id, status)` |
| `report_versions` | `id`, `report_id`, `version`, `content_ref`, `content_hash`, `status`, `reviewed_by`, `published_at`, `evidence_graph jsonb` | unique `(report_id, version)` |
| `report_evidence` | `id`, `report_version_id`, `evidence_type`, `evidence_id`, `claim_id`, `hash` | index `(report_version_id)` |
| `benchmark_results` | `id`, `run_id`, `workload`, `framework`, `metric`, `value`, `unit`, `sample_stats jsonb`, `environment_fingerprint jsonb`, `comparability`, `created_at` | index `(framework, workload, created_at desc)` |

### 3.5 `zk`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `circuits` | `id`, `project_id`, `name`, `framework`, `source_ref`, `source_hash`, `version`, `status`, `created_at` | unique `(project_id, name, version)` |
| `circuit_builds` | `id`, `circuit_id`, `toolchain`, `toolchain_digest`, `constraints`, `artifact_ref`, `artifact_hash`, `status`, `log_ref`, `created_at` | index `(circuit_id, created_at desc)` |
| `proof_systems` | `id`, `name`, `version`, `adapter`, `config jsonb`, `status` | unique `(name, version)` |
| `proof_runs` | `id`, `run_id`, `circuit_build_id`, `proof_system_id`, `status`, `prove_ms`, `verify_ms`, `proof_size_bytes`, `memory_peak_mb`, `proof_ref`, `public_inputs_ref`, `verified` | index `(run_id)`, `(proof_system_id, created_at)` |

`proof_runs` is an optional specialized projection; the authoritative run and manifest live
in `research.experiment_runs`. A proof run without a linked experiment run is rejected.

### 3.6 `privacy`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `schemes` | `id`, `name`, `version`, `description`, `specification_ref`, `status` | unique `(name, version)` |
| `credentials` | `id`, `project_id`, `scheme_id`, `issuer`, `holder_commitment`, `status`, `issued_at`, `expires_at`, `metadata jsonb` | index `(project_id, status)` |
| `commitments` | `id`, `project_id`, `scheme_id`, `commitment`, `context`, `created_at` | unique `(commitment)` |
| `merkle_trees` | `id`, `project_id`, `name`, `depth`, `root`, `updated_at` | unique `(project_id, name)` |
| `merkle_leaves` | `id`, `tree_id`, `leaf_index`, `commitment`, `created_at` | unique `(tree_id, leaf_index)` |
| `nullifiers` | `id`, `project_id`, `tree_id`, `nullifier_hash`, `context`, `used_at` | unique `(tree_id, nullifier_hash)` |
| `disclosure_requests` | `id`, `project_id`, `credential_id`, `predicate`, `status`, `proof_ref`, `created_at` | index `(project_id, status)` |

Privacy tables store commitments and hashes, not raw personal data. If a prototype needs
PII, it goes to a separate encrypted store with explicit classification and retention.

### 3.7 `security`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `threat_models` | `id`, `protocol_id`, `version_id`, `status`, `content_ref`, `created_by`, `created_at` | index `(protocol_id, status)` |
| `assessments` | `id`, `project_id`, `target_type`, `target_id`, `tool`, `status`, `started_at`, `finished_at`, `summary`, `log_ref` | index `(project_id, status, started_at desc)` |
| `findings` | `id`, `project_id`, `assessment_id`, `protocol_id`, `severity`, `title`, `status`, `component`, `description_ref`, `impact`, `remediation`, `evidence_ref`, `reproduction_ref`, `verified_at`, `published_at` | index `(protocol_id, severity, status)`; index `(project_id, status)` |
| `finding_events` | `id`, `finding_id`, `actor`, `action`, `note`, `created_at` | index `(finding_id, created_at)` |
| `dependency_findings` | `id`, `finding_id`, `ecosystem`, `package`, `version`, `advisory_id` | index `(finding_id)` |

### 3.8 `veilguard`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `wallets` | `id`, `project_id`, `kind`, `address`, `network_scope text[]`, `status`, `key_ref`, `label`, `created_at` | unique `(address)`; kind check in (`research`, `deployment`, `simulation`) |
| `wallet_policies` | `id`, `wallet_id`, `version`, `network_ids text[]`, `allowed_recipients text[]`, `allowed_selectors text[]`, `max_value_wei`, `max_gas`, `daily_tx_limit`, `daily_value_wei`, `require_approval`, `expires_at`, `created_by`, `created_at` | unique `(wallet_id, version)` |
| `transaction_requests` | `id`, `project_id`, `wallet_id`, `network_id`, `to_address`, `value_wei`, `data`, `data_hash`, `nonce`, `gas_limit`, `status`, `simulation_id`, `approval_id`, `policy_id`, `request_hash`, `requested_by_type`, `requested_by_id`, `created_at`, `expires_at` | index `(project_id, status, created_at desc)`; unique `request_hash` |
| `simulations` | `id`, `request_id`, `network_id`, `block_number`, `success`, `gas_used`, `state_diff_ref`, `trace_ref`, `simulation_hash`, `created_at` | index `(request_id)` |
| `approvals` | `id`, `request_id`, `requested_by`, `approved_by`, `status`, `reason`, `expires_at`, `jti`, `created_at` | unique `jti`; index `(request_id)` |
| `transactions` | `id`, `request_id`, `tx_hash`, `network_id`, `block_number`, `status`, `gas_used`, `effective_gas_price`, `confirmed_at`, `error` | unique `tx_hash`; index `(request_id)` |
| `daily_usage` | `wallet_id`, `network_id`, `usage_date date`, `tx_count`, `value_wei` | PK `(wallet_id, network_id, usage_date)` |
| `faucet_events` | `id`, `wallet_id`, `network_id`, `amount_wei`, `source`, `created_at` | index `(wallet_id, created_at desc)` |

### 3.9 `agent`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `agents` | `id`, `project_id`, `role`, `name`, `status`, `model_route_id`, `default_capabilities text[]`, `created_at` | unique `(project_id, name)` |
| `tasks` | `id`, `project_id`, `agent_id`, `type`, `status`, `input_ref`, `output_ref`, `capability_grant_id`, `approval_ref`, `started_at`, `finished_at`, `trace_id` | index `(project_id, status, created_at desc)` |
| `task_steps` | `id`, `task_id`, `seq`, `kind`, `status`, `input_hash`, `output_hash`, `started_at`, `finished_at`, `error_code` | unique `(task_id, seq)` |
| `tool_calls` | `id`, `task_id`, `step_id`, `tool`, `args_hash`, `decision`, `result_hash`, `policy_id`, `duration_ms`, `created_at` | index `(task_id, created_at)` |
| `model_providers` | `id`, `name`, `kind`, `base_url`, `credential_ref`, `status`, `metadata jsonb`, `created_at` | unique name |
| `model_routes` | `id`, `name`, `provider_id`, `model_id`, `capabilities jsonb`, `priority`, `fallback_id`, `status` | unique name |
| `model_usage` | `id`, `task_id`, `provider_id`, `model_id`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `latency_ms`, `created_at` | index `(task_id)`, `(created_at)` |
| `memory_entries` | `id`, `agent_id`, `project_id`, `scope`, `content_ref`, `trust_level`, `created_at`, `expires_at` | index `(agent_id, expires_at)` |

### 3.10 `chain`

| Table | Key columns | Constraints / indexes |
| --- | --- | --- |
| `networks` | `id`, `chain_id`, `kind`, `name`, `native_symbol`, `rpc_ref`, `genesis_hash`, `finality_model`, `confirmations`, `capabilities jsonb`, `enabled`, `verified_at` | partial unique `(chain_id) WHERE kind = 'testnet'`; local networks unique by `(id, genesis_hash)`; kind check in (`local`, `testnet`) |
| `contracts` | `id`, `network_id`, `address`, `label`, `abi_ref`, `verified`, `first_seen_block` | unique `(network_id, address)` |
| `sync_cursors` | `network_id`, `stream`, `last_block`, `last_hash`, `updated_at` | PK `(network_id, stream)` |
| `reorg_events` | `id`, `network_id`, `detected_at`, `from_block`, `to_block`, `orphaned_hashes text[]`, `resolved_at` | index `(network_id, detected_at desc)` |
| `ingestion_health` | `network_id`, `checked_at`, `lag_seconds`, `rpc_latency_ms`, `status` | index `(network_id, checked_at desc)` |

Heavy chain facts are **not** stored in PostgreSQL.

---

## 4. ClickHouse schema

Database: `chain`.

### 4.1 `blocks`

```sql
CREATE TABLE chain.blocks (
    chain_id        UInt32,
    number          UInt64,
    hash            String,
    parent_hash     String,
    timestamp       DateTime64(3, 'UTC'),
    tx_count        UInt32,
    gas_used        UInt64,
    gas_limit       UInt64,
    base_fee        UInt256,
    miner           String,
    is_canonical    UInt8,
    ingested_at     DateTime64(3, 'UTC'),
    raw_ref         String
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (chain_id, number, hash)
TTL timestamp + INTERVAL 12 MONTH;
```

### 4.2 `transactions`

```sql
CREATE TABLE chain.transactions (
    chain_id        UInt32,
    block_number    UInt64,
    block_hash      String,
    hash            String,
    tx_index        UInt32,
    from_address    String,
    to_address      Nullable(String),
    value           UInt256,
    nonce           UInt64,
    gas_limit       UInt64,
    gas_used        UInt64,
    gas_price       UInt256,
    max_fee         UInt256,
    max_priority_fee UInt256,
    status          UInt8,
    input_hash      String,
    input_ref       String,
    is_canonical    UInt8,
    ingested_at     DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ingested_at)
ORDER BY (chain_id, block_number, tx_index, hash)
TTL ingested_at + INTERVAL 12 MONTH;
```

### 4.3 `logs`

```sql
CREATE TABLE chain.logs (
    chain_id        UInt32,
    block_number    UInt64,
    block_hash      String,
    tx_hash         String,
    log_index       UInt32,
    address         String,
    topic0          String,
    topic1          Nullable(String),
    topic2          Nullable(String),
    topic3          Nullable(String),
    data_ref        String,
    is_canonical    UInt8,
    ingested_at     DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ingested_at)
ORDER BY (chain_id, block_number, tx_hash, log_index)
TTL ingested_at + INTERVAL 12 MONTH;
```

### 4.4 Reorg representation

- `is_canonical = 1` for the active chain, `0` for orphaned blocks/transactions/logs.
- A reorg writes replacement rows with `is_canonical = 0` for the old range and `1` for the
  new range, using a later `ingested_at` as the replacement version.
- Queries that need exact canonical state use `FINAL` or aggregate with `argMax(..., ingested_at)`.
- `chain.reorg_events` in PostgreSQL records the range and orphaned hashes for audit.
- Raw block JSON is retained in MinIO so the canonical set can be rebuilt.

### 4.5 Aggregates

Materialized views (examples):

- `chain.daily_tx_counts` — per chain/day transaction count, gas used, unique senders.
- `chain.contract_activity` — calls per contract/day.
- `chain.event_counts` — logs per topic0/day.

Aggregates are derived and rebuildable. They are never used as an audit source.

---

## 5. Tenant isolation and RLS

- Every tenant table has `project_id` (and `workspace_id` where appropriate).
- Repository methods require a `ProjectContext`; a missing context is a programming error.
- PostgreSQL RLS is enabled on `research`, `zk`, `privacy`, `security`, `veilguard`,
  `agent`, `protocol` and `system.jobs`:

```sql
ALTER TABLE research.experiments ENABLE ROW LEVEL SECURITY;

CREATE POLICY project_isolation ON research.experiments
    USING (project_id = current_setting('app.project_id', true))
    WITH CHECK (project_id = current_setting('app.project_id', true));
```

- The API sets `SET LOCAL app.project_id = '<prj_...>'` at transaction start.
- Background jobs set the project context from the job record.
- The migration role has `BYPASSRLS`; application roles do not.
- Cross-project admin operations use an explicit, audited admin function, not a bypass role.
- CI runs cross-tenant tests for every repository method.

RLS is defense in depth, not a replacement for authorization.

---

## 6. Audit log

- Append-only: application roles have `INSERT`/`SELECT`; no `UPDATE`/`DELETE`.
- `hash = sha256(prev_hash || canonical_json(record))`; `prev_hash` references the previous
  record in the same partition/stream.
- A daily anchor job writes the latest hash and count to MinIO with object lock.
- Partition by month (`audit_log_YYYY_MM`) for retention and vacuum.
- Sensitive fields are hashed or omitted; never store secrets.
- Audit queries are restricted to `auditor` and `workspace_owner`.

---

## 7. Jobs, outbox and idempotency

- `system.jobs` is the durable source of job state; Celery messages are hints.
- A job claim uses `FOR UPDATE SKIP LOCKED` and a lease with `lease_expires_at`.
- A worker that loses its lease must not commit results; results are idempotent by run ID.
- `idempotency_keys` stores `(scope, key)` with the request hash and response reference;
  a repeated key with a different hash returns `409`.
- Outbox insertion is in the same transaction as the state change.
- Job payloads above 64 KB are stored in MinIO and referenced by `payload_ref`.

---

## 8. Index strategy

| Pattern | Index |
| --- | --- |
| Tenant list pages | `(project_id, created_at desc)` or `(project_id, status, updated_at desc)` |
| Queue polling | `(queue, status, scheduled_at)` partial `WHERE status IN ('queued','retry')` |
| Outbox relay | partial `WHERE published_at IS NULL` on `available_at` |
| Expiring tokens | `(expires_at)` partial `WHERE revoked_at IS NULL` |
| Chain cursors | PK `(network_id, stream)` |
| Audit search | `(project_id, occurred_at desc)`, `(actor_id, occurred_at desc)` |
| Finding triage | `(protocol_id, severity, status)` |
| Wallet usage | PK `(wallet_id, network_id, usage_date)` |

Rules:

- Do not index every column. Measure with `pg_stat_statements`.
- Partial indexes are preferred for status-filtered queues.
- Avoid `SELECT *` in hot paths; use explicit projections.
- Use keyset pagination (`(created_at, id) < ...`), not large offsets.

---

## 9. Migrations

- Alembic, one head, linear history; no branching migrations.
- Naming convention enforced by `MetaData(naming_convention=...)`.
- Expand/contract for zero-downtime:
  1. add nullable column / new table,
  2. dual-write and backfill in batches,
  3. switch reads,
  4. drop old column in a later release.
- Destructive migration requires a backup, a restore test and an ADR.
- Lock timeout is set (e.g. 5 s); long backfills run as jobs, not in migration.
- Role/grant changes are migrations and reviewed by security.
- CI applies migrations to an empty database and to a snapshot of the previous release.

---

## 10. Backup and recovery

| Store | Method | Frequency | Retention |
| --- | --- | --- | --- |
| PostgreSQL | `pg_dump -Fc` + WAL archive (v1.0) | Nightly + continuous | 30 daily, 12 weekly, 12 monthly |
| ClickHouse | `BACKUP DATABASE chain` to MinIO | Nightly | 14 daily, 8 weekly |
| MinIO | Versioning + offsite copy | Continuous | Per object lifecycle |
| Redis | AOF for queue durability | Continuous | 7 days |

Restore test is a release gate (G8). Backups are encrypted; keys are stored separately.

---

## 11. Capacity estimates (v0.1)

| Data | Estimate |
| --- | --- |
| Users/projects | < 100 |
| Protocols | 50–200 |
| Experiments/runs | 10k rows/year |
| Proof/benchmark results | 100k rows/year |
| Chain blocks (6 testnets) | ~50M rows/year in ClickHouse (compressed) |
| Chain transactions | ~500M rows/year worst case; retention 12 months |
| Audit | 1M rows/year |
| Artifacts | 1–5 TB with retention |

If ClickHouse transaction volume exceeds the single-node budget, reduce retention for
non-essential testnets or sample logs; do not drop raw blocks before the retention policy.

---

## 12. Integrity invariants

1. An experiment run always references an immutable experiment version.
2. A completed run always has a manifest hash and at least one verifier record.
3. A published report always references reviewed evidence.
4. A transaction request always has a simulation and policy decision before signing.
5. A signature always references an approval (or an explicit policy that does not require
   one) and a one-time request hash.
6. A finding marked `verified` has reproduction evidence.
7. An event in the outbox has a unique ID and a schema version.
8. A capability grant has an expiry and an issuer.
9. No table stores a raw secret or private key.
10. Every tenant row has a project ID that passes RLS.
