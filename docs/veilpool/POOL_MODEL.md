# VeilPool Pool Model

**Status:** Current · **Version:** 1.0 · **Date:** 2026-11-02
**Related:** [Product Spec](PRODUCT_SPEC.md) · [Architecture](ARCHITECTURE.md) · [Threat Model](THREAT_MODEL.md)

---

## 1. Model in one page

A pool is defined by:

```text
(chain_id, asset, denomination, tree_depth, maturity, fee_bps, contract)
```

Each pool has:

- an independent Merkle tree of deposit commitments,
- an independent nullifier set,
- a fixed denomination,
- a maturity period,
- a protocol fee and relayer fee market,
- a liquidity balance.

Deposits and withdrawals are public on-chain events. The link between them is hidden by the
commitment/proof/nullifier construction, subject to the limits described below.

---

## 2. Denominations

| Pool | Asset | Denomination | Maturity | Tree depth | Protocol fee |
| --- | --- | --- | --- | --- | --- |
| ETH-0.1 | test ETH | 0.1 | 30 min | 20 | 0.24% |
| ETH-1 | test ETH | 1.0 | 2 h | 20 | 0.22% |
| ETH-10 | test ETH | 10 | 6 h | 20 | 0.20% |
| USDC-100 | test USDC | 100 | 30 min | 20 | 0.28% |
| USDC-1000 | test USDC | 1,000 | 2 h | 20 | 0.25% |
| tBTC-0.01 | test tBTC | 0.01 | 2 h | 20 | 0.30% |

Rules:

- Amounts are exact; no partial deposits.
- Splitting a note or merging notes is not supported in v1.
- A pool can be paused by the operator; paused pools reject deposit and withdrawal.
- A new denomination is a new pool with an empty anonymity set.
- Values are configuration, not hard-coded; changing a pool creates a new version.

---

## 3. Note

A note is a client-side secret. It is never stored by the API, relayer or compliance service.

```text
note = {
  version,
  chain_id,
  pool_id,
  denomination,
  secret,
  nullifier_secret,
  commitment,
  checksum
}
```

Derived values:

```text
commitment = H(secret, nullifier_secret, pool_id, denomination)
nullifier  = H(nullifier_secret, pool_id)      // or circuit-defined derivation
```

Rules:

- The note must include `chain_id` and `pool_id`; cross-pool and cross-chain use is rejected.
- The note must have a checksum; a corrupted note is rejected, not guessed.
- The note is displayed once and must be backed up before deposit.
- The note is encrypted at rest in the client vault (WebCrypto + IndexedDB).
- Notes are excluded from analytics, logs, crash reports and support tickets.
- A note can be exported as an encrypted file; the passphrase never leaves the client.

### Note states

| State | Meaning |
| --- | --- |
| `unbacked` | Created, not exported; deposit is blocked |
| `backed_up` | Encrypted backup exists |
| `unspent` | No withdrawal observed |
| `pending` | Withdrawal submitted, not confirmed |
| `spent` | Nullifier observed on-chain |
| `lost` | User cannot produce the note; unrecoverable |

### 3.1 Note format v1

```text
note-v1:<base64url(payload)>.<base64url(checksum)>
```

Payload:

```text
version       1 byte   = 0x01
chain_id      4 bytes  big-endian
pool_len      1 byte
pool_id       pool_len bytes UTF-8
denomination  32 bytes big-endian
secret        32 bytes CSPRNG
nullifier_secret 32 bytes CSPRNG
```

Checksum:

```text
sha256("veilpool-note-v1" || payload)[0:8]
```

Rules:

- The note is text-safe and copy/paste-safe.
- The checksum detects truncation and typos; it is not a MAC.
- The pool ID and chain ID are inside the checksum, so cross-pool/cross-chain edits fail.
- Unknown versions are rejected, never guessed.
- A future version requires a migration and backup compatibility test.
- Test vectors are fixtures in the test suite; see [TEST_PLAN.md](TEST_PLAN.md).

Encrypted backup envelope:

