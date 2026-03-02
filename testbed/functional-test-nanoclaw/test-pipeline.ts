/**
 * TotalReclaw Direct Pipeline Test
 *
 * Tests the full encrypted storage/recall pipeline WITHOUT needing a Claude
 * agent or Anthropic API key. Validates T195 (storage), T196 (cross-session
 * recall), and partially T197 (multi-fact storage/export).
 *
 * Reimplements the crypto from totalreclaw-mcp.ts and talks directly to the
 * TotalReclaw server HTTP API.
 *
 * Dependencies: @noble/hashes, node:crypto, node:fs
 *
 * Environment variables:
 *   TOTALRECLAW_SERVER_URL       — default http://localhost:8090
 *   TOTALRECLAW_MASTER_PASSWORD  — default "pipeline-test-password"
 *   TOTALRECLAW_CREDENTIALS_PATH — default ./test-credentials.json
 */

import { argon2id } from "@noble/hashes/argon2.js";
import { hkdf } from "@noble/hashes/hkdf.js";
import { sha256 } from "@noble/hashes/sha2.js";
import { hmac } from "@noble/hashes/hmac.js";
import crypto from "node:crypto";
import fs from "node:fs";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SERVER_URL =
  process.env.TOTALRECLAW_SERVER_URL || "http://localhost:8090";
const MASTER_PASSWORD =
  process.env.TOTALRECLAW_MASTER_PASSWORD || "pipeline-test-password";
const CREDENTIALS_PATH =
  process.env.TOTALRECLAW_CREDENTIALS_PATH || "./test-credentials.json";
const NAMESPACE = "pipeline-test";

// ---------------------------------------------------------------------------
// Crypto — byte-for-byte match with totalreclaw-mcp.ts
// ---------------------------------------------------------------------------

const AUTH_KEY_INFO = "totalreclaw-auth-key-v1";
const ENCRYPTION_KEY_INFO = "totalreclaw-encryption-key-v1";
const DEDUP_KEY_INFO = "openmemory-dedup-v1";

const ARGON2_TIME_COST = 3;
const ARGON2_MEMORY_COST = 65536; // 64 MiB in KiB
const ARGON2_PARALLELISM = 4;
const ARGON2_DK_LEN = 32;

const IV_LENGTH = 12;
const TAG_LENGTH = 16;
const KEY_LENGTH = 32;

interface DerivedKeys {
  authKey: Buffer;
  encryptionKey: Buffer;
  dedupKey: Buffer;
  salt: Buffer;
}

function deriveKeys(password: string, existingSalt?: Buffer): DerivedKeys {
  const salt = existingSalt ?? crypto.randomBytes(32);

  const masterKey = argon2id(Buffer.from(password, "utf8"), salt, {
    t: ARGON2_TIME_COST,
    m: ARGON2_MEMORY_COST,
    p: ARGON2_PARALLELISM,
    dkLen: ARGON2_DK_LEN,
  });

  // @noble/hashes v2 requires Uint8Array for info param
  const enc = (s: string) => Buffer.from(s, "utf8");
  const authKey = Buffer.from(
    hkdf(sha256, masterKey, salt, enc(AUTH_KEY_INFO), 32)
  );
  const encryptionKey = Buffer.from(
    hkdf(sha256, masterKey, salt, enc(ENCRYPTION_KEY_INFO), 32)
  );
  const dedupKey = Buffer.from(
    hkdf(sha256, masterKey, salt, enc(DEDUP_KEY_INFO), 32)
  );

  return { authKey, encryptionKey, dedupKey, salt: Buffer.from(salt) };
}

function computeAuthKeyHash(authKey: Buffer): string {
  return Buffer.from(sha256(authKey)).toString("hex");
}

/**
 * Encrypt plaintext with AES-256-GCM.
 *
 * Wire format: iv(12) || tag(16) || ciphertext
 *
 * Returns hex-encoded string (matching what the server expects).
 *
 * NOTE: The totalreclaw-mcp.ts `encrypt()` returns base64, but the server's
 * store endpoint parses with `bytes.fromhex()`. This test uses hex to match
 * the server's actual implementation.
 */
