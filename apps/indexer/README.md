# VeilPool local-chain indexer

> ## LOCAL / TESTNET ONLY — VERIFIER MODE MATTERS
>
> **The default `INDEXER_VERIFIER_KIND=mock` means `MockVerifier` performs no
> cryptography.** The indexer then reports `mock_verifier: true` and a "MOCK
> VERIFIER" disclaimer. Setting `INDEXER_VERIFIER_KIND=groth16` only changes the
> reported metadata/disclaimer for a `VeilPoolPoseidon` deployment with a real
> Groth16 verifier; it does not add proving or verification to this service. The
> development zkey used by the spike is **not audited**. There is still **no
> production security, no audit and no anonymity claim**. Do not use real funds,
> a mainnet RPC or a public deployment with this stack.
>
> This service only stores public chain facts. It has no note, secret, nullifier-secret or
> proof endpoint, and it must never receive client note material.

This is the first real local-chain slice for VeilPool. It indexes the events emitted by
`contracts/src/VeilPool.sol`, normalizes them into SQLite, handles reorgs by rolling back to a
common ancestor and replaying canonical blocks, and exposes a small read-only HTTP API for the
API team.

The API consumes this indexer in `VEILPOOL_MODE=local`; mock mode keeps its SQLite
`MockChain`. The integration surface is documented in
[API integration surface](#api-integration-surface).

---

## Layout

```text
apps/indexer/
├── README.md
├── pyproject.toml
├── requirements.txt
├── scripts/
│   └── gen_poseidon_constants.py  # reproducible circomlib Poseidon(3) constants
├── veilpool_indexer/
│   ├── __init__.py
│   ├── __main__.py       # CLI / poller + uvicorn entry point
│   ├── api.py            # FastAPI read API
│   ├── config.py         # env config, chain allow-list, verifier kind, mainnet rejection
│   ├── events.py         # event topic constants + ABI decoding
│   ├── indexer.py        # polling, reorg detection, replay
│   ├── merkle.py         # depth-20 Poseidon tree / membership path builder
│   ├── poolids.py        # bytes32 <-> short pool label helpers
│   ├── poseidon.py       # pure-Python Poseidon(3), circomlib 2.0.5 compatible
│   ├── poseidon_constants.py  # GENERATED round constants
│   ├── rpc.py            # minimal JSON-RPC client (httpx)
│   └── store.py          # SQLite schema and read/write queries
└── tests/
    ├── conftest.py
    ├── fake_chain.py     # deterministic fake Anvil JSON-RPC
    ├── chain_fixtures.py
    ├── test_api.py
    ├── test_api_path.py
    ├── test_api_verifier.py
    ├── test_config.py
    ├── test_indexer.py
    ├── test_merkle.py
    └── test_poseidon.py
```

---

## Requirements

- Python 3.11 or newer (3.12 tested).
- `fastapi`, `uvicorn`, `httpx` (see `requirements.txt`).
- `pytest` for tests.
- Foundry (`forge`, `anvil`) only for the real local-chain run. Tests do **not** require
  Anvil, Foundry or network access.

Install and test:

```powershell
Set-Location G:\Worker-Space\VeilLab\apps\indexer
python -m pip install -r requirements.txt
python -m pytest -q

# Equivalent from the repository root:
Set-Location G:\Worker-Space\VeilLab
python -m pytest apps/indexer -q
```

Expected test result in this workspace: **29 passed**. The suite uses a fake JSON-RPC
transport. It does not start Anvil.

To regenerate the committed Poseidon constants from the circomlibjs reference table:

```powershell
Set-Location G:\Worker-Space\VeilLab
python apps/indexer/scripts/gen_poseidon_constants.py
```

The generator reads
`circuits/node_modules/circomlibjs/src/poseidon_constants.json` and rewrites
`apps/indexer/veilpool_indexer/poseidon_constants.py`. Do not edit the generated module
by hand.

### Execution status in this workspace

Foundry is **not installed on the default `PATH`** here, but the live slice was exercised with a
temporary Foundry/Anvil 1.9.0 toolchain (not vendored):

- `forge test -vv`: **22 passed**.
- `forge script script/Deploy.s.sol:Deploy --broadcast`: deployed `MockVerifier` and
  `VeilPool` to Anvil chain ID 31337 and created all three pools.
- `python -m veilpool_indexer --once`: indexed 8 events from blocks 0–7
  (`PoolCreated` ×3, `Deposit`, `RootUpdated`, `PoolPaused`, `PoolResumed`, `Withdrawal`).
- `anvil_reorg 2`: the indexer rolled back from block 7 to common ancestor 5, replayed, and
  the reorged withdrawal became a 404 while the earlier deposit stayed canonical.

The temporary toolchain and Anvil process were removed/stopped afterwards. Run the commands
below on a machine with Foundry on `PATH` to reproduce the live path. The indexer pytest suite
does not require Foundry or Anvil.

These results were captured for the three-pool `MockVerifier` slice. Other proof-related files
under `contracts/src` are owned by the contracts track and may change the full-project compile
result; re-run `forge test` on the integrated branch.

---

## Quick start (manual, exact commands)

Use four terminals or the one-command script below.

### 1. Start Anvil

```powershell
anvil --host 127.0.0.1 --port 8545 --chain-id 31337
```

Anvil's chain ID must be **31337**. The indexer rejects other chain IDs unless they are
explicitly allow-listed with `INDEXER_ALLOWED_CHAIN_IDS` (known mainnet IDs are always
rejected).

### 2. Deploy the contracts

```powershell
Set-Location G:\Worker-Space\VeilLab\contracts
forge install foundry-rs/forge-std --no-commit   # once per checkout
forge script script/Deploy.s.sol:Deploy `
  --rpc-url http://127.0.0.1:8545 `
  --broadcast `
  --unlocked --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 `
  -vv
```

The command above uses Anvil's **unlocked** account #0 via `--unlocked --sender`; no private
key is stored or required. Never use a real key or real funds.

`Deploy.s.sol` refuses to run unless `block.chainid == 31337`. It deploys `MockVerifier` and
`VeilPool`, then creates the three ETH pools:

| Pool ID (ASCII bytes32) | Denomination | Maturity | Root window |
| --- | --- | --- | --- |
| `pool_eth_01` | 0.1 ETH | 1800 s (30 min) | 64 roots |
| `pool_eth_1` | 1 ETH | 7200 s (2 h) | 64 roots |
| `pool_eth_10` | 10 ETH | 21600 s (6 h) | 64 roots |

The root window is a **count of recent roots**, not a time or block window. `64` is a local
demo value; the contract accepts `1..1024`.

Copy the printed `VeilPool` address. The script also prints the chain ID and pool IDs.

### 3. Run the indexer

```powershell
Set-Location G:\Worker-Space\VeilLab\apps\indexer
$env:ANVIL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_ADDRESS = "0x..."       # VeilPool address printed above
$env:INDEXER_DB = "indexer.db"
$env:INDEXER_START_BLOCK = "0"
$env:INDEXER_PORT = "8100"
python -m veilpool_indexer
```

The service starts the background poller and serves the read API at
`http://127.0.0.1:8100`. Useful variants:

```powershell
# Catch up once, print a JSON sync summary, and exit.
python -m veilpool_indexer --once

# Serve only cached DB reads; do not contact the RPC.
python -m veilpool_indexer --no-poll

# One-command local stack (starts Anvil, deploys, runs the indexer).
powershell -ExecutionPolicy Bypass -File ..\..\infrastructure\anvil-deploy.ps1 -InstallDeps
```

The one-command script stops the Anvil process it started when it exits. Use
`-KeepAnvil` to leave it running, or `-SkipAnvil` to use an existing Anvil.

### 4. Query the API

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health
Invoke-RestMethod http://127.0.0.1:8100/pools/pool_eth_01/deposits
Invoke-RestMethod http://127.0.0.1:8100/pools/pool_eth_01/roots
Invoke-RestMethod "http://127.0.0.1:8100/pools/pool_eth_01/path/0x<32-byte-commitment>"
Invoke-RestMethod "http://127.0.0.1:8100/withdrawals/0x<32-byte-nullifier>"
```

FastAPI's OpenAPI UI is at `http://127.0.0.1:8100/docs`.

To produce events, deposit into one of the deployed pools with the contract ABI:

```solidity
deposit(bytes32 commitment) external payable
```

The indexer sees the `Deposit` and `RootUpdated` events without any note material. A test
withdrawal requires the `MockVerifier` proof shape documented in `contracts/README.md`; it is
not a real proof.

---

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANVIL_RPC_URL` | `http://127.0.0.1:8545` | Local Anvil JSON-RPC URL |
| `VEILPOOL_ADDRESS` | required | Deployed `VeilPool` address |
| `INDEXER_DB` | `indexer.db` | SQLite database path |
| `INDEXER_START_BLOCK` | `0` | First block to scan |
| `INDEXER_BATCH_SIZE` | `500` | Blocks per `eth_getLogs`/header batch |
| `INDEXER_POLL_SECONDS` | `2.0` | Poll interval |
| `INDEXER_MAX_REORG_DEPTH` | `512` | Maximum common-ancestor walk; deeper fails closed |
| `INDEXER_FINALITY_CONFIRMATIONS` | `1` | Confirmations needed for API `finality="final"` |
| `INDEXER_HOST` | `127.0.0.1` | HTTP bind host |
| `INDEXER_PORT` | `8100` | HTTP port |
| `INDEXER_ALLOWED_CHAIN_IDS` | `31337` | Comma-separated local/testnet allow-list; mainnet IDs rejected |
| `INDEXER_RPC_TIMEOUT` | `10.0` | HTTP timeout seconds |
| `INDEXER_RPC_RETRIES` | `2` | Retries for transport/JSON-RPC failures |
| `INDEXER_VERIFIER_KIND` | `mock` | `mock` or `groth16`; controls `mock_verifier`, `verifier_kind` and disclaimer text |

CLI flags `--once`, `--no-poll`, `--rpc-url`, `--contract`, `--db`, `--start-block`,
`--host`, `--port` and `--log-level` override the environment for one run.

`INDEXER_VERIFIER_KIND` is validated at startup; any value other than `mock` or `groth16`
is a configuration error. It is metadata only: the indexer does not verify proofs. `mock`
is the safe default for the existing local `MockVerifier` deployment. Use `groth16` when
pointing the indexer at a `VeilPoolPoseidon` deployment with a real verifier so clients are
not told "MOCK VERIFIER" when that is no longer true.

---

## What is indexed

`eth_getLogs` is filtered by the configured `VeilPool` address and these event topics:

- `Deposit(bytes32 indexed poolId, bytes32 commitment, uint256 leafIndex, uint256 timestamp)`
- `Withdrawal(bytes32 indexed poolId, bytes32 nullifier, address recipient, uint256 fee, uint256 timestamp)`
- `RootUpdated(bytes32 indexed poolId, bytes32 root, uint256 leafIndex)`
- `PoolPaused(bytes32 indexed poolId, string reason)`
- `PoolResumed(bytes32 indexed poolId)`
- `PoolCreated(bytes32 indexed poolId, uint256 denomination, uint32 rootWindow, uint32 maturity)` — extra metadata event

Every normalized event row stores:

```text
chain_id, contract_address, event_type,
block_number, block_hash, block_timestamp, log_index, tx_hash,
pool_id (bytes32 hex), pool_key (ASCII label when printable),
commitment, nullifier, root, leaf_index,
recipient, fee_wei, reason, denomination_wei, root_window, maturity_seconds,
canonical, removed, indexed_at
```

Event-specific fields are `NULL` for other event types. `fee_wei` and `denomination_wei` are
stored as decimal text so no 256-bit value is truncated. The unique key is
`(chain_id, tx_hash, log_index)`, and duplicate polls are upserts.

SQLite tables:

- `meta` — verified chain ID, last seen tip, timestamps, last error.
- `cursors` — `(chain_id, contract_address)` → last scanned block/hash.
- `blocks` — scanned block headers, including non-canonical history.
- `events` — normalized canonical/non-canonical event rows.
- `reorgs` — rollback audit rows (previous last block, ancestor, new tip).

`canonical=1` marks the active chain. A reorg marks affected rows `canonical=0` and keeps them
for audit; API responses only expose canonical rows.

---

## Reorg handling

On every poll the indexer:

1. Calls `eth_chainId` and verifies it is allow-listed (default only `31337`). A mismatch fails
   closed and is recorded in `meta.last_error`.
2. Reads the current tip and checks the stored cursor header by block number/hash.
3. If the cursor hash no longer matches (or the tip retreated), walks backwards through the
   stored canonical header table until it finds a block hash that matches the RPC. This is the
   common ancestor, bounded by `INDEXER_MAX_REORG_DEPTH`. If no ancestor is found, the poll
   fails instead of guessing.
4. Marks events and headers above the ancestor `canonical=0`, records a `reorgs` row, and
   sets the cursor to the ancestor.
5. Replays logs from `ancestor + 1` to the new tip. Replayed events are upserted back to
   `canonical=1`; removed events stay `canonical=0`.

The current root exposed by `/pools/{pool_id}/roots` is the latest canonical `RootUpdated`
event. Root history is still rebuilt from replayed events, not from a persisted tree. The
`/pools/{pool_id}/path/{commitment}` endpoint separately rebuilds a depth-20 Poseidon tree
from the pool's canonical `Deposit` rows on each request; see [Merkle path](#merkle-path).

---

## API integration surface

Base URL: `http://127.0.0.1:8100` (or `INDEXER_HOST`/`INDEXER_PORT`). The API is read-only.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Indexer, chain, cursor, lag, counts, last error |
| `GET` | `/pools` | Pool IDs with config (denomination, root window, maturity), counts, paused state and latest root |
| `GET` | `/pools/{pool_id}/deposits` | Canonical deposits for one pool |
| `GET` | `/pools/{pool_id}/roots` | Canonical root history for one pool |
| `GET` | `/pools/{pool_id}/path/{commitment}` | Public depth-20 Poseidon Merkle path for one commitment |
| `GET` | `/withdrawals/{nullifier}` | Canonical withdrawal by nullifier |
| `GET` | `/docs` | OpenAPI UI |

`{pool_id}` accepts either the short label (`pool_eth_01`) or the raw 32-byte hex
(`0x706f6f6c5f6574685f3031...`). Responses include both `pool_id` (raw hex) and `pool_key`
(short label when printable). There is no pool-ID mapping table; the deployment script encodes
the short IDs as right-padded ASCII `bytes32`.

### Health

```json
{
  "status": "ok",
  "service": "veilpool-indexer",
  "mode": "local-chain",
  "mock_verifier": true,
  "verifier_kind": "mock",
  "testnet_only": true,
  "chain_id": 31337,
  "contract_address": "0x...",
  "indexed_block": 12,
  "tip_block": 12,
  "lag": 0,
  "finality_confirmations": 1,
  "last_synced_at": "2026-11-03T12:00:00.000Z",
  "last_error": null,
  "reorgs": 0,
  "event_counts": { "Deposit": 2, "RootUpdated": 2 },
  "disclaimer": "LOCAL CHAIN / MOCK VERIFIER. ..."
}
```

`status` is `starting` before the first successful sync, `degraded` when `last_error` is set,
and `ok` otherwise. `lag = tip_block - indexed_block` (clamped at zero).

`verifier_kind` is `mock` or `groth16`, from `INDEXER_VERIFIER_KIND`. `mock_verifier` is
`true` only for `mock`. Every envelope (`/health`, `/pools`, deposit/root/path responses and
withdrawals) carries the same pair and a matching disclaimer:

- `mock`: `"LOCAL CHAIN / MOCK VERIFIER. ... MockVerifier ... performs no ZK proof verification."`
- `groth16`: `"LOCAL CHAIN / GROTH16 VERIFIER (development zkey, not audited). No production security or anonymity claim."`

The flag is informational; the indexer never verifies a proof.

### Deposits

```json
{
  "chain_id": 31337,
  "contract_address": "0x...",
  "pool_id": "0x706f6f6c5f6574685f3031...",
  "pool_key": "pool_eth_01",
  "canonical_only": true,
  "mock_verifier": true,
  "verifier_kind": "mock",
  "count": 1,
  "items": [
    {
      "event_type": "Deposit",
      "commitment": "0x...",
      "leaf_index": 0,
      "block_number": 1,
      "block_hash": "0x...",
      "block_timestamp": 1700000012,
      "log_index": 1,
      "tx_hash": "0x...",
      "canonical": true,
      "confirmations": 1,
      "finality": "final",
      "indexed_at": "2026-11-03T12:00:00.000Z"
    }
  ],
  "next_cursor": null
}
```

### Roots

The contract does not emit the initial empty root in `PoolCreated`, so `/roots` is empty
until the first deposit's `RootUpdated` event.

```json
{
  "pool_id": "0x706f6f6c5f6574685f3031...",
  "pool_key": "pool_eth_01",
  "current_root": "0x...",
  "current_root_block": 2,
  "count": 2,
  "items": [
    {
      "event_type": "RootUpdated",
      "root": "0x...",
      "leaf_index": 0,
      "block_number": 1,
      "block_hash": "0x...",
      "log_index": 2,
      "tx_hash": "0x...",
      "canonical": true,
      "confirmations": 2,
      "finality": "final"
    }
  ]
}
```

### Merkle path

`GET /pools/{pool_id}/path/{commitment}` returns the public depth-20 Poseidon Merkle path
for a deposit commitment. The browser can feed `root`, `path_elements` and `path_indices`
into the `PoseidonMerkle(20)` circuit/JS witness builder. It exposes only public chain
facts (commitment, sibling hashes, path bits, computed root); it does not return or accept
note secrets, witnesses or proofs.

```json
{
  "chain_id": 31337,
  "contract_address": "0x...",
  "pool_id": "0x706f6f6c5f6574685f3031...",
  "pool_key": "pool_eth_01",
  "commitment": "0x...",
  "leaf_index": 0,
  "leaf_count": 2,
  "tree_depth": 20,
  "root": "0x...",
  "path_elements": ["0x...", "0x... (20 total)"],
  "path_indices": [0, 0, 0, "... 20 entries total"],
  "root_block_number": 2,
  "root_block_hash": "0x...",
  "canonical_only": true,
  "mock_verifier": true,
  "verifier_kind": "mock",
  "disclaimer": "LOCAL CHAIN / MOCK VERIFIER. ..."
}
```

Conventions (must match the circuit byte-for-byte):

- Depth is **20**. Leaves are canonical deposit commitments in on-chain `leaf_index`
  order, starting at 0. Only `Deposit` commitments are leaves; there is no leaf wrapper.
- `zero[0] = 0`; `zero[i+1] = Poseidon(DOMAIN_NODE, zero[i], zero[i])`.
- `node = Poseidon(DOMAIN_NODE, left, right)` with
  `DOMAIN_NODE = 0x7665696c706f6f6c2d6d65726b6c652d7631`
  (`"veilpool-merkle-v1"`).
- `path_elements[i]` is the sibling at level `i`. `path_indices[i]` is `0` when the
  current node is the left child and `1` when it is the right child. `path_indices[0]`
  is the least significant bit of `leaf_index`.
- A missing right sibling uses `zero[level]`, so a one-leaf tree still returns 20
  siblings (the zero-subtree chain), not an empty path.

Poseidon provenance: the pure-Python implementation is `veilpool_indexer/poseidon.py`
(`Poseidon(3)`: state `[0, a0, a1, a2]`, 8 full + 56 partial rounds). The committed
`poseidon_constants.py` is generated from the same circomlibjs table used by
`circuits/scripts/gen-poseidon-solidity.mjs`
(`circuits/node_modules/circomlibjs/src/poseidon_constants.json`, SHA-256
`354f31bb...f3f2c`). Tests compare the result with
`circuits/test-vectors/membership-v1.json` (8 leaves, target leaf 5).

Error behavior:

| Condition | Status | `detail.code` |
| --- | --- | --- |
| Unknown pool selector | 404 | `POOL_NOT_FOUND` |
| Known pool with no canonical deposits | 404 | `POOL_EMPTY` |
| Malformed, oversized, zero or `>= p` query commitment | 400 | `INVALID_COMMITMENT` |
| Commitment is not a canonical deposit in the pool | 404 | `COMMITMENT_NOT_FOUND` |
| A **stored** deposit commitment is `>= p` (or malformed) | 422 | `NON_CANONICAL_COMMITMENT` |
| A **stored** deposit commitment is zero | 422 | `ZERO_COMMITMENT` |
| Canonical deposits do not have contiguous leaf indices | 409 | `LEAF_INDEX_MISMATCH` |

Stored leaves are validated before the query value is rejected, so a pool that already
contains an invalid stored leaf returns 422 even if the requested value is also `>= p`.
`POOL_EMPTY` is used instead of `COMMITMENT_NOT_FOUND` when the pool itself is known but
has no leaves, so a client can distinguish "waiting for the first deposit" from a wrong
commitment. A stored commitment `>= p` cannot be a Poseidon output and would be silently
reduced by a careless implementation; this endpoint refuses to build a misleading path.

Root metadata: `root_block_number` and `root_block_hash` come from the latest canonical
`RootUpdated` event and are `null` when no such event exists. **Important current-spike
caveat:** `VeilPool.sol` still hashes its on-chain tree with `keccak256`, while this
endpoint (and the circuit) use Poseidon. Until the contract is migrated to
`VeilPoolPoseidon`, `root` here is the Poseidon root for the indexed leaves and may differ
from the `root` value in the latest `RootUpdated` event. Do not treat it as the contract's
current keccak root.

Performance: the tree is rebuilt from SQLite rows on every request and the Poseidon
permutation is pure Python. Cost is roughly `O(leaf_count + 20)` hashes plus one database
read of the pool's deposits; there is no cached tree or incremental update. That is fine
for local/testnet-sized pools but is not a production proving/indexing service. Clients
should still check that the returned root is known and inside the contract's accepted root
window before submitting a proof.

### Withdrawal

Returns the canonical withdrawal event with `found: true`. Add `?pool_id=pool_eth_01`
when the same nullifier may exist in more than one pool (nullifiers are scoped per pool
on-chain).

```json
{
  "found": true,
  "event_type": "Withdrawal",
  "pool_id": "0x...",
  "pool_key": "pool_eth_01",
  "nullifier": "0x...",
  "recipient": "0x...",
  "fee_wei": "1000",
  "block_number": 3,
  "block_hash": "0x...",
  "log_index": 1,
  "tx_hash": "0x...",
  "canonical": true,
  "confirmations": 1,
  "finality": "final"
}
```

Missing canonical records return `404` with `detail.code` equal to `POOL_NOT_FOUND`,
`POOL_EMPTY`, `COMMITMENT_NOT_FOUND` or `WITHDRAWAL_NOT_FOUND`. Before the first sync,
pool/withdrawal routes return `503` `INDEXER_NOT_READY`. Invalid selectors and commitments
return `400`; stored non-canonical commitments return `422`; non-contiguous stored leaf
indices return `409`.

### API integration (implemented)

- The API runs in `VEILPOOL_MODE=local` with `VEILPOOL_INDEXER_URL` and proxies these reads
  server-to-server. The indexer remains read-only and should stay on loopback.
- Map ETH pools by `pool_key` (`pool_eth_01`, `pool_eth_1`, `pool_eth_10`) or by the raw
  `pool_id`. USDC/tBTC pools are mock-only because the contract is ETH-only.
- Use `(chain_id, tx_hash, log_index)` as the idempotency key when importing deposits or
  withdrawals into the API database.
- Treat `canonical` as always true in API responses. A reorg can make a previously returned
  deposit/withdrawal disappear; the API should reconcile by pool from the indexer and clear
  local nullifier status when `/withdrawals/{nullifier}` becomes 404.
- The contract events do not include a depositor or relayer address. The indexer does not infer
  them from transaction senders; keep those API fields nullable or fill them from a separate
  wallet/relayer source.
- `confirmations`/`finality` are computed from the indexer's last seen Anvil tip. With
  `INDEXER_FINALITY_CONFIRMATIONS=1` every observed block is `final`; this is a local
  convenience, not probabilistic finality.
- Fetch the membership path from `/pools/{pool_id}/path/{commitment}` and pass the returned
  `root`/`path_elements`/`path_indices` to the client-side witness builder. The client must
  verify that the root is known to the contract and inside its root window; the indexer is
  not a trust anchor.
- `mock_verifier`/`verifier_kind` are deployment metadata for UI copy. Set
  `INDEXER_VERIFIER_KIND=groth16` for a `VeilPoolPoseidon` deployment so clients do not show
  a stale mock-verifier warning. This does not make the development zkey audited.
- `POST /api/v1/local/deposits` sends a deposit through the local Anvil unlocked account and
  polls this indexer until the event is visible. It is a dev-only bridge, not a relayer.
- Do not add note, secret or proof fields to these responses. The indexer has no such data.

---

## Boundary and limitations

1. **Verifier metadata, not verification.** With `INDEXER_VERIFIER_KIND=mock` (default),
   `MockVerifier` checks only an encoded copy of public signals and is trivially forgeable.
   With `groth16`, the endpoint metadata says `mock_verifier: false`, but the indexer still
   does not verify proofs, and the spike's development zkey is not audited. Neither mode
   proves Merkle membership or note ownership.
2. **Not a production chain service.** The API consumes it in local mode; mock mode still uses
   SQLite `MockChain`. This slice proves the contract → events → indexer → API path, not
   production finality, HA or note privacy.
3. **Root history vs. path rebuild.** `/roots` is still normalized from `RootUpdated` events.
   `/path` rebuilds a Poseidon tree from canonical `Deposit` rows on every request; it is not
   a persistent or incrementally updated tree. In the current spike the contract tree is
   keccak-based, so the returned Poseidon root may not equal the on-chain `RootUpdated` root.
4. **Local chain only.** Chain ID 31337 is the default; known mainnet IDs are rejected even if
   someone puts them in `INDEXER_ALLOWED_CHAIN_IDS`. No mainnet RPC or key is included.
5. **SQLite, one writer, no auth, no TLS.** Suitable for a local demo only. The API is
   unauthenticated and binds to `127.0.0.1` by default. List endpoints cap at 1000 rows and
   `next_cursor` is currently always null.
6. **Polling, not subscriptions.** No `eth_subscribe`, WebSocket or backfill queue. Anvil only.
7. **Hash-based reorg detection, not consensus finality.** A reorg deeper than
   `INDEXER_MAX_REORG_DEPTH` fails closed and requires an operator decision.
8. **ETH only.** No ERC-20/tBTC pools. No per-pool balance ledger.
9. **`PoolCreated` is extra.** The five required state-machine events are Deposit, Withdrawal,
   RootUpdated, PoolPaused and PoolResumed; PoolCreated is indexed for pool discovery.
10. **No note material.** There is intentionally no note endpoint, note table or log field.
11. **Pure-Python path rebuild.** Poseidon is a reference implementation, not an optimized
    backend. Rebuilding every path request is acceptable for local demos but scales linearly
    with the pool's leaf count and should not be used as a production path service.

The only `MOCK` label in the on-chain path is the verifier, and it is selected by deployment
configuration (`INDEXER_VERIFIER_KIND`). The indexer itself reads real events from the local
Anvil chain, but the deployed system is still a **local demo with no privacy guarantees**.
