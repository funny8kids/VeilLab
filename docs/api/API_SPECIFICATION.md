# API Specification Baseline

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [API_CONVENTIONS](API_CONVENTIONS.md) · [EVENT_SCHEMA](EVENT_SCHEMA.md)

> This is the endpoint baseline. The generated OpenAPI document is the machine-readable
> contract. Field-level schemas will be added in `packages/contracts` during P1.

---

## 1. Conventions

- All public endpoints are under `/api/v1` and require authentication unless marked public.
- All tenant resources require a `project_id` either in the path or body.
- Lists support `limit`, `cursor`, `sort` and explicit filters.
- Mutations that create jobs return `202` with `job_id`/`run_id`.
- `Idempotency-Key` is required where noted.
- Errors use `application/problem+json`.

Legend: **Auth** = `session`, `pat`, `capability`, `public`, `mTLS`; **Scope** = required PAT
scope when using a PAT.

---

## 2. Authentication

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/auth/login` | public | Local login; returns session cookie + CSRF token |
| `POST` | `/auth/logout` | session | Revoke session |
| `GET` | `/auth/me` | any | Current actor, memberships, permissions |
| `POST` | `/auth/password/change` | session | Change password (requires current password) |
| `POST` | `/auth/totp/enable` | session | Begin TOTP enrollment |
| `POST` | `/auth/totp/verify` | session | Confirm TOTP code |
| `POST` | `/auth/tokens` | session | Create PAT (returns secret once) |
| `GET` | `/auth/tokens` | session | List PAT metadata |
| `DELETE` | `/auth/tokens/{token_id}` | session | Revoke PAT |
| `POST` | `/auth/ws-ticket` | session/PAT | Issue single-use WebSocket ticket |

Login response:

```json
{
  "user": {"id": "usr_...", "email": "researcher@example.org", "display_name": "R"},
  "csrf_token": "...",
  "expires_at": "2026-11-02T21:30:00Z"
}
```

---

## 3. Workspaces and projects

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/workspaces` | session/PAT | `read` | List workspaces |
| `POST` | `/workspaces` | session | — | Create workspace |
| `GET` | `/workspaces/{id}` | member | `read` | Workspace detail |
| `PATCH` | `/workspaces/{id}` | owner/admin | — | Update workspace |
| `GET` | `/workspaces/{id}/members` | member | `read` | List members |
| `POST` | `/workspaces/{id}/members` | owner/admin | — | Invite member |
| `DELETE` | `/workspaces/{id}/members/{user_id}` | owner/admin | — | Remove member |
| `GET` | `/projects` | member | `read` | List accessible projects |
| `POST` | `/projects` | workspace admin | — | Create project |
| `GET` | `/projects/{id}` | member | `read` | Project detail |
| `PATCH` | `/projects/{id}` | project admin | — | Update project |
| `DELETE` | `/projects/{id}` | owner | — | Request project deletion |
| `GET` | `/projects/{id}/members` | member | `read` | List project members |
| `POST` | `/projects/{id}/members` | project admin | — | Add member |
| `GET` | `/projects/{id}/usage` | member | `read` | Quotas and consumption |

Project deletion is a two-step flow: request (`DELETE`) then confirm
(`POST /projects/{id}/confirm-deletion`) after re-authentication.

---

## 4. Protocol Observatory

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/protocols` | member | `read` | Search/list protocols |
| `POST` | `/protocols` | member | `write` | Create a manual protocol draft |
| `GET` | `/protocols/{id}` | member | `read` | Profile + versions + sources |
| `PATCH` | `/protocols/{id}` | member | `write` | Edit draft metadata |
| `POST` | `/protocols/{id}/refresh` | member | `write` | Queue a discovery refresh |
| `GET` | `/protocols/{id}/versions` | member | `read` | Version history |
| `POST` | `/protocols/{id}/versions/{version_id}/publish` | reviewer | `write` | Publish a reviewed version |
| `GET` | `/protocols/{id}/sources` | member | `read` | Source snapshots and hashes |
| `GET` | `/protocols/{id}/dependencies` | member | `read` | Dependency inventory |
| `GET` | `/protocols/{id}/audits` | member | `read` | Audit history |

Discovery never auto-publishes. `publish` requires a reviewer role and records the review.

---

## 5. Research

### 5.1 Studies

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/research/studies` | member | `read` | List studies |
| `POST` | `/research/studies` | member | `research:write` | Create study |
| `GET` | `/research/studies/{id}` | member | `read` | Study detail |
| `PATCH` | `/research/studies/{id}` | member | `research:write` | Update study |
| `POST` | `/research/studies/{id}/close` | member | `research:write` | Close study |

