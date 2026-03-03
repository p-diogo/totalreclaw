/**
 * In-Memory Mock TotalReclaw Server
 *
 * Provides a lightweight HTTP server that implements the TotalReclaw API
 * endpoints needed for E2E functional testing. Facts are stored in memory
 * and can be reset between scenarios.
 *
 * Endpoints:
 *   POST /v1/register  — Register a user (always succeeds)
 *   POST /v1/store     — Store encrypted facts with blind indices
 *   POST /v1/search    — Search facts by blind trapdoor intersection
 *   GET  /v1/export    — Export all facts for a user
 *   DELETE /v1/facts/:id — Soft-delete a fact
 *   GET  /health       — Health check
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// In-memory storage
// ---------------------------------------------------------------------------

interface StoredFact {
  id: string;
  encrypted_blob: string;
  blind_indices: string[];
  decay_score: number;
  timestamp: string;
  source: string;
  content_fp?: string;
  agent_id?: string;
  encrypted_embedding?: string;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** userId -> Map<factId, StoredFact> */
const userFacts = new Map<string, Map<string, StoredFact>>();
/** authKeyHash -> userId */
const users = new Map<string, string>();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getOrCreateUser(authKeyHash: string): string {
  let uid = users.get(authKeyHash);
  if (!uid) {
    uid = `mock-user-${crypto.randomUUID()}`;
    users.set(authKeyHash, uid);
    userFacts.set(uid, new Map());
  }
  return uid;
}

function getUserIdFromAuth(authHeader: string | undefined): string | null {
  if (!authHeader?.startsWith('Bearer ')) return null;
  const authKey = authHeader.slice(7);
  // Hash the auth key with SHA-256, same as the real server
  const hash = crypto.createHash('sha256').update(Buffer.from(authKey, 'hex')).digest('hex');
  return users.get(hash) ?? null;
}

function getUserFacts(userId: string): Map<string, StoredFact> {
  if (!userFacts.has(userId)) {
    userFacts.set(userId, new Map());
  }
  return userFacts.get(userId)!;
}

async function readBody(req: http.IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString('utf8');
}

function jsonResponse(
  res: http.ServerResponse,
  status: number,
  body: unknown,
): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

// ---------------------------------------------------------------------------
// Route handlers
// ---------------------------------------------------------------------------

async function handleRegister(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { auth_key_hash } = body as { auth_key_hash: string; salt: string };
  const userId = getOrCreateUser(auth_key_hash);
  jsonResponse(res, 200, { success: true, user_id: userId });
}

async function handleStore(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const userId = getUserIdFromAuth(req.headers.authorization);
  if (!userId) {
    jsonResponse(res, 401, { success: false, error_code: 'UNAUTHORIZED' });
    return;
  }

  const body = JSON.parse(await readBody(req));
  const { facts } = body as { user_id: string; facts: Array<{
    id: string;
    encrypted_blob: string;
    blind_indices: string[];
    decay_score: number;
    timestamp: string;
    source: string;
    content_fp?: string;
    agent_id?: string;
    encrypted_embedding?: string;
  }> };

  const store = getUserFacts(userId);
  const ids: string[] = [];
  const duplicate_ids: string[] = [];

  for (const fact of facts) {
    // Dedup by content_fp
    if (fact.content_fp) {
      const existing = Array.from(store.values()).find(
        (f) => f.content_fp === fact.content_fp && f.is_active,
      );
      if (existing) {
        duplicate_ids.push(fact.id);
        continue;
      }
    }

    const now = new Date().toISOString();
    store.set(fact.id, {
      id: fact.id,
      encrypted_blob: fact.encrypted_blob,
      blind_indices: fact.blind_indices,
      decay_score: fact.decay_score,
      timestamp: fact.timestamp,
      source: fact.source,
      content_fp: fact.content_fp,
      agent_id: fact.agent_id,
      encrypted_embedding: fact.encrypted_embedding,
      version: 1,
      is_active: true,
      created_at: now,
      updated_at: now,
    });
    ids.push(fact.id);
  }

  jsonResponse(res, 200, { success: true, ids, duplicate_ids });
}

