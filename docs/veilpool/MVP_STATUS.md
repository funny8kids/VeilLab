# VeilPool MVP Status

**Status:** Local mock MVP + local Anvil slice + browser Groth16 proof flow
**Date:** 2026-11-03
**Scope:** [MVP_SCOPE.md](MVP_SCOPE.md) · [ZK Circuit Spec](ZK_CIRCUIT_SPEC.md) · [ZK Contract Integration](ZK_CONTRACT_INTEGRATION.md)

---

## 1. What is implemented

| Component | Path | Status |
| --- | --- | --- |
| Solidity contracts | `contracts/` | `VeilPool` + `MockVerifier`; 53 Foundry tests passing |
| Real-proof path | `contracts/src/VeilPoolPoseidon.sol`, `apps/web/src/lib/prover.ts` | Poseidon tree + Groth16 adapter + browser prover; real proof verified on the EVM and through the local API |
| FastAPI backend | `apps/api/` | Mock + local modes; 107 pytest tests passing |
| React/Vite web app | `apps/web/` | 8 screens, EN/中文, dark/light, note v2, encrypted vault, browser Groth16 prover; 86 Vitest tests passing |
| Browser E2E | `tests/e2e/` | 3 mock smoke tests + local deposit spec + full local Groth16 proof spec |
| Chain indexer | `apps/indexer/` | Anvil JSON-RPC → SQLite, reorg rollback/replay, read API, Poseidon path API; 29 pytest tests passing |
| ZK circuit | `circuits/` | Depth-20 Poseidon membership circuit; compiled, proved and verified with a development setup |
| Docs link check | `scripts/check_docs.py` | 0 broken local links |
| CI | `.github/workflows/ci.yml` | API, indexer, web, contracts, E2E and docs jobs |
| Local infra | `infrastructure/` | Anvil deploy script, Compose skeleton and env example |

### Modes

| Mode | Chain source | Verifier | Use |
| --- | --- | --- | --- |
| `mock` (default) | SQLite `MockChain` | `MockVerifier` | Product demo, web/E2E |
| `local` | Local Anvil + standalone indexer | `MockVerifier` or `Groth16VerifierAdapter` | Local chain integration |
| real-proof path | `VeilPoolPoseidon` + browser prover | `Groth16VerifierAdapter` | Local Groth16 proof flow |

`local` is still **not production-private**: the default deploy uses the non-cryptographic
`MockVerifier`. The real-proof path uses a single-machine development zkey and is unaudited.

---

## 2. Verified end-to-end

### 2.1 Mock product flow

- Web loads pools/relayers/policy from the mock API.
- Deposit: note generated client-side, backup gate, intent, mock deposit event, root/leaf
  created, local activity recorded.
- Network inspection: intent and mock-deposit POST bodies contain `commitment` only — no
  `veilnote1`, secret or nullifier secret.
- Withdrawal gate: a note with no matching confirmed deposit is blocked; a note that is still
  maturing is blocked.
- Relayer quote/submit path is implemented against the mock API.
- EN/中文 and dark/light are implemented in the React app.
- Auto-lock: 15 minutes of inactivity, with an honest import-backup recovery path.

### 2.2 Live local Anvil slice

Validated on 2026-11-03 with Foundry/Anvil 1.9.0:

1. `Deploy.s.sol` deployed `MockVerifier` and `VeilPool` on chain 31337 and created the three
   ETH pools.
2. The indexer read `PoolCreated`, `Deposit`, `RootUpdated` and later events into SQLite.
3. The API ran with `VEILPOOL_MODE=local`, read pools/roots/deposits from the indexer, and
   returned `mode:"local"`, `mock:false` and `chain_data_status:"available"`.
4. `POST /api/v1/deposits/intent` returned a pending intent with
   `next_step:"POST /api/v1/local/deposits"` and no completion claim.
