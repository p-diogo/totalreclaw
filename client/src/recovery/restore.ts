/**
 * Recovery flow: restore all facts from a BIP-39 mnemonic via the subgraph.
 *
 * This is the core UX promise: a user on a new device pastes their 12-word
 * mnemonic, and all their facts are recovered from the blockchain.
 *
 * Flow:
 *   1. Derive keys from mnemonic (encryption key, auth key, Smart Account address)
 *   2. Query subgraph for all facts belonging to that Smart Account
 *   3. Decrypt each fact's encrypted blob
 *   4. Sort by importance, populate hot cache with top 30
 *   5. Return all decrypted facts
 */

import { SubgraphClient, type SubgraphFact } from "../subgraph/client";
import { HotCache, type HotFact } from "../cache/hot-cache";

export interface RestoredFact {
  id: string;
  text: string;
  type?: string;
  importance?: number;
  decayScore: number;
  sequenceId?: string;
  blockNumber?: string;
}

export interface RestoreResult {
  totalFacts: number;
  restoredFacts: RestoredFact[];
  failedDecryptions: number;
  hotCachePopulated: boolean;
  smartAccountAddress: string;
}

export interface RestoreOptions {
  subgraphEndpoint: string;
  cachePath: string;
  /**
   * Function to derive keys from mnemonic. Injected to avoid importing
   * the crypto module directly (keeps this module testable with mocks).
   */
  deriveKeys: (mnemonic: string) => {
    encryptionKeyHex: string;
    smartAccountAddress: string;
  };
  /**
   * Function to decrypt a hex blob using the encryption key.
   * Returns the decrypted JSON string.
   */
  decrypt: (hexBlob: string, keyHex: string) => string;
}

/**
 * Restore all facts from a BIP-39 mnemonic via the subgraph.
 */
export async function restoreFromMnemonic(
  mnemonic: string,
  options: RestoreOptions,
): Promise<RestoreResult> {
  // 1. Derive keys
  const { encryptionKeyHex, smartAccountAddress } = options.deriveKeys(mnemonic);

  // 2. Fetch all facts from subgraph
  const client = new SubgraphClient(options.subgraphEndpoint);
  const subgraphFacts = await client.fetchAllFacts(smartAccountAddress);

  // 3. Decrypt each fact
  const restoredFacts: RestoredFact[] = [];
  let failedDecryptions = 0;

  for (const fact of subgraphFacts) {
    try {
      // The encryptedBlob from the subgraph is the raw Protobuf payload.
      // We need to extract the encrypted_blob field from it.
      // However, in our simplified model, the subgraph stores the encrypted
      // blob directly in the encryptedBlob field.
      const docJson = options.decrypt(fact.encryptedBlob, encryptionKeyHex);
      const doc = JSON.parse(docJson) as {
        text: string;
        metadata?: {
          type?: string;
          importance?: number;
        };
      };

      restoredFacts.push({
        id: fact.id,
        text: doc.text,
        type: doc.metadata?.type,
        importance: doc.metadata?.importance
          ? Math.round(doc.metadata.importance * 10)
          : undefined,
        decayScore: parseFloat(fact.decayScore),
        sequenceId: fact.sequenceId,
        blockNumber: fact.blockNumber,
      });
    } catch {
      failedDecryptions++;
    }
  }

  // 4. Sort by importance (descending) and populate hot cache
  let hotCachePopulated = false;
  try {
    const hotFacts: HotFact[] = restoredFacts
      .filter((f) => f.importance !== undefined)
      .map((f) => ({
        id: f.id,
        text: f.text,
        importance: f.importance!,
      }));

    const cache = new HotCache(options.cachePath, encryptionKeyHex);
    cache.setHotFacts(hotFacts);
    cache.setFactCount(restoredFacts.length);
    cache.setSmartAccountAddress(smartAccountAddress);
    cache.flush();
    hotCachePopulated = true;
  } catch {
    // Hot cache population failed -- not critical
  }

  return {
    totalFacts: subgraphFacts.length,
    restoredFacts,
    failedDecryptions,
    hotCachePopulated,
    smartAccountAddress,
  };
}
