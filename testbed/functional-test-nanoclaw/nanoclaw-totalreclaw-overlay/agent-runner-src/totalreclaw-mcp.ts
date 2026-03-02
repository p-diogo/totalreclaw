/**
 * TotalReclaw MCP Server for NanoClaw
 *
 * Self-contained stdio MCP server that provides zero-knowledge encrypted
 * memory tools. Crypto and API client logic copied from the OpenClaw plugin
 * (skill/plugin/crypto.ts, skill/plugin/api-client.ts) to remain fully
 * self-contained with only two external deps:
 *   - @modelcontextprotocol/sdk (already in agent-runner)
 *   - @noble/hashes (added via Dockerfile.nanoclaw-totalreclaw)
 *
 * Environment variables:
 *   TOTALRECLAW_SERVER_URL       — defaults to http://totalreclaw-server:8080
 *   TOTALRECLAW_MASTER_PASSWORD  — REQUIRED
 *   TOTALRECLAW_NAMESPACE        — defaults to group folder name
 *   TOTALRECLAW_CREDENTIALS_PATH — defaults to /workspace/.totalreclaw/credentials.json
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { argon2id } from '@noble/hashes/argon2.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { hmac } from '@noble/hashes/hmac.js';
import { mnemonicToSeedSync, validateMnemonic } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english.js';
import { stemmer } from 'porter-stemmer';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SERVER_URL = process.env.TOTALRECLAW_SERVER_URL || 'http://totalreclaw-server:8080';
const MASTER_PASSWORD = process.env.TOTALRECLAW_MASTER_PASSWORD || '';
const NAMESPACE = process.env.TOTALRECLAW_NAMESPACE || 'default';
const CREDENTIALS_PATH = process.env.TOTALRECLAW_CREDENTIALS_PATH || '/workspace/.totalreclaw/credentials.json';

function log(msg: string): void {
  console.error(`[totalreclaw-mcp] ${msg}`);
}

// =========================================================================
// Local Embedding via @huggingface/transformers (bge-small-en-v1.5 ONNX)
// =========================================================================

/**
 * Local embedding generation using Xenova/bge-small-en-v1.5 ONNX model.
 * No API key needed -- runs entirely client-side, preserving zero-knowledge.
 *
 * Model details:
 *   - Quantized (int8) ONNX: ~33.8MB download on first use, cached in ~/.cache/huggingface/
 *   - Lazy init: first call ~2-3s (model load), subsequent ~15ms
 *   - Output: 384-dimensional normalized embedding vector
 *   - For retrieval, queries should be prefixed with an instruction string
 *     (documents/passages should NOT be prefixed)
 */

// @ts-ignore - @huggingface/transformers types
import { pipeline } from '@huggingface/transformers';

const EMBEDDING_MODEL_ID = 'Xenova/bge-small-en-v1.5';
const EMBEDDING_DIM = 384;

/**
 * Query instruction prefix for bge-small-en-v1.5 retrieval tasks.
 *
 * Per the BAAI model card: prepend this to short queries when searching
 * for relevant passages. Do NOT prepend for documents/passages being stored.
 */
const QUERY_PREFIX = 'Represent this sentence for searching relevant passages: ';

let embeddingPipeline: any = null;

/**
 * Get the embedding vector dimensions (always 384 for bge-small-en-v1.5).
 */
function getEmbeddingDims(): number {
  return EMBEDDING_DIM;
}

/**
 * Generate a 384-dimensional embedding vector for the given text.
 * On first call, downloads and loads the ONNX model (~33.8MB, cached).
 *
 * For bge-small-en-v1.5, queries should set `isQuery: true` to prepend the
 * retrieval instruction prefix. Documents being stored should use the default
 * (`isQuery: false`) so no prefix is added.
 *
 * @param text - The text to embed.
 * @param options - Optional settings.
 * @param options.isQuery - If true, prepend the BGE query instruction prefix
 *                          for improved retrieval accuracy (default: false).
 */
async function generateEmbedding(
  text: string,
  options?: { isQuery?: boolean },
): Promise<number[]> {
  if (!embeddingPipeline) {
    embeddingPipeline = await pipeline('feature-extraction', EMBEDDING_MODEL_ID, {
      quantized: true,
    });
  }

  const input = options?.isQuery ? QUERY_PREFIX + text : text;
  const output = await embeddingPipeline(input, { pooling: 'mean', normalize: true });
  return Array.from(output.data as Float32Array);
}

// =========================================================================
// LSH Hasher (copied from skill/plugin/lsh.ts — must match byte-for-byte)
// =========================================================================

/**
 * Random Hyperplane LSH hasher.
 *
 * Deterministic hyperplane generation from seed (HKDF + Box-Muller).
 * Produces blind-hashed bucket IDs that merge with word-based blind indices.
 *
 * Default parameters:
 *   - 32 bits per table (balanced discrimination vs. recall)
 *   - 20 tables (moderate table count for good coverage)
 *   - Middle ground between 64-bit x 12 (too strict) and 12-bit x 28 (too loose)
 */
class LSHHasher {
  private hyperplanes: Float64Array[];
  private readonly dims: number;
  private readonly nTables: number;
  private readonly nBits: number;

  constructor(seed: Uint8Array, dims: number, nTables: number = 20, nBits: number = 32) {
    if (seed.length < 16) throw new Error(`LSH seed too short: expected >= 16 bytes, got ${seed.length}`);
    if (dims < 1) throw new Error(`dims must be positive, got ${dims}`);
    if (nTables < 1) throw new Error(`nTables must be positive, got ${nTables}`);
    if (nBits < 1) throw new Error(`nBits must be positive, got ${nBits}`);

    this.dims = dims;
    this.nTables = nTables;
    this.nBits = nBits;
    this.hyperplanes = new Array(nTables);

    for (let t = 0; t < nTables; t++) {
      this.hyperplanes[t] = this.generateTableHyperplanes(seed, t);
    }
  }