5. `POST /api/v1/local/deposits` sent the deposit through Anvil account 0, waited for the
   indexer, and returned the confirmed deposit with `tx_hash`, `block_number`,
   `local_chain:"ANVIL"`, `indexer_lag:0`.
6. Repeating the same local-deposit call returned the same transaction without a second send.
7. The indexer's deposit list and the API pool overlay reflected the new leaf and root.
8. The web app detected `ANVIL LOCAL`, routed the deposit to `/api/v1/local/deposits`, showed
   “Local deposit confirmed” with the transaction hash and block number, and the local
   Playwright spec passed without sending the note.
9. The second browser deposit was indexed as leaf 1; the API and indexer deposit lists agreed.

Recorded live values:

| Field | Value |
| --- | --- |
| Contract | `0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512` |
| Pool | `pool_eth_01` |
| Deposit tx | `0x44c0c6465269560c7e66acdb331d1f123c3d1dbb3dd567e62d41b95efddca95b` |
| Deposit block | 4 |
| Indexed leaf | 0 |
| Indexer lag at confirmation | 0 |

The indexer workstream also exercised a live two-block reorg: it found the common ancestor,
rolled back the reorged withdrawal, replayed canonical blocks and kept the earlier deposit
canonical.

### 2.3 Real Groth16 proof on the EVM

The separate `VeilPoolPoseidon` spike verifies the actual circuit proof (not a mock shape):

- Circuit: depth 20, 6 public signals, 14,569 constraints.
- Fixture: `chain_id=11155111`, `pool_eth_01`, eight leaves, leaf 5 is the spendable note.
- The contract creates the pool with the right-padded deploy label and maps it to the
  circuit field with `uint256(poolId) >> 8`.
- Depositing the eight fixture leaves reproduces the circuit root exactly.
- The fixture proof is accepted by the generated Groth16 verifier through the adapter.
- The withdrawal pays the fixture recipient, marks the nullifier spent, and a replay reverts
  with `NullifierAlreadySpent`.
- Tampered root/nullifier/recipient/fee/pool/chain and malformed proofs are rejected.

Important finding: the generated `circuits/build/Verifier.sol` originally did not match the
final zkey (stale `IC0`/delta constants). Off-chain `snarkjs` verification passed, but the
on-chain pairing check failed. The verifier was regenerated from
`membership_0001.zkey`; the stale file is kept as `circuits/build/Verifier.stale.sol`.

### 2.4 Live real-proof withdrawal (local Anvil)

On 2026-11-03 the full local proof path was exercised with Foundry/Anvil 1.9.0:

1. `DeployPoseidon.s.sol` deployed `Groth16VerifierAdapter`, the generated verifier and
   `VeilPoolPoseidon`; it created the maturity-0 `pool_eth_01` spike pool.
2. A chain-31337 proof was generated from `circuits/scripts/gen-local-fixture.mjs` and the
   development zkey; `snarkjs groth16 verify` returned `OK!`.
3. One deposit reproduced the proof root exactly; the indexer path API returned the same root,
   leaf index and 20 path elements.
4. Direct `cast send withdraw(...)` with the real proof succeeded (gas `339,388`).
5. The API path proxy and `POST /api/v1/local/withdrawals` were tested with a three-leaf tree:
   a new proof for leaf 2 was broadcast through the API, confirmed by the indexer and returned
   with `status:"confirmed"`, tx
   `0x966e2c91983b051bb2fe5122fd8f6aea0d70efb8e270482b3b5ba75a8178f6bf`, block 9, fee
   `240000000000000` and recipient balance `0.09976 ETH`.
6. Replaying the same quote returned the stored withdrawal; reusing the nullifier with a new
   quote returned `409 NULLIFIER_SPENT`.
7. A deliberately invalid proof produced a reverted transaction and `502 WITHDRAWAL_REVERTED`
   with the tx hash, block and gas used; the quote stayed active instead of being consumed.
