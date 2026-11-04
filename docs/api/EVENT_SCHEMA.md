# Event Schema

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [EVENT_ARCHITECTURE](../architecture/EVENT_ARCHITECTURE.md) · [API_CONVENTIONS](API_CONVENTIONS.md)

---

## 1. Envelope

VeilLab events are CloudEvents 1.0-compatible JSON objects.

```json
{
  "specversion": "1.0",
  "id": "evt_01JB8Z4K2M9Q7R3T5V6W8X0Y1Z",
  "type": "dev.veillab.research.experiment.completed.v1",
  "source": "veillab.research",
  "subject": "projects/prj_01J.../experiments/exp_01J.../runs/run_01J...",
  "time": "2026-11-02T10:15:30Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.veillab.dev/events/research/experiment.completed/v1.json",
  "projectid": "prj_01J...",
  "traceid": "4bf92f3577b34da6a3ce929d0e0e4736",
  "correlationid": "job_01J...",
  "causationid": "evt_01J...",
  "data": {
    "experiment_id": "exp_01J...",
    "run_id": "run_01J...",
    "status": "completed",
    "verification_status": "verified",
    "manifest_hash": "sha256:..."
  }
}
```

| Field | Required | Rules |
| --- | --- | --- |
| `specversion` | Yes | Always `"1.0"` |
| `id` | Yes | `evt_` + ULID, globally unique |
| `type` | Yes | Reverse-DNS + domain + aggregate + action + `.vN` |
| `source` | Yes | Producing service, e.g. `veillab.research` |
| `subject` | Yes | Resource path, no query string |
| `time` | Yes | UTC, millisecond precision |
| `datacontenttype` | Yes | `application/json` |
| `dataschema` | Yes | Versioned schema URI |
| `projectid` | Conditional | Required for tenant-scoped events |
| `traceid` | Yes | W3C trace ID |
| `correlationid` | No | Workflow/job correlation |
| `causationid` | No | Event that caused this event |
| `data` | Yes | Event-specific payload |

Extension attributes are lowercase, ≤ 20 characters, and must not collide with CloudEvents
reserved names.

---

## 2. Type naming

```text
dev.veillab.<domain>.<aggregate>.<action>.v<major>
```

- `domain`: `identity`, `protocol`, `research`, `crypto`, `chain`, `security`, `privacy`,
  `veilguard`, `agent`, `plugin`, `job`, `system`.
- `aggregate`: singular snake_case (`experiment`, `experiment_run`, `finding`).
- `action`: past tense (`created`, `completed`, `denied`).
- `vN`: schema major version.

Examples:

```text
dev.veillab.research.experiment.completed.v1
dev.veillab.research.experiment_run.verification_completed.v1
dev.veillab.chain.reorg.detected.v1
dev.veillab.veilguard.transaction.confirmed.v1
dev.veillab.agent.tool.denied.v1
```

The short name used in UI and docs is `experiment.completed`; the full type is authoritative
on the wire.

---

## 3. Payload rules

1. `data` MUST be a JSON object, not an array or scalar.
2. IDs are strings with prefixes; no embedded objects when an ID suffices.
3. Timestamps are ISO 8601 UTC.
4. Amounts are strings for wei.
5. Hashes are lowercase, prefixed (`sha256:` or `0x`).
6. No secrets, tokens, keys, raw prompts, full PII or signed transactions.
7. Large payloads use a reference (`*_ref`, `*_id`), not inline data.
8. Maximum event size is 256 KB; larger data must be stored in MinIO.
9. Unknown fields are allowed for forward compatibility; consumers MUST ignore them.
10. Enumerations are lowercase strings; new values may be added within a major version.

---

## 4. Event catalog

