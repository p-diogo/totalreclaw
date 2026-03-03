/**
 * Subgraph store path — writes facts on-chain via ERC-4337 UserOps.
 *
 * Used when TOTALRECLAW_SUBGRAPH_MODE=true. Replaces the HTTP POST
 * to /v1/store with an on-chain transaction flow.
 */

export interface SubgraphStoreConfig {
  relayUrl: string;        // Relay endpoint for UserOp submission
  mnemonic: string;        // BIP-39 mnemonic for key derivation
  subgraphEndpoint: string; // GraphQL endpoint for verification
  cachePath: string;        // Hot cache file path
}

export interface FactPayload {
  id: string;
  timestamp: string;
  owner: string;           // Smart Account address (hex)
  encryptedBlob: string;   // Hex-encoded AES-256-GCM ciphertext
  blindIndices: string[];   // SHA-256 hashes (word + LSH)
  decayScore: number;
  source: string;
  contentFp: string;
  agentId: string;
  encryptedEmbedding?: string;
}

/**
 * Encode a fact payload as a minimal Protobuf wire format.
 *
 * Field numbers match server/proto/totalreclaw.proto:
 *   1: id (string), 2: timestamp (string), 3: owner (string),
 *   4: encrypted_blob (bytes), 5: blind_indices (repeated string),
 *   6: decay_score (double), 7: is_active (bool), 8: version (int32),
 *   9: source (string), 10: content_fp (string), 11: agent_id (string),
 *   12: sequence_id (int64), 13: encrypted_embedding (string)
 */
export function encodeFactProtobuf(fact: FactPayload): Buffer {
  const parts: Buffer[] = [];

  // Helper: encode a string field
  const writeString = (fieldNumber: number, value: string) => {
    if (!value) return;
    const data = Buffer.from(value, 'utf-8');
    const key = (fieldNumber << 3) | 2; // wire type 2 = length-delimited
    parts.push(encodeVarint(key));
    parts.push(encodeVarint(data.length));
    parts.push(data);
  };

  // Helper: encode a bytes field
  const writeBytes = (fieldNumber: number, value: Buffer) => {
    const key = (fieldNumber << 3) | 2;
    parts.push(encodeVarint(key));
    parts.push(encodeVarint(value.length));
    parts.push(value);
  };

  // Helper: encode a double field (wire type 1 = 64-bit)
  const writeDouble = (fieldNumber: number, value: number) => {
    const key = (fieldNumber << 3) | 1;
    parts.push(encodeVarint(key));
    const buf = Buffer.alloc(8);
    buf.writeDoubleLE(value);
    parts.push(buf);
  };

  // Helper: encode a varint field (wire type 0)
  const writeVarintField = (fieldNumber: number, value: number) => {
    const key = (fieldNumber << 3) | 0;
    parts.push(encodeVarint(key));
    parts.push(encodeVarint(value));
  };

  // Encode fields
  writeString(1, fact.id);
  writeString(2, fact.timestamp);
  writeString(3, fact.owner);
  writeBytes(4, Buffer.from(fact.encryptedBlob, 'hex'));

  for (const index of fact.blindIndices) {
    writeString(5, index);
  }

  writeDouble(6, fact.decayScore);
  writeVarintField(7, 1); // is_active = true
  writeVarintField(8, 2); // version = 2
  writeString(9, fact.source);
  writeString(10, fact.contentFp);
  writeString(11, fact.agentId);
  // Field 12 (sequence_id) is assigned by the subgraph mapping, not the client
  if (fact.encryptedEmbedding) {
    writeString(13, fact.encryptedEmbedding);
  }

  return Buffer.concat(parts);
}

/** Encode an integer as a Protobuf varint */
function encodeVarint(value: number): Buffer {
  const bytes: number[] = [];
  let v = value >>> 0; // unsigned
  while (v > 0x7f) {
    bytes.push((v & 0x7f) | 0x80);
    v >>>= 7;
  }
  bytes.push(v & 0x7f);
  return Buffer.from(bytes);
}

/**
 * Submit a fact to the relay for on-chain storage.
 *
 * In production, this builds a full ERC-4337 UserOp and submits it.
 * For local development (Hardhat), we can submit a direct transaction
 * since the deployer is the EntryPoint.
 */
export async function submitToRelay(
  protobufPayload: Buffer,
  config: SubgraphStoreConfig,
): Promise<{ txHash: string; success: boolean }> {
  const response = await fetch(`${config.relayUrl}/v1/relay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      calldata: protobufPayload.toString('hex'),
      // For local dev, the relay submits directly to Hardhat
      // For production, this would include the full signed UserOp
    }),
  });

  if (!response.ok) {
    throw new Error(`Relay submission failed: ${response.status} ${response.statusText}`);
  }

  const result = await response.json() as { tx_hash?: string; success?: boolean };
  return {
    txHash: result.tx_hash || '',
    success: result.success !== false,
  };
}

/**
 * Check if subgraph mode is enabled.
 */
export function isSubgraphMode(): boolean {
  return process.env.TOTALRECLAW_SUBGRAPH_MODE === 'true';
}

/**
 * Get subgraph configuration from environment variables.
 */
export function getSubgraphConfig(): SubgraphStoreConfig {
  return {
    relayUrl: process.env.TOTALRECLAW_RELAY_URL || 'http://localhost:8545',
    mnemonic: process.env.TOTALRECLAW_MASTER_PASSWORD || '',
    subgraphEndpoint: process.env.TOTALRECLAW_SUBGRAPH_ENDPOINT || 'http://localhost:8000/subgraphs/name/totalreclaw',
    cachePath: process.env.TOTALRECLAW_CACHE_PATH || `${process.env.HOME}/.totalreclaw/cache.enc`,
  };
}
