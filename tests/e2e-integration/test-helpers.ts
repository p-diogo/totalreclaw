/**
 * E2E Integration Test Helpers for TotalReclaw.
 *
 * Provides:
 * - IntegrationTestRunner: TAP-style test runner with non-throwing assertions
 * - Crypto helpers: key generation, AES-256-GCM encrypt/decrypt, blind indices
 * - HTTP helpers: typed wrappers for every server endpoint
 * - DB helpers: direct PostgreSQL access for verification
 * - Mock service helpers: control mock bundler/subgraph
 */

import * as crypto from 'crypto';
import pg from 'pg';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const SERVER_URL = 'http://127.0.0.1:38080';
export const MOCK_SERVICES_URL = 'http://127.0.0.1:39090';
export const DB_CONNECTION: pg.PoolConfig = {
  host: '127.0.0.1',
  port: 35432,
  database: 'totalreclaw',
  user: 'totalreclaw',
  password: 'test-password',
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TestResult {
  journey: string;
  assertion: string;
  passed: boolean;
  error?: string;
}

export interface TestKeys {
  /** 32 random bytes — the raw auth key. */
  authKey: Buffer;
  /** Hex-encoded authKey — this is the Bearer token value. */
  authKeyHex: string;
  /** hex(SHA-256(authKey)) — this is what gets registered as auth_key_hash. */
  authKeyHash: string;
  /** 32 random bytes for AES-256-GCM encryption. */
  encryptionKey: Buffer;
  /** 32 random bytes for HMAC-SHA256 content fingerprinting. */
  dedupKey: Buffer;
  /** hex(32 random bytes) — sent during registration. */
  salt: string;
}

export interface FactInput {
  id: string;
  timestamp: string;
  encrypted_blob: string;
  blind_indices: string[];
  decay_score?: number;
  is_active?: boolean;
  version?: number;
  source: string;
  content_fp?: string;
  agent_id?: string;
  encrypted_embedding?: string;
}

// ---------------------------------------------------------------------------
// IntegrationTestRunner
// ---------------------------------------------------------------------------

export class IntegrationTestRunner {
  private results: TestResult[] = [];
  private currentJourney: string = '';
  private assertionCount: number = 0;
  private pool: pg.Pool | null = null;

  // ---- Journey lifecycle ----

  startJourney(name: string): void {
    this.currentJourney = name;
    console.log(`# Journey: ${name}`);
  }

  // ---- Assertions (non-throwing — record pass/fail and continue) ----

  assert(condition: boolean, message: string): void {
    this.assertionCount++;
    const passed = !!condition;
    this.results.push({
      journey: this.currentJourney,
      assertion: message,
      passed,
      error: passed ? undefined : 'Condition was false',
    });
    if (passed) {
      console.log(`ok ${this.assertionCount} - ${this.currentJourney}: ${message}`);
    } else {
      console.log(`not ok ${this.assertionCount} - ${this.currentJourney}: ${message}`);
    }
  }

  assertEqual<T>(actual: T, expected: T, message: string): void {
    this.assertionCount++;
    const passed = actual === expected;
    this.results.push({
      journey: this.currentJourney,
      assertion: message,
      passed,
      error: passed ? undefined : `Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    });
    if (passed) {
      console.log(`ok ${this.assertionCount} - ${this.currentJourney}: ${message}`);
    } else {
      console.log(
        `not ok ${this.assertionCount} - ${this.currentJourney}: ${message}` +
        `\n  ---\n  expected: ${JSON.stringify(expected)}\n  actual: ${JSON.stringify(actual)}\n  ...`
      );
    }
  }

  assertIncludes(str: string, substr: string, message: string): void {
    this.assertionCount++;
    const passed = typeof str === 'string' && str.includes(substr);
    this.results.push({
      journey: this.currentJourney,
      assertion: message,
      passed,
      error: passed ? undefined : `"${str}" does not include "${substr}"`,
    });
    if (passed) {
      console.log(`ok ${this.assertionCount} - ${this.currentJourney}: ${message}`);
    } else {
      console.log(
        `not ok ${this.assertionCount} - ${this.currentJourney}: ${message}` +
        `\n  ---\n  string: ${JSON.stringify(str)}\n  expected substring: ${JSON.stringify(substr)}\n  ...`
      );
    }
  }

  assertStatusCode(response: Response, expected: number, message: string): void {
    this.assertEqual(response.status, expected, message);
  }

  assertStatusCodeOneOf(response: Response, expected: number[], message: string): void {
    this.assertionCount++;
    const passed = expected.includes(response.status);
    this.results.push({
      journey: this.currentJourney,
      assertion: message,
      passed,
      error: passed ? undefined : `Status ${response.status} not in [${expected.join(', ')}]`,
    });
    if (passed) {
      console.log(`ok ${this.assertionCount} - ${this.currentJourney}: ${message}`);
    } else {
      console.log(
        `not ok ${this.assertionCount} - ${this.currentJourney}: ${message}` +
        `\n  ---\n  actual: ${response.status}\n  expected one of: [${expected.join(', ')}]\n  ...`
      );
    }
  }

  assertGreaterThan(actual: number, threshold: number, message: string): void {
    this.assertionCount++;
    const passed = actual > threshold;
    this.results.push({
      journey: this.currentJourney,
      assertion: message,
      passed,
      error: passed ? undefined : `${actual} is not > ${threshold}`,
    });
    if (passed) {
      console.log(`ok ${this.assertionCount} - ${this.currentJourney}: ${message}`);
    } else {
      console.log(
        `not ok ${this.assertionCount} - ${this.currentJourney}: ${message}` +
        `\n  ---\n  actual: ${actual}\n  threshold: ${threshold}\n  ...`
      );
    }
  }

  assertTruthy(value: unknown, message: string): void {
    this.assert(!!value, message);
  }

  // ---- HTTP helpers — match actual server API exactly ----

  /**
   * POST /v1/register
   * Body: { auth_key_hash: hex, salt: hex }
   * No auth required.
   */
  async register(authKeyHash: string, salt: string): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auth_key_hash: authKeyHash, salt }),
    });
  }

  /**
   * POST /v1/store
   * Body: { user_id, facts: FactInput[] }
   * Auth: Bearer <authKeyHex>
   */
  async store(authKeyHex: string, userId: string, facts: FactInput[]): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/store`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authKeyHex}`,
      },
      body: JSON.stringify({ user_id: userId, facts }),
    });
  }

  /**
   * POST /v1/search
   * Body: { user_id, trapdoors, max_candidates?, min_decay_score? }
   * Auth: Bearer <authKeyHex>
   */
  async search(
    authKeyHex: string,
    userId: string,
    trapdoors: string[],
    maxCandidates: number = 3000,
  ): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authKeyHex}`,
      },
      body: JSON.stringify({
        user_id: userId,
        trapdoors,
        max_candidates: maxCandidates,
      }),
    });
  }

  /**
   * GET /v1/export?limit=&cursor=
   * Auth: Bearer <authKeyHex>
   */
  async exportFacts(authKeyHex: string, limit?: number, cursor?: string): Promise<Response> {
    const params = new URLSearchParams();
    if (limit !== undefined) params.set('limit', String(limit));
    if (cursor) params.set('cursor', cursor);
    const qs = params.toString();
    return fetch(`${SERVER_URL}/v1/export${qs ? '?' + qs : ''}`, {
      headers: { 'Authorization': `Bearer ${authKeyHex}` },
    });
  }

  /**
   * DELETE /v1/facts/:factId
   * Auth: Bearer <authKeyHex>
   */
  async deleteFact(authKeyHex: string, factId: string): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/facts/${factId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authKeyHex}` },
    });
  }

  /**
   * DELETE /v1/account
   * Auth: Bearer <authKeyHex>
   */
  async deleteAccount(authKeyHex: string): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/account`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authKeyHex}` },
    });
  }

  /**
   * GET /v1/billing/status?wallet_address=
   * Auth: Bearer <authKeyHex>
   */
  async billingStatus(authKeyHex: string, walletAddress: string): Promise<Response> {
    return fetch(
      `${SERVER_URL}/v1/billing/status?wallet_address=${encodeURIComponent(walletAddress)}`,
      { headers: { 'Authorization': `Bearer ${authKeyHex}` } },
    );
  }

  /**
   * POST /v1/billing/checkout
   * Body: { wallet_address, tier }
   * Auth: Bearer <authKeyHex>
   */
  async billingCheckout(authKeyHex: string, walletAddress: string, tier: string = 'pro'): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/billing/checkout`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authKeyHex}`,
      },
      body: JSON.stringify({ wallet_address: walletAddress, tier }),
    });
  }

  /**
   * POST /v1/billing/checkout/crypto
   * Body: { wallet_address, tier }
   * Auth: Bearer <authKeyHex>
   */
  async billingCheckoutCrypto(authKeyHex: string, walletAddress: string, tier: string = 'pro'): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/billing/checkout/crypto`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authKeyHex}`,
      },
      body: JSON.stringify({ wallet_address: walletAddress, tier }),
    });
  }

  // ---- Relay proxy helpers ----

  /**
   * POST /v1/bundler
   * Proxies JSON-RPC to Pimlico bundler.
   * Auth: Bearer <authKeyHex>
   * Optional: X-Wallet-Address header for quota tracking.
   */
  async bundlerRpc(
    authKeyHex: string,
    method: string,
    params: unknown[],
    walletAddress?: string,
  ): Promise<Response> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authKeyHex}`,
    };
    if (walletAddress) {
      headers['X-Wallet-Address'] = walletAddress;
    }
    return fetch(`${SERVER_URL}/v1/bundler`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method,
        params,
      }),
    });
  }

  /**
   * POST /v1/subgraph
   * Proxies GraphQL to Graph Studio subgraph.
   * Auth: Bearer <authKeyHex>
   * Optional: X-Wallet-Address header for quota tracking.
   */
  async subgraphQuery(
    authKeyHex: string,
    query: string,
    variables?: Record<string, unknown>,
    walletAddress?: string,
  ): Promise<Response> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authKeyHex}`,
    };
    if (walletAddress) {
      headers['X-Wallet-Address'] = walletAddress;
    }
    return fetch(`${SERVER_URL}/v1/subgraph`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, variables: variables ?? {} }),
    });
  }

  // ---- Webhook helpers ----

  /**
   * POST /v1/billing/webhook/stripe
   * Signature: stripe-signature header (t=<ts>,v1=<hmac>)
   */
  async sendStripeWebhook(payload: string, signature: string): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/billing/webhook/stripe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'stripe-signature': signature,
      },
      body: payload,
    });
  }

  /**
   * POST /v1/billing/webhook/coinbase
   * Signature: x-cc-webhook-signature header (HMAC-SHA256 hex)
   */
  async sendCoinbaseWebhook(payload: string, signature: string): Promise<Response> {
    return fetch(`${SERVER_URL}/v1/billing/webhook/coinbase`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-cc-webhook-signature': signature,
      },
      body: payload,
    });
  }

  // ---- Sync helper ----

  /**
   * GET /v1/sync?since_sequence=&limit=
   * Auth: Bearer <authKeyHex>
   */
  async sync(authKeyHex: string, sinceSequence: number = 0, limit: number = 1000): Promise<Response> {
    return fetch(
      `${SERVER_URL}/v1/sync?since_sequence=${sinceSequence}&limit=${limit}`,
      { headers: { 'Authorization': `Bearer ${authKeyHex}` } },
    );
  }

  // ---- Health helper ----

  async health(): Promise<Response> {
    return fetch(`${SERVER_URL}/health`);
  }

  // ---- Mock services control ----

  async resetMocks(): Promise<void> {
    await fetch(`${MOCK_SERVICES_URL}/control/reset`, { method: 'POST' });
  }

  async getMockRequests(): Promise<unknown[]> {
    const resp = await fetch(`${MOCK_SERVICES_URL}/control/requests`);
    return resp.json() as Promise<unknown[]>;
  }

  async configureMock(config: Record<string, unknown>): Promise<void> {
    await fetch(`${MOCK_SERVICES_URL}/control/configure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
  }

  // ---- DB direct access ----

  private getPool(): pg.Pool {
    if (!this.pool) {
      this.pool = new pg.Pool(DB_CONNECTION);
    }
    return this.pool;
  }

  async dbQuery(sql: string, params?: unknown[]): Promise<pg.QueryResult> {
    return this.getPool().query(sql, params);
  }

  async closeDb(): Promise<void> {
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
    }
  }

  // ---- Results ----

  getSummary(): { total: number; passed: number; failed: number; results: TestResult[] } {
    const total = this.results.length;
    const passed = this.results.filter((r) => r.passed).length;
    const failed = total - passed;
    return { total, passed, failed, results: this.results };
  }

  printSummary(): void {
    const { total, passed, failed } = this.getSummary();
    console.log(`\n1..${total}`);
    console.log(`# tests ${total}`);
    console.log(`# pass  ${passed}`);
    if (failed > 0) {
      console.log(`# fail  ${failed}`);
      console.log('# --- FAILED ASSERTIONS ---');
      for (const r of this.results.filter((r) => !r.passed)) {
        console.log(`#   [${r.journey}] ${r.assertion}: ${r.error}`);
      }
    } else {
      console.log('# All tests passed!');
    }
  }
}

