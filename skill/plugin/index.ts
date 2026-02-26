/**
 * OpenMemory Plugin for OpenClaw
 *
 * Registers runtime tools so OpenClaw can execute OpenMemory operations:
 *   - openmemory_remember  -- store an encrypted memory
 *   - openmemory_recall    -- search and decrypt memories
 *   - openmemory_forget    -- soft-delete a memory
 *   - openmemory_export    -- export all memories (JSON or Markdown)
 *
 * Also registers a `before_agent_start` hook that automatically injects
 * relevant memories into the agent's context.
 *
 * All data is encrypted client-side with AES-256-GCM. The server never
 * sees plaintext.
 */

import {
  deriveKeys,
  computeAuthKeyHash,
  encrypt,
  decrypt,
  generateBlindIndices,
  generateContentFingerprint,
} from './crypto.js';
import { createApiClient, type StoreFactPayload } from './api-client.js';
import { extractFacts, type ExtractedFact } from './extractor.js';
import { initLLMClient } from './llm-client.js';
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
const CREDENTIALS_PATH = '/home/node/.openmemory/credentials.json';

// ---------------------------------------------------------------------------
// Module-level state (persists across tool calls within a session)
// ---------------------------------------------------------------------------

let authKeyHex: string | null = null;
let encryptionKey: Buffer | null = null;
let dedupKey: Buffer | null = null;
let userId: string | null = null;
let apiClient: ReturnType<typeof createApiClient> | null = null;
let initPromise: Promise<void> | null = null;

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

/**
 * Derive keys from the master password, load or create credentials, and
 * register with the server if this is the first run.
 */
