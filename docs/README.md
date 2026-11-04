# VeilLab Documentation

**Current product:** VeilPool · testnet-only private pool / mixer
**Baseline:** v1.0 · 2026-11-02

> This directory contains the current VeilPool product baseline plus the earlier
> research-platform documents, which are retained as **legacy/supporting** material.
> When a legacy document conflicts with `veilpool/`, `veilpool/` wins.

---

## 1. Start here

| Document | Purpose |
| --- | --- |
| [`00_PROJECT_VISION.md`](00_PROJECT_VISION.md) | VeilPool mission, principles, trust model |
| [`veilpool/README.md`](veilpool/README.md) | Product documentation index |
| [`veilpool/PRODUCT_SPEC.md`](veilpool/PRODUCT_SPEC.md) | Users, flows, screens, scope, metrics |
| [`veilpool/MVP_SCOPE.md`](veilpool/MVP_SCOPE.md) | First runnable local vertical slice and mock boundaries |
| [`veilpool/MVP_STATUS.md`](veilpool/MVP_STATUS.md) | Implementation status, test evidence and gaps |
| [`veilpool/POOL_MODEL.md`](veilpool/POOL_MODEL.md) | Denominations, notes, nullifiers, maturity, fees, relayers |
| [`veilpool/ARCHITECTURE.md`](veilpool/ARCHITECTURE.md) | Components, trust zones, contracts, failure modes |
| [`veilpool/DATA_MODEL.md`](veilpool/DATA_MODEL.md) | PostgreSQL schema, client-only notes, retention |
| [`veilpool/API_SPEC.md`](veilpool/API_SPEC.md) | Public, relayer and admin endpoints |
| [`veilpool/COMPLIANCE.md`](veilpool/COMPLIANCE.md) | Screening, limits, review, audit |
| [`veilpool/THREAT_MODEL.md`](veilpool/THREAT_MODEL.md) | Mixer-specific threats and mitigations |
| [`veilpool/TEST_PLAN.md`](veilpool/TEST_PLAN.md) | Test matrix, boundaries, gates, traceability |
| [`veilpool/FEATURE_OPTIMIZATION.md`](veilpool/FEATURE_OPTIMIZATION.md) | Prioritized backlog and usability checklist |

Prototype: [`../prototype/index.html`](../prototype/index.html) ·
[`../prototype/README.md`](../prototype/README.md).

---

## 2. Reading order

### Product / design

1. `00_PROJECT_VISION.md`
2. `veilpool/PRODUCT_SPEC.md`
3. `veilpool/POOL_MODEL.md`
4. `veilpool/COMPLIANCE.md`
5. `../prototype/README.md`

### Engineering

1. `veilpool/ARCHITECTURE.md`
2. `veilpool/DATA_MODEL.md`
3. `veilpool/API_SPEC.md`
4. `veilpool/THREAT_MODEL.md`

### Security / QA

1. `veilpool/THREAT_MODEL.md`
2. `veilpool/TEST_PLAN.md`
3. `veilpool/COMPLIANCE.md`
4. `security/TESTNET_ONLY_POLICY.md` (still applies)

### Planning

1. `veilpool/FEATURE_OPTIMIZATION.md`
2. `veilpool/TEST_PLAN.md` release gates

---

## 3. Source of truth

1. **VeilPool product baseline** (`veilpool/`).
2. **Testnet-only policy** (`security/TESTNET_ONLY_POLICY.md`) — safety constraint.
3. **Prototype** (`../prototype/`) — current UI direction.
4. **Legacy research baseline** (everything else) — reference only.
5. Implementation and code comments.

Disagreements are resolved by a documentation PR, not by divergent code.

---

## 4. Legacy research baseline

These documents describe the earlier research platform. They remain for history and for
supporting ideas (testnet policy, isolation, audit), but they are **not** the current
architecture.

| Area | Documents |
| --- | --- |
| Vision / architecture | `architecture/*` |
| Security | `security/*` (TESTNET_ONLY_POLICY remains binding) |
| Database | `database/*` |
| API / events | `api/*` |
| Research | `research/*` |
| Roadmap / gates | `roadmap/*` |
| ADRs | `adr/*` |

Legacy documents may still be useful for:

- testnet-only enforcement,
- trust-zone and network isolation,
- audit hash chains,
- reproducibility and evidence practices,
- incident response.

---

## 5. Document conventions

- Normative keywords: **MUST / SHOULD / MAY** (RFC 2119).
- IDs are opaque, prefixed strings (`pool_`, `dep_`, `wdr_`, `cmp_`).
- Timestamps are ISO 8601 UTC.
- Chain IDs and RPC endpoints are configuration; only approved testnets.
- “Note” always means the client-side secret withdrawal credential; never a server field.
- Mermaid diagrams are explanatory; contracts and tests are authoritative.

---

## 6. Change process

| Change | Required artifact |
| --- | --- |
| New pool / denomination | Pool model + config + test cases |
| New API field | API spec + schema test |
| New compliance rule | Compliance doc + test case + audit requirement |
| New relayer behavior | Architecture + threat model + test |
| New external destination | Network policy + security review |
| New note format | Pool model + migration + backup compatibility test |
| New chain | Testnet-only policy + chain ID/genesis test |

Every behavior change updates the corresponding doc in the same PR. A feature is not done
until its tests and boundaries are defined in `veilpool/TEST_PLAN.md`.
