# VeilPool ZK Circuit Specification (v0.1 spike)

**Status:** Draft / local spike · **Date:** 2026-11-03
**Scope:** testnet-only, no production security or anonymity claim
**Related:** [Pool Model](POOL_MODEL.md) · [Architecture](ARCHITECTURE.md) · [Test Plan](TEST_PLAN.md) · [MVP Status](MVP_STATUS.md) · [Testnet-Only Policy](../security/TESTNET_ONLY_POLICY.md)
**Implementation:** [`circuits/`](../../circuits/README.md)

---

> ## Read this first
>
> **The current `MockVerifier` is not cryptography.** It accepts any correctly
> encoded copy of the public signals. It does not verify membership, knowledge
> of a note, a Merkle path, or a nullifier derivation. A caller who can read a
> root and the public signals can construct a "proof" it accepts.
>
> **This circuit is not integrated.** The current `VeilPool.sol` tree hashes
> nodes with `keccak256`; this circuit uses Poseidon. The current contract
> cannot produce a root that this circuit proves against, and no deployed
> verifier accepts this proof. Replacing the tree and verifier is a breaking
> contract change; see §11.
>
> **No production claim.** The circuit is a local spike. It is not audited, the
> trusted setup is a single-machine development setup, and no claim is made
> about anonymity, browser proving performance, or mainnet safety. Testnet
> only.

---

## 1. Purpose

This document specifies the first candidate withdrawal proof for VeilPool: a
fixed-depth, fixed-denomination membership proof that binds the note, the pool,
the chain, the Merkle root, the nullifier, the recipient and the relayer fee.

It refines the public-signal list in [POOL_MODEL.md §5.1](POOL_MODEL.md) and the
contract boundary in [ARCHITECTURE.md §8](ARCHITECTURE.md). It is deliberately
narrow:

- It proves **membership of a commitment in a Poseidon Merkle tree** and
  **correct nullifier derivation**.
- It does **not** prove root freshness, maturity, fee caps, pool solvency,
  compliance, note backup, or that a deposit was funded.
- It does **not** provide anonymity by itself. Fixed denominations, timing,
  recipient reuse, relayer metadata and the public `Withdrawal` event remain
  observable.

The spike in [`circuits/`](../../circuits/README.md) compiles, witnesses,
proves and verifies one deterministic fixture. It is evidence that the
statement is expressible and testable, not evidence that it is secure.

---

## 2. Statement

Let `p` be the BN254 scalar field modulus:

```text
p = 21888242871839275222246405745257275088548364400416034343698204186575808495617
```

The circuit proves knowledge of:

```text
(secret_field, nullifier_secret_field, denomination, pathElements[20], pathIndices[20])
```

such that, for the public tuple
`(chain_id, pool_id, root, nullifier, recipient, fee)`:

```text
commitment = Poseidon(
  DOMAIN_COMMITMENT,
  chain_id,
  pool_id,
  denomination,
  secret_field,
  nullifier_secret_field
)

nullifier = Poseidon(
  DOMAIN_NULLIFIER,
  chain_id,
  pool_id,
  commitment,
  nullifier_secret_field
)

root = MerkleRoot(commitment, pathElements, pathIndices)
```

All public inputs are also witness inputs. The circuit constrains them to the
derived values; the prover cannot choose a different public value without
invalidating the witness.

### 2.1 What the verifier learns

The proof reveals the six public signals and nothing else about the witness,
subject to the security of Groth16, Poseidon and the trusted setup. With the
development setup in §10, that zero-knowledge claim is not trustworthy because
the setup is insecure. The proof does not hide:

- the recipient address,
- the relayer fee,
- the pool and chain,
- the withdrawal transaction timing,
- the nullifier value (which is public and stored on-chain).

The nullifier is not a deposit identifier, but it is a stable per-note value.
Anyone who knows a note can compute its nullifier; the chain learns it at
withdrawal.

### 2.2 What the proof does not establish

| Property | Enforced by |
| --- | --- |
| Root is current or inside the accepted window | `VeilPool` root history and `rootTimestamp` |
| Root is old enough (maturity) | `VeilPool.withdraw` |
| Nullifier has not been spent | `VeilPool._nullifierSpent[poolId][nullifier]` |
| Fee is within the pool cap | `VeilPool.withdraw` / `quoteWithdrawal` |
| Recipient is non-zero | `VeilPool.withdraw` |
| Pool is not paused | `VeilPool.withdraw` |
| Deposit was funded at the pool denomination | `VeilPool.deposit` (`msg.value`) |
| Commitment is a canonical Poseidon field element | Not enforced today; see §11.4 |
| Denomination in the note equals the pool's denomination | Not enforced by the circuit; see §6.2 |
| Recipient passed compliance screening | API / compliance service, off-chain |
| Note was backed up | Client vault |

---

## 3. Cryptographic parameters

| Parameter | Value |
| --- | --- |
| Curve | BN254 (alt_bn128), as used by circom/snarkjs |
| Scalar field | `p` above |
| Hash | Poseidon over BN254, circomlib 2.0.5 |
| Proof system | Groth16 |
| Tree depth | 20 |
| Maximum leaves | `2^20 = 1,048,576` |
| Public inputs | 6 |
| Public outputs | 0 |
| Non-linear constraints | 6,623 (measured) |
| Total constraints | 14,569 (measured) |

The Poseidon parameters are the circomlib 2.0.5 parameters. No independent
cryptanalysis or parameter review was performed for this spike. Poseidon is
used because a depth-20 Poseidon Merkle path is small enough to be practical
for a browser prover; a keccak256 path would be orders of magnitude larger.
That choice is a product/engineering trade-off, not a security proof.

Groth16 is circuit-specific and requires a trusted setup. See §10. The setup
used for the recorded run is **not** a secure ceremony.

---

## 4. Note, commitment, nullifier and Merkle path

### 4.1 Note fields used by the circuit

The note format is defined in [POOL_MODEL.md §3.1](POOL_MODEL.md). Note v1
stores `chain_id` in 4 bytes, while the circuit allows a `uint64` chain ID. A
chain ID above `2^32 - 1` therefore requires a new note version even though the
circuit range is wider. Testnets in scope fit in 4 bytes.

This circuit uses:

| Note field | Circuit role |
| --- | --- |
| `chain_id` | Public signal; also hashed into commitment and nullifier |
| `pool_id` | Public signal in canonical field form; hashed into both |
| `denomination` | Private witness; hashed into commitment |
| `secret` | Private witness, reduced to a field element |
| `nullifier_secret` | Private witness, reduced to a field element |

