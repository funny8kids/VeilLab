# VeilPool Web

React + TypeScript + Vite implementation of the eight VeilPool screens:
Overview, Deposit, Withdraw, Pools, Activity, Relayers, Compliance and Settings.

> **Not a production mixer.** This is a testnet-only local demo. Local Anvil mode
> can generate a real Groth16 proof in the browser, but it uses a **development
> zkey with no ceremony** and an unaudited circuit. Mock/demo mode still uses a
> proof-shaped value, not a proof. There is no wallet signing, no production
> chain custody, no real relayer network, no production key management and no
> mainnet path. Do not use any mode with real funds.

The visual language follows `prototype/index.html` and `prototype/styles.css`
(tokens, cards, typography, motion, dark/light themes, EN/中文).

---

## Run

From `apps/web/`:

```powershell
npm.cmd install
npm.cmd run dev
```

Open <http://127.0.0.1:5173/overview>.

```powershell
npm.cmd run build      # tsc --noEmit && vite build
npm.cmd test           # Vitest
npm.cmd run preview    # serve dist/ locally
```

The test suite covers the note backup gate, the "no note in API payload"
boundary (including mock/local deposit, vault-selected withdrawal and local
Groth16 withdrawal calls), optional bearer-token headers, mock/local health-mode
detection, local deposit routing and manual-instruction mapping, the local
withdrawal mode/`submission_available` gate, note parsing/commitment integrity,
Poseidon vectors against `circuits/test-vectors/membership-v1.json`
(commitment, nullifier, zero hash, 8-leaf root and Merkle path), note v2
generation/parsing and v1/v2 compatibility, witness construction against
`circuits/build/local-input.json` (skipped when build artifacts are absent),
256-byte proof encoding against `circuits/build/local-proof-hex.json`, the live
path-response pool-id shape, 20-level path and root validation, v1-note
rejection, the local proof request whitelist, proof-path and local-withdrawal
API calls with mocked `fetch`, passphrase encryption, v1 and v2 vault note
retrieval, backup/export/import, refresh/lock behaviour, the unspent-note picker
set, and the auto-lock boundary.

---

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL for the VeilPool API |
| `VITE_API_TOKEN` | unset | Optional local-dev bearer token |
| `VITE_ZK_NOTES` | unset/false | Generate circuit-compatible note v2 in mock/demo mode too |

Copy `.env.example` to `.env.local` to override it. Vite only exposes variables
prefixed with `VITE_`.

### Poseidon and note v2

Notes are generated in the browser and have two formats:

- **v1 (`veilnote1`)** — the original demo/mock note. Its commitment and
  nullifier use SHA-256 and are **not** circuit-compatible.
- **v2 (`veilnote2`)** — the circuit-compatible format. It is used
  automatically in local Anvil mode, and in mock/demo mode when
  `VITE_ZK_NOTES=true`. It stores canonical BN254 field elements and computes:

  ```text
  commitment = Poseidon6(DOMAIN_COMMITMENT, chain_id, pool_id_field,
                         denomination_wei, secret, nullifier_secret)
  nullifier  = Poseidon5(DOMAIN_NULLIFIER, chain_id, pool_id_field,
                         commitment, nullifier_secret)
  ```

  Domain tags are the circuit constants:
  `0x7665696c706f6f6c2d636f6d6d69742d7631` (commitment) and
  `0x7665696c706f6f6c2d6e756c6c2d7631` (nullifier). `pool_id_field` is
  `0x00 || UTF-8(pool_id) || zero padding` to 32 bytes (1–31 UTF-8 bytes,
  no NUL), so it is below `2^248`.

The Poseidon implementation in `src/lib/poseidon.ts` is pure TypeScript/BigInt
and matches circomlib 2.0.5 (`Poseidon(3)`, `Poseidon(5)` and `Poseidon(6)`).
The round constants and MDS matrices are committed in
`src/lib/poseidonConstants.ts`; they are generated from
`circuits/node_modules/circomlibjs/src/poseidon_constants.json` (source
SHA-256 `354f31bbed9d9a8b884d8f2181e339cb425b6e3e4cc7240bd3dd22f0070f3f2c`)
by `scripts/generate-poseidon-constants.mjs`:

