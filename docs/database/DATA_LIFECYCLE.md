# Data Lifecycle

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [DATABASE_DESIGN](DATABASE_DESIGN.md) · [SECURITY_ARCHITECTURE](../security/SECURITY_ARCHITECTURE.md)

---

## 1. Principles

1. **Minimize.** Collect only what a research workflow needs.
2. **Classify.** Every dataset has a class and an owner.
3. **Retain deliberately.** Default retention is finite and documented.
4. **Immutable evidence.** Published artifacts and audit records are protected from silent
   modification.
5. **Delete completely.** Deleting a project removes its data, objects, caches and derived
   indexes within the stated window.
6. **Prove it.** Lifecycle jobs emit evidence and are tested.

---

## 2. Classification

| Class | Definition | Examples | Handling |
| --- | --- | --- | --- |
| `public` | Intended for publication | Published reports, public protocol metadata | Integrity + review |
| `internal` | Default for platform data | Experiment definitions, chain data, agent tasks | Auth + project scope |
| `confidential` | Restricted business/research data | Embargoed findings, unpublished reports, datasets under NDA | Need-to-know, audit, encryption |
| `restricted` | Secrets and key material | Wallet keys, API keys, DB credentials, session secrets | Isolation, no logging, encryption |

Rules:

- Every project has a default classification (`internal` unless set).
- Datasets and reports inherit the higher of project and item classification.
- `restricted` data MUST NOT be stored in PostgreSQL plaintext, MinIO unencrypted or any
  agent context.
- Classification changes require an audit record and may trigger re-encryption or access
  review.

---

## 3. Retention schedule

| Data | Class | Active retention | Archive | Deletion |
| --- | --- | --- | --- | --- |
| User account | internal | Life of account | — | 30 days after deletion request |
| Sessions / PATs | restricted | Until expiry | — | Purged 30 days after expiry/revocation |
| Workspace/project metadata | internal | Life of project | — | 30 days after project deletion |
| Protocol profiles/sources | public/internal | Indefinite | — | On request/correction; source snapshots retained for provenance |
| Experiment definitions | internal | Life of project | — | With project |
| Raw run artifacts | internal/confidential | 2 years | — | After 2 years unless pinned |
| Reproducibility bundles (manifest, hashes, verifier output) | internal | 5 years | Cold storage after 2 years | After 5 years with review |
| Datasets | per dataset | Life of dataset | — | On deletion request + 30 days |
| Published reports | public | Indefinite | — | Correction creates a new version; old version retained |
| Draft reports | confidential | 1 year after last edit | — | Auto-purge |
| Security findings | confidential | 5 years after closure | — | After 5 years with review |
| Threat models | confidential | Life of protocol + 2 years | — | Review |
| Chain raw blocks | public | 90 days hot | 1 year cold | After 1 year |
| ClickHouse chain facts | public | 12 months | Aggregates indefinite | TTL |
| Audit log | confidential | 2 years | 7 years cold | After 7 years |
| Job records | internal | 90 days after completion | — | Purge |
| Outbox events | internal | 7 days published; 30 days archive | — | Purge |
| Application logs | internal | 30 days dev / 90 days prod | — | Purge |
| Agent task traces | internal | 90 days | — | Purge |
| Agent prompts/responses | internal | Off by default; ≤ 30 days if enabled | — | Purge |
| Model usage/cost | internal | 2 years | — | Aggregate after 2 years |
| Testnet transaction records | internal | 2 years | — | Purge |
| Wallet key material | restricted | Life of wallet | — | Cryptographic erasure on retirement |
| Backups | mixed | 30 daily / 12 weekly / 12 monthly | Offsite | Per schedule |

Retention starts from the event described (completion, closure, deletion), not from creation,
unless stated otherwise.

---

## 4. Deletion

### 4.1 Project deletion

A project deletion is a two-step, audited operation:

1. **Request** — owner confirms the project name and states a reason; project becomes
   `pending_deletion` and read-only.
2. **Grace period** — 30 days, cancellable by an owner.
3. **Purge job** — deletes in order:
   - active jobs cancelled and tokens revoked,
   - MinIO objects under project prefixes (artifacts, datasets, reports, raw sources),
   - ClickHouse rows filtered by project-owned contract addresses (where applicable),
   - PostgreSQL rows in dependency order,
   - read models, caches and search indexes,
   - encryption keys for project-specific confidential data.
4. **Certificate of deletion** — a signed record with counts and hashes, stored in audit.

Shared public chain data is not deleted; it is not project-owned.

### 4.2 User deletion

- Sessions and PATs revoked immediately.
- Membership removed; owned projects must be transferred or deleted first.
- Personal profile data deleted after 30 days.
- Audit records referencing the user are retained (legally required) with the actor ID
  pseudonymized where policy allows.
- Authored reports remain with the project; authorship may be anonymized on request.

### 4.3 Dataset deletion

- A dataset version can be deleted only if no active experiment references it.
- Referenced versions are tombstoned; the object is retained until references are archived.
- A deleted dataset version is removed from listings immediately and purged within 30 days.

