/**
 * OpenMemory MCP Server for NanoClaw
 *
 * Self-contained stdio MCP server that provides zero-knowledge encrypted
 * memory tools. Crypto and API client logic copied from the OpenClaw plugin
 * (skill/plugin/crypto.ts, skill/plugin/api-client.ts) to remain fully
 * self-contained with only two external deps:
 *   - @modelcontextprotocol/sdk (already in agent-runner)
 *   - @noble/hashes (added via Dockerfile.nanoclaw-openmemory)
 *
 * Environment variables:
 *   OPENMEMORY_SERVER_URL       — defaults to http://openmemory-server:8080
 *   OPENMEMORY_MASTER_PASSWORD  — REQUIRED
 *   OPENMEMORY_NAMESPACE        — defaults to group folder name
 *   OPENMEMORY_CREDENTIALS_PATH — defaults to /workspace/.openmemory/credentials.json
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
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const SERVER_URL = process.env.OPENMEMORY_SERVER_URL || 'http://openmemory-server:8080';
const MASTER_PASSWORD = process.env.OPENMEMORY_MASTER_PASSWORD || '';
const NAMESPACE = process.env.OPENMEMORY_NAMESPACE || 'default';
const CREDENTIALS_PATH = process.env.OPENMEMORY_CREDENTIALS_PATH || '/workspace/.openmemory/credentials.json';

function log(msg: string): void {
  console.error(`[openmemory-mcp] ${msg}`);
}

// =========================================================================
// Crypto (copied from skill/plugin/crypto.ts — must match byte-for-byte)
// =========================================================================

const AUTH_KEY_INFO = 'openmemory-auth-key-v1';
const ENCRYPTION_KEY_INFO = 'openmemory-encryption-key-v1';
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
    const hash = Buffer.from(sha256(Buffer.from(token, 'utf8'))).toString('hex');
    if (!seen.has(hash)) {
      seen.add(hash);
      indices.push(hash);
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
    throw new Error('OPENMEMORY_MASTER_PASSWORD is not set');
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
  name: 'openmemory_remember',
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
  name: 'openmemory_recall',
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
  name: 'openmemory_forget',
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
  name: 'openmemory_export',
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

  // Generate content fingerprint for dedup
  const contentFp = generateContentFingerprint(factText, s.dedupKey);

  // Build the store payload
  const factId = crypto.randomUUID();
  const payload: StoreFactPayload = {
    id: factId,
    timestamp: new Date().toISOString(),
    encrypted_blob: encryptedBlob,
    blind_indices: blindIndices,
    decay_score: importance,
    source: `nanoclaw:${NAMESPACE}`,
    content_fp: contentFp,
    agent_id: `nanoclaw:${NAMESPACE}`,
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

  // Generate trapdoors (blind indices) for the query
  const trapdoors = generateBlindIndices(query.trim());
  if (trapdoors.length === 0) {
    return textResult({ memories: [], latency_ms: Date.now() - startTime });
  }

  // Search server for encrypted candidates
  // Request more candidates than k so we can re-rank client-side
  const maxCandidates = Math.min(k * 10, 200);
  const candidates = await api.search(s.userId, trapdoors, maxCandidates, s.authKeyHex);

  // Decrypt candidates and score them client-side
  const decryptedResults: Array<{
    fact_id: string;
    fact_text: string;
    score: number;
    importance: number;
    decay_score: number;
  }> = [];

  for (const candidate of candidates) {
    try {
      // Server returns hex, decrypt expects base64
      const b64 = Buffer.from(candidate.encrypted_blob, 'hex').toString('base64');
      const plaintext = decrypt(b64, s.encryptionKey);

      // Simple BM25-like scoring: count query term matches in plaintext
      const queryTokens = query.trim().toLowerCase().split(/\s+/).filter(t => t.length >= 2);
      const factTokens = new Set(plaintext.toLowerCase().split(/\s+/));
      let matchCount = 0;
      for (const qt of queryTokens) {
        if (factTokens.has(qt)) matchCount++;
      }
      const relevance = queryTokens.length > 0 ? matchCount / queryTokens.length : 0;

      decryptedResults.push({
        fact_id: candidate.fact_id,
        fact_text: plaintext,
        score: relevance,
        importance: candidate.decay_score,
        decay_score: candidate.decay_score,
      });
    } catch (err) {
      // Skip facts that fail to decrypt (wrong key, corrupted)
      log(`Failed to decrypt fact ${candidate.fact_id}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  // Sort by score descending, then by importance descending
  decryptedResults.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return b.importance - a.importance;
  });

  const topK = decryptedResults.slice(0, k);

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
      '# OpenMemory Export',
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
  { name: 'openmemory', version: '1.0.0' },
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
      case 'openmemory_remember':
        return await handleRemember((args ?? {}) as Record<string, unknown>);

      case 'openmemory_recall':
        return await handleRecall((args ?? {}) as Record<string, unknown>);

      case 'openmemory_forget':
        return await handleForget((args ?? {}) as Record<string, unknown>);

      case 'openmemory_export':
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
  log(`OpenMemory MCP server started (namespace: ${NAMESPACE}, server: ${SERVER_URL})`);
}

main().catch((error) => {
  log(`Fatal: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
