# VeilPool API Specification

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [Architecture](ARCHITECTURE.md) · [Data Model](DATA_MODEL.md) · [Compliance](COMPLIANCE.md)

Base path: `/api/v1`. JSON, UTF-8. Errors use `application/problem+json`.

> **Hard rule:** no endpoint accepts a secret note, note passphrase or raw proof input.
> Withdrawal requests carry a proof and public signals only.

---

## 1. Authentication

| Client | Mechanism |
| --- | --- |
| Web user | HttpOnly session cookie + CSRF header |
| CLI / relayer | Bearer token (scoped) or mTLS |
| Admin | Session + TOTP + role check |
| Internal indexer | mTLS service identity |

Public endpoints: `GET /pools`, `GET /pools/{id}`, `GET /health`, `GET /compliance/policy`.
All other endpoints require auth.

> **MVP implementation note:** the local demo ships one shared development bearer token.
> `VEILPOOL_REQUIRE_AUTH=false` keeps the web demo open; when set to `true`, non-public
> endpoints require `Authorization: Bearer <VEILPOOL_API_TOKEN>` and admin endpoints also
> require `X-Admin-Token`. This is not the session/TOTP design above and must not be used
> outside a local demo.

---

## 2. Pools

### `GET /pools`

Returns active and paused pools.

```json
{
  "items": [
    {
      "id": "pool_eth_01",
      "chain_id": 11155111,
      "asset": "ETH",
      "denomination": "0.1",
      "denomination_wei": "100000000000000000",
      "maturity_seconds": 1800,
      "protocol_fee_bps": 24,
      "anonymity_set": 842,
      "liquidity_wei": "1820000000000000000",
      "status": "active",
      "min_set_size": 100
    }
  ],
  "next_cursor": null
}
```

### `GET /pools/{pool_id}`

Returns pool config, contract addresses, current root, last indexed block, maturity and set
size.

```json
{
  "id": "pool_eth_01",
  "chain_id": 11155111,
  "asset": "ETH",
  "denomination": "0.1",
  "tree_depth": 20,
  "maturity_seconds": 1800,
  "protocol_fee_bps": 24,
  "contract_address": "0x...",
  "verifier_address": "0x...",
  "root": "0x...",
  "indexed_block": 6123456,
  "confirmations": 12,
  "finality": "finalized",
  "anonymity_set": 842,
  "status": "active"
}
```

### `GET /pools/{pool_id}/anonymity`

```json
{
  "pool_id": "pool_eth_01",
  "unspent_matured_deposits": 842,
  "total_deposits": 1104,
  "total_withdrawals": 262,
  "updated_at": "2026-11-02T10:15:30Z"
}
```

### `GET /pools/{pool_id}/root`

Returns the current Merkle root and a short root history for proof generation.

```json
{
  "root": "0x...",
  "block_number": 6123456,
  "block_hash": "0x...",
  "root_history": [
    {"root": "0x...", "block_number": 6123450, "valid_until_block": 6123456}
  ]
}
```

### `GET /pools/{pool_id}/deposits/{tx_hash}`

Returns deposit indexing status for a transaction hash.

```json
{
  "tx_hash": "0x...",
  "pool_id": "pool_eth_01",
  "status": "confirmed",
  "commitment": "0x...",
  "leaf_index": 1103,
  "block_number": 6123456,
  "confirmations": 12,
  "indexed_at": "2026-11-02T10:15:30Z"
}
```

No endpoint returns a note, secret or raw proof input.

---

## 3. Deposit preparation

### `POST /deposits/intent`

Called before the wallet prompt. It screens the depositor address and returns a quote.
`Idempotency-Key` is required.

Request:

```json
{
  "pool_id": "pool_eth_01",
  "depositor_address": "0x...",
  "amount": "0.1"
}
```

Response:

```json
{
  "intent_id": "dep_01J...",
  "compliance": {"decision": "allow", "check_id": "cmp_01J...", "expires_at": "..."},
  "deposit_contract": "0x...",
  "denomination_wei": "100000000000000000",
  "protocol_fee_bps": 24,
  "expires_at": "2026-11-02T10:20:00Z"
}
```

