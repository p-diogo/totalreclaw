/**
 * TotalReclaw Plugin for OpenClaw
 *
 * Registers runtime tools so OpenClaw can execute TotalReclaw operations:
 *   - totalreclaw_remember  -- store an encrypted memory
 *   - totalreclaw_recall    -- search and decrypt memories
 *   - totalreclaw_forget    -- soft-delete a memory
 *   - totalreclaw_export    -- export all memories (JSON or Markdown)
 *
 * Also registers a `before_agent_start` hook that automatically injects
 * relevant memories into the agent's context.
 *
 * All data is encrypted client-side with AES-256-GCM. The server never
 * sees plaintext.
 */

import {
  deriveKeys,
  deriveLshSeed,
  computeAuthKeyHash,
  encrypt,
  decrypt,
  generateBlindIndices,
  generateContentFingerprint,
} from './crypto.js';
import { createApiClient, type StoreFactPayload } from './api-client.js';
import { extractFacts, type ExtractedFact } from './extractor.js';
import { initLLMClient, generateEmbedding, getEmbeddingDims } from './llm-client.js';
import { LSHHasher } from './lsh.js';
import { rerank, cosineSimilarity, type RerankerCandidate } from './reranker.js';
import { isSubgraphMode, getSubgraphConfig, encodeFactProtobuf, submitToRelay } from './subgraph-store.js';
import { searchSubgraph, getSubgraphFactCount } from './subgraph-search.js';
import { PluginHotCache, type HotFact } from './hot-cache-wrapper.js';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

// ---------------------------------------------------------------------------
// OpenClaw Plugin API type (defined locally to avoid SDK dependency)
// ---------------------------------------------------------------------------

interface OpenClawPluginApi {
  logger: {
    info(...args: unknown[]): void;
    warn(...args: unknown[]): void;
    error(...args: unknown[]): void;
  };
  config?: {
    agents?: {
      defaults?: {
        model?: {
          primary?: string;
        };
      };
    };
    [key: string]: unknown;
  };
  pluginConfig?: Record<string, unknown>;
  registerTool(tool: unknown, opts?: { name?: string; names?: string[] }): void;
  registerService(service: { id: string; start(): void; stop?(): void }): void;
  on(hookName: string, handler: (...args: unknown[]) => unknown, opts?: { priority?: number }): void;
}

// ---------------------------------------------------------------------------
// Persistent credential storage
// ---------------------------------------------------------------------------

/** Path where we persist userId + salt across restarts. */
const CREDENTIALS_PATH = '/home/node/.totalreclaw/credentials.json';

// ---------------------------------------------------------------------------
// Module-level state (persists across tool calls within a session)
// ---------------------------------------------------------------------------

let authKeyHex: string | null = null;
let encryptionKey: Buffer | null = null;
let dedupKey: Buffer | null = null;
let userId: string | null = null;
let apiClient: ReturnType<typeof createApiClient> | null = null;
let initPromise: Promise<void> | null = null;

// LSH hasher — lazily initialized on first use (needs credentials + embedding dims)
let lshHasher: LSHHasher | null = null;
let lshInitFailed = false; // If true, skip LSH on future calls (provider doesn't support embeddings)

// Hot cache for subgraph mode — lazily initialized
let pluginHotCache: PluginHotCache | null = null;

// Two-tier search state (C1): skip redundant searches when query is semantically similar
let lastSearchTimestamp = 0;
let lastQueryEmbedding: number[] | null = null;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const SEMANTIC_SKIP_THRESHOLD = 0.85;

// Auto-extract throttle (C3): only extract every N turns in agent_end hook
let turnsSinceLastExtraction = 0;
const AUTO_EXTRACT_EVERY_TURNS = parseInt(process.env.TOTALRECLAW_EXTRACT_EVERY_TURNS ?? '5', 10);

// B2: Minimum relevance threshold — cosine below this means no memory injection
const RELEVANCE_THRESHOLD = parseFloat(process.env.TOTALRECLAW_RELEVANCE_THRESHOLD ?? '0.3');

