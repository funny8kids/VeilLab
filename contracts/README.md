# VeilPool contracts (testnet-only MVP)

> ## MOCK — NOT A REAL MIXER
>
> **`MockVerifier` performs no cryptography.** It accepts a deterministically encoded copy of
> the public signals. Anyone who can read a valid Merkle root can construct a "proof" it
> accepts. This project provides **no anonymity, no membership proof, and no production
> security**. Do not use it with real funds or on any public network. It exists only for a
> local/testnet product demo.

Solidity `^0.8.24` Foundry project for the VeilPool MVP:

- fixed-denomination ETH pools identified by `poolId`;
- deposit commitments inserted into a 20-level incremental Merkle tree;
- bounded root history ("root window") with a timestamp per accepted root;
- on-chain maturity before a root can be used for withdrawal;
- one nullifier per pool;
- owner pause/resume;
- bounded relayer fees and a protocol fee fixed at `0` bps for the MVP;
- safe low-level ETH transfers.

The pool does not use a proxy, does not use `delegatecall`, and does not contain any
mainnet-specific chain ID, RPC or deployment configuration.

---

## Layout

```text
contracts/
├── foundry.toml
├── .gitignore
├── README.md
├── script/
│   ├── Deploy.s.sol
│   ├── DeployPoseidon.s.sol
│   └── DepositFixture.s.sol
├── src/
│   ├── IVerifier.sol
│   ├── MockVerifier.sol
│   ├── VeilPool.sol
│   ├── Poseidon.sol
│   ├── Groth16VerifierAdapter.sol
│   ├── VeilPoolPoseidon.sol
│   └── verifiers/
│       └── Groth16Verifier.sol
└── test/
    ├── VeilPool.t.sol
    ├── Groth16.t.sol
    ├── VeilPoolPoseidon.t.sol
    └── fixtures/
        └── MembershipFixture.sol
```

---

## Requirements