Rules:

- The client must back up the note before calling this endpoint.
- A `block` decision returns `403` with a stable code.
- A `review` decision returns `202` and a review ID; no deposit prompt.
- The endpoint does not receive the note.

---

## 4. Withdrawal

### `POST /withdrawals/quote`

Request:

```json
{
  "pool_id": "pool_eth_01",
  "recipient_address": "0x...",
  "relayer_id": "rel_01"
}
```

Response:

```json
{
  "quote_id": "q_01J...",
  "relayer_id": "rel_01",
  "relayer_fee_bps": 24,
  "relayer_fee_wei": "240000000000000",
  "gas_estimate_wei": "310000000000000",
  "recipient_receives_wei": "99450000000000000",
  "expires_at": "2026-11-02T10:20:00Z",
  "compliance": {"decision": "allow", "check_id": "cmp_01J..."}
}
```

### `POST /withdrawals/submit`

Request contains **proof + public signals**, never the note:

```json
{
  "pool_id": "pool_eth_01",
  "quote_id": "q_01J...",
  "proof": "0x...",
  "public_signals": {
    "root": "0x...",
    "nullifier_hash": "0x...",
    "recipient": "0x...",
    "fee_wei": "240000000000000"
  },
  "recipient_address": "0x..."
}
```

Response `202`:

```json
{
  "withdrawal_id": "wdr_01J...",
  "status": "submitted",
  "tx_hash": "0x...",
  "relayer_id": "rel_01"
}
```

Rules:

- The server validates the proof shape and public signals; it does not need the note.
- The API forwards the validated request to the relayer gateway; the client does not need a
  direct connection to individual relayer nodes.
- The relayer cannot alter `recipient` or `fee` without invalidating the proof.
- Duplicate nullifier → `409 NULLIFIER_SPENT`.
- Expired quote → `409 QUOTE_EXPIRED`.
- Compliance block → `403 COMPLIANCE_BLOCKED`.
- The endpoint is idempotent by `Idempotency-Key`.

### `GET /withdrawals/{withdrawal_id}`

```json
{
  "id": "wdr_01J...",
  "status": "confirmed",
  "tx_hash": "0x...",
  "block_number": 6123456,
  "confirmations": 12,
  "nullifier_hash": "0x...",
  "recipient_address": "0x...",
  "failure_code": null
}
```

### `GET /withdrawals/by-nullifier/{nullifier_hash}`

Returns public status. This can be used by a client to check whether a note is spent, but the
client must understand that querying a nullifier derived from a note can leak information to
the API. Prefer local activity history; treat this endpoint as privacy-sensitive.

---

## 5. Relayers

### `GET /relayers`

```json
{
  "items": [
    {
      "id": "rel_01",
      "name": "Relay-01",
      "fee_bps": 24,
      "uptime_bps": 9998,
      "latency_ms": 38,
      "supported_pools": ["pool_eth_01", "pool_usdc_100"],
      "status": "online"
    }
  ]
}
```

### `GET /relayers/{relayer_id}`

Returns fee, uptime, latency, supported pools, compliance status and last heartbeat.

### `POST /relayers/{relayer_id}/heartbeat` (internal, mTLS)

Relayer heartbeat; not public.

---

## 6. Compliance

### `GET /compliance/policy`

Public policy summary: allowed jurisdictions, limits, list version, review SLA.

### `POST /compliance/check` (internal only)

Internal screening endpoint used by the API’s deposit/withdraw flows. Not exposed to
arbitrary clients.

```json
{
  "subject_type": "withdrawal",
  "address": "0x...",
  "pool_id": "pool_eth_01",
  "amount_wei": "100000000000000000"
}
```

Response:

```json
{
  "check_id": "cmp_01J...",
  "decision": "allow",
  "risk_score": 4,
  "reasons": [],
  "policy_version": 7,
  "expires_at": "2026-11-02T10:20:00Z"
}
```

Rules:

- `block` is final for the request.
- `review` creates a review item; no submission until a human decides.
- Decisions expire; expired decisions cannot be reused.
- Address is hashed where policy allows; raw address retention requires legal review.

