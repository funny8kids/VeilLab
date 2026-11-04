# Module Boundaries

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [ADR-001](../adr/ADR-001-MODULAR-MONOLITH.md) · [DATABASE_DESIGN](../database/DATABASE_DESIGN.md)

---

## 1. Purpose

VeilLab is a modular monolith at the business layer and a set of isolated deployables at
the execution layer. This document defines:

- which module owns which data,
- which dependencies are allowed,
- how modules communicate,
- how the rules are enforced in CI.

Without these rules, a monolith becomes a distributed set of hidden couplings with a
single deployment. The boundary rules are therefore normative.

---

## 2. Module catalog

| Module | Responsibility | Owns | Publishes | Consumes |
| --- | --- | --- | --- | --- |
| `control_center.identity` | Users, sessions, PATs, OIDC, service identities | `identity.users`, `identity.sessions`, `identity.api_tokens`, `identity.service_accounts` | `identity.user.created` | — |
| `control_center.projects` | Workspaces, projects, membership, quotas | `identity.workspaces`, `identity.projects`, `identity.memberships` | `project.created`, `project.archived` | `identity.user.created` |
| `control_center.iam` | RBAC, capability grants, policy decisions | `identity.roles`, `identity.capability_grants` | `capability.issued`, `capability.revoked`, `policy.denied` | `project.created` |
| `control_center.plugins` | Plugin registry, manifests, installation | `system.plugins`, `system.plugin_permissions` | `plugin.installed`, `plugin.enabled`, `plugin.quarantined` | — |
| `control_center.jobs` | Durable jobs, leases, retries, cancellation | `system.jobs`, `system.job_attempts` | `job.queued`, `job.started`, `job.completed`, `job.failed` | — |
| `control_center.events` | Outbox, relay, subscriptions, replay | `system.outbox`, `system.event_subscriptions` | (transport) | all events |
| `control_center.audit` | Append-only audit log and query | `system.audit_log` | — | privileged action events |
| `observatory` | Discovery, source ingestion, protocol registry | `protocol.*` | `protocol.discovered`, `protocol.updated`, `protocol.version.published` | `project.created` |
| `research_engine` | Studies, experiments, runs, datasets, reports, benchmarks | `research.*` | `research.created`, `experiment.*`, `dataset.*`, `report.published`, `benchmark.completed` | `protocol.*`, `capability.*` |
| `cryptography` | Interfaces, adapters, proof/FHE/MPC orchestration | `zk.*` | `proof.generated`, `proof.verified`, `circuit.built` | `experiment.queued` |
| `chain_intelligence` | Network registry, collection, normalization, reorg, state verification | `chain.*` (PG), ClickHouse `chain` | `chain.block.ingested`, `chain.reorg.detected`, `chain.sync.degraded` | — |
| `security_center` | Assessments, threat models, findings, reproduction | `security.*` | `security.assessment.completed`, `security.finding.created`, `security.finding.verified` | `experiment.*`, `protocol.*` |
| `privacy_products` | Identity schemes, credentials, commitments, nullifiers | `privacy.*` | `privacy.credential.issued`, `privacy.proof.requested` | `zk.*`, `chain.*` |
| `veilguard` | Wallets, policies, simulation, approvals, reconciliation | `veilguard.*` | `testnet.simulation.completed`, `testnet.transaction.requested`, `testnet.transaction.confirmed`, `testnet.policy.denied` | `chain.*`, `capability.*` |
| `model_gateway` | Providers, routing, metering, health | `agent.model_providers`, `agent.model_usage` | `model.request.completed`, `model.provider.degraded` | — |
| `agents` | Agent definitions, tasks, steps, tool calls | `agent.agents`, `agent.tasks`, `agent.task_steps`, `agent.tool_calls` | `agent.task.*`, `agent.tool.denied` | `capability.*`, `model.*` |
| `platform` | DB, cache, object storage, messaging, config, secrets, observability | No business tables | — | — |

**Ownership rule:** the module named above is the only writer of its tables. Other modules
may read through a public query API or a published read model, never by SQL join.

