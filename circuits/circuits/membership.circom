pragma circom 2.1.0;

// VeilPool membership circuit spike.
//
// TESTNET / SPIKE ONLY. This file is not audited and must not be used with real funds.
//
// Hash choice: Poseidon over BN254 (circomlib 2.0.5). Poseidon is used because a
// depth-20 Poseidon Merkle path is practical to prove in a browser, whereas a
// keccak256 path would be orders of magnitude larger. The current on-chain
// VeilPool tree uses keccak256, so it is NOT compatible with this circuit; see
// docs/veilpool/ZK_CIRCUIT_SPEC.md, section "Contract integration gap".
//
// Public signals, in this exact order:
//   0 chain_id
//   1 pool_id
//   2 root
//   3 nullifier
//   4 recipient
//   5 fee
//
// All public inputs are also witness inputs. The circuit constrains them to the
// values derived from the private note and Merkle path.

include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/bitify.circom";
include "circomlib/circuits/comparators.circom";

// Domain tags are ASCII strings encoded as big-endian integers. They are public
// constants, not secrets. Changing any tag is a circuit-version change.
//   "veilpool-commit-v1"  = 0x7665696c706f6f6c2d636f6d6d69742d7631
//   "veilpool-null-v1"    = 0x7665696c706f6f6c2d6e756c6c2d7631
//   "veilpool-merkle-v1"  = 0x7665696c706f6f6c2d6d65726b6c652d7631
//
// The note-format checksum uses a different domain string ("veilpool-note-v1")
// and SHA-256; it is not the commitment domain.
//
// The BN254 scalar field modulus is
//   21888242871839275222246405745257275088548364400416034343698204186575808495617
// All public values must be canonical field elements. In particular:
//   - pool_id MUST be < 2^248 (top byte zero), so the on-chain bytes32 pool ID
//     can be mapped to a field element without truncation;
//   - root and nullifier are Poseidon outputs, therefore < p;
//   - recipient is an address, therefore < 2^160;
//   - fee, chain_id and denomination are range-checked to < 2^64.

// Computes root = Merkle(leaf, pathElements, pathIndices) with
// node = Poseidon(DOMAIN_NODE, left, right) and depth levels.
template PoseidonMerkle(depth) {
    signal input leaf;
    signal input pathElements[depth];
    signal input pathIndices[depth];
    signal output root;

    var DOMAIN_NODE = 0x7665696c706f6f6c2d6d65726b6c652d7631;

    signal current[depth + 1];
    current[0] <== leaf;

    component hashes[depth];
    for (var i = 0; i < depth; i++) {
        // A path index is a bit. Anything else is rejected by the witness.
        pathIndices[i] * (pathIndices[i] - 1) === 0;

        // index 0: current is the left child; index 1: current is the right child.
        hashes[i] = Poseidon(3);
        hashes[i].inputs[0] <== DOMAIN_NODE;
        hashes[i].inputs[1] <== current[i] + pathIndices[i] * (pathElements[i] - current[i]);
        hashes[i].inputs[2] <== pathElements[i] + pathIndices[i] * (current[i] - pathElements[i]);
        current[i + 1] <== hashes[i].out;
    }

    root <== current[depth];
}

// The withdrawal membership statement.
//
// Private witness:
//   secret, nullifier_secret, denomination, pathElements[20], pathIndices[20]
//
// Constraints:
//   commitment = Poseidon(DOMAIN_COMMITMENT, chain_id, pool_id, denomination,
//                         secret, nullifier_secret)
//   nullifier  = Poseidon(DOMAIN_NULLIFIER, chain_id, pool_id, commitment,
//                         nullifier_secret)
//   root       = PoseidonMerkle(commitment, pathElements, pathIndices)
//
// The recipient and fee are public inputs and are not otherwise interpreted by
// the circuit. Binding them to the proof is the verifier's job.
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

    var DOMAIN_COMMITMENT = 0x7665696c706f6f6c2d636f6d6d69742d7631;
    var DOMAIN_NULLIFIER = 0x7665696c706f6f6c2d6e756c6c2d7631;

    // --- Canonical encoding / range checks ---------------------------------
    // These keep every public signal inside the range the ABI can encode
    // without truncation and inside the BN254 scalar field.
    component chainIdBits = Num2Bits(64);
    chainIdBits.in <== chain_id;

    component poolIdBits = Num2Bits(248);
    poolIdBits.in <== pool_id;

    component recipientBits = Num2Bits(160);
    recipientBits.in <== recipient;

    component feeBits = Num2Bits(64);
    feeBits.in <== fee;

    component denominationBits = Num2Bits(64);
    denominationBits.in <== denomination;

    component denominationIsZero = IsZero();
    denominationIsZero.in <== denomination;
    denominationIsZero.out === 0;

    // --- Commitment ---------------------------------------------------------
    component commitmentHash = Poseidon(6);
    commitmentHash.inputs[0] <== DOMAIN_COMMITMENT;
    commitmentHash.inputs[1] <== chain_id;
    commitmentHash.inputs[2] <== pool_id;
    commitmentHash.inputs[3] <== denomination;
    commitmentHash.inputs[4] <== secret;
    commitmentHash.inputs[5] <== nullifier_secret;

    signal commitment;
    commitment <== commitmentHash.out;

    // The contract rejects a zero commitment on deposit; mirror that here.
    component commitmentIsZero = IsZero();
    commitmentIsZero.in <== commitment;
    commitmentIsZero.out === 0;

    // --- Nullifier ----------------------------------------------------------
    // Binding the commitment into the nullifier makes the nullifier unique per
    // note, not merely per nullifier_secret. chain_id and pool_id prevent
    // cross-chain and cross-pool replay.
    component nullifierHash = Poseidon(5);
    nullifierHash.inputs[0] <== DOMAIN_NULLIFIER;
    nullifierHash.inputs[1] <== chain_id;
    nullifierHash.inputs[2] <== pool_id;
    nullifierHash.inputs[3] <== commitment;
    nullifierHash.inputs[4] <== nullifier_secret;

    nullifierHash.out === nullifier;

    // --- Merkle membership --------------------------------------------------
    component merkle = PoseidonMerkle(depth);
    merkle.leaf <== commitment;
    for (var i = 0; i < depth; i++) {
        merkle.pathElements[i] <== pathElements[i];
        merkle.pathIndices[i] <== pathIndices[i];
    }
    merkle.root === root;
}

component main {public [chain_id, pool_id, root, nullifier, recipient, fee]} = Membership(20);