async function handleSearch(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const userId = getUserIdFromAuth(req.headers.authorization);
  if (!userId) {
    jsonResponse(res, 401, { success: false, error_code: 'UNAUTHORIZED' });
    return;
  }

  const body = JSON.parse(await readBody(req));
  const { trapdoors, max_candidates } = body as {
    user_id: string;
    trapdoors: string[];
    max_candidates: number;
  };

  const store = getUserFacts(userId);
  const trapdoorSet = new Set(trapdoors);

  // Find all active facts that have at least one matching blind index
  const matches: Array<{
    fact: StoredFact;
    matchCount: number;
  }> = [];

  for (const fact of store.values()) {
    if (!fact.is_active) continue;
    const matchCount = fact.blind_indices.filter((idx) =>
      trapdoorSet.has(idx),
    ).length;
    if (matchCount > 0) {
      matches.push({ fact, matchCount });
    }
  }

  // Sort by match count (descending), then by timestamp (descending)
  matches.sort((a, b) => {
    if (b.matchCount !== a.matchCount) return b.matchCount - a.matchCount;
    return b.fact.timestamp.localeCompare(a.fact.timestamp);
  });

  // Limit to max_candidates
  const limited = matches.slice(0, max_candidates);

  const results = limited.map(({ fact }) => ({
    fact_id: fact.id,
    encrypted_blob: fact.encrypted_blob,
    decay_score: fact.decay_score,
    timestamp: new Date(fact.timestamp).getTime(),
    version: fact.version,
    encrypted_embedding: fact.encrypted_embedding,
  }));

  jsonResponse(res, 200, { success: true, results });
}

async function handleExport(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const userId = getUserIdFromAuth(req.headers.authorization);
  if (!userId) {
    jsonResponse(res, 401, { success: false, error_code: 'UNAUTHORIZED' });
    return;
  }

  const url = new URL(req.url ?? '/', `http://${req.headers.host}`);
  const limit = parseInt(url.searchParams.get('limit') ?? '1000', 10);

  const store = getUserFacts(userId);
  const activeFacts = Array.from(store.values()).filter((f) => f.is_active);

  const facts = activeFacts.slice(0, limit).map((f) => ({
    id: f.id,
    encrypted_blob: f.encrypted_blob,
    blind_indices: f.blind_indices,
    decay_score: f.decay_score,
    version: f.version,
    source: f.source,
    created_at: f.created_at,
    updated_at: f.updated_at,
  }));

  jsonResponse(res, 200, {
    success: true,
    facts,
    has_more: activeFacts.length > limit,
    total_count: activeFacts.length,
  });
}

async function handleDelete(
  req: http.IncomingMessage,
  res: http.ServerResponse,
  factId: string,
): Promise<void> {
  const userId = getUserIdFromAuth(req.headers.authorization);
  if (!userId) {
    jsonResponse(res, 401, { success: false, error_code: 'UNAUTHORIZED' });
    return;
  }

  const store = getUserFacts(userId);
  const fact = store.get(factId);
  if (fact) {
    fact.is_active = false;
    fact.updated_at = new Date().toISOString();
  }

  jsonResponse(res, 200, { success: true });
}

// ---------------------------------------------------------------------------
// Anthropic API mock for Scenario H (llm-orchestrator.ts)
// ---------------------------------------------------------------------------

import { getNextAlexChenMessage } from './interceptors/llm-interceptor.js';

async function handleAnthropicMessages(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  // Read and discard body (we don't need it — we use pre-scripted messages)
  await readBody(req);

  const { index, text } = getNextAlexChenMessage();

  jsonResponse(res, 200, {
    id: `msg_mock_${String(index + 1).padStart(3, '0')}`,
    type: 'message',
    role: 'assistant',
    content: [{ type: 'text', text }],
    model: 'claude-3-5-haiku-20241022',
    stop_reason: 'end_turn',
    stop_sequence: null,
    usage: { input_tokens: 100, output_tokens: 50 },
  });
}

// ---------------------------------------------------------------------------
// Server lifecycle
// ---------------------------------------------------------------------------

export interface MockServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
  reset: () => void;
}

export async function startMockServer(port = 0): Promise<MockServer> {
  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      if (method === 'GET' && url === '/health') {
        jsonResponse(res, 200, { status: 'ok' });
        return;
      }

      if (method === 'POST' && url === '/v1/messages') {
        await handleAnthropicMessages(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/register') {
        await handleRegister(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/store') {
        await handleStore(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/search') {
        await handleSearch(req, res);
        return;
      }

      if (method === 'GET' && url.startsWith('/v1/export')) {
        await handleExport(req, res);
        return;
      }

      const deleteMatch = url.match(/^\/v1\/facts\/([^/]+)$/);
      if (method === 'DELETE' && deleteMatch) {
        await handleDelete(req, res, decodeURIComponent(deleteMatch[1]));
        return;
      }

      jsonResponse(res, 404, { error: 'Not found' });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  return new Promise<MockServer>((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      const actualPort = addr.port;
      const url = `http://127.0.0.1:${actualPort}`;

      resolve({
        url,
        port: actualPort,
        stop: () =>
          new Promise<void>((res) => {
            server.close(() => res());
          }),
        reset: () => {
          userFacts.clear();
          users.clear();
        },
      });
    });
  });
}
