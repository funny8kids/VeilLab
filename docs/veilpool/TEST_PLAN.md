# VeilPool Test Plan

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [Pool Model](POOL_MODEL.md) · [Threat Model](THREAT_MODEL.md) · [Compliance](COMPLIANCE.md)

---

## 1. Purpose

This plan answers one question: **can a real user complete deposit → maturity → withdrawal
without losing funds, leaking a note, or bypassing policy?**

It covers product boundaries, security invariants, failure recovery and release gates. A
feature is not “done” until its cases and boundaries exist here and pass in CI.

---

## 2. Test levels

| Level | Scope | Environment |
| --- | --- | --- |
| Unit | Note parsing, amount math, fee math, validation, state transitions | Local |
| Property-based | Pool accounting, nullifier uniqueness, note/commitment consistency | Local |
| Contract | Deposit, withdraw, pause, fee bounds, nullifier, root window | Anvil |
| Integration | API + indexer + compliance + relayer gateway | Local stack |
| E2E | Browser deposit → wait → withdraw, errors, recovery | Anvil + Sepolia staging |
| Security | Replay, forgery, note leakage, IDOR, XSS, CSRF, supply chain | Local + staging |
| Compliance | Sanctions, limits, jurisdiction, review, audit | Staging with fixture lists |
| Performance | Proof generation, API p95, indexer lag, relayer latency | Reference hardware |
| Accessibility | Keyboard, focus, contrast, screen reader, reduced motion | Browser matrix |
| Chaos | RPC timeout, reorg, relayer offline, DB fail, provider down | Local/staging |

Tools: Vitest/Playwright, Foundry, Pytest, k6/autocannon, axe, dependency/container scanners.

---

## 3. Non-negotiable invariants

These must hold in every test and production run:

| ID | Invariant |
| --- | --- |
| I1 | Deposit amount equals the pool denomination exactly |
| I2 | Notes never leave the client; no API/log/table receives a note |
| I3 | A nullifier is spent at most once per pool |
| I4 | Pool balance = deposits − withdrawals − fees |
| I5 | A proof verifies only for the correct pool, root window and public signals |
| I6 | A compliance block prevents submission |
| I7 | A reorg replay converges to the same root/nullifier set |
| I8 | No mainnet chain ID or RPC is accepted |
| I9 | A failed/reverted transaction does not consume a note |
| I10 | A paused pool cannot deposit or withdraw |

---

## 4. Feature test matrix

### 4.1 Pools

| ID | Case | Expected |
| --- | --- | --- |
| POOL-01 | List active pools | Denominations, set size, fee, maturity visible |
| POOL-02 | Same asset, different denominations | Separate trees, sets and balances |
| POOL-03 | Paused pool | Deposit/withdraw blocked; clear reason |
| POOL-04 | Retired pool | Read-only; no new actions |
| POOL-05 | Pool balance mismatch | Alert; pause; no withdrawals |
| POOL-06 | Fee above cap | Config rejected at startup |
| POOL-07 | Maturity change | New deposits use new value; old deposits keep original |
| POOL-08 | Unknown pool ID | 404, no information leak |

### 4.2 Deposit

| ID | Case | Expected |
| --- | --- | --- |
| DEP-01 | Valid deposit | Note created, backed up, tx confirmed, leaf indexed |
| DEP-02 | Amount below denomination | Rejected before wallet prompt |
| DEP-03 | Amount above denomination | Rejected |
| DEP-04 | Zero / negative amount | Schema error |
| DEP-05 | Wrong network | Blocked; switch to testnet |
| DEP-06 | Mainnet chain ID | Blocked; security event |
| DEP-07 | Note not backed up | Deposit blocked |
| DEP-08 | Compliance `block` | No wallet prompt; stable reason code |
| DEP-09 | Compliance `review` | 202; no deposit until reviewed |
| DEP-10 | User rejects wallet | Deposit cancelled; note remains unspent |
| DEP-11 | Transaction reverts | Deposit failed; no leaf; note unspent |
| DEP-12 | Duplicate submit click | One tx; idempotency |
| DEP-13 | Indexer lag | Status `submitted`, not `confirmed` |
| DEP-14 | Reorg after confirmation | Status returns to pending; reconcile |
| DEP-15 | Pool capacity/paused | Deposit blocked |
| DEP-16 | Deposit intent replay/expiry | Expired intent rejected; no duplicate deposit |

