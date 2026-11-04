# Development Roadmap

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [RELEASE_PLAN](RELEASE_PLAN.md) · [ACCEPTANCE_CRITERIA](ACCEPTANCE_CRITERIA.md)

---

## 1. Planning assumptions

| Assumption | Value |
| --- | --- |
| Staffing | 1 lead engineer + AI coding assistance; part-time security review |
| Working mode | Design-first, vertical slices, gates before features |
| Host | 1 physical host, 4 VMs (Dev, Research, Agent, Testnet) |
| Calendar | 24 weeks to v1.0-rc; GA after a 4-week soak and all gates green |
| Scope rule | If time is short, reduce scope, never skip a security gate |
| Estimate type | Order-of-magnitude, not a commitment |

The 24-week plan is aggressive for the breadth of the platform. It is achievable only if:

- cryptography integrations are limited to a small, well-understood set per phase,
- AI assistance is used for scaffolding/tests/docs, not for unreviewed security code,
- testnet infrastructure is available early,
- gates are automated from P0 rather than retrofitted.

---

## 2. Phase overview

| Phase | Weeks | Focus | Exit gate |
| --- | --- | --- | --- |
| P0 | 1–2 | Repository, architecture, security boundaries, skeleton | G0 (partial) |
| P1 | 3–4 | Data, identity, jobs, events, chain adapters, network policy | G0, G1, G2 (partial) |
| P2 | 5–6 | Protocol Observatory | G2, Observatory acceptance |
| P3 | 7–10 | Cryptography Studio and runner | G3 |
| P4 | 11–13 | Research Engine and reproducibility | G4 |
| P5 | 14–16 | AI Research Team | G5 |
| P6 | 17–19 | Security Center + advanced crypto | G7 (partial) |
| P7 | 20–22 | Privacy products, benchmark center, plugins | G4, G7 |
| P8 | 23–24 | VeilGuard, integration, hardening, v1.0-rc | G1, G5, G6, G8 |

Release mapping:

- **v0.1 Research Foundation** at end of P5 (week 16).
- **v0.5 Advanced Research** at end of P7 (week 22).
- **v1.0-rc** at end of P8 (week 24); **GA** after soak and gate sign-off.

---

## 3. P0 · Foundations (weeks 1–2)

### Deliverables

- [ ] Freeze principles and scope in `docs/00_PROJECT_VISION.md`.
- [ ] Architecture, module boundaries, data flow, deployment, event, plugin docs.
- [ ] Security architecture, threat model, network isolation, testnet policy, agent model,
      incident response.
- [ ] Database design, ERD, data lifecycle.
- [ ] API conventions, endpoint baseline, event schema.
- [ ] Experiment, benchmark, reproducibility specs.
- [ ] ADR-001…005.
- [ ] Monorepo skeleton: `apps/`, `packages/`, `core/`, `infrastructure/`, `tests/`.
- [ ] Python/Node/Rust toolchains with lockfiles.
- [ ] CI: lint, typecheck, unit tests, secret scan, dependency scan, docs links.
- [ ] Docker Compose base + dev + observability.
- [ ] Network policy skeleton and `configs/chains.yaml` with deny-by-default validation.
- [ ] Threat model review #1.

### Exit criteria

- A new contributor can read the docs and understand the trust boundaries.
- `docker compose up` starts empty services (web/api/db/redis/minio/clickhouse).
- CI runs on a trivial PR and fails on a committed secret.
- G0 partial: services start, health checks pass, no secret in repo.

### Risks

- Over-designing before code. Mitigation: vertical slices start in P1.
- Docker Desktop isolation is weaker than the target. Mitigation: gates run on the VM topology.

---

## 4. P1 · Core platform and chains (weeks 3–4)

### Deliverables