`version` and `checksum` are note-format fields, not circuit inputs. The checksum
is a typo/truncation check, not a MAC and not a proof.

### 4.2 Secret reduction

The note stores 32 CSPRNG bytes for each secret. A uniform 256-bit value is not
necessarily a canonical BN254 scalar, so the circuit uses:

```text
secret_field           = uint256_be(secret_bytes)           mod p
nullifier_secret_field = uint256_be(nullifier_secret_bytes) mod p
```

The raw 32 bytes remain the note secret. The client must keep the raw bytes for
backup and derive the field values deterministically. The reduction bias is
negligible for this use, but it is a defined encoding step, not a hash.

Client rules (not enforced by the circuit):

- generate both secrets from a CSPRNG;
- reject an all-zero secret or all-zero nullifier secret;
- never reuse a `(chain_id, pool_id, denomination, secret, nullifier_secret)`
  tuple for a second note;
- never send the raw secret, reduced field value, witness or note to a server.

Reusing all note inputs creates the same commitment. Depositing it twice creates
two leaves but one nullifier, so only one of the two deposits can ever be spent.
That is a self-inflicted lock, not a pool drain, but the client must prevent it.

### 4.3 Pool ID encoding

The note format carries `pool_id` as UTF-8 text. The circuit needs a field
element. The canonical encoding is:

```text
pool_id_bytes32 = 0x00 || UTF-8(pool_id_text) || 0x00 ... (right padding to 32 bytes)
pool_id_field   = uint256_be(pool_id_bytes32)
```

Rules:

- `pool_id_text` must be 1–31 UTF-8 bytes. Longer IDs are rejected.
- `pool_id_text` must not contain a NUL byte (`U+0000`); padding must be
  unambiguous.
- The first byte MUST be `0x00`. Therefore `pool_id_field < 2^248 < p`.
- The remaining 31 bytes hold the UTF-8 ID, right-padded with zero bytes.
- This is a **new canonical pool ID encoding**. The current contracts accept
  arbitrary `bytes32` pool IDs and the API uses strings up to 64 characters;
  neither enforces this rule today. See §11.3.

Example: `"pool_eth_01"` (11 bytes) becomes:

```text
0x00706f6f6c5f6574685f30310000000000000000000000000000000000000000
```

### 4.4 Commitment

```text
commitment = Poseidon(
  DOMAIN_COMMITMENT,   // 0x7665696c706f6f6c2d636f6d6d69742d7631 ("veilpool-commit-v1")
  chain_id,
  pool_id,
  denomination,
  secret_field,
  nullifier_secret_field
)
```

`Poseidon(6)` has six inputs in the order shown. The output is a field element.
The circuit rejects a zero commitment, mirroring `VeilPool.deposit`.

This refines the shorthand in [POOL_MODEL.md §3](POOL_MODEL.md)
(`H(secret, nullifier_secret, pool_id, denomination)`) by adding domain tags and
`chain_id`. A note created for this circuit must use the formula above; the
shorthand is not a second compatible encoding.

Including `chain_id` and `pool_id` in the commitment means a note for one chain
or pool does not produce the same commitment on another. This is defense in
depth in addition to the public-signal checks.

`denomination` is private. The circuit does **not** prove it equals the pool's
configured denomination. The pool pays its fixed denomination regardless, so a
mismatched note cannot mint extra funds, but a client that accepts a mismatched
note may show the wrong amount. Clients must validate the note's denomination
against the pool before proving. This is a UX/integrity issue, not an inflation
bug.

### 4.5 Nullifier

```text
nullifier = Poseidon(
  DOMAIN_NULLIFIER,    // 0x7665696c706f6f6c2d6e756c6c2d7631 ("veilpool-null-v1")
  chain_id,
  pool_id,
  commitment,
  nullifier_secret_field
)
```

`Poseidon(5)` has five inputs in the order shown. Binding the commitment makes
the nullifier unique per note, not merely per `nullifier_secret`. Binding
`chain_id` and `pool_id` prevents cross-chain and cross-pool reuse. The contract
stores the nullifier in a per-pool set.

The nullifier is deterministic. A second withdrawal attempt with the same note
produces the same nullifier and is rejected by the contract after the first
spend. There is no per-withdrawal nonce.

### 4.6 Merkle tree

The tree is a fixed-depth binary tree with `2^20` leaf slots:

```text
leaf[leafIndex] = commitment
```

Only commitments are leaves. There is no extra leaf wrapper hash.

Empty subtree roots:

```text
zero[0] = 0
zero[i+1] = Poseidon(DOMAIN_NODE, zero[i], zero[i])   for i = 0..19
```

Internal node:

```text
node = Poseidon(
  DOMAIN_NODE,   // 0x7665696c706f6f6c2d6d65726b6c652d7631 ("veilpool-merkle-v1")
  left,
  right
)
```

`Poseidon(3)` has three inputs in the order shown. This is **not**
`Poseidon(left, right)`; the domain tag is part of the hash. Any contract,
indexer or client implementation must use the same tag and input order.

Path encoding:

- `pathElements[i]` is the sibling at level `i`.
- `pathIndices[i]` is a bit: `0` means the current node is the left child,
  `1` means it is the right child.
- `pathIndices[0]` is the least significant bit of `leafIndex`.
- A depth-20 path has 20 elements and 20 bits.

The circuit recomputes:

```text
current = commitment
for i in 0..19:
  left  = pathIndices[i] == 0 ? current : pathElements[i]
  right = pathIndices[i] == 0 ? pathElements[i] : current
  current = Poseidon(DOMAIN_NODE, left, right)
require current == root
```

The circuit does not know `leafIndex` as a separate witness; the bits are the
index. It also does not enforce that the leaf is at a particular index or that
the tree is the contract's canonical tree. Root membership is only as meaningful
as the tree that produced the root.

---

## 5. Circuit interface and witness layout

### 5.1 Public signals

Public signals are declared in this exact order in Circom:

| Index | Name | Type / range | Source | Notes |
| --- | --- | --- | --- | --- |
| 0 | `chain_id` | `uint64` | `block.chainid` in the verifier wrapper | Not in `IVerifier` ABI |
| 1 | `pool_id` | `uint248` canonical | `bytes32 poolId` argument | Top byte must be zero |
| 2 | `root` | BN254 field element | `bytes32 root` argument | Poseidon root, not keccak |
| 3 | `nullifier` | BN254 field element | `bytes32 nullifier` argument | Public input constrained to the hash output |
| 4 | `recipient` | `uint160` address | `address recipient` argument | Bound to payout address |
| 5 | `fee` | `uint64` wei | `uint256 relayerFee` argument | Bound to relayer fee |

