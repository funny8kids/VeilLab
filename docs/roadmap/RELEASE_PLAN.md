# Release Plan

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md) · [ACCEPTANCE_CRITERIA](ACCEPTANCE_CRITERIA.md)

---

## 1. Release philosophy

- **Gates over dates.** A release ships when its gates pass, not when the calendar says so.
- **Scope is negotiable; safety is not.** Cut features before cutting G1 or G5.
- **Every release is reproducible.** Signed images, SBOM, lockfiles, migrations, changelog.
- **Every release is reversible.** Rollback or restore is tested before shipping.

---

## 2. Versioning

| Artifact | Scheme | Notes |
| --- | --- | --- |
| Platform | SemVer `MAJOR.MINOR.PATCH` | Major = breaking API/plugin/event contract |
| API | URL major `/api/v1` | Breaking change → `/api/v2` |
| Event schema | `.vN` suffix | Additive within major |
| Plugin API | `api_version` integer | Host supports N and N-1 |
| Database | Migration revision IDs | Forward-only; expand/contract |
| Adapter/verifier | Independent SemVer | Historical runs pin versions |

Pre-release suffixes: `-alpha.N`, `-beta.N`, `-rc.N`. `latest` is never a deployable tag.

---

## 3. Release calendar (target)

| Release | Target | Content | Gate requirement |
| --- | --- | --- | --- |
| `v0.1-alpha` | Week 8 | Platform skeleton + first chain ingest + Circom spike | G0, G1 partial, G2 partial |
| `v0.1` | Week 16 | Research Foundation: Observatory, Chain, Crypto, Research, Agents | G0–G6 (G1 write-path N/A; G7 partial) |
| `v0.5` | Week 22 | Advanced crypto, Security Center, privacy prototypes, plugins | G0–G7 |
| `v1.0-rc` | Week 24 | VeilGuard, full integration, hardening | G0–G8 |
| `v1.0` | Week 28 | GA after 4-week soak and external review | All gates + soak |

Dates are targets for a single lead + AI assistance. A slip is expected if a gate fails; the
response is to fix the gate, not to relabel the release.

---

## 4. v0.1 · Research Foundation

### Goal

Close the research loop: discover a protocol, build a profile, run an experiment, verify it,
and publish an evidence-backed report.

### Must have

| Area | Scope |
| --- | --- |
| Control Center | Local auth, users, workspaces, projects, RBAC, audit |
| Jobs/events | Durable jobs, outbox, at-least-once events, DLQ |
| Observatory | GitHub/arXiv/docs discovery, protocol registry, review/publish |
| Chain Intelligence | Ethereum Sepolia, Base Sepolia, Arbitrum Sepolia; local Anvil; reorg handling |
| Cryptography | Circom + Noir adapters, runner sandbox, proof verify, benchmark |
| Research Engine | Studies, experiments, runs, datasets, manifests, reports, R2 reproduction |
| Agents | Discovery, code analysis, benchmark, report agents; capability tokens; model gateway |
| Security | Testnet policy, network isolation, agent isolation, audit |

### Should have

- Optimism Sepolia and Polygon Amoy read-only.
- Benchmark Center basic comparison.
- Plugin framework skeleton (no third-party install).

### Out of scope

- VeilGuard transaction execution.
- FHE/MPC/zkVM adapters.
- Private identity product.
- Multi-user OIDC.

### Exit criteria

- G0–G6 pass (G1 write-path tests are absence/fail-closed until VeilGuard lands; G7 is partial).
- A researcher can complete the loop on a clean deployment using docs.
- No mainnet path, no agent key access.

---

## 5. v0.5 · Advanced Research

### Goal

Build technical differentiation and a safe extension model.

### Must have

| Area | Scope |
| --- | --- |
| Advanced crypto | zkVM spike (SP1 or RISC Zero), OpenFHE spike, MP-SPDZ spike |
| Security Center | Static analysis, dependency scan, permission analysis, Foundry/Echidna fixture |
| Benchmark Center | Comparability groups, raw samples, environment fingerprints, export |
| Plugin System | Manifest, signature, scan, install/enable, isolated runtime, one real plugin |
| Agent Team | Multi-agent workflows, quotas, prompt-injection eval |
| Chain Intelligence | OP Sepolia + Polygon Amoy; finality modeling per chain |
| Privacy | Semaphore membership prototype, commitments, Merkle, nullifiers |

### Exit criteria