```json
{
  "version": 1,
  "kdf": "scrypt",
  "salt": "base64",
  "nonce": "base64",
  "ciphertext": "base64",
  "pool_id": "pool_eth_01",
  "created_at": "2026-11-02T10:00:00Z"
}
```

The passphrase never leaves the client. The server has no backup endpoint.

---

## 4. Deposit

### Preconditions

- Wallet connected to an approved testnet.
- Pool active and not paused.
- Amount equals the pool denomination.
- Depositor address passes compliance screening.
- Note backed up.
- Pool capacity not exceeded.

### Flow

1. Generate note locally.
2. Derive commitment.
3. Request compliance decision for `(address, pool, amount, action=deposit)`.
4. Submit `deposit(commitment)` to the pool contract.
5. Wait for transaction confirmation.
6. Indexer records the deposit event, leaf index and block.
7. UI shows `confirmed`; maturity countdown starts.
8. After maturity, the note becomes withdrawable.

### Invariants

- One deposit event creates exactly one leaf.
- Leaf index is unique and monotonic per tree.
- Deposit amount equals denomination.
- A reverted deposit creates no spendable note.
- A reorg removes or reorders deposit events consistently; see §8.

---

## 5. Withdrawal

### Preconditions

- Note is valid, backed up and unspent.
- Pool matches the note.
- Maturity elapsed.
- Merkle root used by the proof is current or within the allowed root window.
- Recipient passes compliance screening.
- Relayer is online and supports the pool.
- Fee quote not expired.

### Flow

1. Parse note locally.
2. Derive commitment and nullifier.
3. Fetch current Merkle root and membership path.
4. Generate proof locally (Web Worker/WASM).
5. Request compliance decision for `(recipient, pool, amount, action=withdraw)`.
6. Select relayer and obtain a signed fee quote.
7. Send proof, public signals, recipient and quote to the relayer.
8. Relayer validates proof shape, policy and fee; submits transaction.
9. Contract verifies proof, checks nullifier unused, transfers funds.
10. Indexer observes the withdrawal and marks the nullifier spent.
11. UI shows `confirmed`; note becomes `spent`.

### Invariants

- A nullifier is spent at most once per pool.
- A valid proof cannot be replayed on another pool or chain.
- A proof cannot be used after its root window expires.
- The recipient receives `denomination - protocol_fee - relayer_fee - gas`.
- A failed transaction does not mark the nullifier spent unless it is on-chain.
- Relayer cannot alter recipient or amount without invalidating the proof/public signals.

### 5.1 Public signals and domain separation

The withdrawal proof binds, at minimum:

```text
chain_id
pool_id
root
nullifier_hash
recipient
fee_wei
```

Rules:

- `chain_id` and `pool_id` are part of the proof domain; a proof for one pool/chain cannot be
  replayed on another.
- `recipient` and `fee_wei` are public signals; changing either invalidates the proof.
- `root` must be in the accepted root window.
- `nullifier_hash` is derived from the note and the pool domain.
- The circuit must enforce that the commitment is a member of the tree with that root.
- The verifier must reject proofs with unknown public signal counts or malformed encoding.
- The circuit/verifier requires an independent audit before any real-value use.

---

## 6. Anonymity set

### Definition

The anonymity set is the number of **unspent, matured deposits** in a pool at a given time.
It is not the total number of deposits ever made.

### Display rules

| Set size | Label | Guidance |
| --- | --- | --- |
| `< 25` | Very small | Do not recommend; strong warning |
| `25–99` | Small | Warn; suggest waiting |
| `100–499` | Moderate | Allowed |
| `500+` | Large | Recommended |

- Always show the set size next to the denomination.
- Do not show a single “privacy score” that hides the inputs.
- Show the maturity period and the last update time.
- Show liquidity separately; a large set with low liquidity is still risky.

### Limits of the model

- The set is only as strong as the deposit/withdrawal graph and timing.
- Exchange or wallet clustering can link deposit and withdrawal addresses.
- Fixed denominations reduce amount fingerprinting but do not eliminate it.
- Relayer metadata can leak timing if the relayer is malicious.
- The UI must not promise “untraceable”.

