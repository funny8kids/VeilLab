// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

/// @title IVerifier
/// @notice Verifies the public signals of a VeilPool withdrawal proof.
/// @dev The production implementation is expected to verify a zero-knowledge membership
///      proof. The MVP ships a non-cryptographic mock implementation; see MockVerifier.sol.
interface IVerifier {
    /// @notice Verify a withdrawal proof against its public signals.
    /// @param proof Opaque proof bytes. The encoding is verifier-versioned.
    /// @param root Merkle root the proof is valid against.
    /// @param nullifier Nullifier derived from the note and pool domain.
    /// @param recipient Address that receives the withdrawn denomination minus fees.
    /// @param relayerFee Fee paid to the transaction submitter, in wei.
    /// @param poolId Pool identifier the proof is bound to.
    /// @return True only when the proof is valid for every supplied public signal.
    function verifyProof(
        bytes calldata proof,
        bytes32 root,
        bytes32 nullifier,
        address recipient,
        uint256 relayerFee,
        bytes32 poolId
    ) external view returns (bool);
}
