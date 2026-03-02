/**
 * AES-256-GCM Encryption
 *
 * Provides authenticated encryption using AES-256 in GCM mode.
 */

import * as crypto from 'crypto';
import { TotalReclawError, TotalReclawErrorCode } from '../types';

/**
 * Result of AES-256-GCM encryption
 */
export interface EncryptedData {
  /** Encrypted ciphertext */
  ciphertext: Buffer;
  /** Initialization vector (12 bytes for GCM) */
  iv: Buffer;
  /** Authentication tag (16 bytes for GCM) */
  tag: Buffer;
}

/** IV length for GCM mode (12 bytes is recommended) */
const IV_LENGTH = 12;

/** Tag length for GCM mode (16 bytes = 128 bits) */
const TAG_LENGTH = 16;

/** Key length for AES-256 (32 bytes) */
const KEY_LENGTH = 32;

/**
 * Encrypt plaintext using AES-256-GCM
 *
 * @param plaintext - Data to encrypt
 * @param key - 32-byte encryption key
 * @returns Encrypted data with IV and authentication tag
 */
export function encrypt(plaintext: Buffer, key: Buffer): EncryptedData {
  if (key.length !== KEY_LENGTH) {
    throw new TotalReclawError(
      TotalReclawErrorCode.ENCRYPTION_FAILED,
      `Invalid key length: expected ${KEY_LENGTH} bytes, got ${key.length}`
    );
  }

  try {
    // Generate random IV
    const iv = crypto.randomBytes(IV_LENGTH);

    // Create cipher
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv, {
      authTagLength: TAG_LENGTH,
    });

    // Encrypt
    const ciphertext = Buffer.concat([
      cipher.update(plaintext),
      cipher.final(),
    ]);

    // Get authentication tag
    const tag = cipher.getAuthTag();

    return {
      ciphertext,
      iv,
      tag,
    };
  } catch (error) {
    throw new TotalReclawError(
      TotalReclawErrorCode.ENCRYPTION_FAILED,
      `Encryption failed: ${error instanceof Error ? error.message : 'Unknown error'}`
    );
  }
}

/**
 * Decrypt ciphertext using AES-256-GCM
 *
 * @param ciphertext - Encrypted data
 * @param key - 32-byte encryption key
 * @param iv - 12-byte initialization vector
 * @param tag - 16-byte authentication tag
 * @returns Decrypted plaintext
 */
export function decrypt(
  ciphertext: Buffer,
  key: Buffer,
  iv: Buffer,
  tag: Buffer
): Buffer {
  if (key.length !== KEY_LENGTH) {
    throw new TotalReclawError(
      TotalReclawErrorCode.DECRYPTION_FAILED,
      `Invalid key length: expected ${KEY_LENGTH} bytes, got ${key.length}`
    );
  }

  if (iv.length !== IV_LENGTH) {
    throw new TotalReclawError(
      TotalReclawErrorCode.DECRYPTION_FAILED,
      `Invalid IV length: expected ${IV_LENGTH} bytes, got ${iv.length}`
    );
  }

  if (tag.length !== TAG_LENGTH) {
    throw new TotalReclawError(
      TotalReclawErrorCode.DECRYPTION_FAILED,
      `Invalid tag length: expected ${TAG_LENGTH} bytes, got ${tag.length}`
    );
  }

  try {
    // Create decipher
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv, {
      authTagLength: TAG_LENGTH,
    });

    // Set authentication tag
    decipher.setAuthTag(tag);

    // Decrypt
    const plaintext = Buffer.concat([
      decipher.update(ciphertext),
      decipher.final(),
    ]);

    return plaintext;
  } catch (error) {
    throw new TotalReclawError(
      TotalReclawErrorCode.DECRYPTION_FAILED,
      `Decryption failed: ${error instanceof Error ? error.message : 'Unknown error'}`
    );
  }
}

/**
 * Encrypt a string using AES-256-GCM
 *
 * @param text - Text to encrypt
 * @param key - 32-byte encryption key
 * @returns Encrypted data with IV and authentication tag
 */
export function encryptString(text: string, key: Buffer): EncryptedData {
  return encrypt(Buffer.from(text, 'utf-8'), key);
}

/**
 * Decrypt to a string using AES-256-GCM
 *
 * @param ciphertext - Encrypted data
 * @param key - 32-byte encryption key
 * @param iv - 12-byte initialization vector
 * @param tag - 16-byte authentication tag
 * @returns Decrypted string
 */
export function decryptToString(
  ciphertext: Buffer,
  key: Buffer,
  iv: Buffer,
  tag: Buffer
): string {
  const plaintext = decrypt(ciphertext, key, iv, tag);
  return plaintext.toString('utf-8');
}

/**
 * Encrypt a Float64Array (for embedding vectors) using AES-256-GCM
 *
 * @param vector - Float64Array to encrypt
 * @param key - 32-byte encryption key
 * @returns Encrypted data with IV and authentication tag
 */
export function encryptVector(vector: Float64Array | number[], key: Buffer): EncryptedData {
  const buffer = Buffer.from(new Float64Array(vector).buffer);
  return encrypt(buffer, key);
}

/**
 * Decrypt to a Float64Array (for embedding vectors) using AES-256-GCM
 *
 * @param ciphertext - Encrypted data
 * @param key - 32-byte encryption key
 * @param iv - 12-byte initialization vector
 * @param tag - 16-byte authentication tag
 * @returns Decrypted Float64Array
 */
export function decryptToVector(
  ciphertext: Buffer,
  key: Buffer,
  iv: Buffer,
  tag: Buffer
): Float64Array {
  const plaintext = decrypt(ciphertext, key, iv, tag);
  return new Float64Array(
    plaintext.buffer,
    plaintext.byteOffset,
    plaintext.length / Float64Array.BYTES_PER_ELEMENT
  );
}

/**
 * Serialize encrypted data to a single buffer
 *
 * Format: [iv: 12 bytes][tag: 16 bytes][ciphertext: variable]
 *
 * @param data - Encrypted data
 * @returns Serialized buffer
 */
export function serializeEncryptedData(data: EncryptedData): Buffer {
  return Buffer.concat([data.iv, data.tag, data.ciphertext]);
}

/**
 * Deserialize encrypted data from a single buffer
 *
 * @param buffer - Serialized buffer
 * @returns Encrypted data components
 */
export function deserializeEncryptedData(buffer: Buffer): EncryptedData {
  if (buffer.length < IV_LENGTH + TAG_LENGTH) {
    throw new TotalReclawError(
      TotalReclawErrorCode.DECRYPTION_FAILED,
      'Buffer too short to contain encrypted data'
    );
  }

  const iv = buffer.subarray(0, IV_LENGTH);
  const tag = buffer.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH);
  const ciphertext = buffer.subarray(IV_LENGTH + TAG_LENGTH);

  return { ciphertext, iv, tag };
}
