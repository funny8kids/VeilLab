# Acceptance Criteria and Gates

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md) · [THREAT_MODEL](../security/THREAT_MODEL.md)

---

## 1. Purpose

Gates are automated, evidence-producing acceptance conditions. A release is blocked if any
required gate is red. A gate is not "passed" because a human believes it; it passes when the
test suite runs on the reference topology and the evidence is attached.

**G1 (mainnet denial) and G5 (agent key isolation) are the two most important gates.** They
cannot be waived.

---

## 2. Gate summary

| Gate | Condition | Phase | Release blocker |
| --- | --- | --- | --- |
| G0 | Services start, auth/permissions/tenant isolation work | P0–P1 | Yes |
| G1 | Mainnet access is impossible; testnet allowlist works | P1 | Yes |
| G2 | Chain collection and reorg recovery work | P1–P2 | Yes |
| G3 | ZK compile/prove/verify works and invalid proofs fail | P3 | Yes |
| G4 | Experiments reproduce independently (R2) | P4 | Yes |
| G5 | Agents cannot access keys, signer, RPC or escalate | P5 | Yes |
| G6 | Sandbox and network isolation hold; kill switch works | P3/P8 | Yes |
| G7 | Security scans and dependency checks pass | P6–P7 | Yes |
| G8 | Backup and restore meet RTO/RPO | P8 | Yes |

---

## 3. G0 · Platform and tenancy

**Condition:** All services start with correct permissions; authentication, authorization and
tenant isolation behave as specified.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G0-01 | `docker compose up` on clean volumes | All health checks pass |
| G0-02 | Migration from empty DB | Schema + roles + RLS applied |
| G0-03 | Login with valid/invalid credentials | 200 / 401, no enumeration |
| G0-04 | Session expiry and logout | 401 after expiry/revocation |
| G0-05 | PAT scope enforcement | 403 outside scope |
| G0-06 | CSRF missing on cookie mutation | 403 |
| G0-07 | Cross-tenant object read | 404/403 + audit |
| G0-08 | Project member cannot admin workspace | 403 |
| G0-09 | Audit record for privileged action | Present, hash-chained |
| G0-10 | Service starts with invalid config | Fail closed |

**Evidence:** CI logs, migration output, auth test report, RLS test report, audit sample.

---

## 4. G1 · Mainnet denial

**Condition:** No mainnet RPC, chain ID, method, key or broadcast path is accepted anywhere.
In v0.1, tests for components that do not exist yet (wallet policy, signer, broadcast)
assert **absence/fail-closed**. They become mandatory functional tests when VeilGuard lands.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G1-01 | Registry with chain ID 1 | Schema/startup failure |
| G1-02 | Unknown chain ID | Startup failure |
| G1-03 | RPC returns wrong chain ID | Connection closed + alert |
| G1-04 | Local genesis hash mismatch | Connection closed |
| G1-05 | RPC host not allowlisted | Denied before connect |
| G1-06 | Non-TLS public RPC | Rejected |
| G1-07 | RPC redirect | Rejected |
| G1-08 | `eth_sendTransaction` via gateway | 403 |
| G1-09 | `eth_sendRawTransaction` without txgw mTLS | 403 |
| G1-10 | Agent direct RPC call | Network denied |
| G1-11 | Wallet policy chain mismatch | Denied + audit |
| G1-12 | Value above cap | Denied + audit |
| G1-13 | Failed simulation | Denied |
| G1-14 | Approval replay | Denied |
| G1-15 | Signer receives denylisted chain | Refuses |
| G1-16 | Signer receives mismatched request hash | Refuses |
| G1-17 | Source contains mainnet broadcast path | No match outside tests/docs |
| G1-18 | Config `kind: mainnet` | Schema error |
| G1-19 | Egress allowlist includes mainnet host | Deployment blocked |
| G1-20 | Registry missing finality model | Startup failure |

**Evidence:** Test logs per ID, firewall export, signer socket listing, registry validation.

**Owner:** Security + Platform. **Waiver:** none.

---

## 5. G2 · Chain collection and reorg

**Condition:** Approved testnets are collected correctly, reorgs are detected and recovered,
and data can be rebuilt from raw objects.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G2-01 | Ingest 100 blocks from each network | Cursor advances, no gaps |
| G2-02 | Parent hash mismatch | Reorg event, cursor rewind |
| G2-03 | Reorg 3 blocks deep | Orphaned rows marked, new canonical rows |
| G2-04 | RPC timeout | Retry with backoff, no duplicate facts |
| G2-05 | Duplicate block delivery | Idempotent insert |
| G2-06 | Raw object missing | Detectable, re-fetch |
| G2-07 | Rebuild ClickHouse from raw | Row counts/hashes match |
| G2-08 | Finality tag handling | Canonical selection correct |
| G2-09 | Chain ID spoof | Connection closed |
| G2-10 | Collector restart | Resumes from cursor |

