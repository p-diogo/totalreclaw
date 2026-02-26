/**
 * OpenMemory Canary Test
 *
 * Proves that OpenMemory's recall tool actually decrypts from the server,
 * NOT from OpenClaw's conversation history.
 *
 * This script:
 *   1. Derives the same keys as the OpenClaw plugin (same password, same salt)
 *   2. Encrypts a unique canary text that OpenClaw has NEVER seen
 *   3. Stores it directly via HTTP POST to the server
 *   4. Searches for it via blind indices and decrypts the result
 *
 * If the search returns the canary text correctly decrypted, it proves the
 * full E2EE round-trip: encrypt -> store -> blind search -> retrieve -> decrypt.
 *
 * Usage: node canary-test.mjs
 */

import { argon2id } from '@noble/hashes/argon2.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { hmac } from '@noble/hashes/hmac.js';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SERVER_URL = process.env.OPENMEMORY_SERVER_URL || 'http://127.0.0.1:8080';
const MASTER_PASSWORD = 'test-master-password-for-functional-tests';

// Credentials from: docker exec openclaw-test cat /home/node/.openmemory/credentials.json
const CREDENTIALS = {
  userId: '2c42165d-ad23-43b2-a65d-eddd0d530bc4',
  salt: 'XcQwVXT/7oRS3UnJgYWg0wOtv6Lhog90Jh1gY6KniYE=',
};

// The canary -- something OpenClaw has NEVER seen in any conversation
const CANARY_TEXT =
  'CANARY-2026-02-25: The user\'s favorite pizza topping is pineapple with jalape\u00f1os and the secret code is ALPHA-BRAVO-CHARLIE-7749';

// ---------------------------------------------------------------------------
// Crypto (mirrors skill/plugin/crypto.ts exactly)
// ---------------------------------------------------------------------------

const AUTH_KEY_INFO = 'openmemory-auth-key-v1';
const ENCRYPTION_KEY_INFO = 'openmemory-encryption-key-v1';
const DEDUP_KEY_INFO = 'openmemory-dedup-v1';

function deriveKeys(password, saltBuffer) {
  const passwordBytes = Buffer.from(password, 'utf8');

  // Argon2id -> masterKey
  const masterKey = argon2id(passwordBytes, saltBuffer, {
    t: 3,
    m: 65536,
    p: 4,
    dkLen: 32,
  });

  // HKDF sub-keys (info must be Uint8Array for @noble/hashes v2)
  const enc = (s) => Buffer.from(s, 'utf8');
  const authKey = Buffer.from(hkdf(sha256, masterKey, saltBuffer, enc(AUTH_KEY_INFO), 32));
  const encryptionKey = Buffer.from(hkdf(sha256, masterKey, saltBuffer, enc(ENCRYPTION_KEY_INFO), 32));
  const dedupKey = Buffer.from(hkdf(sha256, masterKey, saltBuffer, enc(DEDUP_KEY_INFO), 32));

  return { authKey, encryptionKey, dedupKey };
}

function encryptAesGcm(plaintext, encryptionKey) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', encryptionKey, iv, {
    authTagLength: 16,
  });
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  // Wire format: iv(12) || tag(16) || ciphertext
  return Buffer.concat([iv, tag, ciphertext]);
}

function decryptAesGcm(combined, encryptionKey) {
  const iv = combined.subarray(0, 12);
  const tag = combined.subarray(12, 28);
  const ciphertext = combined.subarray(28);
  const decipher = crypto.createDecipheriv('aes-256-gcm', encryptionKey, iv, {
    authTagLength: 16,
  });
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
}

function generateBlindIndices(text) {
  const tokens = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 2);

  const seen = new Set();
  const indices = [];

  for (const token of tokens) {
    const hash = Buffer.from(sha256(Buffer.from(token, 'utf8'))).toString('hex');
    if (!seen.has(hash)) {
      seen.add(hash);
      indices.push(hash);
    }
  }

  return indices;
}

function normalizeText(text) {
  return text.normalize('NFC').toLowerCase().replace(/\s+/g, ' ').trim();
}

