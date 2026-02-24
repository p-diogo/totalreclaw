/**
 * Content Fingerprint Derivation (v0.3.1b)
 *
 * Provides HMAC-SHA256 content fingerprint for exact dedup.
 *
 * Spec: docs/specs/openmemory/server.md v0.3.1b section 8.2
 *
 * Key derivation:
 *   dedup_key = HKDF-SHA256(master_key, salt, "openmemory-dedup-v1", 32)
 *
 * Fingerprint computation:
 *   content_fp = HMAC-SHA256(dedup_key, normalize(plaintext))
 *
 * normalize(text):
 *   1. Unicode NFC normalization
 *   2. Lowercase
 *   3. Collapse whitespace (multiple spaces/tabs/newlines to single space)
 *   4. Trim leading/trailing whitespace
 *   5. UTF-8 encode (implicit in Node.js string handling)
 */

import * as crypto from 'crypto';

/**
 * HKDF context string for dedup key derivation.
 * Separate from auth ("openmemory-auth-key-v1") and encryption
 * ("openmemory-encryption-key-v1") context strings so that key
 * rotation of one does not affect the others.
 */
const DEDUP_KEY_INFO = 'openmemory-dedup-v1';

/**
 * Normalize text for deterministic fingerprinting.
 *
 * Steps (per spec section 8.2):
 * 1. Unicode NFC normalization
 * 2. Lowercase
 * 3. Collapse whitespace (multiple spaces/tabs/newlines to single space)
 * 4. Trim leading/trailing whitespace
 *
 * @param text - Raw plaintext
 * @returns Normalized text ready for HMAC
 */
export function normalizeText(text: string): string {
  return text
    .normalize('NFC')         // 1. Unicode NFC
    .toLowerCase()            // 2. Lowercase
    .replace(/\s+/g, ' ')    // 3. Collapse whitespace
    .trim();                  // 4. Trim
}

/**
 * Derive the dedup key from the master key material using HKDF-SHA256.
 *
 * This uses a separate HKDF context string ("openmemory-dedup-v1") so that
 * the dedup key is independent of the auth and encryption keys.
 *
 * @param masterKeyMaterial - The Argon2id-derived master key (or encryption key)
 * @param salt - The user's salt
 * @returns 32-byte dedup key
 */
export function deriveDedupKey(masterKeyMaterial: Buffer, salt: Buffer): Buffer {
  // Extract phase
  const prk = crypto.createHmac('sha256', salt).update(masterKeyMaterial).digest();

  // Expand phase (single round, 32 bytes = one SHA-256 block)
  const info = Buffer.from(DEDUP_KEY_INFO, 'utf-8');
  const hmac = crypto.createHmac('sha256', prk);
  hmac.update(info);
  hmac.update(Buffer.from([1])); // counter = 1
  return hmac.digest();
}

/**
 * Compute a content fingerprint for exact dedup.
 *
 * The fingerprint is an HMAC-SHA256 of the normalized plaintext,
 * keyed by the dedup key. The server sees the fingerprint but
 * cannot reverse it without the dedup key.
 *
 * @param dedupKey - 32-byte dedup key from deriveDedupKey()
 * @param plaintext - The fact text before encryption
 * @returns Hex-encoded HMAC-SHA256 fingerprint (64 chars)
 */
export function computeContentFingerprint(dedupKey: Buffer, plaintext: string): string {
  const normalized = normalizeText(plaintext);
  const data = Buffer.from(normalized, 'utf-8');
  return crypto.createHmac('sha256', dedupKey).update(data).digest('hex');
}
