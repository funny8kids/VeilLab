# Control Center

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [MODULE_BOUNDARIES](MODULE_BOUNDARIES.md) · [API_SPECIFICATION](../api/API_SPECIFICATION.md) · [SECURITY_ARCHITECTURE](../security/SECURITY_ARCHITECTURE.md)

---

## 1. Purpose

The Control Center is the entry point and shared substrate of VeilLab. It provides:

- identity, sessions and service identity,
- workspaces, projects and tenant isolation,
- RBAC and capability issuance,
- plugin registry and lifecycle,
- durable jobs and scheduling,
- events and audit,
- quotas and system settings.

It does **not** perform research, cryptography, chain collection, security analysis or
testnet signing. It authorizes and coordinates those planes.

---

## 2. Module map

```text
core/control_center/
├── identity/          # users, sessions, PATs, OIDC, service accounts
├── projects/          # workspaces, projects, memberships, quotas
├── iam/               # roles, policies, capability grants
├── plugins/           # manifest validation, install/enable, permissions
├── jobs/              # durable jobs, leases, retries, cancellation
├── events/            # outbox, relay, subscriptions, replay
└── audit/             # append-only audit, query, anchors
```

Each submodule follows the facade pattern in
[MODULE_BOUNDARIES](MODULE_BOUNDARIES.md): only `api.py` is imported by other modules.

---

## 3. Identity and sessions

### Human login (v0.1)

1. `POST /auth/login` with email + password.
2. Password verified with Argon2id; failures are rate-limited and audited.
3. If TOTP is enabled, a second factor is required.
4. A session is created: random 256-bit token, stored as a hash, delivered as an
   `HttpOnly`, `Secure`, `SameSite=Lax` cookie.
5. A CSRF token is returned for cookie-authenticated mutations.
6. `GET /auth/me` returns the actor, memberships, roles and permissions.

### PATs

- Created from a session, shown once, stored as SHA-256 hash.
- Scoped and optionally project-bound; expiry ≤ 90 days by default.
- Last-used timestamp and revocation are audited.
- PATs cannot be used for approval actions unless the scope explicitly allows it.

### OIDC (v0.5)

- Authorization Code + PKCE.
- Map IdP groups to workspace/project roles via explicit configuration.
- Do not auto-create admin users from unverified claims.
- Keep local break-glass admin disabled by default in production-like deployments.

### Service identity

- mTLS certificate with a service SAN.
- Short-lived service token audience-bound to the callee.
- Service accounts have explicit scopes, not a human session.

---

## 4. Workspaces and projects

```text
Workspace (billing/ownership boundary)
└── Project (research/data isolation boundary)
    ├── members and roles
    ├── experiments/datasets/reports
    ├── chain data scope
    ├── wallets/policies
    └── agents/tasks
```

Rules:

- Every tenant resource has a `project_id`.
- A user may belong to multiple projects with different roles.
- Project deletion is a two-step, audited flow with a 30-day grace period.
- Quotas are per project and enforced at job creation, not only at runtime.
- Switching project context in the UI clears cached data and cancels in-flight queries.
- Cross-project access returns `404` unless the caller is a workspace owner performing an
  audited admin action.

---

## 5. RBAC and capabilities

### Human roles