### 4.3 Note lifecycle

| ID | Case | Expected |
| --- | --- | --- |
| NOTE-01 | Generate note | Correct pool/chain/denomination, checksum valid |
| NOTE-02 | Backup/export | Encrypted file; passphrase required |
| NOTE-03 | Wrong pool note | Rejected before proof |
| NOTE-04 | Wrong chain note | Rejected |
| NOTE-05 | Corrupted note | Checksum error; no guessing |
| NOTE-06 | Empty note | Validation error |
| NOTE-07 | Note already spent | “Already withdrawn”; no proof |
| NOTE-08 | Note imported after spend | Marked spent |
| NOTE-09 | Note in URL/analytics/log | Test fails; redaction blocks |
| NOTE-10 | Clipboard disabled | Note still viewable/backupable |
| NOTE-11 | Storage quota full | Deposit blocked; backup guidance |
| NOTE-12 | Browser refresh | Note persists only in encrypted vault |
| NOTE-13 | Note format version | Unknown version rejected; v1 test vector matches |
| NOTE-14 | Backup wrong passphrase | Decryption fails cleanly; no note corruption |

### 4.4 Withdrawal

| ID | Case | Expected |
| --- | --- | --- |
| WDR-01 | Valid withdrawal | Proof generated, relayer submits, confirmed |
| WDR-02 | Before maturity | Blocked with countdown |
| WDR-03 | Exactly at maturity | Allowed |
| WDR-04 | One second before maturity | Blocked |
| WDR-05 | Reuse nullifier | `NULLIFIER_SPENT`; no tx |
| WDR-06 | Stale root | `ROOT_STALE`; refresh required |
| WDR-07 | Invalid proof | `PROOF_INVALID`; no submission |
| WDR-08 | Wrong recipient in proof | Verifier rejects |
| WDR-09 | Recipient zero address | Validation error |
| WDR-10 | Recipient sanctioned | Compliance block |
| WDR-11 | Recipient is depositor address | Allowed but privacy warning |
| WDR-12 | Relayer offline | Fallback offered |
| WDR-13 | Quote expired | New quote required |
| WDR-14 | Fee over cap | Quote rejected |
| WDR-15 | Two relayers submit same note | One wins; one reverts; note spent once |
| WDR-16 | Transaction reverted | Note unspent; failure reason |
| WDR-17 | Confirmed then reorged | Pending/reconcile; no false “spent” |
| WDR-18 | Pool paused mid-flow | Submission blocked |
| WDR-19 | Reorg after nullifier spent | Nullifier can be re-spent canonically; old row non-canonical |

### 4.5 Relayers

| ID | Case | Expected |
| --- | --- | --- |
| REL-01 | List relayers | Fee, latency, uptime, pools, status |
| REL-02 | Select relayer | Quote bound to pool/amount/recipient |
| REL-03 | Relayer timeout | Fallback; proof preserved |
| REL-04 | Fee manipulated after quote | Proof/public signal mismatch; reject |
| REL-05 | Relayer disabled | Cannot be selected |
| REL-06 | Relayer attempts to change recipient | Proof invalid |
| REL-07 | Relayer cannot see note | Request schema rejects note fields |
| REL-08 | Relayer offline heartbeat | Status degraded/offline |
| REL-09 | Relayer compliance fail | Disabled; audit |
| REL-10 | Relayer logs recipient | Redaction/policy test |
| REL-11 | Replay a signed quote | Rejected/expired; one-time use |

### 4.6 Compliance

| ID | Case | Expected |
| --- | --- | --- |
| CMP-01 | Exact sanctions match | Block |
| CMP-02 | Fuzzy match | Review |
| CMP-03 | Provider timeout | Fail closed |
| CMP-04 | Stale list | Block high-risk; policy flag |
| CMP-05 | Blocked jurisdiction | Block |
| CMP-06 | Limit exactly reached | Allow last; next blocked |
| CMP-07 | Limit +1 | Block |
| CMP-08 | Review approve | Proceed; audit |
| CMP-09 | Review reject | Block; reason |
| CMP-10 | Review expiry | Recheck |
| CMP-11 | Recipient changed after check | New check |
| CMP-12 | Note in compliance payload | Schema reject |

### 4.7 Indexer / chain