- [ ] PostgreSQL schemas + Alembic migrations + roles/grants + RLS on tenant tables.
- [ ] Identity: local auth, sessions, PATs, workspaces, projects, memberships, RBAC.
- [ ] Capability grant model and token issuance (used by jobs/agents later).
- [ ] Job manager with leases, retries, cancellation, idempotency.
- [ ] Outbox + relay + consumer inbox + DLQ.
- [ ] Audit log with hash chain and daily anchor job.
- [ ] Chain registry + validation + chain-gateway + collector.
- [ ] Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia collectors (read).
- [ ] Local Anvil network + faucet script.
- [ ] Network policy: zones, mTLS skeleton, egress proxy, negative tests.
- [ ] Observability: metrics, logs, traces, dashboards for API/queues/chains.
- [ ] First API endpoints: auth, projects, health, chains.

### Exit criteria

- G0: services start with correct permissions; cross-tenant tests fail closed.
- G1 partial: mainnet chain IDs/hosts rejected; gateway method allowlist works.
- G2 partial: three testnets ingest blocks with reorg handling and cursor recovery.
- A block can be traced from RPC → raw object → ClickHouse → API.

### Risks

- Testnet RPC rate limits. Mitigation: provider allowlist, caching, backoff.
- Reorg edge cases. Mitigation: raw retention, parent-hash checks, replay tests.

---

## 5. P2 · Protocol Observatory (weeks 5–6)

### Deliverables

- [ ] Source adapters: GitHub releases/commits, arXiv metadata, official docs pages.
- [ ] Egress proxy allowlist for source hosts; fetch size/time limits.
- [ ] Raw snapshot storage in MinIO with content hashes.
- [ ] Normalizer and protocol draft model.
- [ ] Registry: protocols, versions, profiles, sources, dependencies, audits.
- [ ] Review/publish workflow (human approval).
- [ ] Search/list/detail UI (read-only first).
- [ ] `protocol.discovered/updated/version.published` events.

### Exit criteria

- Given a protocol name/repo, the system creates a draft with sources, versions and a
  technical summary, without auto-publishing.
- A reviewer can publish a version with frozen source hashes.
- Re-running discovery is idempotent and produces a diff, not duplicates.
- No arbitrary URL fetch; only registry/allowlisted sources.

### Risks

- Scraping fragility and terms of service. Mitigation: official APIs, rate limits, robots/
  terms review, cached snapshots.
- Prompt injection in fetched content. Mitigation: content is data; no auto tool use.

---

## 6. P3 · Cryptography Studio (weeks 7–10)

### Deliverables

- [ ] `cryptography/interfaces` + adapter registry + conformance tests.
- [ ] Rust `crypto-core` for hashing/Merkle/commitments (gRPC, no network).
- [ ] `runner-controller` with lease/heartbeat/complete and sandbox launcher.
- [ ] Sandbox: rootless, no network, read-only root, limits, output hashing.
- [ ] Circom adapter: compile, prove, verify, benchmark.
- [ ] Noir adapter: compile, prove, verify, benchmark.
- [ ] SnarkJS/Noir verifier integration, pinned versions.
- [ ] Circuit registry, builds, proof runs, artifact storage.
- [ ] Benchmark harness per [BENCHMARK_SPEC](../research/BENCHMARK_SPEC.md).
- [ ] Experiment composer UI for circuits and benchmarks.
- [ ] Negative tests: invalid proof, hash mismatch, timeout, network attempt.

### Exit criteria

- G3: compile → prove → verify succeeds for Circom and Noir fixtures; invalid proofs fail;
  artifacts are hashed and reproducible.
- A benchmark records environment fingerprint and raw samples.
- Sandbox cannot reach network or host; a network attempt is detected.
- A runner crash is recovered without duplicate results.

### Risks

- Toolchain versions and WASM/zkey compatibility. Mitigation: pinned images and golden
  fixtures.
- GPU drivers unavailable. Mitigation: CPU-first benchmarks; GPU optional.

---

## 7. P4 · Research Engine (weeks 11–13)

### Deliverables

