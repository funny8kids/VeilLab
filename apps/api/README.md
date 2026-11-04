# VeilPool API — mock + local Anvil mode

> **LOCAL DEMO / TESTNET ONLY.** This is not a production mixer, does not touch
> real funds, and does not provide production privacy. `VEILPOOL_MODE=local`
> reads public events from a local Anvil chain through the standalone indexer
> and can bridge dev deposits/withdrawals through Anvil's unlocked account. It
> is still a development-only slice. If `VEILPOOL_LOCAL_VERIFIER_KIND=groth16`,
> the local verifier is a **development zkey** Groth16 build and is unaudited;
> that label is honesty metadata, not a security claim. The compliance provider
> remains a deterministic fixture in every mode.

FastAPI + SQLAlchemy 2.x + Pydantic v2 API for the VeilPool vertical slice.
SQLite is the local development database. The API **never accepts or stores
client secret note material**: requests are strict (`extra="forbid"`), and keys
that look like secret material are rejected before validation.

Two modes are supported:

| Mode | Chain source | Default chain | Notes |
| --- | --- | --- | --- |
| `mock` (default) | SQLite `MockChain` | 11155111 | Existing web demo, six seeded pools |
| `local` | Standalone indexer + local Anvil | **31337 only** | Three ETH pools, read-only chain facts, public Merkle-path proxy, dev deposit + withdrawal bridges |

`local` startup fails closed unless the chain ID is 31337, the contract address
is set, and both the indexer and RPC URLs are loopback addresses.

---

## Quick start

### Mock mode (default, unchanged web demo)

From `apps/api` (PowerShell):

```powershell
python -m pip install -r requirements.txt

$env:VEILPOOL_MODE = "mock"
$env:VEILPOOL_ADMIN_TOKEN = "dev-admin"

python -m uvicorn veilpool_api.main:app --reload --port 8000
```

Open:

- API root: <http://127.0.0.1:8000/>
- Health: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI: <http://127.0.0.1:8000/docs>

`DATABASE_URL` defaults to `sqlite:///./veilpool.db`. The database is created
and seeded on startup. Delete `veilpool.db` to reset the demo.

With `VEILPOOL_MODE=mock`, the root/health responses and every relevant response
carry `"mock": true`; headers include `X-VeilPool-Mode: mock` and
`X-VeilPool-Mock: true`.

### Local Anvil mode

Use a separate database and start all three local services:

```powershell
# 1. Anvil
anvil --host 127.0.0.1 --port 8545 --chain-id 31337

# 2. Deploy the contracts, then start the indexer (see apps/indexer/README.md)
Set-Location G:\Worker-Space\VeilLab\apps\indexer
$env:ANVIL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_ADDRESS = "0x..."   # printed by the deployment script
python -m veilpool_indexer

# 3. API in local mode
Set-Location G:\Worker-Space\VeilLab\apps\api
$env:VEILPOOL_MODE = "local"
$env:VEILPOOL_CHAIN_ID = "31337"
$env:VEILPOOL_CONTRACT_ADDRESS = "0x..."  # same VeilPool address
$env:VEILPOOL_INDEXER_URL = "http://127.0.0.1:8100"
$env:VEILPOOL_LOCAL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_LOCAL_AUTO_DEPOSIT = "true"
$env:VEILPOOL_LOCAL_AUTO_WITHDRAW = "true"      # optional dev-only relayer bridge
$env:VEILPOOL_LOCAL_VERIFIER_KIND = "groth16"   # only for VeilPoolPoseidon
$env:VEILPOOL_LOCAL_MATURITY_SECONDS = "0"      # match DeployPoseidon; local spike only
$env:DATABASE_URL = "sqlite:///./veilpool-local.db"
python -m uvicorn veilpool_api.main:app --reload --port 8000
```

Set `VEILPOOL_LOCAL_VERIFIER_KIND` to match the deployed contract: `mock` for
the default `MockVerifier` demo, `groth16` only for a local
`VeilPoolPoseidon` + `Groth16VerifierAdapter` deployment. The API rejects any
other value at startup. `groth16` changes service labels and warnings; it does
not make the development zkey, circuit or adapter audited.

The one-command local stack script in `infrastructure/anvil-deploy.ps1` starts
Anvil, deploys the contracts and starts the indexer. Start the API separately
with the environment above.

Local mode only accepts loopback URLs (`127.0.0.1`, `localhost`, `::1`). A
remote RPC, a public indexer URL, a mainnet chain ID or a missing
`VEILPOOL_CONTRACT_ADDRESS` exits at startup rather than degrading silently.

Auth and rate limiting are enabled in a demo-friendly way by default:

- `VEILPOOL_REQUIRE_AUTH` defaults to `false`, so the local web demo continues
  to call the API without a bearer token.
- Rate limits are on by default for the deposit, local deposit, withdrawal,
  compliance and admin scopes, using the per-minute values from the API spec.
  They are per-process, in-memory buckets keyed by bearer token (hashed) or
  client IP. Set `VEILPOOL_RATE_LIMIT_ENABLED=false` to turn them off.
- Request bodies are capped at 64 KiB by default.

To exercise the protected configuration:

```powershell
$env:VEILPOOL_REQUIRE_AUTH = "true"
$env:VEILPOOL_API_TOKEN = "dev-api-token"

# Public, no token:
Invoke-WebRequest http://127.0.0.1:8000/api/v1/pools

# Protected:
Invoke-WebRequest http://127.0.0.1:8000/api/v1/withdrawals/wdr_missing `
  -Headers @{ Authorization = "Bearer dev-api-token" }
