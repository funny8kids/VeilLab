# API Conventions

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [API_SPECIFICATION](API_SPECIFICATION.md) · [EVENT_SCHEMA](EVENT_SCHEMA.md)

---

## 1. Style and scope

- REST over HTTPS, JSON (`application/json`), UTF-8.
- Base path: `/api/v1`.
- OpenAPI 3.1 is generated from FastAPI/Pydantic and is the machine-readable source of truth.
- This document defines conventions; [API_SPECIFICATION.md](API_SPECIFICATION.md) defines the
  endpoint baseline.
- Binary content is transferred via short-lived presigned URLs, not base64 in JSON.
- Internal service APIs live under `/internal/v1`, require mTLS and are never exposed by the
  public reverse proxy.

---

## 2. Authentication

| Client | Mechanism | Header / transport |
| --- | --- | --- |
| Web console | Session cookie + CSRF token | `Cookie: vl_session=...`, `X-CSRF-Token` |
| CLI / automation | Personal access token | `Authorization: Bearer vlp_...` |
| Service | mTLS + short-lived service token | Client certificate + `Authorization` |
| Agent | Capability JWT | `Authorization: Bearer <capability>` |
| WebSocket | Short-lived WS ticket | `?ticket=...` |

Rules:

- Session cookies are `HttpOnly`, `Secure`, `SameSite=Lax`.
- Mutating requests authenticated by cookie MUST include a valid CSRF token.
- PATs are prefixed `vlp_`, hashed at rest and shown once.
- Capability tokens are audience-bound and short-lived; they are not accepted on public
  user endpoints.
- Authentication failures return `401` without revealing whether the account exists.
- Authorization failures return `403` with a policy reason and request ID.

---

## 3. Scopes

PATs and service tokens use explicit scopes:

```text
read                     # read any resource in the token's project
write                    # create/update non-privileged resources
research:write           # experiments, datasets, reports
crypto:write             # circuits, builds, proofs
security:write           # assessments, findings
veilguard:request        # create testnet requests
veilguard:approve        # approve testnet requests
veilguard:admin          # wallets, policies, kill switch
agents:write             # create agents and tasks
models:admin             # providers, routes, keys metadata
plugins:admin            # install/enable plugins
system:admin             # settings, feature flags
audit:read               # audit log
```

- A token can be narrowed to a single `project_id`.
- `admin` implies domain write scopes only within its workspace/project, not global.
- Approval scopes cannot be granted to agents.
- Scope escalation requires a new token, not a header.

---

## 4. Resource representation

- JSON objects use `snake_case`.
- IDs are opaque strings with a prefix (`exp_...`); clients MUST NOT parse them.
- Timestamps are ISO 8601 UTC with `Z`.
- Amounts are strings for wei values to avoid JavaScript precision loss:
  `"value_wei": "1000000000000000"`.
- Hashes are lowercase strings (`0x...` or `sha256:...`).
- Enumerations are lowercase strings; unknown values MUST be handled gracefully.
- `null` means absent; fields are omitted only when documented as optional.
- Responses include a top-level resource or a list object; no redundant `{data: ...}`
  envelope.

Example:

```json
{
  "id": "exp_01JB8Z4K2M9Q7R3T5V6W8X0Y1Z",
  "project_id": "prj_01JB8Z...",
  "name": "semaphore-membership-bench",
  "type": "benchmark",
  "status": "validated",
  "current_version": 2,
  "created_at": "2026-11-02T09:30:00Z",
  "updated_at": "2026-11-02T09:45:00Z"
}
```

The version is carried in the `ETag: "v2"` response header, not in the JSON body.

---

## 5. Errors

Errors use `application/problem+json` (RFC 9457):

```json
{
  "type": "https://docs.veillab.dev/problems/validation-error",
  "title": "Validation failed",
  "status": 422,
  "detail": "The experiment definition is invalid.",
  "instance": "/api/v1/experiments",
  "code": "EXPERIMENT_INVALID",
  "request_id": "req_01JB8Z...",
  "errors": [
    {"field": "spec.resources.memory_mb", "code": "max_exceeded", "message": "Exceeds project quota (16384)."}
  ]
}
```

Rules:

- `type` is a stable URI; `code` is a stable machine-readable string.
- `detail` is safe for display; no stack traces, SQL, hostnames or secrets.
- `request_id` is always present and echoed in `X-Request-ID`.
- Validation errors include a field path.
- `401` vs `403`: unauthenticated vs authenticated-but-denied.
- `404` is used for resources the caller cannot see, to avoid existence leaks.
- `409` for state conflicts and idempotency mismatch.
- `429` includes `Retry-After`.