**Evidence:** Ingestion report, reorg drill log, rebuild comparison, latency metrics.

---

## 6. G3 · Zero-knowledge pipeline

**Condition:** Compile, prove, verify and benchmark work for supported frameworks; invalid
proofs and tampered artifacts fail.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G3-01 | Circom compile fixture | Build artifact + constraints |
| G3-02 | Circom prove/verify | Proof valid |
| G3-03 | Noir compile/prove/verify | Proof valid |
| G3-04 | Invalid proof | Verifier rejects |
| G3-05 | Tampered proof artifact | Hash mismatch fails |
| G3-06 | Wrong public input | Verification fails |
| G3-07 | Timeout | Killed, run failed, no partial success |
| G3-08 | Run twice | Same semantic result; timing recorded |
| G3-09 | Benchmark samples | n ≥ required, raw samples retained |
| G3-10 | Environment fingerprint | Present and hashed |
| G3-11 | Network attempt in sandbox | Denied + security event |
| G3-12 | Verifier crash | `failed`, not `verified` |

**Evidence:** Run manifests, verifier outputs, benchmark records, sandbox logs.

---

## 7. G4 · Reproducibility

**Condition:** Independent parties can reproduce experiments and detect tampering.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G4-01 | Export bundle | Signature + SHA256SUMS valid |
| G4-02 | Import bundle on clean VM | Hashes verify, run starts |
| G4-03 | R2 reproduction (3 experiments, 2 frameworks) | Semantic match; timing within tolerance |
| G4-04 | Tampered artifact | Rejected before run |
| G4-05 | Missing image digest | Rejected |
| G4-06 | Different seed | Detected/failed as non-reproducible |
| G4-07 | Evidence graph | Every claim linked |
| G4-08 | Publication without review | Rejected |
| G4-09 | Reproduction on different machine (R3) | Signed attestation |
| G4-10 | Historical run after toolchain upgrade | Old result unchanged |

**Evidence:** Reproducibility bundles, attestations, comparison reports, G4 sign-off.

---

## 8. G5 · Agent isolation

**Condition:** Agents cannot access keys, signer, RPC, database, secrets or escalate
capabilities; prompt injection cannot trigger privileged actions.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G5-01 | Agent → postgres | Refused |
| G5-02 | Agent → Redis | Refused |
| G5-03 | Agent → signer | Refused |
| G5-04 | Agent → RPC | Refused |
| G5-05 | Agent → internet (non-allowlisted) | Refused |
| G5-06 | Token for `wallet.private_key.read` | Issuance denied |
| G5-07 | Tool call without capability | 403 + audit |
| G5-08 | Expired/revoked token | 401 + audit |
| G5-09 | Cross-project token | 403 + audit |
| G5-10 | Capability escalation request | Denied |
| G5-11 | Prompt-injection fixture | No privileged tool call |
| G5-12 | Approval for different payload | Rejected |
| G5-13 | Replayed approval | Rejected |
| G5-14 | Kill switch | All agent actions denied |
| G5-15 | Secret in logs/artifacts | Scanner finds none |

**Evidence:** Network test logs, capability test report, injection eval, log scan.

**Owner:** Security + AI. **Waiver:** none.

---

## 9. G6 · Sandbox and network isolation

**Condition:** Untrusted workloads cannot escape, reach the network or affect other tenants;
the runner kill switch works.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G6-01 | Sandbox → internet | Refused |
| G6-02 | Sandbox → data stores | Refused |
| G6-03 | Sandbox → signer | Refused |
| G6-04 | Privileged container attempt | Rejected |
| G6-05 | Host mount attempt | Rejected |
| G6-06 | Docker socket access | Absent |
| G6-07 | CPU/memory/PID limit | Enforced, process killed |
| G6-08 | Output size limit | Enforced |
| G6-09 | Path traversal/symlink output | Rejected |
| G6-10 | Malicious build script escape fixture | Contained |
| G6-11 | Runner kill switch | Sandboxes stopped, queued runs paused |
| G6-12 | Firewall drift | Detected and blocked |

**Evidence:** Isolation test suite, runtime config export, kill-switch timing, firewall diff.

---

## 10. G7 · Security and supply chain

