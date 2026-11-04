// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {IVerifier} from "./IVerifier.sol";

/// @title MockVerifier
/// @notice MOCK VERIFIER FOR LOCAL DEMO AND TESTS ONLY.
/// @dev SECURITY WARNING
///      This contract performs NO cryptography. It does not prove Merkle membership,
///      note ownership, knowledge of a secret, or anything else. It only checks that the
///      caller supplied a correctly-encoded copy of the public signals.
///
///      Any account that can read a valid root and the public signals can construct a
///      proof this verifier accepts. Do not use this contract with real funds, on a public
///      network, or as the basis of any privacy claim. It is not production-safe.
///
///      Proof encoding (160 bytes):
///      abi.encode(bytes32 root, bytes32 nullifier, address recipient, uint256 relayerFee,
///                 bytes32 poolId)
contract MockVerifier is IVerifier {
    /// @notice Expected byte length of a mock proof.
    uint256 public constant MOCK_PROOF_LENGTH = 160;

    /// @inheritdoc IVerifier
    function verifyProof(
        bytes calldata proof,
        bytes32 root,
        bytes32 nullifier,
        address recipient,
        uint256 relayerFee,
        bytes32 poolId
    ) external pure override returns (bool) {
        if (proof.length != MOCK_PROOF_LENGTH) {
            return false;
        }

        (
            bytes32 proofRoot,
            bytes32 proofNullifier,
            address proofRecipient,
            uint256 proofRelayerFee,
            bytes32 proofPoolId
        ) = abi.decode(proof, (bytes32, bytes32, address, uint256, bytes32));

        return proofRoot == root && proofNullifier == nullifier && proofRecipient == recipient
            && proofRelayerFee == relayerFee && proofPoolId == poolId;
    }

    /// @notice Encode a mock proof for the supplied public signals.
    /// @dev Convenience helper for local demos and tests. The result is NOT a proof.
    function encodeProof(
        bytes32 root,
        bytes32 nullifier,
        address recipient,
        uint256 relayerFee,
        bytes32 poolId
    ) external pure returns (bytes memory) {
        return abi.encode(root, nullifier, recipient, relayerFee, poolId);
    }
}
