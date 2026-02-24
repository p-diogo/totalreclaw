/**
 * Credential Management Tests
 *
 * Tests for OS keychain storage (keytar mocked) and session manager.
 */

import { generateSalt, deriveKeys } from '../src/crypto/kdf';

// ---------------------------------------------------------------------------
// Mock keytar — native module that may not be available in CI
// ---------------------------------------------------------------------------

const mockStore = new Map<string, string>();

const mockKeytar = {
  setPassword: jest.fn(
    async (service: string, account: string, password: string): Promise<void> => {
      mockStore.set(`${service}:${account}`, password);
    }
  ),
  getPassword: jest.fn(
    async (service: string, account: string): Promise<string | null> => {
      return mockStore.get(`${service}:${account}`) ?? null;
    }
  ),
  deletePassword: jest.fn(
    async (service: string, account: string): Promise<boolean> => {
      const key = `${service}:${account}`;
      if (mockStore.has(key)) {
        mockStore.delete(key);
        return true;
      }
      return false;
    }
  ),
};

// Mock require('keytar') used by keychain.ts
jest.mock('keytar', () => mockKeytar, { virtual: true });

// Import AFTER the mock is in place
import {
  storeCredentials,
  getCredentials,
  deleteCredentials,
  hasCredentials,
  isKeychainAvailable,
} from '../src/credentials/keychain';
import { SessionManager } from '../src/credentials/session';

// ---------------------------------------------------------------------------
// Keychain tests
// ---------------------------------------------------------------------------

describe('Keychain Credential Storage', () => {
  beforeEach(() => {
    mockStore.clear();
    jest.clearAllMocks();
  });

  test('isKeychainAvailable should return true when keytar is present', () => {
    const available = isKeychainAvailable();
    expect(available).toBe(true);
  });

  test('storeCredentials should save password in keychain', async () => {
    await storeCredentials('user-1', 'my-secret-password');

    expect(mockKeytar.setPassword).toHaveBeenCalledWith(
      'openmemory',
      'user-1',
      'my-secret-password'
    );
    expect(mockStore.get('openmemory:user-1')).toBe('my-secret-password');
  });

  test('getCredentials should retrieve stored password', async () => {
    await storeCredentials('user-1', 'my-secret-password');
    const password = await getCredentials('user-1');

    expect(password).toBe('my-secret-password');
    expect(mockKeytar.getPassword).toHaveBeenCalledWith('openmemory', 'user-1');
  });

  test('getCredentials should return null for unknown user', async () => {
    const password = await getCredentials('unknown-user');
    expect(password).toBeNull();
  });

  test('deleteCredentials should remove stored password', async () => {
    await storeCredentials('user-1', 'my-secret-password');
    const deleted = await deleteCredentials('user-1');

    expect(deleted).toBe(true);
    expect(mockStore.has('openmemory:user-1')).toBe(false);
    expect(mockKeytar.deletePassword).toHaveBeenCalledWith('openmemory', 'user-1');
  });

  test('deleteCredentials should return false for unknown user', async () => {
    const deleted = await deleteCredentials('unknown-user');
    expect(deleted).toBe(false);
  });

  test('hasCredentials should return true when credential exists', async () => {
    await storeCredentials('user-1', 'my-secret-password');
    const exists = await hasCredentials('user-1');
    expect(exists).toBe(true);
  });

  test('hasCredentials should return false when no credential exists', async () => {
    const exists = await hasCredentials('unknown-user');
    expect(exists).toBe(false);
  });

  test('full store/get/delete/has lifecycle', async () => {
    const userId = 'lifecycle-user';
    const password = 'lifecycle-password';

    // Initially no credentials
    expect(await hasCredentials(userId)).toBe(false);
    expect(await getCredentials(userId)).toBeNull();

    // Store
    await storeCredentials(userId, password);
    expect(await hasCredentials(userId)).toBe(true);
    expect(await getCredentials(userId)).toBe(password);

    // Delete
    const deleted = await deleteCredentials(userId);
    expect(deleted).toBe(true);
    expect(await hasCredentials(userId)).toBe(false);
    expect(await getCredentials(userId)).toBeNull();

    // Delete again — should be false
    const deletedAgain = await deleteCredentials(userId);
    expect(deletedAgain).toBe(false);
  });

  test('should isolate credentials between users', async () => {
    await storeCredentials('alice', 'alice-password');
    await storeCredentials('bob', 'bob-password');

    expect(await getCredentials('alice')).toBe('alice-password');
    expect(await getCredentials('bob')).toBe('bob-password');

    await deleteCredentials('alice');
    expect(await getCredentials('alice')).toBeNull();
    expect(await getCredentials('bob')).toBe('bob-password');
  });

  test('storeCredentials should overwrite existing password', async () => {
    await storeCredentials('user-1', 'old-password');
    await storeCredentials('user-1', 'new-password');

    expect(await getCredentials('user-1')).toBe('new-password');
  });

  test('storeCredentials should reject empty userId', async () => {
    await expect(storeCredentials('', 'password')).rejects.toThrow(
      'userId and masterPassword are required'
    );
  });

  test('storeCredentials should reject empty masterPassword', async () => {
    await expect(storeCredentials('user-1', '')).rejects.toThrow(
      'userId and masterPassword are required'
    );
  });

  test('getCredentials should reject empty userId', async () => {
    await expect(getCredentials('')).rejects.toThrow('userId is required');
  });

  test('deleteCredentials should reject empty userId', async () => {
    await expect(deleteCredentials('')).rejects.toThrow('userId is required');
  });
});

