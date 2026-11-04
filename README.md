# VeilLab

**VeilPool · Private Pool & Mixer**

Fixed-denomination privacy pools · Non-custodial relayers · Compliance-aware · **Testnet Only**

> **Status:** Local mock MVP + local Groth16 proof flow implemented · 2026-11-03
>
> **Direction update:** VeilLab is now focused on **VeilPool**, a testnet-only private pool /
> mixer. The `prototype/` directory reflects this mixer-first product. The older research
> documents remain available as supporting/legacy material and are not the current product
> architecture.
>
> **Implemented today:** Solidity contracts with Foundry tests, a real Poseidon/Groth16 proof
> path, a browser Web Worker prover, a FastAPI local/mock API, a React/Vite web app, a
> standalone chain indexer with Merkle paths, browser E2E tests and CI. The default product
> still uses `MOCK_CHAIN`, `MOCK_VERIFIER` and `MOCK_FIXTURES`; the real-proof path uses a
> development zkey and is unaudited. There is **no production security, anonymity guarantee,
> real relayer network, production compliance provider or mainnet path**.

---

## 1. What VeilLab is

VeilLab is building **VeilPool**, a privacy pool for testnet assets:

- **Fixed-denomination pools** - ETH, USDC and tBTC test assets with independent anonymity sets.
- **Deposit with a secret note** - the note is the withdrawal credential and never leaves the user.
- **Non-custodial relayers** - submit withdrawal proofs without seeing notes or controlling funds.
- **Compliance-aware flows** - sanctions screening, jurisdiction checks and daily limits on deposit and withdrawal.
- **Testnet-only execution** - no mainnet RPC, signing or broadcast path exists.
- **Supporting research infrastructure** - evidence, benchmarks and protocol profiles remain available as back-office tooling, not the product surface.

## 2. Non-negotiable principles

1. **Testnet Only** - every pool, transaction and contract interaction is restricted to local chains and approved testnets.
2. **The note belongs to the user** - the product never custodies notes, keys or funds; relayers cannot see notes.
3. **Compliance by design** - screening, limits and audit are part of the deposit and withdrawal flows.
4. **Privacy claims must be honest** - show anonymity-set size, maturity and timing guidance; never promise "untraceable".
5. **Security by Design** - network, identity, data and execution isolation exist from day one.

Mainnet execution is not disabled by a feature flag; it **does not exist** as a code path,
configuration option, RPC registration or signing capability. See
[`docs/security/TESTNET_ONLY_POLICY.md`](docs/security/TESTNET_ONLY_POLICY.md).

## 3. Architecture in one line

**Product app + proof worker + non-custodial relayer gateway + compliance engine + testnet-only chain gateway**, with the research modules kept as optional back-office infrastructure.

- Web app: React/Vite console (`apps/web`) with local note handling, note v2 Poseidon commitments and a Web Worker Groth16 prover.
- Business plane: FastAPI modular monolith (`apps/api`) for pools, deposits, withdrawals, relayers and compliance, with mock and local Anvil modes.
- Local chain indexer: standalone Python service (`apps/indexer`) that reads Anvil events into SQLite and serves Merkle paths.
- Contracts: `VeilPool`, `MockVerifier`, and the real-proof `VeilPoolPoseidon` + `Groth16VerifierAdapter` spike.
- Circuits: depth-20 Poseidon membership circuit (`circuits/`) with a development Groth16 setup and browser artifacts.
- Testnet: local Anvil and approved testnets; no mainnet RPC, signing or broadcast path.
- Data: SQLite for the local MVP; PostgreSQL/Redis/MinIO remain the target deployment shape.

## 4. Documentation map

### Current product baseline