  private generateTableHyperplanes(seed: Uint8Array, tableIndex: number): Float64Array {
    const BYTES_PER_FLOAT = 8;
    const totalFloats = this.dims * this.nBits;
    const totalBytes = totalFloats * BYTES_PER_FLOAT;

    const randomBytes = this.deriveRandomBytes(seed, `lsh_table_${tableIndex}`, totalBytes);
    const hyperplaneMatrix = new Float64Array(totalFloats);
    const view = new DataView(randomBytes.buffer, randomBytes.byteOffset, randomBytes.byteLength);

    for (let i = 0; i < totalFloats; i++) {
      const offset = i * BYTES_PER_FLOAT;
      const u1Raw = view.getUint32(offset, true);
      const u2Raw = view.getUint32(offset + 4, true);
      const u1 = (u1Raw + 1) / (0xFFFFFFFF + 2);
      const u2 = (u2Raw + 1) / (0xFFFFFFFF + 2);
      hyperplaneMatrix[i] = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
    }

    return hyperplaneMatrix;
  }

  private deriveRandomBytes(seed: Uint8Array, baseInfo: string, length: number): Uint8Array {
    const MAX_HKDF_OUTPUT = 255 * 32;
    const result = new Uint8Array(length);
    let offset = 0;
    let blockIndex = 0;

    while (offset < length) {
      const remaining = length - offset;
      const chunkLen = Math.min(remaining, MAX_HKDF_OUTPUT);
      const info = Buffer.from(`${baseInfo}_block_${blockIndex}`, 'utf8');
      const chunk = hkdf(sha256, seed, new Uint8Array(0), info, chunkLen);
      result.set(new Uint8Array(chunk), offset);
      offset += chunkLen;
      blockIndex++;
    }

    return result;
  }

  hash(embedding: number[]): string[] {
    if (embedding.length !== this.dims) {
      throw new Error(`Embedding dimension mismatch: expected ${this.dims}, got ${embedding.length}`);
    }

    const results: string[] = new Array(this.nTables);

    for (let t = 0; t < this.nTables; t++) {
      const matrix = this.hyperplanes[t];
      const bits = new Array<string>(this.nBits);

      for (let b = 0; b < this.nBits; b++) {
        const baseOffset = b * this.dims;
        let dot = 0;
        for (let d = 0; d < this.dims; d++) {
          dot += matrix[baseOffset + d] * embedding[d];
        }
        bits[b] = dot >= 0 ? '1' : '0';
      }

      const signature = bits.join('');
      const bucketId = `lsh_t${t}_${signature}`;
      const hashBytes = sha256(Buffer.from(bucketId, 'utf8'));
      results[t] = Buffer.from(hashBytes).toString('hex');
    }

    return results;
  }

  get tables(): number { return this.nTables; }
  get bits(): number { return this.nBits; }
  get dimensions(): number { return this.dims; }
}

// =========================================================================
// LSH Seed Derivation
// =========================================================================

const LSH_SEED_INFO = 'openmemory-lsh-seed-v1';

/**
 * Derive a 32-byte seed for the LSH hasher from the master key chain.
 * Mirrors skill/plugin/crypto.ts deriveLshSeed().
 */
function deriveLshSeed(password: string, salt: Buffer): Uint8Array {
  if (isBip39Mnemonic(password)) {
    const seed = mnemonicToSeedSync(password.trim());
    return new Uint8Array(
      hkdf(sha256, Buffer.from(seed), salt, Buffer.from(LSH_SEED_INFO, 'utf8'), 32),
    );
  }

  const masterKey = argon2id(
    Buffer.from(password, 'utf8'),
    salt,
    { t: ARGON2_TIME_COST, m: ARGON2_MEMORY_COST, p: ARGON2_PARALLELISM, dkLen: ARGON2_DK_LEN },
  );

  return new Uint8Array(
    hkdf(sha256, masterKey, salt, Buffer.from(LSH_SEED_INFO, 'utf8'), 32),
  );
}

// =========================================================================
// Crypto (copied from skill/plugin/crypto.ts — must match byte-for-byte)
// =========================================================================

const AUTH_KEY_INFO = 'totalreclaw-auth-key-v1';
const ENCRYPTION_KEY_INFO = 'totalreclaw-encryption-key-v1';
const DEDUP_KEY_INFO = 'openmemory-dedup-v1';

const ARGON2_TIME_COST = 3;
const ARGON2_MEMORY_COST = 65536; // 64 MB in KiB
const ARGON2_PARALLELISM = 4;
const ARGON2_DK_LEN = 32;

const IV_LENGTH = 12;
const TAG_LENGTH = 16;
const KEY_LENGTH = 32;

/**
 * Check if the input is a BIP-39 mnemonic (12 or 24 words from the English wordlist).
 */
function isBip39Mnemonic(input: string): boolean {
  const words = input.trim().split(/\s+/);
  if (words.length !== 12 && words.length !== 24) return false;
  return validateMnemonic(input.trim(), wordlist);
}

/**
 * Derive keys from a BIP-39 mnemonic using the 512-bit seed as HKDF input.
 */
function deriveKeysFromMnemonic(
  mnemonic: string,
): { authKey: Buffer; encryptionKey: Buffer; dedupKey: Buffer; salt: Buffer } {
  const seed = mnemonicToSeedSync(mnemonic.trim());
  const salt = Buffer.from(seed.slice(0, 32));
  const seedBuf = Buffer.from(seed);
  const enc = (s: string) => new Uint8Array(Buffer.from(s, 'utf8'));

  const authKey = Buffer.from(
    hkdf(sha256, seedBuf, salt, enc(AUTH_KEY_INFO), 32),
  );
  const encryptionKey = Buffer.from(
    hkdf(sha256, seedBuf, salt, enc(ENCRYPTION_KEY_INFO), 32),
  );
  const dedupKey = Buffer.from(
    hkdf(sha256, seedBuf, salt, enc(DEDUP_KEY_INFO), 32),
  );

  return { authKey, encryptionKey, dedupKey, salt };
}