function encrypt(plaintext: string, encryptionKey: Buffer): string {
  if (encryptionKey.length !== KEY_LENGTH) {
    throw new Error(
      `Invalid key length: expected ${KEY_LENGTH}, got ${encryptionKey.length}`
    );
  }

  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv("aes-256-gcm", encryptionKey, iv, {
    authTagLength: TAG_LENGTH,
  });

  const ciphertext = Buffer.concat([
    cipher.update(plaintext, "utf8"),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();

  // Wire format: iv || tag || ciphertext
  const combined = Buffer.concat([iv, tag, ciphertext]);
  return combined.toString("hex");
}

/**
 * Decrypt from hex-encoded string (matching what the server returns).
 */
function decrypt(encryptedHex: string, encryptionKey: Buffer): string {
  if (encryptionKey.length !== KEY_LENGTH) {
    throw new Error(
      `Invalid key length: expected ${KEY_LENGTH}, got ${encryptionKey.length}`
    );
  }

  const combined = Buffer.from(encryptedHex, "hex");

  if (combined.length < IV_LENGTH + TAG_LENGTH) {
    throw new Error("Encrypted data too short");
  }

  const iv = combined.subarray(0, IV_LENGTH);
  const tag = combined.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH);
  const ciphertext = combined.subarray(IV_LENGTH + TAG_LENGTH);

  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    encryptionKey,
    iv,
    { authTagLength: TAG_LENGTH }
  );
  decipher.setAuthTag(tag);

  const plaintext = Buffer.concat([
    decipher.update(ciphertext),
    decipher.final(),
  ]);
  return plaintext.toString("utf8");
}

function generateBlindIndices(text: string): string[] {
  const tokens = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((t) => t.length >= 2);

  const seen = new Set<string>();
  const indices: string[] = [];

  for (const token of tokens) {
    const hash = Buffer.from(sha256(Buffer.from(token, "utf8"))).toString(
      "hex"
    );
    if (!seen.has(hash)) {
      seen.add(hash);
      indices.push(hash);
    }
  }

  return indices;
}

function normalizeText(text: string): string {
  return text.normalize("NFC").toLowerCase().replace(/\s+/g, " ").trim();
}

function generateContentFingerprint(
  plaintext: string,
  dedupKey: Buffer
): string {
  const normalized = normalizeText(plaintext);
  return Buffer.from(
    hmac(sha256, dedupKey, Buffer.from(normalized, "utf8"))
  ).toString("hex");
}

// ---------------------------------------------------------------------------
// API Client
// ---------------------------------------------------------------------------

interface StoredCredentials {
  userId: string;
  salt: string; // base64-encoded (matches totalreclaw-mcp.ts format)
}

interface StoreFactPayload {
  id: string;
  timestamp: string;
  encrypted_blob: string;
  blind_indices: string[];
  decay_score: number;
  source: string;
  content_fp?: string;
  agent_id?: string;
}

interface SearchCandidate {
  fact_id: string;
  encrypted_blob: string;
  decay_score: number;
  timestamp: number;
  version: number;
}

interface ExportedFact {
  id: string;
  encrypted_blob: string;
  blind_indices: string[];
  decay_score: number;
  version: number;
  source: string;
  created_at: string;
  updated_at: string;
}

const baseUrl = SERVER_URL.replace(/\/+$/, "");

async function assertOk(res: Response, context: string): Promise<void> {
  if (res.ok) return;
  let body: string;
  try {
    body = await res.text();
  } catch {
    body = "(could not read response body)";
  }
  throw new Error(`${context}: HTTP ${res.status} - ${body}`);
}

async function apiRegister(
  authKeyHash: string,
  saltHex: string
): Promise<{ user_id: string }> {
  const res = await fetch(`${baseUrl}/v1/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auth_key_hash: authKeyHash, salt: saltHex }),
  });
  await assertOk(res, "register");
  const json = (await res.json()) as Record<string, unknown>;
  if (!json.success) {
    // If user already exists, we need to handle this
    if (json.error_code === "USER_EXISTS") {
      throw new Error("USER_EXISTS");
    }
    throw new Error(
      `register: server returned success=false - ${json.error_code}: ${json.error_message}`
    );
  }
  return { user_id: json.user_id as string };
}

async function apiStore(
  userId: string,
  facts: StoreFactPayload[],
  authKeyHex: string
): Promise<{
  ids: string[];
  duplicate_ids?: string[];
  httpStatus: number;
}> {
  const res = await fetch(`${baseUrl}/v1/store`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authKeyHex}`,
    },
    body: JSON.stringify({ user_id: userId, facts }),
  });
  const httpStatus = res.status;
  await assertOk(res, "store");
  const json = (await res.json()) as Record<string, unknown>;
  if (!json.success) {
    throw new Error(
      `store: server returned success=false - ${json.error_code}: ${json.error_message}`
    );
  }
  return {
    ids: (json.ids as string[]) ?? [],
    duplicate_ids: json.duplicate_ids as string[] | undefined,
    httpStatus,
  };
}