`workspace_owner`, `workspace_admin`, `project_admin`, `researcher`, `reviewer`, `viewer`,
`auditor`. The permission matrix is in
[SECURITY_ARCHITECTURE §4](../security/SECURITY_ARCHITECTURE.md#4-authorization).

### Capability grants

- Issued to agents, jobs and plugins—not to humans.
- Bound to project, resources, capabilities, quotas, audience and expiry.
- Stored in `identity.capability_grants`; the JWT is a short-lived projection.
- Revocation by `jti` takes effect immediately for new calls.
- Issuance requires an explicit task and policy check; no standing agent tokens.

### Policy decisions

Every privileged operation returns a decision:

```json
{
  "allow": false,
  "reason": "capability_missing",
  "policy_id": "pol_...",
  "capability": "testnet.execute",
  "resource": "wlt_...",
  "request_id": "req_..."
}
```

Denials are audited and emitted as `identity.policy.denied`.

---

## 6. Plugin registry

Lifecycle: upload → validate → scan → review → install → enable → disable/quarantine → remove.

Rules:

- Installation does not grant runtime permission.
- Permission changes require re-approval.
- Third-party code runs only in an isolated worker.
- A revoked digest cannot start.
- See [PLUGIN_ARCHITECTURE](PLUGIN_ARCHITECTURE.md).

---

## 7. Jobs

### State machine

```text
queued → leased → running → succeeded
   │        │        │
   │        │        └→ failed → retry (new attempt) → queued
   │        └→ lease_expired → queued
   └→ cancelled
```

- A job is durable in PostgreSQL; the queue message is a hint.
- A worker claims with a lease and heartbeat.
- A lost lease means the worker must not commit results.
- Idempotency keys prevent duplicate side effects.
- Cancellation is cooperative with a hard kill path for sandboxes.
- Retries use exponential backoff with jitter and a max attempt count.
- Exhausted jobs go to a DLQ with an alert.

### Queues

`default`, `discovery`, `chain_sync`, `experiments`, `security`, `reports`, `maintenance`.
Crypto/benchmark jobs are **not** executed by the general worker; they are leased to the
Research runner.

### Quotas

Per project: concurrent jobs, CPU/memory, wall time, runs/day, storage. Per agent: tool calls,
tokens, cost. Per wallet: transactions/day, value/day. Quotas are reserved before execution.

---

## 8. Events and audit

- State change + outbox insert in one transaction.
- Relay publishes to Redis Streams; consumers are idempotent.
- Every privileged action writes an audit record with actor, capability, decision, resource,
  trace ID and request ID.
- Audit is append-only; a daily hash anchor is written to WORM storage.
- See [EVENT_ARCHITECTURE](EVENT_ARCHITECTURE.md) and
  [EVENT_SCHEMA](../api/EVENT_SCHEMA.md).

---

## 9. Settings and configuration

| Setting | Scope | Change control |
| --- | --- | --- |
| Feature flags | Global/project | Admin + audit |
| Quotas | Project | Admin + audit |
| Model routing | Global/project | Admin + audit |
| Chain registry | Global | Security review + startup validation |
| Network allowlist | Global | Security review + CI test |
| Plugin permissions | Project | Admin review + audit |
| Retention policy | Global/project | Data owner + audit |

Secrets are never stored in settings. Settings hold references only.

---

## 10. Failure behavior

| Failure | Behavior |
| --- | --- |
| Identity provider unavailable | Existing sessions continue until expiry; new logins fail closed |
| Redis unavailable | API serves reads; job creation returns 503 |
| Outbox relay down | State changes continue; events queue; alert |
| Audit write fails | Privileged action fails closed |
| Plugin registry unavailable | Existing enabled plugins continue if digest cached; new installs fail |
| Quota service unavailable | Deny new jobs (fail closed) |

---

## 11. Acceptance tests

- Login/logout/session expiry/CSRF/TOTP.
- PAT scope and revocation.
- Workspace/project membership and cross-tenant access.
- Capability issuance, expiry and revocation.
- Job lease, heartbeat, lost lease, retry, cancel.
- Outbox relay and consumer idempotency.
- Audit hash chain and anchor verification.
- Plugin install/enable/permission diff/quarantine.
- Fail-closed behavior for Redis/audit/quota outages.

G0 covers the core; G5 and G7 cover agent and plugin-specific cases.

---

## 12. Open questions

- OIDC provider choice and group mapping.
- Break-glass admin procedure for a single-operator deployment.
- Whether project quotas are hard or burstable.
- Audit retention and external anchoring provider.