function deriveKeys(
  password: string,
  existingSalt?: Buffer,
): { authKey: Buffer; encryptionKey: Buffer; dedupKey: Buffer; salt: Buffer } {
  // BIP-39 mnemonic path: skip Argon2id, derive directly from 512-bit seed
  if (isBip39Mnemonic(password)) {
    return deriveKeysFromMnemonic(password);
  }

  const salt = existingSalt ?? crypto.randomBytes(32);

  const masterKey = argon2id(
    Buffer.from(password, 'utf8'),
    salt,
    { t: ARGON2_TIME_COST, m: ARGON2_MEMORY_COST, p: ARGON2_PARALLELISM, dkLen: ARGON2_DK_LEN },
  );

  // @noble/hashes v2 requires Uint8Array for info param
  const enc = (s: string) => Buffer.from(s, 'utf8');
  const authKey = Buffer.from(
    hkdf(sha256, masterKey, salt, enc(AUTH_KEY_INFO), 32),
  );
  const encryptionKey = Buffer.from(
    hkdf(sha256, masterKey, salt, enc(ENCRYPTION_KEY_INFO), 32),
  );
  const dedupKey = Buffer.from(
    hkdf(sha256, masterKey, salt, enc(DEDUP_KEY_INFO), 32),
  );

  return { authKey, encryptionKey, dedupKey, salt: Buffer.from(salt) };
}

function computeAuthKeyHash(authKey: Buffer): string {
  return Buffer.from(sha256(authKey)).toString('hex');
}

function encrypt(plaintext: string, encryptionKey: Buffer): string {
  if (encryptionKey.length !== KEY_LENGTH) {
    throw new Error(`Invalid key length: expected ${KEY_LENGTH}, got ${encryptionKey.length}`);
  }

  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv('aes-256-gcm', encryptionKey, iv, {
    authTagLength: TAG_LENGTH,
  });

  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();

  // Wire format: iv || tag || ciphertext (same order as client library)
  const combined = Buffer.concat([iv, tag, ciphertext]);
  return combined.toString('base64');
}

function decrypt(encryptedBase64: string, encryptionKey: Buffer): string {
  if (encryptionKey.length !== KEY_LENGTH) {
    throw new Error(`Invalid key length: expected ${KEY_LENGTH}, got ${encryptionKey.length}`);
  }

  const combined = Buffer.from(encryptedBase64, 'base64');

  if (combined.length < IV_LENGTH + TAG_LENGTH) {
    throw new Error('Encrypted data too short');
  }

  const iv = combined.subarray(0, IV_LENGTH);
  const tag = combined.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH);
  const ciphertext = combined.subarray(IV_LENGTH + TAG_LENGTH);

  const decipher = crypto.createDecipheriv('aes-256-gcm', encryptionKey, iv, {
    authTagLength: TAG_LENGTH,
  });
  decipher.setAuthTag(tag);

  const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return plaintext.toString('utf8');
}

function generateBlindIndices(text: string): string[] {
  const tokens = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 2);

  const seen = new Set<string>();
  const indices: string[] = [];

  for (const token of tokens) {
    // Exact word hash (unchanged behavior).
    const hash = Buffer.from(sha256(Buffer.from(token, 'utf8'))).toString('hex');
    if (!seen.has(hash)) {
      seen.add(hash);
      indices.push(hash);
    }

    // Stemmed word hash. The stem is prefixed with "stem:" before hashing
    // to avoid collisions between a word that happens to equal another
    // word's stem (e.g., the word "commun" vs the stem of "community").
    const stem = stemmer(token);
    if (stem.length >= 2 && stem !== token) {
      const stemHash = Buffer.from(
        sha256(Buffer.from(`stem:${stem}`, 'utf8'))
      ).toString('hex');
      if (!seen.has(stemHash)) {
        seen.add(stemHash);
        indices.push(stemHash);
      }
    }
  }

  return indices;
}