---

## 3. Dependency matrix

Rows depend on columns. `✅` = direct public API allowed; `E` = asynchronous event only;
`R` = read-only query API allowed; `—` = forbidden.

| ↓ depends on → | control | observatory | research | crypto | chain | security | privacy | veilguard | model | agents |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| control | — | — | — | — | — | — | — | — | — | — |
| observatory | ✅ | — | — | — | — | — | — | — | — | — |
| research | ✅ | R | — | ✅ | R | — | — | — | — | — |
| crypto | ✅ | — | ✅ | — | — | — | — | — | — | — |
| chain | ✅ | — | — | — | — | — | — | — | — | — |
| security | ✅ | R | R | — | — | — | — | — | — | — |
| privacy | ✅ | — | R | ✅ | R | — | — | — | — | — |
| veilguard | ✅ | — | — | — | R | — | — | — | — | — |
| model_gateway | ✅ | — | — | — | — | — | — | — | — | — |
| agents | ✅ | R | R | — | — | — | — | — | ✅ | — |

Notes:

- `research` depends on `cryptography` only through a **job port**; it does not import
  proof-system internals. The adapter registry is resolved at runtime.
- `crypto` may read experiment definitions but MUST NOT mutate research state. It reports
  results as events/artifacts, and only the research engine changes experiment status.
- `veilguard` reads chain state; it never writes chain tables and never talks to signer.
  The signer is reached only by `testnet-gateway`, which is outside the business modules.
- `agents` never import `veilguard`. Agent testnet actions go through the API tool gateway
  and the normal policy/approval path.
- `privacy` consumes cryptography through public interfaces; product code does not shell
  out to proof toolchains directly.

---

## 4. Interface pattern

Every core module exposes a narrow public facade and keeps implementation private:

```text
core/<module>/
├── api.py             # public functions/classes; the only cross-module import surface
├── contracts.py       # command/query DTOs owned by this module
├── events.py          # published event payload models
├── errors.py          # domain errors mapped to API problem+json
├── models.py          # SQLAlchemy models (private)
├── repository.py      # persistence (private)
├── service.py         # domain logic (private)
└── internal/          # adapters, helpers, policies (private)
```

Rules:

1. `api.py` MUST expose intent-level operations, not raw CRUD or ORM objects.
2. Cross-module DTOs MUST be immutable Pydantic models or frozen dataclasses.
3. A module MUST NOT return its ORM model across a boundary.
4. A module MUST NOT accept a SQLAlchemy `Session` from another module.
5. Public API functions MUST be idempotent where retries are possible, or require an
   idempotency key.
6. Public API functions MUST enforce authorization themselves; callers are not trusted to
   have done it.
7. Public API functions MUST emit audit records for state changes.

Example facade:

```python
# core/research_engine/api.py
async def create_experiment(cmd: CreateExperiment, actor: Actor) -> ExperimentRef: ...
async def start_run(experiment_id: str, actor: Actor, idempotency_key: str) -> RunRef: ...
async def record_verification(run_id: str, verdict: VerificationVerdict) -> None: ...
```

The facade delegates to private services; it never leaks the ORM.

---

## 5. Communication rules

### Synchronous

Allowed only when the caller needs an immediate decision or read:

- authorization and capability checks,
- reading registry metadata needed to build a job,
- querying chain state for a simulation,
- validating a dataset reference.

Synchronous calls MUST have a timeout, a bounded retry policy and a defined failure mode.
They MUST NOT form chains longer than three modules.

### Asynchronous

Use events for side effects and state propagation:

- experiment completion → report generation,
- protocol update → re-index,
- finding created → notification,
- transaction confirmed → reconciliation,
- model provider degraded → routing change.

Events are delivered at-least-once. Consumers are idempotent by event `id`. Ordering is
guaranteed only per aggregate key (see [EVENT_ARCHITECTURE.md](EVENT_ARCHITECTURE.md)).

### Transactions

