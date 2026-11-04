# VeilPool ZK Contract Integration (local spike)

**Status:** local proof spike · **Date:** 2026-11-03
**Scope:** local Foundry/EVM only · testnet-only design · **not audited · not production**
**Related:** [ZK Circuit Spec](ZK_CIRCUIT_SPEC.md) · [Circuits README](../../circuits/README.md) · [Contracts README](../../contracts/README.md) · [Pool Model](POOL_MODEL.md)

---

> ## Read this first
>
> This document describes a **local spike**, not a shipped integration.
>
> - The Groth16 verifier is generated from a **single-machine development zkey**
>   (`circuits/build/membership_0001.zkey`). Its toxic waste was not destroyed in
>   an auditable ceremony. Anyone who can recover it can forge proofs for this
>   circuit.
> - The Poseidon implementation, adapter, pool and generated verifier are
>   **not audited**.
> - The default shipped demo path is still **`VeilPool.sol` + `MockVerifier.sol`**.
>   `MockVerifier` performs no cryptography. This spike does **not** change that
>   default, `apps/`, the prototype, or the existing docs.
> - No production security, anonymity, privacy, liveness or mainnet claim is made.
>   Do not use any of this with real funds. Do not add a mainnet RPC, broadcast,
>   or real key.

This spike answers one narrow question: **can the existing depth-20
Poseidon/Groth16 membership proof be verified on the EVM against a root built by
a real on-chain Poseidon pool?** The answer is yes, locally: the fixture proof is
accepted by the EVM verifier, the eight fixture deposits reproduce the circuit
root exactly, and a full withdrawal succeeds.

---

## 1. What is real in this spike

| Piece | Status |
| --- | --- |
| Circom membership circuit (`circuits/circuits/membership.circom`) | Real depth-20 Poseidon circuit, already compiled/proved |
| Groth16 proof (`circuits/build/proof.json`) | Real proof from `membership_0001.zkey` |
| Public signals (`circuits/build/public.json`) | Real six-signal array in circuit order |
| EVM pairing check | Real BN254 precompiles via the generated Solidity verifier |
| Solidity Poseidon (`contracts/src/Poseidon.sol`) | Generated from circomlibjs 2.0.5 constants; matches the fixture vectors |
| `Groth16VerifierAdapter` | Real `IVerifier` wrapper, real public-signal binding |
| `VeilPoolPoseidon` | Real Poseidon Merkle tree, root history, nullifier set, ETH payouts |
| Foundry end-to-end test | Real proof verified on the EVM, then a real withdrawal |

The development trusted setup is **not** real production key material. The
fixture's note secrets are public test values.

---

## 2. Architecture

```text
client / fixture (off-chain)
  note: chain_id, pool_id_text, denomination, secret, nullifier_secret
  path: pathElements[20], pathIndices[20]
        |
        |  circom witness + snarkjs Groth16 prove
        |  circuits/build/membership_0001.zkey
        v
  proof.json + public.json
  public = [chain_id, pool_id, root, nullifier, recipient, fee]
        |
        |  abi.encode(uint256[2] pA, uint256[2][2] pB, uint256[2] pC)
        |  256 bytes, pB in snarkjs soliditycalldata order
        v
+-----------------------------------------------+
| Groth16VerifierAdapter (IVerifier)            |
|  - reads block.chainid                        |
|  - converts bytes32 deploy label -> pool field|
|  - range-checks root/nullifier/fee/chain      |
|  - calls generated Groth16Verifier            |
+-----------------------------------------------+
        |                         ^
        | verifyProof(...)        | verifier key from
        v                         | membership_0001.zkey
+-----------------------------------------------+
| Groth16Verifier (generated Solidity)          |
|  BN254 pairing precompiles (0x06/0x07/0x08)   |
+-----------------------------------------------+
        |
        | true only if all six signals match
        v
+-----------------------------------------------+
| VeilPoolPoseidon                              |
|  - Poseidon Merkle tree, depth 20             |
|  - zero[i+1] = Poseidon(DOMAIN_NODE, z, z)    |
|  - root window + root timestamps/maturity     |
|  - per-pool nullifier set                     |
|  - fixed denomination, fee cap, pause/resume  |
|  - same public ABI as VeilPool                |
+-----------------------------------------------+
        |
        | ETH payouts (relayer fee + recipient)
        v
  recipient / relayer
```

