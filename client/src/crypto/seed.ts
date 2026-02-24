/**
 * BIP-39 Seed Management for OpenMemory Phase 3 (Subgraph).
 *
 * The user's 12-word mnemonic is the ONLY secret. From it we derive:
 *   1. A private key (for signing UserOperations)
 *   2. An EOA address (for computing the Smart Account counterfactual address)
 *   3. An encryption key (for AES-256-GCM, same as Phase 1-2)
 *   4. An auth key (for HMAC operations, same as Phase 1-2)
 *
 * Derivation:
 *   mnemonic -> BIP-39 seed (512 bits)
 *     -> BIP-32/44 derive m/44'/60'/0'/0/0 -> private key (256 bits) + EOA address
 *     -> HKDF(private_key, "openmemory-encryption-key-v1") -> encryption key (256 bits)
 *     -> HKDF(private_key, "openmemory-auth-key-v1") -> auth key (256 bits)
 *
 * The encryption key derivation uses the SAME HKDF info strings as
 * client/src/crypto/kdf.ts so that the AES and blind-index modules work
 * identically regardless of whether the key came from a master password
 * or a BIP-39 seed.
 */

import * as bip39 from "bip39";
import * as crypto from "crypto";

/**
 * Standard Ethereum BIP-44 derivation path.
 */
export const DERIVATION_PATH = "m/44'/60'/0'/0/0";

/**
 * Keys derived from a BIP-39 mnemonic.
 */
export interface SeedDerivedKeys {
  /** 32-byte private key for signing UserOperations */
  privateKey: Buffer;
  /** Ethereum EOA address (checksummed hex) */
  eoaAddress: string;
  /** 32-byte encryption key for AES-256-GCM (same usage as kdf.ts) */
  encryptionKey: Buffer;
  /** 32-byte auth key for HMAC operations (same usage as kdf.ts) */
  authKey: Buffer;
}

/**
 * Generate a new 12-word BIP-39 mnemonic.
 *
 * Uses 128 bits of entropy (12 words). This is the standard for Ethereum
 * wallets and provides ~2^128 security -- more than sufficient.
 *
 * @returns 12-word mnemonic string (space-separated)
 */
export function generateMnemonic(): string {
  return bip39.generateMnemonic(128); // 128 bits = 12 words
}

/**
 * Validate a BIP-39 mnemonic.
 *
 * @param mnemonic - Space-separated word list
 * @returns true if valid
 */
export function validateMnemonic(mnemonic: string): boolean {
  if (!mnemonic || mnemonic.trim().length === 0) return false;
  return bip39.validateMnemonic(mnemonic);
}

/**
 * Derive all keys from a BIP-39 mnemonic.
 *
 * This is the primary entry point for the seed path. It produces all the
 * keys needed for OpenMemory operations:
 *   - privateKey: for signing ERC-4337 UserOperations
 *   - eoaAddress: for computing the Smart Account counterfactual address
 *   - encryptionKey: for AES-256-GCM encryption (identical to kdf.ts output)
 *   - authKey: for HMAC authentication (identical to kdf.ts output)
 *
 * @param mnemonic - 12-word BIP-39 mnemonic
 * @returns All derived keys
 */