function normalizeText(text: string): string {
  return text
    .normalize('NFC')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function generateContentFingerprint(plaintext: string, dedupKey: Buffer): string {
  const normalized = normalizeText(plaintext);
  return Buffer.from(
    hmac(sha256, dedupKey, Buffer.from(normalized, 'utf8')),
  ).toString('hex');
}

// =========================================================================
// API Client (copied from skill/plugin/api-client.ts)
// =========================================================================

interface StoreFactPayload {
  id: string;
  timestamp: string;
  encrypted_blob: string;
  blind_indices: string[];
  decay_score: number;
  source: string;
  content_fp?: string;
  agent_id?: string;
  encrypted_embedding?: string;
}

interface SearchCandidate {
  fact_id: string;
  encrypted_blob: string;
  decay_score: number;
  timestamp: number;
  version: number;
  encrypted_embedding?: string;
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

function createApiClient(serverUrl: string) {
  const baseUrl = serverUrl.replace(/\/+$/, '');

  async function assertOk(res: Response, context: string): Promise<void> {
    if (res.ok) return;
    let body: string;
    try {
      body = await res.text();
    } catch {
      body = '(could not read response body)';
    }
    throw new Error(`${context}: HTTP ${res.status} - ${body}`);
  }

  return {
    async register(
      authKeyHash: string,
      saltHex: string,
    ): Promise<{ user_id: string }> {
      const res = await fetch(`${baseUrl}/v1/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auth_key_hash: authKeyHash, salt: saltHex }),
      });
      await assertOk(res, 'register');
      const json = (await res.json()) as Record<string, unknown>;
      if (!json.success) {
        throw new Error(
          `register: server returned success=false - ${json.error_code}: ${json.error_message}`,
        );
      }
      return { user_id: json.user_id as string };
    },

    async store(
      userId: string,
      facts: StoreFactPayload[],
      authKeyHex: string,
    ): Promise<{ ids: string[]; duplicate_ids?: string[] }> {
      const res = await fetch(`${baseUrl}/v1/store`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authKeyHex}`,
        },
        body: JSON.stringify({ user_id: userId, facts }),
      });
      await assertOk(res, 'store');
      const json = (await res.json()) as Record<string, unknown>;
      if (!json.success) {
        throw new Error(
          `store: server returned success=false - ${json.error_code}: ${json.error_message}`,
        );
      }
      return {
        ids: (json.ids as string[]) ?? [],
        duplicate_ids: json.duplicate_ids as string[] | undefined,
      };
    },

    async search(
      userId: string,
      trapdoors: string[],
      maxCandidates: number,
      authKeyHex: string,
    ): Promise<SearchCandidate[]> {
      const res = await fetch(`${baseUrl}/v1/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authKeyHex}`,
        },
        body: JSON.stringify({
          user_id: userId,
          trapdoors,
          max_candidates: maxCandidates,
        }),
      });
      await assertOk(res, 'search');
      const json = (await res.json()) as Record<string, unknown>;
      if (!json.success) {
        throw new Error(
          `search: server returned success=false - ${json.error_code}: ${json.error_message}`,
        );
      }
      return (json.results as SearchCandidate[]) ?? [];
    },

    async deleteFact(factId: string, authKeyHex: string): Promise<void> {
      const res = await fetch(`${baseUrl}/v1/facts/${encodeURIComponent(factId)}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${authKeyHex}`,
        },
      });
      await assertOk(res, 'deleteFact');
      const json = (await res.json()) as Record<string, unknown>;
      if (!json.success) {
        throw new Error(
          `deleteFact: server returned success=false - ${json.error_code}: ${json.error_message}`,
        );
      }
    },

    async exportFacts(
      authKeyHex: string,
      limit: number = 1000,
      cursor?: string,
    ): Promise<{ facts: ExportedFact[]; cursor?: string; has_more: boolean; total_count?: number }> {
      const params = new URLSearchParams({ limit: String(limit) });
      if (cursor) params.set('cursor', cursor);

      const res = await fetch(`${baseUrl}/v1/export?${params.toString()}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${authKeyHex}`,
        },
      });
      await assertOk(res, 'exportFacts');
      const json = (await res.json()) as Record<string, unknown>;
      if (!json.success) {
        throw new Error(
          `exportFacts: server returned success=false - ${json.error_code}: ${json.error_message}`,
        );
      }
      return {
        facts: (json.facts as ExportedFact[]) ?? [],
        cursor: json.cursor as string | undefined,
        has_more: (json.has_more as boolean) ?? false,
        total_count: json.total_count as number | undefined,
      };
    },

    async health(): Promise<boolean> {
      try {
        const res = await fetch(`${baseUrl}/health`, { method: 'GET' });
        return res.status === 200;
      } catch {
        return false;
      }
    },
  };
}

// =========================================================================
// State Management
// =========================================================================

interface DerivedState {
  userId: string;
  authKey: Buffer;
  encryptionKey: Buffer;
  dedupKey: Buffer;
  salt: Buffer;
  authKeyHex: string;
}

let state: DerivedState | null = null;
const api = createApiClient(SERVER_URL);

interface StoredCredentials {
  userId: string;
  salt: string; // base64-encoded
}

function loadCredentials(): { userId: string; salt: Buffer } | null {
  try {
    if (!fs.existsSync(CREDENTIALS_PATH)) return null;
    const data = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf-8')) as StoredCredentials;
    return {
      userId: data.userId,
      salt: Buffer.from(data.salt, 'base64'),
    };
  } catch {
    return null;
  }
}

function saveCredentials(userId: string, salt: Buffer): void {
  const dir = path.dirname(CREDENTIALS_PATH);
  fs.mkdirSync(dir, { recursive: true });
  const data: StoredCredentials = {
    userId,
    salt: salt.toString('base64'),
  };
  fs.writeFileSync(CREDENTIALS_PATH, JSON.stringify(data, null, 2), 'utf-8');
}

/**
 * Lazy initialization: derive keys + register/login on first tool call.
 */
async function ensureInitialized(): Promise<DerivedState> {
  if (state) return state;

  if (!MASTER_PASSWORD) {
    throw new Error('TOTALRECLAW_MASTER_PASSWORD is not set');
  }

  const existing = loadCredentials();

  if (existing) {
    // Restore keys from existing salt
    log(`Restoring credentials for user ${existing.userId}`);
    const keys = deriveKeys(MASTER_PASSWORD, existing.salt);
    state = {
      userId: existing.userId,
      authKey: keys.authKey,
      encryptionKey: keys.encryptionKey,
      dedupKey: keys.dedupKey,
      salt: keys.salt,
      authKeyHex: keys.authKey.toString('hex'),
    };
    return state;
  }

  // Fresh registration
  log('No credentials found, registering new user...');
  const keys = deriveKeys(MASTER_PASSWORD);
  const authKeyHash = computeAuthKeyHash(keys.authKey);
  const saltHex = keys.salt.toString('hex');

  const { user_id } = await api.register(authKeyHash, saltHex);
  log(`Registered user: ${user_id}`);

  saveCredentials(user_id, keys.salt);

  state = {
    userId: user_id,
    authKey: keys.authKey,
    encryptionKey: keys.encryptionKey,
    dedupKey: keys.dedupKey,
    salt: keys.salt,
    authKeyHex: keys.authKey.toString('hex'),
  };

  return state;
}