- [ ] Studies, experiments, versions, runs, manifests.
- [ ] Validation pipeline and quotas.
- [ ] Deterministic verifier framework and verifier registry.
- [ ] Datasets: versions, upload sessions, hash verification, download.
- [ ] Reports: drafts, evidence graph, review, publication.
- [ ] Reproducibility bundle export and import.
- [ ] Reproduction runs and comparison.
- [ ] Research UI: experiment detail, run timeline, artifacts, manifest, verification.
- [ ] Events for experiment lifecycle, dataset, report, benchmark.

### Exit criteria

- G4: three experiments across two frameworks reproduced on a clean VM; tamper detection
  works; R2 recorded.
- A published report cannot exist without evidence and review.
- Dataset versions are immutable and hash-verified on upload.
- Every completed run has a manifest and verifier record.

### Risks

- Scope creep in report authoring. Mitigation: start with structured sections + evidence
  links, not a full editor.
- Storage growth. Mitigation: quotas, retention, cold archive.

---

## 8. P5 · AI Research Team (weeks 14–16)

### Deliverables

- [ ] Model gateway: providers, base URLs, secret refs, routing, health, metering, cost.
- [ ] Agent runtime in Z3 with no DB/RPC route.
- [ ] Capability issuance, tool gateway, quotas, revocation, kill switch.
- [ ] Tools: research search, protocol get/propose, source fetch/analyze, experiment
      create/status, dataset read, artifact put, benchmark plan, report draft.
- [ ] Agents: discovery, code analysis, crypto research, benchmark, report.
- [ ] Prompt-injection eval suite and provenance labeling.
- [ ] Agent UI: roster, tasks, steps, tool calls, model usage.
- [ ] Human review for publish/deploy/execute.

### Exit criteria

- G5: agent cannot read keys, reach signer/RPC/DB, mint tokens or escalate capabilities.
- A prompt-injection fixture cannot trigger a privileged tool call.
- Model keys exist only in the model gateway; logs are redacted.
- A full research task runs from discovery to a draft report with evidence links.
- v0.1 gate set G0–G6 is green (G1 write-path tests assert absence until P8).

### Risks

- Model/provider instability. Mitigation: routing/fallback, health checks, local model option.
- Cost overrun. Mitigation: per-task budgets and alerts.
- Over-broad capabilities. Mitigation: narrow defaults and review.

---

## 9. P6 · Security Center and advanced crypto (weeks 17–19)

### Deliverables

- [ ] Static analysis adapter (Semgrep/Slither), dependency scanner, permission analyzer.
- [ ] Foundry test runner and Echidna/Medusa fuzz adapter (sandboxed).
- [ ] Threat model registry and finding workflow with evidence/reproduction.
- [ ] Security report templates and disclosure states.
- [ ] zkVM adapter spike (SP1 or RISC Zero) with benchmark.
- [ ] FHE adapter spike (OpenFHE) with a bounded workload.
- [ ] MPC adapter spike (MP-SPDZ) with a local multi-process run.
- [ ] Security UI: assessments, findings, severity, evidence.

### Exit criteria

- A known vulnerable fixture is detected and reproduced with evidence.
- A finding cannot be marked verified without reproduction.
- zkVM/FHE/MPC spikes produce verified outputs and environment fingerprints (not production-
  grade, but measurable).
- G7 partial: SAST/dependency/container scans pass with no criticals.

### Risks

- Tool false positives/negatives. Mitigation: multiple tools, manual review, fixtures.
- FHE/MPC resource cost. Mitigation: small parameter sets, dedicated queue, timeouts.
- Scope explosion. Mitigation: one representative workload per framework.

---

## 10. P7 · Privacy products, benchmarks, plugins (weeks 20–22)

### Deliverables

- [ ] Private Identity prototype: Semaphore membership, commitments, Merkle tree, nullifier.
- [ ] Selective disclosure prototype: predicate proof over a test credential.
- [ ] Benchmark Center: comparability groups, raw samples, export.
- [ ] Plugin system: manifest, signature, scan, install/enable, isolated runtime.
- [ ] At least one third-party-style plugin (e.g. a simple security tool) installed through
      the full lifecycle.
