// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {IVerifier} from "./IVerifier.sol";

/// @title VeilPool
/// @notice Testnet-only, fixed-denomination ETH privacy pool MVP.
/// @dev Design notes:
///      - One active pool per denomination. The required deposit ABI has no poolId, so a
///        deposit is routed by its exact msg.value. Creating a second pool with the same
///        denomination is rejected.
///      - The root window is a count of recent deposit roots, not a time or block window.
///      - Every accepted root records block.timestamp. Withdrawals require the root to be at
///        least `maturity` seconds old.
///      - Protocol fee is fixed at 0 bps for the MVP. The recipient receives
///        denomination - relayerFee - protocolFee, and the relayer fee is paid to msg.sender.
///      - There is no upgrade proxy and the verifier is immutable.
contract VeilPool {
    /// @notice Merkle tree depth. Matches the 20-level tree in the pool model.
    uint256 public constant TREE_DEPTH = 20;
    /// @notice Maximum number of leaves per pool (2^20).
    uint256 public constant MAX_LEAVES = 1 << TREE_DEPTH;
    /// @notice Maximum total fee as a fraction of the denomination (10%).
    uint256 public constant MAX_FEE_BPS = 1_000;
    /// @notice Basis-point denominator.
    uint256 public constant BPS_DENOMINATOR = 10_000;
    /// @notice Protocol fee in basis points. Fixed at zero for the MVP.
    uint256 public constant PROTOCOL_FEE_BPS = 0;
    /// @notice Maximum accepted root-window size.
    uint256 public constant MAX_ROOT_WINDOW = 1_024;

    /// @notice Per-pool configuration and Merkle-tree metadata.
    struct Pool {
        uint256 denomination;
        uint32 rootWindow;
        uint32 maturity;
        bool paused;
        bool exists;
        uint256 leafCount;
        bytes32 currentRoot;
    }

    /// @notice Proof verifier. Immutable: changing it requires a new deployment.
    IVerifier public immutable verifier;
    /// @notice Pool operator. Can only create pools and pause/resume them.
    address public immutable owner;

    mapping(bytes32 => Pool) private _pools;
    mapping(uint256 => bytes32) private _poolIdByDenomination;
    mapping(bytes32 => mapping(uint256 => bytes32)) private _nodes;
    mapping(bytes32 => bytes32[]) private _rootHistory;
    mapping(bytes32 => uint256) private _rootStart;
    mapping(bytes32 => mapping(bytes32 => bool)) private _knownRoot;
    mapping(bytes32 => mapping(bytes32 => uint256)) private _rootTimestamp;
    mapping(bytes32 => mapping(bytes32 => uint256)) private _rootOccurrences;
    mapping(bytes32 => mapping(bytes32 => bool)) private _nullifierSpent;

    /// @dev _zeroHashes[level] is the root of an empty subtree of height `level`.
    bytes32[] private _zeroHashes;

    uint256 private _reentrancyStatus = 1;

    /// @notice Emitted when a commitment is inserted into a pool tree.
    event Deposit(bytes32 indexed poolId, bytes32 commitment, uint256 leafIndex, uint256 timestamp);
    /// @notice Emitted when a note is withdrawn. `fee` is relayerFee + protocolFee.
    event Withdrawal(
        bytes32 indexed poolId, bytes32 nullifier, address recipient, uint256 fee, uint256 timestamp
    );
    /// @notice Emitted when a new deposit root becomes current.
    event RootUpdated(bytes32 indexed poolId, bytes32 root, uint256 leafIndex);
    /// @notice Emitted when the operator pauses a pool.
    event PoolPaused(bytes32 indexed poolId, string reason);
    /// @notice Emitted when the operator resumes a pool.
    event PoolResumed(bytes32 indexed poolId);
    /// @notice Emitted when a pool is created.
    event PoolCreated(
        bytes32 indexed poolId, uint256 denomination, uint32 rootWindow, uint32 maturity
    );

    error NotOwner();
    error InvalidVerifier();
    error InvalidPoolId();
    error InvalidDenomination();
    error InvalidRootWindow(uint256 rootWindow);
    error PoolAlreadyExists(bytes32 poolId);
    error DenominationAlreadyRegistered(uint256 denomination, bytes32 poolId);
    error UnknownDenomination(uint256 amount);
    error UnknownPool(bytes32 poolId);
    error PoolIsPaused(bytes32 poolId);
    error InvalidCommitment();
    error TreeFull(bytes32 poolId);
    error InvalidRecipient();
    error InvalidNullifier();
    error UnknownRoot(bytes32 poolId, bytes32 root);
    error MaturityNotReached(uint256 readyAt);
    error NullifierAlreadySpent(bytes32 poolId, bytes32 nullifier);
    error FeeTooHigh(uint256 fee, uint256 maxFee);
    error InvalidProof();
    error ZeroPayout();
    error TransferFailed();
    error DirectEthTransferNotAllowed();
    error Reentrancy();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier nonReentrant() {
        if (_reentrancyStatus != 1) revert Reentrancy();
        _reentrancyStatus = 2;
        _;
        _reentrancyStatus = 1;
    }

    /// @param verifier_ Proof verifier address. Must be non-zero.
    constructor(address verifier_) {
        if (verifier_ == address(0)) revert InvalidVerifier();
        verifier = IVerifier(verifier_);
        owner = msg.sender;

        _zeroHashes.push(bytes32(0));
        for (uint256 level = 0; level < TREE_DEPTH; level++) {
            bytes32 previous = _zeroHashes[level];
            _zeroHashes.push(keccak256(abi.encodePacked(previous, previous)));
        }
    }

    /// @notice Create a fixed-denomination ETH pool.
    /// @param poolId Unique bytes32 pool identifier.
    /// @param denomination Exact deposit amount in wei.
    /// @param rootWindow Number of recent deposit roots accepted for withdrawal.
    /// @param maturity Seconds a root must age before withdrawals against it are allowed.
    function createPool(bytes32 poolId, uint256 denomination, uint32 rootWindow, uint32 maturity)
        external
        onlyOwner
    {
        if (poolId == bytes32(0)) revert InvalidPoolId();
        if (denomination == 0 || denomination > type(uint256).max / BPS_DENOMINATOR) {
            revert InvalidDenomination();
        }
        if (rootWindow == 0 || rootWindow > MAX_ROOT_WINDOW) {
            revert InvalidRootWindow(rootWindow);
        }
        if (_pools[poolId].exists) revert PoolAlreadyExists(poolId);

        bytes32 existingPool = _poolIdByDenomination[denomination];
        if (existingPool != bytes32(0)) {
            revert DenominationAlreadyRegistered(denomination, existingPool);
        }

        bytes32 initialRoot = _zeroHashes[TREE_DEPTH];
        _pools[poolId] = Pool({
            denomination: denomination,
            rootWindow: rootWindow,
            maturity: maturity,
            paused: false,
            exists: true,
            leafCount: 0,
            currentRoot: initialRoot
        });
        _poolIdByDenomination[denomination] = poolId;
        _rootHistory[poolId].push(initialRoot);
        _knownRoot[poolId][initialRoot] = true;
        _rootTimestamp[poolId][initialRoot] = block.timestamp;
        _rootOccurrences[poolId][initialRoot] = 1;

        emit PoolCreated(poolId, denomination, rootWindow, maturity);
    }

    /// @notice Deposit one note commitment into the pool matching msg.value.
    /// @dev The pool is selected by exact denomination; any other value reverts.
    /// @param commitment Note commitment, must be non-zero.
    function deposit(bytes32 commitment) external payable {
        bytes32 poolId = _poolIdByDenomination[msg.value];
        if (poolId == bytes32(0)) revert UnknownDenomination(msg.value);

        Pool storage pool = _pools[poolId];
        if (pool.paused) revert PoolIsPaused(poolId);
        if (commitment == bytes32(0)) revert InvalidCommitment();

        uint256 leafIndex = pool.leafCount;
        if (leafIndex >= MAX_LEAVES) revert TreeFull(poolId);

        pool.leafCount = leafIndex + 1;
        _insert(poolId, leafIndex, commitment);

        bytes32 newRoot = _nodes[poolId][1];
        pool.currentRoot = newRoot;
        _pushRoot(poolId, newRoot);

        emit Deposit(poolId, commitment, leafIndex, block.timestamp);
        emit RootUpdated(poolId, newRoot, leafIndex);
    }

    /// @notice Withdraw a note from a pool.
    /// @param proof Verifier-specific proof bytes.
    /// @param root Merkle root the proof targets; must be inside the pool's root window.
    /// @param nullifier Nullifier for this note; spendable once per pool.
    /// @param recipient Address receiving the denomination minus fees.
    /// @param relayerFee Fee paid to msg.sender (the relayer), in wei.
    /// @param poolId Pool to withdraw from.
    function withdraw(
        bytes calldata proof,
        bytes32 root,
        bytes32 nullifier,
        address payable recipient,
        uint256 relayerFee,
        bytes32 poolId
    ) external nonReentrant {
        Pool storage pool = _pools[poolId];
        if (!pool.exists) revert UnknownPool(poolId);
        if (pool.paused) revert PoolIsPaused(poolId);
        if (recipient == address(0)) revert InvalidRecipient();
        if (nullifier == bytes32(0)) revert InvalidNullifier();
        if (!_knownRoot[poolId][root]) revert UnknownRoot(poolId, root);

        uint256 readyAt = _rootTimestamp[poolId][root] + pool.maturity;
        if (block.timestamp < readyAt) revert MaturityNotReached(readyAt);

        if (_nullifierSpent[poolId][nullifier]) {
            revert NullifierAlreadySpent(poolId, nullifier);
        }

        if (!verifier.verifyProof(proof, root, nullifier, recipient, relayerFee, poolId)) {
            revert InvalidProof();
        }

        uint256 denomination = pool.denomination;
        uint256 protocolFee = (denomination * PROTOCOL_FEE_BPS) / BPS_DENOMINATOR;
        uint256 maxAllowedFee = (denomination * MAX_FEE_BPS) / BPS_DENOMINATOR;
        uint256 totalFee = relayerFee + protocolFee;
        if (totalFee > maxAllowedFee) revert FeeTooHigh(totalFee, maxAllowedFee);

        uint256 recipientAmount = denomination - totalFee;
        if (recipientAmount == 0) revert ZeroPayout();

        _nullifierSpent[poolId][nullifier] = true;

        if (relayerFee != 0) {
            _sendValue(payable(msg.sender), relayerFee);
        }
        if (protocolFee != 0) {
            _sendValue(payable(owner), protocolFee);
        }
        _sendValue(recipient, recipientAmount);

        emit Withdrawal(poolId, nullifier, recipient, totalFee, block.timestamp);
    }

    /// @notice Pause deposits and withdrawals for a pool. Owner only.
    function pause(bytes32 poolId, string calldata reason) external onlyOwner {
        Pool storage pool = _pools[poolId];
        if (!pool.exists) revert UnknownPool(poolId);
        pool.paused = true;
        emit PoolPaused(poolId, reason);
    }

    /// @notice Resume deposits and withdrawals for a pool. Owner only.
    function resume(bytes32 poolId) external onlyOwner {
        Pool storage pool = _pools[poolId];
        if (!pool.exists) revert UnknownPool(poolId);
        pool.paused = false;
        emit PoolResumed(poolId);
    }

    /// @notice Returns pool configuration and current tree state.
    function poolInfo(bytes32 poolId)
        external
        view
        returns (
            uint256 denomination_,
            uint32 rootWindow_,
            bool paused_,
            uint256 leafCount_,
            bytes32 currentRoot_,
            bool exists_
        )
    {
        Pool storage pool = _pools[poolId];
        return (
            pool.denomination,
            pool.rootWindow,
            pool.paused,
            pool.leafCount,
            pool.currentRoot,
            pool.exists
        );
    }

    /// @notice Returns the denomination configured for a pool.
    function denominationOf(bytes32 poolId) external view returns (uint256) {
        return _pools[poolId].denomination;
    }

    /// @notice Returns the current Merkle root for a pool.
    function currentRoot(bytes32 poolId) external view returns (bytes32) {
        return _pools[poolId].currentRoot;
    }

    /// @notice Returns the number of commitments inserted into a pool.
    function leafCount(bytes32 poolId) external view returns (uint256) {
        return _pools[poolId].leafCount;
    }

    /// @notice Returns the pool registered for an exact denomination.
    function poolIdForDenomination(uint256 denomination) external view returns (bytes32) {
        return _poolIdByDenomination[denomination];
    }

    /// @notice Returns true when a root is inside the pool's current root window.
    function isKnownRoot(bytes32 poolId, bytes32 root) external view returns (bool) {
        return _knownRoot[poolId][root];
    }

    /// @notice Returns when a root was accepted, or zero if it is not in the root window.
    function rootTimestamp(bytes32 poolId, bytes32 root) external view returns (uint256) {
        return _rootTimestamp[poolId][root];
    }

    /// @notice Returns the maturity period configured for a pool, in seconds.
    function maturityOf(bytes32 poolId) external view returns (uint32) {
        return _pools[poolId].maturity;
    }

    /// @notice Returns true when a nullifier has been spent in a pool.
    function isNullifierSpent(bytes32 poolId, bytes32 nullifier) external view returns (bool) {
        return _nullifierSpent[poolId][nullifier];
    }

    /// @notice Maximum total fee for a pool's denomination.
    function maxFee(bytes32 poolId) external view returns (uint256) {
        return (_pools[poolId].denomination * MAX_FEE_BPS) / BPS_DENOMINATOR;
    }

    /// @notice Computes the withdrawal payout for a fee quote.
    /// @return recipientAmount Amount the recipient receives.
    /// @return protocolFee Protocol fee accrued by the pool (zero in the MVP).
    /// @return totalFee Sum of the relayer fee and protocol fee.
    function quoteWithdrawal(bytes32 poolId, uint256 relayerFee)
        external
        view
        returns (uint256 recipientAmount, uint256 protocolFee, uint256 totalFee)
    {
        Pool storage pool = _pools[poolId];
        if (!pool.exists) revert UnknownPool(poolId);

        uint256 denomination = pool.denomination;
        protocolFee = (denomination * PROTOCOL_FEE_BPS) / BPS_DENOMINATOR;
        totalFee = relayerFee + protocolFee;

        uint256 maxPoolFee = (denomination * MAX_FEE_BPS) / BPS_DENOMINATOR;
        if (totalFee > maxPoolFee) revert FeeTooHigh(totalFee, maxPoolFee);

        recipientAmount = denomination - totalFee;
    }

    /// @dev Insert a leaf and recompute its path using a sparse heap-indexed tree.
    function _insert(bytes32 poolId, uint256 leafIndex, bytes32 commitment) private {
        uint256 nodeIndex = (uint256(1) << TREE_DEPTH) + leafIndex;
        _nodes[poolId][nodeIndex] = commitment;

        for (uint256 level = 0; level < TREE_DEPTH; level++) {
            nodeIndex >>= 1;
            uint256 leftIndex = nodeIndex << 1;

            bytes32 left = _nodes[poolId][leftIndex];
            bytes32 right = _nodes[poolId][leftIndex + 1];
            if (left == bytes32(0)) left = _zeroHashes[level];
            if (right == bytes32(0)) right = _zeroHashes[level];

            _nodes[poolId][nodeIndex] = keccak256(abi.encodePacked(left, right));
        }
    }

    /// @dev Add a root to the bounded history and evict the oldest root if necessary.
    function _pushRoot(bytes32 poolId, bytes32 root) private {
        Pool storage pool = _pools[poolId];
        bytes32[] storage history = _rootHistory[poolId];
        history.push(root);
        _knownRoot[poolId][root] = true;
        _rootTimestamp[poolId][root] = block.timestamp;
        _rootOccurrences[poolId][root] += 1;

        uint256 start = _rootStart[poolId];
        if (history.length - start > pool.rootWindow) {
            bytes32 evictedRoot = history[start];
            uint256 occurrences = _rootOccurrences[poolId][evictedRoot];

            // Only delete the timestamp if this was the last live occurrence of the
            // root. Duplicate roots are practically impossible, but this keeps
            // eviction safe if one ever appears.
            if (occurrences <= 1) {
                delete _rootOccurrences[poolId][evictedRoot];
                delete _knownRoot[poolId][evictedRoot];
                delete _rootTimestamp[poolId][evictedRoot];
            } else {
                _rootOccurrences[poolId][evictedRoot] = occurrences - 1;
            }

            _rootStart[poolId] = start + 1;
        }
    }

    /// @dev Send ETH with a low-level call and bubble failure as a typed error.
    function _sendValue(address payable to, uint256 amount) private {
        (bool success,) = to.call{value: amount}("");
        if (!success) revert TransferFailed();
    }

    /// @dev The pool does not accept plain ETH transfers; funds must enter through deposit().
    receive() external payable {
        revert DirectEthTransferNotAllowed();
    }
}