async function initialize(logger: OpenClawPluginApi['logger']): Promise<void> {
  const serverUrl =
    process.env.OPENMEMORY_SERVER_URL || 'http://openmemory-server:8080';
  const masterPassword = process.env.OPENMEMORY_MASTER_PASSWORD;

  if (!masterPassword) {
    logger.error('OPENMEMORY_MASTER_PASSWORD environment variable not set');
    throw new Error('OPENMEMORY_MASTER_PASSWORD not set');
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
 * Store extracted facts in the OpenMemory server.
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
      const contentFp = generateContentFingerprint(fact.text, dedupKey);
      const factId = crypto.randomUUID();

      const payload: StoreFactPayload = {
        id: factId,
        timestamp: new Date().toISOString(),
        encrypted_blob: encryptedBlob,
        blind_indices: blindIndices,
        decay_score: fact.importance,
        source: 'auto-extraction',
        content_fp: contentFp,
        agent_id: 'openclaw-plugin-auto',
      };

      await apiClient.store(userId, [payload], authKeyHex);
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
  id: 'openmemory',
  name: 'OpenMemory',
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
      id: 'openmemory',
      start: () => {
        api.logger.info('OpenMemory plugin loaded');
      },
      stop: () => {
        api.logger.info('OpenMemory plugin stopped');
      },
    });

    // ---------------------------------------------------------------
    // Tool: openmemory_remember
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'openmemory_remember',
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

            // Generate content fingerprint for dedup.
            const contentFp = generateContentFingerprint(params.text, dedupKey!);

            // Generate a unique fact ID.
            const factId = crypto.randomUUID();

            // Build the payload matching the server's FactJSON schema.
            const factPayload: StoreFactPayload = {
              id: factId,
              timestamp: new Date().toISOString(),
              encrypted_blob: encryptedBlob,
              blind_indices: blindIndices,
              decay_score: importance,
              source: 'explicit',
              content_fp: contentFp,
              agent_id: 'openclaw-plugin',
            };

            await apiClient!.store(userId!, [factPayload], authKeyHex!);

            return {
              content: [{ type: 'text', text: `Memory stored (ID: ${factId})` }],
              details: { factId },
            };
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            api.logger.error(`openmemory_remember failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to store memory: ${message}` }],
            };
          }
        },
      },
      { name: 'openmemory_remember' },
    );

    // ---------------------------------------------------------------
    // Tool: openmemory_recall
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'openmemory_recall',
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

            // Generate trapdoors (blind indices for the query).
            const trapdoors = generateBlindIndices(params.query);

            if (trapdoors.length === 0) {
              return {
                content: [{ type: 'text', text: 'No searchable terms in query.' }],
                details: { count: 0, memories: [] },
              };
            }

            // Request more candidates than needed so we can re-rank client-side.
            const candidates = await apiClient!.search(
              userId!,
              trapdoors,
              k * 50,
              authKeyHex!,
            );

            // Decrypt, score, and rank.
            interface ScoredMemory {
              factId: string;
              text: string;
              metadata: Record<string, unknown>;
              score: number;
              timestamp: number;
            }

            const scored: ScoredMemory[] = [];

            for (const candidate of candidates) {
              try {
                const docJson = decryptFromHex(candidate.encrypted_blob, encryptionKey!);
                const doc = JSON.parse(docJson) as { text: string; metadata?: Record<string, unknown> };
                const score = textScore(params.query, doc.text);
                scored.push({
                  factId: candidate.fact_id,
                  text: doc.text,
                  metadata: doc.metadata ?? {},
                  score,
                  timestamp: candidate.timestamp,
                });
              } catch {
                // Skip candidates we cannot decrypt (e.g. corrupted data).
              }
            }

            // Sort by score descending, take top k.
            scored.sort((a, b) => b.score - a.score);
            const topK = scored.slice(0, k);

            if (topK.length === 0) {
              return {
                content: [{ type: 'text', text: 'No memories found matching your query.' }],
                details: { count: 0, memories: [] },
              };
            }

            // Format results.
            const lines = topK.map((m, i) => {
              const imp = m.metadata.importance
                ? ` (importance: ${Math.round((m.metadata.importance as number) * 10)}/10)`
                : '';
              const age = relativeTime(m.timestamp);
              return `${i + 1}. ${m.text}${imp} -- ${age} [ID: ${m.factId}]`;
            });

            const formatted = lines.join('\n');

            return {
              content: [{ type: 'text', text: formatted }],
              details: {
                count: topK.length,
                memories: topK.map((m) => ({
                  factId: m.factId,
                  text: m.text,
                  score: m.score,
                })),
              },
            };
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            api.logger.error(`openmemory_recall failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to search memories: ${message}` }],
            };
          }
        },
      },
      { name: 'openmemory_recall' },
    );

    // ---------------------------------------------------------------
    // Tool: openmemory_forget
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'openmemory_forget',
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
            api.logger.error(`openmemory_forget failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to delete memory: ${message}` }],
            };
          }
        },
      },
      { name: 'openmemory_forget' },
    );

    // ---------------------------------------------------------------
    // Tool: openmemory_export
    // ---------------------------------------------------------------

    api.registerTool(
      {
        name: 'openmemory_export',
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
            api.logger.error(`openmemory_export failed: ${message}`);
            return {
              content: [{ type: 'text', text: `Failed to export memories: ${message}` }],
            };
          }
        },
      },
      { name: 'openmemory_export' },
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

          // Generate trapdoors from the user prompt.
          const trapdoors = generateBlindIndices(evt.prompt);
          if (trapdoors.length === 0) return undefined;

          // Fetch candidates from the server.
          const candidates = await apiClient!.search(
            userId!,
            trapdoors,
            400,
            authKeyHex!,
          );

          if (candidates.length === 0) return undefined;

          // Decrypt and score.
          interface ScoredMemory {
            text: string;
            importance: number;
            age: string;
            score: number;
          }

          const scored: ScoredMemory[] = [];

          for (const candidate of candidates) {
            try {
              const docJson = decryptFromHex(candidate.encrypted_blob, encryptionKey!);
              const doc = JSON.parse(docJson) as { text: string; metadata?: Record<string, unknown> };
              const score = textScore(evt.prompt, doc.text);
              const importance = doc.metadata?.importance
                ? Math.round((doc.metadata.importance as number) * 10)
                : 5;
              scored.push({
                text: doc.text,
                importance,
                age: relativeTime(candidate.timestamp),
                score,
              });
            } catch {
              // Skip un-decryptable candidates.
            }
          }

          // Take top 8.
          scored.sort((a, b) => b.score - a.score);
          const topK = scored.slice(0, 8);

          if (topK.length === 0) return undefined;

          // Build context string.
          const lines = topK.map(
            (m, i) =>
              `${i + 1}. ${m.text} (importance: ${m.importance}/10, ${m.age})`,
          );
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

          const facts = await extractFacts(evt.messages, 'turn');
          if (facts.length > 0) {
            await storeExtractedFacts(facts, api.logger);
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