```powershell
npm.cmd run generate:poseidon
```

Run `npm.cmd install` in `circuits/` first so the source constants exist.
Regenerate and review the generated file whenever the circomlib version or
the required Poseidon arities change.

`parseNote()` accepts both prefixes and verifies the stored hashes against the
contents. v1 keeps its existing behaviour; v2 also re-derives the canonical
pool-id field, commitment and nullifier. The vault is opaque encrypted JSON, so
it stores, lists, exports and imports both versions; mixing v1 and v2 notes in
one vault is supported.

### Browser-local Groth16 prover (local Anvil mode)

Local Anvil mode now wires the withdrawal flow end to end:

1. The note is parsed in the tab. It must be v2. A v1 note shows
   “This note is not a ZK note. Regenerate it in local mode.” and cannot quote
   or submit.
2. `GET /api/v1/pools/{pool_id}/path/{commitment}` returns the public Merkle
   path. The browser re-hashes it locally with Poseidon before proving. The
   path response's `pool_id` is the chain's right-padded `bytes32` deploy label
   (`0x706f…0000`), not the circuit's zero-prefixed field (`0x00706f…`). The
   prover prefers `pool_key` and accepts the deploy label only when shifting out
   its zero low byte reproduces the note's field. The circuit encoding is not
   changed.
3. `src/lib/prover.ts` builds the Circom witness. Public inputs are exactly
   `chain_id`, `pool_id`, `root`, `nullifier`, `recipient`, `fee`; private
   inputs are `secret`, `nullifier_secret`, `denomination`,
   `pathElements[20]`, `pathIndices[20]`.
4. A dedicated Web Worker (`src/workers/prover.worker.ts`) dynamically imports
   `snarkjs` and runs `groth16.fullProve`, then `groth16.verify` against the
   local verification key.
5. Only the 256-byte ABI proof and the six public signals are POSTed to
   `/api/v1/local/withdrawals`. The note, witness and secret field values never
   leave the browser and are never logged.

Mock/demo mode is unchanged and still uses `buildMockProof`. Local mode never
falls back to the mock withdrawal route.

#### Artifacts

The circuit build directory is not committed. Copy the development artifacts
into `apps/web/public/zk/` before starting the web app:

```powershell
node circuits/scripts/export-web-artifacts.mjs
```

Expected files and approximate sizes from the current build:

| File | Size |
| --- | --- |
| `public/zk/membership.wasm` | 3.4 MiB |
| `public/zk/membership.zkey` | 6.0 MiB |
| `public/zk/verification_key.json` | 3.8 KiB |

`public/zk/` is gitignored. The worker loads the fixed public URLs
`/zk/membership.wasm`, `/zk/membership.zkey` and `/zk/verification_key.json`.
There is no `VEILPOOL_STATIC_ARTIFACTS` environment variable in the web app; if
you serve the build under a sub-path, keep these absolute public paths valid or
change the defaults in `src/lib/prover.ts` and
`src/workers/prover.worker.ts`.

`snarkjs@0.7.6` is loaded only from the worker when a proof is requested. The
normal app bundle does not import it at startup. The measured production build
has a separate worker chunk (~2 kB) and a snarkjs worker chunk (~455 kB); the
main app JS is ~476 kB (~163 kB gzip). Those are bundle sizes, not proving-time
measurements.

If an artifact is missing or a dev server answers with `index.html`, the UI
tells the user to run the export script. This is a **development zkey**, not a
trusted-setup ceremony. Anyone who can recover its toxic waste can forge proofs.
The circuit and Poseidon implementation are unaudited. Do not use these
artifacts with real funds.

### Local development bearer token

If `VITE_API_TOKEN` is set when Vite starts or builds, every API request sends
`Authorization: Bearer <token>`. If it is unset or empty, no `Authorization`
header is sent. The value is read only from `import.meta.env`; it is never read
from the URL, `localStorage`, a note or a form field, and it is never logged.

