# ADR-001 · Modular Monolith for the Business Plane

**Status:** Accepted · **Date:** 2026-11-02 · **Deciders:** Architecture, Platform

---

## Context

VeilLab has six business planes (Research, Cryptography, Chain Intelligence, Security,
Privacy Products, VeilGuard) sharing identity, projects, jobs, events, datasets and audit.
The initial team is one operator plus AI assistance, deployed on a single host.

A microservice-first architecture would require:

- independent deploy pipelines, versioning and service discovery,
- distributed transactions or sagas for simple workflows,
- multiple databases or shared-database coupling,
- observability and on-call maturity that does not yet exist,
- significantly more code and configuration before the first experiment runs.

At the same time, not all workloads can share a process: untrusted builds, AI agents, chain
collection and signing have different trust and resource profiles.

## Decision

1. **Business logic is a modular monolith**: one FastAPI application (`apps/api`) composes
   domain modules under `core/`. Workers and the scheduler reuse the same modules through
   job handlers.
2. **One PostgreSQL database** holds business state. Each module owns its schema/tables and
   only writes its own data.
3. **Modules communicate through public facades** (`core/<module>/api.py`) for synchronous
   calls and through a transactional outbox + events for side effects.
4. **Separate deployables only where trust, resource or failure isolation demands it**:
   `runner-controller`/sandboxes, `crypto-core`, `chain-collector`, `chain-gateway`,
   `testnet-gateway`, `test-signer`, `agent-runtime`, `model-gateway`.
5. **No shared database across zones** for research runners, agents or the signer.
6. **Boundaries are enforced** by import-linter, schema ownership tests, database roles and
   architecture tests, not by convention alone.

## Consequences

### Positive

- One transaction boundary for most workflows; simpler consistency.
- One migration stream, one API contract, one deployment for business changes.
- Lower operational burden for a small team.
- Refactoring module boundaries is cheaper than refactoring network boundaries.
- Isolated components still get least privilege and independent failure domains.

### Negative

- A bug in one module can affect the whole API process.
- Scaling is coarse-grained; a heavy endpoint can starve others.
- Module discipline must be enforced continuously or the monolith becomes tangled.
- The API process holds more credentials than a microservice would.

### Mitigations

- Long-running work always goes to workers; the API does not compute proofs.
- Per-module rate limits and quotas.
- Import contracts and schema grants in CI.
- Clear split triggers (see below).

## Alternatives considered

| Alternative | Why not now |
| --- | --- |
| Microservices per plane | Premature operational cost; distributed workflows without a team to operate them |
| Serverless functions | Poor fit for long-running proofs, local state and custom networking |
| Single Python script/notebook | No audit, isolation, reproducibility or multi-user support |
| Modular monolith with separate databases per module | Distributed consistency without the scaling benefit |

## Split triggers

Split a module into a service when at least one is true:

- it needs a different trust zone or credential set (already done for runners/agents/testnet),
- its CPU/memory profile starves the API,
- it must scale independently based on measured load,
- a separate team owns its release cadence,
- it has a materially different availability SLO.

## References

- [SYSTEM_ARCHITECTURE](../architecture/SYSTEM_ARCHITECTURE.md)
- [MODULE_BOUNDARIES](../architecture/MODULE_BOUNDARIES.md)
- [EVENT_ARCHITECTURE](../architecture/EVENT_ARCHITECTURE.md)