- [Foundry](https://book.getfoundry.sh/getting-started/installation) (`forge`, `cast`, `anvil`)
- Git (for the `forge-std` test dependency)
- No RPC endpoint is required. Do not add a mainnet RPC.

Check the toolchain:

```powershell
forge --version
```

In this workspace Foundry v1.9.0 is available at
`%LOCALAPPDATA%\veilpool-tools\foundry-v1.9.0\forge.exe` (with `anvil`, `cast` and `chisel`).

---

## Build and test

From the repository root in PowerShell:

```powershell
Set-Location G:\Worker-Space\VeilLab\contracts
forge install foundry-rs/forge-std --no-commit
forge build
forge test -vvv
```

Useful variants:

```powershell
forge test --match-contract VeilPoolTest -vvvv
forge test --match-test test_WithdrawHappyPath -vvvv
forge fmt --check
```

`forge install` adds `lib/forge-std` as a dependency; `lib/` and build artifacts are ignored by
`contracts/.gitignore`. Do not commit.

### Execution status in this workspace

Foundry v1.9.0 is available and the full suite passes: **53 tests** across
`VeilPoolTest`, `Groth16Test` and `VeilPoolPoseidonTest`. `forge fmt --check` passes.
`forge-std` is installed under `contracts/lib/forge-std` and is gitignored.

The two Poseidon scripts compile with `forge build`; `DeployPoseidon.s.sol` is dry-run against
a temporary local Anvil. No broadcast is performed by the verification run. The original
`VeilPool` + `MockVerifier` path and the real-proof spike are separate. See
[`docs/veilpool/ZK_CONTRACT_INTEGRATION.md`](../docs/veilpool/ZK_CONTRACT_INTEGRATION.md).

---

## Contract behavior

### Pools

`createPool(bytes32 poolId, uint256 denomination, uint32 rootWindow, uint32 maturity)` is
owner-only. `maturity` is the number of seconds a root must age before it can be used for a
withdrawal. `rootWindow` and `maturity` are fixed for the life of the pool.

Because the required deposit ABI is `deposit(bytes32 commitment) external payable` and has no
`poolId`, a deposit is routed by its **exact `msg.value`**. Therefore:

- only one active pool may exist per denomination;
- any `msg.value` other than a registered denomination reverts with
  `UnknownDenomination(uint256)`;
- pool IDs must be non-zero and unique.

`poolId` is still used for withdrawals, events, root history, tree state and nullifiers.

### Deposit

`deposit(bytes32 commitment)`:

1. resolves the pool from the exact `msg.value`;
2. rejects a paused pool;
3. rejects `bytes32(0)` commitments;
4. inserts the commitment at the next leaf index;
5. updates the current root, the bounded root history and the root timestamp;
6. emits `Deposit(poolId, commitment, leafIndex, timestamp)` and
   `RootUpdated(poolId, root, leafIndex)`.

No claim is made that the commitment hides a note; note generation happens client-side and is
outside this repository.

### Withdraw

`withdraw(proof, root, nullifier, recipient, relayerFee, poolId)`:

1. rejects an unknown pool or a paused pool;
2. rejects a zero recipient or zero nullifier;
3. requires `root` to be inside the pool's root window;
4. requires the root to be mature:
   `block.timestamp >= rootTimestamp(poolId, root) + maturity`; otherwise reverts with
   `MaturityNotReached(uint256 readyAt)`;
5. rejects a nullifier already spent **in that pool**;
6. calls the immutable verifier with all public signals;
7. bounds `relayerFee + protocolFee` to `MAX_FEE_BPS = 1000` (10% of the denomination);
8. marks the nullifier spent before any ETH transfer;
9. pays `relayerFee` to `msg.sender` (the relayer), `protocolFee` to the owner (zero in the
   MVP), and `denomination - relayerFee - protocolFee` to `recipient`;
10. emits `Withdrawal(poolId, nullifier, recipient, totalFee, timestamp)`.

The fee bound means a withdrawal can never pay out zero or a negative amount. `_sendValue`
uses a low-level `call` and reverts with `TransferFailed()` if the recipient rejects ETH; because
the nullifier write happens in the same transaction, a failed transfer does not consume the
note.

### Maturity

`maturity` is stored per pool in seconds and exposed by `maturityOf(poolId)`.
`rootTimestamp(poolId, root)` records when a root was accepted: the initial empty root at pool
creation, and every deposit root at deposit time. A withdrawal using that root is allowed only
once `maturity` seconds have elapsed. Root maturity is therefore a property of the root, not of
an individual note. Using a newer root can extend the wait; clients should use a root that
contains their deposit.

The initial empty root is recorded for completeness. It has no deposit behind it, so it cannot
produce a spendable note with a real verifier.

### Root window

`rootWindow` is a **count of recent roots**, not a time or block window. The initial empty root
plus each deposit root are appended, and each accepted root stores `block.timestamp` in
`rootTimestamp(poolId, root)`. When the history exceeds `rootWindow`, the oldest root is evicted.
Its known flag and timestamp are cleared only after its last live occurrence leaves the window.
A proof against an evicted or never-recorded root reverts with `UnknownRoot(poolId, root)`.
`rootTimestamp` returns `0` for such roots.

### Pause / resume

The immutable owner can pause and resume individual pools:

```solidity
pause(bytes32 poolId, string calldata reason)
resume(bytes32 poolId)
```

Both deposit and withdrawal are blocked while paused. The owner cannot move user funds, change
the verifier, or upgrade the contract.

### Fees

- `MAX_FEE_BPS = 1000` (10% maximum total fee).
- `PROTOCOL_FEE_BPS = 0` for the MVP.
- `relayerFee` is paid to `msg.sender`.
- `quoteWithdrawal(poolId, relayerFee)` returns the payout breakdown and reverts if the quote is
  over the cap.
- Fee changes are not implemented in the MVP; a different fee policy requires a new deployment.

### Events

```solidity
event Deposit(bytes32 indexed poolId, bytes32 commitment, uint256 leafIndex, uint256 timestamp);
event Withdrawal(bytes32 indexed poolId, bytes32 nullifier, address recipient, uint256 fee, uint256 timestamp);
event RootUpdated(bytes32 indexed poolId, bytes32 root, uint256 leafIndex);
event PoolPaused(bytes32 indexed poolId, string reason);
event PoolResumed(bytes32 indexed poolId);
event PoolCreated(bytes32 indexed poolId, uint256 denomination, uint32 rootWindow, uint32 maturity);
```

`Withdrawal.fee` is the sum of the relayer fee and protocol fee.

---

## Real-proof spike (separate contract)

`VeilPoolPoseidon` is a separate local spike with the same public behavior as `VeilPool` but a
Poseidon Merkle tree. `Groth16VerifierAdapter` binds six public signals in circuit order
(`chain_id, pool_id, root, nullifier, recipient, fee`) and calls the generated
`Groth16Verifier`.

- The fixture proof from `circuits/build/` is accepted on the EVM at chain ID `11155111`.
- Eight fixture deposits reproduce the circuit root exactly.
- A real withdrawal pays the recipient, spends the nullifier and rejects replay.
- The spike uses a **development zkey** and an unaudited reference Poseidon implementation.
- Deposit gas is roughly 14.17M; this is not production-ready.
- The default `script/Deploy.s.sol` still deploys `VeilPool` + `MockVerifier` and remains the
  shipped demo. The separate `script/DeployPoseidon.s.sol` deploys this spike on chain ID
  `31337` only.

See [`docs/veilpool/ZK_CONTRACT_INTEGRATION.md`](../docs/veilpool/ZK_CONTRACT_INTEGRATION.md)
for the signal order, pool-ID conversion, fixture values and exact commands.

### Deploy the spike on local Anvil

> **DEVELOPMENT ZKEY / NO CEREMONY / NOT PRODUCTION.** The verifier was exported from a
> single-machine development zkey. Anyone who can recover its toxic waste can forge proofs.
> The circuit, Poseidon implementation, adapter and pool are unaudited.

`DeployPoseidon.s.sol` refuses any chain other than `31337`. It deploys
`Groth16VerifierAdapter` (whose constructor deploys the generated `Groth16Verifier`) and
`VeilPoolPoseidon`, then creates exactly one pool:

| Field | Value |
| --- | --- |
| Label | `bytes32("pool_eth_01")` |
| Pool ID | `0x706f6f6c5f6574685f3031000000000000000000000000000000000000000000` |
| Denomination | `0.1 ether` (`100000000000000000` wei) |
| Root window | `64` roots (count-based, not time-based) |
| Maturity | `0` seconds |

> **MATURITY 0 IS A LOCAL SPIKE SETTING, NOT A PRODUCT DEFAULT.**
>
> Maturity 0 makes every accepted root immediately eligible for withdrawal so a local browser
> proof does not need to wait. It removes the root-aging defense. The shipped mock demo uses 30
> minutes, 2 hours and 6 hours. Do not copy maturity 0 into a product, testnet or public
> deployment.

```powershell
Set-Location G:\Worker-Space\VeilLab\contracts
$Forge = "$env:LOCALAPPDATA\veilpool-tools\foundry-v1.9.0\forge.exe"

# Terminal 1: local Anvil only.
anvil --host 127.0.0.1 --port 8545 --chain-id 31337

# Terminal 2: deploy the spike. Uses Anvil's unlocked account #0; no private key.
& $Forge script script/DeployPoseidon.s.sol:DeployPoseidon `
  --rpc-url http://127.0.0.1:8545 `
  --broadcast `
  --unlocked --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 `
  -vv
```

On a fresh Anvil chain with account #0 as the first deployer, the addresses are deterministic:

| Contract | Address |
| --- | --- |
| `Groth16VerifierAdapter` | `0x5FbDB2315678afecb367f032d93F642f64180aa3` |
| `VeilPoolPoseidon` | `0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512` |
| `Groth16Verifier` (via adapter) | `0xa16E02E87b7454126E5E10d957A927A7F5B5d2be` |

These are example addresses for a fresh chain and nonce 0; the script prints the authoritative
addresses for the actual deployment. The script also prints the exact indexer/API environment
variables below.

### Reproduce the fixture tree on the live chain (optional)

`DepositFixture.s.sol` deposits the eight **public** fixture commitments into the labelled
pool so the live chain reproduces the fixture root. It refuses any chain other than `31337`,
requires `VEILPOOL_POSEIDON_ADDRESS`, and only runs against a fresh pool with zero leaves. It
sends commitments only; no note secret, nullifier secret or proof is sent on chain.

```powershell
Set-Location G:\Worker-Space\VeilLab\contracts
$env:VEILPOOL_POSEIDON_ADDRESS = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"

& $Forge script script/DepositFixture.s.sol:DepositFixture `
  --rpc-url http://127.0.0.1:8545 `
  --broadcast `
  --unlocked --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 `
  -vv
```

The script prints the current root and fails unless it equals the fixture root
`0x2145dfa5869ae142af6de0e91ea20be3100f93e76a6f2d279e520b1db1b329bb`.

> **The static fixture proof is bound to chain ID `11155111`.** It is rejected by the adapter on
> local chain `31337` by design. `DepositFixture.s.sol` only reproduces the fixture Merkle tree;
> generate a fresh proof with `chain_id = 31337` for a local withdrawal.

### Run the indexer and API against the spike pool

`VeilPoolPoseidon` emits the same `Deposit`, `RootUpdated`, `Withdrawal`, `PoolPaused`,
`PoolResumed` and `PoolCreated` events as `VeilPool`, so the existing indexer can follow it.
Point both services at the `VeilPoolPoseidon` address:

```powershell
# Terminal 3: indexer
Set-Location G:\Worker-Space\VeilLab\apps\indexer
$env:ANVIL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_ADDRESS = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
$env:INDEXER_DB = "indexer.db"
$env:INDEXER_START_BLOCK = "0"
$env:INDEXER_PORT = "8100"
$env:INDEXER_ALLOWED_CHAIN_IDS = "31337"
python -m veilpool_indexer

# Terminal 4: API in local-chain mode
Set-Location G:\Worker-Space\VeilLab\apps\api
$env:VEILPOOL_MODE = "local"
$env:VEILPOOL_CHAIN_ID = "31337"
$env:VEILPOOL_CONTRACT_ADDRESS = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
$env:VEILPOOL_INDEXER_URL = "http://127.0.0.1:8100"
$env:VEILPOOL_LOCAL_RPC_URL = "http://127.0.0.1:8545"
$env:VEILPOOL_LOCAL_AUTO_DEPOSIT = "false"
python -m uvicorn veilpool_api.main:app --port 8000
```

### Browser proof path (conceptual interface only)

No `apps/` change is made by this spike. The shipped web app is still the mock/local API demo;
a real browser prover is not wired. A browser proof for this pool must use these values:

- `chain_id = 31337`, `pool_id_text = "pool_eth_01"`.
- Contract pool label `D = bytes32("pool_eth_01")`. The circuit field is
  `F = uint256(D) >> 8`; never pass the zero-prefixed `F` to `createPool`.
- `denomination = 100000000000000000` wei.
- `commitment = Poseidon(6)(DOMAIN_COMMITMENT, chain_id, F, denomination, secret, nullifier_secret)`.
- `nullifier = Poseidon(5)(DOMAIN_NULLIFIER, chain_id, F, commitment, nullifier_secret)`.
- Public signals, in circuit order:
  `[chain_id, F, root, nullifier, recipient, relayerFee]`.
- Proof bytes: exactly 256 bytes,
  `abi.encode(uint256[2] pA, uint256[2][2] pB, uint256[2] pC)`, with `pB` in snarkjs
  `soliditycalldata` order.
- Withdrawal call:
  `withdraw(proof, root, nullifier, recipient, relayerFee, bytes32("pool_eth_01"))`.

Build the Merkle path from the canonical deposit order at `/pools/pool_eth_01/deposits` and use
the latest root from `/pools/pool_eth_01/roots` (the root must remain inside the 64-root
window). Because maturity is 0, a root is immediately eligible. Generate the proof locally and
never send note secrets, nullifier secrets or proof material to the API/indexer.

> The indexer/API payloads still contain the shipped `"mock_verifier": true` label. That flag is
> hard-coded in the apps and is not verifier introspection. It does not mean this deployment
> uses `MockVerifier`, and it is not a security claim.

---

## Mock proof format

`MockVerifier` expects exactly 160 bytes:

```solidity
abi.encode(
    bytes32 root,
    bytes32 nullifier,
    address recipient,
    uint256 relayerFee,
    bytes32 poolId
)
```

`MockVerifier.encodeProof(...)` produces this encoding for tests and local demos. The verifier
only compares the decoded values to the supplied public signals. **It does not verify Merkle
membership, note ownership, a secret, or a chain domain.** A real deployment must replace it
with an audited ZK verifier and a matching circuit.

---

## Tests written

`test/VeilPool.t.sol` covers:

| Test | Requirement |
| --- | --- |
| `test_ValidDeposit` | Valid deposit, event, leaf index, root update, initial/deposit root timestamps |
| `test_WrongAmountReverts` | Deposit below/above the exact denomination reverts |
| `test_ZeroCommitmentReverts` | Rejects the zero commitment sentinel |
| `test_DuplicateNullifierReverts` | Nullifier can be spent only once per pool |
| `test_NullifierIsScopedPerPool` | Same nullifier is independent across pools |
| `test_PausedPoolBlocksDepositAndWithdraw` | Paused pool blocks both actions |
| `test_ResumeUnblocksPool` | Resume restores deposits |
| `test_PauseOnlyOwner` | Non-owner cannot pause |
| `test_RootWindowExpiresOldRoot` | Old root and its timestamp are evicted; a root inside the window still works |
| `test_MaturityBeforeReadyReverts` | Withdrawal before `rootTimestamp + maturity` reverts |
| `test_MaturityExactlyAtReadySucceeds` | Withdrawal exactly at maturity succeeds |
| `test_MaturityAfterReadySucceeds` | Withdrawal after maturity succeeds |
| `test_RootTimestampUnknownReverts` | Unknown root timestamp returns zero and withdrawal reverts |
| `test_WithdrawHappyPath` | Mock proof, recipient payout, relayer fee, event |
| `test_InvalidProofReverts` | Malformed mock proof is rejected |
| `test_ZeroRecipientReverts` | Zero recipient is rejected |
| `test_RejectedTransferDoesNotSpendNullifier` | Failed ETH transfer rolls back the nullifier |
| `test_FeeAtCapSucceeds` | Fee exactly at the 10% cap is allowed |
| `test_FeeAboveCapReverts` | Fee above the cap reverts |
| `test_ProtocolFeeIsZeroInMvp` | Protocol fee is zero and the quote is consistent |
| `test_CreatePoolRejectsDuplicateDenomination` | One pool per denomination |
| `test_MockVerifierRejectsMismatchedSignals` | Mock verifier checks public-signal binding only |

The tests do not claim security coverage. They exercise the MVP contract state machine.

`test/Groth16.t.sol` (17 tests) covers the real fixture proof, six-signal binding, malformed
proof lengths, tampered root/nullifier/recipient/fee/pool/chain, non-canonical pool labels and
field bounds. `test/VeilPoolPoseidon.t.sol` (14 tests) covers Poseidon vectors against
circomlibjs, the empty-subtree root, reproducing the fixture root from eight deposits, a real
withdrawal, replay, maturity, pause behavior and canonical pool labels.

---

## Known gaps

1. **Default path has no real zero-knowledge proof.** `MockVerifier` is non-cryptographic. It
   cannot prove membership and is trivially forgeable. The real-proof spike is separate and uses
   a development setup; it is not the default deployment.
2. **The real-proof spike is not production-ready.** It uses an unaudited reference Poseidon
   implementation, a single-machine zkey and very high deposit gas. A ceremony and audit are
   required before any real-value use.
3. **Maturity is root-based, not note-based.** A root's clock starts when the root is accepted.
   A deposit that lands just before a newer root may need to wait for the newer root (or use the
   older root while it is still in the window).
4. **Root window is count-based.** It is not block- or time-based, and the root history array
   grows indefinitely even though only the last `rootWindow` entries are valid.
5. **Protocol fee is fixed at zero.** There is no protocol-fee accrual or treasury claim path.
6. **One pool per denomination.** This follows from the required `deposit(bytes32)` ABI and
   `msg.value` routing. Supporting multiple pools with the same denomination needs a pool-ID
   parameter or a different depot design.
7. **ETH only.** ERC-20, USDC and tBTC pools are not implemented.
8. **No relayer quote/signature validation.** The contract bounds the fee but does not verify
   an off-chain signed quote or expiry.
9. **No compliance integration.** Sanctions, jurisdiction and limits are out of scope here.
10. **No per-pool balance ledger.** ETH is held by the contract as a whole; accounting relies on
    events. A balance reconciliation layer is not implemented.
11. **Default deploy path uses the mock verifier.** `script/Deploy.s.sol` deploys
    `VeilPool` + `MockVerifier` and remains the shipped local demo. The separate
    `script/DeployPoseidon.s.sol` deploys the real-proof spike on chain ID 31337 only; it does
    not change the default path or add a public-network deployment.
12. **Foundry is not on the default `PATH` here.** Use
    `%LOCALAPPDATA%\veilpool-tools\foundry-v1.9.0\forge.exe` or install Foundry; CI installs it.
13. **Testnet only.** No mainnet chain IDs, RPCs, keys or broadcast path are included. Do not add
    them.
14. **Centralized immutable owner.** The owner can pause a pool indefinitely and there is no
    ownership transfer or timelock. Acceptable for a testnet MVP, not for production operations.
15. **Mock proof does not bind chain ID.** The mock proof echoes `poolId` but not `chain_id`.
    The real adapter binds `block.chainid` and rejects a proof for another chain.
16. **Local chain ID differs from the fixture chain ID.** The static fixture proof is bound to
    chain ID `11155111`, while the local spike deployment is chain ID `31337`. The fixture proof
    is rejected on the local deployment by design. `DepositFixture.s.sol` only reproduces the
    fixture root; a browser withdrawal needs a fresh proof generated for `31337`.
17. **Indexer/API still report `mock_verifier: true`.** That value is hard-coded in the shipped
    apps and is not verifier introspection. It does not mean the Poseidon pool uses
    `MockVerifier`, and it is not a security claim.