The order is part of the verifier interface. A verifier built for this circuit
must use exactly this order:

```text
[chain_id, pool_id, root, nullifier, recipient, fee]
```

The generated verifier has `nPublic = 6` and `nOutputs = 0`. `snarkjs` writes
public signals to `public.json` in this order; the fixture records the same
order.

Why these ranges:

- `chain_id`: current testnets and Ethereum chains fit in 64 bits; the wrapper
  rejects larger values.
- `pool_id`: the canonical encoding above guarantees `< 2^248 < p`, so the
  bytes32-to-field mapping loses no bits.
- `root`, `nullifier`: Poseidon outputs are already `< p`. The wrapper still
  rejects non-canonical `bytes32` inputs.
- `recipient`: a Solidity `address` is 160 bits.
- `fee`: all current pool denominations are below `2^64` wei; the wrapper
  rejects larger fees. The contract's fee cap is much tighter.

### 5.2 Private witness

| Name | Count | Encoding |
| --- | --- | --- |
| `secret` | 1 | BN254 field element, reduced from note bytes |
| `nullifier_secret` | 1 | BN254 field element, reduced from note bytes |
| `denomination` | 1 | integer `< 2^64`, non-zero |
| `pathElements` | 20 | field elements |
| `pathIndices` | 20 | integers `0` or `1` |
| **Total private inputs** | **43** | |

The six public inputs are also present in the witness input JSON. Circom treats
them as inputs and the circuit constrains the derived values to equal them.

### 5.3 Circom declaration

```circom
template Membership(depth) {
    signal input chain_id;
    signal input pool_id;
    signal input root;
    signal input nullifier;
    signal input recipient;
    signal input fee;

    signal input secret;
    signal input nullifier_secret;
    signal input denomination;
    signal input pathElements[depth];
    signal input pathIndices[depth];
    // ...
}

component main {public [chain_id, pool_id, root, nullifier, recipient, fee]} =
    Membership(20);
```

The full source is [`circuits/circuits/membership.circom`](../../circuits/circuits/membership.circom).

### 5.4 Witness JSON

`input.json` uses decimal strings for every field element. Example shape:

```json
{
  "chain_id": "11155111",
  "pool_id": "198655969066724116100767858592150160576042375226781091767425152450098626560",
  "root": "15049780002719594699334822932270417263986540263615501146279714551974396635579",
  "nullifier": "12588264354977242030084359464951865421683901410919186763886194437570411015691",
  "recipient": "57005",
  "fee": "100000000000000",
  "secret": "6087853478126770807687652477465951213136924855729282061000007915049570429958",
  "nullifier_secret": "19954140100765766771997219441647387020585061857825962256107660866243846604369",
  "denomination": "100000000000000000",
  "pathElements": ["..."],
  "pathIndices": ["1", "0", "1", "0", "..."]
}
```

The witness file (`build/witness.wtns`) contains all private values. It is
secret material and must never be sent to the API, relayer, logs, analytics or
issue trackers.

---

## 6. Constraints

### 6.1 Enforced constraints

| ID | Constraint | Purpose |
| --- | --- | --- |
| C1 | `chain_id < 2^64` | Canonical encoding; wrapper range |
| C2 | `pool_id < 2^248` | Canonical bytes32→field mapping |
| C3 | `recipient < 2^160` | Address range |
| C4 | `fee < 2^64` | Canonical fee range |
| C5 | `denomination < 2^64` and `denomination != 0` | Field/ABI range; non-zero note |
| C6 | `commitment = Poseidon(DOMAIN_COMMITMENT, chain_id, pool_id, denomination, secret, nullifier_secret)` | Binds note to chain/pool |
| C7 | `commitment != 0` | Mirrors deposit rejection |
| C8 | `nullifier = Poseidon(DOMAIN_NULLIFIER, chain_id, pool_id, commitment, nullifier_secret)` | Deterministic, domain-separated nullifier |
| C9 | Each `pathIndices[i]` is 0 or 1 | Prevents arbitrary path arithmetic |
| C10 | Recomputed Merkle root equals public `root` | Membership |

The circuit has no public outputs; equality is enforced with `===` constraints.
The compiled artifact is 6,623 non-linear constraints and 14,569 total
constraints at depth 20 (measured with circom 2.2.3 / snarkjs 0.7.6).

### 6.2 Deliberately not enforced

| Non-constraint | Why | Where handled |
| --- | --- | --- |
| `denomination == pool.denomination` | Pool ID is the registry key; circuit is pool-agnostic | Client validation; contract pays fixed denomination |
| `fee <= denomination` / fee cap | Business policy; can change without a new circuit | `VeilPool.withdraw` |
| `recipient != 0` | Contract already rejects zero | `VeilPool.withdraw` |
| `root` is known/fresh | Requires chain state | `VeilPool._knownRoot`, maturity |
| Nullifier unused | Requires chain state | `VeilPool` nullifier set |
| Commitment was deposited | Requires tree state | Contract tree + root membership |
| Leaf index range | Path bits are the index; no separate index witness | Tree construction |
| Note version/checksum | Format concern, not proof statement | Client note parser |
| Relayer identity | Not in the public signal list | Off-chain quote; residual front-running risk |

The circuit is intentionally pool-agnostic. A proof is valid for the pool ID
hashed into the note and supplied as a public signal, provided the commitment is
in that pool's tree. The contract is responsible for ensuring the tree, root
window and pool configuration are the ones users expect.

---

## 7. Domain separation

### 7.1 Domain tags

| Tag | ASCII | Hex (32-byte padded in JSON) | Used in |
| --- | --- | --- | --- |
| `DOMAIN_COMMITMENT` | `veilpool-commit-v1` | `0x7665696c706f6f6c2d636f6d6d69742d7631` | Commitment Poseidon(6) |
| `DOMAIN_NULLIFIER` | `veilpool-null-v1` | `0x7665696c706f6f6c2d6e756c6c2d7631` | Nullifier Poseidon(5) |
| `DOMAIN_NODE` | `veilpool-merkle-v1` | `0x7665696c706f6f6c2d6d65726b6c652d7631` | Merkle node Poseidon(3) |

Tags are constants, not secrets. They are ASCII strings interpreted as
big-endian integers.

