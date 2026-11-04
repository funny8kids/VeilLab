# VeilPool Feature Optimization

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [Product Spec](PRODUCT_SPEC.md) · [Test Plan](TEST_PLAN.md)

---

## 1. What “real usability” means

A user can complete the full loop without a founder on a call:

1. Connect a testnet wallet.
2. Understand the pool and anonymity set.
3. Generate and safely back up a note.
4. Deposit and see confirmation.
5. Wait for maturity without guessing.
6. Recover the note after a refresh or device restart.
7. Generate a proof and choose a working relayer.
8. Withdraw to a fresh address.
9. Understand a block/review decision.
10. Recover from a failed transaction or reorg.

If any step needs a manual database edit, the product is not usable.

---

## 2. Priority matrix

| Priority | Feature | Impact | Effort | Why |
| --- | --- | --- | --- | --- |
| P0 | Encrypted note vault + backup/import | Very high | M | Without it, funds are lost on refresh |
| P0 | Testnet wallet + network guard | Very high | S | Wrong network is the top user error |
| P0 | Deposit status + maturity countdown | Very high | S | Users need to know when withdrawal is possible |
| P0 | Local proof worker with progress | Very high | M | Proof generation is the core action |
| P0 | Relayer fallback + fee quote | High | M | A single relayer is a single point of failure |
| P0 | Compliance allow/review/block UX | High | M | Policy must be understandable |
| P0 | Reorg-safe indexer + stale-root UX | High | M | False “confirmed” erodes trust |
| P0 | Note isolation tests in CI | Very high | S | Prevents catastrophic leakage |
| P0 | Error taxonomy + request IDs | High | S | Makes support possible |
| P1 | Note health check (privacy-preserving) | High | M | “Is this note spent?” without leaking it |
| P1 | Withdrawal scheduling / timing guidance | Medium | S | Reduces timing correlation |
| P1 | QR deposit address | Medium | S | Better deposit UX |
| P1 | Relayer reputation / uptime history | Medium | S | Better selection |
| P1 | Admin console (pause, limits, review) | High | M | Operability |
| P1 | Observability + alerts | High | M | Detect balance/indexer issues |
| P1 | Address book / fresh-address helper | Medium | S | Reduces address reuse |
| P2 | Multiple proof backends (WASM/native) | Medium | M | Performance/portability |
| P2 | Proof aggregation / batching | Medium | L | Scale, not v1 |
| P2 | PWA / mobile layout | Medium | M | Access |
| P2 | Localization beyond EN/ZH | Low | S | Reach |
| P2 | Cross-chain testnet pools | Low | L | Complexity, not v1 |

---

## 3. P0 details

### 3.1 Encrypted note vault

- WebCrypto AES-GCM with a random session key held in `sessionStorage`; the key is not
  recoverable after tab close.
- IndexedDB stores ciphertext only; the session key never leaves the browser.
- Auto-lock after 15 minutes of inactivity; refresh preserves the session key, tab close
  discards it. Recovery requires an encrypted backup import; there is no password unlock.
- Export/import encrypted file; never plaintext CSV.
- Show an “unbacked” warning before deposit.
- Never place notes in `localStorage` or URL.

### 3.2 Wallet and network guard

- Only approved testnet chain IDs.
- Verify `eth_chainId` after connect and before every transaction.
- If wrong network: block, explain, offer switch.
- No “add mainnet” path.
- Handle account/network change events.

### 3.3 Deposit status and maturity

- Show `submitted → confirmed → matured` with block/confirmation.
- Maturity countdown based on chain time, not device clock alone; show drift warning.
- Disable withdraw until maturity; allow “notify me” later.
- Show the exact pool and denomination.

### 3.4 Local proof worker

- Run in a Web Worker/WASM; never send note or witness to the server.
- Show phase progress (`loading tree → building witness → proving → verifying`).
- Allow cancel; do not corrupt the vault.
- Cache the tree path safely; invalidate on root change.
- On failure, preserve note and show a deterministic error code.

### 3.5 Relayer fallback

- Quote includes relayer ID, fee, expiry and supported pools.
- On timeout/offline, offer at least two alternatives.
- Keep the proof local; do not regenerate unless the root changed.
- Show “submitted via Relay-02” in the receipt.
- Detect stuck tx and offer replacement/retry without double-spend.

### 3.6 Compliance UX

