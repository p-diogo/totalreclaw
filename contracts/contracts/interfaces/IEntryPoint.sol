// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @dev Minimal IEntryPoint interface — only what EventfulDataEdge needs.
 * Full ERC-4337 EntryPoint interface is provided by the account-abstraction package.
 * For PoC we only use the address for msg.sender checks.
 */
interface IEntryPoint {
    // Intentionally empty — we only use the address for msg.sender checks.
}
