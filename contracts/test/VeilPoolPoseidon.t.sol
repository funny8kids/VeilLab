// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Groth16VerifierAdapter} from "../src/Groth16VerifierAdapter.sol";
import {Poseidon} from "../src/Poseidon.sol";
import {VeilPoolPoseidon} from "../src/VeilPoolPoseidon.sol";
import {MembershipFixture} from "./fixtures/MembershipFixture.sol";

/// @title VeilPoolPoseidonTest
/// @notice LOCAL SPIKE ONLY: proves the fixture proof on the EVM against a real
///         Poseidon Merkle root built by VeilPoolPoseidon deposits.
contract VeilPoolPoseidonTest is Test {
    Groth16VerifierAdapter internal verifier;
    VeilPoolPoseidon internal pool;

    address internal alice;
    address internal relayer;

    // The contract takes the right-padded ASCII deploy label D, exactly like
    // bytes32("pool_eth_01") in contracts/script/Deploy.s.sol. This is NOT the
    // circuit's zero-prefixed field F. The adapter computes uint256(D) >> 8 = F.
    bytes32 internal constant POOL_ID_LABEL = MembershipFixture.POOL_ID_LABEL;
    uint256 internal constant DENOMINATION = MembershipFixture.DENOMINATION;
    uint32 internal constant ROOT_WINDOW = 64;
    uint32 internal constant MATURITY = 1 hours;

    function setUp() public {
        vm.chainId(MembershipFixture.CHAIN_ID);
        verifier = new Groth16VerifierAdapter();
        pool = new VeilPoolPoseidon(address(verifier));
        // Create the pool with the deploy label D, not the circuit field F.
        pool.createPool(POOL_ID_LABEL, DENOMINATION, ROOT_WINDOW, MATURITY);

        alice = makeAddr("alice");
        relayer = makeAddr("relayer");
        vm.deal(alice, 10 ether);
    }

    /* ---------------------------------------------------------------------- */
    /* Helpers                                                                 */
    /* ---------------------------------------------------------------------- */

    function _depositFixtureLeaves() internal {
        bytes32[8] memory leaves = MembershipFixture.leaves();
        for (uint256 i = 0; i < leaves.length; i++) {
            vm.prank(alice);
            pool.deposit{value: DENOMINATION}(leaves[i]);
        }
    }

    function _withdraw(bytes memory proof, address recipient, uint256 fee) internal {
        vm.prank(relayer);
        pool.withdraw(
            proof,
            bytes32(MembershipFixture.ROOT),
            bytes32(MembershipFixture.NULLIFIER),
            payable(recipient),
            fee,
            POOL_ID_LABEL
        );
    }

    /* ---------------------------------------------------------------------- */
    /* Poseidon vectors                                                        */
    /* ---------------------------------------------------------------------- */

    function test_PoseidonMatchesCircomlibVectors() public pure {
        assertEq(Poseidon.hash3(MembershipFixture.DOMAIN_NODE, 0, 0), MembershipFixture.ZERO_HASH_1);
        assertEq(Poseidon.hash3(MembershipFixture.DOMAIN_NODE, 1, 2), MembershipFixture.HASH3_1_2);

        assertEq(
            Poseidon.hash5(
                MembershipFixture.DOMAIN_NULLIFIER,
                MembershipFixture.CHAIN_ID,
                MembershipFixture.POOL_ID_FIELD,
                MembershipFixture.COMMITMENT,
                MembershipFixture.NULLIFIER_SECRET_FIELD
            ),
            MembershipFixture.NULLIFIER
        );

        assertEq(
            Poseidon.hash6(
                MembershipFixture.DOMAIN_COMMITMENT,
                MembershipFixture.CHAIN_ID,
                MembershipFixture.POOL_ID_FIELD,
                MembershipFixture.DENOMINATION,
                MembershipFixture.SECRET_FIELD,
                MembershipFixture.NULLIFIER_SECRET_FIELD
            ),
            MembershipFixture.COMMITMENT
        );
    }

    function test_ZeroSubtreeMatchesFixture() public pure {
        uint256 zero = 0;
        for (uint256 level = 0; level < 20; level++) {
            zero = Poseidon.hash3(MembershipFixture.DOMAIN_NODE, zero, zero);
        }
        assertEq(zero, MembershipFixture.ZERO_HASH_20);
    }

    function test_InitialRootIsPoseidonEmptyTree() public view {
        assertEq(uint256(pool.currentRoot(POOL_ID_LABEL)), MembershipFixture.ZERO_HASH_20);
    }

    function test_FixtureTreeRootRecomputedFromLeaves() public pure {
        bytes32[8] memory leaves = MembershipFixture.leaves();
        uint256[8] memory nodes;
        for (uint256 i = 0; i < 8; i++) {
            nodes[i] = uint256(leaves[i]);
        }

        uint256 count = 8;
        uint256 zero = 0;
        for (uint256 level = 0; level < 20; level++) {
            uint256 nextCount = (count + 1) / 2;
            uint256[8] memory next;
            for (uint256 i = 0; i < nextCount; i++) {
                uint256 left = nodes[2 * i];
                uint256 right = 2 * i + 1 < count ? nodes[2 * i + 1] : zero;
                next[i] = Poseidon.hash3(MembershipFixture.DOMAIN_NODE, left, right);
            }
            nodes = next;
            count = nextCount;
            zero = Poseidon.hash3(MembershipFixture.DOMAIN_NODE, zero, zero);
        }

        assertEq(nodes[0], MembershipFixture.ROOT);
    }

    /* ---------------------------------------------------------------------- */
    /* End-to-end deposit / withdraw                                           */
    /* ---------------------------------------------------------------------- */

    function test_EightFixtureDepositsReproduceRoot() public {
        _depositFixtureLeaves();

        assertEq(pool.leafCount(POOL_ID_LABEL), 8);
        assertEq(pool.currentRoot(POOL_ID_LABEL), bytes32(MembershipFixture.ROOT));
        assertEq(address(pool).balance, 8 * DENOMINATION);
        assertTrue(pool.isKnownRoot(POOL_ID_LABEL, bytes32(MembershipFixture.ROOT)));
    }

    function test_WithdrawWithRealProof() public {
        _depositFixtureLeaves();

        bytes32 root = bytes32(MembershipFixture.ROOT);
        bytes32 nullifier = bytes32(MembershipFixture.NULLIFIER);
        address recipient = MembershipFixture.RECIPIENT;
        uint256 fee = MembershipFixture.FEE;

        uint256 readyAt = pool.rootTimestamp(POOL_ID_LABEL, root) + MATURITY;
        vm.warp(readyAt + 1);

        uint256 recipientBefore = recipient.balance;
        uint256 relayerBefore = relayer.balance;

        _withdraw(MembershipFixture.proof(), recipient, fee);

        assertEq(recipient.balance, recipientBefore + DENOMINATION - fee);
        assertEq(relayer.balance, relayerBefore + fee);
        assertEq(address(pool).balance, 8 * DENOMINATION - DENOMINATION);
        assertTrue(pool.isNullifierSpent(POOL_ID_LABEL, nullifier));
    }

    function test_ReplayRevertsAfterRealWithdrawal() public {
        _depositFixtureLeaves();
        vm.warp(block.timestamp + MATURITY + 1);

        bytes32 nullifier = bytes32(MembershipFixture.NULLIFIER);
        _withdraw(MembershipFixture.proof(), MembershipFixture.RECIPIENT, MembershipFixture.FEE);

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(
                VeilPoolPoseidon.NullifierAlreadySpent.selector, POOL_ID_LABEL, nullifier
            )
        );
        pool.withdraw(
            MembershipFixture.proof(),
            bytes32(MembershipFixture.ROOT),
            nullifier,
            payable(MembershipFixture.RECIPIENT),
            MembershipFixture.FEE,
            POOL_ID_LABEL
        );
    }

    function test_TamperedRecipientFailsProof() public {
        _depositFixtureLeaves();
        vm.warp(block.timestamp + MATURITY + 1);

        vm.prank(relayer);
        vm.expectRevert(VeilPoolPoseidon.InvalidProof.selector);
        pool.withdraw(
            MembershipFixture.proof(),
            bytes32(MembershipFixture.ROOT),
            bytes32(MembershipFixture.NULLIFIER),
            payable(address(0xBEEF)),
            MembershipFixture.FEE,
            POOL_ID_LABEL
        );

        assertFalse(pool.isNullifierSpent(POOL_ID_LABEL, bytes32(MembershipFixture.NULLIFIER)));
    }

    function test_MaturityBeforeReadyRevertsWithRealProof() public {
        _depositFixtureLeaves();
        bytes32 root = bytes32(MembershipFixture.ROOT);
        uint256 readyAt = pool.rootTimestamp(POOL_ID_LABEL, root) + MATURITY;
        vm.warp(readyAt - 1);

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(VeilPoolPoseidon.MaturityNotReached.selector, readyAt)
        );
        pool.withdraw(
            MembershipFixture.proof(),
            root,
            bytes32(MembershipFixture.NULLIFIER),
            payable(MembershipFixture.RECIPIENT),
            MembershipFixture.FEE,
            POOL_ID_LABEL
        );
    }

    function test_PausedPoolBlocksRealWithdraw() public {
        _depositFixtureLeaves();
        vm.warp(block.timestamp + MATURITY + 1);
        pool.pause(POOL_ID_LABEL, "spike pause");

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(VeilPoolPoseidon.PoolIsPaused.selector, POOL_ID_LABEL)
        );
        pool.withdraw(
            MembershipFixture.proof(),
            bytes32(MembershipFixture.ROOT),
            bytes32(MembershipFixture.NULLIFIER),
            payable(MembershipFixture.RECIPIENT),
            MembershipFixture.FEE,
            POOL_ID_LABEL
        );

        pool.resume(POOL_ID_LABEL);
        _withdraw(MembershipFixture.proof(), MembershipFixture.RECIPIENT, MembershipFixture.FEE);
    }

    /* ---------------------------------------------------------------------- */
    /* Integration guards                                                      */
    /* ---------------------------------------------------------------------- */

    function test_DepositRejectsNonCanonicalCommitment() public {
        uint256 modulus = pool.FIELD_MODULUS();
        vm.prank(alice);
        vm.expectRevert(VeilPoolPoseidon.InvalidCommitment.selector);
        pool.deposit{value: DENOMINATION}(bytes32(modulus));
    }

    function test_CreatePoolRejectsNonCanonicalLabel() public {
        vm.expectRevert(VeilPoolPoseidon.InvalidPoolId.selector);
        pool.createPool(bytes32(uint256(1)), 1 ether, ROOT_WINDOW, 0);
    }

    function test_CreatePoolRejectsZeroPrefixedCircuitField() public {
        // Passing the circuit field F instead of the deploy label D would make
        // the adapter derive the wrong pool_id. createPool rejects it.
        vm.expectRevert(VeilPoolPoseidon.InvalidPoolId.selector);
        pool.createPool(bytes32(MembershipFixture.POOL_ID_FIELD), 2 ether, ROOT_WINDOW, 0);
    }

    function test_PoolLabelMapsToFixtureField() public view {
        // The contract pool ID is D = bytes32("pool_eth_01"), not F.
        assertEq(POOL_ID_LABEL, bytes32("pool_eth_01"));
        assertTrue(POOL_ID_LABEL != bytes32(MembershipFixture.POOL_ID_FIELD));
        assertEq(uint256(POOL_ID_LABEL) >> 8, MembershipFixture.POOL_ID_FIELD);
        assertEq(uint8(uint256(POOL_ID_LABEL)), 0);
        (bool ok, uint256 field) = verifier.poolIdField(POOL_ID_LABEL);
        assertTrue(ok);
        assertEq(field, MembershipFixture.POOL_ID_FIELD);
    }
}