- Show decision before the wallet/proof action.
- `allow` → proceed; `review` → pause with SLA; `block` → stable code + support ID.
- Never show a vague “something went wrong”.
- Provide a “why?” panel with policy version and reason codes.
- Do not ask for a note.

### 3.7 Reorg-safe indexer

- Show confirmations and finality.
- If a reorg affects a deposit/withdrawal, mark `pending` and explain.
- Rebuild roots from events; compare to chain root.
- Block withdrawal on stale root.
- Alert on balance mismatch.

### 3.8 Error taxonomy

Examples:

```text
NOTE_INVALID
NOTE_UNBACKED
NOTE_SPENT
POOL_PAUSED
MATURITY_NOT_REACHED
ROOT_STALE
PROOF_FAILED
PROOF_INVALID
RELAYER_OFFLINE
QUOTE_EXPIRED
COMPLIANCE_BLOCKED
COMPLIANCE_REVIEW
LIMIT_EXCEEDED
CHAIN_NOT_ALLOWED
TX_REVERTED
INDEXER_LAG
```

Each error has: user message, cause, next action, support code, retryable flag.

---

## 4. P1 details

### 4.1 Note health check

Problem: users want to know if a note is spent without exposing it.

Options:

- Query by nullifier (leaks a link between note and API).
- Local activity + public tx lookup (no extra leak).
- Batched/anonymous nullifier check (privacy-preserving but complex).

Recommendation: default to local activity; offer an explicit “check on-chain” action with a
warning. Do not log the nullifier with a user ID.

### 4.2 Withdrawal timing

- Show “recommended wait” based on set size and recent flow.
- Do not force; explain the trade-off.
- Avoid a “withdraw now” dark pattern.

### 4.3 Deposit QR

- QR encodes pool, chain, contract and denomination; never a note.
- Verify chain/pool on scan.
- Expiring deposit intent.

### 4.4 Relayer reputation

- Uptime, median latency, rejection rate, last heartbeat.
- Do not rank by fee alone.
- Show “last successful withdrawal” age.

### 4.5 Admin console

- Pause/resume pool with reason.
- Fee/maturity changes within bounds.
- Compliance review queue.
- Audit search/export.
- Incident banner.

### 4.6 Observability

- Balance reconciliation per pool.
- Nullifier/withdrawal count.
- Indexer lag/reorg.
- Relayer uptime.
- Compliance provider health.
- Note-leak scanner in logs.

### 4.7 Fresh-address helper

- Warn if recipient equals depositor address.
- Suggest “use a fresh wallet/address” without generating keys.
- Do not auto-create wallets.

---

## 5. P2 / later

- Mobile/PWA layout.
- Native CLI for testnet automation.
- Multiple proof backends.
- Proof aggregation.
- Additional testnet assets.
- Cross-chain testnet pools (explicitly out of v1).
- Anonymous nullifier-status service.
- Compliance proofs (research; do not overclaim).

---

## 6. What not to build

- Arbitrary-amount mixing.
- “Untraceable” marketing.
- Mainnet support.
- Custodial note storage.
- Server-side proof generation.
- A server-side deposit→withdrawal graph.
- Auto-withdraw without user confirmation.
- A “privacy score” that hides its inputs.
- Token/yield mechanics.

---

## 7. Suggested sequence

### Phase A · Make it not lose funds

1. Note vault + backup/import.
2. Network guard.
3. Deposit/maturity status.
4. Note isolation tests.

### Phase B · Make it complete

5. Local prover.
6. Relayer quote/fallback.
7. Compliance UX.
8. Reorg-safe indexer.

### Phase C · Make it operable

9. Admin pause/limits.
10. Observability/alerts.
11. Review queue/audit.
12. Support/error taxonomy.

### Phase D · Make it pleasant

13. QR, fresh-address helper, timing guidance.
14. Relayer reputation.
15. Accessibility/localization.
16. Performance tuning.

---

## 8. Real-usability checklist

- [ ] A new user can finish the loop from the UI alone.
- [ ] A refresh does not lose the note.
- [ ] A lost browser can restore from backup.
- [ ] Wrong network is blocked before signing.
- [ ] Withdrawal before maturity is impossible.
- [ ] A relayer outage does not strand the user.
- [ ] A compliance block is explainable.
- [ ] A reorg does not produce a false receipt.
- [ ] Support can diagnose with a request ID.
- [ ] Operators can pause a pool in under a minute.
- [ ] No note appears in network/log/DB/analytics.
- [ ] E2E tests cover the happy path and at least five failure paths.
