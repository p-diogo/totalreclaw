/**
 * ERC-4337 UserOperation Builder for TotalReclaw.
 *
 * Builds UserOperations that target the EventfulDataEdge contract on Base L2.
 * The calldata is the encrypted Protobuf-serialized TotalReclawFact.
 *
 * Flow:
 *   1. Client encrypts fact + serializes to Protobuf (existing code)
 *   2. This module wraps the encrypted bytes into a UserOperation
 *   3. The UserOp is signed with the seed-derived private key
 *   4. The signed UserOp is sent to the /relay endpoint (Task 8)
 *   5. The server submits to Pimlico bundler -> Base L2 -> EventfulDataEdge
 *
 * Dependencies:
 *   - viem for signing and encoding
 */

export interface UserOperationConfig {
  /** 32-byte private key derived from BIP-39 seed */
  privateKey: Buffer;
  /** EventfulDataEdge contract address */
  dataEdgeAddress: `0x${string}`;
  /** ERC-4337 EntryPoint address */
  entryPointAddress: `0x${string}`;
  /** Chain ID (84532 for Base Sepolia, 8453 for Base mainnet) */
  chainId: number;
  /** Encrypted Protobuf payload to write on-chain */
  encryptedPayload: Buffer;
  /** Optional: override nonce (for sequential operations) */
  nonce?: bigint;
}

export interface UserOperationResult {
  /** Hex-encoded calldata (the encrypted payload) */
  callData: string;
  /** Target contract address */
  target: string;
  /** Operation nonce */
  nonce: bigint;
  /** Sender (Smart Account) address */
  sender: string;
  /** Full UserOperation JSON for submission to bundler */
  userOpJson: Record<string, unknown>;
}

/**
 * Encode an encrypted fact as hex calldata for the EventfulDataEdge fallback().
 *
 * The EventfulDataEdge contract uses a fallback() function, so the calldata
 * IS the encrypted payload directly (no function selector).
 *
 * @param encryptedBlob - Encrypted Protobuf bytes
 * @returns Hex-encoded calldata string (0x-prefixed)
 */
export function encodeFactAsCalldata(encryptedBlob: Buffer): string {
  if (encryptedBlob.length === 0) return "0x";
  return "0x" + encryptedBlob.toString("hex");
}

/**
 * Build an ERC-4337 UserOperation for writing an encrypted fact on-chain.
 *
 * This creates the UserOperation structure but does NOT submit it. The caller
 * should send the result to the /relay endpoint.
 *
 * @param config - UserOperation configuration
 * @returns UserOperation ready for submission
 */
export async function buildUserOperation(
  config: UserOperationConfig
): Promise<UserOperationResult> {
  const {
    privateKey,
    dataEdgeAddress,
    entryPointAddress,
    encryptedPayload,
    nonce,
  } = config;

  // Encode the encrypted payload as calldata
  const callData = encodeFactAsCalldata(encryptedPayload);

  // Compute the sender address from the private key
  const { privateKeyToAccount } = await import("viem/accounts");
  const account = privateKeyToAccount(
    `0x${privateKey.toString("hex")}` as `0x${string}`
  );
  const sender = account.address;

  // Build the UserOperation JSON
  // This is the structure expected by the Pimlico bundler
  const userOpJson: Record<string, unknown> = {
    sender,
    nonce: nonce !== undefined ? `0x${nonce.toString(16)}` : "0x0",
    // initCode is empty for already-deployed Smart Accounts
    // For first-time users, this would contain the factory + creation calldata
    initCode: "0x",
    // The Smart Account's execute() will be called with (target, value, data)
    // For simplicity, we encode this as: target + calldata
    callData,
    // Gas limits -- these are estimates; the bundler will simulate and adjust
    callGasLimit: "0x50000", // 327,680
    verificationGasLimit: "0x60000", // 393,216
    preVerificationGas: "0x10000", // 65,536
    maxFeePerGas: "0x0", // Will be set by bundler
    maxPriorityFeePerGas: "0x0", // Will be set by bundler
    paymasterAndData: "0x", // Paymaster address + data (set by relay server)
    signature: "0x", // Will be signed below
  };

  // Sign the UserOperation
  // In production, this would use the full ERC-4337 UserOp hash
  // For PoC, we sign a simplified hash of the critical fields
  const { keccak256, encodePacked } = await import("viem");
  const messageHash = keccak256(
    encodePacked(
      ["address", "uint256", "bytes", "address"],
      [
        sender as `0x${string}`,
        nonce !== undefined ? nonce : 0n,
        callData as `0x${string}`,
        entryPointAddress,
      ]
    )
  );

  const signature = await account.signMessage({
    message: { raw: messageHash as `0x${string}` },
  });
  userOpJson.signature = signature;

  return {
    callData,
    target: dataEdgeAddress,
    nonce: nonce !== undefined ? nonce : 0n,
    sender,
    userOpJson,
  };
}

/**
 * Submit a UserOperation to the relay server.
 *
 * This sends the signed UserOp JSON to the TotalReclaw server's /relay endpoint,
 * which forwards it to the Pimlico bundler.
 *
 * @param relayUrl - The /relay endpoint URL (e.g., "https://api.totalreclaw.dev/relay")
 * @param userOp - The UserOperation result from buildUserOperation()
 * @returns Transaction hash from the bundler
 */
export async function submitUserOperation(
  relayUrl: string,
  userOp: UserOperationResult
): Promise<string> {
  const response = await fetch(relayUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      userOperation: userOp.userOpJson,
      target: userOp.target,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(
      `Relay submission failed (${response.status}): ${JSON.stringify(error)}`
    );
  }

  const result = await response.json() as { transactionHash: string };
  return result.transactionHash;
}