### Identity and platform

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.identity.user.created.v1` | control | `user_id`, `email_hash` | audit, web |
| `dev.veillab.identity.project.created.v1` | control | `project_id`, `workspace_id`, `owner_id` | audit, all modules |
| `dev.veillab.identity.project.archived.v1` | control | `project_id`, `reason` | all modules, lifecycle |
| `dev.veillab.identity.capability.issued.v1` | control | `grant_id`, `subject_type`, `subject_id`, `caps`, `expires_at` | audit, agent |
| `dev.veillab.identity.capability.revoked.v1` | control | `grant_id`, `jti`, `reason` | audit, agent, tool gateway |
| `dev.veillab.identity.policy.denied.v1` | control | `actor_type`, `actor_id`, `action`, `resource`, `reason` | audit, security |

### Protocol

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.protocol.protocol.discovered.v1` | observatory | `protocol_id`, `source_type`, `source_url`, `draft_id` | research, web |
| `dev.veillab.protocol.protocol.updated.v1` | observatory | `protocol_id`, `changed_fields`, `source_hash` | research, web |
| `dev.veillab.protocol.version.published.v1` | observatory | `protocol_id`, `version_id`, `source_commit` | research, security |

### Research

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.research.study.created.v1` | research | `study_id`, `protocol_id`, `owner_id` | web, agents |
| `dev.veillab.research.experiment.created.v1` | research | `experiment_id`, `study_id`, `type` | web, agents |
| `dev.veillab.research.experiment.validated.v1` | research | `experiment_id`, `version`, `adapter` | web |
| `dev.veillab.research.experiment.queued.v1` | research | `experiment_id`, `run_id`, `job_id` | runner, web |
| `dev.veillab.research.experiment.started.v1` | research | `experiment_id`, `run_id`, `runner_id` | web, audit |
| `dev.veillab.research.experiment.completed.v1` | research | `experiment_id`, `run_id`, `manifest_hash`, `verification_status` | web, reports, agents |
| `dev.veillab.research.experiment.failed.v1` | research | `experiment_id`, `run_id`, `failure_code` | web, reports |
| `dev.veillab.research.experiment.cancelled.v1` | research | `experiment_id`, `run_id`, `reason` | web, runner |
| `dev.veillab.research.experiment_run.verification_completed.v1` | research | `run_id`, `verifier`, `status`, `checks` | web, reports |
| `dev.veillab.research.dataset.created.v1` | research | `dataset_id`, `project_id` | web |
| `dev.veillab.research.dataset.version.published.v1` | research | `dataset_id`, `version_id`, `content_hash` | experiments, web |
| `dev.veillab.research.report.published.v1` | research | `report_id`, `version`, `content_hash` | web, notifications |
| `dev.veillab.research.benchmark.completed.v1` | research | `run_id`, `framework`, `workload`, `metrics_summary`, `comparability` | benchmark center, web |

### Cryptography

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.crypto.circuit.built.v1` | crypto | `circuit_id`, `build_id`, `constraints`, `artifact_hash` | research, web |
| `dev.veillab.crypto.proof.generated.v1` | crypto | `run_id`, `proof_system`, `proof_size_bytes`, `prove_ms` | research, web |
| `dev.veillab.crypto.proof.verified.v1` | crypto | `run_id`, `verified`, `verify_ms` | research, web |

### Chain

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.chain.block.ingested.v1` | chain | `network_id`, `number`, `hash`, `parent_hash` | veilguard, web |
| `dev.veillab.chain.reorg.detected.v1` | chain | `network_id`, `from_block`, `to_block`, `orphaned_hashes` | veilguard, research, web |
| `dev.veillab.chain.sync.degraded.v1` | chain | `network_id`, `lag_seconds`, `reason` | ops, web |
| `dev.veillab.chain.sync.recovered.v1` | chain | `network_id`, `lag_seconds` | ops, web |

### Security

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.security.assessment.completed.v1` | security | `assessment_id`, `tool`, `findings_count` | web, reports |
| `dev.veillab.security.finding.created.v1` | security | `finding_id`, `severity`, `protocol_id`, `status` | web, reports |
| `dev.veillab.security.finding.verified.v1` | security | `finding_id`, `verifier`, `evidence_hash` | reports, web |
| `dev.veillab.security.finding.published.v1` | security | `finding_id`, `disclosure_ref` | web |

