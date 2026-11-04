# VeilPool MVP Scope

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-03
**Target:** first runnable local vertical slice

---

## 1. Goal

Deliver a locally runnable VeilPool demo that exercises the full product loop:

```text
pools → deposit intent → note backup gate → mock deposit
→ maturity → mock proof → relayer quote → mock withdrawal
→ activity → compliance decision
```

The MVP proves the **product and data boundaries**. It does **not** claim a real ZK mixer,
real chain custody or production privacy.

---

## 2. Hard boundaries

1. Testnet/local only. No mainnet RPC, signing or broadcast.
2. No note is sent to the API. No server-side note table.
3. Mock cryptography is labeled `MOCK` in API, UI and README.
4. Compliance decisions are deterministic fixtures, not a real sanctions provider.
5. No real funds, no production keys.
6. The UI must show an explicit “Local demo / mock proof” state when mock mode is on.

---

## 3. Components

| Component | Path | Deliverable |
| --- | --- | --- |
| Solidity contracts | `contracts/` | `VeilPool`, `MockVerifier`, `IVerifier`, Merkle/nullifier logic, Foundry tests |
| Real-proof spike | `contracts/src/VeilPoolPoseidon.sol` | Poseidon tree, Groth16 adapter, circuit fixtures and tests |
| API | `apps/api/` | FastAPI, SQLite mock chain, local Anvil mode, pools/deposit/withdraw/relayers/compliance/health |
| Indexer | `apps/indexer/` | Anvil JSON-RPC collector, SQLite store, reorg handling, read API |
| Web | `apps/web/` | React + Vite, 8 screens, EN/ZH, dark/light, note vault, API client |
| Circuits | `circuits/` | Depth-20 Poseidon membership circuit, fixtures and development Groth16 setup |
| Infra | `infrastructure/` | Compose skeleton, Anvil deploy script, env example |
| Tests | `tests/` | API tests, indexer tests, contract tests, E2E smoke, boundary cases |
| CI | `.github/workflows/ci.yml` | Python, web, contract, E2E and docs jobs |

---

## 4. API minimum

- `GET /api/v1/health`
- `GET /api/v1/pools`
- `GET /api/v1/pools/{id}`
- `GET /api/v1/pools/{id}/root`
- `POST /api/v1/deposits/intent`
- `GET /api/v1/deposits/{tx_hash}`
- `GET /api/v1/relayers`
- `POST /api/v1/withdrawals/quote`
- `POST /api/v1/withdrawals/submit`
- `GET /api/v1/withdrawals/{id}`
- `GET /api/v1/compliance/policy`
- `POST /api/v1/admin/pools/{id}/pause` (dev token)
- `POST /api/v1/admin/pools/{id}/resume` (dev token)

No `/notes`, no note fields, no `/activity` server endpoint.

---

## 5. Web minimum

- Overview: pools, anonymity set, compliance, recent activity
- Deposit: pool selection, note generation/backup gate, mock deposit
- Withdraw: note input, recipient, relayer, mock proof/submit
- Pools: cards with set size, fee, maturity
- Activity: local-only list from browser storage
- Relayers: list and selection
- Compliance: policy and decision explanation
- Settings: testnet only, note backup, theme/language

The existing `prototype/` is the visual reference. Reuse its tokens and layout.

---

## 6. Mock mode

`VEILPOOL_MODE=mock`:

- `MockChain` records deposits/withdrawals in SQLite.
- `MockVerifier` accepts a deterministic test proof shape; it is **not** cryptographic.
- Maturity can be shortened via env for tests.
- The UI displays `MOCK PROOF` and `LOCAL DEMO`.

`VEILPOOL_MODE=local`:

- Local Anvil + deployed contracts; `MockVerifier` remains non-cryptographic.
- The standalone indexer reads `Deposit` / `RootUpdated` / withdrawal events.
- `POST /api/v1/local/deposits` can bridge a deposit through the local Anvil unlocked
  account when `VEILPOOL_LOCAL_AUTO_DEPOSIT=true`; the server never accepts a private key.
- Withdrawals use a dev-only Anvil bridge that accepts a real 256-byte Groth16 proof; it is
  not a production non-custodial relayer.
- Still no mainnet and no real ZK.

The separate real-proof spike (`VeilPoolPoseidon` + `Groth16VerifierAdapter`) is exercised by
Foundry only. It is not wired into the API or web app.

---

## 7. Definition of done

- `python -m pytest` passes API and indexer tests.
- `npm run build` passes web build.
- `forge test` passes; the real fixture proof is verified on the EVM.
- A user can complete deposit → maturity → withdrawal in mock mode from the UI.
- The browser network log contains no note.
- No note in SQLite, logs or fixtures.
- README has exact run commands.
- Known gaps are listed explicitly (production ZK, relayer, compliance provider, local withdrawal bridge).

---

## 8. Out of scope for this MVP

- Production Groth16/PLONK ceremony, audit and verifier-key management.
- Wiring the real-proof spike into the API/web/indexer and local proving.
- Production sanctions provider and legal review.
- Production key management.
- Mainnet.
- Mobile layout.