// =========================================================================
// Dynamic Candidate Pool Sizing
// =========================================================================

/** Cached fact count for dynamic candidate pool sizing. */
let cachedFactCount: number | null = null;
/** Timestamp of last fact count fetch (ms). */
let lastFactCountFetch: number = 0;
/** Cache TTL for fact count: 5 minutes. */
const FACT_COUNT_CACHE_TTL = 5 * 60 * 1000;

/**
 * Compute the candidate pool size from a fact count.
 *
 * Formula: pool = min(max(factCount * 3, 400), 5000)
 *   - At least 400 candidates (even for tiny vaults)
 *   - At most 5000 candidates (to bound decryption + reranking cost)
 *   - 3x fact count in between
 */
function computeCandidatePool(factCount: number): number {
  return Math.min(Math.max(factCount * 3, 400), 5000);
}

/**
 * Fetch the user's fact count from the server, with caching.
 *
 * Uses the /v1/export endpoint with limit=1 to get `total_count` without
 * downloading all facts. Falls back to 400 (which gives pool=1200) if
 * the server is unreachable or returns no count.
 */
async function getFactCount(s: DerivedState): Promise<number> {
  const now = Date.now();

  // Return cached value if fresh.
  if (cachedFactCount !== null && (now - lastFactCountFetch) < FACT_COUNT_CACHE_TTL) {
    return cachedFactCount;
  }

  try {
    const page = await api.exportFacts(s.authKeyHex, 1);
    const count = page.total_count ?? page.facts.length;

    cachedFactCount = count;
    lastFactCountFetch = now;
    log(`Fact count updated: ${count} (candidate pool: ${computeCandidatePool(count)})`);
    return count;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    log(`Failed to fetch fact count (using ${cachedFactCount ?? 400}): ${msg}`);
    return cachedFactCount ?? 400; // Fall back to cached or default
  }
}

// =========================================================================
// LSH + Embedding Helpers
// =========================================================================

let lshHasherInstance: LSHHasher | null = null;
let lshInitFailed = false;

/**
 * Get or lazily initialize the LSH hasher.
 * Returns null if the provider doesn't support embeddings.
 */
function getLSHHasher(): LSHHasher | null {
  if (lshHasherInstance) return lshHasherInstance;
  if (lshInitFailed) return null;

  try {
    if (!MASTER_PASSWORD || !state) {
      log('LSH hasher: credentials not available yet');
      return null;
    }

    const dims = getEmbeddingDims();
    const lshSeed = deriveLshSeed(MASTER_PASSWORD, state.salt);
    lshHasherInstance = new LSHHasher(lshSeed, dims);
    log(`LSH hasher initialized (dims=${dims}, tables=${lshHasherInstance.tables}, bits=${lshHasherInstance.bits})`);
    return lshHasherInstance;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    log(`LSH hasher initialization failed (will use word-only indices): ${msg}`);
    lshInitFailed = true;
    return null;
  }
}

/**
 * Generate an embedding for the given text, compute LSH bucket hashes,
 * and encrypt the embedding.
 *
 * Returns null if embedding generation fails — caller should fall back to
 * word-only blind indices.
 */
async function generateEmbeddingAndLSH(
  text: string,
  encryptionKey: Buffer,
): Promise<{ embedding: number[]; lshBuckets: string[]; encryptedEmbedding: string } | null> {
  try {
    const embedding = await generateEmbedding(text);

    const hasher = getLSHHasher();
    const lshBuckets = hasher ? hasher.hash(embedding) : [];

    // Encrypt the embedding (JSON array) — encrypt returns base64, server expects hex
    const encB64 = encrypt(JSON.stringify(embedding), encryptionKey);
    const encryptedEmbedding = Buffer.from(encB64, 'base64').toString('hex');

    return { embedding, lshBuckets, encryptedEmbedding };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    log(`Embedding/LSH generation failed (falling back to word-only indices): ${msg}`);
    return null;
  }
}

// =========================================================================
// Reranker (copied from skill/plugin/reranker.ts — BM25 + cosine + RRF)
// =========================================================================

const STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'do', 'for',
  'from', 'had', 'has', 'have', 'he', 'her', 'him', 'his', 'how', 'if',
  'in', 'into', 'is', 'it', 'its', 'me', 'my', 'no', 'not', 'of', 'on',
  'or', 'our', 'out', 'she', 'so', 'than', 'that', 'the', 'their', 'them',
  'then', 'there', 'these', 'they', 'this', 'to', 'up', 'us', 'was', 'we',
  'were', 'what', 'when', 'where', 'which', 'who', 'whom', 'why', 'will',
  'with', 'you', 'your',
]);

function tokenize(text: string, removeStopWords: boolean = true): string[] {
  let tokens = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 2);

  if (removeStopWords) {
    tokens = tokens.filter((t) => !STOP_WORDS.has(t));
  }

  // Stem each token for morphological normalization.
  // This ensures BM25 matches "gaming" with "games" (both stem to "game").
  return tokens.map((t) => stemmer(t));
}

function bm25Score(
  queryTerms: string[],
  docTerms: string[],
  avgDocLen: number,
  docCount: number,
  termDocFreqs: Map<string, number>,
  k1: number = 1.2,
  b: number = 0.75,
): number {
  if (docTerms.length === 0 || avgDocLen === 0 || docCount === 0) return 0;

  const docTf = new Map<string, number>();
  for (const term of docTerms) {
    docTf.set(term, (docTf.get(term) ?? 0) + 1);
  }

  const docLen = docTerms.length;
  let score = 0;

  for (const qi of queryTerms) {
    const freq = docTf.get(qi) ?? 0;
    if (freq === 0) continue;

    const nqi = termDocFreqs.get(qi) ?? 0;
    const idf = Math.log((docCount - nqi + 0.5) / (nqi + 0.5) + 1);
    const tfNorm = (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * docLen / avgDocLen));
    score += idf * tfNorm;
  }

  return score;
}