This is a local-development convenience only. **Do not bake a real token into a
public production build.** Anything compiled into the browser bundle is visible
to users; a static bundle is not a secret store. If the API requires auth in a
real deployment, use a same-origin proxy or a server-side session flow instead.
When a token is configured, the API's CORS policy must allow the
`Authorization` header.

### API mode, chain labels and demo fallback

The app calls `GET /api/v1/health` on load. Health is retried three times with a
short backoff. The health `mode` field decides how the UI labels the backend:

- `mode: "mock"` (or a legacy response with no mode) → `MOCK CHAIN`
- `mode: "local"` → `ANVIL LOCAL`; the Settings API panel also shows the chain
  ID, the chain service, indexer status and indexer lag. High lag or a stalled
  indexer shows a warning.
- health unreachable → `DEMO` with clearly labelled demo fixtures
- health succeeds but a core resource fails → the chain-mode badge plus
  `PARTIAL API`

Local Anvil mode is a development environment. It is not production, not
audited and not private infrastructure.

If health is unreachable, the entire UI renders with clearly labelled demo
fixtures:

- topbar: `DEMO`
- a persistent "API unavailable" banner with the API URL and a retry button
- demo/sample badges on illustrative panels

If the API health check succeeds but any core resource (pools, relayers or policy)
fails or returns an empty list, the affected panel falls back to demo data and the
header shows the chain mode plus `PARTIAL API`.

While the app is in demo/partial mode it silently retries every 30 seconds. It also
revalidates health and pools on window focus, so recovering the API does not
require a reload.

Implemented API calls (all under `/api/v1`):

- `GET /health`
- `GET /pools`
- `GET /relayers`
- `GET /compliance/policy`
- `GET /pools/{id}/root`
- `GET /pools/{id}/path/{commitment}` (local Anvil mode; public Merkle path proxy)
- `POST /deposits/intent` (with `Idempotency-Key`)
- `POST /mock/deposits` (also tries `/deposits/mock` on 404/405; sends `intent_id` + `commitment` only)
- `POST /local/deposits` (local Anvil mode; sends `intent_id` + `commitment` only)
- `POST /withdrawals/quote`
- `POST /withdrawals/submit` (with `Idempotency-Key`; not used in local Anvil mode)
- `POST /local/withdrawals` (local Anvil mode; sends `quote_id`, `proof`, `root`, `nullifier`, `recipient` and `relayer_fee_wei` only)

There is **no** `/activity` call. Activity is local-only.

The API must allow browser CORS from the web origin for the methods and headers
above, including `Authorization` when `VITE_API_TOKEN` is set. Session-cookie and
CSRF handling are not implemented; the MVP should expose the public endpoints
described in the API spec or run behind a same-origin proxy. The optional bearer
token is a local-development helper, not a production authentication design. When
serving the production build from a static host, add an SPA fallback rewrite to
`index.html` for the eight browser routes.

### Local Anvil mode behaviour

When health reports `mode: "local"`:

- **Deposit:** the note is generated as v2 with the API health `chain_id`
  (default `31337` when health does not report one). The intent still goes to
  `POST /deposits/intent`. The deposit is then submitted to
  `POST /local/deposits` instead of the mock route. The UI shows an explicit
  `Submitting to local Anvil…` state while waiting for the local chain and
  indexer. A local activity row is marked `confirmed` only when
  the API returns a deposit with a `tx_hash`; the returned block number is shown.
  - `409 LOCAL_DEPOSIT_DISABLED`: the deposit is **not** successful. The screen
    shows the contract address, denomination (wei), calldata and instruction
    from the API, with copy buttons. The note and pending intent stay in the
    tab so the user can retry after enabling local deposits.
  - `504 INDEXER_CONFIRMATION_TIMEOUT`, `502`, `503` or a client timeout: the
    screen shows `Deposit not confirmed`, the transaction hash when supplied,
    and a retry that reuses the same intent. Nothing is marked confirmed.
  - A local-mode intent failure is shown as an API error; it does not silently
    fall back to a demo success.
