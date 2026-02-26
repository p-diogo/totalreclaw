/**
 * OpenMemory Fact Audit Script
 *
 * Decrypts and displays ALL facts stored in the OpenMemory database.
 * Uses the same Argon2id -> HKDF -> AES-256-GCM crypto chain as the
 * OpenClaw plugin (skill/plugin/crypto.ts).
 *
 * Usage:
 *   # First extract credentials from the Docker container:
 *   docker exec openclaw-test cat /home/node/.openmemory/credentials.json > /tmp/creds.json
 *
 *   # Then run this script:
 *   node audit-facts.mjs /tmp/creds.json
 */

import { argon2id } from '@noble/hashes/argon2.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import crypto from 'node:crypto';
import fs from 'node:fs';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SERVER_URL = process.env.OPENMEMORY_SERVER_URL || 'http://127.0.0.1:8080';
const MASTER_PASSWORD =
  process.env.OPENMEMORY_MASTER_PASSWORD || 'test-master-password-for-functional-tests';

// ---------------------------------------------------------------------------
// Crypto (mirrors skill/plugin/crypto.ts exactly)
// ---------------------------------------------------------------------------

const AUTH_KEY_INFO = 'openmemory-auth-key-v1';
const ENCRYPTION_KEY_INFO = 'openmemory-encryption-key-v1';
const DEDUP_KEY_INFO = 'openmemory-dedup-v1';

function deriveKeys(password, saltBuffer) {
  const passwordBytes = Buffer.from(password, 'utf8');

  // Argon2id -> masterKey (matches plugin exactly)
  const masterKey = argon2id(passwordBytes, saltBuffer, {
    t: 3,
    m: 65536,
    p: 4,
    dkLen: 32,
  });

  // HKDF sub-keys (info must be Uint8Array for @noble/hashes v2)
  const enc = (s) => Buffer.from(s, 'utf8');
  const authKey = Buffer.from(hkdf(sha256, masterKey, saltBuffer, enc(AUTH_KEY_INFO), 32));
  const encryptionKey = Buffer.from(
    hkdf(sha256, masterKey, saltBuffer, enc(ENCRYPTION_KEY_INFO), 32),
  );
  const dedupKey = Buffer.from(hkdf(sha256, masterKey, saltBuffer, enc(DEDUP_KEY_INFO), 32));

  return { authKey, encryptionKey, dedupKey };
}

/**
 * Decrypt a hex-encoded AES-256-GCM blob.
 *
 * Wire format: iv(12) || tag(16) || ciphertext
 * (matches skill/plugin/crypto.ts encrypt/decrypt)
 */