| ID | Case | Expected |
| --- | --- | --- |
| IDX-01 | Chain ID mismatch | Disconnect; alert |
| IDX-02 | Duplicate logs | Idempotent |
| IDX-03 | Out-of-order logs | Ordered by block/log index |
| IDX-04 | Reorg 1 block | Rollback + replay |
| IDX-05 | Reorg 12 blocks | Rollback + replay; alert |
| IDX-06 | Missing log | Detect gap; refetch |
| IDX-07 | RPC timeout | Retry/backoff; no gap |
| IDX-08 | Rebuild from genesis | Same root/nullifiers |
| IDX-09 | Root changed during proof | Stale root handling |
| IDX-10 | Finality tag | Correct confirmed/finalized display |
| IDX-11 | Cursor restart | Resume correctly |
| IDX-12 | Raw event retention | Audit/replay works |
| IDX-13 | Reorg reuses leaf index | Old non-canonical; new canonical leaf allowed |

### 4.8 API / UI

| ID | Case | Expected |
| --- | --- | --- |
| API-01 | Idempotency same body | Same response |
| API-02 | Idempotency different body | 409 |
| API-03 | Rate limit | 429 + Retry-After |
| API-04 | Cross-user activity | 404/403 |
| API-05 | Proof shape invalid | 422 |
| API-06 | Note field in request | 422/schema reject |
| API-07 | CSRF missing | 403 |
| API-08 | Error leak | No note/address/stack |
| API-09 | Activity endpoint | Not available server-side in v1; activity is local |
| API-10 | Compliance check endpoint | Not public; internal auth only |
| UI-01 | Screen navigation | Active nav/crumb correct |
| UI-02 | EN/中文 | All 358 strings switch; technical IDs stable |
| UI-03 | Dark/light | Both themes pass contrast |
| UI-04 | Empty/loading/error | Clear states |
| UI-05 | Keyboard flow | All actions reachable |
| UI-06 | Long note/address | Truncation, copy, no layout break |
| UI-07 | Note warning | Visible before deposit |
| UI-08 | Maturity countdown | Accurate across reload |
| UI-09 | Relayer offline | Fallback visible |
| UI-10 | Compliance block | Reason + request ID |
| UI-11 | Reduced motion | Animations disabled |
| UI-12 | 1180px width | No horizontal overflow |
| UI-13 | Activity source | Local note vault + public events; no account graph |
| UI-14 | Lighthouse accessibility | 100 on overview/deposit, EN/ZH, dark/light |

### 4.9 Privacy

| ID | Case | Expected |
| --- | --- | --- |
| PRIV-01 | Deposit→withdraw timing guidance | Wait recommendation shown; no instant-withdraw dark pattern |
| PRIV-02 | Recipient equals depositor | Warning + fresh-address guidance |
| PRIV-03 | Aggregate analytics | No deposit→withdrawal graph, no note-derived IDs |
| PRIV-04 | Set-size display | Unspent/matured definition; updated timestamp |
| PRIV-05 | Relayer metadata | Recipient/timing not retained beyond submission need |

### 4.10 Operations

| ID | Case | Expected |
| --- | --- | --- |
| OPS-01 | Pause pool | Deposit/withdraw blocked; reason shown |
| OPS-02 | Fee change | Bounded; new deposits only; audit |
| OPS-03 | Admin without TOTP/role | 403; audit |
| OPS-04 | Backup/restore | Pools, events, nullifiers, audit restored |
| OPS-05 | Incident runbook | Pause/rotate/notify steps executable |
| OPS-06 | Key rotation | Old keys revoked; services restart |
| OPS-07 | Balance reconciliation | Mismatch alerts and pauses |
| OPS-08 | Disable relayer | Removed from quotes; audit |

---

## 5. Boundary cases