8. A second live run deposited leaf 3 and withdrew through the API (tx
   `0x8102874bb03287e0a4b7b8a759d00e80bdac696c82bf1c40f3d819e7abe6d49b`, block 11).
9. The browser flow then generated a v2 note, deposited through the API, fetched the path,
   proved the withdrawal in a Web Worker, and submitted it through the API. The Playwright
   spec passed in 5.9 s total (deposit + quote + proof + withdrawal), with no note or witness
   in any POST body. Recorded tx
   `0x3f332a1139a192ae2ad9b2f7c558cd9f37674d5ce41b9308f99f9208a2002460`, block 18, recipient
   `0x4444444444444444444444444444444444444444`.

This is the first end-to-end **real Groth16 proof** path in the repository. It still uses a
development zkey, an unaudited circuit/Poseidon implementation and a maturity-0 local pool; it
is not a production deployment.

---

## 3. Test evidence

| Suite | Result |
| --- | --- |
| Contract Foundry | **53 passed** (22 original + 17 Groth16 + 14 Poseidon pool) |
| API pytest | **107 passed** |
| Indexer pytest | **29 passed** |
| Web Vitest | **86 passed** |
| Browser Playwright | **3 mock passed + 2 local Anvil specs passed** (local specs are skipped unless `VEILPOOL_LOCAL_E2E=1`) |
| Circuit verifier negatives | **11/11 passed** |
| Circuit witness negatives | **11/11 passed** |
| Circuit compile/witness/prove/verify | success; `OK!` |
| Docs links | 0 broken |
| Web production build | **passed** (475.94 KB main JS / 163.39 KB gzip; 46.27 KB CSS; worker 1.99 KB; snarkjs chunk 455.16 KB loaded on demand) |

Contract tests include deposit amount, duplicate nullifier, pause/resume, root window,
maturity before/at/after, fee cap, failed transfer rollback and mock proof mismatch, plus the
real-proof adapter and Poseidon tests.

Circuit timings from the native CLI were roughly 1.1 s prove / 0.64 s verify, including Node
startup. This is **not** a browser/WASM benchmark.

---

## 4. What is still mock or limited

- **Default verifier:** `MockVerifier` performs no cryptography. It accepts a correctly
  encoded copy of the public signals.
- **Default chain:** mock mode records synthetic events in SQLite; no RPC or broadcast.
- **Local mode:** real Anvil events. The default local deploy uses `MockVerifier`; the
  Poseidon spike uses `Groth16VerifierAdapter`. The deposit/withdraw bridges use the local
  Anvil unlocked account only when the corresponding auto flags are enabled.
- **Local withdrawals:** bridged through a dev-only Anvil endpoint that accepts a real 256-byte
  Groth16 proof. It is not a production non-custodial relayer; the API uses Anvil's unlocked
  account and does not custody notes.
- **Real-proof path:** development zkey, unaudited Poseidon, maturity-0 local pool and very high
  deposit gas (~14.2M). The full browser note → deposit → proof → withdrawal flow works
  locally, but it is not a production deployment.
- **Maturity override:** `VEILPOOL_LOCAL_MATURITY_SECONDS=0` is a local spike setting to match
  the Poseidon deploy; it is not a product default.
- **Compliance:** deterministic fixtures, not a sanctions provider.
- **Relayers:** fixtures and mock quote/submit records; no external relayer gateway.
- **Local activity:** browser-only.
- **Auth:** a shared development bearer token, not sessions/CSRF/TOTP.
- **ERC-20:** contract MVP is ETH-only; API seeds USDC/tBTC as mock assets in mock mode and
  retires them in local mode.
- **Reorg reconciliation:** local deposits already stored by the API are not automatically
  removed if the indexer later marks them non-canonical.

---

## 5. Known gaps

### P0 before calling it a real mixer

1. Replace `MockVerifier` with the audited verifier in the deployed pool path.
2. Multi-party trusted-setup ceremony, verifier-key pinning and audit.
3. Harden the browser proof flow for production: artifact hash pinning, memory/performance
   limits, retry/resume, and independent review of the Poseidon/worker boundary.