function decryptFromHex(hexBlob, encryptionKey) {
  const combined = Buffer.from(hexBlob, 'hex');

  const iv = combined.subarray(0, 12);
  const tag = combined.subarray(12, 28);
  const ciphertext = combined.subarray(28);

  const decipher = crypto.createDecipheriv('aes-256-gcm', encryptionKey, iv, {
    authTagLength: 16,
  });
  decipher.setAuthTag(tag);

  const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return plaintext.toString('utf8');
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  // Step 1: Load credentials
  const credPath = process.argv[2];
  if (!credPath) {
    console.error('Usage: node audit-facts.mjs <credentials.json>');
    console.error('');
    console.error('Get credentials from Docker:');
    console.error(
      '  docker exec openclaw-test cat /home/node/.openmemory/credentials.json > /tmp/creds.json',
    );
    process.exit(1);
  }

  const creds = JSON.parse(fs.readFileSync(credPath, 'utf8'));
  const { userId, salt: saltB64 } = creds;
  const saltBuffer = Buffer.from(saltB64, 'base64');

  console.log('='.repeat(70));
  console.log('  OpenMemory Fact Audit');
  console.log('='.repeat(70));
  console.log();
  console.log(`User ID: ${userId}`);
  console.log(`Salt:    ${saltB64}`);
  console.log();

  // Step 2: Derive keys
  console.log('Deriving keys (Argon2id + HKDF)...');
  const keys = deriveKeys(MASTER_PASSWORD, saltBuffer);
  const authKeyHex = keys.authKey.toString('hex');
  console.log(`Auth key: ${authKeyHex.slice(0, 16)}...`);
  console.log(`Enc key:  ${keys.encryptionKey.toString('hex').slice(0, 16)}...`);
  console.log();

  // Step 3: Export all facts via API
  console.log('Fetching facts via /v1/export...');
  const allFacts = [];
  let cursor = undefined;
  let hasMore = true;

  while (hasMore) {
    const params = new URLSearchParams({ limit: '5000' });
    if (cursor) params.set('cursor', cursor);

    const resp = await fetch(`${SERVER_URL}/v1/export?${params.toString()}`, {
      headers: { Authorization: `Bearer ${authKeyHex}` },
    });

    if (!resp.ok) {
      console.error(`Export failed: HTTP ${resp.status} - ${await resp.text()}`);
      process.exit(1);
    }

    const data = await resp.json();
    if (!data.success) {
      console.error(`Export failed: ${data.error_code} - ${data.error_message}`);
      process.exit(1);
    }

    allFacts.push(...(data.facts || []));
    cursor = data.cursor;
    hasMore = data.has_more;
  }

  console.log(`Retrieved ${allFacts.length} fact(s) from server.`);
  console.log();

  // Step 4: Decrypt and display each fact
  console.log('='.repeat(70));
  console.log(`  DECRYPTED FACTS (${allFacts.length} total)`);
  console.log('='.repeat(70));
  console.log();

  const decrypted = [];
  let failCount = 0;

  for (const fact of allFacts) {
    try {
      const plainJson = decryptFromHex(fact.encrypted_blob, keys.encryptionKey);
      const doc = JSON.parse(plainJson);
      decrypted.push({ ...fact, doc });

      console.log(`--- Fact ${fact.id} ---`);
      console.log(`  Source:       ${fact.source}`);
      console.log(`  Decay Score:  ${fact.decay_score}`);
      console.log(`  Version:      ${fact.version}`);
      console.log(`  Created:      ${fact.created_at}`);
      console.log(`  Updated:      ${fact.updated_at}`);
      console.log(`  Text:         ${doc.text}`);
      if (doc.metadata) {
        console.log(`  Type:         ${doc.metadata.type || 'N/A'}`);
        console.log(`  Importance:   ${doc.metadata.importance ?? 'N/A'} (raw) = ${doc.metadata.importance != null ? Math.round(doc.metadata.importance * 10) + '/10' : 'N/A'}`);
        console.log(`  Meta Source:  ${doc.metadata.source || 'N/A'}`);
        console.log(`  Meta Created: ${doc.metadata.created_at || 'N/A'}`);
      }
      console.log();
    } catch (err) {
      failCount++;
      console.log(`--- Fact ${fact.id} --- DECRYPTION FAILED: ${err.message}`);
      console.log();
    }
  }

  // Step 5: Analysis
  console.log('='.repeat(70));
  console.log('  QUALITY ANALYSIS');
  console.log('='.repeat(70));
  console.log();

  const autoFacts = decrypted.filter((f) => f.source === 'auto-extraction');
  const explicitFacts = decrypted.filter((f) => f.source === 'explicit');
  const otherFacts = decrypted.filter(
    (f) => f.source !== 'auto-extraction' && f.source !== 'explicit',
  );

  console.log(`Total facts:        ${decrypted.length}`);
  console.log(`  Auto-extracted:   ${autoFacts.length}`);
  console.log(`  Explicit:         ${explicitFacts.length}`);
  if (otherFacts.length > 0) {
    console.log(`  Other sources:    ${otherFacts.length}`);
  }
  console.log(`  Decrypt failures: ${failCount}`);
  console.log();

  // Type distribution
  const typeCounts = {};
  for (const f of decrypted) {
    const t = f.doc.metadata?.type || 'unknown';
    typeCounts[t] = (typeCounts[t] || 0) + 1;
  }
  console.log('Type Distribution:');
  for (const [type, count] of Object.entries(typeCounts).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${type}: ${count}`);
  }
  console.log();

  // Importance distribution
  const importanceValues = decrypted
    .filter((f) => f.doc.metadata?.importance != null)
    .map((f) => f.doc.metadata.importance);
  if (importanceValues.length > 0) {
    const avg = importanceValues.reduce((a, b) => a + b, 0) / importanceValues.length;
    const min = Math.min(...importanceValues);
    const max = Math.max(...importanceValues);
    console.log('Importance (0-1 scale, where 0.5 = 5/10):');
    console.log(`  Min: ${min} (${Math.round(min * 10)}/10)`);
    console.log(`  Max: ${max} (${Math.round(max * 10)}/10)`);
    console.log(`  Avg: ${avg.toFixed(2)} (${Math.round(avg * 10)}/10)`);
  }
  console.log();

  // Decay score distribution
  const decayScores = decrypted.map((f) => f.decay_score);
  if (decayScores.length > 0) {
    console.log('Decay Scores (server-side, 0-10):');
    console.log(`  Min: ${Math.min(...decayScores)}`);
    console.log(`  Max: ${Math.max(...decayScores)}`);
    console.log(`  Avg: ${(decayScores.reduce((a, b) => a + b, 0) / decayScores.length).toFixed(1)}`);
  }
  console.log();

  // Duplicate check (by text)
  const textMap = new Map();
  for (const f of decrypted) {
    const text = f.doc.text;
    if (!textMap.has(text)) {
      textMap.set(text, []);
    }
    textMap.get(text).push(f.id);
  }
  const duplicates = [...textMap.entries()].filter(([, ids]) => ids.length > 1);
  if (duplicates.length > 0) {
    console.log(`DUPLICATES FOUND: ${duplicates.length} texts appear more than once:`);
    for (const [text, ids] of duplicates) {
      console.log(`  "${text.slice(0, 60)}..." -> ${ids.length} copies (IDs: ${ids.join(', ')})`);
    }
  } else {
    console.log('No exact-text duplicates found.');
  }
  console.log();

  // Near-duplicate check (normalized)
  const normalizedMap = new Map();
  for (const f of decrypted) {
    const norm = f.doc.text.toLowerCase().replace(/\s+/g, ' ').trim();
    if (!normalizedMap.has(norm)) {
      normalizedMap.set(norm, []);
    }
    normalizedMap.get(norm).push({ id: f.id, text: f.doc.text });
  }
  const nearDuplicates = [...normalizedMap.entries()].filter(([, entries]) => entries.length > 1);
  if (nearDuplicates.length > 0) {
    console.log(`NEAR-DUPLICATES (case-insensitive): ${nearDuplicates.length}`);
    for (const [norm, entries] of nearDuplicates) {
      console.log(`  "${norm.slice(0, 60)}..." -> ${entries.length} copies`);
    }
  } else {
    console.log('No near-duplicates found (case-insensitive check).');
  }
  console.log();

  console.log('='.repeat(70));
  console.log('  AUDIT COMPLETE');
  console.log('='.repeat(70));
}

main().catch((err) => {
  console.error('Audit failed:', err);
  process.exit(1);
});