export async function mnemonicToKeys(mnemonic: string): Promise<SeedDerivedKeys> {
  if (!validateMnemonic(mnemonic)) {
    throw new Error("Invalid BIP-39 mnemonic");
  }

  // Step 1: Mnemonic -> BIP-39 seed (512 bits)
  const seed = bip39.mnemonicToSeedSync(mnemonic);

  // Step 2: BIP-32 HD key derivation -> private key at m/44'/60'/0'/0/0
  // Use viem's HDKey for BIP-32 derivation
  const { HDKey } = await import("viem/accounts");
  const hdKey = HDKey.fromMasterSeed(seed);
  const derived = hdKey.derive(DERIVATION_PATH);

  if (!derived.privateKey) {
    throw new Error("Failed to derive private key from seed");
  }

  const privateKey = Buffer.from(derived.privateKey);

  // Step 3: Compute EOA address from private key using viem
  const { privateKeyToAccount } = await import("viem/accounts");
  const account = privateKeyToAccount(
    `0x${privateKey.toString("hex")}` as `0x${string}`
  );
  const eoaAddress = account.address;

  // Step 4: Derive OpenMemory keys using HKDF with same info strings as kdf.ts
  // This ensures the AES and blind-index modules work identically.
  const encryptionKey = hkdfSha256(
    privateKey,
    Buffer.from("openmemory-seed-salt-v1", "utf-8"), // Fixed salt for seed path
    Buffer.from("openmemory-encryption-key-v1", "utf-8"),
    32
  );

  const authKey = hkdfSha256(
    privateKey,
    Buffer.from("openmemory-seed-salt-v1", "utf-8"),
    Buffer.from("openmemory-auth-key-v1", "utf-8"),
    32
  );

  return {
    privateKey,
    eoaAddress,
    encryptionKey,
    authKey,
  };
}

/**
 * Compute the Smart Account counterfactual address from a mnemonic.
 *
 * This is a convenience function for the recovery flow. The Smart Account
 * address is deterministic given the EOA address and the account factory.
 *
 * For the PoC, this returns the EOA address. In production, use the
 * Pimlico/ZeroDev SDK to compute the counterfactual Smart Account address
 * from the EOA + factory + salt.
 *
 * @param mnemonic - 12-word BIP-39 mnemonic
 * @returns Smart Account address (hex string)
 */
export async function mnemonicToSmartAccountAddress(
  mnemonic: string
): Promise<string> {
  const keys = await mnemonicToKeys(mnemonic);
  // TODO: Replace with actual Smart Account counterfactual address computation
  // using Pimlico SDK: toSimpleSmartAccount({ client, owner: eoaAddress, ... })
  // For PoC, we use the EOA address directly.
  return keys.eoaAddress;
}

/**
 * Store a mnemonic in the OS keychain.
 *
 * Reuses the existing keychain module (client/src/credentials/keychain.ts).
 * The mnemonic is stored under the account name "{userId}-seed".
 *
 * @param userId - User identifier
 * @param mnemonic - 12-word mnemonic to store
 */
export async function storeSeedInKeychain(
  userId: string,
  mnemonic: string
): Promise<void> {
  const { storeCredentials } = await import("../credentials/keychain");
  await storeCredentials(`${userId}-seed`, mnemonic);
}

/**
 * Retrieve a mnemonic from the OS keychain.
 *
 * @param userId - User identifier
 * @returns The stored mnemonic, or null if not found
 */
export async function getSeedFromKeychain(
  userId: string
): Promise<string | null> {
  const { getCredentials } = await import("../credentials/keychain");
  return getCredentials(`${userId}-seed`);
}

/**
 * Delete a mnemonic from the OS keychain.
 *
 * @param userId - User identifier
 * @returns true if a credential was deleted
 */
export async function deleteSeedFromKeychain(
  userId: string
): Promise<boolean> {
  const { deleteCredentials } = await import("../credentials/keychain");
  return deleteCredentials(`${userId}-seed`);
}

// --- Internal: HKDF-SHA256 ---

/**
 * HKDF-SHA256 -- identical to the implementation in kdf.ts.
 * Duplicated here to avoid circular imports and keep the seed module self-contained.
 */
function hkdfSha256(
  ikm: Buffer,
  salt: Buffer,
  info: Buffer,
  length: number
): Buffer {
  const prk = crypto.createHmac("sha256", salt).update(ikm).digest();

  const okm = Buffer.alloc(length);
  let t = Buffer.alloc(0);
  let offset = 0;
  let counter = 1;

  while (offset < length) {
    const hmac = crypto.createHmac("sha256", prk);
    hmac.update(t);
    hmac.update(info);
    hmac.update(Buffer.from([counter]));
    t = hmac.digest();

    const copyLength = Math.min(t.length, length - offset);
    t.copy(okm, offset, 0, copyLength);
    offset += copyLength;
    counter++;
  }

  return okm;
}