// ---------------------------------------------------------------------------
// Session Manager tests
// ---------------------------------------------------------------------------

describe('Session Manager', () => {
  // Use fast KDF params for tests (reduce Argon2id cost).
  // Note: argon2 requires timeCost >= 2.
  const fastKdfParams = {
    memoryCost: 1024,
    timeCost: 2,
    parallelism: 1,
  };

  test('should create with default timeout of 30 minutes', () => {
    const session = new SessionManager();
    expect(session.sessionTimeoutMs).toBe(30 * 60 * 1000);
  });

  test('should accept custom timeout', () => {
    const session = new SessionManager({ timeoutMs: 5 * 60 * 1000 });
    expect(session.sessionTimeoutMs).toBe(5 * 60 * 1000);
  });

  test('should reject non-positive timeout', () => {
    expect(() => new SessionManager({ timeoutMs: 0 })).toThrow(
      'Session timeout must be a positive number'
    );
    expect(() => new SessionManager({ timeoutMs: -1000 })).toThrow(
      'Session timeout must be a positive number'
    );
  });

  test('should derive and cache keys on first call', async () => {
    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });
    const salt = generateSalt();

    const keys = await session.getOrDeriveKeys('user-1', salt, 'test-password');

    expect(keys.authKey).toBeInstanceOf(Buffer);
    expect(keys.encryptionKey).toBeInstanceOf(Buffer);
    expect(keys.authKey.length).toBe(32);
    expect(keys.encryptionKey.length).toBe(32);
    expect(session.hasSession('user-1')).toBe(true);
  });

  test('should return cached keys on subsequent calls without password', async () => {
    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });
    const salt = generateSalt();

    const keys1 = await session.getOrDeriveKeys('user-1', salt, 'test-password');
    const keys2 = await session.getOrDeriveKeys('user-1', salt);

    // Should be the exact same buffer references (from cache)
    expect(keys1.authKey).toBe(keys2.authKey);
    expect(keys1.encryptionKey).toBe(keys2.encryptionKey);
  });

  test('should throw when session expired and no password provided', async () => {
    const session = new SessionManager({
      timeoutMs: 1, // 1ms — will expire almost immediately
      kdfParams: fastKdfParams,
    });
    const salt = generateSalt();

    await session.getOrDeriveKeys('user-1', salt, 'test-password');

    // Wait for expiry
    await new Promise((resolve) => setTimeout(resolve, 10));

    await expect(session.getOrDeriveKeys('user-1', salt)).rejects.toThrow(
      'Session expired or not yet established'
    );
  });

  test('should re-derive keys after expiry when password is provided', async () => {
    const session = new SessionManager({
      timeoutMs: 1,
      kdfParams: fastKdfParams,
    });
    const salt = generateSalt();

    const keys1 = await session.getOrDeriveKeys('user-1', salt, 'test-password');
    // Save a copy of the auth key value before it gets zeroed on expiry
    const authKeyValue = Buffer.from(keys1.authKey);
    const encKeyValue = Buffer.from(keys1.encryptionKey);

    // Wait for expiry
    await new Promise((resolve) => setTimeout(resolve, 10));

    const keys2 = await session.getOrDeriveKeys('user-1', salt, 'test-password');

    // New derivation should produce equal keys (same password + salt)
    expect(keys2.authKey).toEqual(authKeyValue);
    expect(keys2.encryptionKey).toEqual(encKeyValue);
    // References should differ (new buffer instances)
    expect(keys2.authKey).not.toBe(keys1.authKey);
  });

  test('invalidateSession should zero and remove cached keys', async () => {
    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });
    const salt = generateSalt();

    const keys = await session.getOrDeriveKeys('user-1', salt, 'test-password');
    // Keep a reference to verify zeroing
    const authKeyRef = keys.authKey;
    const encKeyRef = keys.encryptionKey;

    session.invalidateSession('user-1');

    // Buffers should be zeroed
    expect(authKeyRef.every((b) => b === 0)).toBe(true);
    expect(encKeyRef.every((b) => b === 0)).toBe(true);

    // Session should be gone
    expect(session.hasSession('user-1')).toBe(false);
  });

  test('invalidateAll should clear all sessions', async () => {
    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });

    const salt1 = generateSalt();
    const salt2 = generateSalt();

    await session.getOrDeriveKeys('user-1', salt1, 'password-1');
    await session.getOrDeriveKeys('user-2', salt2, 'password-2');

    expect(session.activeSessionCount).toBe(2);

    session.invalidateAll();

    expect(session.activeSessionCount).toBe(0);
    expect(session.hasSession('user-1')).toBe(false);
    expect(session.hasSession('user-2')).toBe(false);
  });

  test('hasSession should return false for unknown user', () => {
    const session = new SessionManager();
    expect(session.hasSession('unknown')).toBe(false);
  });

  test('activeSessionCount should track sessions correctly', async () => {
    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });

    expect(session.activeSessionCount).toBe(0);

    const salt = generateSalt();
    await session.getOrDeriveKeys('user-1', salt, 'password');
    expect(session.activeSessionCount).toBe(1);

    await session.getOrDeriveKeys('user-2', generateSalt(), 'password');
    expect(session.activeSessionCount).toBe(2);

    session.invalidateSession('user-1');
    expect(session.activeSessionCount).toBe(1);
  });

  test('should isolate sessions between users', async () => {
    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });

    const salt1 = generateSalt();
    const salt2 = generateSalt();

    const keys1 = await session.getOrDeriveKeys('user-1', salt1, 'password-1');
    const keys2 = await session.getOrDeriveKeys('user-2', salt2, 'password-2');

    // Different salts should produce different keys
    expect(keys1.authKey).not.toEqual(keys2.authKey);
    expect(keys1.encryptionKey).not.toEqual(keys2.encryptionKey);

    // Invalidating one should not affect the other
    session.invalidateSession('user-1');
    expect(session.hasSession('user-1')).toBe(false);
    expect(session.hasSession('user-2')).toBe(true);
  });

  test('should produce keys consistent with direct deriveKeys call', async () => {
    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });

    const salt = generateSalt();
    const password = 'consistency-check';

    const sessionKeys = await session.getOrDeriveKeys('user-1', salt, password);
    const directKeys = await deriveKeys(password, salt, fastKdfParams);

    expect(sessionKeys.authKey).toEqual(directKeys.authKey);
    expect(sessionKeys.encryptionKey).toEqual(directKeys.encryptionKey);
  });
});

