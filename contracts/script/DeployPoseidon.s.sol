// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {Groth16VerifierAdapter} from "../src/Groth16VerifierAdapter.sol";
import {VeilPoolPoseidon} from "../src/VeilPoolPoseidon.sol";

/// @title DeployPoseidon
/// @notice LOCAL SPIKE ONLY: deploy the real-proof Poseidon path to Anvil chain ID 31337.
/// @dev WARNING: DEVELOPMENT ZKEY / NO CEREMONY / NOT PRODUCTION.
///      The generated Groth16 verifier comes from a single-machine development zkey,
///      not a multi-party ceremony. The circuit, Poseidon implementation, adapter and
///      pool are unaudited. This deployment has no production security and must never
///      hold real funds.
///
///      Pool created by this script:
///        label        bytes32("pool_eth_01")
///        denomination 0.1 ether
///        root window  64 roots (a count, not a time window)
///        maturity     0 seconds
///
///      !!! MATURITY 0 IS A LOCAL SPIKE SETTING, NOT A PRODUCT DEFAULT !!!
///      It makes every accepted root immediately eligible for withdrawal so a local
///      browser proof does not need to wait or time-travel. The shipped mock demo uses
///      30 minutes / 2 hours / 6 hours. Maturity 0 removes the root-aging defense and
///      must not be copied into a product, testnet or public deployment.
contract DeployPoseidon is Script {
    uint256 internal constant LOCAL_CHAIN_ID = 31337;

    uint256 internal constant DENOMINATION = 0.1 ether;
    uint32 internal constant ROOT_WINDOW = 64;

    // LOCAL SPIKE ONLY - NOT A PRODUCT DEFAULT. See the contract-level warning above.
    uint32 internal constant MATURITY = 0;

    // Right-padded ASCII deploy label, as used by Deploy.s.sol. The adapter converts
    // it to the circuit pool_id field with uint256(label) >> 8.
    bytes32 internal constant POOL_ETH_01 = bytes32("pool_eth_01");

    function run() external returns (Groth16VerifierAdapter adapter, VeilPoolPoseidon pool) {
        require(block.chainid == LOCAL_CHAIN_ID, "DeployPoseidon: local Anvil chain ID 31337 only");

        console2.log("============================================================");
        console2.log("VeilPool Poseidon spike deployment (REAL GROTH16 PROOF PATH)");
        console2.log("DEVELOPMENT ZKEY / NO CEREMONY / NOT PRODUCTION");
        console2.log("Unaudited circuit, Poseidon, adapter and pool.");
        console2.log("LOCAL ANVIL CHAIN ID 31337 ONLY. Never use real funds.");
        console2.log("============================================================");

        vm.startBroadcast();

        adapter = new Groth16VerifierAdapter();
        pool = new VeilPoolPoseidon(address(adapter));

        // Use the right-padded bytes32 deploy label, not the circuit's zero-prefixed
        // field. createPool rejects the circuit encoding so a broken pool cannot exist.
        pool.createPool(POOL_ETH_01, DENOMINATION, ROOT_WINDOW, MATURITY);

        vm.stopBroadcast();

        // Fail loudly if the deploy label or deposit routing drifted.
        require(
            pool.poolIdForDenomination(DENOMINATION) == POOL_ETH_01,
            "DeployPoseidon: pool_eth_01 pool ID mismatch"
        );
        require(
            pool.denominationOf(POOL_ETH_01) == DENOMINATION,
            "DeployPoseidon: pool denomination mismatch"
        );
        require(pool.maturityOf(POOL_ETH_01) == MATURITY, "DeployPoseidon: pool maturity mismatch");

        address groth16Verifier = address(adapter.groth16Verifier());
        require(groth16Verifier.code.length != 0, "DeployPoseidon: generated verifier not deployed");

        console2.log("Groth16VerifierAdapter deployed at:", address(adapter));
        console2.log("VeilPoolPoseidon deployed at:", address(pool));
        console2.log("Groth16Verifier (via adapter) deployed at:", groth16Verifier);
        console2.log("Chain ID:", block.chainid);
        console2.log("Pool label: pool_eth_01");
        console2.log(string.concat("Pool ID (bytes32): ", vm.toString(POOL_ETH_01)));
        console2.log("Denomination (wei):", DENOMINATION);
        console2.log("Root window (count of roots):", uint256(ROOT_WINDOW));
        console2.log("Maturity (seconds):", uint256(MATURITY));
        console2.log("Pool check: poolIdForDenomination(0.1 ether) == pool_eth_01");

        console2.log("");
        console2.log("!!! MATURITY 0: LOCAL SPIKE SETTING, NOT A PRODUCT DEFAULT !!!");
        console2.log("Roots are immediately withdrawable. Do not ship this configuration.");
        console2.log("The shipped mock demo uses 30 min / 2 h / 6 h maturities.");
        console2.log("");

        _logIndexerEnv(address(pool));
        _logApiEnv(address(pool));

        console2.log("Fixture deposit (optional, reproduces the fixture root):");
        console2.log(
            string.concat("  $env:VEILPOOL_POSEIDON_ADDRESS = \"", vm.toString(address(pool)), "\"")
        );
        console2.log("  forge script script/DepositFixture.s.sol:DepositFixture ...");

        console2.log("");
        console2.log("NOTE: the static fixture proof is bound to chain_id 11155111.");
        console2.log("On chain 31337, generate a fresh proof with chain_id 31337.");
    }

    /// @dev Print the exact environment variables consumed by apps/indexer.
    function _logIndexerEnv(address pool) internal pure {
        console2.log("Indexer environment (apps/indexer):");
        console2.log("  $env:ANVIL_RPC_URL = \"http://127.0.0.1:8545\"");
        console2.log(string.concat("  $env:VEILPOOL_ADDRESS = \"", vm.toString(pool), "\""));
        console2.log("  $env:INDEXER_DB = \"indexer.db\"");
        console2.log("  $env:INDEXER_START_BLOCK = \"0\"");
        console2.log("  $env:INDEXER_PORT = \"8100\"");
        console2.log("  $env:INDEXER_ALLOWED_CHAIN_IDS = \"31337\"");
        console2.log("  python -m veilpool_indexer");
    }

    /// @dev Print the exact environment variables consumed by apps/api in local mode.
    function _logApiEnv(address pool) internal pure {
        console2.log("API environment (apps/api):");
        console2.log("  $env:VEILPOOL_MODE = \"local\"");
        console2.log("  $env:VEILPOOL_CHAIN_ID = \"31337\"");
        console2.log(
            string.concat("  $env:VEILPOOL_CONTRACT_ADDRESS = \"", vm.toString(pool), "\"")
        );
        console2.log("  $env:VEILPOOL_INDEXER_URL = \"http://127.0.0.1:8100\"");
        console2.log("  $env:VEILPOOL_LOCAL_RPC_URL = \"http://127.0.0.1:8545\"");
        console2.log("  $env:VEILPOOL_LOCAL_AUTO_DEPOSIT = \"false\"");
        console2.log("  python -m uvicorn veilpool_api.main:app --port 8000");
    }
}