| Document | Purpose |
| --- | --- |
| [`docs/veilpool/README.md`](docs/veilpool/README.md) | VeilPool documentation index |
| [`docs/veilpool/PRODUCT_SPEC.md`](docs/veilpool/PRODUCT_SPEC.md) | Users, flows, screens, scope, metrics |
| [`docs/veilpool/POOL_MODEL.md`](docs/veilpool/POOL_MODEL.md) | Denominations, notes, nullifiers, maturity, fees, relayers |
| [`docs/veilpool/ARCHITECTURE.md`](docs/veilpool/ARCHITECTURE.md) | Components, trust zones, contracts, failure modes |
| [`docs/veilpool/DATA_MODEL.md`](docs/veilpool/DATA_MODEL.md) | PostgreSQL schema, client-only notes, retention |
| [`docs/veilpool/API_SPEC.md`](docs/veilpool/API_SPEC.md) | Public, relayer and admin endpoints |
| [`docs/veilpool/COMPLIANCE.md`](docs/veilpool/COMPLIANCE.md) | Screening, limits, review, audit |
| [`docs/veilpool/THREAT_MODEL.md`](docs/veilpool/THREAT_MODEL.md) | Mixer-specific threats and mitigations |
| [`docs/veilpool/TEST_PLAN.md`](docs/veilpool/TEST_PLAN.md) | Test matrix, boundaries, gates, traceability |
| [`docs/veilpool/FEATURE_OPTIMIZATION.md`](docs/veilpool/FEATURE_OPTIMIZATION.md) | Prioritized backlog and usability checklist |
| [`docs/veilpool/MVP_SCOPE.md`](docs/veilpool/MVP_SCOPE.md) | First runnable local vertical slice and mock boundaries |
| [`docs/veilpool/MVP_STATUS.md`](docs/veilpool/MVP_STATUS.md) | Implementation status, test evidence and gaps |
| [`docs/veilpool/ZK_CIRCUIT_SPEC.md`](docs/veilpool/ZK_CIRCUIT_SPEC.md) | Real membership circuit and verifier specification |
| [`docs/veilpool/ZK_CONTRACT_INTEGRATION.md`](docs/veilpool/ZK_CONTRACT_INTEGRATION.md) | Poseidon/Groth16 contract spike and real proof evidence |
| [`prototype/index.html`](prototype/index.html) | Interactive VeilPool prototype (8 screens, EN/中文, dark/light) |
| [`prototype/screenshots/theme-compare.png`](prototype/screenshots/theme-compare.png) | Dark/light and bilingual comparison |
| [`prototype/screenshots/map-dark.png`](prototype/screenshots/map-dark.png) | Dark prototype map |

### Safety constraint (still binding)

- [`docs/security/TESTNET_ONLY_POLICY.md`](docs/security/TESTNET_ONLY_POLICY.md) - no mainnet RPC, signing or broadcast.

### Legacy research baseline

Everything under `docs/architecture/`, `docs/security/` (except the testnet-only policy),
`docs/database/`, `docs/api/`, `docs/research/`, `docs/roadmap/` and `docs/adr/` describes the
earlier research platform. It is kept for reference and selective reuse; it is not the current
product architecture.

## 5. Run the MVP (local mock)

This is a **local mock vertical slice**: no real ZK, no real chain, no real funds.

### API

```powershell
cd apps/api
python -m pip install -r requirements.txt
$env:VEILPOOL_MODE = "mock"
$env:VEILPOOL_ADMIN_TOKEN = "dev-admin"
python -m uvicorn veilpool_api.main:app --reload --port 8000
```

### Web

```powershell
cd apps/web
npm.cmd install
npm.cmd run dev
```

Open <http://127.0.0.1:5173/overview>.

### Contracts

```powershell
cd contracts
forge install foundry-rs/forge-std --no-commit
forge test -vvv
```

Foundry is available locally at
`%LOCALAPPDATA%\veilpool-tools\foundry-v1.9.0\forge.exe` in this workspace; see
[`docs/veilpool/MVP_STATUS.md`](docs/veilpool/MVP_STATUS.md) for the current test evidence.