function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length === 0 || b.length === 0) return 0;

  const len = Math.min(a.length, b.length);
  let dot = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < len; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  if (denom === 0) return 0;
  return dot / denom;
}

interface RankedItem {
  id: string;
  score: number;
}

function rrfFuse(rankings: RankedItem[][], k: number = 60): RankedItem[] {
  const fusedScores = new Map<string, number>();

  for (const ranking of rankings) {
    for (let rank = 0; rank < ranking.length; rank++) {
      const item = ranking[rank];
      const contribution = 1 / (k + rank + 1);
      fusedScores.set(item.id, (fusedScores.get(item.id) ?? 0) + contribution);
    }
  }

  const fused: RankedItem[] = [];
  for (const [id, score] of fusedScores) {
    fused.push({ id, score });
  }

  fused.sort((a, b) => b.score - a.score);
  return fused;
}

interface RerankerCandidate {
  id: string;
  text: string;
  embedding?: number[];
}

/**
 * Re-rank decrypted candidates using BM25 + Cosine + RRF fusion.
 * Candidates without embeddings get BM25-only ranking.
 */
function rerankCandidates(
  query: string,
  queryEmbedding: number[],
  candidates: RerankerCandidate[],
  topK: number = 8,
): RerankerCandidate[] {
  if (candidates.length === 0) return [];

  const queryTerms = tokenize(query);
  const candidateTerms = candidates.map((c) => tokenize(c.text));

  const docCount = candidates.length;
  let totalDocLen = 0;

  const termDocFreqs = new Map<string, number>();
  for (const terms of candidateTerms) {
    totalDocLen += terms.length;
    const uniqueTerms = new Set(terms);
    for (const term of uniqueTerms) {
      termDocFreqs.set(term, (termDocFreqs.get(term) ?? 0) + 1);
    }
  }

  const avgDocLen = docCount > 0 ? totalDocLen / docCount : 0;

  // BM25 scores
  const bm25Ranking: RankedItem[] = [];
  for (let i = 0; i < candidates.length; i++) {
    const score = bm25Score(queryTerms, candidateTerms[i], avgDocLen, docCount, termDocFreqs);
    bm25Ranking.push({ id: candidates[i].id, score });
  }
  bm25Ranking.sort((a, b) => b.score - a.score);

  // Cosine similarity scores
  const cosineRanking: RankedItem[] = [];
  for (const candidate of candidates) {
    if (candidate.embedding && candidate.embedding.length > 0) {
      const score = cosineSimilarity(queryEmbedding, candidate.embedding);
      cosineRanking.push({ id: candidate.id, score });
    }
  }
  cosineRanking.sort((a, b) => b.score - a.score);

  // RRF fusion
  const rankings: RankedItem[][] = [bm25Ranking];
  if (cosineRanking.length > 0) {
    rankings.push(cosineRanking);
  }

  const fused = rrfFuse(rankings);

  const candidateMap = new Map<string, RerankerCandidate>();
  for (const c of candidates) {
    candidateMap.set(c.id, c);
  }

  const result: RerankerCandidate[] = [];
  for (const item of fused) {
    if (result.length >= topK) break;
    const candidate = candidateMap.get(item.id);
    if (candidate) {
      result.push(candidate);
    }
  }

  return result;
}

// =========================================================================
// Tool Descriptions
// =========================================================================

const REMEMBER_DESCRIPTION = `Store a fact in your encrypted memory vault.

WHEN TO USE:
- User explicitly asks you to remember something ("remember that...")
- User shares a preference ("I prefer...", "I like...", "I hate...")
- User provides personal info (name, location, schedule)
- User corrects previous information about themselves
- You observe an important fact, decision, or goal worth persisting

WHEN NOT TO USE:
- Temporary context (current conversation only)
- Sensitive credentials (use secure storage instead)

IMPORTANCE GUIDE:
- 9-10: Critical identity (name, core values, major preferences)
- 7-8: Important preferences (dietary, work style, communication)
- 5-6: Moderate (minor preferences, schedule details)
- 3-4: Low (casual mentions, may forget)
- 1-2: Minimal (ephemeral context)`;

const RECALL_DESCRIPTION = `Search your encrypted memories for relevant information.

WHEN TO USE:
- At conversation start to load relevant context
- When user asks about their preferences or past conversations
- When you need to recall specific information the user shared

WHEN NOT TO USE:
- For general knowledge queries (use your training)
- For current conversation context (use message history)

PARAMETERS:
- query: Natural language search query (required)
- k: Number of results to return (default: 8, max: 50)`;

const FORGET_DESCRIPTION = `Delete a specific memory from your vault.

WHEN TO USE:
- User explicitly asks to forget something
- User says information is outdated or incorrect
- User requests to remove sensitive information

WHEN NOT TO USE:
- To update information (use remember with updated fact instead)
- Without user's explicit request

PARAMETERS:
- fact_id: The ID of the fact to forget (from recall results)`;

const EXPORT_DESCRIPTION = `Export all memories decrypted in plaintext for portability.

WHEN TO USE:
- User wants to backup their memories
- User wants to see all stored information
- User wants to transfer memories to another system

OUTPUT FORMATS:
- markdown: Human-readable format (default)
- json: Machine-readable format`;

// =========================================================================
// Tool Definitions
// =========================================================================

const rememberToolDef = {
  name: 'totalreclaw_remember',
  description: REMEMBER_DESCRIPTION,
  inputSchema: {
    type: 'object' as const,
    properties: {
      fact: {
        type: 'string',
        description: 'The fact to remember (atomic, concise)',
      },
      importance: {
        type: 'number',
        minimum: 1,
        maximum: 10,
        default: 5,
        description: 'Importance score 1-10',
      },
    },
    required: ['fact'],
  },
};