// ---------------------------------------------------------------------------
// Integration: Keychain + Session Manager
// ---------------------------------------------------------------------------

describe('Credential Management Integration', () => {
  // Note: argon2 requires timeCost >= 2.
  const fastKdfParams = {
    memoryCost: 1024,
    timeCost: 2,
    parallelism: 1,
  };

  beforeEach(() => {
    mockStore.clear();
    jest.clearAllMocks();
  });

  test('full workflow: store creds -> derive keys -> cache -> timeout -> re-derive', async () => {
    const userId = 'integration-user';
    const masterPassword = 'integration-password';
    const salt = generateSalt();

    // 1. Store credentials in keychain
    await storeCredentials(userId, masterPassword);
    expect(await hasCredentials(userId)).toBe(true);

    // 2. Retrieve password from keychain
    const storedPassword = await getCredentials(userId);
    expect(storedPassword).toBe(masterPassword);

    // 3. Use password to derive and cache keys
    const session = new SessionManager({
      timeoutMs: 1, // very short timeout for testing
      kdfParams: fastKdfParams,
    });

    const keys1 = await session.getOrDeriveKeys(userId, salt, storedPassword!);
    expect(keys1.authKey.length).toBe(32);
    expect(keys1.encryptionKey.length).toBe(32);
    // Save copies before they are zeroed on expiry
    const authKeyCopy = Buffer.from(keys1.authKey);
    const encKeyCopy = Buffer.from(keys1.encryptionKey);

    // 4. Wait for session to expire
    await new Promise((resolve) => setTimeout(resolve, 10));

    // 5. Session expired — retrieve password from keychain again and re-derive
    const refreshedPassword = await getCredentials(userId);
    expect(refreshedPassword).toBe(masterPassword);

    const keys2 = await session.getOrDeriveKeys(userId, salt, refreshedPassword!);

    // Keys should be equal (same password + salt) but new buffer instances
    expect(keys2.authKey).toEqual(authKeyCopy);
    expect(keys2.encryptionKey).toEqual(encKeyCopy);
  });

  test('deleting credentials does not affect active session', async () => {
    const userId = 'delete-test-user';
    const masterPassword = 'delete-test-password';
    const salt = generateSalt();

    await storeCredentials(userId, masterPassword);

    const session = new SessionManager({
      timeoutMs: 60_000,
      kdfParams: fastKdfParams,
    });

    // Derive keys while credentials exist
    const keys = await session.getOrDeriveKeys(userId, salt, masterPassword);

    // Delete credentials from keychain
    await deleteCredentials(userId);
    expect(await hasCredentials(userId)).toBe(false);

    // Session should still be valid (keys are cached in memory)
    expect(session.hasSession(userId)).toBe(true);
    const cachedKeys = await session.getOrDeriveKeys(userId, salt);
    expect(cachedKeys.authKey).toBe(keys.authKey);
  });

  test('password should not appear in error messages', async () => {
    const session = new SessionManager({
      timeoutMs: 1,
      kdfParams: fastKdfParams,
    });
    const salt = generateSalt();

    await session.getOrDeriveKeys('user-1', salt, 'super-secret-pw');

    // Wait for expiry
    await new Promise((resolve) => setTimeout(resolve, 10));

    try {
      await session.getOrDeriveKeys('user-1', salt);
      fail('Should have thrown');
    } catch (e: unknown) {
      const message = (e as Error).message;
      expect(message).not.toContain('super-secret-pw');
    }
  });
});