### 7.2 Why the domains are separate

- A commitment hash cannot be reinterpreted as a Merkle node or a nullifier.
- A nullifier hash cannot be reinterpreted as a commitment.
- The Merkle node hash is domain-separated from leaf commitments, so an
  internal node value is not a valid leaf preimage by construction.
- `chain_id` and `pool_id` are inside both the commitment and the nullifier.
  A proof for one chain/pool does not produce the same commitment or nullifier
  on another.
- The note checksum domain (`sha256("veilpool-note-v1" || payload)[0:8]`) is a
  separate string-integrity mechanism. It is not a proof and not a MAC.

### 7.3 Versioning

Changing any of the following is a **new circuit version** and requires a new
trusted setup, new verifier address, new test vectors and a new pool version:

- a domain tag,
- the Poseidon input order or arity,
- the tree depth,
- the commitment or nullifier formula,
- the public signal order,
- the proof encoding.

Do not reuse an old verifier key for a modified circuit.

---

## 8. Root window, maturity, replay and double-spend

### 8.1 Layer responsibilities

| Property | Circuit | Verifier wrapper | `VeilPool` |
| --- | --- | --- | --- |
| Commitment membership | Yes | Passes `root` | Provides root history |
| Nullifier derivation | Yes | Passes `nullifier` | Stores spent set |
| Chain binding | Hashes `chain_id` | Injects `block.chainid` | — |
| Pool binding | Hashes `pool_id` | Passes canonical `poolId` | Keys pools and nullifiers |
| Recipient binding | Public input | Passes `recipient` | Pays `recipient` |
| Fee binding | Public input | Passes `relayerFee` | Caps and pays fee |
| Root freshness | No | No | `_knownRoot` + root window |
| Maturity | No | No | `rootTimestamp + maturity` |
| Replay/double-spend | Nullifier determinism | No | Per-pool nullifier set |
| Pause | No | No | `paused` |
| Fee cap | No | Range only | `MAX_FEE_BPS` |

### 8.2 Replay matrix

| Change | Result |
| --- | --- |
| Same proof, same pool, same chain, second submission | Verifier may return true; contract reverts `NullifierAlreadySpent` |
| Same proof on another chain | Wrapper injects a different `chain_id`; proof verification fails |
| Same proof on another pool | Public `pool_id` differs; proof verification fails; tree/root likely unknown |
| Same proof with different `root` | Proof verification fails; proof is bound to the original root |
| Same proof with different `recipient` | Proof verification fails |
| Same proof with different `fee` | Proof verification fails |
| Same proof after root eviction | Contract rejects `UnknownRoot` even if the proof is cryptographically valid |
| Same proof before maturity | Contract rejects `MaturityNotReached` |
| Same proof with fee above cap | Contract rejects `FeeTooHigh` |
| Truncated/oversized proof | Wrapper rejects length before pairing |
| Non-canonical `pool_id` (top byte non-zero) | Wrapper rejects |
| `root` or `nullifier` ≥ `p` | Wrapper rejects |
| `fee` or `chain_id` ≥ `2^64` | Wrapper rejects |
| Two relayers race the same note | One transaction wins; the other reverts; nullifier spent once |

### 8.3 Nullifier race and reorg

The circuit makes the nullifier deterministic, but it cannot make the spend
atomic. The contract's per-pool nullifier set is the authority:

- two concurrent submissions: one sets the nullifier, the other reverts;
- a reverted transaction does not consume the note;
- an on-chain reorg can remove the spend and make the note spendable again on
  the canonical chain; the indexer must reconcile (see `WDR-17`, `WDR-19`);
- the client must not display `spent` until the withdrawal is confirmed under
  the configured finality policy.

Maturity is based on the root's on-chain acceptance time, not the proof
generation time. A proof generated before maturity is still valid; the contract
rejects it until the root is old enough.

### 8.4 Chain ID is not a fork identifier

`chain_id` is necessary but not sufficient to distinguish two chains that share
a chain ID (for example, a testnet fork or a misconfigured RPC). A future
version should bind a genesis hash or an explicit chain-instance domain. For
this testnet spike, the API/indexer's chain-ID check and testnet-only policy
remain the operational control.

### 8.5 Relayer front-running

`recipient` and `fee` are bound, but the proof does not bind the relayer's
address. Anyone who obtains a valid proof can submit it and receive the
`relayerFee`, while the recipient still receives the payout. This is a
fee-capture/censorship risk, not a theft-of-principal risk. Mitigations are
off-chain (private submission, quote binding, trusted relayer path); binding a
relayer address would require an additional public signal and a circuit change.

---

## 9. Verifier ABI and proof encoding

### 9.1 Existing interface

The existing interface is unchanged:

```solidity
interface IVerifier {
    function verifyProof(
        bytes calldata proof,
        bytes32 root,
        bytes32 nullifier,
        address recipient,
        uint256 relayerFee,
        bytes32 poolId
    ) external view returns (bool);
}
```

`chain_id` is not a parameter. The real verifier wrapper reads
`block.chainid` itself. This avoids an ABI change and prevents a caller from
supplying a different chain ID.

### 9.2 Wrapper behavior

The wrapper is the bridge between the six-signal circuit and the five-argument
interface. Its checks are normative:

```solidity
uint256 constant P = 21888242871839275222246405745257275088548364400416034343698204186575808495617;

function verifyProof(
    bytes calldata proof,
    bytes32 root,
    bytes32 nullifier,
    address recipient,
    uint256 relayerFee,
    bytes32 poolId
) external view returns (bool) {
    if (proof.length != 256) return false;
    if (block.chainid > type(uint64).max) return false;
    if (uint256(poolId) >> 248 != 0) return false;
    if (uint256(root) >= P) return false;
    if (uint256(nullifier) >= P) return false;
    if (relayerFee > type(uint64).max) return false;

    uint256[6] memory input = [
        block.chainid,
        uint256(poolId),
        uint256(root),
        uint256(nullifier),
        uint256(uint160(recipient)),
        relayerFee
    ];

    (uint256[2] memory a, uint256[2][2] memory b, uint256[2] memory c) =
        abi.decode(proof, (uint256[2], uint256[2][2], uint256[2]));

    return groth16Verifier.verifyProof(a, b, c, input);
}
```

This snippet is illustrative; no wrapper contract was compiled or deployed in
this spike. Notes:

- `recipient` is an `address`, so it is already `< 2^160`; the cast is
  lossless.