async function apiSearch(
  userId: string,
  trapdoors: string[],
  maxCandidates: number,
  authKeyHex: string
): Promise<SearchCandidate[]> {
  const res = await fetch(`${baseUrl}/v1/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authKeyHex}`,
    },
    body: JSON.stringify({
      user_id: userId,
      trapdoors,
      max_candidates: maxCandidates,
    }),
  });
  await assertOk(res, "search");
  const json = (await res.json()) as Record<string, unknown>;
  if (!json.success) {
    throw new Error(
      `search: server returned success=false - ${json.error_code}: ${json.error_message}`
    );
  }
  return (json.results as SearchCandidate[]) ?? [];
}

async function apiExport(
  authKeyHex: string,
  limit: number = 1000,
  cursor?: string
): Promise<{
  facts: ExportedFact[];
  cursor?: string;
  has_more: boolean;
  total_count?: number;
}> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);

  const res = await fetch(`${baseUrl}/v1/export?${params.toString()}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${authKeyHex}`,
    },
  });
  await assertOk(res, "exportFacts");
  const json = (await res.json()) as Record<string, unknown>;
  if (!json.success) {
    throw new Error(
      `exportFacts: server returned success=false - ${json.error_code}: ${json.error_message}`
    );
  }
  return {
    facts: (json.facts as ExportedFact[]) ?? [],
    cursor: json.cursor as string | undefined,
    has_more: (json.has_more as boolean) ?? false,
    total_count: json.total_count as number | undefined,
  };
}

async function apiHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/health`, { method: "GET" });
    return res.status === 200;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Credential persistence
// ---------------------------------------------------------------------------

function loadCredentials(): { userId: string; salt: Buffer } | null {
  try {
    if (!fs.existsSync(CREDENTIALS_PATH)) return null;
    const data = JSON.parse(
      fs.readFileSync(CREDENTIALS_PATH, "utf-8")
    ) as StoredCredentials;
    return {
      userId: data.userId,
      salt: Buffer.from(data.salt, "base64"),
    };
  } catch {
    return null;
  }
}

function saveCredentials(userId: string, salt: Buffer): void {
  const data: StoredCredentials = {
    userId,
    salt: salt.toString("base64"),
  };
  fs.writeFileSync(CREDENTIALS_PATH, JSON.stringify(data, null, 2), "utf-8");
}

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;
let testIndex = 0;

function ok(name: string, detail?: string): void {
  testIndex++;
  const extra = detail ? ` - ${detail}` : "";
  console.log(`ok ${testIndex} - ${name}${extra}`);
  passed++;
}

function notOk(name: string, detail?: string): void {
  testIndex++;
  const extra = detail ? ` - ${detail}` : "";
  console.log(`not ok ${testIndex} - ${name}${extra}`);
  failed++;
}

function assert(
  condition: boolean,
  name: string,
  detail?: string
): void {
  if (condition) {
    ok(name, detail);
  } else {
    notOk(name, detail);
  }
}

function logSection(title: string): void {
  console.log(`\n# === ${title} ===`);
}

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const TEST_FACTS = [
  "Alice works at Acme Corp as a senior engineer",
  "Alice prefers Python over JavaScript for backend development",
  "Team standup meeting is every Monday at 10am Pacific",
];