### 5.2 Experiments

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/experiments` | member | `read` | List experiments |
| `POST` | `/experiments` | member | `research:write` | Create draft (Idempotency-Key) |
| `GET` | `/experiments/{id}` | member | `read` | Definition + status |
| `PATCH` | `/experiments/{id}` | member | `research:write` | Edit draft (ETag) |
| `POST` | `/experiments/{id}/validate` | member | `research:write` | Validate definition |
| `POST` | `/experiments/{id}/runs` | member | `research:write` | Start run (Idempotency-Key) |
| `GET` | `/experiments/{id}/runs` | member | `read` | List runs |
| `GET` | `/experiments/{id}/runs/{run_id}` | member | `read` | Run detail |
| `POST` | `/experiments/{id}/runs/{run_id}/cancel` | member | `research:write` | Cancel run |
| `GET` | `/runs/{run_id}/artifacts` | member | `read` | Artifact list |
| `GET` | `/runs/{run_id}/artifacts/{artifact_id}/download` | member | `read` | Presigned download |
| `POST` | `/runs/{run_id}/verify` | member | `research:write` | Re-run deterministic verifier |
| `POST` | `/runs/{run_id}/reproduce` | member | `research:write` | Create a reproduction run |
| `GET` | `/runs/{run_id}/manifest` | member | `read` | Immutable manifest |

Run detail:

```json
{
  "id": "run_01JB8Z...",
  "experiment_id": "exp_01JB8Z...",
  "version": 2,
  "attempt": 1,
  "status": "verifying",
  "verification_status": "pending",
  "started_at": "2026-11-02T10:00:00Z",
  "finished_at": null,
  "manifest_hash": "sha256:...",
  "artifacts": 6,
  "trace_id": "4bf92f...",
  "links": {"self": "...", "events": "..."}
}
```

### 5.3 Datasets

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/datasets` | member | `read` | List datasets |
| `POST` | `/datasets` | member | `research:write` | Create dataset |
| `GET` | `/datasets/{id}` | member | `read` | Dataset + versions |
| `POST` | `/datasets/{id}/versions` | member | `research:write` | Create upload session |
| `POST` | `/datasets/{id}/versions/{version}/complete` | member | `research:write` | Verify hashes and seal |
| `GET` | `/datasets/{id}/versions/{version}/download` | member | `read` | Presigned bundle URL |

### 5.4 Reports

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/reports` | member | `read` | List reports |
| `POST` | `/reports` | member | `research:write` | Create draft |
| `GET` | `/reports/{id}` | member | `read` | Report + versions |
| `PATCH` | `/reports/{id}` | member | `research:write` | Edit draft |
| `POST` | `/reports/{id}/publish` | reviewer | `research:write` | Publish reviewed version (Idempotency-Key) |
| `POST` | `/reports/{id}/retract` | owner/reviewer | `research:write` | Retract with reason |

Publication requires a review record; the API rejects self-review if policy forbids it.

---

## 6. Cryptography

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/cryptography/frameworks` | member | `read` | Adapter catalog |
| `GET` | `/cryptography/circuits` | member | `read` | List circuits |
| `POST` | `/cryptography/circuits` | member | `crypto:write` | Register circuit source |
| `GET` | `/cryptography/circuits/{id}` | member | `read` | Circuit + builds |
| `POST` | `/cryptography/circuits/{id}/builds` | member | `crypto:write` | Queue build |
| `GET` | `/cryptography/proof-systems` | member | `read` | Proof system catalog |
| `GET` | `/cryptography/proof-runs` | member | `read` | List proof runs |
| `GET` | `/cryptography/benchmarks` | member | `read` | Comparable benchmarks |
| `GET` | `/cryptography/benchmarks/{id}` | member | `read` | Raw samples + environment |

Benchmark query requires explicit comparability filters:

```text
GET /cryptography/benchmarks?framework=circom&workload=membership&comparability=comparable
```

---

