# Entity Relationship Diagrams

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [DATABASE_DESIGN](DATABASE_DESIGN.md)

> Diagrams show principal relationships, not every column. Foreign keys may be logical
> (ID reference) across module boundaries to preserve ownership; those are marked in prose.

---

## 1. Identity and tenancy

```mermaid
erDiagram
    users ||--o{ user_identities : "has"
    users ||--o{ sessions : "opens"
    users ||--o{ api_tokens : "owns"
    users ||--o{ workspace_members : "joins"
    users ||--o{ project_members : "joins"
    users ||--o{ workspaces : "owns"

    workspaces ||--o{ workspace_members : "includes"
    workspaces ||--o{ projects : "contains"

    projects ||--o{ project_members : "includes"
    projects ||--o{ capability_grants : "scopes"
    projects ||--o{ service_accounts : "owns"

    roles ||--o{ workspace_members : "defines"
    roles ||--o{ project_members : "defines"

    users {
        text id PK
        citext email UK
        text display_name
        text password_hash
        text status
        timestamptz created_at
    }
    workspaces {
        text id PK
        text name
        text slug UK
        text owner_id FK
        text status
    }
    projects {
        text id PK
        text workspace_id FK
        text name
        text slug
        text status
        jsonb quota
    }
    capability_grants {
        text id PK
        text subject_type
        text subject_id
        text project_id FK
        text_array capabilities
        jsonb resource_scope
        text jti UK
        timestamptz expires_at
        timestamptz revoked_at
    }
```

Notes:

- `capability_grants.subject_id` references a user, service account, agent or task depending
  on `subject_type`. It is a logical reference, not a single-table FK.
- Workspace membership and project membership are separate. A project role never grants
  workspace administration.
- `api_tokens.project_id` optionally narrows a PAT to one project.

---

## 2. Protocol, research and cryptography

```mermaid
erDiagram
    protocols ||--o{ protocol_versions : "has"
    protocols ||--o{ protocol_profiles : "profiles"
    protocol_versions ||--o{ protocol_profiles : "versions"
    protocols ||--o{ protocol_sources : "cites"
    protocols ||--o{ protocol_dependencies : "depends_on"
    protocols ||--o{ protocol_audits : "audited_by"

    projects ||--o{ studies : "contains"
    protocols ||--o{ studies : "investigated_by"

    studies ||--o{ experiments : "plans"
    experiments ||--o{ experiment_versions : "versions"
    experiments ||--o{ experiment_runs : "runs"
    experiment_versions ||--o{ experiment_runs : "executes"

    experiment_runs ||--o{ run_artifacts : "produces"
    experiment_runs ||--o{ run_verifications : "verified_by"
    experiment_runs ||--o{ benchmark_results : "measures"
    experiment_runs ||--o| proof_runs : "specializes"

    projects ||--o{ datasets : "owns"
    datasets ||--o{ dataset_versions : "versions"
    dataset_versions ||--o{ dataset_files : "contains"

    studies ||--o{ reports : "reports"
    reports ||--o{ report_versions : "versions"
    report_versions ||--o{ report_evidence : "cites"

    projects ||--o{ circuits : "owns"
    circuits ||--o{ circuit_builds : "builds"
    circuit_builds ||--o{ proof_runs : "proves"
    proof_systems ||--o{ proof_runs : "uses"

    protocols {
        text id PK
        text slug UK
        text name
        text category
        text status
    }
    studies {
        text id PK
        text project_id FK
        text protocol_id FK
        text title
        text status
    }
    experiments {
        text id PK
        text project_id FK
        text study_id FK
        text type
        text status
        int current_version
    }
    experiment_versions {
        text id PK
        text experiment_id FK
        int version
        jsonb definition
        text definition_hash UK
    }
    experiment_runs {
        text id PK
        text experiment_id FK
        text version_id FK
        int attempt
        text status
        text manifest_hash
        text verification_status
    }
    run_artifacts {
        text id PK
        text run_id FK
        text path
        text sha256
        bigint size_bytes
    }
    benchmark_results {
        text id PK
        text run_id FK
        text framework
        text workload
        text metric
        numeric value
        text comparability
    }
    reports {
        text id PK
        text project_id FK
        text study_id FK
        text status
    }
    report_versions {
        text id PK
        text report_id FK
        int version
        text content_ref
        text status
    }
```

Notes:

- `experiment_versions` is immutable. Editing an experiment creates a new version.
- `experiment_runs.version_id` pins the exact definition used.
- `run_artifacts.path` is a content-addressed MinIO key; `sha256` is mandatory.
- `proof_runs.run_id` is unique when present; the experiment run is authoritative.
- `report_evidence.evidence_id` is a logical reference to a manifest, finding, protocol
  version or dataset; it is not a single FK.

---

## 3. Chain and VeilGuard

