# VeilPool Threat Model

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-02
**Method:** STRIDE + mixer-specific attack scenarios
**Related:** [Architecture](ARCHITECTURE.md) · [Compliance](COMPLIANCE.md) · [Test Plan](TEST_PLAN.md)

---

## 1. Scope

In scope:

- Browser client, note vault, local prover, wallet interaction.
- API, relayer gateway, relayer nodes, indexer, compliance service.
- Pool/verifier/nullifier contracts on approved testnets.
- User, relayer, operator and reviewer behavior.

Out of scope:

- Mainnet funds (none).
- Wallet provider compromise.
- Host OS/kernel zero-days.
- Legal/regulatory adequacy of the compliance program.

---

## 2. Assets

| ID | Asset | Impact if compromised |
| --- | --- | --- |
| A1 | Secret notes | Theft → unauthorized testnet withdrawal |
| A2 | Note backups | Loss → unrecoverable funds; theft → withdrawal |
| A3 | Pool liquidity | Drain via proof/nullifier bug |
| A4 | Nullifier integrity | Double-spend |
| A5 | Anonymity set | Linkage/deanonymization |
| A6 | Recipient/depositor metadata | Privacy loss, compliance exposure |
| A7 | Relayer availability | Withdrawals stuck/censored |
| A8 | Compliance decisions | Policy bypass or unfair blocks |
| A9 | Audit log | Loss of accountability |
| A10 | Admin keys | Pool pause/fee/root manipulation |
| A11 | Indexer state | Wrong roots, double-spend window |
| A12 | Frontend integrity | Malicious note exfiltration |

---

## 3. Actors

| Actor | Capability | Motivation |
| --- | --- | --- |
| User | Browser, note, wallet | Privacy |
| Malicious website/extension | XSS, clipboard, phishing | Steal notes |
| Malicious relayer | Sees proof/recipient/timing | Censor, link, front-run |
| Compromised RPC | False logs/roots | Cause wrong state |
| Compliance provider | Lists, scores | False positives/negatives |
| Operator | Admin keys, config | Mistake or abuse |
| External attacker | API/edge access | Data theft/DoS |
| Sanctions evader | Attempts blocked flows | Bypass policy |

---

## 4. Trust boundaries

| Boundary | Untrusted side | Trusted side | Controls |
| --- | --- | --- | --- |
| B1 Browser ↔ API | Client input | API | Schema, auth, rate limit, no note endpoints |
| B2 Browser ↔ Relayer | Proof, recipient | Relayer | Proof validation, quote binding, compliance |
| B3 Relayer ↔ Chain | Transaction | Contract | On-chain proof/nullifier checks |
| B4 Chain ↔ Indexer | Logs/reorgs | Indexer | Chain ID, hashes, reorg handling |
| B5 API ↔ Compliance | Address/amount | Compliance | mTLS, policy version, audit |
| B6 Admin ↔ API | Human action | API | TOTP, role, audit |
| B7 Frontend supply chain | Dependencies | Browser | CSP, pinning, SRI, review |

---

## 5. Threat catalog