### Privacy

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.privacy.credential.issued.v1` | privacy | `credential_id`, `scheme_id`, `commitment` | privacy, web |
| `dev.veillab.privacy.proof.requested.v1` | privacy | `proof_id`, `scheme_id`, `tree_id` | crypto, web |
| `dev.veillab.privacy.proof.completed.v1` | privacy | `proof_id`, `verified`, `proof_ref` | privacy, web |

### VeilGuard

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.veilguard.simulation.completed.v1` | veilguard | `simulation_id`, `request_id`, `success`, `gas_used`, `simulation_hash` | web, approvals |
| `dev.veillab.veilguard.transaction.requested.v1` | veilguard | `request_id`, `wallet_id`, `network_id`, `request_hash` | approvals, web |
| `dev.veillab.veilguard.transaction.approved.v1` | veilguard | `request_id`, `approval_id`, `approved_by`, `expires_at` | gateway, web |
| `dev.veillab.veilguard.transaction.denied.v1` | veilguard | `request_id`, `reason`, `policy_id` | web, audit |
| `dev.veillab.veilguard.transaction.submitted.v1` | veilguard | `request_id`, `tx_hash`, `network_id` | reconciliation, web |
| `dev.veillab.veilguard.transaction.confirmed.v1` | veilguard | `request_id`, `tx_hash`, `block_number`, `status` | web, research |
| `dev.veillab.veilguard.transaction.failed.v1` | veilguard | `request_id`, `tx_hash`, `reason` | web, reconciliation |
| `dev.veillab.veilguard.signer.refused.v1` | testnet-gateway | `request_id`, `reason`, `policy_hash` | security, audit |