const recallToolDef = {
  name: 'totalreclaw_recall',
  description: RECALL_DESCRIPTION,
  inputSchema: {
    type: 'object' as const,
    properties: {
      query: {
        type: 'string',
        description: 'The search query',
      },
      k: {
        type: 'number',
        default: 8,
        description: 'Number of results to return (max: 50)',
      },
    },
    required: ['query'],
  },
};

const forgetToolDef = {
  name: 'totalreclaw_forget',
  description: FORGET_DESCRIPTION,
  inputSchema: {
    type: 'object' as const,
    properties: {
      fact_id: {
        type: 'string',
        description: 'The ID of the fact to forget',
      },
    },
    required: ['fact_id'],
  },
};

const exportToolDef = {
  name: 'totalreclaw_export',
  description: EXPORT_DESCRIPTION,
  inputSchema: {
    type: 'object' as const,
    properties: {
      format: {
        type: 'string',
        enum: ['markdown', 'json'],
        default: 'markdown',
        description: 'Output format',
      },
    },
  },
};

// =========================================================================
// Tool Handlers
// =========================================================================

interface ToolResult {
  content: Array<{ type: string; text: string }>;
  isError?: boolean;
  [key: string]: unknown;
}

function textResult(data: unknown): ToolResult {
  return {
    content: [{ type: 'text', text: JSON.stringify(data) }],
  };
}

function errorResult(msg: string): ToolResult {
  return {
    content: [{ type: 'text', text: JSON.stringify({ error: msg }) }],
    isError: true,
  };
}

async function handleRemember(args: Record<string, unknown>): Promise<ToolResult> {
  const fact = args.fact as string | undefined;
  if (!fact || typeof fact !== 'string' || fact.trim().length === 0) {
    return errorResult('Invalid input: fact is required and must be a non-empty string');
  }

  const importance = (args.importance as number | undefined) ?? 5;
  if (typeof importance !== 'number' || importance < 1 || importance > 10) {
    return errorResult('Invalid input: importance must be a number between 1 and 10');
  }

  const s = await ensureInitialized();
  const factText = fact.trim();

  // Encrypt the fact text (encrypt returns base64, server expects hex)
  const encryptedB64 = encrypt(factText, s.encryptionKey);
  const encryptedBlob = Buffer.from(encryptedB64, 'base64').toString('hex');

  // Generate blind indices for search
  // Include namespace in the indexed text so namespace-scoped searches work
  const searchableText = `${factText} namespace:${NAMESPACE}`;
  const blindIndices = generateBlindIndices(searchableText);

  // Generate embedding + LSH bucket hashes (PoC v2).
  // Falls back to word-only indices if embedding generation fails.
  const embeddingResult = await generateEmbeddingAndLSH(factText, s.encryptionKey);

  // Merge LSH bucket hashes into blind indices
  const allIndices = embeddingResult
    ? [...blindIndices, ...embeddingResult.lshBuckets]
    : blindIndices;

  // Generate content fingerprint for dedup
  const contentFp = generateContentFingerprint(factText, s.dedupKey);

  // Build the store payload
  const factId = crypto.randomUUID();
  const payload: StoreFactPayload = {
    id: factId,
    timestamp: new Date().toISOString(),
    encrypted_blob: encryptedBlob,
    blind_indices: allIndices,
    decay_score: importance,
    source: `nanoclaw:${NAMESPACE}`,
    content_fp: contentFp,
    agent_id: `nanoclaw:${NAMESPACE}`,
    encrypted_embedding: embeddingResult?.encryptedEmbedding,
  };

  const result = await api.store(s.userId, [payload], s.authKeyHex);
  const wasDuplicate = result.duplicate_ids?.includes(factId) ?? false;

  return textResult({
    success: true,
    fact_id: factId,
    was_duplicate: wasDuplicate,
    action: wasDuplicate ? 'skipped' : 'created',
  });
}