- The `poolId` check rejects any ID whose top byte is non-zero. Because
  `< 2^248 < p`, the remaining value is canonical without a modular reduction.
- `root` and `nullifier` are `bytes32`; a value `>= p` could otherwise be
  reduced by the verifier or rejected inconsistently. Reject it explicitly.
- `relayerFee > uint64.max` is rejected. The current pool denominations are
  below `2^64` wei; the contract cap is much lower.
- `abi.decode` on exactly 256 bytes into fixed-size arrays cannot encounter a
  dynamic-length ambiguity. Length is checked first.
- Return `false` for malformed input. Reverting also blocks the withdrawal, but
  `VeilPool` maps only `false` to `InvalidProof`; a revert produces a different
  error and worse diagnostics.
- The wrapper must be `view` and must not write state.

### 9.3 Proof encoding

The proof is exactly **256 bytes**: eight 32-byte big-endian words.

| Offset | Size | Word | Source |
| --- | --- | --- | --- |
| 0 | 32 | `a.x` | `proof.pi_a[0]` |
| 32 | 32 | `a.y` | `proof.pi_a[1]` |
| 64 | 32 | `b[0][0]` | `snarkjs soliditycalldata` order |
| 96 | 32 | `b[0][1]` | `snarkjs soliditycalldata` order |
| 128 | 32 | `b[1][0]` | `snarkjs soliditycalldata` order |
| 160 | 32 | `b[1][1]` | `snarkjs soliditycalldata` order |
| 192 | 32 | `c.x` | `proof.pi_c[0]` |
| 224 | 32 | `c.y` | `proof.pi_c[1]` |

Equivalently:

```text
proof = abi.encode(
  [a.x, a.y],
  [[b00, b01], [b10, b11]],
  [c.x, c.y]
)
```

Use the output of:

```text
snarkjs zkey export soliditycalldata public.json proof.json
```

Do **not** hand-copy `proof.json` points into the on-chain arrays. The
generated Solidity verifier's `pi_b` order is not the same as `proof.json`'s
nested pair order; `soliditycalldata` applies the required swap. In the
recorded fixture, the mapping is:

```text
b00 = proof.pi_b[0][1]    b01 = proof.pi_b[0][0]
b10 = proof.pi_b[1][1]    b11 = proof.pi_b[1][0]
```

`proof.json` includes a third projective coordinate `1` for `pi_a`, `pi_b`
pairs and `pi_c`. The on-chain encoding is affine: drop those `1` values. A
160-byte `MockVerifier` proof is not a valid Groth16 proof and must be rejected
by the length check.

Groth16 proofs are not guaranteed to be unique for the same statement. Do not
use the proof bytes as an idempotency key or a unique withdrawal identifier;
use the nullifier and the transaction hash.

### 9.4 Generated verifier ABI

`snarkjs zkey export solidityverifier` produces:

```solidity
function verifyProof(
    uint[2] calldata _pA,
    uint[2][2] calldata _pB,
    uint[2] calldata _pC,
    uint[6] calldata _pubSignals
) public view returns (bool)
```

The wrapper decodes the 256-byte proof into the three arrays and builds the
six-element public signal array in the order from §5.1.

### 9.5 Key and circuit identification

The generated verifier embeds the verification key constants. For a real
deployment, additionally record and publish:

- SHA-256 of `membership.circom`,
- SHA-256 of `membership.r1cs`,
- SHA-256 of `verification_key.json`,
- circuit version / domain tags,
- ptau transcript hash and phase-2 contribution hashes.

The verifier address is immutable in the current `VeilPool` design. Changing
the circuit requires a new verifier and a new pool deployment. Do not use a
proxy that can silently swap the verifier key.

### 9.6 Gas

Groth16 verification uses the BN254 pairing precompiles and is usually cheaper
than proving, but no gas measurement on the target testnet was performed for
this spike. Measure `verifyProof` on Anvil and the target testnet before setting
a gas budget. Do not quote a number from another circuit.

---

## 10. Trusted setup and ceremony assumptions

### 10.1 What the spike used

The recorded run used:

1. a local `bn128` Powers of Tau file at 2^14 (16,384 powers; the circuit has
   14,569 constraints),
2. one local phase-1 contribution,
3. `groth16 setup` for this circuit,
4. one local phase-2 contribution,
5. `zkey export verificationkey`.

This is a **development setup**, not a ceremony. It has a single local
contributor and a single local entropy source, no public transcript, and no
auditable destruction of toxic waste. Anyone who can reproduce or recover the
toxic waste can forge proofs for this circuit. Do not use these artifacts with
real funds.

### 10.2 Production assumptions

For any non-testnet use, all of the following are required before the verifier
is trusted:

- freeze the circuit source and domain tags before the ceremony;
- run a multi-party phase-1 (Powers of Tau) ceremony with independent
  contributors and a published transcript;
- verify every contribution and the final ptau;
- run a circuit-specific phase-2 ceremony with multiple independent
  contributors;
- publish all contribution hashes, the final zkey hash and the verification
  key hash;
- have an independent party reproduce the build from source and compare the
  circuit hash / r1cs hash / vk hash;
- audit the circuit, verifier wrapper and setup process;
- define an incident plan for a setup compromise (pause, new pool version, new
  ceremony).

A Groth16 setup is circuit-specific. Any circuit change, including a domain tag
or tree-depth change, invalidates the setup and requires a new phase-2
ceremony. A universal-setup proof system (for example PLONK) would remove the
per-circuit phase 2 but still requires a trusted phase 1; it was not evaluated
in this spike.

### 10.3 Verification key integrity

The generated verifier's constants are the verification key. Publish their
hash and compare it to the audited artifact. If a deployment script can replace
the verifier, the setup's security is irrelevant. The current `VeilPool`
constructor takes an immutable verifier address; keep that property.

---

## 11. Contract integration gap

This section is the most important limitation of the spike. **No contract, API
or web integration was performed.**

### 11.1 Hash mismatch: keccak vs Poseidon

`contracts/src/VeilPool.sol` currently builds the tree with:

```solidity
_nodes[poolId][nodeIndex] = keccak256(abi.encodePacked(left, right));
```

and zero hashes with the same keccak rule. The circuit uses:

```text
Poseidon(DOMAIN_NODE, left, right)
```

These roots are not interchangeable. A proof generated against a Poseidon root
cannot verify against a keccak root, and a keccak root is generally not even a
canonical BN254 field element.

Options:

| Option | Assessment |
| --- | --- |
| A. Replace the on-chain tree with Poseidon | Recommended for a browser prover. Requires a verified Solidity Poseidon implementation (or an audited equivalent), new zero hashes, new root history, updated tests and indexer. Gas cost must be measured. This is a breaking contract change. |
| B. Build a keccak path circuit | Not recommended for v1. A keccak permutation is much larger than a Poseidon permutation; a depth-20 path would be impractical for the stated browser target and would require a larger ptau and setup. |
| C. Attest a Poseidon root off-chain | Adds a trusted committee/oracle assumption and a new root-authentication mechanism. Not recommended without a separate design and audit. |

Option A also requires the indexer and any root-rebuild test to use the exact
same `DOMAIN_NODE`, input order, zero-subtree rule and leaf indexing as the
circuit. A root rebuilt from events must equal the root the client used.

### 11.2 `chain_id` injection

`IVerifier` has no `chain_id` parameter. The wrapper reads `block.chainid` and
places it at public-signal index 0. This is intentional and avoids trusting the
caller. It must be tested on every deployed chain. If `block.chainid` exceeds
`2^64`, the wrapper rejects all proofs.

### 11.3 Pool ID canonicality

The current contract accepts any non-zero `bytes32` pool ID. The wrapper
requires `uint256(poolId) < 2^248` (top byte zero). Existing IDs that are
keccak-derived or longer than 31 UTF-8 bytes are not guaranteed to satisfy this
rule and cannot be assumed compatible.

Required integration changes:

- define the canonical `pool_id_text -> bytes32` encoding in the pool registry;
- reject IDs longer than 31 UTF-8 bytes at pool creation;
- migrate or re-create pools with new IDs (testnet only);
- update the API's pool ID limits (currently up to 64 characters in places);
- update note parsing to reject non-canonical pool IDs.

This is a breaking change and should be a new pool version.

### 11.4 Commitment and root canonicality

`VeilPool.deposit` rejects zero commitments but accepts any other `bytes32`.
A value `>= p` cannot be a Poseidon output and can never be a valid leaf in the
Poseidon tree. Depositing one burns the note: no valid proof can ever spend it.

Minimum mitigation without a deposit proof:

```solidity
if (uint256(commitment) >= P) revert InvalidCommitment();
```

This does not prove the commitment is well-formed, but it prevents the obvious
unspendable case. A deposit-side proof or a client-side derivation check would
be stronger; both are out of scope for this spike.

Roots have the same issue: a keccak root may be `>= p`, and the wrapper rejects
it. This is another symptom of §11.1.

### 11.5 Fee, chain and denomination bounds

`createPool` currently allows a denomination up to `type(uint256).max / 10000`.
The circuit range-checks `denomination` and `fee` to `< 2^64`. The wrapper
rejects `relayerFee > uint64.max` and `block.chainid > uint64.max`.

Required integration changes:

- enforce `denomination < 2^64` at pool creation;
- enforce `fee < 2^64` in the relayer/API quote schema (the contract cap is
  tighter for current pools);
- document that a future asset with 18 decimals and a large denomination may
  not fit the `uint64` fee/denomination range;
- add tests for the boundary values.

### 11.6 `MockVerifier` replacement

`MockVerifier` must not appear in any real withdrawal path. It accepts a
160-byte encoding of the public signals and performs no cryptography. The real
verifier wrapper must:

- reject 160-byte proof caches,
- require exactly 256 bytes,
- use the six-signal order above,
- return `false` for malformed input,
- be covered by the negative tests in §12.

The current Foundry tests use `MockVerifier`; they can remain as MVP tests but
must be clearly labelled and must not be used as evidence that real proofs work.

---

## 12. Test vectors and negative cases

### 12.1 Positive fixture

Files:

- [`circuits/test-vectors/membership-v1.json`](../../circuits/test-vectors/membership-v1.json) — readable fixture
- `circuits/test-vectors/membership-v1.canonical.json` — canonical form
- `circuits/test-vectors/membership-v1.canonical.sha256` — SHA-256 of the canonical bytes
- `circuits/test-vectors/negative-cases.json` — negative-case manifest

Canonical SHA-256:

```text
599f75c3cf34663e1980c25194ea10acac3ff910b7dd75902cdfab9e9cc3ac5b
```

Additional working-tree hashes from the recorded run (recompute after any
source change; line-ending conversion changes the source hash):

```text
membership.circom       52f2c6f6f7201fd83ac42c54fd213442258705cee747a2d50eb767a7329b3ded
membership-v1.json      76a097ebddc5b891a2a05f093610c82941f910d540750c617ff68123316c8bca
```

Fixture values:

| Field | Value |
| --- | --- |
| `chain_id` | `11155111` (Sepolia) |
| `pool_id_text` | `pool_eth_01` |
| `pool_id` | `0x00706f6f6c5f6574685f30310000000000000000000000000000000000000000` |
| `denomination` | `100000000000000000` wei (0.1 ETH) |
| `secret_bytes` | `0xff6b229a0dc80b46c46d80bbe3b933739f67a0dceeee94355817846394266c0b` |
| `secret_field` | `0x0d759a5ba7cfea762adc242b5c3279a1d66417728e4f615f04adb87fe4266c06` |
| `nullifier_secret_bytes` | `0x5c81f312d065befdfcf2ef5f287d97dba9fdab77a20d9e279586c0435d520652` |
| `nullifier_secret_field` | `0x2c1da49fef341ed444a2a9a8a6fc3f7e81c9c32f28542d9651a4caaf6d520651` |
| `commitment` | `0x2a829d48f48ff29616eb89685dc388a139f999cf858bd12e18a68f03e713ad02` |
| `nullifier` | `0x1bd4b483b8383cc27ccbbca529064dd29c4207a7e28832b3c0781d4cd84eae0b` |
| `root` | `0x2145dfa5869ae142af6de0e91ea20be3100f93e76a6f2d279e520b1db1b329bb` |
| `leaf_index` | `5` (path bits `10100000000000000000`) |
| `recipient` | `0x000000000000000000000000000000000000dead` |
| `fee` | `100000000000000` wei (0.0001 ETH) |
| `depth` | `20` |

Public signal order and values:

```json
[
  "11155111",
  "198655969066724116100767858592150160576042375226781091767425152450098626560",
  "15049780002719594699334822932270417263986540263615501146279714551974396635579",
  "12588264354977242030084359464951865421683901410919186763886194437570411015691",
  "57005",
  "100000000000000"
]
```

The decimal forms in the JSON array correspond to the same values as the hex
table. The fixture deliberately uses a raw `secret_bytes` above `p` so that the
reduction rule is exercised.

