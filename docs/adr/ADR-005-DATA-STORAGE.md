# ADR-005 · Polyglot Persistence

**Status:** Accepted · **Date:** 2026-11-02 · **Deciders:** Data, Architecture

---

## Context

VeilLab stores fundamentally different data:

- transactional business metadata (users, projects, experiments, findings, wallets),
- high-volume append-only chain facts (blocks, transactions, logs),
- large immutable objects (source snapshots, proofs, datasets, reports),
- ephemeral coordination (queues, locks, caches, rate limits).

A single PostgreSQL instance would struggle with chain analytics volume and object storage.
A data lake alone would lose transactional guarantees for business state. A document store
would weaken schema and relational integrity.

## Decision

Use four purpose-built stores with explicit ownership:

| Store | Role | Why |
| --- | --- | --- |
| **PostgreSQL** | Business system of record | ACID, relational integrity, RLS, outbox, jobs |
| **ClickHouse** | Chain analytics | Columnar compression, scan speed, TTL, partitions |
| **MinIO** | Immutable objects | Content addressing, versioning, object lock, presigned URLs |
| **Redis** | Ephemeral coordination | Low-latency queues, locks, rate limits, revocation sets |

Rules:

1. PostgreSQL is authoritative for business state. ClickHouse is derived and rebuildable.
2. MinIO objects are immutable by hash; metadata lives in PostgreSQL.
3. Redis is never the only copy of durable state.
4. Each module owns its PostgreSQL schema; no cross-schema writes.
5. Cross-store consistency uses the outbox/event pattern and idempotent projections.
6. Chain raw data is written to MinIO before normalization, so ClickHouse can be rebuilt.
7. Object keys are content-addressed and never contain user-controlled paths.
8. Every store has an independent backup and restore procedure (G8).

## Consequences

### Positive

- Right tool for each workload; predictable performance at research scale.
- Chain re-ingestion and analytics do not degrade transactional latency.
- Immutable artifacts support reproducibility and audit.
- Redis keeps interactive latency low without becoming a system of record.

### Negative

- Four systems to operate, monitor, back up and secure.
- Cross-store consistency is eventual; projections can lag.
- More skills and failure modes.
- Backup/restore is more complex; gate G8 is essential.

### Mitigations

- Docker Compose reference topology and documented runbooks.
- Health checks, dashboards and alerts per store.
- Rebuild scripts for ClickHouse and read models.
- Restore drills quarterly (v0.1) and monthly (v1.0).
- Keep data ownership explicit; no dual writes outside the outbox pattern.

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| PostgreSQL only | Chain scan volume and compression are a poor fit; large objects bloat the DB |
| ClickHouse for everything | Weak transactions, no relational integrity for business state |
| MongoDB/document store | Schema drift, weaker relational and RLS story |
| Data lake + query engine only | No low-latency transactional control plane |
| Kafka as system of record | Operational overhead; not a query store |
| S3-only with metadata in files | No concurrency, permissions or transactions |

## Evolution triggers

- ClickHouse single-node capacity exceeded → cluster/sharding.
- Object storage > 10 TB or multi-region → managed S3 with replication.
- PostgreSQL write contention → read replicas or module split.
- Event volume > outbox/Redis capacity → Kafka (see EVENT_ARCHITECTURE).
- Multi-tenant SaaS → per-region data residency and stronger isolation.

## References

- [DATABASE_DESIGN](../database/DATABASE_DESIGN.md)
- [DATA_LIFECYCLE](../database/DATA_LIFECYCLE.md)
- [DEPLOYMENT_ARCHITECTURE](../architecture/DEPLOYMENT_ARCHITECTURE.md)
- [EVENT_ARCHITECTURE](../architecture/EVENT_ARCHITECTURE.md)
