# Deployment Architecture

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [ADR-001](../adr/ADR-001-MODULAR-MONOLITH.md) · [NETWORK_ISOLATION](../security/NETWORK_ISOLATION.md)

---

## 1. Deployment goals

- Run the entire platform on a single physical host with four isolated VMs.
- Keep research computation, agents and testnet signing in separate failure/trust domains.
- Start with Docker Compose; keep a clean path to a container orchestrator later.
- Make backup, restore and disaster recovery boring and tested.
- Make mainnet access structurally impossible, not just disabled.

### Non-goal

This is not a high-availability production deployment. v0.1 targets a single operator and
a single host. Availability improvements (replicas, managed databases, object storage
replication) are v1.0+ work.

---

## 2. Host and VM topology

```text
Physical host (Linux recommended)
├── VM 01 · dev        Z0 Data + Z1 Control
│   ├── web, api, scheduler, worker
│   ├── PostgreSQL, Redis, ClickHouse, MinIO
│   ├── Prometheus, Grafana, OTel Collector
│   └── optional: OpenBao (v0.5+)
│
├── VM 02 · research   Z2 Research
│   ├── runner-controller
│   ├── crypto-core
│   └── ephemeral sandbox containers (no egress)
│
├── VM 03 · agent      Z3 Agent
│   ├── agent-runtime
│   └── model-gateway (egress only to allowlisted AI endpoints)
│
└── VM 04 · testnet    Z4 Read + Z5 Sign
    ├── chain-gateway, chain-collector
    ├── testnet-gateway
    ├── test-signer (no egress)
    └── optional local Anvil / Hardhat networks
```

### Zone mapping

| Zone | VM | Trust level | Contains secrets? |
| --- | --- | --- | --- |
| Z0 Data | 01 | Highest data sensitivity | DB credentials, encryption keys |
| Z1 Control | 01 | High | API signing keys, service tokens |
| Z2 Research | 02 | Medium (untrusted workloads) | No DB/Redis credentials |
| Z3 Agent | 03 | Low (untrusted output) | AI provider keys only in model gateway |
| Z4 Testnet read | 04 | Medium | RPC credentials, DB insert role |
| Z5 Testnet sign | 04 | Critical | Test wallet keys in signer only |

`test-signer` is a separate container on VM 04 with no network route. For stronger isolation,
move it to a dedicated mini-PC or HSM-backed signer in v1.0. The gateway-to-signer channel
uses a Unix socket or loopback mTLS with a pinned client certificate.

### Development on Windows/macOS

Docker Desktop provides **logical** network separation only; containers share a host kernel
and the operator can reach all networks. Therefore:

- Day-to-day development MAY run the full stack on one machine.
- Gates G1, G5 and G6 (mainnet denial, agent key isolation, sandbox/network isolation)
  MUST run on the four-VM Linux topology or an equivalent isolated environment.
- The console and docs MUST NOT claim isolation guarantees from a single-host dev setup.

---

## 3. Network plan

| Network | Members | Ingress | Egress |
| --- | --- | --- | --- |
| `vl-data` | PostgreSQL, ClickHouse, Redis, secret store | From Z1, Z4 (scoped roles) | None |
| `vl-object` | MinIO | Presigned access from Z1, Z2, Z3, Z4 | None |
| `vl-observability` | OTel Collector, Prometheus, Grafana | Metrics/logs from all zones; admin UI | None |
| `vl-control` | web, api, scheduler, worker | 443 from LAN | Package mirror; AI not allowed |
| `vl-research` | runner-controller, crypto-core, sandboxes | From API (mTLS) | None at runtime |
| `vl-agent` | agent-runtime, model-gateway | From API (mTLS) | AI providers via egress proxy |
| `vl-testnet-read` | chain-gateway, collector | From Z1 for queries | Allowlisted testnet RPC |
| `vl-testnet-sign` | testnet-gateway, signer | From API (mTLS) | Gateway only; signer none |

Rules:

- `vl-research`, `vl-agent` and `vl-testnet-*` have **no route to each other**.
- The agent network cannot resolve or route to RPC hostnames.
- The research network cannot resolve AI provider hostnames.
- The signer network has no default gateway.
- MinIO is isolated on `vl-object`: DB/Redis are **not** reachable from Z2/Z3, but presigned
  object URLs are. Presigned URLs are scoped, short-lived and path-bound.
- Outbound internet goes through an egress proxy with an explicit SNI/host allowlist.
- DNS is resolved by the proxy/gateway, not by workloads, to prevent DNS rebinding.

The full matrix and firewall implementation are in
[NETWORK_ISOLATION.md](../security/NETWORK_ISOLATION.md).

---

## 4. Compose structure