// ---------------------------------------------------------------------------
// Dynamic candidate pool sizing
// ---------------------------------------------------------------------------

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
async function getFactCount(logger: OpenClawPluginApi['logger']): Promise<number> {
  const now = Date.now();

  // Return cached value if fresh.
  if (cachedFactCount !== null && (now - lastFactCountFetch) < FACT_COUNT_CACHE_TTL) {
    return cachedFactCount;
  }

  try {
    if (!apiClient || !authKeyHex) {
      return cachedFactCount ?? 400; // Not initialized yet, use default
    }

    const page = await apiClient.exportFacts(authKeyHex, 1);
    const count = page.total_count ?? page.facts.length;

    cachedFactCount = count;
    lastFactCountFetch = now;
    logger.info(`Fact count updated: ${count} (candidate pool: ${computeCandidatePool(count)})`);
    return count;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    logger.warn(`Failed to fetch fact count (using ${cachedFactCount ?? 400}): ${msg}`);
    return cachedFactCount ?? 400; // Fall back to cached or default
  }
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

/**
 * Derive keys from the master password, load or create credentials, and
 * register with the server if this is the first run.
 */
async function initialize(logger: OpenClawPluginApi['logger']): Promise<void> {
  const serverUrl =
    process.env.TOTALRECLAW_SERVER_URL || 'http://totalreclaw-server:8080';
  const masterPassword = process.env.TOTALRECLAW_MASTER_PASSWORD;

  if (!masterPassword) {
    logger.error('TOTALRECLAW_MASTER_PASSWORD environment variable not set');
    throw new Error('TOTALRECLAW_MASTER_PASSWORD not set');
  }

  apiClient = createApiClient(serverUrl);

  // --- Attempt to load existing credentials ---
  let existingSalt: Buffer | undefined;
  let existingUserId: string | undefined;

  try {
    if (fs.existsSync(CREDENTIALS_PATH)) {
      const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, 'utf8'));
      existingSalt = Buffer.from(creds.salt, 'base64');
      existingUserId = creds.userId;
      logger.info(`Loaded existing credentials for user ${existingUserId}`);
    }
  } catch (e) {
    logger.warn('Failed to load credentials, will register new account');
  }

  // --- Derive keys ---
  const keys = deriveKeys(masterPassword, existingSalt);
  authKeyHex = keys.authKey.toString('hex');
  encryptionKey = keys.encryptionKey;
  dedupKey = keys.dedupKey;

  // Cache credentials for lazy LSH seed derivation
  masterPasswordCache = masterPassword;
  saltCache = keys.salt;

  if (existingUserId) {
    userId = existingUserId;
    logger.info(`Authenticated as user ${userId}`);
  } else {
    // First run -- register with the server.
    const authHash = computeAuthKeyHash(keys.authKey);
    const saltHex = keys.salt.toString('hex');
    const result = await apiClient.register(authHash, saltHex);
    userId = result.user_id;

    // Persist credentials so we can resume later.
    const dir = path.dirname(CREDENTIALS_PATH);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(
      CREDENTIALS_PATH,
      JSON.stringify({ userId, salt: keys.salt.toString('base64') }),
    );

    logger.info(`Registered new user: ${userId}`);
  }
}

/**
 * Ensure `initialize()` has completed (runs at most once).
 */
async function ensureInitialized(logger: OpenClawPluginApi['logger']): Promise<void> {
  if (!initPromise) {
    initPromise = initialize(logger);
  }
  await initPromise;
}

// ---------------------------------------------------------------------------
// LSH + Embedding helpers
// ---------------------------------------------------------------------------

/** Master password cached for LSH seed derivation (set during initialize()). */
let masterPasswordCache: string | null = null;
/** Salt cached for LSH seed derivation (set during initialize()). */
let saltCache: Buffer | null = null;

/**
 * Get or initialize the LSH hasher.
 *
 * The hasher is created lazily because it needs:
 *   1. The master password + salt (available after initialize())
 *   2. The embedding dimensions (available after initLLMClient())
 *
 * If the provider doesn't support embeddings, this returns null and
 * sets `lshInitFailed` to avoid retrying.
 */
function getLSHHasher(logger: OpenClawPluginApi['logger']): LSHHasher | null {
  if (lshHasher) return lshHasher;
  if (lshInitFailed) return null;

  try {
    if (!masterPasswordCache || !saltCache) {
      logger.warn('LSH hasher: credentials not available yet');
      return null;
    }

    const dims = getEmbeddingDims();
    const lshSeed = deriveLshSeed(masterPasswordCache, saltCache);
    lshHasher = new LSHHasher(lshSeed, dims);
    logger.info(`LSH hasher initialized (dims=${dims}, tables=${lshHasher.tables}, bits=${lshHasher.bits})`);
    return lshHasher;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    logger.warn(`LSH hasher initialization failed (will use word-only indices): ${msg}`);
    lshInitFailed = true;
    return null;
  }
}

/**
 * Generate an embedding for the given text and compute LSH bucket hashes.
 *
 * Returns null if embedding generation fails (provider doesn't support it,
 * network error, etc.). In that case, the caller should fall back to
 * word-only blind indices.
 */
