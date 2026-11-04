# VeilPool Infrastructure

Testnet/local only. No mainnet RPC, signing or production keys.

## Services

| Service | Purpose | Port |
| --- | --- | --- |
| PostgreSQL 16 | Future API database | 5432 |
| Redis 7 | Future quote cache, rate limits, idempotency | 6379 |
| Anvil | Local EVM chain (chain ID 31337) | 8545 |

The MVP API can run with SQLite and does not require these services. Compose is provided so
the next milestone can switch to Postgres + Anvil without changing the product contracts.

```bash
docker compose -f infrastructure/docker-compose.yml up -d
```

## Local chain slice (Anvil + indexer)

> **MOCK verifier / no real ZK.** The local deployment uses `MockVerifier`, which performs no
> cryptography. It is for a local product demo only. Never use real funds or a mainnet RPC.

With Foundry available (on `PATH`, or in
`%LOCALAPPDATA%\veilpool-tools\foundry-v1.9.0\`), one command starts Anvil (chain ID 31337),
deploys `MockVerifier` + `VeilPool` with the three ETH pools, and runs the read-only indexer:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/anvil-deploy.ps1 -InstallDeps
```

Useful switches:

- `-SkipAnvil` — use an already-running local Anvil; the script will not stop it.
- `-DeployOnly` — deploy and print addresses, but do not start the indexer.
- `-NoIndexer` — deploy but do not start the indexer.
- `-KeepAnvil` — leave a script-started Anvil process running after exit.
- `-InstallDeps` — install `forge-std` and the Python indexer requirements if missing.

The indexer itself starts at `http://127.0.0.1:8100` by default. See
[`../apps/indexer/README.md`](../apps/indexer/README.md) for exact manual commands, the API
surface, reorg behavior and limitations.

If Foundry is not installed, the script exits with a clear error and no deployment is
attempted. The indexer tests do not require Foundry or Anvil:

```powershell
Set-Location apps/indexer
python -m pip install -r requirements.txt
python -m pytest -q
```

## Environment

Copy `env.example` to `.env` at the repository root for local runs. Never commit `.env`.

## Boundary

- No mainnet RPC.
- Anvil is local only.
- Do not put real keys or funds in this environment.
- The mock API/verifier is not cryptography.