The circuit proves membership and nullifier derivation. The pool enforces root
freshness, maturity, nullifier uniqueness, pause state, fee caps and payout
accounting. The adapter binds `block.chainid` and converts the pool ID.

---

## 3. Contracts and files

| File | Purpose |
| --- | --- |
| `contracts/src/Poseidon.sol` | Generated loop-based Poseidon over BN254; `hash3`, `hash5`, `hash6`; `DOMAIN_NODE` |
| `contracts/src/Groth16VerifierAdapter.sol` | Implements `IVerifier`; six-signal ordering, pool-ID conversion, range checks, malformed-proof handling |
| `contracts/src/verifiers/Groth16Verifier.sol` | Generated snarkjs verifier; GPL-3.0 header retained; development key warning added |
| `contracts/src/VeilPoolPoseidon.sol` | Separate Poseidon pool; copy of `VeilPool` semantics; **does not modify `VeilPool.sol`** |
| `contracts/src/VeilPool.sol` | Unchanged default keccak256 demo pool |
| `contracts/src/MockVerifier.sol` | Unchanged mock verifier for the default demo |
| `contracts/src/IVerifier.sol` | Unchanged interface |
| `contracts/test/Groth16.t.sol` | 17 adapter/proof tests |
| `contracts/test/VeilPoolPoseidon.t.sol` | 14 Poseidon/pool integration tests |
| `contracts/test/fixtures/MembershipFixture.sol` | Generated proof, signals, leaves and Poseidon vectors |
| `circuits/scripts/gen-poseidon-solidity.mjs` | Regenerates `Poseidon.sol` from circomlibjs constants |
| `circuits/scripts/gen-solidity-fixture.mjs` | Regenerates the Solidity fixture from `proof.json` / `public.json` / test vectors |

`IVerifier` is unchanged. No function signature in the pool ABI changed; the new
contract adds `FIELD_MODULUS`, `DOMAIN_NODE`, `VERIFIER_KIND` and the same pool
getters as `VeilPool`.

### 3.1 `VeilPoolPoseidon` behavior

It keeps the `VeilPool` state machine:

- one pool per exact denomination (deposit is routed by `msg.value`);
- owner-only pool creation, pause and resume;
- bounded count-based root history;
- root timestamp + maturity before withdrawal;
- per-pool nullifier set;
- relayer fee paid to `msg.sender`, protocol fee fixed at 0 bps;
- 10% total fee cap;
- non-reentrant withdrawal and low-level ETH transfers;
- `receive()` rejects direct ETH.

It changes only what is required for this circuit:

1. Internal nodes: `Poseidon.hash3(DOMAIN_NODE, left, right)` instead of `keccak256`.
2. Empty subtree roots: the same Poseidon rule instead of keccak.
3. Deposits reject `uint256(commitment) >= p`. A value at or above the BN254
   scalar field cannot be a Poseidon output and could never be spent.