// ===========================================================================
// Crypto Helpers
// ===========================================================================

/**
 * Generate a complete set of test keys for one user.
 *
 * - authKey: 32 random bytes (the raw auth key)
 * - authKeyHex: hex(authKey) — the Bearer token (64 hex chars)
 * - authKeyHash: hex(SHA-256(authKey)) — registered in the server
 * - encryptionKey: 32 random bytes for AES-256-GCM
 * - dedupKey: 32 random bytes for content fingerprinting
 * - salt: hex(32 random bytes)
 */
export function generateTestKeys(): TestKeys {
  const authKey = crypto.randomBytes(32);
  const authKeyHex = authKey.toString('hex');
  const authKeyHash = crypto.createHash('sha256').update(authKey).digest().toString('hex');
  const encryptionKey = crypto.randomBytes(32);
  const dedupKey = crypto.randomBytes(32);
  const salt = crypto.randomBytes(32).toString('hex');

  return { authKey, authKeyHex, authKeyHash, encryptionKey, dedupKey, salt };
}

/**
 * AES-256-GCM encryption.
 *
 * Returns hex-encoded: nonce(12 bytes) || ciphertext || tag(16 bytes).
 * This matches the format the server expects in encrypted_blob.
 */
export function encryptFact(plaintext: string, key: Buffer): string {
  const nonce = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, nonce);
  const encrypted = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag(); // 16 bytes
  return Buffer.concat([nonce, encrypted, tag]).toString('hex');
}