### Local chain + indexer (optional)

```powershell
# Terminal 1: Anvil (chain ID 31337 only)
anvil --host 127.0.0.1 --port 8545 --chain-id 31337

# Terminal 2: deploy contracts (uses Anvil's unlocked account #0; no private key)
cd contracts
# `--unlocked --sender` asks Anvil to sign from its unlocked test account.
forge script script/Deploy.s.sol:Deploy --rpc-url http://127.0.0.1:8545 --broadcast --unlocked --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 -vv

# Terminal 3: index public events
cd apps/indexer
$env:ANVIL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_ADDRESS = "0x..." # printed by the deploy script
python -m veilpool_indexer

# Terminal 4 (optional): API in local-chain mode
cd apps/api
$env:VEILPOOL_MODE = "local"
$env:VEILPOOL_CHAIN_ID = "31337"
$env:VEILPOOL_CONTRACT_ADDRESS = "0x..." # printed by the deploy script
$env:VEILPOOL_INDEXER_URL = "http://127.0.0.1:8100"
$env:VEILPOOL_LOCAL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_LOCAL_AUTO_DEPOSIT = "true"
python -m uvicorn veilpool_api.main:app --port 8000
```

`VEILPOOL_LOCAL_AUTO_DEPOSIT=true` uses Anvil's unlocked account 0 for a local demo deposit.
It is not a custody design and never accepts a private key. Local withdrawals and the real ZK
prover are not wired yet; the on-chain verifier remains `MockVerifier` in this path.

### Real proof browser flow (local spike)

```powershell
# Deploy the Poseidon pool instead of the mock pool
cd contracts
forge script script/DeployPoseidon.s.sol:DeployPoseidon --rpc-url http://127.0.0.1:8545 --broadcast --unlocked --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 -vv

# Copy the development wasm/zkey into the web app
cd ../circuits
node scripts/export-web-artifacts.mjs

# Start the API with auto-deposit/withdraw and GROTH16 labels, then run:
cd ../tests/e2e
$env:VEILPOOL_LOCAL_E2E = "1"
npm.cmd test -- local-proof.spec.ts
```

The full flow generates a note v2, deposits through the local bridge, proves in a Web Worker and
withdraws through the API. The zkey is a single-machine development setup; do not treat it as a
ceremony or production key.

### E2E

```powershell
cd tests/e2e
npm.cmd install
npm.cmd test
```

The E2E config starts the mock API and web dev server automatically. It asserts that the
deposit flow works and that POST bodies never contain the note/secret material.

### Full local verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

## 6. Repository layout

```text
apps/
  api/        FastAPI business API and mock chain
  web/        React/Vite product UI
  indexer/    Anvil event indexer and read API
contracts/    Solidity contracts and Foundry tests
circuits/     Circom membership circuit, fixtures and Groth16 spike
tests/e2e/    Playwright browser tests
prototype/    Interactive 8-screen product prototype
docs/         Product, architecture, compliance, test and ZK documents
infrastructure/  Local Anvil/Compose skeleton
scripts/      Documentation and verification helpers
```

The current product deployment units are defined in
[`docs/veilpool/ARCHITECTURE.md`](docs/veilpool/ARCHITECTURE.md). The older full repository
layout in `docs/architecture/SYSTEM_ARCHITECTURE.md` is legacy.

## 7. Contributing to the design

- Normative keywords **MUST / SHOULD / MAY** follow RFC 2119 semantics.
- Product/architecture changes update `docs/veilpool/` in the same PR.
- Security-relevant changes require review against
  [`docs/veilpool/THREAT_MODEL.md`](docs/veilpool/THREAT_MODEL.md).
- A feature is not "done" until its cases and boundaries are defined in
  [`docs/veilpool/TEST_PLAN.md`](docs/veilpool/TEST_PLAN.md).
- Mainnet, note storage and server-side proving are out of scope by design.

## 8. License

TBD before the first public release.