## 7. Chain Intelligence

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/chains` | member | `read` | Registered networks + health |
| `GET` | `/chains/{id}` | member | `read` | Network detail |
| `GET` | `/chains/{id}/status` | member | `read` | Head, lag, finality |
| `GET` | `/chains/{id}/blocks` | member | `read` | List blocks |
| `GET` | `/chains/{id}/blocks/{number}` | member | `read` | Block + transactions |
| `GET` | `/chains/{id}/transactions/{hash}` | member | `read` | Transaction + receipt |
| `GET` | `/chains/{id}/logs` | member | `read` | Logs by address/topic/range |
| `POST` | `/chains/{id}/sync` | admin | `system:admin` | Trigger backfill |
| `GET` | `/chains/{id}/reorgs` | member | `read` | Reorg history |

Chain list response includes `kind` (`local`/`testnet`), `chain_id`, `finality_model` and a
`testnet: true` flag. No endpoint accepts an arbitrary RPC URL.

---

## 8. Security Center

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/security/assessments` | member | `read` | List assessments |
| `POST` | `/security/assessments` | member | `security:write` | Queue scan/fuzz |
| `GET` | `/security/assessments/{id}` | member | `read` | Assessment detail |
| `GET` | `/security/findings` | member | `read` | List findings |
| `POST` | `/security/findings` | member | `security:write` | Create draft finding |
| `GET` | `/security/findings/{id}` | member | `read` | Finding + evidence |
| `PATCH` | `/security/findings/{id}` | member | `security:write` | Update triage |
| `POST` | `/security/findings/{id}/verify` | reviewer | `security:write` | Verify reproduction |
| `POST` | `/security/findings/{id}/publish` | reviewer | `security:write` | Publish after disclosure review |
| `GET` | `/security/threat-models` | member | `read` | Threat model registry |

Findings default to `confidential`; list responses hide details unless the caller has
`security:write` or is a reviewer.

---

## 9. Privacy Products

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/privacy/schemes` | member | `read` | Identity scheme catalog |
| `GET` | `/privacy/credentials` | member | `read` | Credentials (commitments only) |
| `POST` | `/privacy/credentials` | member | `research:write` | Issue a test credential |
| `GET` | `/privacy/trees` | member | `read` | Merkle trees |
| `POST` | `/privacy/trees` | member | `research:write` | Create tree |
| `POST` | `/privacy/trees/{id}/leaves` | member | `research:write` | Add commitment |
| `POST` | `/privacy/proofs` | member | `research:write` | Request membership/disclosure proof |
| `GET` | `/privacy/proofs/{id}` | member | `read` | Proof status + verifier output |
| `POST` | `/privacy/nullifiers/check` | member | `read` | Check nullifier usage (no secret) |

No raw PII is accepted by these endpoints. Credentials are commitments and metadata.

---

## 10. VeilGuard Testnet

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/veilguard/wallets` | member | `read` | List test wallets (no keys) |
| `POST` | `/veilguard/wallets` | admin | `veilguard:admin` | Register wallet via signer |
| `GET` | `/veilguard/wallets/{id}` | member | `read` | Wallet + policy + usage |
| `POST` | `/veilguard/wallets/{id}/policies` | admin | `veilguard:admin` | Create policy version |
| `POST` | `/veilguard/simulations` | member | `veilguard:request` | Simulate a transaction |
| `GET` | `/veilguard/requests` | member | `read` | List requests |
| `POST` | `/veilguard/requests` | member | `veilguard:request` | Create request (Idempotency-Key) |
| `GET` | `/veilguard/requests/{id}` | member | `read` | Request + simulation + approval |
| `POST` | `/veilguard/requests/{id}/approve` | reviewer | `veilguard:approve` | Approve (Idempotency-Key) |
| `POST` | `/veilguard/requests/{id}/reject` | reviewer | `veilguard:approve` | Reject with reason |
| `POST` | `/veilguard/requests/{id}/execute` | member | `veilguard:request` | Request execution after approval |
| `GET` | `/veilguard/transactions` | member | `read` | Reconciliation list |
| `POST` | `/veilguard/kill-switch` | owner | `veilguard:admin` | Disable all signing/broadcast |
| `POST` | `/veilguard/kill-switch/reset` | owner | `veilguard:admin` | Re-enable after review |

Execution response:

```json
{
  "request_id": "txr_01JB8Z...",
  "status": "submitted",
  "tx_hash": "0x...",
  "network": {"id": "eth-sepolia", "chain_id": 11155111, "testnet": true},
  "simulation_hash": "sha256:...",
  "policy_id": "pol_...",
  "approval_id": "apr_...",
  "links": {"transaction": "/api/v1/veilguard/transactions/..."}
}
```

---

## 11. Agents and models

### 11.1 Agents

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/agents` | member | `read` | Agent roster |
| `POST` | `/agents` | member | `agents:write` | Create agent |
| `PATCH` | `/agents/{id}` | member | `agents:write` | Update capabilities/defaults |
| `GET` | `/agents/tasks` | member | `read` | List tasks |
| `POST` | `/agents/tasks` | member | `agents:write` | Create task (Idempotency-Key) |
| `GET` | `/agents/tasks/{id}` | member | `read` | Task detail |
| `GET` | `/agents/tasks/{id}/steps` | member | `read` | Steps and tool calls |
| `POST` | `/agents/tasks/{id}/cancel` | member | `agents:write` | Cancel and revoke token |

Task creation requires explicit `capabilities`; the API rejects forbidden capabilities and
requires approval for restricted ones.

### 11.2 Models

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/models/providers` | member | `read` | Providers (no keys) |
| `POST` | `/models/providers` | admin | `models:admin` | Register provider + secret ref |
| `PATCH` | `/models/providers/{id}` | admin | `models:admin` | Update provider |
| `POST` | `/models/providers/{id}/test` | admin | `models:admin` | Health check |
| `GET` | `/models/routes` | member | `read` | Virtual model routes |
| `POST` | `/models/routes` | admin | `models:admin` | Create route |
| `GET` | `/models/usage` | member | `read` | Tokens and cost |