---

## 7. Fees

```text
withdrawal_amount = denomination
protocol_fee      = denomination × protocol_fee_bps / 10_000
relayer_fee       = denomination × relayer_fee_bps / 10_000
gas_cost          = actual gas used × effective gas price
recipient_amount  = denomination - protocol_fee - relayer_fee - gas_cost
```

Rules:

- Protocol fee is set per pool by the operator and capped by policy.
- Relayer fee is quoted and signed; the quote expires.
- Fee changes do not affect existing deposits.
- The UI shows all fees before proof generation.
- If fees exceed the denomination (misconfiguration), the pool is paused automatically.

---

## 8. Relayers

A relayer is a non-custodial submission service.

| Property | Requirement |
| --- | --- |
| Note access | None; never receives the note |
| Fund custody | None |
| Submission | Receives proof, public signals, recipient, fee quote |
| Policy | Must pass relayer compliance checks |
| Availability | Heartbeat and uptime tracked |
| Fee | Quoted, signed, bounded, expiring |
| Failure | Timeout → user can choose another relayer |

A relayer can:

- censor or delay a withdrawal,
- observe recipient and timing metadata,
- choose not to submit.

A relayer cannot:

- derive the note,
- redirect funds,
- change the recipient without invalidating the proof,
- withdraw the note itself.

---

## 9. Chain events and indexer

Required events:

```text
Deposit(poolId, commitment, leafIndex, timestamp)
Withdrawal(poolId, nullifier, recipient, fee, timestamp)
PoolPaused(poolId, reason)
PoolResumed(poolId)
RootUpdated(poolId, root, leafIndex)
```

Indexer rules:

- Events are ordered by `(block_number, log_index)`.
- Duplicate events are ignored by `(tx_hash, log_index)`.
- A reorg rolls back affected leaves and nullifiers, then replays the canonical chain.
- Rebuilding the tree from raw events must produce the same root.
- A stale indexer blocks withdrawals that depend on a root not yet observed.
- The API exposes `indexed_at`, `block_number`, `confirmations` and `finality`.

---

## 10. Boundaries and failure modes

| Boundary | Expected behavior |
| --- | --- |
| Amount != denomination | Reject before wallet prompt |
| Note for another pool/chain | Reject with explicit reason |
| Note already spent | Show “already withdrawn”; no proof |
| Maturity not reached | Block withdrawal; show countdown |
| Root stale | Wait or refresh; never prove against unknown root |
| Nullifier already on-chain | Mark note spent; no resubmission |
| Recipient sanctioned | Compliance block; no relayer submission |
| Relayer offline | Offer fallback; preserve proof locally |
| Relayer quote expired | Request a new quote |
| Transaction reverted | Keep note unspent; show revert reason |
| Reorg after confirmation | Mark pending; reconcile; re-evaluate nullifier |
| Pool paused | Block deposit and withdrawal; explain |
| Low liquidity | Warn; do not guarantee withdrawal |
| Note lost | Explicitly unrecoverable; no support recovery |

---

## 11. Invariants for property-based testing

1. `pool_balance == sum(deposits) - sum(withdrawals) - fees` at every block.
2. `nullifier` is unique per pool; no two withdrawals share it.
3. A deposit leaf is inserted once and never mutated in place.
4. A withdrawal proof is valid only for the pool and root window it targets.
5. A note’s commitment matches its secret and pool.
6. A reorg replay converges to the same root as a fresh index.
7. An expired quote cannot be submitted.
8. A blocked recipient cannot be replaced after proof generation.
9. A note is never persisted server-side.
10. A paused pool cannot process deposit or withdrawal.

---

## 12. Open model questions

- Should the root window be a fixed number of blocks or a time window?
- Should notes have an expiry? No by default; testnet only.
- Should there be a minimum set size enforced on-chain or only in the UI?
- How to handle a relayer that submits but never reports? Timeout + receipt lookup.
- Should protocol fees be claimable by an operator test account? Testnet only.
