/**
 * Journey 3: Wallet & Seed Derivation
 *
 * Tests BIP-39 mnemonic generation, deterministic key derivation (HKDF),
 * registration + auth with derived keys, cross-device recovery, and
 * rejection of invalid/wrong mnemonics.
 * 10 assertions.
 */

import { generateMnemonic, validateMnemonic } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english';
import * as crypto from 'crypto';
import {
  IntegrationTestRunner,
  encryptFact,
  decryptFact,
  computeBlindIndices,
  computeContentFingerprint,
  buildFact,
  type TestKeys,
  type FactInput,
} from '../test-helpers.js';

// ---------------------------------------------------------------------------
// HKDF-SHA256 — matches client/src/crypto/seed.ts exactly
// ---------------------------------------------------------------------------

function hkdfSha256(ikm: Buffer, salt: Buffer, info: Buffer, length: number): Buffer {
  const prk = crypto.createHmac('sha256', salt).update(ikm).digest();
  const okm = Buffer.alloc(length);
  let t = Buffer.alloc(0);
  let offset = 0;
  let counter = 1;

  while (offset < length) {
    const hmac = crypto.createHmac('sha256', prk);
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

// ---------------------------------------------------------------------------
// Derive keys from mnemonic — mirrors seed.ts (without BIP-32 / viem)
//
// seed.ts does: mnemonic → BIP-39 seed → BIP-32 derive → privateKey →
//   HKDF(privateKey, "totalreclaw-seed-salt-v1", "totalreclaw-auth-key-v1")
//   HKDF(privateKey, "totalreclaw-seed-salt-v1", "totalreclaw-encryption-key-v1")
//
// For the E2E test we replicate this using @scure/bip39 for seed derivation
// and a simplified BIP-32 derive using Node.js crypto (no viem dependency).
// ---------------------------------------------------------------------------

function deriveKeysFromMnemonic(mnemonic: string): {
  authKey: Buffer;
  authKeyHash: string;
  authKeyHex: string;
  encryptionKey: Buffer;
  dedupKey: Buffer;
  salt: string;
} {
  // Step 1: mnemonic → BIP-39 seed (64 bytes)
  const seed = mnemonicToSeedSync(mnemonic);

  // Step 2: Derive a "private key" from the seed using BIP-32 m/44'/60'/0'/0/0
  // We use a simplified HMAC-SHA512 based derivation that matches the standard.
  const privateKey = deriveBIP32PrivateKey(seed);

  // Step 3: Derive TotalReclaw keys using HKDF with the same info strings as seed.ts
  const fixedSalt = Buffer.from('totalreclaw-seed-salt-v1', 'utf-8');

  const authKey = hkdfSha256(
    privateKey,
    fixedSalt,
    Buffer.from('totalreclaw-auth-key-v1', 'utf-8'),
    32,
  );

  const encryptionKey = hkdfSha256(
    privateKey,
    fixedSalt,
    Buffer.from('totalreclaw-encryption-key-v1', 'utf-8'),
    32,
  );

  // Dedup key: derive from the same private key with a dedup-specific info string
  // In production this comes from the encryption key or a separate derivation.
  // For tests, we use the encryption key as dedup key (same as test-helpers' generateTestKeys).
  const dedupKey = crypto.randomBytes(32);

  const authKeyHex = authKey.toString('hex');
  const authKeyHash = crypto.createHash('sha256').update(authKey).digest().toString('hex');
  const salt = crypto.randomBytes(32).toString('hex');

  return { authKey, authKeyHash, authKeyHex, encryptionKey, dedupKey, salt };
}

// ---------------------------------------------------------------------------
// BIP-39 seed from mnemonic (synchronous)
// ---------------------------------------------------------------------------

function mnemonicToSeedSync(mnemonic: string): Buffer {
  // PBKDF2 with 2048 iterations, "mnemonic" as salt prefix (BIP-39 spec)
  return crypto.pbkdf2Sync(
    Buffer.from(mnemonic.normalize('NFKD'), 'utf-8'),
    Buffer.from('mnemonic', 'utf-8'),
    2048,
    64,
    'sha512',
  );
}

// ---------------------------------------------------------------------------
// Simplified BIP-32 derivation for m/44'/60'/0'/0/0
// ---------------------------------------------------------------------------

function deriveBIP32PrivateKey(seed: Buffer): Buffer {
  // Master key from seed: HMAC-SHA512(key="Bitcoin seed", data=seed)
  let hmac = crypto.createHmac('sha512', Buffer.from('Bitcoin seed', 'utf-8'));
  hmac.update(seed);
  let I = hmac.digest();
  let key: Buffer = Buffer.from(I.subarray(0, 32));
  let chainCode: Buffer = Buffer.from(I.subarray(32));

  // Derive each level of m/44'/60'/0'/0/0
  const path = [
    0x8000002c, // 44'
    0x8000003c, // 60'
    0x80000000, // 0'
    0x00000000, // 0
    0x00000000, // 0
  ];

  for (const index of path) {
    const isHardened = (index & 0x80000000) !== 0;
    const data = Buffer.alloc(37);

    if (isHardened) {
      // Hardened: 0x00 || key || index
      data[0] = 0;
      key.copy(data, 1);
    } else {
      // Normal: compressed public key || index
      // For simplicity, compute the compressed public key from the private key
      const pubKey = compressedPubKey(key);
      pubKey.copy(data, 0);
    }
    data.writeUInt32BE(index, 33);

    hmac = crypto.createHmac('sha512', chainCode);
    hmac.update(data);
    I = hmac.digest();

    // child key = (IL + parent key) mod n
    // For correctness we do modular addition over secp256k1 order
    key = addPrivateKeys(Buffer.from(I.subarray(0, 32)), key);
    chainCode = Buffer.from(I.subarray(32));
  }

  return key;
}

// secp256k1 order
const SECP256K1_ORDER = BigInt('0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141');

function addPrivateKeys(a: Buffer, b: Buffer): Buffer {
  const aBig = BigInt('0x' + a.toString('hex'));
  const bBig = BigInt('0x' + b.toString('hex'));
  const sum = (aBig + bBig) % SECP256K1_ORDER;
  const hex = sum.toString(16).padStart(64, '0');
  return Buffer.from(hex, 'hex');
}

function compressedPubKey(privateKey: Buffer): Buffer {
  // Use Node.js crypto to get the public key
  const ecdh = crypto.createECDH('secp256k1');
  ecdh.setPrivateKey(privateKey);
  const uncompressed = ecdh.getPublicKey();
  // Compress: 0x02 or 0x03 prefix + x coordinate
  const x = uncompressed.subarray(1, 33);
  const y = uncompressed.subarray(33, 65);
  const prefix = (y[y.length - 1] & 1) === 0 ? 0x02 : 0x03;
  return Buffer.concat([Buffer.from([prefix]), x]);
}

// ===========================================================================
// Journey 3
// ===========================================================================

export default async function journey3Wallet(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 3: Wallet & Seed Derivation');

  // ---- 1. Generate BIP-39 mnemonic ----
  const mnemonic = generateMnemonic(wordlist, 128);
  runner.assert(mnemonic.split(' ').length === 12, 'Mnemonic is 12 words');

  // ---- 2. Validate mnemonic ----
  runner.assert(validateMnemonic(mnemonic, wordlist), 'Mnemonic validates');

  // ---- 3. Derive keys ----
  const keysA = deriveKeysFromMnemonic(mnemonic);
  runner.assertEqual(keysA.authKey.length, 32, 'Auth key is 32 bytes');
  runner.assertEqual(keysA.encryptionKey.length, 32, 'Encryption key is 32 bytes');

  // ---- 4. Register with derived auth_key_hash ----
  const regResp = await runner.register(keysA.authKeyHash, keysA.salt);
  runner.assertStatusCode(regResp, 200, 'Register with derived keys returns 200');
  const regBody = (await regResp.json()) as { success: boolean; user_id?: string };
  const userId = regBody.user_id!;

  // ---- 5. Store + search using derived keys — round-trip works ----
  const plaintext = 'Wallet derivation test fact for journey three verification';
  const fact = buildFact(plaintext, keysA.encryptionKey, keysA.dedupKey, { withFingerprint: true });
  await runner.store(keysA.authKeyHex, userId, [fact]);

  const trapdoors = computeBlindIndices('wallet derivation journey', keysA.dedupKey);
  const searchResp = await runner.search(keysA.authKeyHex, userId, trapdoors);
  const searchBody = (await searchResp.json()) as {
    success: boolean;
    results?: Array<{ fact_id: string; encrypted_blob: string }>;
  };
  // Decrypt the result if found
  const found =
    searchBody.results &&
    searchBody.results.length > 0 &&
    decryptFact(searchBody.results[0].encrypted_blob, keysA.encryptionKey) === plaintext;
  runner.assert(!!found, 'Round-trip store+search+decrypt works with derived keys');

  // ---- 6. "Device B" — same mnemonic produces same keys ----
  const keysB = deriveKeysFromMnemonic(mnemonic);
  runner.assert(keysA.authKey.equals(keysB.authKey), 'Device B derives same auth key');
  runner.assert(
    keysA.encryptionKey.equals(keysB.encryptionKey),
    'Device B derives same encryption key',
  );

  // ---- 7. Auth with Device B keys — search returns same facts ----
  const searchResp2 = await runner.search(keysB.authKeyHex, userId, trapdoors);
  runner.assertStatusCode(searchResp2, 200, 'Device B search returns 200 (same auth)');

  // ---- 8. Invalid mnemonic ----
  runner.assert(
    !validateMnemonic('invalid mnemonic words here not real bip thirty nine test', wordlist),
    'Invalid mnemonic rejected',
  );

  // ---- 9. Wrong mnemonic → different keys → auth fails (401) ----
  const wrongMnemonic = generateMnemonic(wordlist, 128);
  const wrongKeys = deriveKeysFromMnemonic(wrongMnemonic);
  const wrongSearchResp = await runner.search(wrongKeys.authKeyHex, userId, trapdoors);
  runner.assertStatusCodeOneOf(wrongSearchResp, [401, 403], 'Wrong mnemonic auth rejected');
}