Provider responses never include API keys or full base URLs with credentials.

---

## 12. Plugins

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/plugins` | member | `read` | Installed plugins |
| `POST` | `/plugins/install` | admin | `plugins:admin` | Upload/install bundle (Idempotency-Key) |
| `GET` | `/plugins/{id}` | member | `read` | Manifest, permissions, status |
| `POST` | `/plugins/{id}/enable` | admin | `plugins:admin` | Enable for project |
| `POST` | `/plugins/{id}/disable` | admin | `plugins:admin` | Disable |
| `DELETE` | `/plugins/{id}` | admin | `plugins:admin` | Remove after retention |

Installation does not imply enablement. Permission diffs are returned for review.

---

## 13. System

| Method | Path | Auth | Scope | Purpose |
| --- | --- | --- | --- | --- |
| `GET` | `/system/health` | public | — | Liveness/readiness (no details) |
| `GET` | `/system/status` | member | `read` | Component status (redacted) |
| `GET` | `/system/jobs` | admin | `system:admin` | Job queue view |
| `GET` | `/system/jobs/{id}` | admin | `system:admin` | Job detail |
| `POST` | `/system/jobs/{id}/cancel` | admin | `system:admin` | Cancel job |
| `GET` | `/system/audit` | auditor/owner | `audit:read` | Audit query |
| `GET` | `/system/config` | owner | `system:admin` | Safe config view (no secrets) |
| `GET` | `/system/queues` | admin | `system:admin` | Queue depth/lag |
| `POST` | `/system/replay` | admin | `system:admin` | Replay events (audited) |

`/system/health` returns only `{"status":"ok"}` or `503`; dependency details stay internal.

---

## 14. WebSocket events

`GET /api/v1/ws/events?ticket=...`

Client messages:

```json
{"type": "subscribe", "topics": ["research", "chain"]}
{"type": "unsubscribe", "topics": ["chain"]}
{"type": "ping"}
```

Server messages:

```json
{"type": "event", "event": {"specversion": "1.0", "id": "evt_...", "type": "dev.veillab.research.experiment.completed.v1", "data": {...}}}
{"type": "subscribed", "topics": ["research"]}
{"type": "error", "code": "FORBIDDEN_TOPIC", "message": "..."}
```

Server filters by project membership and topic permission. Payloads are the same as the
event schema, with sensitive fields removed.

---

## 15. Internal endpoints

These are not public; mTLS and caller identity are mandatory.

| Method | Path | Caller | Purpose |
| --- | --- | --- | --- |
| `POST` | `/internal/v1/runners/lease` | runner-controller | Lease a run |
| `POST` | `/internal/v1/runners/{runner_id}/heartbeat` | runner-controller | Extend lease |
| `POST` | `/internal/v1/runners/{runner_id}/complete` | runner-controller | Report result + artifact hashes |
| `POST` | `/internal/v1/agent-tools/{tool}` | agent-runtime | Invoke a mediated tool |
| `POST` | `/internal/v1/signer/sign` | testnet-gateway | Request signature (local pinned channel) |
| `POST` | `/internal/v1/chain/{network}/call` | collector/api | Allowlisted RPC method |
| `POST` | `/internal/v1/chain/{network}/send-raw` | testnet-gateway | Broadcast signed tx |

Internal calls include `X-Request-ID`, `X-Trace-ID` and the caller's service identity. They
do not accept user sessions.

---

## 16. Status codes

| Code | Use |
| --- | --- |
| `200` | Read/update success |
| `201` | Resource created |
| `202` | Job/run accepted |
| `204` | Delete/no content |
| `302` | Presigned download redirect |
| `400` | Malformed request |
| `401` | Unauthenticated |
| `403` | Forbidden / policy denied |
| `404` | Not found / not visible |
| `409` | Conflict / idempotency mismatch |
| `412` | ETag mismatch |
| `422` | Validation error |
| `429` | Rate/quota limited |
| `500` | Internal error (no details) |
| `503` | Dependency unavailable / fail closed |

---

## 17. Deferred to later versions

- OIDC login endpoints (v0.5).
- Batch/bulk operations.
- GraphQL (not planned).
- Public webhooks (v1.0, signed).
- Multi-region routing.
- User-facing plugin marketplace APIs.
