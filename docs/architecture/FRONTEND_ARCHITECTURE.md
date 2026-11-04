# Frontend Architecture

**Status:** Draft · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [API_CONVENTIONS](../api/API_CONVENTIONS.md) · [SECURITY_ARCHITECTURE](../security/SECURITY_ARCHITECTURE.md)

---

## 1. Goals

> The console is a **research instrument**, not a Web3 dashboard.
>
> Reference prototype: [`../../prototype/index.html`](../../prototype/index.html) ·
> screen map: [`../../prototype/README.md`](../../prototype/README.md).

- Dense, legible information for long research sessions.
- Every chain view is unmistakably testnet.
- Evidence is one click away from every claim.
- Destructive and signing actions are explicit, reviewable and audited.
- The UI never holds keys, never talks to RPC, and never is the security boundary.

---

## 2. Stack

| Concern | Choice |
| --- | --- |
| Framework | React + TypeScript (strict) |
| Build | Vite |
| Routing | React Router (data router) |
| Server state | TanStack Query |
| Local UI state | Zustand (small, scoped stores) |
| Forms | React Hook Form + Zod |
| UI | Tailwind CSS + shadcn/ui |
| Charts | ECharts |
| API client | Generated from OpenAPI (`packages/sdk-ts`) |
| Real-time | Native WebSocket + reconnect/backoff |
| Testing | Vitest + Testing Library + Playwright |
| Lint/format | ESLint + Prettier + TypeScript strict |

No component library that hides accessibility or forces a marketing aesthetic. No global
state for server data. No `localStorage` for tokens.

---

## 3. Route map

```text
/                              → redirect to /overview
/login                         → local login / OIDC handoff
/overview                      → research + system overview

/research                      → studies list
/research/:studyId             → study detail, experiments, reports
/research/experiments/new      → experiment composer
/research/experiments/:id      → definition, runs, manifest, verification
/research/experiments/:id/runs/:runId → run detail, logs, artifacts

/observatory                   → protocol discovery feed
/observatory/protocols         → registry
/observatory/protocols/:id     → profile, versions, sources, findings

/crypto                        → framework catalog
/crypto/circuits               → circuits
/crypto/circuits/:id           → builds, proofs, benchmarks
/crypto/benchmarks             → comparable benchmark explorer

/chains                        → network health
/chains/:networkId             → head, blocks, txs, reorgs, sync
/chains/:networkId/blocks/:n   → block detail
/chains/:networkId/txs/:hash   → transaction detail

/security                      → assessments and findings
/security/findings/:id         → evidence, reproduction, remediation

/privacy                       → identity / disclosure experiments
/privacy/credentials           → credential schemes and proofs

/veilguard                     → wallets, policies, limits
/veilguard/requests            → transaction requests + simulations
/veilguard/requests/:id        → approval and execution detail
/veilguard/transactions        → reconciliation

/agents                        → agent roster
/agents/tasks                  → task list
/agents/tasks/:id              → steps, tool calls, model usage
/workflows                     → workflow definitions and runs

/data                          → datasets and integrity
/data/datasets/:id             → versions, files, manifests

/plugins                       → installed plugins, permissions
/settings                      → profile, models, API keys, members, audit
/settings/audit                → audit log
/settings/system               → health, queues, feature flags
```

The exact navigation is defined in `apps/web/src/app/navigation.ts`. Routes are lazy-loaded
by feature area.

---