This fixture is **not a note for real funds**. Every secret is public in the
repository.

### 12.2 Regenerating

```powershell
cd circuits
node scripts/gen-fixture.mjs
node scripts/canonicalize.mjs
```

Changing the circuit, domain tags, tree depth or hash order requires a new
fixture, new setup and new verifier key. Do not edit the fixture by hand.

### 12.3 Negative cases

Witness-level cases (implemented in
`circuits/scripts/witness-negative.mjs`, all 11 pass):

| Case | Expected |
| --- | --- |
| Valid baseline | Witness accepted |
| Wrong `secret` | Witness rejected (root mismatch) |
| Wrong `root` | Witness rejected |
| Wrong `nullifier` | Witness rejected |
| `pathIndices[0] = 2` | Witness rejected (boolean constraint) |
| Wrong `pathElements[0]` | Witness rejected (root mismatch) |
| `fee = 2^64` | Witness rejected (range check) |
| `recipient = 2^160` | Witness rejected (range check) |
| `pool_id = 2^248` | Witness rejected (range check) |
| `chain_id = 2^64` | Witness rejected (range check) |
| `denomination = 0` | Witness rejected (non-zero constraint) |

Verifier-level cases (implemented in
`circuits/scripts/verify-negative.mjs`, all 11 pass):

| Case | Expected |
| --- | --- |
| Untampered proof | `true` |
| Wrong `chain_id` | `false` |
| Wrong `pool_id` | `false` |
| Wrong `root` | `false` |
| Wrong `nullifier` | `false` |
| Wrong `recipient` | `false` |
| Wrong `fee` | `false` |
| Swapped `root`/`nullifier` | `false` |
| `root >= p` | `false` |
| Tampered proof (`a.x + 1`) | `false` |
| Truncated proof | `false` |

Wrapper/contract cases to implement in M2 (not executable in this spike because
there is no wrapper contract):

| Case | Expected |
| --- | --- |
| Proof length 160 (MockVerifier shape) | Wrapper rejects |
| Proof length 255 / 257 | Wrapper rejects |
| `pool_id` top byte non-zero | Wrapper rejects |
| `root >= p` | Wrapper rejects |
| `nullifier >= p` | Wrapper rejects |
| `fee > uint64.max` | Wrapper rejects |
| `block.chainid > uint64.max` | Wrapper rejects |
| Zero recipient | `VeilPool` rejects |
| Fee above pool cap | `VeilPool` rejects |
| Nullifier already spent | `VeilPool` rejects |
| Root not in window | `VeilPool` rejects |
| Root not mature | `VeilPool` rejects |
| Pool paused | `VeilPool` rejects |
| Reorg removes spend | Indexer reconciles; note may become unspent |
| Two relayers race | One succeeds, one reverts |

### 12.4 Recorded spike results

| Check | Command | Result |
| --- | --- | --- |
| Compile | `circom circuits/membership.circom --r1cs --wasm --sym -l node_modules -o build` | Success; 6,623 non-linear / 14,569 total |
| Witness | `snarkjs wtns calculate` + `wtns check` | `WITNESS IS CORRECT` |
| Prove | `snarkjs groth16 prove` | Success |
| Verify | `snarkjs groth16 verify` | `OK!` |
| Public tampering | `node scripts/verify-negative.mjs` | 11/11 passed |
| Witness tampering | `node scripts/witness-negative.mjs` | 11/11 passed |
| Canonical fixture | `node scripts/canonicalize.mjs` | SHA-256 above |

The recorded CLI timings were roughly 1,112 ms to prove and 637 ms to verify
on the development machine, including Node process startup. This is **not** a
browser benchmark. The test plan's `< 8 s` browser target remains unverified.

---

## 13. Client integration notes

These are requirements for the future client; none are implemented in this
spike.

1. **Generate** both note secrets from a CSPRNG, reject zero/all-zero values,
   and never reuse a tuple.
2. **Reduce** secrets modulo `p` exactly as specified; keep the raw bytes for
   the note backup.
3. **Encode** `pool_id` with the canonical 31-byte rule; reject non-canonical
   IDs before generating a note or a proof.
4. **Derive** the commitment and nullifier with the exact domain tags and input
   order. The client must not duplicate this logic in multiple languages
   without cross-language test vectors.
5. **Fetch** the root and path from the indexer, but verify that the root is
   known and inside the accepted window according to the contract; do not
   blindly trust an API-supplied root.
6. **Check maturity** before submitting; the contract enforces it, but the UI
   should not invite a guaranteed revert.
7. **Prove locally** in a Web Worker/WASM. The witness, note and secrets must
   never leave the client. There is no server-side proving fallback.
8. **Clear** witness buffers after proving where the platform allows it. Do not
   put the witness in `localStorage`, IndexedDB, URLs, analytics or crash
   reports.
9. **Encode** the proof as 256 bytes and the public signals in the exact order.
   Reject any verifier response that does not match the expected proof system.
10. **Handle failures** distinctly: witness failure (bad note/path), verifier
    false (bad proof/public signals), contract revert (nullifier, root,
    maturity, fee cap, pause), and relayer/network failure.
11. **Regenerate** when the root changes or is evicted; a proof is bound to its
    root.
12. **Do not claim** anonymity from a successful proof. The proof hides the
    witness link; it does not hide recipient, fee, timing or transaction
    metadata.

Browser proving performance is not measured. The circuit is small (6,623
non-linear constraints), but WASM witness generation, memory use, mobile
devices and cold starts still need a benchmark before the `< 8 s` target can be
claimed.

---

## 14. Audit checklist

### 14.1 Circuit

- [ ] Every derived public signal is constrained to the witness
      (`chain_id`/`pool_id`/`root`/`nullifier`); `recipient`/`fee` are public
      inputs bound by the verifier and range-checked.
- [ ] Public signal order is exactly `[chain_id, pool_id, root, nullifier, recipient, fee]`.
- [ ] Domain tags are unique, versioned and used in the intended hashes.
- [ ] Commitment and nullifier input order matches the specification byte-for-byte.
- [ ] `Poseidon(6)`, `Poseidon(5)` and `Poseidon(3)` arities and constants are correct.
- [ ] Path bits are constrained to `0/1`; no unconstrained selector.
- [ ] Left/right selection is correct for both bit values.
- [ ] Empty-subtree roots and leaf indexing match the contract/indexer.
- [ ] Depth is 20 and the leaf count bound is documented.
- [ ] Range checks cover every public value that must fit an ABI/field type.
- [ ] Zero commitment and zero denomination are rejected.
- [ ] No public output or unused signal is accidentally exposed.
- [ ] The circuit does not claim to enforce root freshness, maturity or fee caps.
- [ ] Constraint count and circuit hash are recorded.