function generateContentFingerprint(plaintext, dedupKey) {
  const normalized = normalizeText(plaintext);
  return Buffer.from(hmac(sha256, dedupKey, Buffer.from(normalized, 'utf8'))).toString('hex');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  console.log('='.repeat(70));
  console.log('  OpenMemory Canary Test');
  console.log('  Proves E2EE round-trip: encrypt -> store -> search -> decrypt');
  console.log('='.repeat(70));
  console.log();

  // 1. Health check
  console.log('[1/6] Checking server health...');
  const healthRes = await fetch(`${SERVER_URL}/health`);
  const healthData = await healthRes.json();
  console.log(`  Server: ${healthData.status} (v${healthData.version})`);
  if (healthData.status !== 'healthy') {
    console.error('  FAIL: Server is not healthy');
    process.exit(1);
  }
  console.log();

  // 2. Derive keys
  console.log('[2/6] Deriving keys from master password + salt...');
  const salt = Buffer.from(CREDENTIALS.salt, 'base64');
  console.log(`  Salt (base64): ${CREDENTIALS.salt}`);
  console.log(`  Salt (hex):    ${salt.toString('hex')}`);
  console.log(`  UserId:        ${CREDENTIALS.userId}`);

  const keys = deriveKeys(MASTER_PASSWORD, salt);
  const authKeyHex = keys.authKey.toString('hex');
  console.log(`  AuthKey (hex): ${authKeyHex.substring(0, 16)}...`);
  console.log(`  EncKey  (hex): ${keys.encryptionKey.toString('hex').substring(0, 16)}...`);
  console.log(`  DedupKey(hex): ${keys.dedupKey.toString('hex').substring(0, 16)}...`);
  console.log();

  // 3. Encrypt the canary
  console.log('[3/6] Encrypting canary text...');
  console.log(`  Canary: "${CANARY_TEXT}"`);

  const doc = {
    text: CANARY_TEXT,
    metadata: {
      type: 'fact',
      importance: 0.9,
      source: 'canary-test',
      created_at: new Date().toISOString(),
    },
  };
  const docJson = JSON.stringify(doc);
  const encryptedRaw = encryptAesGcm(docJson, keys.encryptionKey);
  const encryptedHex = encryptedRaw.toString('hex');
  console.log(`  Encrypted blob length: ${encryptedHex.length} hex chars (${encryptedRaw.length} bytes)`);
  console.log(`  Blob prefix: ${encryptedHex.substring(0, 40)}...`);

  // Verify we can decrypt our own encryption
  const selfDecrypted = decryptAesGcm(encryptedRaw, keys.encryptionKey);
  const selfDoc = JSON.parse(selfDecrypted);
  console.log(`  Self-decrypt check: "${selfDoc.text.substring(0, 50)}..." OK`);
  console.log();

  // 4. Generate blind indices and content fingerprint
  console.log('[4/6] Generating blind indices and content fingerprint...');
  const blindIndices = generateBlindIndices(CANARY_TEXT);
  const contentFp = generateContentFingerprint(CANARY_TEXT, keys.dedupKey);
  console.log(`  Blind indices count: ${blindIndices.length}`);
  console.log(`  First 3 indices: ${blindIndices.slice(0, 3).map((h) => h.substring(0, 16) + '...').join(', ')}`);
  console.log(`  Content FP: ${contentFp.substring(0, 32)}...`);
  console.log();

  // 5. Store via HTTP
  console.log('[5/6] Storing canary on server via POST /v1/store...');
  const factId = crypto.randomUUID();
  const storePayload = {
    user_id: CREDENTIALS.userId,
    facts: [
      {
        id: factId,
        timestamp: new Date().toISOString(),
        encrypted_blob: encryptedHex,
        blind_indices: blindIndices,
        decay_score: 9.0,
        source: 'canary-test',
        content_fp: contentFp,
        agent_id: 'canary-test-script',
      },
    ],
  };

  const storeRes = await fetch(`${SERVER_URL}/v1/store`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${authKeyHex}`,
    },
    body: JSON.stringify(storePayload),
  });
  const storeData = await storeRes.json();

  if (!storeData.success) {
    console.error(`  FAIL: Store failed: ${storeData.error_code} - ${storeData.error_message}`);
    process.exit(1);
  }
  console.log(`  Stored fact ID: ${factId}`);
  console.log(`  Server response: success=${storeData.success}, ids=${JSON.stringify(storeData.ids)}`);
  if (storeData.duplicate_ids && storeData.duplicate_ids.length > 0) {
    console.log(`  Note: Server detected duplicate (existing ID: ${storeData.duplicate_ids[0]})`);
    console.log('  This is OK -- canary was already stored from a previous run.');
  }
  console.log();

  // 6. Search and decrypt
  console.log('[6/6] Searching for canary via POST /v1/search...');

  // Use a subset of the blind indices as trapdoors (simulating a search for
  // a few key terms from the canary text)
  const queryTerms = ['canary', 'pineapple', 'jalape\u00f1os', 'alpha', 'bravo', 'charlie', '7749'];
  const trapdoors = queryTerms
    .filter((t) => t.length >= 2)
    .map((t) => {
      const normalized = t.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, ' ').trim();
      return Buffer.from(sha256(Buffer.from(normalized, 'utf8'))).toString('hex');
    });

  console.log(`  Query terms: ${queryTerms.join(', ')}`);
  console.log(`  Trapdoors count: ${trapdoors.length}`);

  const searchRes = await fetch(`${SERVER_URL}/v1/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${authKeyHex}`,
    },
    body: JSON.stringify({
      user_id: CREDENTIALS.userId,
      trapdoors,
      max_candidates: 100,
    }),
  });
  const searchData = await searchRes.json();

  if (!searchData.success) {
    console.error(`  FAIL: Search failed: ${searchData.error_code} - ${searchData.error_message}`);
    process.exit(1);
  }

  console.log(`  Search returned ${searchData.total_candidates} candidate(s)`);

  if (!searchData.results || searchData.results.length === 0) {
    console.error('  FAIL: No search results returned!');
    process.exit(1);
  }

  // Try to decrypt each candidate and find our canary
  let canaryFound = false;
  let decryptedCount = 0;
  let canaryResult = null;

  for (const result of searchData.results) {
    try {
      const blobBuffer = Buffer.from(result.encrypted_blob, 'hex');
      const decryptedJson = decryptAesGcm(blobBuffer, keys.encryptionKey);
      const decryptedDoc = JSON.parse(decryptedJson);
      decryptedCount++;

      if (decryptedDoc.text && decryptedDoc.text.includes('CANARY-2026-02-25')) {
        canaryFound = true;
        canaryResult = {
          factId: result.fact_id,
          text: decryptedDoc.text,
          metadata: decryptedDoc.metadata,
        };
      }
    } catch (err) {
      // Could not decrypt -- might be a different memory, skip it
    }
  }

  console.log(`  Successfully decrypted ${decryptedCount}/${searchData.results.length} candidates`);
  console.log();

  // ---------------------------------------------------------------------------
  // Report
  // ---------------------------------------------------------------------------

  console.log('='.repeat(70));
  console.log('  RESULTS');
  console.log('='.repeat(70));
  console.log();

  if (canaryFound) {
    console.log('  STATUS: PASS');
    console.log();
    console.log('  The canary memory was:');
    console.log('    1. Encrypted client-side with AES-256-GCM');
    console.log('    2. Stored on the server as an opaque hex blob');
    console.log('    3. Found via blind index search (SHA-256 trapdoors)');
    console.log('    4. Retrieved as encrypted hex from the server');
    console.log('    5. Decrypted client-side back to the original plaintext');
    console.log();
    console.log('  Decrypted canary text:');
    console.log(`    "${canaryResult.text}"`);
    console.log();
    console.log('  Metadata:');
    console.log(`    ${JSON.stringify(canaryResult.metadata, null, 4)}`);
    console.log();

    // Verify exact match
    if (canaryResult.text === CANARY_TEXT) {
      console.log('  EXACT MATCH: Decrypted text === original canary text');
    } else {
      console.log('  WARNING: Decrypted text does not exactly match original');
      console.log(`  Expected: "${CANARY_TEXT}"`);
      console.log(`  Got:      "${canaryResult.text}"`);
    }
    console.log();
    console.log('  This proves the OpenMemory E2EE round-trip works correctly.');
    console.log('  The server never saw the plaintext -- only encrypted blobs');
    console.log('  and blind indices (SHA-256 hashes of tokens).');
  } else {
    console.log('  STATUS: FAIL');
    console.log();
    console.log('  The canary memory was NOT found in search results.');
    console.log(`  Total candidates returned: ${searchData.total_candidates}`);
    console.log(`  Candidates decrypted: ${decryptedCount}`);
    console.log();
    console.log('  Possible causes:');
    console.log('    - Key derivation mismatch (different password or salt)');
    console.log('    - Blind index generation mismatch');
    console.log('    - Server not returning the stored fact');
    process.exit(1);
  }

  console.log();
  console.log('='.repeat(70));
  console.log('  Next step: Ask OpenClaw to recall "pizza topping canary code"');
  console.log('  If it returns the canary text, it proves OpenClaw decrypts');
  console.log('  from the server, not from conversation history.');
  console.log('='.repeat(70));
}

main().catch((err) => {
  console.error('Canary test failed with error:', err);
  process.exit(1);
});