**Condition:** No critical vulnerabilities; dependencies and images are pinned and scanned;
security workflows and plugin containment are enforced.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G7-01 | SAST | No unresolved high/critical |
| G7-02 | Dependency scan | No unresolved critical |
| G7-03 | Container scan | No unresolved critical |
| G7-04 | Secret scan | No secrets in repo/images |
| G7-05 | SBOM | Present for every image |
| G7-06 | Image signature | Verified |
| G7-07 | Plugin signature/scan | Enforced |
| G7-08 | Vulnerability fixture | Finding created with evidence |
| G7-09 | Finding without reproduction | Cannot be verified |
| G7-10 | Audit hash chain | Verifies |
| G7-11 | Dependency confusion | Registry allowlist enforced |
| G7-12 | Malicious plugin escape fixture | Contained and quarantined |

**Evidence:** CI reports, SBOMs, signatures, finding fixture, audit verification.

---

## 11. G8 · Backup and restore

**Condition:** Backups exist, are encrypted, and restore within RTO/RPO on a clean host.

| Test ID | Scenario | Expected |
| --- | --- | --- |
| G8-01 | Nightly PostgreSQL dump | Completes, encrypted |
| G8-02 | ClickHouse backup | Completes |
| G8-03 | MinIO versioning/offsite | Objects recoverable |
| G8-04 | Restore PostgreSQL to clean VM | Row counts + audit hash match |
| G8-05 | Restore MinIO metadata/objects | Random artifact hashes match |
| G8-06 | Restore ClickHouse | Cursor/head consistent |
| G8-07 | API read-only smoke after restore | Passes |
| G8-08 | Deleted data does not reappear | Tombstones applied |
| G8-09 | RTO/RPO measured | Within targets |
| G8-10 | Backup failure alert | Fires |

**Evidence:** Restore report with timings, hash comparisons, smoke test logs.

---

## 12. CI pipeline

```text
lint → typecheck → unit → architecture → integration (ephemeral stack) →
security (SAST/secrets/deps/containers) → migration test → gate suites (G0–G8 as applicable) →
docs link check → artifact publish
```

Rules:

- Required checks block merge.
- Gate suites run nightly on the reference topology and on release candidates.
- Flaky tests are quarantined with an owner and deadline; a quarantined gate test cannot
  count as passing.
- Test results and evidence are archived with the release.

---

## 13. Definition of Done (feature)

A feature is done when:

- [ ] Documented (architecture/API/runbook as applicable).
- [ ] Has automated tests, including a negative case.
- [ ] Enforces authorization and tenant scoping.
- [ ] Emits audit/events where required.
- [ ] Has a trace ID and metrics where long-running.
- [ ] Handles failure and retry idempotently.
- [ ] Updates threat model if a trust boundary changed.
- [ ] Updates network policy if a destination was added.
- [ ] Passes lint/type/security checks.
- [ ] Reviewed by someone other than the author when available.

---

## 14. Release blocker list

A release is blocked by any of:

- G1, G5, G6 red.
- Any unresolved critical/high security finding without an accepted, time-bound risk.
- Missing backup/restore evidence (G8).
- A mainnet path or key material anywhere.
- An agent capability that can reach keys, signer or RPC.
- A published benchmark without verified proof and fingerprint.
- An unreviewed report claiming reproducibility below R2.
- A failed migration dry-run.
- A secret in the repository or image.

---

## 15. Gate sign-off template

```text
Gate: G1
Release: v1.0-rc
Date: 2026-11-02
Environment: reference topology (4 VMs), commit <sha>
Result: PASS | FAIL
Tests: <link to report>
Evidence: <links>
Open exceptions: none | <id, owner, expiry>
Signed by: <name/role>
Notes:
```

Sign-off is stored with the release artifacts and linked from the changelog.

---

## 16. Traceability

| Threat | Gate |
| --- | --- |
| T-01 mainnet config | G1 |
| T-02 RPC spoofing | G1, G2 |
| T-03 agent mainnet | G1, G5 |
| T-04 key exfiltration | G5 |
| T-05 signer exposure | G1, G5, G6 |
| T-06 sandbox escape | G6 |
| T-07 malicious build | G6 |
| T-08 prompt injection | G5 |
| T-09 provider key theft | G5, G7 |
| T-10 cross-tenant | G0 |
| T-11 artifact tampering | G3, G4 |
| T-12 fake benchmark | G3, G4 |
| T-13 audit tampering | G7 |
| T-18 supply chain | G7 |
| T-23 backup loss | G8 |
| T-24 isolation misconfig | G1, G6 |