- **Withdraw:** quote/screening and the vault note picker work. A local quote
  that returns `submission_available: true` enables the real path: fetch the
  Merkle path, prove in the browser worker, then submit to
  `/local/withdrawals`. The progress states are fetching path, loading circuit,
  proving locally, verifying, submitting and confirmed. The UI also respects
  `submission_available: false` and disables submission with a clear warning.
  It never sends a mock withdrawal or simulates success in local mode. Activity
  is recorded only after the API returns `status: "confirmed"` with a
  `tx_hash`; a failure preserves the note and records nothing.
- **Settings:** the API connection panel shows the base URL, auth state
  (`token configured` / `no token`), chain mode, chain ID and indexer
  status/lag. High lag or a stalled indexer is warned about.

### Local ZK withdrawal E2E (Anvil, exact steps)

This is the local spike path. It uses Anvil account 0's **public** development
key and a development zkey. Never use a real key or real funds.

```powershell
# Terminal 1 — Anvil
anvil --host 127.0.0.1 --port 8545 --chain-id 31337

# Terminal 2 — deploy the Poseidon/Groth16 spike
Set-Location G:\Worker-Space\VeilLab\contracts
$Forge = "$env:LOCALAPPDATA\veilpool-tools\foundry-v1.9.0\forge.exe"
& $Forge script script/DeployPoseidon.s.sol:DeployPoseidon `
  --rpc-url http://127.0.0.1:8545 `
  --broadcast `
  --unlocked --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 `
  -vv
# Copy the printed VeilPoolPoseidon address.

# Terminal 3 — copy browser artifacts (run from the repo root)
Set-Location G:\Worker-Space\VeilLab
node circuits/scripts/export-web-artifacts.mjs

# Terminal 4 — indexer (use the VeilPoolPoseidon address)
Set-Location G:\Worker-Space\VeilLab\apps\indexer
$env:ANVIL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_ADDRESS = "<VeilPoolPoseidon address>"
$env:INDEXER_PORT = "8100"
$env:INDEXER_START_BLOCK = "0"
python -m veilpool_indexer

# Terminal 5 — API in local mode
Set-Location G:\Worker-Space\VeilLab\apps\api
$env:VEILPOOL_MODE = "local"
$env:VEILPOOL_CHAIN_ID = "31337"
$env:VEILPOOL_CONTRACT_ADDRESS = "<same VeilPoolPoseidon address>"
$env:VEILPOOL_INDEXER_URL = "http://127.0.0.1:8100"
$env:VEILPOOL_LOCAL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_LOCAL_AUTO_DEPOSIT = "true"
$env:VEILPOOL_LOCAL_AUTO_WITHDRAW = "true"
$env:VEILPOOL_LOCAL_VERIFIER_KIND = "groth16"
$env:DATABASE_URL = "sqlite:///./veilpool-local.db"
python -m uvicorn veilpool_api.main:app --reload --port 8000

