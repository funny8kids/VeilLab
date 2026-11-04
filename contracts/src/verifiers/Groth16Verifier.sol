// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

/*
 * VEILPOOL SPIKE VERIFIER - NOT FOR PRODUCTION
 *
 * Copied from circuits/build/Verifier.sol, regenerated with:
 *   snarkjs zkey export solidityverifier \
 *     circuits/build/membership_0001.zkey \
 *     circuits/build/Verifier.sol
 *
 * The zkey comes from a single-machine development trusted setup, not a
 * multi-party ceremony. Anyone who can recover its toxic waste can forge
 * proofs for this circuit.
 *
 * The earlier circuits/build/Verifier.sol in this workspace did not match
 * membership_0001.zkey / verification_key.json (its IC0 and delta constants
 * were stale, apparently from an earlier export before the final phase-2
 * contribution). It was preserved as circuits/build/Verifier.stale.sol and
 * regenerated from the final zkey before this copy was made. See
 * docs/veilpool/ZK_CONTRACT_INTEGRATION.md.
 *
 * TESTNET / LOCAL SPIKE ONLY. Do not reuse this file or its key in
 * production, and do not deploy it with real funds.
 */

pragma solidity >=0.7.0 <0.9.0;

contract Groth16Verifier {
    // Scalar field size
    uint256 constant r =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;
    // Base field size
    uint256 constant q =
        21888242871839275222246405745257275088696311157297823662689037894645226208583;

    // Verification Key data
    uint256 constant alphax =
        12419798448709820419536496402511510647371965421157782707521723016603594158411;
    uint256 constant alphay =
        7399231151808832483505921512723819484934733319182499555957870917070629175169;
    uint256 constant betax1 =
        5737411321362634803883977132422472522942044058294308723257386578703828326978;
    uint256 constant betax2 =
        20785957332670384912998493220232732830607091041655986929039183127851709491303;
    uint256 constant betay1 =
        5034845399589560347799587017958933651926695579542017488377942059830408405261;
    uint256 constant betay2 =
        14476315200487982760199553352637245831731795881823450584986991335954812304416;
    uint256 constant gammax1 =
        11559732032986387107991004021392285783925812861821192530917403151452391805634;
    uint256 constant gammax2 =
        10857046999023057135944570762232829481370756359578518086990519993285655852781;
    uint256 constant gammay1 =
        4082367875863433681332203403145435568316851327593401208105741076214120093531;
    uint256 constant gammay2 =
        8495653923123431417604973247489272438418190587263600148770280649306958101930;
    uint256 constant deltax1 =
        11313586929697430779256594003685890876635553956570720346659699097352790228914;
    uint256 constant deltax2 =
        18756110298548996319979123092166843054683488243518120598066413464821216378648;
    uint256 constant deltay1 =
        3836209932654227224071378518940299843891583719083905638027792463651075069617;
    uint256 constant deltay2 =
        4166776921318206519281669712811405234285652035695700475419270009883179927658;

    uint256 constant IC0x =
        16759143518793367648509993944101492111531216540347129964365942025916433080906;
    uint256 constant IC0y =
        10578669868095332259568772677141474589460170292973852333169907600823457708351;

    uint256 constant IC1x =
        11256103107489067832043150915870505006439213879793873389274801984232830234730;
    uint256 constant IC1y =
        2808930094151168195660589242643282716548552539136338366311535390523684428774;

    uint256 constant IC2x =
        11761196483249549813171831084661306391247785057451775928471186150995569130502;
    uint256 constant IC2y =
        10002158638380280541367868800218735999920566175994410122790308225349879972071;

    uint256 constant IC3x =
        13713417456223723562418758622202381518158404491465758484936442518459512676322;
    uint256 constant IC3y =
        14886612229429983033780723463279615649110474680148916224949385428147757619754;

    uint256 constant IC4x =
        21193177211871185970384579252510913003409891473189372708929161693450601516538;
    uint256 constant IC4y =
        5049605877916935113225713122134782252293368261865399705609120609986305480743;

    uint256 constant IC5x =
        12780307403748547939736376112761046783203912313543684923785650778886853712949;
    uint256 constant IC5y =
        10943303791717744710647941460789148084205304815629053353748388400555938046578;

    uint256 constant IC6x =
        17328664305948261812160044787736533367622025308603269066514940383808887662374;
    uint256 constant IC6y =
        4942516427532342004871537989207999267438388430745860361563636296846503346315;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[6] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