4. Optimize the Solidity Poseidon implementation and measure production gas.
5. Real relayer gateway, signed quotes, fallback and stuck-transaction handling.
6. Production compliance provider, legal review and review-queue operations.
7. Production authentication/session/CSRF design and key rotation.
8. Reorg reconciliation of stored API rows, external transaction attach, and a production
   non-custodial withdrawal path (the dev bridge is not one).
9. ERC-20 support and per-pool accounting.

### P1 usability

- Faucet/test-asset onboarding.
- Note health check with privacy trade-off.
- QR deposit address.
- Relayer reputation.
- Admin console.
- Mobile/PWA.
- Accessibility audit on every screen; keyboard-first note workflow.

---

## 6. Commands

### Full local verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

### API (mock)

```powershell
cd apps/api
python -m pip install -r requirements.txt
$env:VEILPOOL_MODE = "mock"
$env:VEILPOOL_ADMIN_TOKEN = "dev-admin"
python -m uvicorn veilpool_api.main:app --reload --port 8000
python -m pytest -q
```

### API (local Anvil)

```powershell
$env:VEILPOOL_MODE = "local"
$env:VEILPOOL_CHAIN_ID = "31337"
$env:VEILPOOL_CONTRACT_ADDRESS = "0x..." # printed by Deploy.s.sol
$env:VEILPOOL_INDEXER_URL = "http://127.0.0.1:8100"
$env:VEILPOOL_LOCAL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_LOCAL_AUTO_DEPOSIT = "true"
python -m uvicorn veilpool_api.main:app --port 8000
```

### Contracts

```powershell
cd contracts
forge install foundry-rs/forge-std --no-commit
forge test -vvv
forge fmt --check
```

On this machine, `forge` is available at
`%LOCALAPPDATA%\veilpool-tools\foundry-v1.9.0\forge.exe`.

### Local chain + indexer

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/anvil-deploy.ps1 -InstallDeps
```

### Web and E2E

```powershell
cd apps/web
npm.cmd run build
npm.cmd test

cd ../../tests/e2e
npm.cmd test
```

### Local Groth16 browser E2E

```powershell
# 1. Anvil + DeployPoseidon (maturity 0)
# 2. indexer with INDEXER_VERIFIER_KIND=groth16
# 3. API local with AUTO_DEPOSIT=true, AUTO_WITHDRAW=true,
#    LOCAL_VERIFIER_KIND=groth16, LOCAL_MATURITY_SECONDS=0
# 4. copy the circuit artifacts
cd circuits
node scripts/export-web-artifacts.mjs

# 5. start the web dev server, then:
cd ../tests/e2e
$env:VEILPOOL_LOCAL_E2E = "1"
npm.cmd test -- local-proof.spec.ts
```

The spec asserts a v2 note deposit, a browser Web Worker proof, a confirmed local withdrawal,
and that no note/witness/secret appears in any POST body. It is skipped unless
`VEILPOOL_LOCAL_E2E=1`.

### Circuits

See [`circuits/README.md`](../../circuits/README.md) for the full toolchain, fixture generation,
development trusted setup, browser artifact export and negative tests.

---

## 7. Next milestone

**M3 · Production hardening**

- Replace the reference Poseidon loop with an optimized, reviewed implementation and add gas
  regression tests.
- Run a multi-party trusted-setup ceremony, pin the verifier key and audit the circuit, adapter,
  pool and browser prover.
- Harden the local bridge into a real non-custodial relayer design (auth, signed quotes,
  fallback, reorg reconciliation).
- Add artifact hash pinning and browser proving performance/memory budgets.
- Replace fixture compliance with a real provider and complete legal review.

Until then, keep the local demo labeled `MOCK VERIFIER` / `DEVELOPMENT ZKEY`.