```text
infrastructure/docker/
├── compose.base.yml          # networks, volumes, common env, logging
├── compose.dev.yml           # Z0 + Z1, hot reload, seed data
├── compose.research.yml      # Z2 runner + crypto-core
├── compose.agent.yml         # Z3 agent-runtime + model-gateway
├── compose.testnet.yml       # Z4 + Z5 gateways, collector, signer
├── compose.observability.yml # Prometheus, Grafana, OTel
└── compose.ci.yml            # ephemeral test stack, no external egress
```

Usage:

```bash
# Development (single host, logical isolation)
docker compose -f compose.base.yml -f compose.dev.yml up -d

# Research VM
docker compose -f compose.base.yml -f compose.research.yml up -d

# Agent VM
docker compose -f compose.base.yml -f compose.agent.yml up -d

# Testnet VM
docker compose -f compose.base.yml -f compose.testnet.yml up -d

# Full reference topology (four hosts, external compose projects)
make up-reference
```

Compose projects on different VMs are joined by mTLS service endpoints, not by a shared
Docker network. A shared network across VMs would defeat zone isolation.

---

## 5. Service ports

| Service | Port | Exposure |
| --- | --- | --- |
| `web` | 80/443 | LAN / reverse proxy |
| `api` | 8000 | LAN via web proxy; internal mTLS |
| `postgres` | 5432 | `vl-data` only |
| `redis` | 6379 | `vl-data` only |
| `clickhouse` | 8123 (HTTP), 9000 (native) | `vl-data` only |
| `minio` | 9100 (S3), 9101 (console) | `vl-object`; console admin only |
| `prometheus` | 9090 | `vl-data` / admin |
| `grafana` | 3000 | LAN admin |
| `otel-collector` | 4317 (gRPC), 4318 (HTTP) | Internal |
| `runner-controller` | 8700 | `vl-research`, API only |
| `crypto-core` | 50051 | Research loopback/private |
| `agent-runtime` | 8710 | `vl-agent`, API only |
| `model-gateway` | 8800 | `vl-agent`, agent runtime only |
| `chain-gateway` | 8600 | `vl-testnet-read`, collector/API |
| `testnet-gateway` | 8601 | `vl-testnet-sign`, API only |
| `test-signer` | 8602 | Loopback/Unix socket only |

MinIO uses 9100/9101 because ClickHouse reserves 9000 for native protocol.

---

## 6. Resource allocation

Do not hard-code CPU/RAM/GPU in the repository. Size after measuring the host.

| VM | Priority | Baseline guidance |
| --- | --- | --- |
| Dev | CPU, RAM, disk | 8–12 vCPU, 32–48 GB RAM, 1 TB NVMe |
| Research | CPU, RAM, optional GPU | 8–16 vCPU, 32–64 GB RAM, GPU exclusive |
| Agent | CPU, RAM | 4–8 vCPU, 16–24 GB RAM |
| Testnet | CPU, RAM, disk | 4–8 vCPU, 16–24 GB RAM, 500 GB |

Rules:

- A GPU is assigned to **one** workload class at a time. Never let agent traffic and
  benchmark runs contend for the same GPU.
- Research sandboxes are capped per run and globally to prevent a single circuit from
  exhausting the VM.
- ClickHouse memory is bounded; it must not compete with PostgreSQL for page cache.
- Reserve 20% headroom on each VM for the OS, container runtime and observability.

---

## 7. Storage layout

| Store | Content | Volume | Backup |
| --- | --- | --- | --- |
| PostgreSQL | Business metadata, jobs, audit, outbox | `pgdata` | Nightly dump + WAL (v1.0) |
| ClickHouse | Chain facts, aggregates | `chdata` | `BACKUP` to MinIO nightly |
| MinIO | Raw sources, artifacts, datasets, reports, plugins | `miniodata` | Versioning + replication/offsite |
| Redis | Cache, queues, locks | `redisdata` | AOF for queue durability; not a source of truth |
| Prometheus | Metrics | `promdata` | 30-day local retention |

MinIO buckets:

```text
veillab-raw-sources/     # immutable fetched snapshots
veillab-chain-raw/       # gzipped block/receipt JSON
veillab-artifacts/       # experiment outputs, content-addressed
veillab-datasets/        # versioned datasets
veillab-reports/         # published report bundles
veillab-plugins/         # signed plugin bundles
veillab-backups/         # database backups
```

Bucket policies: no public access; versioning enabled; object lock/retention for
`artifacts`, `reports` and `datasets`; lifecycle rules per
[DATA_LIFECYCLE.md](../database/DATA_LIFECYCLE.md).

---

## 8. Bootstrap order

1. Create networks and volumes.
2. Start PostgreSQL, Redis, ClickHouse, MinIO; wait for health checks.
3. Run migrations (`alembic upgrade head`) as a one-shot job with the migration role.
4. Seed chain registry, roles, permissions and the local test network.
5. Start API, scheduler, worker.
6. Start observability stack.
7. Start runner-controller, crypto-core and verify lease connectivity.
8. Start agent-runtime and model-gateway; verify provider health with a no-op request.
9. Start chain-gateway, collector, testnet-gateway, signer; verify chain-ID pinning and
   signer isolation before enabling transaction execution.
