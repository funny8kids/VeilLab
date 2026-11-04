# Engineering Startup Checklist

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md) · [RELEASE_PLAN](RELEASE_PLAN.md)

---

## 1. Purpose

This checklist turns the design baseline into the first implementation phase. It separates
**design complete** from **implemented and verified**.

Status legend:

- ✅ Design complete (documented and reviewed)
- 🟡 Designed, not implemented
- ⬜ Not started
- 🔒 Security gate (cannot be waived)

---

## 2. Ten startup items

| # | Item | Design | Implementation | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Freeze positioning and Testnet Only principle | ✅ | 🟡 policy config | [Vision](../00_PROJECT_VISION.md), [Policy](../security/TESTNET_ONLY_POLICY.md) |
| 2 | SYSTEM_ARCHITECTURE.md | ✅ | — | [System](../architecture/SYSTEM_ARCHITECTURE.md) |
| 3 | SECURITY_ARCHITECTURE + threat model | ✅ | 🟡 controls | [Security](../security/SECURITY_ARCHITECTURE.md), [Threat model](../security/THREAT_MODEL.md) |
| 4 | Database ERD and core schema | ✅ | ⬜ migrations | [DB](../database/DATABASE_DESIGN.md), [ERD](../database/ERD.md) |
| 5 | API contract and event definitions | ✅ | ⬜ OpenAPI/schemas | [API](../api/API_SPECIFICATION.md), [Events](../api/EVENT_SCHEMA.md) |
| 6 | Monorepo and package boundaries | ✅ | ⬜ scaffold | [Modules](../architecture/MODULE_BOUNDARIES.md) |
| 7 | Docker Compose dev environment | ✅ | ⬜ compose files | [Deployment](../architecture/DEPLOYMENT_ARCHITECTURE.md) |
| 8 | Network allowlist and mainnet denial | ✅ | ⬜ gateway/policy | [Network](../security/NETWORK_ISOLATION.md), [Testnet policy](../security/TESTNET_ONLY_POLICY.md) |
| 9 | Control Center basics | ✅ | ⬜ auth/projects/jobs | [Control Center](../architecture/CONTROL_CENTER.md) |
| 10 | Observatory first workflow | ✅ | ⬜ discovery/registry | [Roadmap P2](DEVELOPMENT_ROADMAP.md) |

Summary: **design 10/10, implementation 0/10 complete** (items 1 and 3 have partial
policy/control scaffolding). The next phase is P0/P1 in the roadmap.

---

## 3. What "design complete" means

- The document exists and is linked from [docs/README](../README.md).
- Trust boundaries, data ownership and failure behavior are stated.
- Security constraints and acceptance tests are defined.
- Open questions are listed with an owner and target phase.
- Another engineer can implement without inventing architecture.

Design complete does **not** mean the design is perfect. It means it is safe to start and
changes require an ADR.

---

## 4. P0 implementation order (next 2 weeks)

### Week 1

1. Create monorepo directories and toolchain files (`pyproject.toml`, `package.json`,
   `Cargo.toml`, lockfiles).
2. Add CI skeleton: lint, typecheck, unit, secret scan, dependency scan, docs link check.
3. Add `infrastructure/docker/compose.base.yml` + `compose.dev.yml`.
4. Add `configs/chains.yaml` with the registry schema and a deny-by-default validator.
5. Add `infrastructure/network_policy/` skeleton and a negative test harness.
6. Add `.env.example` with secret **references**, never values.

### Week 2

1. Implement chain registry validation + tests (G1-01/02/18).
2. Implement health endpoints and service boot checks (G0-01).
3. Add PostgreSQL + Alembic baseline with `identity` and `system` schemas.
4. Implement local auth + projects skeleton (G0-03/05/07).
5. Add job/outbox tables and a no-op relay.
6. Add audit table with append-only grants and hash field.
7. Add the first observability dashboard (API, queues, DB).
8. Write the P0 exit report with evidence links.

---

## 5. Definition of P0 done

- `docker compose up` starts the Dev zone on a clean machine.
- CI blocks a committed secret and a mainnet chain ID.
- Migrations apply to an empty database and roll forward.
- Login, project creation and cross-tenant denial work.
- Audit records a privileged action and verifies its hash.
- A chain registry with `kind: mainnet` fails startup.
- Docs link check passes.
- No feature claims isolation that only exists on a single dev host.

---

## 6. Immediate risks

| Risk | Action |
| --- | --- |
| Designing forever | Timebox P0 to 2 weeks; start P1 vertical slice |
| Docker Desktop isolation illusion | Run gates on the four-VM topology |
| Secret leakage in scaffolding | `.env.example` uses refs; CI secret scan from day one |
| Scope creep in auth | Local auth only in P0; OIDC deferred |
| Chain config drift | Registry validation + `verified_at` + tests |

---

## 7. Next decision points

1. OIDC provider choice (P1).
2. gVisor vs Firecracker for high-risk sandboxes (P3).
3. OpenBao adoption (v0.5).
4. ClickHouse vs PostgreSQL for benchmark series (P4).
5. Model provider data-retention policy (P5).
6. External security review scope (pre-v1.0).