Common codes:

| Code | HTTP | Meaning |
| --- | --- | --- |
| `UNAUTHENTICATED` | 401 | Missing/invalid credentials |
| `FORBIDDEN` | 403 | Capability/role denied |
| `NOT_FOUND` | 404 | Resource absent or not visible |
| `CONFLICT` | 409 | State conflict |
| `IDEMPOTENCY_MISMATCH` | 409 | Same key, different request |
| `PRECONDITION_FAILED` | 412 | ETag mismatch |
| `VALIDATION_ERROR` | 422 | Schema/field error |
| `RATE_LIMITED` | 429 | Quota exceeded |
| `CHAIN_NOT_ALLOWED` | 403 | Mainnet/unknown chain |
| `POLICY_DENIED` | 403 | VeilGuard policy rejection |
| `CAPABILITY_DENIED` | 403 | Agent capability missing |
| `JOB_NOT_CANCELLABLE` | 409 | Job already terminal |

---

## 6. Pagination, filtering, sorting

### Pagination

Cursor-based, stable under inserts:

```http
GET /api/v1/experiments?limit=50&cursor=eyJjcmVhdGVkX2F0IjoiLi4uIiwiaWQiOiJleHBfLi4uIn0
```

```json
{
  "items": [ ... ],
  "next_cursor": "eyJjcmVhdGVkX2F0IjoiLi4uIiwiaWQiOiJleHBfLi4uIn0"
}
```

- `limit` default 50, max 200.
- `next_cursor` is `null` on the last page.
- Cursors encode `(created_at, id)` and are opaque to clients.
- Deleted or inaccessible items are skipped without breaking the cursor.

### Filtering

Explicit query parameters only:

```text
?status=completed&type=benchmark&created_after=2026-10-01T00:00:00Z
```

No generic query language in v1. Free-form search uses a dedicated `q` parameter with
server-defined fields and limits.

### Sorting

`?sort=-created_at` (descending) or `?sort=name`. Allowed fields are documented per endpoint.
Default is `-created_at` for lists.

---

## 7. Idempotency

Required for:

- creating experiments/runs,
- starting jobs,
- creating testnet transaction requests,
- approvals,
- plugin installation,
- report publication.

```http
Idempotency-Key: 8f14e45f-ea0b-4b1e-9c2a-3f6d2a1b7c90
```

Behavior:

- Same key + same request hash within 24 hours ⇒ original response (with
  `Idempotent-Replayed: true`).
- Same key + different request hash ⇒ `409 IDEMPOTENCY_MISMATCH`.
- Keys are scoped to actor + endpoint.
- A key is not a substitute for optimistic concurrency.

---

## 8. Concurrency

- Mutable resources return `ETag: "v3"`.
- Updates MAY require `If-Match: "v3"`.
- A mismatch returns `412 PRECONDITION_FAILED` with the current resource.
- State transitions use explicit action endpoints (`/validate`, `/runs`, `/approve`) rather
  than a generic PATCH of `status`.
- Two conflicting transitions return `409`.

---

## 9. Long-running operations

Anything that can exceed ~2 seconds returns `202 Accepted`:

```http
POST /api/v1/experiments/exp_.../runs
Idempotency-Key: ...
```

```json
{
  "run_id": "run_01JB8Z...",
  "job_id": "job_01JB8Z...",
  "status": "queued",
  "links": {
    "self": "/api/v1/experiments/exp_.../runs/run_01JB8Z...",
    "events": "/api/v1/ws/events"
  }
}
```

- Clients poll the resource or subscribe to events.
- Do not hold HTTP connections for the duration of a proof.
- Cancellation is an explicit endpoint and is best-effort; the runner must acknowledge.

---

## 10. Rate limits and quotas

- Limits apply per user, per PAT, per project and per agent task.
- Responses include:

```text
RateLimit-Limit: 120
RateLimit-Remaining: 87
RateLimit-Reset: 1762071000
Retry-After: 12
```

- Default public API: 120 requests/minute/user; burst 30.
- Expensive endpoints (benchmark start, security scan) have separate quotas.
- Quota exhaustion returns `429` and an audit event if it indicates abuse.

---

## 11. Uploads and downloads

### Upload

