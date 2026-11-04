# 00 · VeilPool Vision

**Status:** Current · **Version:** 2.0 · **Date:** 2026-11-02
**Product docs:** [VeilPool index](veilpool/README.md)

---

## 1. Mission

**VeilPool is a testnet-only private pool / mixer that makes privacy claims inspectable.**

A user deposits a fixed denomination into a shared pool, waits for the anonymity set to
mature, and withdraws with a secret note. The note stays in the browser. A non-custodial
relayer submits the withdrawal without seeing it. Compliance checks are visible and
auditable.

We are not building an “untraceable” product. We are building a privacy product that is
honest about its anonymity set, timing, fees, relayers and policy boundaries.

---

## 2. The problem

Privacy tools fail in predictable ways:

1. **They overclaim.** “Untraceable” hides set size, timing and metadata leakage.
2. **They lose notes.** A refresh, cleared storage or lost device destroys funds.
3. **They hide policy.** Users discover limits and blocks only after signing.
4. **They centralize risk.** A server holds notes, keys or a deposit→withdrawal graph.
5. **They are not operable.** Reorgs, stale roots and relayer outages produce false receipts.

VeilPool is designed around these failures.

---

## 3. Principles

### P1 · Testnet only

No mainnet RPC, signing, broadcast or production key material. Testnet-only is enforced in
configuration, chain identity checks, egress policy and tests.

### P2 · The note belongs to the user

The note is generated, encrypted and stored client-side. No API accepts a note. No server
proves on the user’s behalf. No support flow asks for a note.

### P3 · Fixed denominations

Privacy comes from a shared set. Splitting and merging weaken the set and are out of scope.

### P4 · Non-custodial relayers

Relayers receive a proof and recipient, not a note. They cannot control funds or change the
recipient without invalidating the proof.

### P5 · Compliance by design

Screening, jurisdiction, limits and review are part of deposit and withdrawal. A block is
explainable; a review has an SLA; an audit record exists.

### P6 · Honest privacy UX

Show the anonymity set, maturity, fees and timing guidance. Never promise “untraceable”.
Never hide the trade-offs behind a single score.

### P7 · Fail closed

Unknown chain, stale root, invalid proof, blocked address, expired quote or paused pool stops
the action.

---

## 4. Users

| User | Job |
| --- | --- |
| Privacy-conscious testnet user | Move test assets without a direct deposit→withdrawal link |
| Relayer operator | Earn fees for valid submissions without custody |
| Compliance reviewer | Apply policy consistently with evidence |
| Operator | Keep pools healthy, pause safely, recover from reorgs |
| Researcher | Exercise a privacy pool end to end on testnets |

---

## 5. Product loop

```text
Select fixed-denomination pool
→ generate + back up note
→ deposit exact amount
→ wait for maturity / anonymity set
→ generate proof locally
→ choose relayer
→ withdraw to a fresh address
→ confirm, reconcile, mark note spent
```

Every step has a visible state, a failure mode and a test.

---

## 6. Scope

### In scope

- Testnet assets: ETH, USDC, tBTC.
- Fixed pools: ETH 0.1/1/10, USDC 100/1,000, tBTC 0.01.
- Client-side notes, encrypted vault, backup/import.
- Local proof generation.
- Non-custodial relayers, quotes and fallback.
- Compliance screening, limits, review and audit.
- Indexer with reorg recovery.
- 8-screen desktop product.

### Out of scope

- Mainnet, real funds, custody.
- Arbitrary-amount or cross-chain mixing.
- Server-side notes or proving.
- A production anonymity guarantee.
- Token/yield/speculation.

---

## 7. Success metrics

| Metric | Target |
| --- | --- |
| Deposit completion (valid users) | > 90% |
| Withdrawal completion after maturity | > 95% |
| Note backup before deposit | 100% |
| Proof success on supported browsers | > 99% |
| Relayer submission success | > 98% |
| Reorg recovery ≤ 12 blocks | 100% automatic |
| Compliance decision p95 | < 2 s |
| Notes stored server-side | 0 |
| Mainnet access | 0 |
| Cross-user data exposure | 0 |

---

## 8. Trust model

| Party | Trusted for | Not trusted for |
| --- | --- | --- |
| User/browser | Note custody, local proof | Server-side policy |
| API | Metadata, quotes, status | Notes, custody |
| Relayer | Submission | Note access, fund control |
| Indexer | Chain facts | Final truth without on-chain check |
| Compliance | Policy decision | Note access |
| Contracts | Deposit/withdraw rules | Off-chain privacy |
| Operator | Pause/config | Bypassing hard blocks |

---

## 9. Boundaries

- **No mainnet.** Not a configuration option; a structural absence.
- **No note server-side.** Not a policy; a schema and API boundary.
- **No production anonymity claim.** Testnet prototype; independent audit required before any
  real-value use.
- **No custody.** The product never holds user funds outside the pool contract.
- **No hidden policy.** A block has a reason code and a request ID.

---

## 10. Glossary

| Term | Meaning |
| --- | --- |
| Pool | Fixed asset + denomination + tree + nullifier set |
| Note | Client-side secret withdrawal credential |
| Commitment | Public leaf derived from a note |
| Nullifier | Public one-time value preventing double-spend |
| Anonymity set | Unspent, matured deposits in a pool |
| Maturity | Minimum wait before withdrawal |
| Relayer | Non-custodial submission service |
| Root window | Blocks/time in which a membership proof is valid |
| Compliance decision | allow / review / block |
| R-level | Not applicable to VeilPool v1; research legacy |

---

## 11. What must be true before any real-value discussion

1. Independent circuit and contract audit.
2. Formal/invariant testing of nullifier uniqueness and pool accounting.
3. External privacy review of timing, metadata and relayer leakage.
4. Legal/compliance review for the target jurisdiction.
5. A production key-management and incident-response program.
6. A credible anonymity-set threshold and user guidance.

Until then: testnet only.