| ID | Threat | Impact | Mitigation | Test |
| --- | --- | --- | --- | --- |
| T-01 | Note stolen via clipboard malware | A1/A2 | Short display, no clipboard by default, backup warning, CSP | SEC-NOTE-01 |
| T-02 | Note exfiltrated by XSS/extension | A1/A2 | CSP, no inline scripts, no third-party scripts, encrypted vault | SEC-XSS-01 |
| T-03 | Note sent to API/analytics/logs | A1 | No note endpoints, redaction, schema tests, log scan | NOTE-LEAK-01 |
| T-04 | Note lost | A2 | Mandatory encrypted backup, recovery flow | NOTE-02 |
| T-05 | Note used on wrong pool/chain | A1 | Note binds chain/pool/denomination; reject | NOTE-03 |
| T-06 | Double-spend / nullifier replay | A3/A4 | Unique nullifier, on-chain check, DB unique | WDR-05 |
| T-07 | Proof forgery | A3 | Audited circuit/verifier, negative fixtures | SEC-PROOF-01 |
| T-08 | Stale root proof | A3/A4 | Root window, indexer lag block | WDR-06 |
| T-09 | Malicious relayer censors | A7 | Fallback relayers, timeout | REL-03 |
| T-10 | Relayer links deposit/withdraw | A5/A6 | Non-custodial, no note, timing guidance, multiple relayers | REL-PRIV-01 |
| T-11 | Relayer front-runs | A3 | Proof binds recipient/fee; private submission where possible | SEC-MEV-01 |
| T-12 | Timing correlation | A5 | Maturity, waiting guidance, no instant withdraw | PRIV-01 |
| T-13 | Amount fingerprinting | A5 | Fixed denominations | POOL-02 |
| T-14 | Address reuse linkage | A5 | Fresh recipient guidance, warnings | PRIV-02 |
| T-15 | Deposit/withdraw graph analysis | A5 | No server graph, aggregate analytics only | PRIV-03 |
| T-16 | Indexer reorg inconsistency | A4/A11 | Reorg rollback/replay, root rebuild test | IDX-REORG-01 |
| T-17 | RPC lies about chain/logs | A4/A11 | Chain ID, parent hash, finality, raw retention | IDX-01 |
| T-18 | Compliance bypass | A8 | Fail closed, policy version, review | CMP-06 |
| T-19 | Sanctions false positive | A8 | Manual review, appeal, reason code | CMP-02 |
| T-20 | Admin key compromise | A10 | Least privilege, delay, audit, testnet only | OPS-03 |
| T-21 | Pool drain via accounting bug | A3 | Invariant tests, balance reconciliation, pause | POOL-05 |
| T-22 | API IDOR / cross-user data | A6 | Authz checks, no activity graph, tests | SEC-IDOR-01 |
| T-23 | CSRF on deposit/withdraw intent | A3 | CSRF token, SameSite, origin check | SEC-CSRF-01 |
| T-24 | Rate-limit bypass/DoS | A7 | Per-account/IP limits, queues | API-04 |
| T-25 | Supply-chain compromise | A12 | Lockfiles, pinned deps, CSP, SRI, review | SEC-SUPPLY-01 |
| T-26 | Mainnet misconfiguration | A3 | Testnet-only registry, chain ID/genesis checks | G1 |
| T-27 | Frontend malicious update | A12 | Signed builds, CSP, release review | SEC-REL-01 |
| T-28 | Note in crash report/support | A1 | Redaction, no note field, support policy | NOTE-LEAK-02 |
| T-29 | Browser storage exfiltration | A2 | Encrypted vault, auto-lock, OS key | SEC-STORE-01 |
| T-30 | Relayer fee manipulation | A3 | Signed quote, cap, proof binds fee | REL-04 |

---

## 6. Attack scenarios

### 6.1 Note theft

**Path:** malicious extension reads DOM or clipboard; or user pastes note into a phishing site.

**Impact:** testnet funds stolen.

**Controls:** note shown once, not copied by default, encrypted vault, CSP, no third-party
scripts, clear phishing guidance, auto-lock, note never in URL.

**Residual:** a compromised browser can read anything the user sees. Document this limit.

### 6.2 Double-spend race

**Path:** two relayers submit the same note concurrently.

**Impact:** one succeeds, one reverts; if the indexer marks spent incorrectly, UI misleads.

**Controls:** on-chain nullifier uniqueness; DB unique constraint; indexer projection; UI
uses on-chain state as truth.

### 6.3 Timing correlation

**Path:** user deposits and withdraws within minutes; observer links amounts/time.

**Impact:** privacy loss, not fund loss.

**Controls:** maturity periods, waiting guidance, no instant-withdraw CTA, set-size display.
Residual: users can ignore guidance.

### 6.4 Malicious relayer metadata

**Path:** relayer logs recipient + timing and correlates with a deposit.

**Impact:** linkage.

**Controls:** relayer cannot see note; multiple relayers; no server-side note graph; policy
against logging recipient beyond submission need.

### 6.5 Proof forgery

**Path:** bug in circuit/verifier allows a proof without membership or with a fake nullifier.

**Impact:** pool drain.

**Controls:** circuit audit, verifier tests, negative fixtures, invariant/fuzz tests, pause
switch. Testnet only reduces financial impact but not correctness impact.

### 6.6 Reorg double-count

**Path:** deposit confirmed then reorged; indexer keeps leaf; user withdraws against a tree
that no longer exists.

**Impact:** invalid proof / failed withdrawal; or accounting mismatch.

**Controls:** reorg manager, cursor rollback, root rebuild, confirmation/finality display.

---

## 7. Residual risks

| Risk | Why accepted | Review trigger |
| --- | --- | --- |
| Compromised browser can read notes | Client-side model | Any native app/extension |
| Relayer sees recipient/timing | Submission requires it | Private submission / TEE |
| Testnet only | Product boundary | Never remove without new ADR |
| Compliance provider false positives | Imperfect lists | Appeals process |
| No formal anonymity proof | Research prototype | External audit |
| Frontend supply chain | Practical risk | Signed releases |

---

## 8. Review cadence

- Update for every new endpoint, relayer behavior, pool type or compliance source.
- Re-rate after each security test cycle.
- A threat without a test is a hypothesis.
- Full case mapping: [TEST_PLAN.md](TEST_PLAN.md).
