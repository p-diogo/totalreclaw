// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title EventfulDataEdge
 * @notice Minimal data-availability contract for OpenMemory.
 *
 * Any call to this contract (via fallback) emits a Log(bytes) event containing
 * the raw calldata. The subgraph indexes these events. Access is restricted to
 * the ERC-4337 EntryPoint address so only validated UserOperations can write.
 *
 * Design rationale:
 * - No storage slots — all data lives in events (cheapest on-chain DA).
 * - fallback() instead of a named function — saves ~200 gas on function selector.
 * - Single event type keeps subgraph mapping simple.
 *
 * Gas cost: ~1,200 base + 16 gas/non-zero-byte + 8 gas/zero-byte of calldata.
 * A typical 256-byte encrypted fact costs ~5,300 gas (~$0.0002 on Base L2).
 */
contract EventfulDataEdge {
    /// @notice Emitted for every write. Contains the full encrypted Protobuf payload.
    event Log(bytes data);

    /// @notice The ERC-4337 EntryPoint address. Only this address can trigger writes.
    address public entryPoint;

    /// @notice Contract owner (deployer). Can update entryPoint.
    address public owner;

    /// @param _entryPoint The ERC-4337 EntryPoint contract address on this chain.
    constructor(address _entryPoint) {
        require(_entryPoint != address(0), "Invalid entryPoint");
        entryPoint = _entryPoint;
        owner = msg.sender;
    }

    /// @notice Update the EntryPoint address (e.g., after ERC-4337 upgrade).
    /// @param _newEntryPoint New EntryPoint contract address.
    function setEntryPoint(address _newEntryPoint) external {
        require(msg.sender == owner, "Only owner");
        require(_newEntryPoint != address(0), "Invalid entryPoint");
        entryPoint = _newEntryPoint;
    }

    /// @notice Transfer ownership.
    /// @param _newOwner New owner address.
    function transferOwnership(address _newOwner) external {
        require(msg.sender == owner, "Only owner");
        require(_newOwner != address(0), "Invalid owner");
        owner = _newOwner;
    }

    /**
     * @notice Fallback function — emits the full calldata as a Log event.
     * @dev Only callable by the EntryPoint. This is the primary write path:
     *      EntryPoint validates UserOp signature -> calls Smart Account ->
     *      Smart Account calls this contract -> fallback() emits Log(calldata).
     *
     *      In practice, the Smart Account's execute() calls this contract with
     *      the encrypted Protobuf payload as calldata.
     */
    fallback() external payable {
        require(msg.sender == entryPoint, "Only EntryPoint");
        emit Log(msg.data);
    }

    /// @notice Receive ETH (no-op, but required for payable fallback pattern).
    receive() external payable {}
}
