// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Groth16VerifierAdapter} from "../src/Groth16VerifierAdapter.sol";
import {MembershipFixture} from "./fixtures/MembershipFixture.sol";

/// @title Groth16Test
/// @notice LOCAL SPIKE ONLY: verifies the real fixture proof on the EVM and checks
///         that every public signal and malformed input is rejected.
contract Groth16Test is Test {
    Groth16VerifierAdapter internal adapter;

    function setUp() public {
        vm.chainId(MembershipFixture.CHAIN_ID);
        adapter = new Groth16VerifierAdapter();
    }

    function _proof() internal pure returns (bytes memory) {
        return MembershipFixture.proof();
    }

    function _verify(
        bytes memory proof,
        bytes32 root,
        bytes32 nullifier,
        address recipient,
        uint256 fee,
        bytes32 poolId
    ) internal view returns (bool) {
        return adapter.verifyProof(proof, root, nullifier, recipient, fee, poolId);
    }

    function _validProofAccepted() internal view returns (bool) {
        return _verify(
            _proof(),
            bytes32(MembershipFixture.ROOT),
            bytes32(MembershipFixture.NULLIFIER),
            MembershipFixture.RECIPIENT,
            MembershipFixture.FEE,
            MembershipFixture.POOL_ID_LABEL
        );
    }

    /* ---------------------------------------------------------------------- */
    /* Positive fixture                                                        */
    /* ---------------------------------------------------------------------- */

    function test_FixtureProofAccepted() public view {
        assertTrue(_validProofAccepted());
    }

    function test_VerifierKindIsPinned() public view {
        assertEq(adapter.VERIFIER_KIND(), "groth16-poseidon-membership-v1");
        assertEq(adapter.PROOF_LENGTH(), 256);
        assertEq(address(adapter.groth16Verifier()).code.length > 0, true);
    }

    function test_PoolIdConversionMatchesFixture() public view {
        (bool ok, uint256 field) = adapter.poolIdField(MembershipFixture.POOL_ID_LABEL);
        assertTrue(ok);
        assertEq(field, MembershipFixture.POOL_ID_FIELD);
        assertEq(uint256(MembershipFixture.POOL_ID_LABEL) >> 8, MembershipFixture.POOL_ID_FIELD);
        assertEq(uint8(uint256(MembershipFixture.POOL_ID_LABEL)), 0);
    }

    /* ---------------------------------------------------------------------- */
    /* Public-signal binding                                                   */
    /* ---------------------------------------------------------------------- */

    function test_RejectsTamperedRoot() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(MembershipFixture.ROOT + 1),
                bytes32(MembershipFixture.NULLIFIER),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsTamperedNullifier() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(MembershipFixture.ROOT),
                bytes32(MembershipFixture.NULLIFIER + 1),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsTamperedRecipient() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(MembershipFixture.ROOT),
                bytes32(MembershipFixture.NULLIFIER),
                address(uint160(MembershipFixture.RECIPIENT) + 1),
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsTamperedFee() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(MembershipFixture.ROOT),
                bytes32(MembershipFixture.NULLIFIER),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE + 1,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsTamperedPool() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(MembershipFixture.ROOT),
                bytes32(MembershipFixture.NULLIFIER),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                "pool_eth_02"
            )
        );
    }

    function test_RejectsWrongChain() public {
        vm.chainId(1);
        assertFalse(_validProofAccepted());
    }

    // Note: the adapter checks block.chainid <= uint64.max, but Foundry's
    // vm.chainId cheatcode rejects values >= 2^64, so that branch cannot be
    // exercised directly here. It remains a defensive check in the adapter.

    /* ---------------------------------------------------------------------- */
    /* Range and pool-ID canonicality                                          */
    /* ---------------------------------------------------------------------- */

    function test_RejectsRootAboveFieldModulus() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(adapter.FIELD_MODULUS()),
                bytes32(MembershipFixture.NULLIFIER),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsNullifierAboveFieldModulus() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(MembershipFixture.ROOT),
                bytes32(adapter.FIELD_MODULUS()),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsFeeAboveUint64() public view {
        assertFalse(
            _verify(
                _proof(),
                bytes32(MembershipFixture.ROOT),
                bytes32(MembershipFixture.NULLIFIER),
                MembershipFixture.RECIPIENT,
                uint256(type(uint64).max) + 1,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsNonCanonicalPoolLabels() public view {
        // Low byte must be zero for the right-padded ASCII convention.
        (bool ok1, uint256 field1) = adapter.poolIdField(bytes32(uint256(1)));
        assertFalse(ok1);
        assertEq(field1, 0);

        // Zero is not a valid pool ID.
        (bool ok2, uint256 field2) = adapter.poolIdField(bytes32(0));
        assertFalse(ok2);
        assertEq(field2, 0);

        // A 32-byte ASCII label has a non-zero low byte and is rejected.
        (bool ok3, uint256 field3) = adapter.poolIdField("pool_eth_01_pool_eth_01_pool_eth");
        assertFalse(ok3);
        assertEq(field3, 0);

        // A different right-padded label is canonical but a different field.
        (bool ok4, uint256 field4) = adapter.poolIdField("pool_eth_02");
        assertTrue(ok4);
        assertTrue(field4 != MembershipFixture.POOL_ID_FIELD);
    }

    /* ---------------------------------------------------------------------- */
    /* Malformed and tampered proofs                                           */
    /* ---------------------------------------------------------------------- */

    function test_RejectsMalformedProofLengths() public view {
        bytes32 root = bytes32(MembershipFixture.ROOT);
        bytes32 nullifier = bytes32(MembershipFixture.NULLIFIER);

        assertFalse(
            _verify(
                "",
                root,
                nullifier,
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
        assertFalse(
            _verify(
                new bytes(160),
                root,
                nullifier,
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
        assertFalse(
            _verify(
                new bytes(255),
                root,
                nullifier,
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
        assertFalse(
            _verify(
                new bytes(257),
                root,
                nullifier,
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
        // Correct length, all-zero words: decodable but not a valid proof.
        assertFalse(
            _verify(
                new bytes(256),
                root,
                nullifier,
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsTamperedProofPoint() public pure {
        bytes memory proof = MembershipFixture.proof();
        (uint256[2] memory pA, uint256[2][2] memory pB, uint256[2] memory pC) =
            abi.decode(proof, (uint256[2], uint256[2][2], uint256[2]));

        pA[0] = pA[0] + 1;
        bytes memory tampered = abi.encode(pA, pB, pC);

        // The verifier is deployed in the test contract, so use a fresh adapter
        // via the internal helper value. This branch is checked in the non-view
        // test below; keep this test focused on encoding.
        assertTrue(tampered.length == 256);
        assertTrue(keccak256(tampered) != keccak256(proof));
    }

    function test_RejectsTamperedProofOnChain() public view {
        bytes memory proof = MembershipFixture.proof();
        (uint256[2] memory pA, uint256[2][2] memory pB, uint256[2] memory pC) =
            abi.decode(proof, (uint256[2], uint256[2][2], uint256[2]));

        pA[0] = pA[0] + 1;
        bytes memory tampered = abi.encode(pA, pB, pC);

        assertFalse(
            _verify(
                tampered,
                bytes32(MembershipFixture.ROOT),
                bytes32(MembershipFixture.NULLIFIER),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }

    function test_RejectsMockProofShape() public view {
        // A MockVerifier proof is 160 bytes and must not be accepted by the real
        // adapter even if its decoded words happen to match.
        bytes memory mockProof = abi.encode(
            bytes32(MembershipFixture.ROOT),
            bytes32(MembershipFixture.NULLIFIER),
            MembershipFixture.RECIPIENT,
            MembershipFixture.FEE,
            MembershipFixture.POOL_ID_LABEL
        );
        assertEq(mockProof.length, 160);
        assertFalse(
            _verify(
                mockProof,
                bytes32(MembershipFixture.ROOT),
                bytes32(MembershipFixture.NULLIFIER),
                MembershipFixture.RECIPIENT,
                MembershipFixture.FEE,
                MembershipFixture.POOL_ID_LABEL
            )
        );
    }
}