/**
 * AES-256-GCM decryption.
 *
 * Input: hex-encoded nonce(12) || ciphertext || tag(16).
 */
export function decryptFact(encryptedHex: string, key: Buffer): string {
  const data = Buffer.from(encryptedHex, 'hex');
  const nonce = data.subarray(0, 12);
  const tag = data.subarray(data.length - 16);
  const ciphertext = data.subarray(12, data.length - 16);
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, nonce);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
}

/**
 * Compute blind indices for a plaintext string.
 *
 * Extracts words, normalizes (lowercase), and computes
 * SHA-256(dedupKey || word) for each word.
 */
export function computeBlindIndices(text: string, dedupKey: Buffer): string[] {
  const words = text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')
    .split(/\s+/)
    .filter((w) => w.length > 0);

  const uniqueWords = [...new Set(words)];
  return uniqueWords.map((word) => {
    return crypto
      .createHash('sha256')
      .update(Buffer.concat([dedupKey, Buffer.from(word, 'utf8')]))
      .digest('hex');
  });
}

/**
 * Compute a content fingerprint for dedup.
 *
 * HMAC-SHA256(dedupKey, normalized_text) -> hex.
 */
export function computeContentFingerprint(text: string, dedupKey: Buffer): string {
  const normalized = text.toLowerCase().trim().replace(/\s+/g, ' ');
  return crypto.createHmac('sha256', dedupKey).update(normalized).digest('hex');
}

/**
 * Generate a UUID v4 string (for fact IDs).
 */
export function uuid(): string {
  return crypto.randomUUID();
}

/**
 * Build a complete FactInput for the store endpoint.
 */
export function buildFact(
  plaintext: string,
  encryptionKey: Buffer,
  dedupKey: Buffer,
  opts?: {
    source?: string;
    decayScore?: number;
    agentId?: string;
    withFingerprint?: boolean;
  },
): FactInput {
  const fact: FactInput = {
    id: uuid(),
    timestamp: new Date().toISOString(),
    encrypted_blob: encryptFact(plaintext, encryptionKey),
    blind_indices: computeBlindIndices(plaintext, dedupKey),
    decay_score: opts?.decayScore ?? 1.0,
    is_active: true,
    version: 1,
    source: opts?.source ?? 'conversation',
    agent_id: opts?.agentId,
  };
  if (opts?.withFingerprint !== false) {
    fact.content_fp = computeContentFingerprint(plaintext, dedupKey);
  }
  return fact;
}