### 4.4 Artifact deletion

- Raw artifacts are deletable after retention unless pinned by a published report or a
  reproducibility bundle.
- A pinned artifact cannot be deleted without a retention exception approved by the owner
  and recorded in audit.
- Deletion removes the object and its metadata, but the manifest hash remains for provenance.

### 4.5 Audit deletion

Audit records are not deleted by users. Expiry follows the retention schedule and is
performed by a dedicated maintenance role with a signed deletion report.

---

## 5. Legal hold and exceptions

- A legal hold suspends deletion for named projects, users or records.
- Holds are recorded with scope, reason, owner and review date.
- The purge job checks holds before any destructive action and fails closed on ambiguity.
- Retention exceptions require an owner, justification and expiry; they are reviewed at
  each release gate.

---

## 6. Archival

| Data | Archive trigger | Format | Location |
| --- | --- | --- | --- |
| Reproducibility bundles | 2 years after run | tar.zst + manifest + SHA256SUMS | MinIO cold bucket |
| Chain raw blocks | 90 days | gzip JSON | MinIO cold bucket |
| Audit | 2 years | monthly Parquet + hash anchor | MinIO WORM |
| Published reports | On supersession | signed bundle | MinIO WORM |
| Backups | Per schedule | encrypted dump | Offsite |

Archives are immutable, encrypted and restore-tested. An archive without an index and
restore procedure is not compliant.

---

## 7. Backups and deletion

- Backups follow their own retention; deleting a record does not immediately delete it from
  existing backups.
- Backup retention MUST be disclosed in the privacy notice.
- Restoring a backup after a deletion request requires re-applying the deletion tombstone
  list before serving data.
- Tombstones are retained for the maximum backup retention window plus 30 days.

---

## 8. Logging and redaction

- Logs are structured JSON with a `data_class` field.
- Secrets, tokens, keys, full prompts and raw PII are redacted at the emitter.
- Request bodies are not logged by default; hashes and sizes are logged instead.
- Error messages never include stack traces to clients; server logs may include a sanitized
  stack with request ID.
- Log retention is enforced by the logging backend, not by manual cleanup.

---

## 9. AI and third-party data

- Data sent to an external model provider is limited to the minimum needed and classified
  `internal` or lower by default.
- `confidential` data requires an approved provider with no-training/no-retention terms and
  a documented exception.
- Provider requests are logged as metadata (tokens, model, latency, cost), not raw content,
  unless explicitly enabled for debugging with a short TTL.
- Agent memory is task-scoped and expires; it is not a system of record.
- Model output is labeled machine-generated until reviewed.

---

## 10. Data residency

- v0.1 is self-hosted by the operator; residency is determined by the host location.
- Backups and AI provider calls may cross borders; this is documented before deployment.
- A future multi-tenant offering requires a residency policy and per-region storage.

---

## 11. Lifecycle automation

| Job | Frequency | Action | Evidence |
| --- | --- | --- | --- |
| `lifecycle.expire_sessions` | Hourly | Delete expired sessions/tokens | Count |
| `lifecycle.purge_jobs` | Daily | Delete old job records | Count |
| `lifecycle.purge_outbox` | Daily | Delete published outbox > 7 days | Count |
| `lifecycle.purge_logs` | Daily | Backend retention | Count |
| `lifecycle.expire_agent_memory` | Hourly | Delete expired memory | Count |
| `lifecycle.purge_drafts` | Weekly | Delete stale drafts | Count |
| `lifecycle.archive_runs` | Monthly | Move old artifacts to cold storage | Manifest |
| `lifecycle.purge_projects` | Daily | Execute pending deletions | Certificate |
| `lifecycle.verify_audit_chain` | Daily | Verify hash chain + anchor | Report |
| `lifecycle.backup` | Nightly | Dump/backup | Restore test quarterly |

Every job is idempotent, logs counts, and fails closed if a hold or reference is detected.

---

## 12. Testing and evidence

- Deletion tests create a project with artifacts, datasets, reports and a run, then execute
  purge and verify no residuals in PostgreSQL, MinIO, ClickHouse and caches.
- Restore tests verify that deleted data does not reappear without tombstone re-application.
- Retention tests use a clock abstraction, not sleeps.
- Evidence is attached to G8 and to the release checklist.
- A quarterly data inventory compares actual stores to the retention schedule.

---

## 13. Roles and responsibilities

| Role | Responsibility |
| --- | --- |
| Data owner (project owner) | Classification, retention choice, deletion request |
| Platform operator | Lifecycle jobs, backups, restore, holds |
| Security owner | Restricted data handling, incident response |
| Auditor | Audit retention and integrity verification |

---

## 14. Open items

- Legal review of retention periods per jurisdiction.
- Whether published reports can ever be deleted (currently: corrected, not deleted).
- Provider-specific data processing agreements for AI.
- Encryption key management for project-specific confidential data.
- Cross-border backup policy for team deployments.
