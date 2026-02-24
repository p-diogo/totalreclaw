/**
 * Crypto Module Tests
 *
 * Tests for encryption, key derivation, and blind index generation.
 */

import {
  deriveKeys,
  deriveAuthKey,
  deriveEncryptionKey,
  generateSalt,
  createAuthProof,
  verifyAuthProof,
} from '../src/crypto/kdf';
import { encrypt, decrypt, encryptString, decryptToString, serializeEncryptedData, deserializeEncryptedData } from '../src/crypto/aes';
import {
  tokenize,
  sha256Hash,
  generateBlindIndices,
  generateTrapdoors,
  computeIndexOverlap,
} from '../src/crypto/blind';

describe('Crypto Module', () => {
  describe('Key Derivation', () => {
    test('should generate random salt', () => {
      const salt1 = generateSalt();
      const salt2 = generateSalt();

      expect(salt1.length).toBe(32);
      expect(salt2.length).toBe(32);
      expect(salt1).not.toEqual(salt2);
    });

    test('should generate salt of custom length', () => {
      const salt = generateSalt(16);
      expect(salt.length).toBe(16);
    });

    test('should derive consistent keys from same password and salt', async () => {
      const password = 'test-password-123';
      const salt = generateSalt();

      const keys1 = await deriveKeys(password, salt);
      const keys2 = await deriveKeys(password, salt);

      expect(keys1.authKey).toEqual(keys2.authKey);
      expect(keys1.encryptionKey).toEqual(keys2.encryptionKey);
    });

    test('should derive different keys from different passwords', async () => {
      const salt = generateSalt();

      const keys1 = await deriveKeys('password1', salt);
      const keys2 = await deriveKeys('password2', salt);

      expect(keys1.authKey).not.toEqual(keys2.authKey);
      expect(keys1.encryptionKey).not.toEqual(keys2.encryptionKey);
    });

    test('should derive different keys from different salts', async () => {
      const password = 'test-password';

      const keys1 = await deriveKeys(password, generateSalt());
      const keys2 = await deriveKeys(password, generateSalt());

      expect(keys1.authKey).not.toEqual(keys2.authKey);
      expect(keys1.encryptionKey).not.toEqual(keys2.encryptionKey);
    });

    test('should derive 32-byte keys', async () => {
      const keys = await deriveKeys('test-password', generateSalt());

      expect(keys.authKey.length).toBe(32);
      expect(keys.encryptionKey.length).toBe(32);
    });
  });

  describe('Authentication', () => {
    test('should create and verify auth proof', async () => {
      const password = 'test-password';
      const salt = generateSalt();
      const { authKey } = await deriveKeys(password, salt);
      const data = Buffer.from('test-data', 'utf-8');

      const proof = createAuthProof(authKey, data);
      const verified = verifyAuthProof(authKey, data, proof);

      expect(verified).toBe(true);
    });

    test('should fail verification with wrong key', async () => {
      const password = 'test-password';
      const salt = generateSalt();
      const { authKey } = await deriveKeys(password, salt);
      const { authKey: wrongKey } = await deriveKeys('wrong-password', salt);
      const data = Buffer.from('test-data', 'utf-8');

      const proof = createAuthProof(authKey, data);
      const verified = verifyAuthProof(wrongKey, data, proof);

      expect(verified).toBe(false);
    });

    test('should fail verification with wrong data', async () => {
      const password = 'test-password';
      const salt = generateSalt();
      const { authKey } = await deriveKeys(password, salt);

      const proof = createAuthProof(authKey, Buffer.from('correct-data', 'utf-8'));
      const verified = verifyAuthProof(authKey, Buffer.from('wrong-data', 'utf-8'), proof);

      expect(verified).toBe(false);
    });
  });

  describe('AES-256-GCM Encryption', () => {
    test('should encrypt and decrypt data correctly', async () => {
      const { encryptionKey } = await deriveKeys('test-password', generateSalt());
      const plaintext = Buffer.from('Hello, World!', 'utf-8');

      const encrypted = encrypt(plaintext, encryptionKey);
      const decrypted = decrypt(encrypted.ciphertext, encryptionKey, encrypted.iv, encrypted.tag);

      expect(decrypted).toEqual(plaintext);
    });

    test('should encrypt and decrypt strings correctly', async () => {
      const { encryptionKey } = await deriveKeys('test-password', generateSalt());
      const text = 'Hello, World!';

      const encrypted = encryptString(text, encryptionKey);
      const decrypted = decryptToString(encrypted.ciphertext, encryptionKey, encrypted.iv, encrypted.tag);

      expect(decrypted).toBe(text);
    });

    test('should produce different ciphertexts for same plaintext', async () => {
      const { encryptionKey } = await deriveKeys('test-password', generateSalt());
      const plaintext = Buffer.from('Hello, World!', 'utf-8');

      const encrypted1 = encrypt(plaintext, encryptionKey);
      const encrypted2 = encrypt(plaintext, encryptionKey);

      // Different IVs mean different ciphertexts
      expect(encrypted1.ciphertext).not.toEqual(encrypted2.ciphertext);
      expect(encrypted1.iv).not.toEqual(encrypted2.iv);
    });

    test('should fail decryption with wrong key', async () => {
      const salt = generateSalt();
      const { encryptionKey: key1 } = await deriveKeys('password1', salt);
      const { encryptionKey: key2 } = await deriveKeys('password2', salt);

      const plaintext = Buffer.from('Secret message', 'utf-8');
      const encrypted = encrypt(plaintext, key1);

      expect(() => {
        decrypt(encrypted.ciphertext, key2, encrypted.iv, encrypted.tag);
      }).toThrow();
    });

    test('should fail decryption with tampered ciphertext', async () => {
      const { encryptionKey } = await deriveKeys('test-password', generateSalt());
      const plaintext = Buffer.from('Secret message', 'utf-8');
      const encrypted = encrypt(plaintext, encryptionKey);

      // Tamper with ciphertext
      const tamperedCiphertext = Buffer.from(encrypted.ciphertext);
      tamperedCiphertext[0] ^= 0xff;

      expect(() => {
        decrypt(tamperedCiphertext, encryptionKey, encrypted.iv, encrypted.tag);
      }).toThrow();
    });

    test('should serialize and deserialize encrypted data', async () => {
      const { encryptionKey } = await deriveKeys('test-password', generateSalt());
      const plaintext = Buffer.from('Hello, World!', 'utf-8');

      const encrypted = encrypt(plaintext, encryptionKey);
      const serialized = serializeEncryptedData(encrypted);
      const deserialized = deserializeEncryptedData(serialized);

      expect(deserialized.iv).toEqual(encrypted.iv);
      expect(deserialized.tag).toEqual(encrypted.tag);
      expect(deserialized.ciphertext).toEqual(encrypted.ciphertext);

      const decrypted = decrypt(deserialized.ciphertext, encryptionKey, deserialized.iv, deserialized.tag);
      expect(decrypted).toEqual(plaintext);
    });
  });

  describe('Blind Indices', () => {
    test('should tokenize text correctly', () => {
      const tokens = tokenize('Hello, World! This is a test.');
      expect(tokens).toContain('hello');
      expect(tokens).toContain('world');
      expect(tokens).toContain('this');
      expect(tokens).toContain('is');
      // 'a' is filtered as short token (< 2 chars)
      expect(tokens).not.toContain('a');
      expect(tokens).toContain('test');
    });

    test('should filter short tokens', () => {
      const tokens = tokenize('I am a big fan');
      expect(tokens).not.toContain('i');
      expect(tokens).not.toContain('a');
      expect(tokens).toContain('am');
      expect(tokens).toContain('big');
      expect(tokens).toContain('fan');
    });

    test('should produce consistent SHA-256 hashes', () => {
      const hash1 = sha256Hash('test');
      const hash2 = sha256Hash('test');

      expect(hash1).toBe(hash2);
      expect(hash1.length).toBe(64); // 32 bytes hex = 64 chars
    });

    test('should produce different hashes for different inputs', () => {
      const hash1 = sha256Hash('test1');
      const hash2 = sha256Hash('test2');

      expect(hash1).not.toBe(hash2);
    });

    test('should generate blind indices from text and LSH buckets', () => {
      const text = 'I love coffee';
      const lshBuckets = ['table_0_101010', 'table_1_010101'];

      const indices = generateBlindIndices(text, lshBuckets);

      // Should include token hashes
      expect(indices.length).toBeGreaterThan(0);

      // Should be unique
      const uniqueIndices = new Set(indices);
      expect(uniqueIndices.size).toBe(indices.length);
    });

    test('should generate trapdoors consistently', () => {
      const query = 'coffee preferences';
      const lshBuckets = ['table_0_101010', 'table_1_010101'];

      const trapdoors1 = generateTrapdoors(query, lshBuckets);
      const trapdoors2 = generateTrapdoors(query, lshBuckets);

      expect(trapdoors1).toEqual(trapdoors2);
    });

    test('should compute index overlap correctly', () => {
      const indices1 = ['a', 'b', 'c', 'd'];
      const indices2 = ['b', 'c', 'e', 'f'];

      const overlap = computeIndexOverlap(indices1, indices2);
      expect(overlap).toBe(2); // 'b' and 'c'
    });
  });
});