```mermaid
erDiagram
    networks ||--o{ contracts : "hosts"
    networks ||--o{ sync_cursors : "tracks"
    networks ||--o{ reorg_events : "experiences"
    networks ||--o{ ingestion_health : "reports"

    projects ||--o{ wallets : "owns"
    wallets ||--o{ wallet_policies : "governed_by"
    wallets ||--o{ transaction_requests : "requests"
    networks ||--o{ transaction_requests : "targets"

    transaction_requests ||--o| simulations : "simulated_by"
    transaction_requests ||--o| approvals : "approved_by"
    transaction_requests ||--o| transactions : "broadcast_as"

    wallets ||--o{ daily_usage : "consumes"
    networks ||--o{ daily_usage : "counts"

    networks {
        text id PK
        int chain_id UK
        text kind
        text name
        text genesis_hash
        text finality_model
        boolean enabled
    }
    wallets {
        text id PK
        text project_id FK
        text kind
        text address UK
        text_array network_scope
        text key_ref
        text status
    }
    wallet_policies {
        text id PK
        text wallet_id FK
        int version
        text_array network_ids
        numeric max_value_wei
        int daily_tx_limit
        numeric daily_value_wei
        boolean require_approval
    }
    transaction_requests {
        text id PK
        text project_id FK
        text wallet_id FK
        text network_id FK
        text to_address
        numeric value_wei
        text data_hash
        bigint nonce
        text status
        text request_hash UK
    }
    simulations {
        text id PK
        text request_id FK
        boolean success
        bigint gas_used
        text simulation_hash
    }
    approvals {
        text id PK
        text request_id FK
        text approved_by
        text status
        text jti UK
        timestamptz expires_at
    }
    transactions {
        text id PK
        text request_id FK
        text tx_hash UK
        text status
        bigint block_number
    }
    daily_usage {
        text wallet_id PK
        text network_id PK
        date usage_date PK
        int tx_count
        numeric value_wei
    }
```

Notes:

- `wallets.key_ref` points to a key identifier inside the signer; it is not key material.
- One transaction request has at most one successful simulation and one approval; retries
  create new requests rather than mutating history.
- `daily_usage` is updated in the same transaction that reserves a signing slot.
- Chain facts (blocks/transactions/logs) are in ClickHouse, not in this diagram.

---

## 4. Security, agents and privacy products

```mermaid
erDiagram
    projects ||--o{ assessments : "owns"
    protocols ||--o{ assessments : "targets"
    assessments ||--o{ findings : "produces"
    protocols ||--o{ findings : "affects"
    findings ||--o{ finding_events : "history"

    projects ||--o{ agents : "owns"
    agents ||--o{ tasks : "executes"
    tasks ||--o{ task_steps : "steps"
    task_steps ||--o{ tool_calls : "invokes"
    tasks ||--o{ model_usage : "consumes"
    model_providers ||--o{ model_routes : "serves"
    model_routes ||--o{ model_usage : "meters"

    projects ||--o{ credentials : "owns"
    schemes ||--o{ credentials : "typed_by"
    credentials ||--o{ disclosure_requests : "proves"
    projects ||--o{ merkle_trees : "owns"
    merkle_trees ||--o{ merkle_leaves : "contains"
    merkle_trees ||--o{ nullifiers : "consumes"

    assessments {
        text id PK
        text project_id FK
        text target_type
        text target_id
        text tool
        text status
    }
    findings {
        text id PK
        text project_id FK
        text assessment_id FK
        text protocol_id FK
        text severity
        text status
        text evidence_ref
        text reproduction_ref
    }
    agents {
        text id PK
        text project_id FK
        text role
        text status
    }
    tasks {
        text id PK
        text project_id FK
        text agent_id FK
        text type
        text status
        text capability_grant_id
    }
    tool_calls {
        text id PK
        text task_id FK
        text tool
        text args_hash
        text decision
        text result_hash
    }
    model_usage {
        text id PK
        text task_id FK
        text provider_id
        int prompt_tokens
        int completion_tokens
        numeric cost_usd
    }
    credentials {
        text id PK
        text project_id FK
        text scheme_id FK
        text holder_commitment
        text status
    }
    merkle_trees {
        text id PK
        text project_id FK
        int depth
        text root
    }
    nullifiers {
        text id PK
        text tree_id FK
        text nullifier_hash UK
    }
```

Notes:

- `findings.protocol_id` links to the protocol registry; `assessment_id` links to the tool
  run that produced it.
- `tasks.capability_grant_id` is the durable grant; the runtime token is not stored.
- `tool_calls.args_hash` and `result_hash` allow audit without storing potentially sensitive
  payloads.
- Privacy tables store commitments and nullifiers, not raw attributes.

---

## 5. Logical references across module boundaries

| Reference | From | To | Rule |
| --- | --- | --- | --- |
| `project_id` | most tenant tables | `identity.projects` | FK allowed; RLS key |
| `protocol_id` | research/security | `protocol.protocols` | FK allowed; read-only for consumers |
| `run_id` | zk/research | `research.experiment_runs` | FK allowed |
| `job_id` | research/veilguard | `system.jobs` | logical; job may be pruned |
| `capability_grant_id` | agent.tasks | identity.capability_grants | FK allowed |
| `evidence_id` | research.report_evidence | manifest/finding/dataset | logical, typed |
| `key_ref` | veilguard.wallets | signer keystore | opaque reference, never a key |
| `wallet_id` | veilguard.* | veilguard.wallets | FK |
| `network_id` | chain/veilguard | chain.networks | FK |
| `plugin_id` | system.plugin_permissions | system.plugins | FK |

Logical references are validated by the owning module's public API and integrity jobs, not
by cross-schema joins in application queries.