# Terminal 6 — web
Set-Location G:\Worker-Space\VeilLab\apps\web
npm.cmd install
npm.cmd run dev
```

Then:

1. Open <http://127.0.0.1:5173/deposit>, choose `pool_eth_01` (0.1 ETH) and
   deposit. Local mode always creates a v2 note. With
   `VEILPOOL_LOCAL_AUTO_DEPOSIT=true` the API submits it and the indexer confirms
   it.
2. Open `/withdraw`, select the unspent vault note, enter a fresh recipient
   (for example `0x2222222222222222222222222222222222222222`; `0xdead…` triggers
   the review fixture), choose a relayer and request a quote.
3. Click **Prove & withdraw locally**. The worker fetches the path, loads the
   circuit, proves, verifies, and POSTs the 256-byte proof and public signals to
   `/api/v1/local/withdrawals`.
4. The result shows the local tx hash, block, nullifier, recipient, fee and
   `ANVIL LOCAL` badge. Activity is recorded only after the API reports
   `status: "confirmed"` with a `tx_hash`.

`VEILPOOL_LOCAL_AUTO_WITHDRAW=false` keeps quotes at
`submission_available:false` and returns manual calldata from the API; the web
UI disables the prove button in that case. Re-run the export script after any
circuit/zkey rebuild, then reload the page. The app does not use a
`VEILPOOL_STATIC_ARTIFACTS` variable; the fixed `/zk/...` URLs are the artifact
contract between `public/zk/` and the worker.

---

## Note privacy boundaries

Deposit:

1. The note is generated in the browser with `crypto.getRandomValues`.
   Mock/demo mode uses legacy v1 unless `VITE_ZK_NOTES=true`; local Anvil mode
   always uses circuit-compatible v2.
2. It is shown once. No route re-displays it.
3. It is saved in an encrypted local vault (`veilpool.vault.v1`) using AES-GCM
   and a random 256-bit key held in `sessionStorage` for this tab.
4. The user must confirm the backup checkbox before "Confirm deposit" enables.
5. The user can download an encrypted backup; the backup passphrase is stretched
   locally with PBKDF2-SHA256 (210,000 iterations) and the note is encrypted with
   AES-GCM. The passphrase is never transmitted.
6. The deposit request contains only `pool_id`, `depositor_address`, `amount` and
   `commitment`. The note and its secrets are not included.
7. After a successful intent, the client calls `POST /mock/deposits` in mock
   mode or `POST /local/deposits` in local Anvil mode, with `intent_id` and the
   same commitment. Activity becomes `confirmed` only after the corresponding
   event succeeds; local mode additionally requires a returned `tx_hash`. If it
   fails, the note stays visible and stored, the pending intent is retained in
   this tab, and the UI offers a retry that does not create a second intent.
8. In demo fallback mode the mock event is simulated locally, and both the result
   and activity row are labelled as local demo data. Local Anvil mode never uses
   this simulated success path.

Withdraw:

1. The pasted note, or a note selected from the local vault, is parsed only in
   the tab. `getNote()` decrypts the selected record with the session key.
2. The picker lists unspent vault notes with pool, denomination and backup status.
   A selected note is shown in the form as a masked value, not as the full token.
3. The recipient and relayer form request contains no note material. Quote and
   submit payloads are unchanged by the vault picker.
4. In mock/demo mode the proof is derived from public signals and is explicitly
   labelled `MOCK PROOF`.
5. In local Anvil mode the witness is built in the tab and sent only to a
   same-browser Web Worker. The worker returns the proof and public signals; the
   note, witness and secret field values are never sent to the API, logged or
   stored in activity.
6. Local submission carries exactly `quote_id`, `proof`, `root`, `nullifier`,
   `recipient` and `relayer_fee_wei`. The note is cleared from the form only
   after the API confirms the withdrawal with a `tx_hash`. A failed attempt keeps
   the note so the user can retry.
7. The mock submission path carries `proof`, `public_signals` and the recipient.
   The note is cleared from the form after submission.

As defence in depth, every POST body passes `assertNoNoteMaterial()` before
`fetch`; it throws if a `veilnote1…` or `veilnote2…` token, or a note/secret
field, appears.

The local vault is demo-grade. It is not audited, not a hardware wallet and its
session key is in browser storage. The vault auto-locks after 15 minutes without
input and when the tab is hidden or closed. **Locking discards the random session
key, so no password can reopen the vault.** Export an encrypted vault backup
before closing or clearing browser data; after a lock, import that backup in
Settings to create a new session and restore notes. If you have no backup, the
encrypted records are unrecoverable by design.

---

## Screens

| Route | What is functional |
| --- | --- |
| `/overview` | API/demo stats, compliance summary, active pools, local recent activity |
| `/deposit` | Pool selection, client-side note generation (v1 mock/demo, v2 local/ZK-flag), backup gate, encrypted backup, intent + mock or local Anvil deposit, retryable failure and manual-instruction state |
| `/withdraw` | Vault note picker, local note parsing, recipient validation, relayer selection, quote/screening, mock proof submit; in local Anvil mode, browser-local Groth16 prove and submit to `/local/withdrawals` |
| `/pools` | API/demo pools, set size, fee, maturity, liquidity, refresh |
| `/activity` | Local-only history from browser storage, filters, JSON export |
| `/relayers` | API/demo relayer list, compatibility, fee/uptime/latency, selection |
| `/compliance` | API/demo policy, decision states, limits, screening sources, audit view |
| `/settings` | API connection/auth/mode/indexer status, testnet networks, encrypted vault export/import, lock now, theme/language, clear local data |

The shell includes EN/中文 switching, dark/light switching, the persistent
testnet badge and API/demo status. Preferences persist in `localStorage`.
`?theme=light|dark` and `?lang=en|zh` can be used for deep links and screenshots.

---

## Mock / demo / local-chain limitations

- **Mock proof:** a deterministic SHA-256-shaped value, not a zk proof. It proves
  nothing and is not verifiable by a real circuit. Mock/demo mode still uses it.
- **Local ZK proving uses a development setup.** The browser builds a real
  Poseidon witness and Groth16 proof for the local membership circuit, but the
  zkey is a single-machine development setup and the circuit, Poseidon
  implementation and verifier adapter are unaudited. This is not production
  cryptography, privacy or security.
- **Browser proving performance is not benchmarked.** No browser proof-time or
  memory claim is made here. The local CLI/Node spike is not a browser result.
- **Mock chain:** no wallet, signing, broadcast or indexer. The mock deposit route
  only records the event in the API's mock chain; no real funds move.
- **Local Anvil mode is development infrastructure.** It is not production, not
  audited and not private infrastructure. Local deposits rely on a local chain
  plus indexer; the browser has no wallet and does not sign or broadcast.
- **Local deposits can be disabled or unconfirmed.** `409 LOCAL_DEPOSIT_DISABLED`
  requires a manual contract call shown in the UI; timeouts and indexer errors
  leave the deposit unconfirmed and retryable. The UI does not poll for
  confirmation beyond a retry.
- **Local withdrawals need the local Anvil bridge and a v2 note.** The quote must
  return `submission_available: true` and the API must have
  `VEILPOOL_LOCAL_AUTO_WITHDRAW=true`. A v1 note must be regenerated in local
  mode. Local mode never falls back to the mock withdrawal route.
- **The local withdrawal bridge is custodial development infrastructure.** Anvil
  account 0 submits the transaction and receives the relayer fee. Do not use it
  with real accounts or real funds.
- **Local API auth is a build-time dev token.** `VITE_API_TOKEN` is visible to
  anyone who can inspect the bundle; do not use a real token in a public build.
- **Compliance:** demo decisions and policy fields are deterministic fixtures, not
  a sanctions provider. Manual-review and blocked states are represented but the
  demo quote path uses an allow fixture.
- **Relayers:** fixtures unless the API returns live data. No relayer is paid and
  no relayer gateway is contacted.
- **Activity:** browser-local only, no cross-device sync, no server account graph.
- **Auto-lock:** tab-local and demo-grade. There is no password recovery and no
  production session management; a lock always requires an encrypted backup import.
- **Desktop-first** layout (target width ≥ 1180 px); no mobile layout.
- Demo-grade vault and backup encryption; not audited.
- No mainnet registry, selector, RPC or UI path.

---

## Known gaps

- A secure/production Groth16 setup and independent audit. The browser prover
  works with the development zkey only.
- Browser proving benchmarks (proof time, memory, mobile devices and cold
  starts) have not been measured.
- Root freshness and maturity checks before proving/submitting. The API/contract
  remain authoritative and may reject a stale root or immature pool.
- Wallet connection, signing and automatic local-chain broadcast (local
  deposits/withdrawals use the API bridge; disabled local deposits use a
  copyable manual call).
- Production relayer submission, stuck-transaction handling and proof replay
  UX beyond the local quote semantics.
- Background local deposit confirmation polling after an indexer timeout.
- Real relayer gateway, quote signing, fallback and stuck-transaction handling.
- Production compliance provider, review queue and audit export format.
- Production API authentication, CSRF and session handling (the optional bearer
  token is a build-time local-dev credential, not a production auth design).
- The picker only lists unspent notes from this browser; there is no note-health
  check against the chain.
- Tab close discards the session key; a page refresh keeps it. Switching tabs does not lock the vault.
- Accessibility audit on every screen; keyboard-first note workflow.

## Related

- [Prototype](../../prototype/README.md)
- [MVP scope](../../docs/veilpool/MVP_SCOPE.md)
- [Product spec](../../docs/veilpool/PRODUCT_SPEC.md)
- [API spec](../../docs/veilpool/API_SPEC.md)