| Boundary | Values to test | Expected |
| --- | --- | --- |
| Deposit amount | 0, 1 wei, denom−1, denom, denom+1, max uint | Only exact denomination accepted |
| Token decimals | 6, 18, non-standard | Correct wei conversion; no float |
| Maturity | −1s, exactly, +1s, clock skew ±5m | Only ≥ maturity allowed |
| Note length | 0, 1, max, +1 | Reject invalid; no crash |
| Note charset | unicode, whitespace, uppercase/lowercase | Reject/normalize explicitly |
| Recipient | zero, self, contract, sanctioned, checksum case | Correct validation/screening |
| Relayer fee | 0, 1 bps, cap, cap+1, negative | 0 and cap allowed; cap+1 rejected |
| Relayer quote | expired 1s, valid 1s | Expired rejected |
| Root window | first valid block, last valid block, +1 | +1 rejected |
| Concurrency | double click, two tabs, two relayers | One spend; idempotent UI |
| Storage | disabled, quota full, private mode | Backup/deposit blocked with guidance |
| Chain | Sepolia, Anvil, unknown, mainnet 1 | First two allowed; last two denied |
| Compliance | exact match, fuzzy, list stale, provider down | Block/review/fail-closed |
| Review | 0s, SLA−1s, SLA+1s | Expiry enforced |
| Address length | short, long, checksum-mixed | Reject invalid; no crash |
| Language | EN/ZH, long Chinese strings | No layout break |
| Theme | dark/light, system | Correct tokens/contrast |

---

## 6. Security test cases

| ID | Case | Expected |
| --- | --- | --- |
| SEC-01 | Replay withdrawal proof | Rejected/nullifier spent |
| SEC-02 | Forge proof without membership | Rejected |
| SEC-03 | Use proof on another pool | Rejected |
| SEC-04 | Use proof on another chain | Rejected |
| SEC-05 | Change recipient after proof | Rejected |
| SEC-06 | Change fee after quote | Rejected |
| SEC-07 | XSS via note/address field | Escaped, no execution |
| SEC-08 | CSRF on intent/submit | 403 |
| SEC-09 | IDOR on withdrawal/activity | 404/403 |
| SEC-10 | Note in logs/error/trace | Redaction test fails build |
| SEC-11 | Note in analytics event | Schema rejects |
| SEC-12 | Frontend dependency tamper | SRI/lockfile/signature |
| SEC-13 | Malicious relayer response | Schema validation |
| SEC-14 | Rate-limit abuse | 429; no state change |
| SEC-15 | Admin without TOTP | 403 |

---

## 7. E2E scenarios

### E2E-01 · Happy path

1. Connect testnet wallet.
2. Select ETH 0.1.
3. Generate + export note.
4. Deposit; wait for confirmation.
5. Wait for maturity.
6. Paste note, fresh recipient, choose relayer.
7. Generate proof, submit.
8. Confirm; note marked spent.
9. Balance and activity match.

### E2E-02 · Relayer failure

- Relayer goes offline after quote.
- UI offers fallback.
- Proof remains local; second relayer succeeds.
- No duplicate spend.

### E2E-03 · Compliance block

- Recipient is on fixture sanctions list.
- Withdrawal blocked before proof submission.
- Audit record exists; note remains unspent.

### E2E-04 · Reorg

- Deposit confirmed, then 2-block reorg.
- Status returns to pending.
- Replay restores correct leaf/root.
- Withdrawal either waits or uses valid root.

### E2E-05 · Note recovery

- Clear browser storage.
- Import encrypted backup.
- Note restores; status checks; withdrawal works.

### E2E-06 · Wrong network

- Wallet on mainnet/unknown chain.
- Deposit/withdraw blocked.
- No RPC call; security event.

---

## 8. Non-functional targets

| Metric | Target |
| --- | --- |
| Proof generation | < 8 s on reference laptop for depth 20 |
| API reads p95 | < 300 ms |
| Deposit intent p95 | < 1 s |
| Compliance check p95 | < 2 s |
| Indexer lag p95 | < 30 s testnet |
| Withdrawal confirmation | Network-dependent; UI shows state |
| Relayer quote p95 | < 500 ms |
| Accessibility | WCAG 2.1 AA for core flows |
| Browser support | Latest Chrome, Edge, Firefox, Safari |
| Reorg recovery | ≤ 12 blocks without manual action |

---

## 9. Release gates

| Gate | Condition |
| --- | --- |
| G0 | Build, health, migrations, testnet config |
| G1 | Testnet-only: mainnet/unknown chain denied |
| G2 | Deposit happy path + note backup |
| G3 | Withdrawal proof + relayer confirmation |
| G4 | Note isolation: no note in API/log/DB/analytics |
| G5 | Nullifier uniqueness + double-spend tests |
| G6 | Relayer fallback + fee/quote binding |
| G7 | Compliance allow/review/block + audit |
| G8 | Indexer reorg + root rebuild |
| G9 | Backup/restore + incident runbook |
| G10 | Security scan + accessibility + no critical findings |