```

---

## Tests

```powershell
cd apps/api
python -m pytest -q
```

The suite uses a fresh temporary SQLite database and a fresh in-memory rate
limiter per test. It covers health, pool seeding, exact denominations,
secret-field rejection, deposit intent + mock deposit, double-spend rejection,
pause/resume, compliance block/review, limits, idempotency mismatch,
quote/decision expiry, audit hash chaining, withdrawal status lookup,
auth on/off, missing/invalid bearer tokens, rate limiting, request body size,
security headers, compliance review list/approve/reject/expiry, local-mode
configuration, indexer overlays, indexer error mapping, the local Anvil
deposit bridge, the local Groth16 withdrawal bridge, the public Merkle-path
proxy and verifier-kind labels (with mocked JSON-RPC and `httpx.MockTransport`).
Neither Anvil nor the network is required.

Current workspace result: **107 passed**.

---

## Endpoints

Base path: `/api/v1`. Errors use `application/problem+json` with a stable
`code` and a `request_id`.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Mode, chain/indexer status, DB check; `indexer` block in local mode |
| GET | `/pools` | Six seeded pools in mock; three ETH pools in local |
| GET | `/pools/{pool_id}` | Config + indexer overlay in local mode |
| GET | `/pools/{pool_id}/root` | Mock root history, or indexer root history in local |
| GET | `/pools/{pool_id}/deposits` | Deposits: mock DB rows, or canonical indexer rows |
| GET | `/pools/{pool_id}/deposits/{tx_hash}` | Canonical deposit status |
| GET | `/pools/{pool_id}/path/{commitment}` | **Local-only** public Merkle-path proxy |
| POST | `/deposits/intent` | `Idempotency-Key` required; compliance + expiry |
| POST | `/local/deposits` | **Local-only** Anvil deposit bridge |
| POST | `/local/withdrawals` | **Local-only** Groth16 withdrawal bridge |
| POST | `/mock/deposits` | **Mock-only** chain event recorder |
| GET | `/relayers` | Mock relayer directory |
| GET | `/relayers/{relayer_id}` | Relayer detail |
| POST | `/withdrawals/quote` | Compliance + relayer fee quote |
| POST | `/withdrawals/submit` | Proof shape + public signals; `Idempotency-Key` required; **mock-only** |
| GET | `/withdrawals/{withdrawal_id}` | Status; bearer token when auth is enabled |
| GET | `/withdrawals/by-nullifier/{nullifier_hash}` | Privacy-sensitive lookup; bearer token when auth is enabled |
| GET | `/compliance/policy` | Public mock policy summary |
| POST | `/admin/pools/{pool_id}/pause` | `X-Admin-Token: dev-admin`; audited; **mock-only** |
| POST | `/admin/pools/{pool_id}/resume` | `X-Admin-Token: dev-admin`; audited; **mock-only** |
| GET | `/admin/compliance/reviews` | `X-Admin-Token`; pending review queue (`?status=pending\|approved\|rejected\|all`) |
| POST | `/admin/compliance/reviews/{review_id}/decision` | `X-Admin-Token`; approve/reject with reason + expiry; audited |

`POST /api/v1/deposits/mock` is kept as a hidden alias of `/mock/deposits` for
local clients.

### Authentication

`VEILPOOL_REQUIRE_AUTH=false` (default) keeps every endpoint at its historical
local-demo behavior. `X-Admin-Token` is still required for `/admin/*`.

When `VEILPOOL_REQUIRE_AUTH=true`, the following stay public without a token:

- `GET /health`
- `GET /pools`, `GET /pools/{id}`, `/pools/{id}/root`,
  `/pools/{id}/deposits/{tx_hash}`
- `GET /relayers`, `GET /relayers/{id}`
- `GET /compliance/policy`

`GET /pools/{pool_id}/path/{commitment}` is covered by the existing
`/pools*` public prefix. `POST /local/withdrawals` is **not** public; when auth
is enabled it requires the bearer token like the other write endpoints.

Every other endpoint requires:

```http
Authorization: Bearer <VEILPOOL_API_TOKEN>
```

Admin routes require both the bearer token and `X-Admin-Token`. Missing or
invalid bearer credentials return `401 AUTH_REQUIRED`; missing or invalid admin
credentials return `401 ADMIN_UNAUTHORIZED`. This is a development bearer token,
not a user session, CSRF token or TOTP flow.

### Rate limiting and request limits

In-memory token buckets are keyed by a SHA-256 hash of the bearer token when one
is present, otherwise by client IP. Limits are per process and reset on restart.
Limits apply to deposit intents, local Anvil deposit/withdrawal bridge calls,
the public local Merkle-path proxy, withdrawal quotes/submissions, compliance
endpoints and admin endpoints.
Exceeding a limit returns `429 RATE_LIMITED` with `Retry-After` and
`X-RateLimit-*` headers.

The server rejects request bodies over `VEILPOOL_MAX_BODY_BYTES` (default 64
KiB) with `413 REQUEST_TOO_LARGE`. All responses include
`X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`;
non-public responses also include `Cache-Control: no-store`. Note that
`/pools*` and `/relayers*` are on the public allow-list, matching the task
contract, even though they expose operational metadata.

### Mock deposit flow

1. `POST /deposits/intent` with `pool_id`, `depositor_address`, exact `amount`.
   An optional public 32-byte `commitment` may be included; secret client
   material is still rejected.
2. `POST /mock/deposits` with `intent_id` and a client-derived 32-byte
   `commitment` (the secret client material itself is never sent). If the
   intent carried a commitment, the two must match.
3. Read the returned mock `tx_hash` through
   `GET /pools/{pool_id}/deposits/{tx_hash}`.

### Local mode read model

`GET /health`, `GET /`, `GET /pools` and `GET /pools/{pool_id}` expose an
explicit `indexer` block. In local mode:

- `mode` is `"local"` and `mock` is `false`.
- `services.chain` is the `INDEXER`, not `MOCK_CHAIN`.
- `mock_services` contains only `MOCK_VERIFIER` and `MOCK_COMPLIANCE`; it never
  lists `MOCK_CHAIN`.
- `chain_data_status` is `"available"` or `"unavailable"`.
- The indexer block contains `status`, `indexed_block`, `tip_block`, `lag`,
  `last_error` and `error_code`. The same fields are mirrored at the top level
  of `GET /pools` where useful for the web client.
- If the indexer is down, pool configuration is still returned from SQLite but
  `anonymity_set`, `liquidity_wei`, `current_root`, `indexed_block` and `lag`
  are `null` and a `warning` explains why. Counts are never fabricated.
- Only `pool_eth_01`, `pool_eth_1` and `pool_eth_10` are configured. USDC/tBTC
  rows from an older mock database are marked `retired`; a fresh local database
  seeds only the three ETH pools. All three use the single
  `VEILPOOL_CONTRACT_ADDRESS`.
- `GET /pools/{pool_id}/deposits` proxies canonical indexer deposits with
  `chain_source:"indexer"` and `local_chain:"ANVIL"`. The proxy allow-list is
  commitment, leaf index, transaction hash, block number/hash/timestamp, log
  index, pool id/key, confirmations, finality and indexed-at. Unknown indexer
  fields (including any note-like field) are dropped. An indexer `404` for a
  known pool becomes `200` with `items: []`. If the indexer is unreachable the
  endpoint returns `503 INDEXER_UNAVAILABLE` instead of an ambiguous empty list.
- Mock mode keeps the existing DB-backed behaviour: six pools, `mock:true`, and
  the SQLite `MockChain`.

### Local Merkle-path proxy (local mode only)

`GET /api/v1/pools/{pool_id}/path/{commitment}` lets the browser prover fetch a
membership path from the API instead of calling the standalone indexer
cross-origin. It is a read-only proxy to the indexer's
`GET /pools/{pool_id}/path/{commitment}` and requires `mode=local` and chain
`31337`; mock mode returns `404 LOCAL_ONLY`.

- `pool_id` must be one of the three configured local ETH pools.
- `commitment` must be `0x` plus 64 hex characters.
- Malformed commitment: `400 INVALID_COMMITMENT`.
- Commitment `>=` the BN254 scalar field modulus:
  `422 NON_CANONICAL_COMMITMENT`.
- Indexer `404`: `404 COMMITMENT_NOT_FOUND`.
- Indexer `400` / `422`: `400 INVALID_COMMITMENT` /
  `422 NON_CANONICAL_COMMITMENT`.
- Indexer unavailable/not ready: `503 INDEXER_UNAVAILABLE`.

The response forwards exactly these public fields, dropping every other
indexer key (including note-like keys):

```text
chain_id, contract_address, pool_id, pool_key, commitment, leaf_index,
leaf_count, tree_depth, root, root_block_number, root_block_hash,
path_elements, path_indices, canonical_only, mock_verifier
```

`path_elements` and `path_indices` are the public Merkle path. No note,
witness, secret or proof is accepted or returned. The endpoint is under the
public `/pools*` read prefix and uses its own in-memory rate-limit scope,
`pool_path` (`VEILPOOL_RATE_LIMIT_POOL_PATH`, default 30 per minute).

### Local deposit bridge (local Anvil only)

`POST /api/v1/local/deposits` is a development bridge for the local web demo.
It accepts only:

```json
{
  "intent_id": "dep_01J...",
  "commitment": "0x<64 hex characters>"
}
```

The endpoint is available only when `mode=local` and `chain_id=31337`;
otherwise it returns `404 LOCAL_ONLY`. It reuses the existing intent checks:
the intent must exist, be `pending`, not expired, match its recorded commitment
when one was supplied, and its compliance decision must still be allowed. The
pool must be active.

`VEILPOOL_LOCAL_AUTO_DEPOSIT=false` (the default) never sends a transaction and
returns `409 LOCAL_DEPOSIT_DISABLED` with:

```json
{
  "status": 409,
  "code": "LOCAL_DEPOSIT_DISABLED",
  "contract_address": "0x...",
  "denomination_wei": "100000000000000000",
  "calldata": "0xb214faa5<commitment without 0x>",
  "instruction": "submit the deposit from your own wallet",
  "local_chain": "ANVIL"
}
```

With `VEILPOOL_LOCAL_AUTO_DEPOSIT=true`, the server asks Anvil to send
`eth_sendTransaction` from `VEILPOOL_LOCAL_FROM_ADDRESS` (Anvil account 0) to
`VEILPOOL_CONTRACT_ADDRESS`, with `value = pool.denomination_wei` and calldata
`deposit(bytes32 commitment)`. The selector `0xb214faa5` is computed in code.
**The server never accepts or stores a private key.** Anvil owns the unlocked
development account. Do not use a real account or real funds.

After the transaction hash is returned, the API polls the indexer for that
`tx_hash` and `commitment` for up to
`VEILPOOL_LOCAL_DEPOSIT_TIMEOUT_SECONDS` seconds.

#### Success response contract

The response is the normal deposit view plus the local fields below. A first
successful call returns `201`; a repeat call for an already-consumed intent with
the same commitment returns `200` and the same stored deposit (no second
transaction).

```json
{
  "tx_hash": "0x...",
  "pool_id": "pool_eth_01",
  "status": "confirmed",
  "commitment": "0x...",
  "leaf_index": 0,
  "block_number": 11,
  "block_hash": "0x...",
  "confirmations": 4,
  "finality": "final",
  "indexed_at": "2026-11-03T12:00:00Z",
  "mock": false,
  "chain_source": "indexer",
  "local_chain": "ANVIL",
  "intent_id": "dep_01J...",
  "indexer_lag": 2
}
```

`tx_hash` and `block_number` are the same fields the normal deposit view uses;
they are listed here because the web team relies on them. The existing deposit
row stores `tx_hash`, `block_number`, `block_hash`, `log_index`, `leaf_index`
and `commitment` from the indexer.

#### Local deposit error contract

| HTTP | Code | Behaviour |
| --- | --- | --- |
| 404 | `LOCAL_ONLY` | Not local mode / not chain 31337 |
| 404 | `INTENT_NOT_FOUND` | Unknown intent |
| 409 | `POOL_PAUSED` | Pool not active |
| 409 | `INTENT_EXPIRED` | Intent expired or blocked |
| 409 | `INTENT_CONSUMED` | Consumed with no recoverable deposit |
| 409 | `COMMITMENT_MISMATCH` | Commitment differs from the intent/broadcast |
| 409 | `LOCAL_DEPOSIT_DISABLED` | Auto-deposit off; calldata returned, no tx |
| 422 | `COMPLIANCE_*` / `VALIDATION_ERROR` | Compliance expired/blocked, bad commitment |
| 502 | `INDEXER_MISMATCH` | Indexed tx/commitment/leaf conflicts; intent is not consumed |
| 502 | `LOCAL_RPC_*` | Anvil rejected the RPC call |
| 504 | `INDEXER_CONFIRMATION_TIMEOUT` | Tx broadcast but not indexed in time; includes `tx_hash` and leaves the intent pending |

A timeout does not consume the intent. The broadcast transaction hash is stored
in `local_deposit_broadcasts`, so a repeat call polls the same transaction
instead of sending a second one. If the indexer never confirms it, the intent
stays pending and can be reconciled by an operator.

In local mode, `POST /deposits/intent` remains a compliance/quote step. Its
response includes `next_step: "POST /api/v1/local/deposits"`,
`local_chain: true` and a warning that the deposit is not complete. Mock chain
writes are disabled: `/mock/deposits` returns `404 MOCK_ONLY`, withdrawal
submission returns `409 MOCK_ONLY`, and admin pause/resume returns
`409 MOCK_ONLY`. Read endpoints remain available.

`POST /api/v1/local/deposits` and `POST /api/v1/local/withdrawals` use their
own rate-limit buckets (`local_deposit` / `local_withdrawal`, default 5 per
minute per caller). They are not public endpoints when
`VEILPOOL_REQUIRE_AUTH=true`.

### Local withdrawal bridge (local Anvil only)

`POST /api/v1/local/withdrawals` is a **development-only relayer-like bridge**
for a real Groth16 proof against a local `VeilPoolPoseidon` +
`Groth16VerifierAdapter` deployment. It is not a production non-custodial
relayer: Anvil's unlocked account submits the transaction, so the operator
account is the on-chain `msg.sender` and receives the quoted relayer fee. Do
not use it with real funds or real accounts.

The endpoint is available only when `mode=local` and `chain_id=31337`;
otherwise it returns `404 LOCAL_ONLY`. It never accepts or stores a private
key, note, witness, secret or preimage.

#### Request

```json
{
  "quote_id": "quote_...",
  "proof": "0x...",
  "root": "0x...",
  "nullifier": "0x...",
  "recipient": "0x...",
  "relayer_fee_wei": "240000000000000"
}
```

- `quote_id` must be an existing, unexpired `POST /withdrawals/quote` quote for
  an active local pool.
- `recipient` and `relayer_fee_wei` must match the quote.
- `proof` is exactly **256 bytes** (`0x` + 512 hex characters).
- `root` and `nullifier` are 32-byte hex words; `recipient` is a non-zero
  20-byte address.
- The quote's mock compliance decision is re-checked and must still be allowed
  and bound to the same pool and recipient.

#### Proof encoding

The local bridge accepts only the Groth16 `snarkjs ... soliditycalldata`
encoding:

```text
abi.encode(
  uint256[2]    pA,
  uint256[2][2] pB,
  uint256[2]    pC
)
```

This is 256 bytes = `a.x || a.y || b00 || b01 || b10 || b11 || c.x || c.y`,
with the `pB` order produced by `snarkjs zkey export soliditycalldata`. It is
not the 160-byte `MockVerifier` shape. In local quotes the value is exposed as
`proof_encoding: "abi(uint256[2],uint256[2][2],uint256[2])"`.

The contract call is:

```text
withdraw(bytes,bytes32,bytes32,address,uint256,bytes32)
```

The calldata helper is `veilpool_api.local_chain.encode_withdraw_calldata`.
The function head contains six words (five static arguments plus the dynamic
`bytes` offset), so the proof tail offset is **192 bytes (`0xc0`)**. The tail
contains a length word (`0x100`) and the eight proof words. The selector is
computed with the pure-Python keccak implementation. Malformed proof bytes
return `422 INVALID_PROOF`; malformed root/nullifier/recipient/fee values
return `422 INVALID_PUBLIC_SIGNALS`. Nothing is sent to RPC for malformed
input.

#### Root and nullifier pre-checks

Before broadcasting, the API asks the indexer whether the nullifier already
has a canonical withdrawal. If so it returns `409 NULLIFIER_SPENT` with the
public existing withdrawal under `withdrawal`, and sends nothing.

The proof root must equal the indexer's `current_root` or appear in its root
history. Otherwise the API returns:

- `409 ROOT_STALE` with `current_root` and `ready_roots`, or
- `409 UNKNOWN_ROOT` with `current_root: null` and `ready_roots: []` when the
  indexer has no root history yet.

#### Automatic mode

`VEILPOOL_LOCAL_AUTO_WITHDRAW` defaults to **`false`** for safety. With the
flag off, the endpoint validates the quote, nullifier, root and compliance
decision and returns `409 LOCAL_WITHDRAWAL_DISABLED` with the exact calldata,
so the caller can submit it from their own wallet:

```json
{
  "status": 409,
  "code": "LOCAL_WITHDRAWAL_DISABLED",
  "contract_address": "0x...",
  "calldata": "0xc890dc66...",
  "instruction": "submit the withdrawal from your own wallet",
  "local_chain": "ANVIL",
  "pool_id": "pool_eth_01",
  "quote_id": "quote_...",
  "verifier_kind": "groth16-poseidon"
}
```

With `VEILPOOL_LOCAL_AUTO_WITHDRAW=true`, the API sends `eth_sendTransaction`
from `VEILPOOL_LOCAL_FROM_ADDRESS` (Anvil account 0) to
`VEILPOOL_CONTRACT_ADDRESS` with `value=0` and the calldata above. It checks
`eth_getTransactionReceipt` immediately (short poll) so a reverted transaction
returns `502 WITHDRAWAL_REVERTED` with the tx hash, block and `gas_used`
instead of a misleading indexer timeout. The reverted broadcast row is
removed and the quote stays active. If the receipt succeeds, the API polls the
indexer for the nullifier for up to
`VEILPOOL_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS` (default 20) and verifies the
indexed transaction hash, recipient, fee and pool before persisting a
canonical `Withdrawal` row.

#### Success response

The first confirmed call returns `201`:

```json
{
  "withdrawal_id": "wdr_...",
  "pool_id": "pool_eth_01",
  "status": "confirmed",
  "tx_hash": "0x...",
  "block_number": 5,
  "block_hash": "0x...",
  "nullifier": "0x...",
  "recipient": "0x...",
  "fee_wei": "100000000000000",
  "confirmations": 1,
  "finality": "final",
  "local_chain": "ANVIL",
  "chain_source": "indexer",
  "verifier_kind": "groth16-poseidon",
  "proof_encoding": "abi(uint256[2],uint256[2][2],uint256[2])",
  "mock": false,
  "warning": "..."
}
```

A repeated call with the same quote, nullifier, recipient, fee and proof
returns `200` and the stored withdrawal without a second transaction. Because
the proof itself is never persisted, the API stores a SHA-256 proof digest to
distinguish a true replay from a different proof. A different nullifier,
recipient, fee or proof for the same quote returns `409 QUOTE_CONSUMED`.

#### Error contract

| HTTP | Code | Behaviour |
| --- | --- | --- |
| 404 | `LOCAL_ONLY` | Not local mode / not chain 31337 |
| 404 | `QUOTE_NOT_FOUND` | Unknown quote |
| 409 | `POOL_PAUSED` / `POOL_RETIRED` | Pool is not active for this bridge |
| 409 | `QUOTE_EXPIRED` | Quote expired; quote is marked expired |
| 422 | `INVALID_PUBLIC_SIGNALS` | Bad root/nullifier/recipient/fee or quote mismatch |
| 422 | `INVALID_PROOF` | Proof is not exactly 256 bytes / ABI Groth16 hex |
| 409 | `NULLIFIER_SPENT` | Indexer or local DB already has the nullifier; includes public withdrawal |
| 409 | `ROOT_STALE` / `UNKNOWN_ROOT` | Root not in indexer root history/current root |
| 409 | `LOCAL_WITHDRAWAL_DISABLED` | Auto-withdraw off; calldata returned, no tx |
| 409 | `QUOTE_CONSUMED` | Quote already used with different public data/proof |
| 502 | `WITHDRAWAL_REVERTED` | Receipt status `0`; quote not consumed, failed broadcast removed |
| 502 | `INDEXER_MISMATCH` | Indexed withdrawal conflicts; quote not consumed |
| 502 | `LOCAL_RPC_*` | Anvil rejected or failed the RPC call |
| 504 | `INDEXER_CONFIRMATION_TIMEOUT` | Tx broadcast but not indexed in time; includes `tx_hash`, quote remains usable |
| 503 | `INDEXER_UNAVAILABLE` / `INDEXER_TIMEOUT` | Indexer unavailable before broadcast |

A timeout does **not** consume the quote. The broadcast transaction hash is
stored in `local_withdrawal_broadcasts`, so a retry polls the same transaction
instead of sending a second one. If the quote expires before confirmation, the
normal expiry check applies. A revert does not consume the quote.

#### Verifier-kind honesty

`VEILPOOL_LOCAL_VERIFIER_KIND` controls local labels:

- `mock` (default): health/services keep `MOCK_VERIFIER (shape-only, no ZK)`
  and `mock_services` includes `MOCK_VERIFIER`.
- `groth16`: health/services report
  `GROTH16_POSEIDON (development zkey, unaudited)`, `mock_services` omits
  `MOCK_VERIFIER`, and local quotes/withdrawal responses include
  `verifier_kind: "groth16-poseidon"` plus a non-production warning.

The API rejects any other value at startup. This setting only changes labels
and warnings; it does not select or deploy a contract. If automatic withdrawal
is enabled while the deployed contract still uses `MockVerifier`, the bridge
will submit Groth16 calldata and the transaction will revert (reported as
`502 WITHDRAWAL_REVERTED`). Use `groth16` only with the local
`VeilPoolPoseidon` + adapter deployment. `groth16` is a deployment label for
the local Poseidon + adapter spike; it is **not** evidence of audited
cryptography, production privacy or a secure trusted setup. Mock mode is
unchanged.

### Withdrawal flow

1. `GET /pools/{pool_id}/root` and keep the returned `root`.
2. `POST /withdrawals/quote` with pool, fresh recipient, relayer id.
3. Generate a mock proof client-side and call `POST /withdrawals/submit` with
   the quote id, a shape-valid `proof`, and public signals
   `root`, `nullifier_hash`, `recipient`, `fee_wei`.
4. The mock chain confirms immediately; poll `GET /withdrawals/{id}`.

The mock proof shape is `0x` + 64..4096 hex characters (32..2048 bytes, even
length). The verifier only checks shape; it performs no cryptography.

In local mode, `POST /withdrawals/quote` remains the compliance/fee step but
does not submit anything. When `VEILPOOL_LOCAL_AUTO_WITHDRAW=true` it returns
`submission_available:true`, `proof_encoding:
"abi(uint256[2],uint256[2][2],uint256[2])"`, `verifier_kind` and
`submission_endpoint:"/api/v1/local/withdrawals"`. When the flag is false it
keeps `submission_available:false` and a manual-submission warning.
`POST /withdrawals/submit` stays mock-only and returns `409 MOCK_ONLY` in
local mode.

`Idempotency-Key` is required on both deposit intent and withdrawal submit.
Reusing a key with an identical body replays the stored response. Reusing it
with a different body returns `409 IDEMPOTENCY_MISMATCH`.

---

## Seeded pools

Mock mode seeds six pools on chain id 11155111. Local mode configures only the
three ETH pools on chain id 31337 and the single local `VeilPool` address; the
USDC/tBTC rows are retired if they already exist in the database.

| Pool id | Asset | Denomination | Maturity | Protocol fee |
| --- | --- | --- | --- | --- |
| `pool_eth_01` | ETH | 0.1 | 1800 s | 24 bps |
| `pool_eth_1` | ETH | 1 | 7200 s | 22 bps |
| `pool_eth_10` | ETH | 10 | 21600 s | 20 bps |
| `pool_usdc_100` | USDC (mock) | 100 | 1800 s | 28 bps |
| `pool_usdc_1000` | USDC (mock) | 1000 | 7200 s | 25 bps |
| `pool_btc_001` | tBTC | 0.01 | 7200 s | 30 bps |

The USDC/tBTC rows are mock-only and are not deployed in local mode.

Six mock relayers are seeded (`rel_01`..`rel_06`) with different fees and pool
support; `rel_06` is `degraded` to exercise the status display.

---

## Mock compliance fixture

| Input | Decision |
| --- | --- |
| Address starts with `0xbad` | `block` (`SANCTIONS_MATCH`) |
| Address starts with `0xdead` | `review` (`WATCHLIST_REVIEW`) |
| Amount over per-transaction limit | `block` (`LIMIT_PER_TX`) |
| Address over daily subject limit | `block` (`LIMIT_DAILY`) |
| Anything else | `allow` |

- `block` → `403 COMPLIANCE_BLOCKED`.
- `review` → `202 COMPLIANCE_REVIEW` with a review/check id; no quote or intent
  is issued. The web demo has no review UI, but an operator can use the admin
  review endpoints.
- A review approval is bound to the same subject type (deposit/withdrawal),
  address hash, pool and amount. Retrying the deposit intent or withdrawal quote
  within the approval lifetime proceeds without sending a note. A rejection
  blocks retries for the same decision lifetime. Hard blocks (sanctions fixture
  and limits) cannot be overridden by a review.
- Review decisions default to `VEILPOOL_REVIEW_DECISION_TTL_SECONDS` (24 h) and
  can be shortened per request with `expires_in_seconds` (or set with an
  absolute `expires_at`).
- Decisions are bound to subject, pool/amount and recipient hash, and expire
  (`VEILPOOL_COMPLIANCE_TTL_SECONDS`, default 300 s).
- Limits are stored in base units of the pool asset (mock simplification) and
  are seeded high enough for all six pools. Tests lower them through the DB.
- Addresses are hashed with `VEILPOOL_COMPLIANCE_HASH_SALT`; the compliance
  table does not store raw depositor/recipient addresses.

### Compliance review API

`GET /api/v1/admin/compliance/reviews` returns pending reviews by default
(`?status=pending|approved|rejected|all`, `?limit=1..200`). Items contain the
review id, subject type/ref, pool, amount, risk score, reason codes, provider,
policy version and timestamps. Decided items also include the operator `reason`
and `reviewed_by`. Items do **not** contain a raw address, note or proof
material.

`POST /api/v1/admin/compliance/reviews/{review_id}/decision`:

```json
{
  "decision": "approve",
  "reason": "false positive cleared by operator",
  "expires_in_seconds": 3600
}
```

`decision` is `approve` or `reject`; `reason` is required; `expires_in_seconds`
is optional (1..604800). An absolute ISO-8601 `expires_at` may be supplied
instead, but not both. Each decision appends an append-only, hash-chained
audit row (`compliance.review.approved` or `compliance.review.rejected`).

---

## Security / data boundaries

- **No notes endpoint and no note column.** Request models reject unknown
  fields and any key containing `note`, `passphrase`, `secret`, `mnemonic`,
  `private_key` or `preimage`.
- **Local mode never accepts a private key.** The dev bridge asks the local
  Anvil node to send from its unlocked account 0. No key is read, accepted,
  stored or logged, and the RPC/indexer/contract URLs must be loopback.
- **Indexer data is allow-listed.** Local responses only forward the public
  chain fields listed above. Unknown indexer fields (including note-like keys)
  are dropped rather than proxied.
- **No request-body logging.** The local deposit and withdrawal handlers never
  log their request bodies at info level. Error responses do not echo the
  submitted proof except in the deliberate `LOCAL_WITHDRAWAL_DISABLED`
  manual-submission calldata, which is public transaction data by definition.
- The withdrawal bridge persists the public withdrawal fields and a SHA-256
  digest of the ABI proof for replay discrimination. It never persists the
  proof bytes, witness, note or secret. The Merkle-path proxy forwards only
  public path fields.
- The server stores public-ish facts only: commitments, leaf indexes, tx hashes,
  roots, nullifiers, recipient address (for compliance in this MVP), and mock
  compliance decisions.
- A nullifier is unique per pool for canonical withdrawals. The mock chain
  immediately confirms withdrawals, so a spent nullifier is rejected with
  `409 NULLIFIER_SPENT`.
- Paused pools reject deposit intents, mock deposits, quotes and submissions.
- Admin pause/resume and review decisions require `X-Admin-Token` (default
  `dev-admin`) and append an audit row. When `VEILPOOL_REQUIRE_AUTH=true`, they
  also require the bearer token.
- Review decisions are audit records with actor, reason, decision, expiry and
  request id. The audit log remains append-only.
- Rate limits are in-memory per process and keyed by hashed bearer token or
  client IP. They reset on restart and are not shared across workers.
- Request bodies over `VEILPOOL_MAX_BODY_BYTES` are rejected before route
  handling. Responses carry `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, and `Cache-Control: no-store` on non-public
  responses.
- The audit log is append-only in application code and hash-chained. On SQLite,
  triggers also reject `UPDATE`/`DELETE` on `audit_log`.
- Errors never echo submitted field values. Full addresses and proof material
  are not logged.

---

## Schema notes

- Partial unique indexes are real SQLite partial indexes:
  - `deposits(tx_hash, log_index) WHERE is_canonical`
  - `deposits(pool_id, leaf_index) WHERE is_canonical`
  - `withdrawals(pool_id, nullifier_hash) WHERE is_canonical`
  - `withdrawals(tx_hash, log_index) WHERE is_canonical`
- `nullifiers` uses a composite primary key `(pool_id, nullifier_hash)`.
- `local_withdrawal_broadcasts` is keyed by `quote_id` and stores public
  withdrawal fields plus a SHA-256 proof digest. It never stores proof bytes.
  Like `local_deposit_broadcasts`, it prevents a timeout retry from sending a
  second transaction.
- Token amounts use `NUMERIC(78, 0)` on PostgreSQL and an exact-text variant on
  SQLite, avoiding float precision loss for uint256-scale values.
- No migration framework is included; tables are created with
  `Base.metadata.create_all` for the local demo.

---

## Environment

See `.env.example`. Important variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VEILPOOL_MODE` | `mock` | `mock` or `local` |
| `DATABASE_URL` | `sqlite:///./veilpool.db` | SQLAlchemy URL |
| `VEILPOOL_ADMIN_TOKEN` | `dev-admin` | Admin header token |
| `VEILPOOL_REQUIRE_AUTH` | `false` | Require a bearer token on non-public endpoints |
| `VEILPOOL_API_TOKEN` | `dev-api-token` | Development bearer token |
| `VEILPOOL_RATE_LIMIT_ENABLED` | `true` | Enable in-memory token buckets |
| `VEILPOOL_RATE_LIMIT_WINDOW_SECONDS` | `60` | Bucket refill window |
| `VEILPOOL_RATE_LIMIT_DEPOSIT_INTENT` | `10` | Deposit intents per window |
| `VEILPOOL_RATE_LIMIT_WITHDRAWAL_QUOTE` | `10` | Withdrawal quotes per window |
| `VEILPOOL_RATE_LIMIT_WITHDRAWAL_SUBMIT` | `5` | Withdrawal submissions per window |
| `VEILPOOL_RATE_LIMIT_COMPLIANCE` | `30` | Compliance endpoint requests per window |
| `VEILPOOL_RATE_LIMIT_ADMIN` | `60` | Admin requests per window |
| `VEILPOOL_RATE_LIMIT_LOCAL_DEPOSIT` | `5` | Local Anvil deposit bridge requests per window |
| `VEILPOOL_RATE_LIMIT_LOCAL_WITHDRAWAL` | `5` | Local Anvil withdrawal bridge requests per window |
| `VEILPOOL_RATE_LIMIT_POOL_PATH` | `30` | Local public Merkle-path proxy requests per window |
| `VEILPOOL_MAX_BODY_BYTES` | `65536` | Maximum request body size |
| `VEILPOOL_REVIEW_DECISION_TTL_SECONDS` | `86400` | Default review decision lifetime |
| `VEILPOOL_CHAIN_ID` | `11155111` | Testnet only; `local` requires `31337`; mainnet rejected |
| `VEILPOOL_CONTRACT_ADDRESS` | required in local | Single deployed `VeilPool` address |
| `VEILPOOL_INDEXER_URL` | `http://127.0.0.1:8100` | Standalone indexer base URL; loopback only in local |
| `VEILPOOL_INDEXER_TIMEOUT_SECONDS` | `3` | Indexer HTTP timeout (also used for the local RPC) |
| `VEILPOOL_LOCAL_RPC_URL` | `http://127.0.0.1:8545` | Local Anvil RPC URL; loopback only |
| `VEILPOOL_LOCAL_FROM_ADDRESS` | Anvil account 0 | Unlocked Anvil sender for local auto-deposit |
| `VEILPOOL_LOCAL_AUTO_DEPOSIT` | `false` | Send `deposit(bytes32)` through Anvil when true |
| `VEILPOOL_LOCAL_DEPOSIT_TIMEOUT_SECONDS` | `15` | Indexer confirmation poll timeout |
| `VEILPOOL_LOCAL_AUTO_WITHDRAW` | `false` | Send `withdraw(...)` through Anvil when true |
| `VEILPOOL_LOCAL_WITHDRAWAL_TIMEOUT_SECONDS` | `20` | Withdrawal indexer confirmation poll timeout |
| `VEILPOOL_LOCAL_VERIFIER_KIND` | `mock` | `mock` or `groth16`; controls local labels/warnings only |
| `VEILPOOL_LOCAL_MATURITY_SECONDS` | unset | Local spike override for seeded ETH pool maturity (e.g. `0` for DeployPoseidon) |
| `VEILPOOL_INTENT_TTL_SECONDS` | `600` | Deposit intent lifetime |
| `VEILPOOL_QUOTE_TTL_SECONDS` | `300` | Withdrawal quote lifetime |
| `VEILPOOL_COMPLIANCE_TTL_SECONDS` | `300` | Decision lifetime |
| `VEILPOOL_ROOT_WINDOW_SIZE` | `20` | Accepted root history depth |
| `VEILPOOL_COMPLIANCE_HASH_SALT` | `veilpool-dev-salt` | Address hash salt |
| `VEILPOOL_MOCK_START_BLOCK` | `6000000` | Mock indexer cursor start |
| `VEILPOOL_MOCK_MATURITY_SECONDS` | unset | Test override for seeded maturity |

The app does not auto-load `.env`; export the variables in the shell or use your
process manager. `.env.example` documents the full set. `VEILPOOL_DEV_BEARER_TOKEN`,
`VEILPOOL_BEARER_TOKEN` and `VEILPOOL_AUTH_TOKEN` are accepted as aliases for
`VEILPOOL_API_TOKEN`.

---

## Known gaps (intentional for this MVP)

1. **No production ZK.** `MockVerifier` checks proof encoding/shape, not
   membership, nullifier derivation or any ZK relation. A local
   `VeilPoolPoseidon` + `Groth16VerifierAdapter` deployment can be labelled with
   `VEILPOOL_LOCAL_VERIFIER_KIND=groth16`, but its circuit/adapter are a local
   spike and its zkey is a single-machine development setup. Neither mode is
   audited or private.
2. **Dev Anvil bridges, not a relayer.** Local mode can bridge deposits and
   withdrawals through Anvil's unlocked account 0 and proxy public Merkle
   paths. The withdrawal bridge is a relayer-like dev shortcut: the Anvil
   account is `msg.sender`, receives the relayer fee, and there is no relayer
   authentication, private order flow, fee market, retry worker, reorg
   reconciliation or production key management. `POST /withdrawals/submit`,
   admin pause/resume and the mock chain remain mock-only.
3. **Maturity is client-side.** The API cannot map a nullifier to a deposit
   without the client note, so it does not independently enforce maturity.
   `maturity_seconds` is exposed for the client countdown.
4. **Compliance is a fixture.** No sanctions provider, jurisdiction/IP check or
   velocity limit. Provider failure semantics are not simulated. The admin
   review queue is a local workflow over `compliance_checks`; there is no
   reviewer identity system beyond the dev admin token.
5. **Development auth only.** `VEILPOOL_REQUIRE_AUTH` uses one shared bearer
   token. There are no user sessions, cookies, CSRF tokens, TOTP/role checks or
   key rotation. Rate limits are in-memory, per process, and not shared across
   workers or restarts. With one shared bearer token, token-keyed buckets are
   shared by every caller using that token; deployments behind a NAT also share
   IP-keyed buckets. The default local demo remains unauthenticated.
6. **No Postgres migrations.** The schema is SQLite-first. Partial indexes and
   the `Wei` type are written to be Postgres-compatible, but no migration files
   or Postgres integration tests are included. The exact-amount column is text
   on SQLite and `NUMERIC(78,0)` on Postgres.
7. **No reorg/indexer reconstruction.** Canonical flags exist, but the mock never
   produces reorged rows or rebuilds roots from raw events.
8. **Approximate accounting.** Anonymity set is unspent canonical deposits; fees
   and gas are not reconciled into a pool balance ledger.
9. **No relayer gateway or heartbeat endpoint.** Relayers are seeded mock rows.
   The local withdrawal bridge calls Anvil directly from the operator account;
   it is not a production non-custodial relayer and does not accept relayer
   auth or private proofs.
10. **Root/proof history is minimal.** The mock root endpoint exposes recent
    snapshots. Local mode exposes recent indexer roots and a public
    membership-path proxy, but there is no path cache, path freshness policy,
    or root-rebuild verification in the API.
11. **Public-read throttling is partial.** `/compliance/policy` uses the
    compliance bucket, but `/pools*` and `/relayers*` are not separately
    rate-limited in this MVP.
