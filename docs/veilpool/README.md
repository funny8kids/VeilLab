# VeilPool · Product Documentation

**Status:** Current product baseline · **Version:** 1.1 · **Date:** 2026-11-03

VeilPool is a **testnet-only private pool / mixer** for fixed-denomination assets. Users
deposit into a pool, wait for the anonymity set to mature, and withdraw with a secret note.
Relayers submit withdrawals without seeing notes. Compliance checks run on deposit and
withdrawal.

> This is a product and engineering baseline, not a production anonymity guarantee.
> Mainnet execution does not exist. No real funds are accepted.

---

## 1. Current documents

| Document | Purpose |
| --- | --- |
| [`../00_PROJECT_VISION.md`](../00_PROJECT_VISION.md) | VeilPool mission, principles, trust model |
| [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) | Users, jobs, flows, screens, scope, metrics |
| [`MVP_SCOPE.md`](MVP_SCOPE.md) | First runnable local vertical slice and mock boundaries |
| [`MVP_STATUS.md`](MVP_STATUS.md) | Current implementation status, test evidence and gaps |
| [`POOL_MODEL.md`](POOL_MODEL.md) | Denominations, notes, nullifiers, maturity, fees, relayers, invariants |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Components, trust zones, data flow, contracts, failure modes |
| [`DATA_MODEL.md`](DATA_MODEL.md) | PostgreSQL schema, client-only notes, retention, audit |
| [`API_SPEC.md`](API_SPEC.md) | Public, relayer and admin endpoints, error semantics |
| [`COMPLIANCE.md`](COMPLIANCE.md) | Screening, limits, jurisdictions, review, audit |
| [`THREAT_MODEL.md`](THREAT_MODEL.md) | Mixer-specific assets, threats, mitigations and tests |
| [`TEST_PLAN.md`](TEST_PLAN.md) | Test strategy, cases, boundaries, gates, traceability |
| [`ZK_CIRCUIT_SPEC.md`](ZK_CIRCUIT_SPEC.md) | Real membership circuit, public signals and verifier ABI |
| [`ZK_CONTRACT_INTEGRATION.md`](ZK_CONTRACT_INTEGRATION.md) | Poseidon/Groth16 contract spike, fixture proof and integration blockers |
| [`FEATURE_OPTIMIZATION.md`](FEATURE_OPTIMIZATION.md) | Prioritized backlog and “real usability” checklist |

Prototype: [`../../prototype/index.html`](../../prototype/index.html) ·
[`../../prototype/README.md`](../../prototype/README.md).

---

## 2. Product in one paragraph

A user selects a fixed-denomination pool (e.g. ETH · 0.1), generates a secret note locally,
and deposits the exact amount. The note is the only withdrawal credential and never leaves
the browser. After maturity, the user generates a proof locally, chooses a non-custodial
relayer, and withdraws to a fresh address. The relayer submits the proof; it cannot see the
note or control funds. A compliance service screens addresses and enforces limits before
deposit and withdrawal. The indexer tracks pool events, Merkle roots and spent nullifiers.

---

## 3. Non-negotiable boundaries

1. **Testnet only.** No mainnet RPC, signing, broadcast or production keys.
2. **Notes never reach the server.** No API endpoint accepts a note; no server-side proving.
3. **Fixed denominations.** Amount splitting/merging is out of scope; it weakens privacy.
4. **Non-custodial relayers.** Relayers submit proofs; they cannot see notes or move funds.
5. **Compliance is explicit.** Screening, jurisdiction and limits are visible and auditable.
6. **Honest privacy language.** Show anonymity-set size and maturity; never promise
   “untraceable”.

---

## 4. Reading order

### Product / design

1. `PRODUCT_SPEC.md`
2. `POOL_MODEL.md`
3. `../../prototype/README.md`

### Engineering

1. `ARCHITECTURE.md`
2. `DATA_MODEL.md`
3. `API_SPEC.md`
4. `THREAT_MODEL.md`

### Security / QA

1. `THREAT_MODEL.md`
2. `TEST_PLAN.md`
3. `COMPLIANCE.md`

### Planning

1. `FEATURE_OPTIMIZATION.md`
2. `TEST_PLAN.md` release gates

---

## 5. Legacy documents

The earlier research-platform baseline remains in:

- `../architecture/` — research workflow, runners, observatory
- `../security/` — research threat model, network isolation, testnet policy
- `../database/` — research schema
- `../api/` — research API/event baseline
- `../research/` — experiments, benchmarks, reproducibility
- `../roadmap/` — research phases and gates
- `../adr/` — architecture decisions

Some security material — especially `../security/TESTNET_ONLY_POLICY.md` — still applies.
The rest is **legacy/supporting**, not the VeilPool product architecture. When a legacy
document conflicts with this directory, this directory wins.
