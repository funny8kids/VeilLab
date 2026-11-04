// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {VeilPoolPoseidon} from "../src/VeilPoolPoseidon.sol";
import {MembershipFixture} from "../test/fixtures/MembershipFixture.sol";

/// @title DepositFixture
/// @notice LOCAL SPIKE ONLY: deposit the eight public fixture commitments into a
///         deployed VeilPoolPoseidon so the live chain reproduces the fixture root.
/// @dev Requires chain ID 31337 and the environment variable
///      VEILPOOL_POSEIDON_ADDRESS. The labelled pool_eth_01 / 0.1 ether pool must be
///      fresh (zero leaves). Only the public fixture commitments are sent on chain;
///      no note secret, nullifier secret or proof is sent.
///
///      IMPORTANT: the static fixture proof in MembershipFixture.sol is bound to
///      chain_id 11155111 and is rejected by the adapter on chain 31337. This script
///      only reproduces the fixture Merkle tree. Generate a new proof with
///      chain_id 31337 for a local browser withdrawal.
contract DepositFixture is Script {
    uint256 internal constant LOCAL_CHAIN_ID = 31337;

    function run() external returns (bytes32 root) {
        require(block.chainid == LOCAL_CHAIN_ID, "DepositFixture: local Anvil chain ID 31337 only");

        address poolAddress = vm.envAddress("VEILPOOL_POSEIDON_ADDRESS");
        require(poolAddress.code.length != 0, "DepositFixture: pool address has no code");

        VeilPoolPoseidon pool = VeilPoolPoseidon(payable(poolAddress));
        bytes32 poolId = MembershipFixture.POOL_ID_LABEL;
        uint256 denomination = MembershipFixture.DENOMINATION;

        require(
            pool.poolIdForDenomination(denomination) == poolId,
            "DepositFixture: labelled pool_eth_01 / 0.1 ether pool not found"
        );
        require(
            pool.leafCount(poolId) == 0,
            "DepositFixture: pool already has leaves; deploy a fresh pool to reproduce the fixture"
        );

        bytes32[8] memory leaves = MembershipFixture.leaves();

        console2.log("============================================================");
        console2.log("DepositFixture: eight public fixture commitments");
        console2.log("DEVELOPMENT ZKEY / NO CEREMONY / NOT PRODUCTION");
        console2.log("LOCAL ANVIL CHAIN ID 31337 ONLY. Never use real funds.");
        console2.log("============================================================");
        console2.log("VeilPoolPoseidon:", poolAddress);
        console2.log("Pool label: pool_eth_01");
        console2.log(string.concat("Pool ID (bytes32): ", vm.toString(poolId)));
        console2.log("Denomination per deposit (wei):", denomination);

        vm.startBroadcast();

        for (uint256 i = 0; i < leaves.length; i++) {
            pool.deposit{value: denomination}(leaves[i]);
            console2.log("Deposited fixture leaf index:", i);
        }

        vm.stopBroadcast();

        root = pool.currentRoot(poolId);
        bytes32 expectedRoot = bytes32(MembershipFixture.ROOT);

        require(pool.leafCount(poolId) == 8, "DepositFixture: expected 8 leaves");
        require(root == expectedRoot, "DepositFixture: root does not match the fixture root");

        console2.log("Leaf count:", pool.leafCount(poolId));
        console2.log("Current root:");
        console2.logBytes32(root);
        console2.log("Expected fixture root:");
        console2.logBytes32(expectedRoot);
        console2.log("Root check: currentRoot == MembershipFixture.ROOT");
        console2.log("");
        console2.log("NOTE: the static fixture proof is bound to chain_id 11155111.");
        console2.log("It will be rejected on chain 31337. Generate a fresh proof for 31337.");
        console2.log("The root above is the fixture root; only the proof domain differs.");
    }
}
