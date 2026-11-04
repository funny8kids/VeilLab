# VeilPool Circuits

**Status:** local spike, testnet-only, not audited, not integrated.
**Spec:** [`../docs/veilpool/ZK_CIRCUIT_SPEC.md`](../docs/veilpool/ZK_CIRCUIT_SPEC.md)

This directory contains a minimal Groth16/Poseidon membership circuit spike for
VeilPool. It exists to answer three narrow questions:

1. Can a depth-20 Poseidon membership statement be expressed and compiled with
   circom + circomlib?
2. Can a deterministic fixture be witnessed, proved and verified locally?
3. Does tampering with any public signal or witness input fail as expected?

It does **not** claim production security, anonymity, browser performance, or
that the current contracts can verify this proof. In particular:

- The current `MockVerifier` is **not cryptography**. It accepts a correctly
  encoded copy of the public signals and proves nothing.
- The current `VeilPool.sol` Merkle tree uses `keccak256`, while this circuit
  uses Poseidon. They are **not compatible**. See the integration gap in the
  spec before wiring anything together.
- The trusted setup used here is a single-machine development setup. It is
  insecure by construction and must not be used for real value.

## Layout

```text
circuits/
  circuits/membership.circom       depth-20 membership circuit
  scripts/gen-fixture.mjs          deterministic note + tree + public signals
  scripts/canonicalize.mjs         RFC 8785-style canonical fixture + SHA-256
  scripts/verify-negative.mjs      tampered public signal / proof checks
  scripts/witness-negative.mjs     malformed witness checks
  test-vectors/membership-v1.json  readable fixture
  test-vectors/membership-v1.canonical.json
  test-vectors/membership-v1.canonical.sha256
  test-vectors/negative-cases.json  negative-case manifest
```

`node_modules/` and `build/` are not committed. The Circom compiler is not
vendored; install it as shown below.

## Toolchain tested

| Tool | Version | Notes |
| --- | --- | --- |
| Node.js | 24.22.1 | tested with npm 11.19.1 |
| circom | 2.2.3 | prebuilt Windows binary used for the recorded run |
| snarkjs | 0.7.6 | npm dependency |
| circomlib | 2.0.5 | npm dependency |
| circomlibjs | 0.1.7 | npm dependency; generates fixture values |
| Powers of Tau | local `bn128`, 2^14 | development only, one contribution |

The circuit has 6,623 non-linear constraints and 14,569 total constraints
(depth 20, six public inputs, 43 private inputs, zero public outputs).

## Install

```powershell
cd circuits
npm.cmd install
```

Install Circom 2.2.3. The prebuilt Windows binary is the tested route:

```powershell
$CircomDir = "$env:LOCALAPPDATA\veilpool-tools\circom-2.2.3"
New-Item -ItemType Directory -Force $CircomDir | Out-Null
curl.exe -sSL `
  "https://github.com/iden3/circom/releases/download/v2.2.3/circom-windows-amd64.exe" `
  -o "$CircomDir\circom.exe"
& "$CircomDir\circom.exe" --version
```

Other platforms can use the matching `circom-*` release asset, or build from
source. Those routes were not tested for this report. If `circom` is already on
`PATH`, set `$Circom = "circom"` instead of the full path below.

## Compile and witness

```powershell
$Circom = "$env:LOCALAPPDATA\veilpool-tools\circom-2.2.3\circom.exe"
New-Item -ItemType Directory -Force build | Out-Null

& $Circom circuits/membership.circom --r1cs --wasm --sym -l node_modules -o build

node scripts/gen-fixture.mjs
node node_modules/snarkjs/build/cli.cjs wtns calculate `
  build/membership_js/membership.wasm build/input.json build/witness.wtns
node node_modules/snarkjs/build/cli.cjs wtns check `
  build/membership.r1cs build/witness.wtns
```

`build/input.json` contains the note secrets. It is witness material: do not
send it to a server, attach it to an issue, or commit it.

## Development trusted setup

> **Insecure by construction.** A single local contribution has no
> independence and its toxic waste is not destroyed in any auditable way. This
> is only for a local spike.

```powershell
node node_modules/snarkjs/build/cli.cjs powersoftau new bn128 14 build/pot14_0000.ptau -v
node node_modules/snarkjs/build/cli.cjs powersoftau contribute `
  build/pot14_0000.ptau build/pot14_0001.ptau `
  --name="veilpool-spike-dev" -e="<high-entropy-dev-value>" -v
node node_modules/snarkjs/build/cli.cjs powersoftau prepare phase2 `
  build/pot14_0001.ptau build/pot14_final.ptau -v