### 14.2 Trusted setup

- [ ] The circuit and domain tags were frozen before the ceremony.
- [ ] Phase-1 transcript is public and every contribution was verified.
- [ ] Phase-2 contributions are independent and their hashes are published.
- [ ] The final zkey and verification key hashes are published.
- [ ] A second party reproduced the build and compared hashes.
- [ ] Toxic waste destruction is described and auditable.
- [ ] The verifier address is immutable and pinned to the audited key.
- [ ] A setup-compromise incident plan exists.

### 14.3 Verifier wrapper

- [ ] Proof length is exactly 256 bytes; 160-byte mock proofs are rejected.
- [ ] `chain_id` comes from `block.chainid`, not from a caller argument.
- [ ] `chain_id < 2^64`; `pool_id < 2^248`; `root < p`; `nullifier < p`;
      `fee < 2^64`.
- [ ] Public signal order and `pi_b` coordinate order match `soliditycalldata`.
- [ ] Malformed input returns `false` (or the documented revert behavior).
- [ ] The wrapper is `view`, non-reentrant by construction, and cannot write
      state.
- [ ] The generated verifier's `nPublic` is 6 and the key hash is pinned.
- [ ] Gas is measured on the target chain.
- [ ] No proxy or admin can swap the verifier key silently.

### 14.4 Contract and indexer

- [ ] The on-chain tree uses the exact Poseidon node hash, domain tag and zero
      hashes from this spec (or the circuit is changed to match the contract).
- [ ] Deposits reject commitments `>= p` and zero.
- [ ] Pool IDs are canonical (`< 2^248`) and the registry enforces the limit.
- [ ] Denominations and fees fit the circuit's `uint64` ranges.
- [ ] Root history, root timestamps and maturity remain correct after the tree
      change.
- [ ] Nullifier storage is per pool and cannot be double-spent.
- [ ] Pause, fee cap, recipient zero-check and payout accounting are unchanged.
- [ ] Indexer root reconstruction uses the same Poseidon rules.
- [ ] Reorg rollback/replay converges to the same root and nullifier set.
- [ ] `MockVerifier` is absent from every real withdrawal path and every
      production deployment script.

### 14.5 Client and operations

- [ ] Note secrets are CSPRNG-generated, reduced correctly, never reused.
- [ ] Witness and note never leave the client; logs/analytics/tests are scanned.
- [ ] Proof generation is local and has no server fallback.
- [ ] Root freshness and maturity are checked before submission.
- [ ] Proof encoding and public signal order are tested against the verifier.
- [ ] Failure states are distinct and actionable.
- [ ] Testnet-only chain ID checks remain in place.
- [ ] No UI copy claims "untraceable", "anonymous" or "production-secure".
- [ ] An independent audit is complete before any real-value discussion.

---

## 15. Open risks and questions

| ID | Risk / question | Status |
| --- | --- | --- |
| ZK-1 | Current contract tree is keccak; circuit is Poseidon | Open; blocks integration |
| ZK-2 | Trusted setup is a local development setup | Open; blocks production |
| ZK-3 | Poseidon parameters not independently reviewed | Open |
| ZK-4 | `chain_id` alone does not distinguish same-ID forks | Open; consider genesis hash |
| ZK-5 | Relayer fee can be captured by a front-runner | Open; off-chain mitigation |
| ZK-6 | Note secret reduction changes the note's field encoding | Defined here; needs client migration tests |
| ZK-7 | Pool ID canonical encoding differs from current API/contract IDs | Open; breaking change |
| ZK-8 | Commitment canonicality not enforced on deposit; root canonicality is checked only by the wrapper | Open; see §11.4 |
| ZK-9 | Denomination/fee `uint64` bound may not fit future assets | Open |
| ZK-10 | Browser/WASM proving performance unmeasured | Open |
| ZK-11 | No deposit-side proof; a malformed commitment can be burned | Open; testnet only |
| ZK-12 | No recursion/aggregation; one proof per withdrawal | Accepted for v1 |
| ZK-13 | Root window and maturity remain contract-level; no circuit time | Accepted |
| ZK-14 | Anonymity set, timing and recipient reuse remain product risks | Accepted; no anonymity claim |
| ZK-15 | No audit of the circuit, verifier or setup | Open; blocks real value |

---

## 16. Version history

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | 2026-11-03 | Initial spike: depth-20 Poseidon membership circuit, six public signals, Groth16 dev setup, deterministic fixture, negative tests. Not integrated; not audited. |

---

## Appendix A · Canonical encodings

### A.1 Field element to bytes32

```text
bytes32 = 32-byte big-endian integer
valid   = value < p
```

For `pool_id`, the first byte must be `0x00`, so the value is `< 2^248 < p`.
For `root` and `nullifier`, values are Poseidon outputs and are already `< p`.
The wrapper still checks them.

### A.2 Address

```text
recipient_field = uint256(uint160(recipient))
```

A Solidity `address` is 160 bits, so this is lossless and canonical.

### A.3 Pool ID

```text
pool_id_bytes32 = 0x00 || UTF-8(pool_id_text) || 0x00 ... (32 bytes total)
pool_id_field   = uint256_be(pool_id_bytes32)
```

`pool_id_text` is 1–31 UTF-8 bytes. Reject longer IDs. Do not use
`keccak256(pool_id_text)` for the circuit's `pool_id` signal.

### A.4 Proof

```text
256 bytes = a.x || a.y || b00 || b01 || b10 || b11 || c.x || c.y
```

Use `snarkjs zkey export soliditycalldata` ordering. Do not reorder `pi_b`
manually.

### A.5 Public signals

```text
[chain_id, pool_id, root, nullifier, recipient, fee]
```

Each is a 32-byte big-endian word. `snarkjs` `public.json` is a JSON array of
decimal strings in this order.

### A.6 Canonical JSON

The fixture's canonical form is a recursive lexicographic key sort followed by
compact `JSON.stringify`, UTF-8. The data model contains only strings, booleans,
integers and arrays, so this is RFC 8785-compatible for this fixture. The
SHA-256 is over the exact canonical bytes (no trailing newline), as recorded in
`membership-v1.canonical.sha256`.
