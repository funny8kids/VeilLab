# VeilPool Compliance and Risk

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [Architecture](ARCHITECTURE.md) · [Threat Model](THREAT_MODEL.md) · [Test Plan](TEST_PLAN.md)

---

## 1. Position

VeilPool is a **testnet-only** privacy pool. Compliance controls are part of the product, not
a bolt-on. The goal is to make privacy and policy compatible in the test environment:

- users see why an action is allowed, reviewed or blocked;
- operators can apply consistent limits;
- notes remain client-side;
- only the minimum address/decision data is retained.

This document is not legal advice. Production deployment requires jurisdiction-specific
counsel, licensing review and a provider contract.

---

## 2. Decisions

| Decision | Meaning | User experience |
| --- | --- | --- |
| `allow` | Policy permits the action | Proceed |
| `review` | Human review required | Pause; show review ID and SLA |
| `block` | Policy forbids the action | Stop; stable reason code |

Decisions are bound to:

- subject type (`deposit`, `withdrawal`, `relayer`),
- address (hashed or raw per policy),
- pool,
- amount,
- policy version,
- expiry.

A decision cannot be reused after expiry or for a different amount/pool/address.

---

## 3. Checks

### Deposit

- sanctions / watchlist screening of the depositor address;
- blocked jurisdiction;
- daily deposit limit;
- per-transaction limit;
- pool capacity and status;
- relayer? no; relayer is relevant on withdrawal.

### Withdrawal

- sanctions / watchlist screening of the recipient address;
- blocked jurisdiction;
- daily withdrawal limit;
- per-transaction limit;
- relayer compliance status;
- nullifier not already spent (on-chain check);
- pool not paused.

### Relayer

- operator identity / testnet-only attestation;
- sanctions screening of operator;
- fee within policy bound;
- supported pools;
- heartbeat and uptime;
- incident history.

---

## 4. Limits

| Limit | Default | Scope |
| --- | --- | --- |
| Daily deposit | 10,000 tUSD equivalent | per account / address |
| Daily withdrawal | 10,000 tUSD equivalent | per account / address |
| Per transaction | 5,000 tUSD equivalent | per action |
| Deposit velocity | 10 actions / hour | per account |
| Withdrawal velocity | 10 actions / hour | per account |
| Relayer fee | ≤ 1% | per pool |
| Review SLA | 24 h | manual queue |

Limits are policy-versioned. Changing a limit requires an audit record and a test update.

---

## 5. Screening providers

- Sanctions lists: OFAC, EU, UN (test/staging snapshots).
- Optional chain analytics for high-risk addresses.
- Provider failure → **fail closed** for new deposits/withdrawals; reads remain available.
- List version is recorded on every decision.
- False positives go to manual review; the user can submit context, never the note.

---

## 6. Privacy-preserving compliance

| Data | Handling |
| --- | --- |
| Note | Never collected |
| Proof input | Never collected |
| Depositor/recipient address | Store only if required; restrict and audit |
| Risk score | Store; do not expose beyond need-to-know |
| Sanctions evidence | Restricted; retention per policy |
| Aggregate metrics | No address, no note, no user-level graph |

Rules:

- Do not build a server-side deposit→withdrawal graph.
- Do not use note-derived identifiers in analytics.
- Do not log raw addresses with user IDs unless required for a review.
- Hash addresses where matching can still be done by the compliance provider.
- Delete compliance data when retention expires.

---

## 7. Manual review

A review item contains:

```text
review_id, subject_type, subject_ref, pool_id, amount
risk_score, reason_codes, provider, list_version
requested_at, expires_at, status
reviewer, decision, reason, decided_at
```

Rules:

- The reviewer sees the minimum needed; never a note.
- Approve/reject requires a reason.
- Review decisions expire (default 24 h).
- A review cannot override a sanctions hard-block without a documented exception and owner.
- Every decision is audited and exportable.

---

## 8. Audit

Every compliance action records:

- actor (user/service/admin),
- subject and action,
- policy version and list version,
- decision and reason codes,
- request ID / trace ID,
- timestamp,
- evidence reference (if any).

Audit is append-only with a daily hash anchor. The user can export their own decision record.

---

## 9. Boundaries and edge cases

| Case | Expected |
| --- | --- |
| Exact sanctions match | `block` |
| Fuzzy match | `review` |
| List provider down | Fail closed; alert |
| List version stale | Block high-risk; allow low-risk only with policy flag |
| Blocked jurisdiction (IP/declared) | `block` for new actions |
| Limit exactly reached | Allow last unit; next action blocked |
| Amount over per-tx limit | `block` |
| Relayer fee > cap | Quote rejected |
| Relayer disabled | Cannot be selected |
| Review expires | Action must be rechecked |
| User changes recipient after check | New check required |
| User changes amount after check | New check required |
| Same address deposit/withdraw | Allowed by policy but flagged for privacy guidance |
| Sanctioned recipient after proof | Block; do not submit |
| Compliance approves, then relayer blocks | Relayer decision wins; user can choose another |

---

## 10. Failure modes

| Failure | Behavior |
| --- | --- |
| Provider timeout | Retry once; then fail closed |
| Provider 5xx | Fail closed; incident alert |
| List parse error | Keep last known good; block changes requiring new list |
| Review queue backlog | Alert; do not auto-approve |
| Admin override | Requires role + reason + audit; still subject to hard blocks |
| Audit write failure | Fail the action closed |

---

## 11. Compliance test mapping

| Test | Expected |
| --- | --- |
| Exact sanctions hit | block + audit |
| Fuzzy hit | review + queue |
| Provider down | fail closed |
| Limit boundary | exact limit allowed, +1 blocked |
| Jurisdiction block | block |
| Relayer fee above cap | reject |
| Review expiry | recheck |
| Recipient change | new check |
| Audit tamper | hash chain fails |
| Note in compliance payload | rejected by schema/test |

Full cases: [TEST_PLAN.md](TEST_PLAN.md).

---

## 12. Open questions

- Which jurisdictions are blocked for a testnet-only product?
- Is address retention necessary, or can decisions be hash-only?
- Which sanctions provider is acceptable for a self-hosted test deployment?
- What is the appeal process for false positives?
- How long should compliance evidence be retained?
- Should compliance be enforced on-chain, off-chain, or both? (v1: off-chain gate + on-chain pause.)