### Agent and model

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.agent.task.created.v1` | agent | `task_id`, `agent_id`, `caps`, `expires_at` | web, audit |
| `dev.veillab.agent.task.started.v1` | agent | `task_id`, `agent_id` | web |
| `dev.veillab.agent.task.completed.v1` | agent | `task_id`, `status`, `output_ref`, `tokens` | web, reports |
| `dev.veillab.agent.task.failed.v1` | agent | `task_id`, `failure_code` | web, reports |
| `dev.veillab.agent.tool.denied.v1` | control | `task_id`, `tool`, `capability`, `reason` | security, audit |
| `dev.veillab.agent.model.request.completed.v1` | model gateway | `task_id`, `provider_id`, `tokens`, `cost_usd` | cost, web |
| `dev.veillab.agent.model.provider.degraded.v1` | model gateway | `provider_id`, `reason`, `latency_ms` | ops, routing |

### Plugin, job, system

| Full type | Producer | Key data | Consumers |
| --- | --- | --- | --- |
| `dev.veillab.plugin.plugin.installed.v1` | control | `plugin_id`, `version`, `digest` | web, audit |
| `dev.veillab.plugin.plugin.enabled.v1` | control | `plugin_id`, `version`, `project_id`, `caps` | runner, web |
| `dev.veillab.plugin.plugin.quarantined.v1` | control | `plugin_id`, `version`, `reason` | ops, web |
| `dev.veillab.job.job.queued.v1` | control | `job_id`, `type`, `queue`, `project_id` | ops |
| `dev.veillab.job.job.started.v1` | control | `job_id`, `worker_id` | ops |
| `dev.veillab.job.job.completed.v1` | control | `job_id`, `duration_ms` | ops, originating module |
| `dev.veillab.job.job.failed.v1` | control | `job_id`, `error_code`, `attempts` | ops, originating module |
| `dev.veillab.system.backup.completed.v1` | ops | `backup_id`, `store`, `size_bytes`, `duration_ms` | audit, ops |
| `dev.veillab.system.backup.failed.v1` | ops | `backup_id`, `store`, `error` | ops |
| `dev.veillab.system.audit.anchor.created.v1` | audit | `anchor_id`, `latest_hash`, `count` | audit, ops |

---

## 5. Payload examples

### `experiment.completed`

```json
{
  "experiment_id": "exp_01J...",
  "run_id": "run_01J...",
  "version": 2,
  "attempt": 1,
  "status": "completed",
  "verification_status": "verified",
  "manifest_hash": "sha256:9f2c...",
  "metrics": {
    "compile_ms": 8421,
    "prove_ms": 12030,
    "verify_ms": 41,
    "proof_size_bytes": 1280
  },
  "artifacts": 6,
  "failure_code": null
}
```

### `chain.reorg.detected`

```json
{
  "network_id": "eth-sepolia",
  "chain_id": 11155111,
  "from_block": 6123450,
  "to_block": 6123453,
  "orphaned_hashes": ["0xabc...", "0xdef..."],
  "common_ancestor": "0x123...",
  "detected_at": "2026-11-02T10:15:30Z"
}
```

### `veilguard.transaction.confirmed`

```json
{
  "request_id": "txr_01J...",
  "tx_hash": "0x...",
  "network_id": "eth-sepolia",
  "chain_id": 11155111,
  "block_number": 6123456,
  "status": "confirmed",
  "gas_used": "21000",
  "effective_gas_price": "1000000000",
  "confirmed_at": "2026-11-02T10:16:00Z"
}
```

### `agent.tool.denied`

```json
{
  "task_id": "task_01J...",
  "agent_id": "agt_01J...",
  "tool": "testnet.request",
  "capability": "testnet.execute",
  "resource": "wlt_01J...",
  "reason": "capability missing",
  "policy_id": "pol_01J..."
}
```

### `security.finding.created`

```json
{
  "finding_id": "fnd_01J...",
  "assessment_id": "asm_01J...",
  "protocol_id": "proto_01J...",
  "severity": "high",
  "title": "Nullifier replay across trees",
  "status": "draft",
  "evidence_hash": "sha256:...",
  "reproduction_ref": "run_01J..."
}
```

---

## 6. WebSocket exposure

Only a subset is forwarded to browser clients:

| Forwarded | Rationale |
| --- | --- |
| `research.*`, `crypto.*`, `chain.*`, `security.finding.*`, `veilguard.transaction.*` | UI progress and status |
| `job.*` | Admin views only |
| `agent.task.*`, `agent.tool.denied` | Task progress; denial may be redacted |
| `model.*` | Aggregate cost only, not prompts |

Never forwarded: `identity.capability.*` (contains capability metadata), raw `model.request.completed`
usage per prompt, internal `system.*` events, audit payloads.

The server redacts fields marked `internal_only` and filters by project membership.

---

## 7. Schema management

- JSON Schemas live in `packages/event_schema/<domain>/<aggregate>.<action>/vN.json`.
- `packages/contracts` generates Pydantic models from the schemas.
- Producers validate before insert into the outbox; consumers validate on receipt.
- CI checks:
  - schema is valid JSON Schema 2020-12,
  - required fields are present in examples,
  - no secret-like keys (`password`, `secret`, `private_key`, `token`, `api_key`),
  - additive diff against `main`,
  - every event type is registered in the catalog.
- Adding a required field is breaking; use `.v2`.
- Removing a field is breaking; deprecate for one major version with dual-publish.

---

## 8. Ordering and idempotency

- `id` is the idempotency key.
- Consumers record `(consumer, event_id)` in `system.consumer_inbox`.
- Ordering is per `aggregate_type + aggregate_id` on the same stream.
- Consumers MUST tolerate duplicates, out-of-order delivery across aggregates and replays.
- State transitions are validated against the aggregate's current state; a `completed` event
  before `started` is rejected or deferred, not applied blindly.

---

## 9. Retention and replay

| Store | Retention |
| --- | --- |
| Redis Streams | 7 days |
| Outbox (published) | 7 days |
| Outbox archive (MinIO) | 30 days |
| Audit log | 2 years (see data lifecycle) |

Replay procedure is defined in
[EVENT_ARCHITECTURE.md](../architecture/EVENT_ARCHITECTURE.md#9-replay). Replays are audited
and idempotent.

---

## 10. Security

- Events are internal; producers are authenticated services, not users.
- Redis ACLs restrict streams per service.
- Payloads are validated and size-limited.
- No secrets, tokens, keys, raw prompts or signed transactions.
- WebSocket tickets are single-use and project-scoped.
- Event consumers re-check authorization before acting on tenant data.
- An event is a notification, not an authorization grant. A `transaction.approved` event
  does not replace the approval record checked by the gateway.
