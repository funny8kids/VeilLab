// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {IVerifier} from "./IVerifier.sol";
import {Groth16Verifier} from "./verifiers/Groth16Verifier.sol";

/// @title Groth16VerifierAdapter
/// @notice LOCAL SPIKE ONLY: adapts the six-signal Groth16 membership circuit to IVerifier.
/// @dev SECURITY WARNING
///      This adapter is a local integration spike. The generated Groth16 verifier was
///      produced from a single-machine development zkey, not from a multi-party
///      ceremony. The circuit, Poseidon implementation and this adapter are not
///      audited. Do not use this contract with real funds or make a production
///      security/anonymity claim from it.
///
///      Circuit public signals, in this exact order:
///        [chain_id, pool_id, root, nullifier, recipient, fee]
///
///      - chain_id is injected from block.chainid; it is never caller-supplied.
///      - pool_id is derived from the bytes32 deploy label with the canonical
///        right-padded ASCII convention documented below.
///      - root and nullifier must be canonical BN254 field elements.
///      - recipient is a Solidity address, so it is already < 2^160.
///      - fee is relayerFee and must fit the circuit's uint64 range.
///
///      Proof encoding (256 bytes):
///        abi.encode(uint256[2] pA, uint256[2][2] pB, uint256[2] pC)
///      using snarkjs "soliditycalldata" order for pB. Malformed input returns
///      false; the adapter never reverts on a bad proof.
contract Groth16VerifierAdapter is IVerifier {
    /// @notice BN254 scalar field modulus r.
    uint256 public constant FIELD_MODULUS =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;
    /// @notice Exact ABI-encoded Groth16 proof length.
    uint256 public constant PROOF_LENGTH = 256;
    /// @notice Label identifying the verifier/circuit pair.
    string public constant VERIFIER_KIND = "groth16-poseidon-membership-v1";

    /// @notice Generated verifier for the development zkey. Immutable by construction.
    Groth16Verifier public immutable groth16Verifier;

    /// @dev Deploys the generated verifier so tests and local deployments have a
    ///      self-contained adapter. A production deployment should normally pass
    ///      an independently reviewed verifier address instead.
    constructor() {
        groth16Verifier = new Groth16Verifier();
    }

    /// @inheritdoc IVerifier
    function verifyProof(
        bytes calldata proof,
        bytes32 root,
        bytes32 nullifier,
        address recipient,
        uint256 relayerFee,
        bytes32 poolId
    ) external view override returns (bool) {
        if (proof.length != PROOF_LENGTH) return false;

        // Circuit range checks. Public signals must be canonical field elements.
        if (block.chainid > type(uint64).max) return false;
        if (relayerFee > type(uint64).max) return false;
        if (uint256(root) >= FIELD_MODULUS) return false;
        if (uint256(nullifier) >= FIELD_MODULUS) return false;

        (bool poolOk, uint256 poolField) = _poolIdField(poolId);
        if (!poolOk) return false;

        (uint256[2] memory pA, uint256[2][2] memory pB, uint256[2] memory pC) =
            abi.decode(proof, (uint256[2], uint256[2][2], uint256[2]));

        uint256[6] memory publicSignals = [
            block.chainid,
            poolField,
            uint256(root),
            uint256(nullifier),
            uint256(uint160(recipient)),
            relayerFee
        ];

        return groth16Verifier.verifyProof(pA, pB, pC, publicSignals);
    }

    /// @notice Converts a bytes32 deploy label to the circuit's pool_id field.
    /// @dev POOL ID CONVENTION (spike-only):
    ///
    ///      The deploy scripts use right-padded ASCII labels, e.g.
    ///      bytes32("pool_eth_01") =
    ///        0x706f6f6c5f6574685f303100...00.
    ///
    ///      The circuit uses the canonical zero-prefixed encoding:
    ///        0x00 || UTF-8(label) || zero padding.
    ///
    ///      For labels of at most 31 bytes, the circuit's field value is
    ///      uint256(deployLabel) >> 8. This function returns false unless the
    ///      low byte of the deploy label is zero (so the shift is a pure
    ///      de-padding) and the label is non-zero.
    ///
    ///      LIMITATIONS: this cannot distinguish padding from embedded NUL
    ///      bytes, and it only supports the right-padded ASCII convention. A
    ///      keccak-derived ID, a 32-byte label, or any label whose low byte is
    ///      non-zero is rejected rather than silently truncated. The canonical
    ///      encoder must reject labels longer than 31 UTF-8 bytes and labels
    ///      containing U+0000 before creating a pool.
    /// @param poolId Right-padded ASCII bytes32 pool label.
    /// @return ok True when the label is non-zero and has a zero low byte.
    /// @return field Circuit pool_id field value when ok is true; otherwise 0.
    function poolIdField(bytes32 poolId) external pure returns (bool ok, uint256 field) {
        return _poolIdField(poolId);
    }

    function _poolIdField(bytes32 poolId) internal pure returns (bool ok, uint256 field) {
        uint256 raw = uint256(poolId);
        if (raw == 0 || uint8(raw) != 0) {
            return (false, 0);
        }
        return (true, raw >> 8);
    }
}