node node_modules/snarkjs/build/cli.cjs groth16 setup `
  build/membership.r1cs build/pot14_final.ptau build/membership_0000.zkey
node node_modules/snarkjs/build/cli.cjs zkey contribute `
  build/membership_0000.zkey build/membership_0001.zkey `
  --name="veilpool-spike-dev" -e="<high-entropy-dev-value>" -v
node node_modules/snarkjs/build/cli.cjs zkey export verificationkey `
  build/membership_0001.zkey build/verification_key.json
```

Do not reuse these artifacts. Changing the circuit, a domain tag, the tree
depth, or the hash construction requires a new setup.

## Prove, verify, negative cases

```powershell
node node_modules/snarkjs/build/cli.cjs groth16 prove `
  build/membership_0001.zkey build/witness.wtns build/proof.json build/public.json
node node_modules/snarkjs/build/cli.cjs groth16 verify `
  build/verification_key.json build/public.json build/proof.json

node scripts/verify-negative.mjs
node scripts/witness-negative.mjs
node scripts/canonicalize.mjs
```

Expected results from the recorded run:

| Check | Result |
| --- | --- |
| compile | success; 6,623 non-linear / 14,569 total constraints |
| `wtns check` | witness is correct |
| `groth16 verify` | `OK!` |
| `verify-negative.mjs` | 11/11 passed |
| `witness-negative.mjs` | 11/11 passed |
| CLI prove | ~1,112 ms (native Node CLI; not a browser measurement) |
| CLI verify | ~637 ms (native Node CLI; not a browser measurement) |
| canonical fixture SHA-256 | `599f75c3cf34663e1980c25194ea10acac3ff910b7dd75902cdfab9e9cc3ac5b` |

The timing numbers are a rough local data point only. No WASM/browser proving
benchmark was performed.

## Fixture conventions

- Field elements in `circuit_input` are **decimal strings** and must be
  canonical elements of the BN254 scalar field.
- Byte-oriented values in `note`, `derived`, `tree` and `public_signals` are
  `0x`-prefixed 32-byte lowercase hex.
- Note secrets are 32 CSPRNG bytes reduced modulo the BN254 scalar field:
  `secret_field = uint256(secret_bytes) mod p`. The fixture deliberately uses a
  raw `secret_bytes` above `p` to exercise this rule.
- `pool_id` is `0x00 || UTF-8 pool id (max 31 bytes) || zero padding`, which
  keeps it below `2^248` and therefore below `p`.
- Path bit 0 means "current node is the left child"; bit 1 means "current node
  is the right child". `pathIndices[0]` is the least significant bit of the
  leaf index.
- Merkle node hash is `Poseidon(DOMAIN_NODE, left, right)`, not `Poseidon(left,
  right)`. Empty subtree roots use the same rule.
- The canonical fixture is produced by `scripts/canonicalize.mjs` and hashed
  with SHA-256. Do not edit it by hand.

## Local single-leaf proof fixture

For a fresh local `VeilPoolPoseidon` pool, `gen-local-fixture.mjs` creates a deterministic
single-leaf note for chain 31337. It writes `build/local-input.json` (witness material, do not
commit) and `build/local-expected.json` (public commitment/root/nullifier/path).

```powershell
Set-Location circuits
node scripts/gen-local-fixture.mjs
node node_modules/snarkjs/build/cli.cjs wtns calculate `
  build/membership_js/membership.wasm build/local-input.json build/local.wtns
node node_modules/snarkjs/build/cli.cjs groth16 prove `
  build/membership_0001.zkey build/local.wtns build/local-proof.json build/local-public.json
node node_modules/snarkjs/build/cli.cjs groth16 verify `
  build/verification_key.json build/local-public.json build/local-proof.json
```

This fixture is for local API/contract integration tests. The browser prover generates a fresh
note instead.

---

## Browser artifacts

The web prover loads the wasm and final zkey from `apps/web/public/zk/`. Those files are
gitignored because they are large local development artifacts. Copy them with:

```powershell
Set-Location circuits
node scripts/export-web-artifacts.mjs
```

This copies:

- `build/membership_js/membership.wasm` → `apps/web/public/zk/membership.wasm`
- `build/membership_0001.zkey` → `apps/web/public/zk/membership.zkey`
- `build/verification_key.json` → `apps/web/public/zk/verification_key.json`

The zkey is from the single-machine development setup. Do not serve it as a production
trusted-setup artifact.

---

## What is deliberately missing

- No contract, API or web integration.
- No verifier wrapper contract and no Solidity Poseidon tree.
- No multi-party ceremony, audit, or production key management.
- No proof of deposit, no note encryption, no relayer changes.
- No anonymity analysis. Fixed denominations reduce amount fingerprinting;
  timing, recipient reuse and relayer metadata can still link users.
- No claim that the current `MockVerifier` or `VeilPool` accepts this proof.

See [`../docs/veilpool/ZK_CIRCUIT_SPEC.md`](../docs/veilpool/ZK_CIRCUIT_SPEC.md)
for the full statement, ABI, encoding, test vectors, negative cases and audit
checklist.