A release is blocked by any red gate. G1, G4 and G5 cannot be waived.

---

## 10. Traceability

| Threat | Tests |
| --- | --- |
| T-01 note theft | SEC-07, NOTE-09, NOTE-10 |
| T-03 note to server | NOTE-09, API-06, SEC-10 |
| T-05 wrong pool/chain | NOTE-03, NOTE-04, SEC-03/04 |
| T-06 double-spend | WDR-05, WDR-15, SEC-01 |
| T-07 proof forgery | SEC-02, WDR-07 |
| T-10 relayer linkage | REL-07, REL-10 |
| T-12 timing | PRIV-01, UI-07/08 |
| T-16 reorg | IDX-04/05/08/13, WDR-19, E2E-04 |
| T-18 compliance bypass | CMP-01..12 |
| T-20 admin key | SEC-15, OPS-03 |
| T-24 DoS | API-03, SEC-14 |
| T-26 mainnet | G1, DEP-06, E2E-06 |

---

## 11. Definition of done

- [ ] Cases in this plan implemented and passing.
- [ ] Negative/boundary cases included.
- [ ] Note isolation test runs in CI (schema, logs, error paths).
- [ ] Invariant/property tests pass.
- [ ] E2E happy path and failure paths pass on Anvil + staging.
- [ ] No critical/high security findings open.
- [ ] Accessibility review complete.
- [ ] Runbook and support error codes updated.
- [ ] Evidence attached to the release gate.

---

## 12. Manual QA checklist

- [ ] I can create a note and I am forced to export it.
- [ ] I can recover from a refresh and from clearing storage.
- [ ] I cannot deposit without a backup.
- [ ] I can see maturity and set size before depositing.
- [ ] I cannot withdraw before maturity.
- [ ] I can switch relayers without losing the proof.
- [ ] A blocked recipient gives a reason and request ID.
- [ ] A paused pool blocks both actions.
- [ ] The note never appears in network requests.
- [ ] The UI works in EN/ZH and dark/light.
- [ ] The app is usable at 1180px width.
- [ ] A support engineer can diagnose with request ID only.

---

## 13. Implemented evidence (2026-11-03)

| Suite | Result |
| --- | --- |
| API pytest | 107 passed |
| Indexer pytest | 29 passed |
| Contract Foundry | 53 passed (22 original, 17 Groth16, 14 Poseidon pool) |
| Web Vitest | 86 passed |
| Browser Playwright | 3 mock + 2 local Anvil passed |
| Circuit verifier negatives | 11/11 passed |
| Circuit witness negatives | 11/11 passed |

Live local-chain checks:

- Anvil chain 31337 deployment succeeded; the indexer read the three `PoolCreated` events.
- API `local` mode returned `mode:"local"`, `mock:false`, indexer status and pool overlays.
- `POST /api/v1/deposits/intent` → `POST /api/v1/local/deposits` produced a confirmed
  indexer-backed deposit; a repeat call was idempotent.
- The web app showed `ANVIL LOCAL`, completed a local deposit through the bridge, displayed
  “Local deposit confirmed” with tx/block, and the local Playwright spec passed without sending
  the note. A second browser deposit was indexed as leaf 1.
- The indexer path API returned the exact Poseidon root/path for one- and multi-leaf trees.
- Direct `cast send withdraw(...)` with a real Groth16 proof succeeded; the API path proxy and
  `POST /api/v1/local/withdrawals` then confirmed a real proof withdrawal (tx
  `0x966e2c91983b051bb2fe5122fd8f6aea0d70efb8e270482b3b5ba75a8178f6bf`, block 9) and
  rejected replay/nullifier reuse correctly.
- A deliberately invalid proof returned `502 WITHDRAWAL_REVERTED` with a receipt, and the quote
  remained reusable.
- The full browser flow (v2 note → deposit → Web Worker proof → local withdrawal) passed in
  5.9 s total; the recorded withdrawal was block 18, tx
  `0x3f332a1139a192ae2ad9b2f7c558cd9f37674d5ce41b9308f99f9208a2002460`.
- The indexer's live two-block reorg test rolled back a reorged withdrawal and replayed
  canonical blocks.
- The generated `Verifier.sol` was stale relative to the final zkey; regenerating it made the
  on-chain fixture proof pass.

Remaining untested paths: local withdrawal bridge, browser proving, production auth,
multiparty ceremony, and mainnet (intentionally absent).