## 4. Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Top bar: workspace · project · TESTNET badge · search · user │
├──────────────┬───────────────────────────────────────────────┤
│ Sidebar      │ Page header (title, status, actions)          │
│              │                                               │
│ WORKSPACE    │ Filters / tabs                                │
│  Overview    │ ┌───────────────────────────────────────────┐ │
│  Research    │ │ Content                                   │ │
│  Observatory │ │                                           │ │
│  Crypto      │ │                                           │ │
│  Chains      │ └───────────────────────────────────────────┘ │
│  Security    │                                               │
│ PRODUCTS     │ Right rail: evidence / metadata / activity    │
│  Privacy     │                                               │
│  VeilGuard   │                                               │
│ AUTOMATION   │                                               │
│  Agents      │                                               │
│  Workflows   │                                               │
│  Data        │                                               │
│ SYSTEM       │                                               │
│  Plugins     │                                               │
│  Settings    │                                               │
└──────────────┴───────────────────────────────────────────────┘
```

- Persistent `TESTNET` badge in the top bar; red accent on any transaction action.
- Status chips use text + icon, never color alone.
- Tables support column density, saved views and CSV/JSON export.
- Detail pages use a two-column layout: primary evidence, secondary metadata.
- Destructive actions live behind a confirmation dialog that states scope and policy.

---

## 5. State management

| State | Tool | Rule |
| --- | --- | --- |
| Server data | TanStack Query | Cache keyed by resource + project; invalidate on events |
| URL state | React Router search params | Filters, pagination, tabs are shareable |
| Ephemeral UI | Zustand | Modals, side panels, local selections |
| Forms | React Hook Form + Zod | Schema mirrors API contracts |
| Auth/session | Query + context | Session from `/auth/me`; no token in JS storage |
| Real-time | Query invalidation | Events invalidate or patch relevant queries |

Rules:

- Do not duplicate server data in Zustand.
- Do not use `useEffect` for data fetching; use Query.
- Every query includes `project_id` context; switching projects clears the cache.
- Optimistic updates are allowed only for reversible UI actions, never for approvals,
  transactions or publication.

---

## 6. API client and errors

- Generate `packages/sdk-ts` from the OpenAPI document in CI.
- Wrap generated calls in feature-level hooks (`useExperiment`, `useRun`).
- Parse `application/problem+json` into a typed `ProblemError`.
- Show `request_id` in every error toast/detail for support.
- Handle `401` by redirecting to login; `403` with a policy explanation; `404` without
  leaking existence; `409` with a conflict diff; `429` with retry-after countdown.
- Long-running actions return `202` + `job_id`/`run_id`; the UI subscribes or polls with
  backoff and links to the detail page.

---

## 7. Authentication and permissions

- Session cookie is `HttpOnly`, `Secure`, `SameSite=Lax`; the UI never reads it.
- CSRF token is provided by the API as a non-HttpOnly cookie or endpoint and sent in
  `X-CSRF-Token` for mutating requests.
- The UI hides actions the user cannot perform, but **the server is authoritative**.
- Permission checks use the `permissions` array from `/auth/me` and project membership.
- Agent capability scopes are never available to the browser.
- On project switch, cancel in-flight queries and reset caches.

---

## 8. Real-time updates

- WebSocket endpoint `/api/v1/ws/events` authenticates via session cookie or short-lived
  WS ticket.
- The client subscribes to project-scoped topics (`research`, `chain`, `veilguard`).
- Events are hints; the client re-fetches authoritative resources. Do not reconstruct
  critical state from event payloads.
- Reconnect with exponential backoff and jitter; on reconnect, refetch active queries.
- Show a subtle "live / reconnecting" indicator, not a blocking spinner.
- Event payloads are filtered server-side; the browser never receives raw internal events.

---

## 9. Visual language

- Dark-first research console; high contrast; monospace for hashes, IDs and code.
- Colors: neutral background, one accent for actions, semantic colors for status.
- Never use color alone for severity; include icon and label.
- Hash/ID component: truncated middle, copy button, full value on hover/focus.
- Evidence component: source type, hash, timestamp, verification badge.
- Testnet component: network name, chain ID, finality state.
- Loading: skeletons for layout, inline spinners for actions.
- Empty states explain what to do and link to docs, not just "No data".
- Error states preserve the last good data and show retry.

---

## 10. Security constraints

| Constraint | Reason |
| --- | --- |
| No private keys, seed phrases or signing in the browser | Agent/user key safety |
| No direct RPC calls | Chain policy and audit |
| No secrets in `localStorage`/`sessionStorage` | XSS exfiltration |
| No `dangerouslySetInnerHTML` for fetched content | Prompt injection/XSS |
| Markdown rendering sanitizes HTML and blocks remote images by default | Tracking/exfiltration |
| Strict CSP: no inline scripts, allowlisted connect-src | XSS containment |
| External links use `rel="noopener noreferrer"` | Tabnabbing |
| File previews are sandboxed; no automatic execution | Malicious artifacts |
| All transaction confirmations show chain ID + testnet badge + simulation hash | Wrong-chain errors |
| Clipboard copy of sensitive values is disabled for restricted fields | Leakage |

The console is not a trust boundary. Hiding a button is UX, not authorization.

---

## 11. Performance

- Route-level code splitting; no single huge bundle.
- Virtualize tables above 200 rows.
- Paginate server-side; never fetch all chain data.
- ECharts instances disposed on unmount; downsample large series.
- Prefetch the next likely route on hover.
- Target: initial JS < 300 KB gzipped, LCP < 2.5 s on LAN.
- Use `staleTime` deliberately: metadata 30–60 s, live chain head 2–5 s, audit immutable.

---

## 12. Accessibility

- Keyboard navigation for all actions; visible focus rings.
- Semantic landmarks and headings.
- Tables have captions and proper headers.
- Dialogs trap focus and restore it on close.
- Charts have a data-table alternative.
- Respect `prefers-reduced-motion`.
- Contrast meets WCAG 2.1 AA.
- Status changes announced via ARIA live regions where appropriate.

---

## 13. Testing

| Level | Scope |
| --- | --- |
| Unit | Pure components, formatters, permission helpers |
| Component | Forms, tables, dialogs, error states |
| Integration | Query hooks + MSW-mocked API |
| E2E | Login, create experiment, run, verify, report; testnet request + approval |
| Visual | Critical screens at two breakpoints |
| Accessibility | axe checks in CI for core routes |

E2E runs against a seeded stack in CI with external network disabled. Testnet flows use a
local Anvil network only.

---

## 14. Directory structure

```text
apps/web/
├── src/
│   ├── app/                 # router, providers, navigation
│   ├── features/
│   │   ├── overview/
│   │   ├── research/
│   │   ├── observatory/
│   │   ├── crypto/
│   │   ├── chains/
│   │   ├── security/
│   │   ├── privacy/
│   │   ├── veilguard/
│   │   ├── agents/
│   │   ├── data/
│   │   ├── plugins/
│   │   └── settings/
│   ├── components/          # shared design system
│   ├── lib/                 # API client, formatting, auth, WS
│   ├── styles/
│   └── main.tsx
├── e2e/
├── public/
├── index.html
├── vite.config.ts
└── package.json
```

Feature folders own their routes, queries, components and tests. Cross-feature imports go
through `components/` or `lib/`, not through another feature's internals.