1. `POST /api/v1/datasets/{id}/versions` with file manifest and SHA-256 hashes.
2. API returns presigned PUT URLs valid for 15 minutes.
3. Client uploads directly to MinIO.
4. Client calls `POST .../complete` with hashes.
5. Server verifies size/hash and marks the version `ready`.

Limits: 2 GB per file (configurable), 50 GB per dataset version, archive inspection enabled.

### Download

- `GET /api/v1/.../download` returns `302` to a presigned URL valid for 5 minutes.
- The API never streams large objects itself.
- Downloads of `confidential` artifacts are audited.
- Range requests are supported by MinIO, not the API.

---

## 12. WebSocket

```text
POST /api/v1/auth/ws-ticket  → { "ticket": "...", "expires_at": "..." }
GET  /api/v1/ws/events?ticket=...&topics=research,chain
```

- Tickets are single-use, 60-second TTL, bound to the session/project.
- Server sends project-filtered events only.
- Client sends `{"type":"subscribe","topics":["research"]}` after connect.
- Heartbeat every 30 seconds; reconnect with exponential backoff.
- The server may close with code `4401` (auth), `4403` (forbidden), `4429` (rate limit).
- Events are hints; clients re-fetch authoritative resources.

---

## 13. Internal API

- Prefix `/internal/v1`.
- mTLS required; caller identity checked against the expected peer.
- Not routed by the public reverse proxy.
- Short-lived tokens, audience-bound.
- Endpoints: runner lease/heartbeat/complete, agent tool invocation, signer request,
  chain gateway methods.
- Internal errors use the same problem+json shape but never expose internal details to
  public clients.

---

## 14. Versioning and compatibility

- URL major version `/api/v1`.
- Additive fields are non-breaking; clients MUST ignore unknown fields.
- Removing/renaming a field or changing semantics requires `/api/v2`.
- Deprecation: `Deprecation` and `Sunset` headers, minimum 90 days notice.
- Event schemas follow the same rule (see [EVENT_SCHEMA](EVENT_SCHEMA.md)).
- OpenAPI diff is checked in CI; breaking changes fail the build unless approved.

---

## 15. Security headers and CORS

- TLS only; HSTS enabled.
- CORS is disabled by default. If the console is served from a different origin, allow only
  the exact console origin with credentials.
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy` restrictive.
- CSP is served by the web host, not the API.
- No wildcard CORS with credentials.

---

## 16. OpenAPI and SDKs

- FastAPI generates `openapi.json` at build time.
- `packages/contracts` holds shared Pydantic models; `packages/sdk-ts` and
  `packages/sdk-python` are generated.
- CI checks:
  - spec is valid,
  - generated clients compile,
  - no unintended breaking diff,
  - every endpoint has auth, error responses and an example.
- Hand-written clients are not allowed for the console.

---

## 17. Examples

### Create and start an experiment

```http
POST /api/v1/experiments
Authorization: Bearer vlp_...
Content-Type: application/json
Idempotency-Key: 3c1f...

{
  "project_id": "prj_01JB8Z...",
  "study_id": "study_01JB8Z...",
  "name": "semaphore-membership-bench",
  "type": "benchmark",
  "definition": {
    "api_version": "veillab.dev/v1",
    "adapter": "circom",
    "source": {"repo": "https://github.com/semaphore-protocol/semaphore", "commit": "abc123"},
    "resources": {"cpu": 4, "memory_mb": 8192, "timeout_seconds": 1800},
    "workload": {"circuit": "membership", "repetitions": 5}
  }
}
```

```http
HTTP/1.1 201 Created
ETag: "v1"

{"id":"exp_01JB8Z...","status":"draft","current_version":1,...}
```

```http
POST /api/v1/experiments/exp_01JB8Z.../validate
```

```http
POST /api/v1/experiments/exp_01JB8Z.../runs
Idempotency-Key: 9a2b...

HTTP/1.1 202 Accepted
{"run_id":"run_01JB8Z...","job_id":"job_01JB8Z...","status":"queued"}
```

### Testnet request

```http
POST /api/v1/veilguard/requests
Authorization: Bearer vlp_...
Idempotency-Key: 7d3e...

{
  "project_id": "prj_01JB8Z...",
  "wallet_id": "wlt_01JB8Z...",
  "network_id": "eth-sepolia",
  "to": "0x...",
  "value_wei": "0",
  "data": "0x...",
  "reason": "Test membership verifier deployment"
}
```

Response includes the simulation, policy decision and whether approval is required. A
separate `POST /veilguard/requests/{id}/approve` is performed by a human with
`veilguard:approve`.