async function handleRecall(args: Record<string, unknown>): Promise<ToolResult> {
  const query = args.query as string | undefined;
  if (!query || typeof query !== 'string' || query.trim().length === 0) {
    return textResult({ memories: [], latency_ms: 0, error: 'Invalid input: query is required' });
  }

  let k = (args.k as number | undefined) ?? 8;
  if (k < 1) k = 8;
  if (k > 50) k = 50;

  const startTime = Date.now();
  const s = await ensureInitialized();

  // 1. Generate word trapdoors (blind indices) for the query.
  const wordTrapdoors = generateBlindIndices(query.trim());

  // 2. Generate query embedding + LSH trapdoors (may fail gracefully).
  let queryEmbedding: number[] | null = null;
  let lshTrapdoors: string[] = [];
  try {
    queryEmbedding = await generateEmbedding(query.trim(), { isQuery: true });
    const hasher = getLSHHasher();
    if (hasher && queryEmbedding) {
      lshTrapdoors = hasher.hash(queryEmbedding);
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    log(`Recall: embedding/LSH generation failed (using word-only trapdoors): ${msg}`);
  }

  // 3. Merge word trapdoors + LSH trapdoors.
  const allTrapdoors = [...wordTrapdoors, ...lshTrapdoors];
  if (allTrapdoors.length === 0) {
    return textResult({ memories: [], latency_ms: Date.now() - startTime });
  }

  // 4. Search server for encrypted candidates (dynamic pool sizing).
  const factCount = await getFactCount(s);
  const pool = computeCandidatePool(factCount);
  const candidates = await api.search(s.userId, allTrapdoors, pool, s.authKeyHex);

  // 5. Decrypt candidates (text + embeddings) and build reranker input.
  const rerankerInput: RerankerCandidate[] = [];
  const recallMetaMap = new Map<string, { importance: number; decay_score: number }>();

  for (const candidate of candidates) {
    try {
      // Server returns hex, decrypt expects base64
      const b64 = Buffer.from(candidate.encrypted_blob, 'hex').toString('base64');
      const plaintext = decrypt(b64, s.encryptionKey);

      // Decrypt embedding if present (PoC v2 facts).
      let decryptedEmbedding: number[] | undefined;
      if (candidate.encrypted_embedding) {
        try {
          const embB64 = Buffer.from(candidate.encrypted_embedding, 'hex').toString('base64');
          decryptedEmbedding = JSON.parse(decrypt(embB64, s.encryptionKey));
        } catch {
          // Embedding decryption failed -- proceed without it.
        }
      }

      rerankerInput.push({
        id: candidate.fact_id,
        text: plaintext,
        embedding: decryptedEmbedding,
      });

      recallMetaMap.set(candidate.fact_id, {
        importance: candidate.decay_score,
        decay_score: candidate.decay_score,
      });
    } catch (err) {
      // Skip facts that fail to decrypt (wrong key, corrupted)
      log(`Failed to decrypt fact ${candidate.fact_id}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // 6. Re-rank with BM25 + cosine + RRF fusion.
  const reranked = rerankCandidates(
    query.trim(),
    queryEmbedding ?? [],
    rerankerInput,
    k,
  );

  // 7. Format results for the agent.
  const topK = reranked.map((m) => {
    const meta = recallMetaMap.get(m.id);
    return {
      fact_id: m.id,
      fact_text: m.text,
      importance: meta?.importance ?? 5,
      decay_score: meta?.decay_score ?? 5,
    };
  });

  return textResult({
    memories: topK,
    latency_ms: Date.now() - startTime,
  });
}

async function handleForget(args: Record<string, unknown>): Promise<ToolResult> {
  const factId = args.fact_id as string | undefined;
  if (!factId || typeof factId !== 'string') {
    return errorResult('Invalid input: fact_id is required');
  }

  const s = await ensureInitialized();
  await api.deleteFact(factId, s.authKeyHex);

  return textResult({
    success: true,
    deleted_count: 1,
    fact_ids: [factId],
  });
}

async function handleExport(args: Record<string, unknown>): Promise<ToolResult> {
  const format = (args.format as string | undefined) || 'markdown';
  const s = await ensureInitialized();

  // Paginate through all facts
  const allFacts: ExportedFact[] = [];
  let cursor: string | undefined;
  let hasMore = true;

  while (hasMore) {
    const page = await api.exportFacts(s.authKeyHex, 1000, cursor);
    allFacts.push(...page.facts);
    cursor = page.cursor;
    hasMore = page.has_more;
  }

  // Decrypt all facts
  const decrypted: Array<{
    id: string;
    text: string;
    importance: number;
    source: string;
    created_at: string;
  }> = [];

  for (const fact of allFacts) {
    try {
      // Server returns hex, decrypt expects base64
      const b64 = Buffer.from(fact.encrypted_blob, 'hex').toString('base64');
      const plaintext = decrypt(b64, s.encryptionKey);
      decrypted.push({
        id: fact.id,
        text: plaintext,
        importance: fact.decay_score,
        source: fact.source,
        created_at: fact.created_at,
      });
    } catch {
      // Skip undecryptable facts
    }
  }

  const exportedAt = new Date().toISOString();

  let content: string;
  if (format === 'json') {
    content = JSON.stringify({
      version: '1.0.0',
      exported_at: exportedAt,
      namespace: NAMESPACE,
      facts: decrypted,
    }, null, 2);
  } else {
    const lines: string[] = [
      '# TotalReclaw Export',
      '',
      `**Exported:** ${exportedAt}`,
      `**Namespace:** ${NAMESPACE}`,
      `**Total Facts:** ${decrypted.length}`,
      '',
      '---',
      '',
    ];

    for (const fact of decrypted) {
      lines.push(`## ${fact.text}`);
      lines.push('');
      lines.push(`- **Importance:** ${fact.importance}/10`);
      lines.push(`- **Created:** ${fact.created_at}`);
      lines.push(`- **Source:** ${fact.source}`);
      lines.push('');
      lines.push(`ID: \`${fact.id}\``);
      lines.push('');
      lines.push('---');
      lines.push('');
    }

    content = lines.join('\n');
  }

  return textResult({
    content,
    format,
    fact_count: decrypted.length,
    exported_at: exportedAt,
  });
}

// =========================================================================
// MCP Server Setup
// =========================================================================

const server = new Server(
  { name: 'totalreclaw', version: '1.0.0' },
  {
    capabilities: {
      tools: {},
    },
  },
);

server.setRequestHandler(ListToolsRequestSchema, async (_request, _extra) => ({
  tools: [
    rememberToolDef,
    recallToolDef,
    forgetToolDef,
    exportToolDef,
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request, _extra) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'totalreclaw_remember':
        return await handleRemember((args ?? {}) as Record<string, unknown>);

      case 'totalreclaw_recall':
        return await handleRecall((args ?? {}) as Record<string, unknown>);

      case 'totalreclaw_forget':
        return await handleForget((args ?? {}) as Record<string, unknown>);

      case 'totalreclaw_export':
        return await handleExport((args ?? {}) as Record<string, unknown>);

      default:
        return errorResult(`Unknown tool: ${name}`);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    log(`Tool ${name} error: ${message}`);
    return errorResult(message);
  }
});

// =========================================================================
// Main
// =========================================================================

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log(`TotalReclaw MCP server started (namespace: ${NAMESPACE}, server: ${SERVER_URL})`);
}

main().catch((error) => {
  log(`Fatal: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