4. `createPool` rejects IDs whose low byte is non-zero (the adapter's deploy-label
   convention) and denominations above `uint64.max` (the circuit's range).
5. `VERIFIER_KIND = "groth16-poseidon-membership-v1"`.

These extra checks are spike-only integration guards. They are not a substitute
for an audit.

---

## 4. Public signal order

The circuit declaration is authoritative:

```solidity
component main {public [chain_id, pool_id, root, nullifier, recipient, fee]} =
    Membership(20);
```

The adapter builds exactly this array:

| Index | Signal | Source | Adapter check |
| --- | --- | --- | --- |
| 0 | `chain_id` | `block.chainid` | rejects `> uint64.max` |
| 1 | `pool_id` | `_poolIdField(poolId)` | nonzero, low byte zero, shift right 8 |
| 2 | `root` | `bytes32 root` argument | `< p` |
| 3 | `nullifier` | `bytes32 nullifier` argument | `< p` |
| 4 | `recipient` | `uint160(recipient)` | address is already `< 2^160` |
| 5 | `fee` | `relayerFee` | `<= uint64.max` |

The adapter never takes `chain_id` from the caller. A proof generated for
Sepolia (chain ID `11155111`) is rejected on any other chain, including a local
Anvil chain with a different `block.chainid`. The `block.chainid > uint64.max`
branch is defensive; Foundry's `vm.chainId` cheatcode refuses values `>= 2^64`,
so that branch is not directly exercised by the test suite.

---

## 5. Pool ID conversion (spike-only convention)

There are two encodings in play:

### 5.1 Deploy label `D` (right-padded ASCII)

The existing deploy script uses right-padded ASCII bytes32 labels:

```text
D = bytes32("pool_eth_01")
  = 0x706f6f6c5f6574685f3031000000000000000000000000000000000000000000
```

`D` has the ASCII bytes at offsets 0..10 and zero padding at offsets 11..31.
Its **low byte is zero**.

### 5.2 Circuit field `F` (zero-prefixed canonical encoding)

The fixture/spec encoding is:

```text
F = 0x00 || UTF-8("pool_eth_01") || zero padding
  = 0x00706f6f6c5f6574685f30310000000000000000000000000000000000000000
  = 198655969066724116100767858592150160576042375226781091767425152450098626560
```

For a label of at most 31 bytes:

```text
F = uint256(D) >> 8
```

The adapter implements this in `_poolIdField`:

```solidity
uint256 raw = uint256(poolId);
if (raw == 0 || uint8(raw) != 0) return (false, 0);
return (true, raw >> 8);
```

`VeilPoolPoseidon.createPool` also rejects a pool ID with a non-zero low byte so
a pool cannot be created with an ID the adapter will always reject. It also
rejects a zero top byte: right-padded ASCII labels start with a non-zero byte,
while the circuit's zero-prefixed field `F` starts with `0x00`. That catches the
common mistake of passing `F` where the deploy label `D` is required.

**Important:** the contract takes the deploy label `D`, not the circuit field
`F`. The circuit receives `F` from the adapter. The end-to-end test uses
`POOL_ID_LABEL = MembershipFixture.POOL_ID_LABEL` (which is
`bytes32("pool_eth_01")`), asserts `uint256(D) >> 8 == F` in
`test_PoolLabelMapsToFixtureField`, and asserts that creating a pool with the
zero-prefixed field `F` is rejected in
`test_CreatePoolRejectsZeroPrefixedCircuitField`.

### 5.3 Limitations

- Only the **right-padded ASCII** convention is supported. A keccak-derived ID,
  a 32-byte label, or any label with a non-zero low byte is rejected; it is
  never silently truncated.
- The adapter cannot distinguish trailing padding from embedded NUL bytes. The
  client/API encoder must reject U+0000 in the label.
- Labels must be 1..31 UTF-8 bytes. The API/indexer/deploy script must use the
  same encoder; today the API still has legacy ID lengths in places. This is a
  migration blocker.
- `F = D >> 8` is only valid for this convention. Do not apply it to arbitrary
  bytes32 values.

---

## 6. Domain tags and Poseidon arities

Tags are ASCII strings interpreted as big-endian field elements. They are
constants, not secrets.

| Tag | ASCII | Hex | Used by |
| --- | --- | --- | --- |
| `DOMAIN_COMMITMENT` | `veilpool-commit-v1` | `0x7665696c706f6f6c2d636f6d6d69742d7631` | `Poseidon(6)` commitment |
| `DOMAIN_NULLIFIER` | `veilpool-null-v1` | `0x7665696c706f6f6c2d6e756c6c2d7631` | `Poseidon(5)` nullifier |
| `DOMAIN_NODE` | `veilpool-merkle-v1` | `0x7665696c706f6f6c2d6d65726b6c652d7631` | `Poseidon(3)` Merkle node |

Arities (circomlib 2.0.5):

| Circuit call | Inputs | State width `t` | Partial rounds | Solidity |
| --- | --- | --- | --- | --- |
| `Poseidon(3)` | 3 | 4 | 56 | `Poseidon.hash3` |
| `Poseidon(5)` | 5 | 6 | 60 | `Poseidon.hash5` |
| `Poseidon(6)` | 6 | 7 | 63 | `Poseidon.hash6` |

Empty subtree rule:

```text
zero[0] = 0
zero[i+1] = Poseidon(DOMAIN_NODE, zero[i], zero[i])   for i = 0..19
```

The pool stores `_zeroHashes[level]` with exactly this rule. The fixture's
`zero[20]` is `0x0fd9d3d50b55038e3b12c1a8a26f8e733126640d1bca294b5f7517a14eddcefa`;
the pool's initial root matches it.

The Solidity implementation is a **reference loop**, not the optimized
circomlib partial-round formulation:

```text
state = [0, inputs...]
for each round:
  state[i] += C[round * t + i]
  state[i] = state[i]^5   (full round, or only state[0] in a partial round)
  state = M * state
output = state[0]
```

It is generated from `circomlibjs/src/poseidon_constants.json`. The generator
embeds the constants as `bytes` blobs and reads them with `_word`. It was
verified against circomlibjs for:

- `Poseidon(DOMAIN_NODE, 0, 0)` = `zero[1]`;
- `Poseidon(DOMAIN_NODE, 1, 2)`;
- the fixture's `Poseidon(5)` nullifier;
- the fixture's `Poseidon(6)` commitment;
- the full 20-level zero chain and the eight-leaf tree root.

The constants JSON SHA-256 is recorded in the generated header:
`354f31bbed9d9a8b884d8f2181e339cb425b6e3e4cc7240bd3dd22f0070f3f2c`.
This is provenance, not an audit.

---

## 7. Proof encoding

`IVerifier` receives opaque `bytes`. This spike uses exactly 256 bytes:

```text
proof = abi.encode(
    uint256[2] pA,
    uint256[2][2] pB,
    uint256[2] pC
)
```

- `pA = [pi_a[0], pi_a[1]]`
- `pB = [[pi_b[0][1], pi_b[0][0]], [pi_b[1][1], pi_b[1][0]]]`
- `pC = [pi_c[0], pi_c[1]]`

`pB` uses **snarkjs `soliditycalldata` order**, not the nested order in
`proof.json`. The fixture generator cross-checks its output against
`snarkjs zkey export soliditycalldata` and fails if the arrays differ.

The adapter:

- checks `proof.length == 256` before decoding;
- decodes fixed-size arrays only after the length check;
- returns `false` for wrong lengths, non-canonical fields, non-canonical pool
  IDs and proof points the verifier rejects;
- never reverts on a bad proof.

`abi.decode` of exactly 256 bytes into `uint256[2]`, `uint256[2][2]`,
`uint256[2]` has no dynamic-length ambiguity. A 160-byte `MockVerifier` proof is
rejected by the length check.

Note: an invalid BN254 curve point can make the pairing precompile consume all
forwarded gas before returning failure. The adapter still returns `false`; the
test `test_RejectsTamperedProofOnChain` exercises this and reports an unusually
large test-only gas number because of the precompile behavior.

---

## 8. Fixture and trusted setup

### 8.1 Fixture values

| Field | Value |
| --- | --- |
| `chain_id` | `11155111` (Sepolia) |
| `pool_id_text` | `pool_eth_01` |
| deploy label `D` | `0x706f6f6c5f6574685f3031000000000000000000000000000000000000000000` |
| circuit field `F` | `0x00706f6f6c5f6574685f30310000000000000000000000000000000000000000` |
| denomination | `100000000000000000` wei (0.1 ETH) |
| commitment | `0x2a829d48f48ff29616eb89685dc388a139f999cf858bd12e18a68f03e713ad02` |
| nullifier | `0x1bd4b483b8383cc27ccbbca529064dd29c4207a7e28832b3c0781d4cd84eae0b` |
| root | `0x2145dfa5869ae142af6de0e91ea20be3100f93e76a6f2d279e520b1db1b329bb` |
| leaf index | `5` |
| leaves | 8 leaves, listed in `circuits/test-vectors/membership-v1.json` and `contracts/test/fixtures/MembershipFixture.sol` |
| recipient | `0x000000000000000000000000000000000000dead` |
| fee | `100000000000000` wei (0.0001 ETH) |

The end-to-end test creates the pool with the **deploy label** `D`
(`bytes32("pool_eth_01")`), not with the zero-prefixed circuit field `F`. The
adapter converts `D` to `F`; see §5.

After depositing the eight leaves in order, `VeilPoolPoseidon.currentRoot`
equals the fixture root exactly. This is asserted by
`test_EightFixtureDepositsReproduceRoot`.

### 8.2 Development trusted setup

The recorded run used a local `bn128` Powers of Tau at 2^14, one local phase-1
contribution, `groth16 setup`, and one local phase-2 contribution
(`membership_0001.zkey`). This is a development setup, not a ceremony:

- one machine and one entropy source;
- no independent contributors;
- no public transcript;
- no auditable toxic-waste destruction.

Anyone who can recover the toxic waste can forge proofs for this circuit. Do not
reuse the zkey, verifier or proof with real funds.

### 8.3 Stale generated verifier (important finding)

The `circuits/build/Verifier.sol` that existed when this spike started did **not**
match `circuits/build/membership_0001.zkey` or
`circuits/build/verification_key.json`. The mismatch was in the verifier's
embedded key constants, including:

| Constant | Stale `Verifier.sol` | Final `verification_key.json` / zkey |
| --- | --- | --- |
| `IC0x` | `17803973505119712150992161627743937816492602593344606767889476247092289023854` | `16759143518793367648509993944101492111531216540347129964365942025916433080906` |
| `IC0y` | `20393333158116140860305914286629882924398182453771337111980120055811463334968` | `10578669868095332259568772677141474589460170292973852333169907600823457708351` |
| `deltax1` | `10280651484169373879079980983158080781560193742197006906350220981005152156005` | `11313586929697430779256594003685890876635553956570720346659699097352790228914` |
| `deltax2` | `16647425822568293328812558992622703683316963211532804382458650970607382292758` | `18756110298548996319979123092166843054683488243518120598066413464821216378648` |
| `deltay1` | `6488623050081286892928770092840203803837368199708511801872255761293801294177` | `3836209932654227224071378518940299843891583719083905638027792463651075069617` |
| `deltay2` | `20124898344601103439737915028164960526766689799303289100554148735342471034575` | `4166776921318206519281669712811405234285652035695700475419270009883179927658` |

The first full test run after wiring the adapter therefore failed the pairing
check (`InvalidProof`): 47 tests passed, 6 failed. The off-chain
`snarkjs groth16 verify` was `OK!`, which pointed at the generated Solidity key,
not the proof.

Fix: export the verifier from the final zkey and use that file:

```powershell
Set-Location G:\Worker-Space\VeilLab\circuits
node node_modules/snarkjs/build/cli.cjs zkey export solidityverifier `
  build/membership_0001.zkey build/Verifier.sol
```

The stale file was preserved as `circuits/build/Verifier.stale.sol`. The
regenerated file was copied to
`contracts/src/verifiers/Groth16Verifier.sol` and the GPL-3.0 header plus the
spike warning were retained. After this fix the real proof is accepted on-chain.

This is exactly the key-pinning failure mode described in the circuit spec:
always export the verifier from the final zkey and publish its hash. Never
assume an existing generated verifier matches the proof.

### 8.4 Artifact hashes

SHA-256 from the recorded run:

| Artifact | SHA-256 |
| --- | --- |
| `contracts/src/Poseidon.sol` | `1d1fbf0b367d06bc7c54bcffb19a9eabc8230a614e193d85b3362edf2ddeaeee` |
| `contracts/src/verifiers/Groth16Verifier.sol` | `99ea5896995caede03bcd119af9f9a4e4375d525eb61d3db1defe0b584b46b44` |
| `contracts/test/fixtures/MembershipFixture.sol` | `3f949c6eaa37a53dc1114e6742e77ba13c821c81bbbcf0ace01265c1f4f6d78b` |
| `circuits/build/Verifier.sol` | `efe0e49ee50ab4a9340dc32562f84282af87b1356ad4d08ac57e11f1984716f6` |
| `circuits/build/Verifier.stale.sol` | `ba6cfb1afb9ef0268ab60af8eef247c3413367540b079d73de5286c2e4e86135` |
| `circuits/build/proof.json` | `91ab75513974133938fefd222a6704c092227265e1eb2a3cdbc8bd42617e874a` |
| `circuits/build/public.json` | `64475f615c67b9c8a9793f281b17de47df48371e03851eeccd95c2e3714919a9` |
| `circuits/build/verification_key.json` | `71f95a78cdfd6bb2bf562a27bc8b761ee44c342ae0c7e4ccef92fa49e29f5e0c` |
| `circuits/build/membership_0001.zkey` | `33531f51e4ae66cac54915d57f491aaa6515d5f046e2736b522ee0b2b81efd4c` |

Hashes are informational. Do not treat a hash match as an audit.

---

## 9. Tests and exact commands

### 9.1 Toolchain used

- Foundry `v1.9.0` at
  `C:\Users\15240\AppData\Local\veilpool-tools\foundry-v1.9.0\forge.exe`
- Solidity `0.8.24`
- `forge-std` cloned into `contracts/lib/forge-std` (gitignored)
- Node.js `24.22.1`
- snarkjs `0.7.6`, circomlibjs `0.1.7`, circomlib `2.0.5`
- Windows PowerShell

`contracts/foundry.toml` keeps `code_size_limit = 100_000` for the local test
runner, matching the existing project. That is **not** the EIP-170 mainnet
limit. The runtime sizes below are all under the real 24,576-byte limit.

### 9.2 Run the tests

```powershell
$Forge = "$env:LOCALAPPDATA\veilpool-tools\foundry-v1.9.0\forge.exe"
Set-Location G:\Worker-Space\VeilLab\contracts

& $Forge --version
& $Forge test -vvv

# Individual suites
& $Forge test --match-contract VeilPoolTest -vvv
& $Forge test --match-contract Groth16Test -vvv
& $Forge test --match-contract VeilPoolPoseidonTest -vvv

# Sizes and gas
& $Forge build --sizes
& $Forge test --gas-report --match-contract VeilPoolPoseidonTest
```

If `forge-std` is missing:

```powershell
Set-Location G:\Worker-Space\VeilLab
git clone https://github.com/foundry-rs/forge-std contracts/lib/forge-std
```

### 9.3 Regenerate the Solidity artifacts

```powershell
Set-Location G:\Worker-Space\VeilLab\circuits
npm.cmd install

# Poseidon constants + library
node scripts/gen-poseidon-solidity.mjs

# Proof/signals/leaves -> Solidity fixture
node scripts/gen-solidity-fixture.mjs

# Only after a new final zkey: export the verifier, then copy it to
# contracts/src/verifiers/Groth16Verifier.sol and re-add the spike warning header.
node node_modules/snarkjs/build/cli.cjs zkey export solidityverifier `
  build/membership_0001.zkey build/Verifier.sol
```

`gen-poseidon-solidity.mjs` writes `contracts/src/Poseidon.sol`.
`gen-solidity-fixture.mjs` writes
`contracts/test/fixtures/MembershipFixture.sol` and cross-checks the proof
against `snarkjs zkey export soliditycalldata`.

After regeneration, run `forge fmt` in `contracts/` so the generated files match
the repository's `forge fmt --check` gate. The generated verifier also needs the
spike warning header restored after a fresh `zkey export solidityverifier`.

### 9.3.1 Local chain-31337 proof

The static fixture is bound to Sepolia (`11155111`). For a fresh local pool, generate a
single-leaf proof bound to Anvil:

```powershell
Set-Location circuits
node scripts/gen-local-fixture.mjs
node node_modules/snarkjs/build/cli.cjs wtns calculate `
  build/membership_js/membership.wasm build/local-input.json build/local.wtns
node node_modules/snarkjs/build/cli.cjs groth16 prove `
  build/membership_0001.zkey build/local.wtns build/local-proof.json build/local-public.json
node node_modules/snarkjs/build/cli.cjs groth16 verify `
  build/verification_key.json build/local-public.json build/local-proof.json
node scripts/export-local-proof.mjs
```

`build/local-proof-hex.json` contains the 256-byte ABI proof and the six public signals. The
default note commitment is
`0x15ea983a3ab585b6c1eb9651591cdd00a4d664a209c0d40b054a30205c50f079`; deposit it as leaf 0
of a fresh 0.1 ETH Poseidon pool. The root/nullifier/recipient/fee are in
`build/local-expected.json`. Environment variables can override chain ID, pool label,
denomination, fee and recipient before generation.

`DeployPoseidon.s.sol` creates a maturity-0 local proof pool. That is a spike setting, not a
product default.

### 9.4 Recorded result

```text
Ran 3 test suites: 53 tests passed, 0 failed, 0 skipped (53 total tests)

VeilPoolTest             22 passed
Groth16Test              17 passed
VeilPoolPoseidonTest     14 passed
```

Key passing checks:

- `test_FixtureProofAccepted`: the real `proof.json` is accepted by
  `Groth16VerifierAdapter` on the EVM.
- The pool is created with `bytes32("pool_eth_01")` (deploy label `D`), **not**
  the fixture's zero-prefixed field `F`. `test_PoolLabelMapsToFixtureField`
  asserts `uint256(D) >> 8 == F`, and
  `test_CreatePoolRejectsZeroPrefixedCircuitField` asserts that creating a pool
  with `F` is rejected.
- `test_WithdrawWithRealProof`: eight fixture deposits recreate the root, the
  proof is verified, and the recipient/relayer are paid.
- `test_ReplayRevertsAfterRealWithdrawal`: replay reverts with
  `NullifierAlreadySpent`.
- `test_EightFixtureDepositsReproduceRoot`: root equals
  `0x2145dfa5869ae142af6de0e91ea20be3100f93e76a6f2d279e520b1db1b329bb`.
- `test_PoseidonMatchesCircomlibVectors`: `hash3`, `hash5` and `hash6` match
  the circomlibjs fixture values.
- `snarkjs groth16 verify build/verification_key.json build/public.json
  build/proof.json` prints `OK!`.

### 9.4.1 Browser proof E2E

The full local browser flow passed:

1. Generate a Poseidon note v2 in the web app.
2. Deposit through `POST /api/v1/local/deposits` into a fresh maturity-0 pool.
3. Fetch the depth-20 path through the API proxy.
4. Prove with snarkjs in a Web Worker and verify locally.
5. Submit only the 256-byte proof and public signals to
   `POST /api/v1/local/withdrawals`.

Recorded Playwright run: **5.9 s total** for deposit + quote + proof + withdrawal, tx
`0x3f332a1139a192ae2ad9b2f7c558cd9f37674d5ce41b9308f99f9208a2002460`, block 18. The spec
asserts that no `veilnote2`, secret, nullifier-secret or witness field appears in any POST body.
This is a test runtime, not a production performance benchmark.

### 9.5 Gas and sizes

`forge test --gas-report --match-contract VeilPoolPoseidonTest` (recorded run):

| Contract / function | Gas |
| --- | --- |
| `Groth16VerifierAdapter` deployment | `845,307` |
| `Groth16VerifierAdapter.verifyProof` | `229,992` |
| `Groth16Verifier.verifyProof` (generated) | `222,161` |
| `VeilPoolPoseidon` deployment | `17,952,011` |
| `VeilPoolPoseidon.deposit` (successful, typical) | ~`14,170,000` |
| `VeilPoolPoseidon.deposit` (gas-report average over 49 calls incl. reverts) | `13,935,920` |
| `VeilPoolPoseidon.withdraw` (real proof, successful) | `275,477` |
| `VeilPoolPoseidon.withdraw` (gas-report median / max) | `275,477` / `342,212` |

`forge build --sizes` runtime sizes:

| Contract | Runtime size | Initcode size |
| --- | --- | --- |
| `Groth16Verifier` | `1,816` B | `1,845` B |
| `Groth16VerifierAdapter` | `1,694` B | `3,653` B |
| `VeilPool` (unchanged) | `6,004` B | `6,448` B |
| `VeilPoolPoseidon` | `15,864` B | `25,881` B |

All runtime sizes are below the 24,576-byte EIP-170 limit. Deployment of
`VeilPoolPoseidon` is expensive because its constructor computes the 20 empty
subtree roots with the reference Poseidon loop. The deposit cost is dominated by
20 reference Poseidon hashes; see the gas blocker below.

### 9.6 Compile warnings

`forge build` completed successfully with **no Solidity compiler warnings**.
Forge's linter reports warnings, mostly inherited or expected:

- `unsafe-typecast` on the deliberate `uint8(raw)` low-byte check in the adapter;
- `reentrancy-eth`, `reentrancy-events`, `arbitrary-send-eth` and
  `block-timestamp` in `VeilPool` / `VeilPoolPoseidon` (the same state machine
  and transfer pattern as the existing MVP);
- `inconsistent-type-names` in the generated GPL verifier (`uint` shorthand).

These are lint findings, not compile failures. The new files pass
`forge fmt --check`.

---

## 10. What is real vs mock

| Path | Status |
| --- | --- |
| `VeilPool.sol` + `MockVerifier.sol` | **Default shipped demo path.** Mock verifier, no cryptography, keccak tree. Unchanged. |
| `contracts/script/Deploy.s.sol` | Still deploys `MockVerifier` + `VeilPool` on local Anvil. Unchanged. |
| `VeilPoolPoseidon` + adapter + generated verifier | **Local spike path.** Real EVM proof verification and real Poseidon root. Not the default demo. |
| `apps/`, `prototype/`, existing docs | Not touched by this spike. |
| Circuit and proof | Real circuit/proof; development trusted setup. |
| Production ceremony / audit | **Not done.** |
| Web/API/indexer integration | **Not done.** |
| Mainnet/testnet deployment | **Not done.** No broadcast, no RPC, no keys. |

The default `VeilPool` + `MockVerifier` remains the shipped demo path exactly
because the spike is not production-ready. Do not switch the demo to the
Poseidon pool without a ceremony, audit and client/indexer migration.

---

## 11. Remaining blockers

1. **Trusted setup ceremony.** Replace the single-machine development zkey with
   a multi-party phase-1 and circuit-specific phase-2 ceremony. Publish
   contribution hashes, the final zkey hash and the verification key hash.
2. **Audit.** Audit the circuit, Poseidon constants/implementation, adapter,
   pool changes, generated verifier and deployment process. No audit exists.
3. **Verifier key pinning.** Export the verifier from the final zkey, publish its
   hash, and keep the verifier immutable. The stale-verifier incident in §8.3
   shows why this is not optional.
4. **Deploy script update.** `contracts/script/DeployPoseidon.s.sol` and
   `DepositFixture.s.sol` now exist for the local spike; keep the mock
   `Deploy.s.sol` path documented as the shipped demo. Do not add a mainnet path.
5. **Web/API/indexer integration.** The API and indexer now support the path
   proxy and the dev-only withdrawal bridge, and the web has circuit-compatible
   note v2 plus a Web Worker Groth16 prover. A full local browser E2E
   (note → deposit → proof → withdrawal) passed; the development zkey remains
   the blocking production issue.
6. **Gas.** The reference Poseidon loop makes a successful deposit cost about
   14.2M gas and pool deployment about 17.9M gas. The optimized
   `poseidon-solidity` T4 benchmark is roughly 37.6k gas per 3-input hash
   versus this reference loop's much higher cost. Replace `Poseidon.sol` with an
   audited optimized implementation (or optimize the generated code) and
   re-measure on the target chain. Withdrawal with the real verifier is
   ~275k gas; the adapter is ~230k.
7. **Poseidon constant provenance and review.** The implementation is generated
   from circomlibjs 2.0.5 constants and cross-checked against the fixture, but
   the constants and the loop implementation have not been independently
   reviewed. The Poseidon parameters are a cryptographic assumption.
8. **Canonical encodings and ranges.** The pool ID convention is spike-only and
   incompatible with arbitrary/keccak IDs. Commitment values `>= p` are
   rejected, pool denominations must fit `uint64`, fees must fit `uint64`, and
   `block.chainid` must fit `uint64`. The API, deploy script, note parser and
   indexer must all enforce the same rules.
9. **Anonymity analysis.** Fixed denominations reduce amount fingerprinting, but
   timing, recipient reuse, relayer metadata, withdrawal events and deposit
   graph analysis remain. This spike provides **no anonymity claim**.
10. **No production or public-network deployment.** Local/testnet only. No
    mainnet RPC, no broadcast, no real keys. `MockVerifier` and the development
    zkey must never be used with real funds.
11. **No proof of deposit / note encryption / relayer changes.** These remain
    out of scope, as in the circuit spike.
12. **No migration of existing pools.** `VeilPoolPoseidon` is a new contract with
    new Poseidon roots. Existing keccak pools and their roots cannot be reused.

---

## 12. Explicit non-claims

This spike does **not** provide:

- production security;
- anonymity or privacy guarantees;
- a secure trusted setup;
- an audited circuit, verifier, adapter, Poseidon implementation or pool;
- a mainnet-ready deployment;
- a browser/WASM proving benchmark;
- a deployed API/indexer/client integration;
- a claim that the default `VeilPool` + `MockVerifier` demo verifies real
  proofs. It does not.

It provides one thing: a local, reproducible end-to-end proof that the existing
depth-20 Poseidon/Groth16 membership proof can be verified by an EVM contract
against a Poseidon root built by an on-chain pool, with the fixture root
reproduced exactly and the real proof accepted.