- [ ] Privacy UI: credentials, trees, proofs, verification.
- [ ] Documentation for adding a chain/crypto/security/data plugin.

### Exit criteria

- End-to-end: issue credential → add to tree → generate membership proof → verify on local
  chain → record evidence.
- A plugin cannot access network/secrets/database and is quarantined on violation.
- Benchmark UI refuses cross-fingerprint rankings without a label.
- G4 re-run passes for benchmark results.

### Risks

- ZK circuit complexity and proving time. Mitigation: small tree depth for the demo, scale
  later.
- Plugin security. Mitigation: isolated worker only, permission review, gVisor for high risk.

---

## 11. P8 · VeilGuard and release (weeks 23–24)

### Deliverables

- [ ] Wallet registry (research/deployment/simulation), key refs only.
- [ ] Isolated signer with encrypted keystore, no egress, pinned gateway client.
- [ ] Policy engine: chain, contract, selector, value, gas, daily limits, approval.
- [ ] Simulation: `eth_call`, estimate gas, state diff where supported.
- [ ] Approval workflow and one-time tokens.
- [ ] Testnet gateway: recheck, sign, broadcast, reconcile.
- [ ] Faucet tracker, daily usage, kill switch.
- [ ] VeilGuard UI: wallets, policies, requests, approvals, transactions.
- [ ] Full gate run G0–G8 on the four-VM topology.
- [ ] v1.0-rc docs, release notes, SBOM, signed images, backup/restore drill.

### Exit criteria

- G1: mainnet denial tests pass on the reference topology.
- G5: agent cannot reach signer, keys or mainnet; capability tests pass.
- G6: sandbox escape/network isolation tests pass; kill switch works.
- G8: restore drill meets RTO/RPO.
- A testnet transaction goes through simulation → approval → signature → broadcast →
  confirmation with full audit.
- No critical security findings open.

### Risks

- Last-phase integration surprises. Mitigation: build VeilGuard policy/simulation earlier as
  a stub in P1; keep the signer interface stable.
- Gate failures. Mitigation: freeze features two weeks before P8 end; fix gates only.

---

## 12. Cross-phase engineering standards

- Every feature has an acceptance test and a doc update in the same PR.
- Every external destination is added to network policy + tests.
- Every secret has a secret ref + rotation note.
- Every long-running action is a job with a trace ID.
- Every state machine has transition tests.
- Every migration is tested on an empty DB and a previous-release snapshot.
- No `latest` image tags, no floating dependencies.
- Security-sensitive PRs require a second review when available.

---

## 13. Top risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Scope exceeds 24 weeks | High | Medium | Cut features, keep gates; release v0.5 rather than unsafe v1.0 |
| Crypto toolchain instability | High | Medium | Pin images, golden fixtures, adapter isolation |
| Security gate failure late | Medium | High | Automate gates from P0; freeze before P8 |
| Testnet RPC instability | Medium | Medium | Multiple providers, backoff, raw retention |
| GPU unavailable | Medium | Low | CPU-first benchmarks; GPU optional |
| Single-person bus factor | Medium | High | Docs, runbooks, reproducible builds |
| Agent prompt injection | High | Medium | Capability model, approval, egress controls |
| Data volume exceeds disk | Medium | Medium | Retention, sampling, cold storage |
| AI provider policy change | Medium | Low | Provider abstraction, local model fallback |

---

## 14. What not to do

- Do not add a mainnet path "temporarily".
- Do not let agents hold keys "for testing".
- Do not skip G1/G5 to hit a date.
- Do not build all six planes before the research loop works.
- Do not add Kafka, Kubernetes or a service mesh before metrics justify it.
- Do not claim reproducibility without an independent run.
- Do not publish a benchmark without a verified proof and environment fingerprint.