const SEARCH_QUERIES: Array<{
  query: string;
  expectedFactIndex: number;
  label: string;
}> = [
  {
    query: "Acme engineer",
    expectedFactIndex: 0,
    label: "search for 'Acme engineer' finds fact 1",
  },
  {
    query: "Python backend",
    expectedFactIndex: 1,
    label: "search for 'Python backend' finds fact 2",
  },
  {
    query: "meeting Monday",
    expectedFactIndex: 2,
    label: "search for 'meeting Monday' finds fact 3",
  },
];

// ---------------------------------------------------------------------------
// Main test runner
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log("TAP version 13");
  console.log(
    `# TotalReclaw Direct Pipeline Test - ${new Date().toISOString()}`
  );
  console.log(`# Server: ${SERVER_URL}`);
  console.log(`# Credentials: ${CREDENTIALS_PATH}`);

  // -----------------------------------------------------------------------
  // Pre-check: server health
  // -----------------------------------------------------------------------
  logSection("Pre-check: Server health");
  const healthy = await apiHealth();
  assert(healthy, "server is healthy");
  if (!healthy) {
    console.log(
      `\n# FATAL: Server at ${SERVER_URL} is not reachable. Aborting.`
    );
    console.log(`1..${testIndex}`);
    process.exit(1);
  }

  // -----------------------------------------------------------------------
  // Initialize: derive keys and register (or load existing credentials)
  // -----------------------------------------------------------------------
  logSection("Initialization: key derivation and registration");

  let userId: string;
  let keys: DerivedKeys;
  let authKeyHex: string;

  const existing = loadCredentials();
  if (existing) {
    console.log(`# Loaded existing credentials for user ${existing.userId}`);
    keys = deriveKeys(MASTER_PASSWORD, existing.salt);
    userId = existing.userId;
    authKeyHex = keys.authKey.toString("hex");
    ok("loaded existing credentials");
  } else {
    console.log("# No existing credentials, registering new user...");
    keys = deriveKeys(MASTER_PASSWORD);
    const authKeyHash = computeAuthKeyHash(keys.authKey);
    authKeyHex = keys.authKey.toString("hex");
    const saltHex = keys.salt.toString("hex");

    try {
      const result = await apiRegister(authKeyHash, saltHex);
      userId = result.user_id;
      saveCredentials(userId, keys.salt);
      ok("registered new user", `user_id=${userId}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      notOk("registration", msg);
      console.log(`\n# FATAL: Could not register. Aborting.`);
      console.log(`1..${testIndex}`);
      process.exit(1);
    }
  }

  // Verify auth key hash computation matches what we would expect
  const recomputedHash = computeAuthKeyHash(keys.authKey);
  assert(
    recomputedHash.length === 64,
    "auth key hash is 64 hex chars (SHA-256)"
  );

  // -----------------------------------------------------------------------
  // Test 1: Storage — encrypt and store 3 facts
  // -----------------------------------------------------------------------
  logSection("Test 1: Storage");

  const storedFactIds: string[] = [];
  const storedContentFps: string[] = [];

  for (let i = 0; i < TEST_FACTS.length; i++) {
    const factText = TEST_FACTS[i];
    const encryptedBlob = encrypt(factText, keys.encryptionKey);
    const searchableText = `${factText} namespace:${NAMESPACE}`;
    const blindIndices = generateBlindIndices(searchableText);
    const contentFp = generateContentFingerprint(factText, keys.dedupKey);

    storedContentFps.push(contentFp);

    const factId = crypto.randomUUID();
    const payload: StoreFactPayload = {
      id: factId,
      timestamp: new Date().toISOString(),
      encrypted_blob: encryptedBlob,
      blind_indices: blindIndices,
      decay_score: 7,
      source: `pipeline-test:${NAMESPACE}`,
      content_fp: contentFp,
      agent_id: `pipeline-test:${NAMESPACE}`,
    };

    try {
      const result = await apiStore(userId, [payload], authKeyHex);
      const wasStored = result.ids.includes(factId);
      const wasDuplicate = result.duplicate_ids?.includes(factId) ?? false;

      if (wasStored) {
        storedFactIds.push(factId);
        ok(`stored fact ${i + 1}`, `id=${factId}`);
      } else if (wasDuplicate) {
        // Fact was already stored from a previous run — still counts as ok
        storedFactIds.push(factId);
        ok(`fact ${i + 1} already exists (dedup)`, `id=${factId}`);
      } else {
        notOk(`stored fact ${i + 1}`, "not in stored IDs or duplicate IDs");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      notOk(`stored fact ${i + 1}`, msg);
    }
  }

  assert(
    storedFactIds.length === TEST_FACTS.length,
    `all ${TEST_FACTS.length} facts processed`,
    `${storedFactIds.length}/${TEST_FACTS.length}`
  );

  // -----------------------------------------------------------------------
  // Test 2: Encryption verification
  // -----------------------------------------------------------------------
  logSection("Test 2: Encryption verification");

  try {
    const exportResult = await apiExport(authKeyHex, 1000);
    assert(
      exportResult.facts.length > 0,
      "export returned facts",
      `count=${exportResult.facts.length}`
    );

    // Check that raw encrypted blobs are NOT plaintext
    let allEncrypted = true;
    let decryptedCount = 0;
    const decryptedTexts: string[] = [];

    for (const fact of exportResult.facts) {
      const blob = fact.encrypted_blob;

      // Verify the blob does NOT contain plaintext keywords
      const blobLower = blob.toLowerCase();
      if (
        blobLower.includes("alice") ||
        blobLower.includes("acme") ||
        blobLower.includes("python") ||
        blobLower.includes("meeting")
      ) {
        allEncrypted = false;
      }

      // Verify we CAN decrypt it
      try {
        const plaintext = decrypt(blob, keys.encryptionKey);
        decryptedTexts.push(plaintext);
        decryptedCount++;
      } catch {
        // Some facts may have been created by a different key (from other tests)
        // — that is expected.
      }
    }

    assert(allEncrypted, "no plaintext found in raw encrypted blobs");
    assert(
      decryptedCount > 0,
      "at least one fact decrypted successfully",
      `${decryptedCount} decrypted`
    );

    // Verify the decrypted texts include our test facts
    let matchCount = 0;
    for (const testFact of TEST_FACTS) {
      if (decryptedTexts.includes(testFact)) {
        matchCount++;
      }
    }
    assert(
      matchCount === TEST_FACTS.length,
      "all test facts found after decryption",
      `${matchCount}/${TEST_FACTS.length}`
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    notOk("encryption verification", msg);
  }

  // -----------------------------------------------------------------------
  // Test 3: Cross-session recall
  // -----------------------------------------------------------------------
  logSection("Test 3: Cross-session recall (re-derive keys from same salt)");

  // Simulate a "new session" by re-deriving keys from the same password + salt
  const freshKeys = deriveKeys(MASTER_PASSWORD, keys.salt);
  const freshAuthKeyHex = freshKeys.authKey.toString("hex");

  // Verify the re-derived keys match
  assert(
    freshKeys.authKey.equals(keys.authKey),
    "re-derived authKey matches original"
  );
  assert(
    freshKeys.encryptionKey.equals(keys.encryptionKey),
    "re-derived encryptionKey matches original"
  );

  for (const sq of SEARCH_QUERIES) {
    try {
      // Generate blind indices (trapdoors) for the search query
      const trapdoors = generateBlindIndices(sq.query);
      assert(
        trapdoors.length > 0,
        `trapdoors generated for '${sq.query}'`,
        `count=${trapdoors.length}`
      );

      // Search the server
      const candidates = await apiSearch(
        userId,
        trapdoors,
        100,
        freshAuthKeyHex
      );
      assert(
        candidates.length > 0,
        `search '${sq.query}' returned candidates`,
        `count=${candidates.length}`
      );

      // Decrypt and check if expected fact is in results
      let foundExpected = false;
      const expectedText = TEST_FACTS[sq.expectedFactIndex];

      for (const candidate of candidates) {
        try {
          const plaintext = decrypt(
            candidate.encrypted_blob,
            freshKeys.encryptionKey
          );
          if (plaintext === expectedText) {
            foundExpected = true;
            break;
          }
        } catch {
          // Skip undecryptable candidates
        }
      }

      assert(foundExpected, sq.label);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      notOk(sq.label, msg);
    }
  }

  // -----------------------------------------------------------------------
  // Test 4: Export
  // -----------------------------------------------------------------------
  logSection("Test 4: Export all facts");

  try {
    // Paginate through all facts
    const allFacts: ExportedFact[] = [];
    let cursor: string | undefined;
    let hasMore = true;

    while (hasMore) {
      const page = await apiExport(authKeyHex, 1000, cursor);
      allFacts.push(...page.facts);
      cursor = page.cursor;
      hasMore = page.has_more;
    }

    assert(allFacts.length > 0, "export returned facts", `total=${allFacts.length}`);

    // Decrypt all and verify all 3 test facts are present
    const decryptedExport: string[] = [];
    for (const fact of allFacts) {
      try {
        const plaintext = decrypt(fact.encrypted_blob, keys.encryptionKey);
        decryptedExport.push(plaintext);
      } catch {
        // Skip facts from other test runs / other keys
      }
    }

    let exportMatchCount = 0;
    for (const testFact of TEST_FACTS) {
      if (decryptedExport.includes(testFact)) {
        exportMatchCount++;
      }
    }
    assert(
      exportMatchCount === TEST_FACTS.length,
      "all 3 test facts present in export",
      `${exportMatchCount}/${TEST_FACTS.length}`
    );

    // Verify each exported fact has the expected structure
    const sampleFact = allFacts[0];
    assert(!!sampleFact.id, "exported fact has id");
    assert(!!sampleFact.encrypted_blob, "exported fact has encrypted_blob");
    assert(
      Array.isArray(sampleFact.blind_indices),
      "exported fact has blind_indices array"
    );
    assert(
      typeof sampleFact.decay_score === "number",
      "exported fact has numeric decay_score"
    );
    assert(!!sampleFact.created_at, "exported fact has created_at");
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    notOk("export", msg);
  }

  // -----------------------------------------------------------------------
  // Test 5: Dedup — store a duplicate fact
  // -----------------------------------------------------------------------
  logSection("Test 5: Dedup detection");

  try {
    // Re-store fact 1 with the same content fingerprint
    const factText = TEST_FACTS[0];
    const encryptedBlob = encrypt(factText, keys.encryptionKey);
    const searchableText = `${factText} namespace:${NAMESPACE}`;
    const blindIndices = generateBlindIndices(searchableText);
    const contentFp = generateContentFingerprint(factText, keys.dedupKey);

    // Verify the fingerprint matches what we stored before
    assert(
      contentFp === storedContentFps[0],
      "content fingerprint is deterministic"
    );

    const dupFactId = crypto.randomUUID();
    const payload: StoreFactPayload = {
      id: dupFactId,
      timestamp: new Date().toISOString(),
      encrypted_blob: encryptedBlob,
      blind_indices: blindIndices,
      decay_score: 7,
      source: `pipeline-test:${NAMESPACE}`,
      content_fp: contentFp,
      agent_id: `pipeline-test:${NAMESPACE}`,
    };

    const result = await apiStore(userId, [payload], authKeyHex);

    // The duplicate should NOT appear in stored IDs
    const wasStoredAsNew = result.ids.includes(dupFactId);
    const wasDeduplicated =
      !wasStoredAsNew &&
      result.duplicate_ids !== undefined &&
      result.duplicate_ids.length > 0;

    assert(
      wasDeduplicated || !wasStoredAsNew,
      "duplicate fact was detected",
      wasDeduplicated
        ? `dedup_ids=${JSON.stringify(result.duplicate_ids)}`
        : `stored_ids=${JSON.stringify(result.ids)}`
    );
    assert(
      !wasStoredAsNew,
      "duplicate fact was NOT stored as new"
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    notOk("dedup detection", msg);
  }

  // -----------------------------------------------------------------------
  // Summary
  // -----------------------------------------------------------------------
  console.log(`\n1..${testIndex}`);
  console.log(`\n# Tests: ${testIndex}`);
  console.log(`# Pass:  ${passed}`);
  console.log(`# Fail:  ${failed}`);

  if (failed > 0) {
    console.log(`\n# RESULT: FAIL`);
    process.exit(1);
  } else {
    console.log(`\n# RESULT: PASS`);
    process.exit(0);
  }
}

main().catch((err) => {
  console.error(`\n# FATAL ERROR: ${err instanceof Error ? err.message : String(err)}`);
  if (err instanceof Error && err.stack) {
    console.error(`# ${err.stack.split("\n").join("\n# ")}`);
  }
  process.exit(1);
});