- One module owns one database transaction.
- State change + outbox insert MUST be in the same transaction.
- Cross-module workflows use a saga/process manager in the orchestrating module, with
  explicit compensation states. Do not use distributed transactions.

---

## 6. Forbidden patterns

| Forbidden | Why | Correct alternative |
| --- | --- | --- |
| Cross-schema SQL joins in application code | Couples migrations and ownership | Public query API or read model |
| Importing another module's `models.py` | Leaks persistence | DTO from `api.py` |
| Shared mutable table between modules | Ambiguous ownership | Single owner + events |
| Direct RPC calls from research/security modules | Bypasses chain policy | Chain Intelligence query API |
| Direct signer calls from agents or VeilGuard module | Bypasses policy | Testnet gateway only |
| Reading secret values in an agent or plugin | Exfiltration | Secret references + broker |
| Importing `cryptography.adapters.*` in business modules | Framework lock-in | Adapter registry / job port |
| Module-level global mutable state | Test isolation, concurrency | Explicit dependencies |
| Circular module imports | Build and reasoning failure | Event or invert dependency |

---

## 7. Enforcement

### 7.1 Import contracts

Use `import-linter` (Python) with contracts:

- `core` is layered: `platform` ← domain modules ← `apps`.
- No module imports another module except through `core.<module>.api`.
- `apps.api` may import module facades; `apps.worker` may import job handlers.
- `adapters` may import `packages` and `core.platform`, never `apps`.
- `cryptography.interfaces` must not import concrete adapters.

### 7.2 Database grants

Separate PostgreSQL roles per deployable:

| Role | Grants |
| --- | --- |
| `veillab_api` | SELECT/INSERT/UPDATE on business schemas; no DDL |
| `veillab_worker` | Limited to job/research/audit tables |
| `veillab_runner` | No database access; presigned object URLs only |
| `veillab_collector` | INSERT on `chain` tables; SELECT on registry |
| `veillab_gateway` | SELECT on `chain` metadata, `veilguard` policy views |
| `veillab_signer` | No database access |
| `veillab_agent` | No database access |
| `veillab_model_gateway` | INSERT/SELECT on model usage tables |

CI MUST verify grants against the migration-generated schema.

### 7.3 Architecture tests

- Import graph snapshot test (`tests/architecture/test_imports.py`).
- Forbidden-dependency test for `agents → veilguard`, `research → adapters`,
  `security → signer`.
- Schema ownership test: parse SQLAlchemy metadata, assert table prefixes against module
  ownership manifest.
- Cross-tenant test: create two projects, attempt access with wrong project context,
  expect `404`/`403` and an audit denial.

### 7.4 Code review checklist

- Does the change write outside the module's schema?
- Does it call another module's internals?
- Does it introduce a new external network destination? If yes, update network policy.
- Does it add a secret to config, logs or agent context? If yes, reject.
- Does it add a long-running operation without a job and trace ID?
- Does it change a state machine without updating the spec and tests?

---

## 8. Data ownership and read models

Some cross-plane views are performance-sensitive. They are implemented as **read models**,
not shared tables:

| Read model | Owner | Refresh | Consumers |
| --- | --- | --- | --- |
| `rm_protocol_summary` | observatory | event-driven | research, web |
| `rm_experiment_status` | research | event-driven | web, agents |
| `rm_chain_head` | chain | collector update | veilguard, web |
| `rm_finding_summary` | security | event-driven | web, reports |
| `rm_wallet_usage` | veilguard | transaction events | policy engine, web |

A read model is owned by exactly one module, may be rebuilt from events/source tables, and
MUST be marked stale/rebuildable in its metadata. It is never the source of truth.

---

## 9. Change management

Adding a module requires:

1. ADR if it changes a trust boundary, datastore or deployment unit.
2. Row in the module catalog with owned schema and events.
3. Update to the dependency matrix.
4. Import-linter contract and at least one architecture test.
5. Threat model update if it processes untrusted input or holds credentials.

Renaming or moving a table requires an expand/contract migration and a compatibility
window. Never break a published event schema within a major version.
