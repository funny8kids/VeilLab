// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {MockVerifier} from "../src/MockVerifier.sol";
import {VeilPool} from "../src/VeilPool.sol";

/// @title VeilPool local deployment script
/// @notice Deploy the MOCK verifier and three ETH pools to a local Anvil chain.
/// @dev WARNING: MockVerifier performs no cryptography. This deployment has no
///      anonymity and must never be used with real funds or on a public network.
///
///      Pools mirror docs/veilpool/POOL_MODEL.md for ETH:
///        ETH-0.1  0.1 ether, 30 minutes maturity
///        ETH-1    1 ether,   2 hours maturity
///        ETH-10   10 ether,  6 hours maturity
///      Root window is a count of recent roots. 64 is a local demo value; the
///      contract accepts 1..1024. It is not a time or block window.
contract Deploy is Script {
    uint256 internal constant LOCAL_CHAIN_ID = 31337;

    uint32 internal constant ROOT_WINDOW = 64;
    uint256 internal constant ETH_01_DENOMINATION = 0.1 ether;
    uint256 internal constant ETH_1_DENOMINATION = 1 ether;
    uint256 internal constant ETH_10_DENOMINATION = 10 ether;

    // ASCII bytes32 IDs, matching the short pool IDs used by the mock API.
    // Example: bytes32("pool_eth_01") == 0x706f6f6c5f6574685f303100...
    bytes32 internal constant POOL_ETH_01 = bytes32("pool_eth_01");
    bytes32 internal constant POOL_ETH_1 = bytes32("pool_eth_1");
    bytes32 internal constant POOL_ETH_10 = bytes32("pool_eth_10");

    function run() external returns (MockVerifier verifier, VeilPool pool) {
        require(block.chainid == LOCAL_CHAIN_ID, "VeilPool Deploy: local Anvil chain ID 31337 only");

        console2.log("============================================================");
        console2.log("VeilPool local deployment");
        console2.log("MOCK VERIFIER: no ZK, no membership proof, no privacy.");
        console2.log("LOCAL ANVIL ONLY. Never use real funds.");
        console2.log("============================================================");

        vm.startBroadcast();

        verifier = new MockVerifier();
        pool = new VeilPool(address(verifier));

        pool.createPool(POOL_ETH_01, ETH_01_DENOMINATION, ROOT_WINDOW, 30 minutes);
        pool.createPool(POOL_ETH_1, ETH_1_DENOMINATION, ROOT_WINDOW, 2 hours);
        pool.createPool(POOL_ETH_10, ETH_10_DENOMINATION, ROOT_WINDOW, 6 hours);

        vm.stopBroadcast();

        // Fail loudly if the deployment drifted from the expected IDs.
        require(
            pool.poolIdForDenomination(ETH_01_DENOMINATION) == POOL_ETH_01,
            "Deploy: ETH-0.1 pool ID mismatch"
        );
        require(
            pool.poolIdForDenomination(ETH_1_DENOMINATION) == POOL_ETH_1,
            "Deploy: ETH-1 pool ID mismatch"
        );
        require(
            pool.poolIdForDenomination(ETH_10_DENOMINATION) == POOL_ETH_10,
            "Deploy: ETH-10 pool ID mismatch"
        );

        console2.log("MockVerifier deployed at:", address(verifier));
        console2.log("VeilPool deployed at:", address(pool));
        console2.log("Chain ID:", block.chainid);
        console2.log("Root window (count of roots):", uint256(ROOT_WINDOW));
        console2.log("ETH-0.1: 100000000000000000 wei, 1800 s maturity");
        console2.log("ETH-1:   1000000000000000000 wei, 7200 s maturity");
        console2.log("ETH-10:  10000000000000000000 wei, 21600 s maturity");
        console2.log("Pool ID pool_eth_01:");
        console2.logBytes32(POOL_ETH_01);
        console2.log("Pool ID pool_eth_1:");
        console2.logBytes32(POOL_ETH_1);
        console2.log("Pool ID pool_eth_10:");
        console2.logBytes32(POOL_ETH_10);
        console2.log("Indexer command:");
        console2.log("  $env:VEILPOOL_ADDRESS=\"<VeilPool address above>\"");
        console2.log("  python -m veilpool_indexer");
    }
}
