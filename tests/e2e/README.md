# VeilPool E2E

Local mock MVP browser tests using Playwright with the installed Chrome channel.

```powershell
cd tests/e2e
npm.cmd install
npm.cmd test
```

The config starts:

- API at `http://127.0.0.1:8000` with a separate `veilpool-e2e.db`
- Web dev server at `http://127.0.0.1:5173`

If servers are already running, Playwright reuses them. The tests cover:

- deposit flow: note generation, backup gate, intent + mock deposit, UI result;
- network assertion: no `veilnote1`, `nullifierSecret` or `secret` field in POST bodies;
- withdraw page smoke;
- EN/中文 and dark/light toggles.

No real funds, no real ZK, no mainnet.

## Local Anvil mode (optional)

The API can run against a local Anvil chain and the standalone indexer. Start Anvil, deploy
`contracts/script/Deploy.s.sol`, start the indexer, then start the API with:

```powershell
$env:VEILPOOL_MODE = "local"
$env:VEILPOOL_CHAIN_ID = "31337"
$env:VEILPOOL_CONTRACT_ADDRESS = "0x..." # printed by the deploy script
$env:VEILPOOL_INDEXER_URL = "http://127.0.0.1:8100"
$env:VEILPOOL_LOCAL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_LOCAL_AUTO_DEPOSIT = "true"
python -m uvicorn veilpool_api.main:app --port 8000
```

Start the web dev server, then run the local spec:

```powershell
$env:VEILPOOL_LOCAL_E2E = "1"
npm.cmd test -- local.spec.ts
```

The spec checks health is `mode:"local"`, completes a deposit through the local bridge, and
asserts the note never appears in a POST body. It does not sign transactions itself; the API's
dev bridge uses Anvil's unlocked account. `MockVerifier` is still non-cryptographic.