async function generateEmbeddingAndLSH(
  text: string,
  logger: OpenClawPluginApi['logger'],
): Promise<{ embedding: number[]; lshBuckets: string[]; encryptedEmbedding: string } | null> {
  try {
    const embedding = await generateEmbedding(text);

    const hasher = getLSHHasher(logger);
    const lshBuckets = hasher ? hasher.hash(embedding) : [];

    // Encrypt the embedding (JSON array of numbers) for zero-knowledge storage
    const encryptedEmbedding = encryptToHex(JSON.stringify(embedding), encryptionKey!);

    return { embedding, lshBuckets, encryptedEmbedding };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    logger.warn(`Embedding/LSH generation failed (falling back to word-only indices): ${msg}`);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

/**
 * Encrypt a plaintext document string and return its hex-encoded ciphertext.
 *
 * The server stores blobs as hex (not base64), so we convert the base64
 * output of `encrypt()` into hex.
 */
function encryptToHex(plaintext: string, key: Buffer): string {
  const b64 = encrypt(plaintext, key);
  return Buffer.from(b64, 'base64').toString('hex');
}

/**
 * Decrypt a hex-encoded ciphertext blob into a UTF-8 string.
 */
function decryptFromHex(hexBlob: string, key: Buffer): string {
  const b64 = Buffer.from(hexBlob, 'hex').toString('base64');
  return decrypt(b64, key);
}

/**
 * Simple text-overlap scoring between a query and a candidate document.
 * Returns the number of overlapping lowercase words.
 */
function textScore(query: string, docText: string): number {
  const queryWords = new Set(
    query.toLowerCase().split(/\s+/).filter((w) => w.length >= 2),
  );
  const docWords = docText.toLowerCase().split(/\s+/);
  let score = 0;
  for (const word of docWords) {
    if (queryWords.has(word)) score++;
  }
  return score;
}

/**
 * Format a relative time string (e.g. "2 hours ago").
 */
function relativeTime(isoOrMs: string | number): string {
  const ms = typeof isoOrMs === 'number' ? isoOrMs : new Date(isoOrMs).getTime();
  const diffMs = Date.now() - ms;
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ---------------------------------------------------------------------------
// Auto-extraction helper
// ---------------------------------------------------------------------------

/**
 * Store extracted facts in the TotalReclaw server.
 * Encrypts each fact, generates blind indices and fingerprint, stores via API.
 * Silently skips duplicates.
 */
async function storeExtractedFacts(
  facts: ExtractedFact[],
  logger: OpenClawPluginApi['logger'],
): Promise<number> {
  if (!encryptionKey || !dedupKey || !authKeyHex || !userId || !apiClient) return 0;

  let stored = 0;

  for (const fact of facts) {
    try {
      const doc = {
        text: fact.text,
        metadata: {
          type: fact.type,
          importance: fact.importance / 10,
          source: 'auto-extraction',
          created_at: new Date().toISOString(),
        },
      };

      const encryptedBlob = encryptToHex(JSON.stringify(doc), encryptionKey);
      const blindIndices = generateBlindIndices(fact.text);

      // Generate embedding + LSH bucket hashes (PoC v2).
      const embeddingResult = await generateEmbeddingAndLSH(fact.text, logger);
      const allIndices = embeddingResult
        ? [...blindIndices, ...embeddingResult.lshBuckets]
        : blindIndices;

      const contentFp = generateContentFingerprint(fact.text, dedupKey);
      const factId = crypto.randomUUID();

      const payload: StoreFactPayload = {
        id: factId,
        timestamp: new Date().toISOString(),
        encrypted_blob: encryptedBlob,
        blind_indices: allIndices,
        decay_score: fact.importance,
        source: 'auto-extraction',
        content_fp: contentFp,
        agent_id: 'openclaw-plugin-auto',
        encrypted_embedding: embeddingResult?.encryptedEmbedding,
      };

      if (isSubgraphMode()) {
        const config = getSubgraphConfig();
        const protobuf = encodeFactProtobuf({
          id: factId,
          timestamp: new Date().toISOString(),
          owner: userId!,
          encryptedBlob: encryptedBlob,
          blindIndices: allIndices,
          decayScore: fact.importance,
          source: 'auto-extraction',
          contentFp: contentFp,
          agentId: 'openclaw-plugin-auto',
          encryptedEmbedding: embeddingResult?.encryptedEmbedding,
        });
        await submitToRelay(protobuf, config);
      } else {
        await apiClient.store(userId, [payload], authKeyHex);
      }
      stored++;
    } catch {
      // Skip failed facts (e.g., duplicates return success with duplicate_ids)
    }
  }

  if (stored > 0) {
    logger.info(`Auto-extracted and stored ${stored} memories`);
  }

  return stored;
}

// ---------------------------------------------------------------------------
// Plugin definition
// ---------------------------------------------------------------------------

const plugin = {
  id: 'totalreclaw',
  name: 'TotalReclaw',
  description: 'Zero-knowledge encrypted memory vault for AI agents',
  kind: 'memory' as const,
  configSchema: {
    type: 'object',
    additionalProperties: false,
    properties: {
      extraction: {
        type: 'object',
        properties: {
          model: { type: 'string', description: "Override the extraction model (e.g., 'glm-4.5-flash', 'gpt-4.1-mini')" },
          enabled: { type: 'boolean', description: 'Enable/disable auto-extraction (default: true)' },
        },
        additionalProperties: false,
      },
    },
  },

  register(api: OpenClawPluginApi) {
    // ---------------------------------------------------------------
    // LLM client initialization (auto-detect provider from OpenClaw config)
    // ---------------------------------------------------------------

    initLLMClient({
      primaryModel: api.config?.agents?.defaults?.model?.primary as string | undefined,
      pluginConfig: api.pluginConfig,
      logger: api.logger,
    });

    // ---------------------------------------------------------------
    // Service registration (lifecycle logging)
    // ---------------------------------------------------------------

    api.registerService({
      id: 'totalreclaw',
      start: () => {
        api.logger.info('TotalReclaw plugin loaded');
      },
      stop: () => {
        api.logger.info('TotalReclaw plugin stopped');
      },
    });

    // ---------------------------------------------------------------
    // Tool: totalreclaw_remember
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'totalreclaw_remember',
        label: 'Remember',
        description:
          'Store a memory in the encrypted vault. Use this when the user shares important information worth remembering.',
        parameters: {
          type: 'object',
          properties: {
            text: {
              type: 'string',
              description: 'The memory text to store',
            },
            type: {
              type: 'string',
              enum: ['fact', 'preference', 'decision', 'episodic', 'goal'],
              description: 'The kind of memory (default: fact)',
            },
            importance: {
              type: 'number',
              minimum: 1,
              maximum: 10,
              description: 'Importance score 1-10 (default: 5)',
            },
          },
          required: ['text'],
          additionalProperties: false,
        },
        async execute(_toolCallId: string, params: { text: string; type?: string; importance?: number }) {
          try {
            await ensureInitialized(api.logger);

            const memoryType = params.type ?? 'fact';
            const importance = params.importance ?? 5;

            // Build the document JSON that will be encrypted.
            const doc = {
              text: params.text,
              metadata: {
                type: memoryType,
                importance: importance / 10, // normalise to 0-1 range
                source: 'explicit',
                created_at: new Date().toISOString(),
              },
            };

            // Encrypt the document.
            const encryptedBlob = encryptToHex(JSON.stringify(doc), encryptionKey!);

            // Generate blind indices for server-side search.
            const blindIndices = generateBlindIndices(params.text);

            // Generate embedding + LSH bucket hashes (PoC v2).
            // Falls back to word-only indices if embedding generation fails.
            const embeddingResult = await generateEmbeddingAndLSH(params.text, api.logger);

            // Merge LSH bucket hashes into blind indices.
            const allIndices = embeddingResult
              ? [...blindIndices, ...embeddingResult.lshBuckets]
              : blindIndices;

            // Generate content fingerprint for dedup.
            const contentFp = generateContentFingerprint(params.text, dedupKey!);

            // Generate a unique fact ID.
            const factId = crypto.randomUUID();

            // Build the payload matching the server's FactJSON schema.
            const factPayload: StoreFactPayload = {
              id: factId,
              timestamp: new Date().toISOString(),
              encrypted_blob: encryptedBlob,
              blind_indices: allIndices,
              decay_score: importance,
              source: 'explicit',
              content_fp: contentFp,
              agent_id: 'openclaw-plugin',
              encrypted_embedding: embeddingResult?.encryptedEmbedding,
            };

            if (isSubgraphMode()) {
              // Subgraph mode: encode as Protobuf and submit via relay
              const config = getSubgraphConfig();
              const protobuf = encodeFactProtobuf({
                id: factId,
                timestamp: new Date().toISOString(),
                owner: userId!,
                encryptedBlob: encryptedBlob,
                blindIndices: allIndices,
                decayScore: importance,
                source: 'explicit',
                contentFp: contentFp,
                agentId: 'openclaw-plugin',
                encryptedEmbedding: embeddingResult?.encryptedEmbedding,
              });
              await submitToRelay(protobuf, config);
            } else {
              await apiClient!.store(userId!, [factPayload], authKeyHex!);
            }

            return {
              content: [{ type: 'text', text: `Memory stored (ID: ${factId})` }],
              details: { factId },
            };
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            api.logger.error(`totalreclaw_remember failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to store memory: ${message}` }],
            };
          }
        },
      },
      { name: 'totalreclaw_remember' },
    );

    // ---------------------------------------------------------------
    // Tool: totalreclaw_recall
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'totalreclaw_recall',
        label: 'Recall',
        description:
          'Search the encrypted memory vault. Returns the most relevant memories matching the query.',
        parameters: {
          type: 'object',
          properties: {
            query: {
              type: 'string',
              description: 'Search query text',
            },
            k: {
              type: 'number',
              minimum: 1,
              maximum: 20,
              description: 'Number of results to return (default: 8)',
            },
          },
          required: ['query'],
          additionalProperties: false,
        },
        async execute(_toolCallId: string, params: { query: string; k?: number }) {
          try {
            await ensureInitialized(api.logger);

            const k = Math.min(params.k ?? 8, 20);

            // 1. Generate word trapdoors (blind indices for the query).
            const wordTrapdoors = generateBlindIndices(params.query);

            // 2. Generate query embedding + LSH trapdoors (may fail gracefully).
            let queryEmbedding: number[] | null = null;
            let lshTrapdoors: string[] = [];
            try {
              queryEmbedding = await generateEmbedding(params.query, { isQuery: true });
              const hasher = getLSHHasher(api.logger);
              if (hasher && queryEmbedding) {
                lshTrapdoors = hasher.hash(queryEmbedding);
              }
            } catch (err) {
              const msg = err instanceof Error ? err.message : String(err);
              api.logger.warn(`Recall: embedding/LSH generation failed (using word-only trapdoors): ${msg}`);
            }

            // 3. Merge word trapdoors + LSH trapdoors.
            const allTrapdoors = [...wordTrapdoors, ...lshTrapdoors];

            if (allTrapdoors.length === 0) {
              return {
                content: [{ type: 'text', text: 'No searchable terms in query.' }],
                details: { count: 0, memories: [] },
              };
            }

            // 4. Request more candidates than needed so we can re-rank client-side.
            // 5. Decrypt candidates (text + embeddings) and build reranker input.
            const rerankerCandidates: RerankerCandidate[] = [];
            const metaMap = new Map<string, { metadata: Record<string, unknown>; timestamp: number }>();

            if (isSubgraphMode()) {
              // --- Subgraph search path ---
              const factCount = await getSubgraphFactCount(userId!);
              const pool = computeCandidatePool(factCount);
              const subgraphResults = await searchSubgraph(userId!, allTrapdoors, pool);

              for (const result of subgraphResults) {
                try {
                  const docJson = decryptFromHex(result.encryptedBlob, encryptionKey!);
                  const doc = JSON.parse(docJson) as { text: string; metadata?: Record<string, unknown> };

                  let decryptedEmbedding: number[] | undefined;
                  if (result.encryptedEmbedding) {
                    try {
                      decryptedEmbedding = JSON.parse(
                        decryptFromHex(result.encryptedEmbedding, encryptionKey!),
                      );
                    } catch {
                      // Embedding decryption failed -- proceed without it.
                    }
                  }

                  rerankerCandidates.push({
                    id: result.id,
                    text: doc.text,
                    embedding: decryptedEmbedding,
                    importance: (doc.metadata?.importance as number) ?? 0.5,
                    createdAt: result.timestamp ? parseInt(result.timestamp, 10) : undefined,
                  });

                  metaMap.set(result.id, {
                    metadata: doc.metadata ?? {},
                    timestamp: Date.now(), // Subgraph doesn't return ms timestamp; use current
                  });
                } catch {
                  // Skip candidates we cannot decrypt.
                }
              }

              // Update hot cache with top results for instant auto-recall.
              try {
                if (!pluginHotCache && encryptionKey) {
                  const config = getSubgraphConfig();
                  pluginHotCache = new PluginHotCache(config.cachePath, encryptionKey.toString('hex'));
                  pluginHotCache.load();
                }
                if (pluginHotCache) {
                  const hotFacts: HotFact[] = rerankerCandidates.map((c) => {
                    const meta = metaMap.get(c.id);
                    const importance = meta?.metadata.importance
                      ? Math.round((meta.metadata.importance as number) * 10)
                      : 5;
                    return { id: c.id, text: c.text, importance };
                  });
                  pluginHotCache.setHotFacts(hotFacts);
                  pluginHotCache.setFactCount(rerankerCandidates.length);
                  pluginHotCache.flush();
                }
              } catch {
                // Hot cache update is best-effort -- don't fail the recall.
              }
            } else {
              // --- Server search path (existing behavior) ---
              const factCount = await getFactCount(api.logger);
              const pool = computeCandidatePool(factCount);
              const candidates = await apiClient!.search(
                userId!,
                allTrapdoors,
                pool,
                authKeyHex!,
              );

              for (const candidate of candidates) {
                try {
                  const docJson = decryptFromHex(candidate.encrypted_blob, encryptionKey!);
                  const doc = JSON.parse(docJson) as { text: string; metadata?: Record<string, unknown> };

                  let decryptedEmbedding: number[] | undefined;
                  if (candidate.encrypted_embedding) {
                    try {
                      decryptedEmbedding = JSON.parse(
                        decryptFromHex(candidate.encrypted_embedding, encryptionKey!),
                      );
                    } catch {
                      // Embedding decryption failed -- proceed without it.
                    }
                  }

                  rerankerCandidates.push({
                    id: candidate.fact_id,
                    text: doc.text,
                    embedding: decryptedEmbedding,
                    importance: (doc.metadata?.importance as number) ?? 0.5,
                    createdAt: typeof candidate.timestamp === 'number'
                      ? candidate.timestamp / 1000
                      : new Date(candidate.timestamp).getTime() / 1000,
                  });

                  metaMap.set(candidate.fact_id, {
                    metadata: doc.metadata ?? {},
                    timestamp: candidate.timestamp,
                  });
                } catch {
                  // Skip candidates we cannot decrypt (e.g. corrupted data).
                }
              }
            }

            // 6. Re-rank with BM25 + cosine + RRF fusion.
            const reranked = rerank(
              params.query,
              queryEmbedding ?? [],
              rerankerCandidates,
              k,
            );

            if (reranked.length === 0) {
              return {
                content: [{ type: 'text', text: 'No memories found matching your query.' }],
                details: { count: 0, memories: [] },
              };
            }

            // 7. Format results.
            const lines = reranked.map((m, i) => {
              const meta = metaMap.get(m.id);
              const imp = meta?.metadata.importance
                ? ` (importance: ${Math.round((meta.metadata.importance as number) * 10)}/10)`
                : '';
              const age = meta ? relativeTime(meta.timestamp) : '';
              return `${i + 1}. ${m.text}${imp} -- ${age} [ID: ${m.id}]`;
            });

            const formatted = lines.join('\n');

            return {
              content: [{ type: 'text', text: formatted }],
              details: {
                count: reranked.length,
                memories: reranked.map((m) => ({
                  factId: m.id,
                  text: m.text,
                })),
              },
            };
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            api.logger.error(`totalreclaw_recall failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to search memories: ${message}` }],
            };
          }
        },
      },
      { name: 'totalreclaw_recall' },
    );

    // ---------------------------------------------------------------
    // Tool: totalreclaw_forget
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'totalreclaw_forget',
        label: 'Forget',
        description: 'Delete a specific memory by its ID.',
        parameters: {
          type: 'object',
          properties: {
            factId: {
              type: 'string',
              description: 'The UUID of the memory to delete',
            },
          },
          required: ['factId'],
          additionalProperties: false,
        },
        async execute(_toolCallId: string, params: { factId: string }) {
          try {
            await ensureInitialized(api.logger);

            await apiClient!.deleteFact(params.factId, authKeyHex!);

            return {
              content: [{ type: 'text', text: `Memory ${params.factId} deleted` }],
              details: { deleted: true },
            };
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            api.logger.error(`totalreclaw_forget failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to delete memory: ${message}` }],
            };
          }
        },
      },
      { name: 'totalreclaw_forget' },
    );

    // ---------------------------------------------------------------
    // Tool: totalreclaw_export
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'totalreclaw_export',
        label: 'Export',
        description:
          'Export all stored memories. Decrypts every memory and returns them as JSON or Markdown.',
        parameters: {
          type: 'object',
          properties: {
            format: {
              type: 'string',
              enum: ['json', 'markdown'],
              description: 'Output format (default: json)',
            },
          },
          additionalProperties: false,
        },
        async execute(_toolCallId: string, params: { format?: string }) {
          try {
            await ensureInitialized(api.logger);

            const format = params.format ?? 'json';

            // Paginate through all facts.
            const allFacts: Array<{
              id: string;
              text: string;
              metadata: Record<string, unknown>;
              created_at: string;
            }> = [];

            let cursor: string | undefined;
            let hasMore = true;

            while (hasMore) {
              const page = await apiClient!.exportFacts(authKeyHex!, 1000, cursor);

              for (const fact of page.facts) {
                try {
                  const docJson = decryptFromHex(fact.encrypted_blob, encryptionKey!);
                  const doc = JSON.parse(docJson) as { text: string; metadata?: Record<string, unknown> };
                  allFacts.push({
                    id: fact.id,
                    text: doc.text,
                    metadata: doc.metadata ?? {},
                    created_at: fact.created_at,
                  });
                } catch {
                  // Skip facts we cannot decrypt.
                }
              }

              cursor = page.cursor ?? undefined;
              hasMore = page.has_more;
            }

            // Format output.
            let formatted: string;

            if (format === 'markdown') {
              if (allFacts.length === 0) {
                formatted = '*No memories stored.*';
              } else {
                const lines = allFacts.map((f, i) => {
                  const meta = f.metadata;
                  const type = (meta.type as string) ?? 'fact';
                  const imp = meta.importance
                    ? ` (importance: ${Math.round((meta.importance as number) * 10)}/10)`
                    : '';
                  return `${i + 1}. **[${type}]** ${f.text}${imp}  \n   _ID: ${f.id} | Created: ${f.created_at}_`;
                });
                formatted = `# Exported Memories (${allFacts.length})\n\n${lines.join('\n')}`;
              }
            } else {
              formatted = JSON.stringify(allFacts, null, 2);
            }

            return {
              content: [{ type: 'text', text: formatted }],
              details: { count: allFacts.length },
            };
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            api.logger.error(`totalreclaw_export failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to export memories: ${message}` }],
            };
          }
        },
      },
      { name: 'totalreclaw_export' },
    );

    // ---------------------------------------------------------------
    // Hook: before_agent_start
    // ---------------------------------------------------------------

    api.on(
      'before_agent_start',
      async (event: unknown) => {
        try {
          const evt = event as { prompt?: string } | undefined;

          // Skip trivial or missing prompts.
          if (!evt?.prompt || evt.prompt.length < 5) {
            return undefined;
          }

          await ensureInitialized(api.logger);

          if (isSubgraphMode()) {
            // --- Subgraph mode: hot cache first, then background refresh ---

            // Initialize hot cache if needed.
            if (!pluginHotCache && encryptionKey) {
              const config = getSubgraphConfig();
              pluginHotCache = new PluginHotCache(config.cachePath, encryptionKey.toString('hex'));
              pluginHotCache.load();
            }

            // Try to return cached facts instantly.
            const cachedFacts = pluginHotCache?.getHotFacts() ?? [];

            // Query subgraph in parallel for fresh results.
            // 1. Generate word trapdoors from the user prompt.
            const wordTrapdoors = generateBlindIndices(evt.prompt);

            // 2. Generate query embedding + LSH trapdoors (may fail gracefully).
            let queryEmbedding: number[] | null = null;
            let lshTrapdoors: string[] = [];
            try {
              queryEmbedding = await generateEmbedding(evt.prompt, { isQuery: true });
              const hasher = getLSHHasher(api.logger);
              if (hasher && queryEmbedding) {
                lshTrapdoors = hasher.hash(queryEmbedding);
              }
            } catch {
              // Embedding/LSH failed -- proceed with word-only trapdoors.
            }

            // Two-tier search (C1): if cache is fresh AND query is semantically similar, return cached
            const now = Date.now();
            const cacheAge = now - lastSearchTimestamp;
            if (cacheAge < CACHE_TTL_MS && cachedFacts.length > 0 && queryEmbedding && lastQueryEmbedding) {
              const querySimilarity = cosineSimilarity(queryEmbedding, lastQueryEmbedding);
              if (querySimilarity > SEMANTIC_SKIP_THRESHOLD) {
                const lines = cachedFacts.slice(0, 8).map((f, i) =>
                  `${i + 1}. ${f.text} (importance: ${f.importance}/10, cached)`,
                );
                return { prependContext: `## Relevant Memories\n\n${lines.join('\n')}` };
              }
            }

            // 3. Merge trapdoors — hook path uses LSH-only for lighter query (C1).
            const hookTrapdoors = lshTrapdoors.length > 0 ? lshTrapdoors : wordTrapdoors;
            const allTrapdoors = hookTrapdoors;

            // If we have cached facts and no trapdoors, return cached facts.
            if (allTrapdoors.length === 0 && cachedFacts.length > 0) {
              const lines = cachedFacts.slice(0, 8).map((f, i) =>
                `${i + 1}. ${f.text} (importance: ${f.importance}/10, cached)`,
              );
              return { prependContext: `## Relevant Memories\n\n${lines.join('\n')}` };
            }

            if (allTrapdoors.length === 0) return undefined;

            // 4. Query subgraph for fresh results.
            let subgraphResults: Awaited<ReturnType<typeof searchSubgraph>> = [];
            try {
              const factCount = await getSubgraphFactCount(userId!);
              const pool = computeCandidatePool(factCount);
              subgraphResults = await searchSubgraph(userId!, allTrapdoors, pool);
            } catch {
              // Subgraph query failed -- fall back to cached facts if available.
              if (cachedFacts.length > 0) {
                const lines = cachedFacts.slice(0, 8).map((f, i) =>
                  `${i + 1}. ${f.text} (importance: ${f.importance}/10, cached)`,
                );
                return { prependContext: `## Relevant Memories\n\n${lines.join('\n')}` };
              }
              return undefined;
            }

            if (subgraphResults.length === 0 && cachedFacts.length === 0) return undefined;

            // If subgraph returned no results but we have cache, use cache.
            if (subgraphResults.length === 0) {
              const lines = cachedFacts.slice(0, 8).map((f, i) =>
                `${i + 1}. ${f.text} (importance: ${f.importance}/10, cached)`,
              );
              return { prependContext: `## Relevant Memories\n\n${lines.join('\n')}` };
            }

            // 5. Decrypt subgraph results and build reranker input.
            const rerankerCandidates: RerankerCandidate[] = [];
            const hookMetaMap = new Map<string, { importance: number; age: string }>();

            for (const result of subgraphResults) {
              try {
                const docJson = decryptFromHex(result.encryptedBlob, encryptionKey!);
                const doc = JSON.parse(docJson) as { text: string; metadata?: Record<string, unknown> };

                let decryptedEmbedding: number[] | undefined;
                if (result.encryptedEmbedding) {
                  try {
                    decryptedEmbedding = JSON.parse(
                      decryptFromHex(result.encryptedEmbedding, encryptionKey!),
                    );
                  } catch {
                    // Embedding decryption failed -- proceed without it.
                  }
                }

                const importanceRaw = (doc.metadata?.importance as number) ?? 0.5;
                const createdAtSec = result.timestamp ? parseInt(result.timestamp, 10) : undefined;
                rerankerCandidates.push({
                  id: result.id,
                  text: doc.text,
                  embedding: decryptedEmbedding,
                  importance: importanceRaw,
                  createdAt: createdAtSec,
                });

                const importance = doc.metadata?.importance
                  ? Math.round((doc.metadata.importance as number) * 10)
                  : 5;
                hookMetaMap.set(result.id, {
                  importance,
                  age: 'subgraph',
                });
              } catch {
                // Skip un-decryptable candidates.
              }
            }

            // 6. Re-rank with BM25 + cosine + RRF fusion.
            const reranked = rerank(
              evt.prompt,
              queryEmbedding ?? [],
              rerankerCandidates,
              8,
            );

            // B2: Minimum relevance threshold — skip noise injection for irrelevant turns.
            const candidatesWithEmb = rerankerCandidates.filter(c => c.embedding && c.embedding.length > 0);
            if (candidatesWithEmb.length > 0 && queryEmbedding && queryEmbedding.length > 0) {
              const topCosine = Math.max(
                ...candidatesWithEmb.map(c => cosineSimilarity(queryEmbedding!, c.embedding!))
              );
              if (topCosine < RELEVANCE_THRESHOLD) return undefined;
            }

            // Update hot cache with reranked results.
            try {
              if (pluginHotCache) {
                const hotFacts: HotFact[] = rerankerCandidates.map((c) => {
                  const meta = hookMetaMap.get(c.id);
                  return { id: c.id, text: c.text, importance: meta?.importance ?? 5 };
                });
                pluginHotCache.setHotFacts(hotFacts);
                pluginHotCache.setLastQueryEmbedding(queryEmbedding);
                pluginHotCache.flush();
              }
            } catch {
              // Hot cache update is best-effort.
            }

            // Record search state for two-tier cache (C1).
            lastSearchTimestamp = Date.now();
            lastQueryEmbedding = queryEmbedding;

            if (reranked.length === 0) return undefined;

            // 7. Build context string.
            const lines = reranked.map((m, i) => {
              const meta = hookMetaMap.get(m.id);
              const importance = meta?.importance ?? 5;
              const age = meta?.age ?? '';
              return `${i + 1}. ${m.text} (importance: ${importance}/10, ${age})`;
            });
            const contextString = `## Relevant Memories\n\n${lines.join('\n')}`;

            return { prependContext: contextString };
          }

          // --- Server mode (existing behavior) ---

          // 1. Generate word trapdoors from the user prompt.
          const wordTrapdoors = generateBlindIndices(evt.prompt);

          // 2. Generate query embedding + LSH trapdoors (may fail gracefully).
          let queryEmbedding: number[] | null = null;
          let lshTrapdoors: string[] = [];
          try {
            queryEmbedding = await generateEmbedding(evt.prompt, { isQuery: true });
            const hasher = getLSHHasher(api.logger);
            if (hasher && queryEmbedding) {
              lshTrapdoors = hasher.hash(queryEmbedding);
            }
          } catch {
            // Embedding/LSH failed -- proceed with word-only trapdoors.
          }

          // 3. Merge word + LSH trapdoors.
          const allTrapdoors = [...wordTrapdoors, ...lshTrapdoors];
          if (allTrapdoors.length === 0) return undefined;

          // 4. Fetch candidates from the server (dynamic pool sizing).
          const factCount = await getFactCount(api.logger);
          const pool = computeCandidatePool(factCount);
          const candidates = await apiClient!.search(
            userId!,
            allTrapdoors,
            pool,
            authKeyHex!,
          );

          if (candidates.length === 0) return undefined;

          // 5. Decrypt candidates (text + embeddings) and build reranker input.
          const rerankerCandidates: RerankerCandidate[] = [];
          const hookMetaMap = new Map<string, { importance: number; age: string }>();

          for (const candidate of candidates) {
            try {
              const docJson = decryptFromHex(candidate.encrypted_blob, encryptionKey!);
              const doc = JSON.parse(docJson) as { text: string; metadata?: Record<string, unknown> };

              // Decrypt embedding if present.
              let decryptedEmbedding: number[] | undefined;
              if (candidate.encrypted_embedding) {
                try {
                  decryptedEmbedding = JSON.parse(
                    decryptFromHex(candidate.encrypted_embedding, encryptionKey!),
                  );
                } catch {
                  // Embedding decryption failed -- proceed without it.
                }
              }

              const importanceRaw = (doc.metadata?.importance as number) ?? 0.5;
              const createdAtSec = typeof candidate.timestamp === 'number'
                ? candidate.timestamp / 1000
                : new Date(candidate.timestamp).getTime() / 1000;
              rerankerCandidates.push({
                id: candidate.fact_id,
                text: doc.text,
                embedding: decryptedEmbedding,
                importance: importanceRaw,
                createdAt: createdAtSec,
              });

              const importance = doc.metadata?.importance
                ? Math.round((doc.metadata.importance as number) * 10)
                : 5;
              hookMetaMap.set(candidate.fact_id, {
                importance,
                age: relativeTime(candidate.timestamp),
              });
            } catch {
              // Skip un-decryptable candidates.
            }
          }

          // 6. Re-rank with BM25 + cosine + RRF fusion.
          const reranked = rerank(
            evt.prompt,
            queryEmbedding ?? [],
            rerankerCandidates,
            8,
          );

          // B2: Minimum relevance threshold — skip noise injection for irrelevant turns.
          const candidatesWithEmbSrv = rerankerCandidates.filter(c => c.embedding && c.embedding.length > 0);
          if (candidatesWithEmbSrv.length > 0 && queryEmbedding && queryEmbedding.length > 0) {
            const topCosine = Math.max(
              ...candidatesWithEmbSrv.map(c => cosineSimilarity(queryEmbedding!, c.embedding!))
            );
            if (topCosine < RELEVANCE_THRESHOLD) return undefined;
          }

          if (reranked.length === 0) return undefined;

          // 7. Build context string.
          const lines = reranked.map((m, i) => {
            const meta = hookMetaMap.get(m.id);
            const importance = meta?.importance ?? 5;
            const age = meta?.age ?? '';
            return `${i + 1}. ${m.text} (importance: ${importance}/10, ${age})`;
          });
          const contextString = `## Relevant Memories\n\n${lines.join('\n')}`;

          return { prependContext: contextString };
        } catch (err: unknown) {
          // The hook must NEVER throw -- log and return undefined.
          const message = err instanceof Error ? err.message : String(err);
          api.logger.warn(`before_agent_start hook failed: ${message}`);
          return undefined;
        }
      },
      { priority: 10 },
    );

    // ---------------------------------------------------------------
    // Hook: agent_end — auto-extract facts after each conversation turn
    // ---------------------------------------------------------------

    api.on(
      'agent_end',
      async (event: unknown) => {
        try {
          const evt = event as { messages?: unknown[]; success?: boolean } | undefined;
          if (!evt?.success || !evt?.messages || evt.messages.length < 2) return;

          await ensureInitialized(api.logger);

          // C3: Throttle auto-extraction to every N turns (configurable via env).
          turnsSinceLastExtraction++;
          if (turnsSinceLastExtraction >= AUTO_EXTRACT_EVERY_TURNS) {
            const facts = await extractFacts(evt.messages, 'turn');
            if (facts.length > 0) {
              await storeExtractedFacts(facts, api.logger);
            }
            turnsSinceLastExtraction = 0;
          }
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          api.logger.warn(`agent_end extraction failed: ${message}`);
        }
      },
      { priority: 90 },
    );

    // ---------------------------------------------------------------
    // Hook: before_compaction — extract ALL facts before context is lost
    // ---------------------------------------------------------------

    api.on(
      'before_compaction',
      async (event: unknown) => {
        try {
          const evt = event as { messages?: unknown[]; messageCount?: number } | undefined;
          if (!evt?.messages || evt.messages.length < 2) return;

          await ensureInitialized(api.logger);

          api.logger.info(
            `Pre-compaction extraction: processing ${evt.messages.length} messages`,
          );

          const facts = await extractFacts(evt.messages, 'full');
          if (facts.length > 0) {
            await storeExtractedFacts(facts, api.logger);
          }
          turnsSinceLastExtraction = 0; // Reset C3 counter on compaction.
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          api.logger.warn(`before_compaction extraction failed: ${message}`);
        }
      },
      { priority: 5 },
    );

    // ---------------------------------------------------------------
    // Hook: before_reset — final extraction before session is cleared
    // ---------------------------------------------------------------

    api.on(
      'before_reset',
      async (event: unknown) => {
        try {
          const evt = event as { messages?: unknown[]; reason?: string } | undefined;
          if (!evt?.messages || evt.messages.length < 2) return;

          await ensureInitialized(api.logger);

          api.logger.info(
            `Pre-reset extraction (${evt.reason ?? 'unknown'}): processing ${evt.messages.length} messages`,
          );

          const facts = await extractFacts(evt.messages, 'full');
          if (facts.length > 0) {
            await storeExtractedFacts(facts, api.logger);
          }
          turnsSinceLastExtraction = 0; // Reset C3 counter on reset.
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          api.logger.warn(`before_reset extraction failed: ${message}`);
        }
      },
      { priority: 5 },
    );
  },
};

export default plugin;
