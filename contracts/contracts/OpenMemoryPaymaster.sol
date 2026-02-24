// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title OpenMemoryPaymaster
 * @notice ERC-4337 Verifying Paymaster that sponsors gas for OpenMemory writes.
 *
 * Validation rules:
 * 1. UserOperation must target the EventfulDataEdge contract.
 * 2. Sender must not exceed the per-window rate limit.
 * 3. Paymaster must have sufficient ETH balance.
 *
 * Rate limiting:
 * - Tracked per sender (Smart Account address).
 * - Sliding window: maxOpsPerWindow operations per rateLimitWindow seconds.
 * - Owner can adjust limits without redeploying.
 *
 * Funding:
 * - Owner deposits ETH into this contract.
 * - EntryPoint draws from this contract to cover gas.
 * - Owner can withdraw excess ETH.
 */
contract OpenMemoryPaymaster {

    // --- State ---

    address public immutable entryPoint;
    address public owner;
    address public dataEdge;
    uint256 public maxOpsPerWindow;
    uint256 public rateLimitWindow;

    struct RateLimit {
        uint256 count;
        uint256 windowStart;
    }

    mapping(address => RateLimit) public rateLimits;

    // --- Events ---

    event Funded(address indexed from, uint256 amount);
    event Withdrawn(address indexed to, uint256 amount);
    event RateLimitsUpdated(uint256 maxOps, uint256 window);
    event DataEdgeUpdated(address indexed newDataEdge);
    event OperationSponsored(address indexed sender, uint256 opsInWindow);

    // --- Constructor ---

    constructor(
        address _entryPoint,
        address _dataEdge,
        uint256 _maxOpsPerWindow,
        uint256 _rateLimitWindow
    ) {
        require(_entryPoint != address(0), "Invalid entryPoint");
        require(_dataEdge != address(0), "Invalid dataEdge");
        require(_maxOpsPerWindow > 0, "Invalid maxOps");
        require(_rateLimitWindow > 0, "Invalid window");

        entryPoint = _entryPoint;
        dataEdge = _dataEdge;
        maxOpsPerWindow = _maxOpsPerWindow;
        rateLimitWindow = _rateLimitWindow;
        owner = msg.sender;
    }

    // --- Owner Functions ---

    function setRateLimits(uint256 _maxOps, uint256 _window) external {
        require(msg.sender == owner, "Only owner");
        require(_maxOps > 0, "Invalid maxOps");
        require(_window > 0, "Invalid window");
        maxOpsPerWindow = _maxOps;
        rateLimitWindow = _window;
        emit RateLimitsUpdated(_maxOps, _window);
    }

    function setDataEdge(address _newDataEdge) external {
        require(msg.sender == owner, "Only owner");
        require(_newDataEdge != address(0), "Invalid dataEdge");
        dataEdge = _newDataEdge;
        emit DataEdgeUpdated(_newDataEdge);
    }

    function transferOwnership(address _newOwner) external {
        require(msg.sender == owner, "Only owner");
        require(_newOwner != address(0), "Invalid owner");
        owner = _newOwner;
    }

    function withdraw(uint256 amount) external {
        require(msg.sender == owner, "Only owner");
        require(amount <= address(this).balance, "Insufficient balance");
        (bool success, ) = owner.call{value: amount}("");
        require(success, "Withdraw failed");
        emit Withdrawn(owner, amount);
    }

    // --- Rate Limit Queries ---

    function getOpsCount(address sender) external view returns (uint256) {
        RateLimit memory rl = rateLimits[sender];
        if (block.timestamp >= rl.windowStart + rateLimitWindow) {
            return 0; // Window expired
        }
        return rl.count;
    }

    // --- Internal: Rate Limit Check ---

    function _checkAndIncrementRateLimit(address sender) internal returns (bool) {
        RateLimit storage rl = rateLimits[sender];

        // Reset window if expired
        if (block.timestamp >= rl.windowStart + rateLimitWindow) {
            rl.count = 0;
            rl.windowStart = block.timestamp;
        }

        // Check limit
        if (rl.count >= maxOpsPerWindow) {
            return false; // Rate limited
        }

        rl.count++;
        emit OperationSponsored(sender, rl.count);
        return true;
    }

    // --- ERC-4337 Paymaster Interface ---
    //
    // The full IPaymaster interface has two functions:
    //   validatePaymasterUserOp(UserOperation, bytes32, uint256) -> (bytes, uint256)
    //   postOp(PostOpMode, bytes, uint256, uint256)
    //
    // For the PoC, we implement a simplified version. The production version
    // should inherit from BasePaymaster in @account-abstraction/contracts.
    //
    // The validatePaymasterUserOp function is called by the EntryPoint during
    // UserOperation validation. It must:
    //   1. Verify the target is our DataEdge contract.
    //   2. Check rate limits for the sender.
    //   3. Return a context (bytes) and validationData (uint256).

    /**
     * @notice Validates whether this paymaster will sponsor a UserOperation.
     * @dev Called by EntryPoint. Simplified for PoC -- production should use
     *      the full PackedUserOperation struct from EntryPoint v0.7.
     * @param sender The Smart Account address initiating the operation.
     * @param target The contract being called (must be dataEdge).
     * @return willSponsor True if the paymaster agrees to sponsor this operation.
     */
    function validateOperation(
        address sender,
        address target
    ) external returns (bool willSponsor) {
        require(msg.sender == entryPoint, "Only EntryPoint");

        // Rule 1: Target must be our DataEdge
        if (target != dataEdge) {
            return false;
        }

        // Rule 2: Sender must not be rate-limited
        if (!_checkAndIncrementRateLimit(sender)) {
            return false;
        }

        return true;
    }

    // --- Receive ETH ---

    receive() external payable {
        emit Funded(msg.sender, msg.value);
    }
}