- G0–G7 pass.
- At least one experiment from each advanced framework is verified and reproducible.
- A malicious plugin is contained and quarantined in a test.
- A security finding is reproduced with evidence and verified by a human.

### Out of scope

- Production-grade FHE/MPC performance.
- VeilGuard signing.
- Public plugin marketplace.

---

## 6. v1.0 · Privacy Research Platform

### Goal

A complete, independently operable testnet research platform with safe testnet execution.

### Must have

| Area | Scope |
| --- | --- |
| VeilGuard | Wallets, policies, simulation, approval, signer, broadcast, reconciliation, kill switch |
| Privacy Products | Private identity, selective disclosure prototype, verifiable privacy |
| Chain Intelligence | All approved testnets, state verification, reorg drills |
| Security Center | Full finding workflow, disclosure states, report templates |
| Plugin Center | Install/configure/enable/disable, permission diff, quarantine |
| AI Research Team | End-to-end research loop with human review |
| Operations | Backup/restore, monitoring, incident runbooks, signed images, SBOM |

### Exit criteria

- G0–G8 pass on the four-VM reference topology.
- A testnet transaction completes simulation → approval → signature → broadcast →
  confirmation with audit.
- An independent reviewer reproduces a published result (R2).
- Restore drill meets RTO 8h / RPO 24h.
- No open critical/high security findings without an accepted, time-bound risk.

### GA conditions

- 4-week soak with no SEV1/SEV2 incidents.
- External security review or penetration test completed (scope agreed).
- Documentation and runbooks reviewed by someone other than the author.
- Backup restore repeated on fresh hardware.
- All accepted risks have an owner and expiry.

---

## 7. Release process

```text
1. Feature freeze (T-10 business days)
2. Gate run on reference topology
3. Migration dry-run (empty DB + previous release snapshot)
4. Backup + restore drill (G8)
5. Security scan + SBOM + image signing
6. Release candidate deploy to staging
7. 72-hour soak + smoke tests
8. Sign-off (engineering + security)
9. Tag, publish images, changelog, docs
10. Production deploy with rollback plan
11. Post-release monitoring (7 days)
```

### Freeze rules

- Only gate fixes, docs, and release-blocking bugs after freeze.
- No schema changes except those required for a gate fix, with a migration review.
- No new external destinations.
- No new agent capabilities.

---

## 8. Release artifacts

| Artifact | Required |
| --- | --- |
| Container images | Digest-pinned, signed (cosign) |
| SBOM | CycloneDX per image |
| Source tag | Signed git tag |
| Changelog | Human-readable, categorized |
| Migration plan | Forward + rollback/restore |
| Gate report | G0–G8 evidence links |
| Threat model diff | Updated for new boundaries |
| Docs | Updated architecture/API/runbooks |
| Backup | Pre-release backup verified |
| Known issues | With severity and workaround |

---

## 9. Compatibility and deprecation

- API: additive changes within v1; breaking changes require v2 and 90 days notice.
- Events: additive within `.vN`; breaking changes require `.v(N+1)` and dual-publish ≥ 30 days.
- Plugins: host supports current and previous `api_version`; 90 days deprecation notice.
- Adapters: pinned by digest; deprecation documented; historical runs remain reproducible.
- Database: expand/contract; destructive migrations require an ADR and backup.

---

## 10. Rollback

| Scenario | Action |
| --- | --- |
| API regression | Redeploy previous image; migrations are backward-compatible |
| Bad migration | Restore from pre-release backup; do not run ad-hoc down migrations |
| Plugin regression | Disable/quarantine; previous version remains installed |
| Model provider outage | Route to fallback; disable provider |
| Chain gateway regression | Disable writes; keep reads or pause sync |
| Signer regression | Kill switch; no alternate signer |

Rollback is rehearsed during the release candidate deploy.

---

## 11. Communication

- Internal: release notes + gate report + known issues.
- Users: changelog, breaking changes, migration steps, testnet-only reminder.
- Security: coordinated disclosure for findings; no exploit details before fix.
- Incidents: follow [INCIDENT_RESPONSE](../security/INCIDENT_RESPONSE.md).

---

## 12. Post-release

- 7-day monitoring window with heightened alerts.
- Review queue latency, error rate, cost, chain lag, policy denials.
- Collect reproduction attempts and failures.
- Open follow-up issues with owners.
- Update roadmap based on actuals, not estimates.
- Schedule the next restore drill and access review.
