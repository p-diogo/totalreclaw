/**
 * OpenMemory Crypto Module
 *
 * Provides cryptographic primitives for zero-knowledge memory operations.
 */

export {
  deriveAuthKey,
  deriveEncryptionKey,
  deriveKeys,
  generateSalt,
  DEFAULT_KDF_PARAMS,
  createAuthProof,
  verifyAuthProof,
} from './kdf';

export type { KeyDerivationParams } from './kdf';

export {
  encrypt,
  decrypt,
} from './aes';

export type { EncryptedData } from './aes';

export {
  generateBlindIndices,
  generateTrapdoors,
  tokenize,
  sha256Hash,
} from './blind';

// Fingerprint (v0.3.1b dedup)
export {
  normalizeText,
  deriveDedupKey,
  computeContentFingerprint,
} from './fingerprint';

// Seed management (v0.3 subgraph / Phase 3)
export {
  generateMnemonic,
  validateMnemonic,
  mnemonicToKeys,
  mnemonicToSmartAccountAddress,
  storeSeedInKeychain,
  getSeedFromKeychain,
  deleteSeedFromKeychain,
  DERIVATION_PATH,
} from './seed';

export type { SeedDerivedKeys } from './seed';