10. Enable VeilGuard policies. Transaction execution remains disabled until G1/G5 pass.

The bootstrap MUST fail closed: if the chain registry cannot be validated, no chain
gateway starts; if the signer cannot attest its key scope, no transaction gateway starts.

---

## 9. Secrets injection

| Secret | Holder | Injection |
| --- | --- | --- |
| PostgreSQL credentials | api, worker, collector | Docker secret / env from secret file |
| Redis password | api, worker, scheduler | Docker secret |
| MinIO keys | api, worker, runner (scoped) | Short-lived credentials or scoped keys |
| AI provider keys | model-gateway only | Secret store, never env of agent |
| RPC URLs/keys | chain-gateway only | Secret file, validated against registry |
| Test wallet keys | test-signer only | Encrypted keystore, passphrase from secret store |
| Session signing key | api | Secret file, rotated quarterly |
| Service mTLS keys | each service | Per-service cert, short-lived |

Rules:

- No secret is baked into an image, committed to git, or stored in PostgreSQL plaintext.
- Secrets MUST NOT appear in logs, traces, agent context or error messages.
- The API stores only `secret_ref` metadata (provider, path, purpose, rotation date).
- Rotation is a documented procedure with overlap windows; see
  [SECURITY_ARCHITECTURE.md](../security/SECURITY_ARCHITECTURE.md).

---

## 10. Observability

```text
services → OTel SDK → OTel Collector → Prometheus (metrics)
                                     → Tempo/Loki (traces/logs, optional)
                                     → Grafana
```

Minimum dashboards:

- API latency/error rate, auth failures, policy denials.
- Queue depth, job age, retry rate, DLQ count.
- Runner leases, sandbox failures, proof/verification durations.
- Chain lag per network, RPC error rate, reorg count.
- VeilGuard: requests, simulations, approvals, signatures, broadcasts, daily limits.
- Model gateway: requests, tokens, cost, provider health.
- Storage: PostgreSQL connections/locks, ClickHouse merges, MinIO capacity.

Alerts (v0.1):

| Alert | Condition | Severity |
| --- | --- | --- |
| Mainnet attempt | any denylisted chain ID or RPC host | SEV1 |
| Signer isolation breach | signer egress or unexpected client | SEV1 |
| Agent secret access | capability/tool denial spike | SEV1 |
| Chain lag | > 5 minutes for 10 minutes | SEV2 |
| Queue backlog | oldest job > 30 minutes | SEV2 |
| PostgreSQL disk | > 80% | SEV2 |
| Backup failure | nightly job failed | SEV2 |
| Model cost | > 80% monthly budget | SEV3 |

---

## 11. Backup and restore

### Backup

- PostgreSQL: nightly `pg_dump` (custom format) to MinIO, encrypted; WAL archiving in v1.0.
- ClickHouse: nightly `BACKUP DATABASE chain TO Disk('backups', ...)`.
- MinIO: versioning + cross-volume/offsite copy; object lock protects artifacts.
- Configuration: `configs/` and Compose files are in git; secrets are backed up separately
  in the secret store with a documented recovery key procedure.
- Backups are encrypted with a key not stored on the same host.

### Restore drill

Quarterly (v0.1), monthly (v1.0):

1. Provision a clean VM.
2. Restore the latest PostgreSQL dump and MinIO metadata.
3. Verify row counts, latest audit hash, random artifact hashes.
4. Restore ClickHouse and verify chain head/cursor consistency.
5. Start API in read-only mode and run smoke tests.
6. Record RTO/RPO actuals and attach evidence to the gate report (G8).

A backup that has not been restored is not a backup.

---

## 12. Upgrade and rollback

- Images are immutable and digest-pinned. `latest` is forbidden in deployment.
- Database migrations are expand/contract; API deploy order is migrate → canary → full.
- Plugin upgrades are digest-pinned and can be rolled back to the previous version.
- Experiment definitions pin toolchain image digests; upgrading a toolchain creates a new
  adapter version and does not silently change historical results.
- Rollback of a migration requires a tested down-path or restore; destructive migrations
  are not allowed without a backup and an ADR.

---

## 13. Disaster recovery

| Scenario | Recovery |
| --- | --- |
| Dev VM loss | Rebuild from Compose + restore PostgreSQL/MinIO; RTO 8 h |
| Research VM loss | Rebuild; in-flight runs fail and are requeued |
| Agent VM loss | Rebuild; no data loss beyond task context |
| Testnet VM loss | Rebuild; signer keys restored from encrypted backup; rotate if compromise suspected |
| Host loss | Restore to new hardware from offsite backups; RTO 24 h |
| Ransomware/compromise | Isolate host, revoke all credentials, restore from immutable backup, rotate keys |

Test wallet keys are disposable by policy, but their compromise still requires rotation and
an incident report. There are no mainnet keys to recover.
