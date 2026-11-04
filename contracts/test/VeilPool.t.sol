// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockVerifier} from "../src/MockVerifier.sol";
import {VeilPool} from "../src/VeilPool.sol";

contract RejectingRecipient {
    receive() external payable {
        revert("no ETH accepted");
    }
}

contract VeilPoolTest is Test {
    event Deposit(bytes32 indexed poolId, bytes32 commitment, uint256 leafIndex, uint256 timestamp);
    event Withdrawal(
        bytes32 indexed poolId, bytes32 nullifier, address recipient, uint256 fee, uint256 timestamp
    );
    event RootUpdated(bytes32 indexed poolId, bytes32 root, uint256 leafIndex);
    event PoolPaused(bytes32 indexed poolId, string reason);
    event PoolResumed(bytes32 indexed poolId);
    event PoolCreated(
        bytes32 indexed poolId, uint256 denomination, uint32 rootWindow, uint32 maturity
    );

    MockVerifier internal verifier;
    VeilPool internal pool;

    bytes32 internal constant POOL_ID = keccak256("pool.eth.0.1");
    uint256 internal constant DENOMINATION = 0.1 ether;
    uint32 internal constant ROOT_WINDOW = 64;
    uint32 internal constant DEFAULT_MATURITY = 0;
    uint32 internal constant TEST_MATURITY = 30 minutes;
    uint256 internal constant TEST_MATURITY_DENOMINATION = 2 ether;
    bytes32 internal constant TEST_MATURITY_POOL_ID = keccak256("pool.eth.2");

    address internal alice;
    address internal bob;
    address internal relayer;

    function setUp() public {
        verifier = new MockVerifier();
        pool = new VeilPool(address(verifier));
        pool.createPool(POOL_ID, DENOMINATION, ROOT_WINDOW, DEFAULT_MATURITY);

        alice = makeAddr("alice");
        bob = makeAddr("bob");
        relayer = makeAddr("relayer");
        vm.deal(alice, 100 ether);
    }

    /* ---------------------------------------------------------------------- */
    /* Helpers                                                                 */
    /* ---------------------------------------------------------------------- */

    function _deposit(uint256 denomination, address from, bytes32 commitment) internal {
        vm.prank(from);
        pool.deposit{value: denomination}(commitment);
    }

    function _mockProof(
        bytes32 root,
        bytes32 nullifier,
        address recipient,
        uint256 relayerFee,
        bytes32 poolId
    ) internal pure returns (bytes memory) {
        return abi.encode(root, nullifier, recipient, relayerFee, poolId);
    }

    function _createMaturityPool() internal {
        pool.createPool(
            TEST_MATURITY_POOL_ID, TEST_MATURITY_DENOMINATION, ROOT_WINDOW, TEST_MATURITY
        );
    }

    function _depositMaturityNote(bytes32 commitment)
        internal
        returns (bytes32 root, uint256 readyAt)
    {
        _deposit(TEST_MATURITY_DENOMINATION, alice, commitment);
        root = pool.currentRoot(TEST_MATURITY_POOL_ID);
        readyAt = block.timestamp + TEST_MATURITY;
    }

    /* ---------------------------------------------------------------------- */
    /* Deposit                                                                 */
    /* ---------------------------------------------------------------------- */

    function test_ValidDeposit() public {
        bytes32 commitment = keccak256("commitment-1");
        bytes32 emptyRoot = pool.currentRoot(POOL_ID);

        vm.expectEmit(true, false, false, true);
        emit Deposit(POOL_ID, commitment, 0, block.timestamp);
        vm.prank(alice);
        pool.deposit{value: DENOMINATION}(commitment);

        bytes32 root = pool.currentRoot(POOL_ID);
        assertEq(address(pool).balance, DENOMINATION);
        assertEq(pool.leafCount(POOL_ID), 1);
        assertEq(pool.denominationOf(POOL_ID), DENOMINATION);
        assertEq(pool.maturityOf(POOL_ID), DEFAULT_MATURITY);
        assertEq(pool.poolIdForDenomination(DENOMINATION), POOL_ID);
        assertEq(pool.rootTimestamp(POOL_ID, emptyRoot), block.timestamp);
        assertEq(pool.rootTimestamp(POOL_ID, root), block.timestamp);
        assertTrue(root != emptyRoot);
        assertTrue(pool.isKnownRoot(POOL_ID, root));
    }

    function test_WrongAmountReverts() public {
        vm.startPrank(alice);

        vm.expectRevert(
            abi.encodeWithSelector(VeilPool.UnknownDenomination.selector, DENOMINATION - 1)
        );
        pool.deposit{value: DENOMINATION - 1}(keccak256("commitment-under"));

        vm.expectRevert(
            abi.encodeWithSelector(VeilPool.UnknownDenomination.selector, DENOMINATION + 1)
        );
        pool.deposit{value: DENOMINATION + 1}(keccak256("commitment-over"));

        vm.stopPrank();
    }

    function test_ZeroCommitmentReverts() public {
        vm.prank(alice);
        vm.expectRevert(VeilPool.InvalidCommitment.selector);
        pool.deposit{value: DENOMINATION}(bytes32(0));
    }

    function test_CreatePoolRejectsDuplicateDenomination() public {
        vm.expectRevert(
            abi.encodeWithSelector(
                VeilPool.DenominationAlreadyRegistered.selector, DENOMINATION, POOL_ID
            )
        );
        pool.createPool(keccak256("another-pool"), DENOMINATION, ROOT_WINDOW, DEFAULT_MATURITY);
    }

    /* ---------------------------------------------------------------------- */
    /* Withdrawal                                                              */
    /* ---------------------------------------------------------------------- */

    function test_WithdrawHappyPath() public {
        bytes32 commitment = keccak256("note-happy");
        _deposit(DENOMINATION, alice, commitment);

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-happy");
        uint256 relayerFee = 0.001 ether;
        uint256 expectedRecipient = DENOMINATION - relayerFee;
        bytes memory proof = _mockProof(root, nullifier, bob, relayerFee, POOL_ID);

        uint256 bobBefore = bob.balance;
        uint256 relayerBefore = relayer.balance;

        vm.expectEmit(true, false, false, true);
        emit Withdrawal(POOL_ID, nullifier, bob, relayerFee, block.timestamp);
        vm.prank(relayer);
        pool.withdraw(proof, root, nullifier, payable(bob), relayerFee, POOL_ID);

        assertEq(bob.balance, bobBefore + expectedRecipient);
        assertEq(relayer.balance, relayerBefore + relayerFee);
        assertEq(address(pool).balance, 0);
        assertTrue(pool.isNullifierSpent(POOL_ID, nullifier));
        assertTrue(pool.isKnownRoot(POOL_ID, root));
    }

    function test_DuplicateNullifierReverts() public {
        _deposit(DENOMINATION, alice, keccak256("note-duplicate"));

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-duplicate");
        bytes memory proof = _mockProof(root, nullifier, bob, 0, POOL_ID);

        vm.prank(relayer);
        pool.withdraw(proof, root, nullifier, payable(bob), 0, POOL_ID);

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(VeilPool.NullifierAlreadySpent.selector, POOL_ID, nullifier)
        );
        pool.withdraw(proof, root, nullifier, payable(bob), 0, POOL_ID);
    }

    function test_NullifierIsScopedPerPool() public {
        bytes32 secondPoolId = keccak256("pool.eth.1");
        uint256 secondDenomination = 1 ether;
        pool.createPool(secondPoolId, secondDenomination, ROOT_WINDOW, DEFAULT_MATURITY);

        _deposit(DENOMINATION, alice, keccak256("note-pool-a"));
        _deposit(secondDenomination, alice, keccak256("note-pool-b"));

        bytes32 rootA = pool.currentRoot(POOL_ID);
        bytes32 rootB = pool.currentRoot(secondPoolId);
        bytes32 nullifier = keccak256("shared-nullifier");

        vm.prank(relayer);
        pool.withdraw(
            _mockProof(rootA, nullifier, bob, 0, POOL_ID),
            rootA,
            nullifier,
            payable(bob),
            0,
            POOL_ID
        );

        vm.prank(relayer);
        pool.withdraw(
            _mockProof(rootB, nullifier, bob, 0, secondPoolId),
            rootB,
            nullifier,
            payable(bob),
            0,
            secondPoolId
        );

        assertTrue(pool.isNullifierSpent(POOL_ID, nullifier));
        assertTrue(pool.isNullifierSpent(secondPoolId, nullifier));
    }

    function test_InvalidProofReverts() public {
        _deposit(DENOMINATION, alice, keccak256("note-invalid-proof"));

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-invalid-proof");

        vm.prank(relayer);
        vm.expectRevert(VeilPool.InvalidProof.selector);
        pool.withdraw("", root, nullifier, payable(bob), 0, POOL_ID);
    }

    function test_ZeroRecipientReverts() public {
        _deposit(DENOMINATION, alice, keccak256("note-zero-recipient"));

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-zero-recipient");

        vm.prank(relayer);
        vm.expectRevert(VeilPool.InvalidRecipient.selector);
        pool.withdraw(
            _mockProof(root, nullifier, address(0), 0, POOL_ID),
            root,
            nullifier,
            payable(address(0)),
            0,
            POOL_ID
        );
    }

    function test_RejectedTransferDoesNotSpendNullifier() public {
        RejectingRecipient rejectingRecipient = new RejectingRecipient();
        _deposit(DENOMINATION, alice, keccak256("note-rejecting-recipient"));

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-rejecting-recipient");
        address recipient = address(rejectingRecipient);

        vm.prank(relayer);
        vm.expectRevert(VeilPool.TransferFailed.selector);
        pool.withdraw(
            _mockProof(root, nullifier, recipient, 0, POOL_ID),
            root,
            nullifier,
            payable(recipient),
            0,
            POOL_ID
        );

        assertFalse(pool.isNullifierSpent(POOL_ID, nullifier));
        assertEq(address(pool).balance, DENOMINATION);
    }

    /* ---------------------------------------------------------------------- */
    /* Fees                                                                    */
    /* ---------------------------------------------------------------------- */

    function test_FeeAtCapSucceeds() public {
        _deposit(DENOMINATION, alice, keccak256("note-fee-cap"));

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-fee-cap");
        uint256 cap = pool.maxFee(POOL_ID);
        uint256 expectedRecipient = DENOMINATION - cap;

        uint256 bobBefore = bob.balance;
        uint256 relayerBefore = relayer.balance;

        vm.prank(relayer);
        pool.withdraw(
            _mockProof(root, nullifier, bob, cap, POOL_ID),
            root,
            nullifier,
            payable(bob),
            cap,
            POOL_ID
        );

        assertEq(cap, (DENOMINATION * pool.MAX_FEE_BPS()) / pool.BPS_DENOMINATOR());
        assertEq(bob.balance, bobBefore + expectedRecipient);
        assertEq(relayer.balance, relayerBefore + cap);
        assertEq(address(pool).balance, 0);
    }

    function test_FeeAboveCapReverts() public {
        _deposit(DENOMINATION, alice, keccak256("note-fee-too-high"));

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-fee-too-high");
        uint256 cap = pool.maxFee(POOL_ID);
        uint256 tooHigh = cap + 1;

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(VeilPool.FeeTooHigh.selector, tooHigh, cap));
        pool.withdraw(
            _mockProof(root, nullifier, bob, tooHigh, POOL_ID),
            root,
            nullifier,
            payable(bob),
            tooHigh,
            POOL_ID
        );

        assertFalse(pool.isNullifierSpent(POOL_ID, nullifier));
    }

    function test_ProtocolFeeIsZeroInMvp() public {
        _deposit(DENOMINATION, alice, keccak256("note-protocol-fee"));

        assertEq(pool.PROTOCOL_FEE_BPS(), 0);
        (uint256 recipientAmount, uint256 protocolFee, uint256 totalFee) =
            pool.quoteWithdrawal(POOL_ID, 0.002 ether);
        assertEq(protocolFee, 0);
        assertEq(totalFee, 0.002 ether);
        assertEq(recipientAmount, DENOMINATION - 0.002 ether);
    }

    /* ---------------------------------------------------------------------- */
    /* Pause                                                                   */
    /* ---------------------------------------------------------------------- */

    function test_PausedPoolBlocksDepositAndWithdraw() public {
        _deposit(DENOMINATION, alice, keccak256("note-paused"));

        bytes32 root = pool.currentRoot(POOL_ID);
        bytes32 nullifier = keccak256("nullifier-paused");
        bytes memory proof = _mockProof(root, nullifier, bob, 0, POOL_ID);

        vm.expectEmit(true, false, false, true);
        emit PoolPaused(POOL_ID, "maintenance");
        pool.pause(POOL_ID, "maintenance");

        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(VeilPool.PoolIsPaused.selector, POOL_ID));
        pool.deposit{value: DENOMINATION}(keccak256("note-paused-2"));

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(VeilPool.PoolIsPaused.selector, POOL_ID));
        pool.withdraw(proof, root, nullifier, payable(bob), 0, POOL_ID);

        assertFalse(pool.isNullifierSpent(POOL_ID, nullifier));
        assertEq(pool.leafCount(POOL_ID), 1);
    }

    function test_ResumeUnblocksPool() public {
        pool.pause(POOL_ID, "maintenance");

        vm.expectEmit(true, false, false, true);
        emit PoolResumed(POOL_ID);
        pool.resume(POOL_ID);

        _deposit(DENOMINATION, alice, keccak256("note-resumed"));
        assertEq(pool.leafCount(POOL_ID), 1);
    }

    function test_PauseOnlyOwner() public {
        vm.prank(alice);
        vm.expectRevert(VeilPool.NotOwner.selector);
        pool.pause(POOL_ID, "not allowed");
    }

    /* ---------------------------------------------------------------------- */
    /* Root window                                                             */
    /* ---------------------------------------------------------------------- */

    function test_RootWindowExpiresOldRoot() public {
        bytes32 smallWindowPool = keccak256("pool.small-window");
        uint256 denomination = 1 ether;
        pool.createPool(smallWindowPool, denomination, 2, DEFAULT_MATURITY);

        address user = makeAddr("window-user");
        vm.deal(user, 10 ether);

        _deposit(denomination, user, keccak256("window-1"));
        bytes32 root1 = pool.currentRoot(smallWindowPool);

        _deposit(denomination, user, keccak256("window-2"));
        bytes32 root2 = pool.currentRoot(smallWindowPool);

        _deposit(denomination, user, keccak256("window-3"));
        bytes32 root3 = pool.currentRoot(smallWindowPool);

        assertFalse(pool.isKnownRoot(smallWindowPool, root1));
        assertTrue(pool.isKnownRoot(smallWindowPool, root2));
        assertTrue(pool.isKnownRoot(smallWindowPool, root3));
        assertEq(pool.rootTimestamp(smallWindowPool, root1), 0);
        assertEq(pool.rootTimestamp(smallWindowPool, root2), block.timestamp);
        assertEq(pool.rootTimestamp(smallWindowPool, root3), block.timestamp);

        bytes32 nullifier = keccak256("window-nullifier");
        vm.prank(user);
        vm.expectRevert(
            abi.encodeWithSelector(VeilPool.UnknownRoot.selector, smallWindowPool, root1)
        );
        pool.withdraw(
            _mockProof(root1, nullifier, user, 0, smallWindowPool),
            root1,
            nullifier,
            payable(user),
            0,
            smallWindowPool
        );

        // A root still inside the window can be used.
        vm.prank(user);
        pool.withdraw(
            _mockProof(root2, nullifier, user, 0, smallWindowPool),
            root2,
            nullifier,
            payable(user),
            0,
            smallWindowPool
        );
        assertTrue(pool.isNullifierSpent(smallWindowPool, nullifier));
    }

    /* ---------------------------------------------------------------------- */
    /* Maturity                                                                */
    /* ---------------------------------------------------------------------- */

    function test_MaturityBeforeReadyReverts() public {
        vm.expectEmit(true, false, false, true);
        emit PoolCreated(
            TEST_MATURITY_POOL_ID, TEST_MATURITY_DENOMINATION, ROOT_WINDOW, TEST_MATURITY
        );
        pool.createPool(
            TEST_MATURITY_POOL_ID, TEST_MATURITY_DENOMINATION, ROOT_WINDOW, TEST_MATURITY
        );

        (bytes32 root, uint256 readyAt) = _depositMaturityNote(keccak256("note-maturity-before"));

        assertEq(pool.maturityOf(TEST_MATURITY_POOL_ID), TEST_MATURITY);
        assertEq(pool.rootTimestamp(TEST_MATURITY_POOL_ID, root), block.timestamp);

        vm.warp(readyAt - 1);
        bytes32 nullifier = keccak256("nullifier-maturity-before");

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(VeilPool.MaturityNotReached.selector, readyAt));
        pool.withdraw(
            _mockProof(root, nullifier, bob, 0, TEST_MATURITY_POOL_ID),
            root,
            nullifier,
            payable(bob),
            0,
            TEST_MATURITY_POOL_ID
        );

        assertFalse(pool.isNullifierSpent(TEST_MATURITY_POOL_ID, nullifier));
        assertEq(address(pool).balance, TEST_MATURITY_DENOMINATION);
    }

    function test_MaturityExactlyAtReadySucceeds() public {
        _createMaturityPool();
        (bytes32 root, uint256 readyAt) = _depositMaturityNote(keccak256("note-maturity-exactly"));

        vm.warp(readyAt);

        bytes32 nullifier = keccak256("nullifier-maturity-exactly");
        uint256 bobBefore = bob.balance;

        vm.prank(relayer);
        pool.withdraw(
            _mockProof(root, nullifier, bob, 0, TEST_MATURITY_POOL_ID),
            root,
            nullifier,
            payable(bob),
            0,
            TEST_MATURITY_POOL_ID
        );

        assertEq(bob.balance, bobBefore + TEST_MATURITY_DENOMINATION);
        assertTrue(pool.isNullifierSpent(TEST_MATURITY_POOL_ID, nullifier));
    }

    function test_MaturityAfterReadySucceeds() public {
        _createMaturityPool();
        (bytes32 root, uint256 readyAt) = _depositMaturityNote(keccak256("note-maturity-after"));

        vm.warp(readyAt + 1);

        bytes32 nullifier = keccak256("nullifier-maturity-after");
        uint256 bobBefore = bob.balance;

        vm.prank(relayer);
        pool.withdraw(
            _mockProof(root, nullifier, bob, 0, TEST_MATURITY_POOL_ID),
            root,
            nullifier,
            payable(bob),
            0,
            TEST_MATURITY_POOL_ID
        );

        assertEq(bob.balance, bobBefore + TEST_MATURITY_DENOMINATION);
        assertTrue(pool.isNullifierSpent(TEST_MATURITY_POOL_ID, nullifier));
    }

    function test_RootTimestampUnknownReverts() public {
        bytes32 unknownRoot = keccak256("unknown-root");
        bytes32 nullifier = keccak256("nullifier-unknown-root");

        assertEq(pool.rootTimestamp(POOL_ID, unknownRoot), 0);

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(VeilPool.UnknownRoot.selector, POOL_ID, unknownRoot));
        pool.withdraw(
            _mockProof(unknownRoot, nullifier, bob, 0, POOL_ID),
            unknownRoot,
            nullifier,
            payable(bob),
            0,
            POOL_ID
        );
    }

    /* ---------------------------------------------------------------------- */
    /* Mock verifier behavior                                                   */
    /* ---------------------------------------------------------------------- */

    function test_MockVerifierRejectsMismatchedSignals() public view {
        bytes32 root = keccak256("mock-root");
        bytes32 nullifier = keccak256("mock-nullifier");
        bytes memory proof = _mockProof(root, nullifier, bob, 1, POOL_ID);

        assertTrue(verifier.verifyProof(proof, root, nullifier, bob, 1, POOL_ID));
        assertFalse(verifier.verifyProof(proof, root, nullifier, bob, 2, POOL_ID));
        assertFalse(verifier.verifyProof(proof, root, nullifier, alice, 1, POOL_ID));
        assertFalse(verifier.verifyProof(proof, root, keccak256("other"), bob, 1, POOL_ID));
        assertFalse(verifier.verifyProof(proof, root, nullifier, bob, 1, keccak256("other")));
        assertFalse(verifier.verifyProof("", root, nullifier, bob, 1, POOL_ID));
    }
}