### `GET /compliance/reviews` (admin)

List pending reviews with reason codes, risk score and age.

### `POST /compliance/reviews/{id}/decision` (admin)

Approve/reject with a reason. Audited.

---

## 7. Activity

**v1 is local-only.** The client derives activity from:

- its encrypted note vault,
- public deposit/withdrawal events queried by transaction hash,
- the local note state (`unspent`, `pending`, `spent`).

There is **no server-side account activity endpoint** in v1. This avoids building a
deposit→withdrawal graph and avoids linking notes to an account.

The prototype’s Activity screen is a client-side view. If a future version adds an optional
server-backed history, it must be explicit opt-in, separately consented and documented as a
privacy trade-off.

---

## 8. Admin

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/admin/pools` | Create pool |
| `PATCH` | `/admin/pools/{id}` | Fee/maturity/status (bounded) |
| `POST` | `/admin/pools/{id}/pause` | Pause with reason |
| `POST` | `/admin/pools/{id}/resume` | Resume |
| `GET` | `/admin/compliance/reviews` | Review queue |
| `POST` | `/admin/compliance/reviews/{id}/decision` | Approve/reject |
| `GET` | `/admin/audit` | Audit query |
| `POST` | `/admin/relayers/{id}/disable` | Disable relayer |

Admin actions require TOTP and are audited.

---

## 9. Errors

| Code | HTTP | Meaning |
| --- | --- | --- |
| `POOL_NOT_FOUND` | 404 | Unknown pool |
| `POOL_PAUSED` | 409 | Pool paused |
| `AMOUNT_MISMATCH` | 422 | Amount != denomination |
| `NOTE_INVALID` | 422 | Client-side only; API never receives note |
| `ROOT_STALE` | 409 | Root not current |
| `NULLIFIER_SPENT` | 409 | Double-spend |
| `QUOTE_EXPIRED` | 409 | Relayer quote expired |
| `COMPLIANCE_BLOCKED` | 403 | Policy block |
| `COMPLIANCE_REVIEW` | 202 | Manual review required |
| `RELAYER_OFFLINE` | 503 | Relayer unavailable |
| `PROOF_INVALID` | 422 | Proof/public signals invalid |
| `IDEMPOTENCY_MISMATCH` | 409 | Same key, different body |
| `RATE_LIMITED` | 429 | Limit exceeded |
| `CHAIN_NOT_ALLOWED` | 403 | Mainnet/unknown chain |

---

## 10. Rate limits

| Scope | Default |
| --- | --- |
| Public reads | 120/min/IP |
| Deposit intents | 10/min/account |
| Local deposits (dev) | 5/min/account |
| Withdrawal quotes | 10/min/account |
| Withdrawal submissions | 5/min/account |
| Compliance checks | 30/min/account |
| Admin | 60/min/operator |

The MVP implementation uses in-memory token buckets per process, keyed by hashed bearer token
or client IP. Limits reset on restart and are not shared across workers. Public reads are not
rate-limited in the MVP yet.

---

## 11. Local-chain mode (MVP implementation)

`VEILPOOL_MODE=local` reads public chain facts from the standalone indexer. It is local
Anvil only, requires `VEILPOOL_CHAIN_ID=31337`, a loopback indexer/RPC URL and
`VEILPOOL_CONTRACT_ADDRESS`. It is still **not private**: the deployed verifier is
`MockVerifier`.

### `POST /local/deposits`

Dev-only bridge from a deposit intent to a local Anvil transaction. The request contains only
public data:

```json
{
  "intent_id": "dep_...",
  "commitment": "0x<32 bytes>"
}
```

When `VEILPOOL_LOCAL_AUTO_DEPOSIT=true`, the API sends `deposit(bytes32)` from the local Anvil
unlocked account (`VEILPOOL_LOCAL_FROM_ADDRESS`) and waits for the indexer to observe the
event. The API never accepts or stores a private key.

Success is a normal deposit view plus:

```json
{
  "tx_hash": "0x...",
  "block_number": 4,
  "block_hash": "0x...",
  "confirmations": 1,
  "local_chain": "ANVIL",
  "chain_source": "indexer",
  "intent_id": "dep_...",
  "indexer_lag": 0,
  "finality": "final"
}
```

Errors:

| Status | Code | Meaning |
| --- | --- | --- |
| 404 | `LOCAL_ONLY` | Endpoint used outside local mode |
| 409 | `LOCAL_DEPOSIT_DISABLED` | Auto-deposit off; response includes contract address, denomination and calldata |
| 409 | `INTENT_EXPIRED` / `INTENT_CONSUMED` | Intent is no longer usable; a consumed intent replays the stored deposit |
| 409 | `COMMITMENT_MISMATCH` | Commitment differs from the intent |
| 502 | `INDEXER_MISMATCH` / `LOCAL_RPC_*` | Broadcast or indexer verification failed |
| 504 | `INDEXER_CONFIRMATION_TIMEOUT` | Transaction was broadcast but not indexed in time; the intent stays pending |

In local mode, mock-only writes (`/mock/deposits`, withdrawal submit, admin pause/resume)
return `MOCK_ONLY`. Deposit intents still expose the compliance decision and
`next_step:"POST /api/v1/local/deposits"`; they do not claim the deposit is complete.

The API drops unknown/note-like fields from indexer payloads and never stores note material.

### `GET /pools/{pool_id}/path/{commitment}`

Local mode read-only proxy to the indexer's Poseidon Merkle path. It returns only public chain
facts:

```json
{
  "commitment": "0x...",
  "leaf_index": 1,
  "leaf_count": 2,
  "tree_depth": 20,
  "root": "0x...",
  "path_elements": ["0x... (20)"],
  "path_indices": [1, 0, "... (20)"],
  "canonical_only": true,
  "mock_verifier": false
}
```

It exposes no note, witness or proof input. Mock mode returns a clear local-only error.

### `POST /local/withdrawals`

Dev-only bridge for a real Groth16 proof on local Anvil. Request:

```json
{
  "quote_id": "q_...",
  "proof": "0x... (256 bytes)",
  "root": "0x...",
  "nullifier": "0x...",
  "recipient": "0x...",
  "relayer_fee_wei": "240000000000000"
}
```

`proof` is `abi.encode(uint256[2] pA, uint256[2][2] pB, uint256[2] pC)` in snarkjs
`soliditycalldata` order. The recipient and fee must match the quote. The API checks the root
against the indexer, rejects an already-spent nullifier, sends
`withdraw(bytes,bytes32,bytes32,address,uint256,bytes32)` from the local Anvil unlocked account,
checks the receipt (including revert status), waits for the indexer, and stores only public
fields.

Success returns `withdrawal_id`, `pool_id`, `status:"confirmed"`, `tx_hash`, `block_number`,
`block_hash`, `nullifier`, `recipient`, `fee_wei`, `confirmations`, `finality`,
`local_chain:"ANVIL"`, `chain_source:"indexer"` and the configured `verifier_kind`.

Errors: `LOCAL_ONLY`, `QUOTE_NOT_FOUND`, `QUOTE_EXPIRED`, `QUOTE_CONSUMED`, `INVALID_PROOF`,
`INVALID_PUBLIC_SIGNALS`, `NULLIFIER_SPENT`, `ROOT_STALE`, `LOCAL_WITHDRAWAL_DISABLED`,
`WITHDRAWAL_REVERTED`, `INDEXER_CONFIRMATION_TIMEOUT`. A timeout leaves the quote reusable; a
revert does not consume the quote.

`VEILPOOL_LOCAL_VERIFIER_KIND=mock|groth16` controls the honest verifier label. `groth16` means
the development zkey path, not a production verifier.

---

## 12. Privacy rules

- No note in requests, responses, logs, traces, analytics or errors.
- Proofs and public signals are bounded and redacted in logs (hash only).
- `recipient_address` and `depositor_address` are confidential; access is audited.
- A nullifier lookup is privacy-sensitive; do not log it with a user identifier.
- No cross-user activity joins.
- Error messages must not echo full addresses or notes.
