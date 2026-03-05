#!/usr/bin/env tsx
/**
 * Billing Quota & Upgrade Flow E2E Tests (T621-T624)
 *
 * Tests the relay proxy's quota enforcement for free-tier and pro-tier users,
 * the upgrade flow from free to pro via Stripe/Coinbase, dynamic limit changes,
 * and DB-backed counter persistence.
 *
 * These tests exercise the proxy endpoints:
 *   POST /v1/bundler   — JSON-RPC proxy (write quota for eth_sendUserOperation)
 *   POST /v1/subgraph  — GraphQL proxy (read quota)
 *
 * And the billing endpoints:
 *   GET  /v1/billing/status              — Usage and subscription info
 *   POST /v1/billing/checkout            — Stripe checkout URL
 *   POST /v1/billing/checkout/crypto     — Coinbase checkout URL
 *   POST /v1/billing/webhook/stripe      — Stripe webhook (checkout.session.completed)
 *
 * The mock server simulates DB-backed quota tracking (counters persist across
 * "restarts" because they're stored in the mock's in-memory DB, not in a
 * per-request counter that resets). This mirrors the T600 DB-backed implementation.
 *
 * Run:
 *   cd tests/e2e-functional && npx tsx test-billing-quota.ts
 *
 * Tasks: T621, T622, T623, T624
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MockSubscription {
  wallet_address: string;
  tier: 'free' | 'pro';
  source: 'stripe' | 'coinbase_commerce' | null;
  stripe_id: string | null;
  stripe_customer_id: string | null;
  coinbase_id: string | null;
  expires_at: Date | null;
  free_writes_used: number;
  free_reads_used: number;
  created_at: Date;
  updated_at: Date;
}

interface QuotaConfig {
  free_tier_writes_per_month: number;
  free_tier_reads_per_month: number;
  pro_tier_writes_per_month: number;
  pro_tier_reads_per_month: number;
}

interface QuotaMockServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
  reset: () => void;
  /** Get or create a subscription for a wallet address. */
  getSubscription: (wallet: string) => MockSubscription;
  /** Directly set subscription state. */
  setSubscription: (wallet: string, state: Partial<MockSubscription>) => void;
  /** Change quota limits at runtime (simulates env var change / redeploy). */
  setQuotaConfig: (config: Partial<QuotaConfig>) => void;
  /** Get current quota config. */
  getQuotaConfig: () => QuotaConfig;
}

// ---------------------------------------------------------------------------
// JSON-RPC methods that count as "write" operations (mirrors proxy.py)
// ---------------------------------------------------------------------------

const WRITE_RPC_METHODS = new Set([
  'eth_sendUserOperation',
]);

// ---------------------------------------------------------------------------
// In-memory DB-backed storage (simulates PostgreSQL subscriptions table)
// ---------------------------------------------------------------------------

let subscriptions = new Map<string, MockSubscription>();
let registeredUsers = new Map<string, string>();

let quotaConfig: QuotaConfig = {
  free_tier_writes_per_month: 3,  // Small limit for testing
  free_tier_reads_per_month: 5,   // Small limit for testing
  pro_tier_writes_per_month: 10000,
  pro_tier_reads_per_month: 100000,
};

function makeDefaultSubscription(wallet: string): MockSubscription {
  const now = new Date();
  return {
    wallet_address: wallet.toLowerCase(),
    tier: 'free',
    source: null,
    stripe_id: null,
    stripe_customer_id: null,
    coinbase_id: null,
    expires_at: null,
    free_writes_used: 0,
    free_reads_used: 0,
    created_at: now,
    updated_at: now,
  };
}

function getOrCreateSubscription(wallet: string): MockSubscription {
  const key = wallet.toLowerCase();
  let sub = subscriptions.get(key);
  if (!sub) {
    sub = makeDefaultSubscription(wallet);
    subscriptions.set(key, sub);
  }
  return sub;
}

function isExpired(sub: MockSubscription): boolean {
  if (!sub.expires_at) return false;
  return sub.expires_at.getTime() < Date.now();
}

function getEffectiveTier(sub: MockSubscription): 'free' | 'pro' {
  if (sub.tier === 'pro' && !isExpired(sub)) return 'pro';
  return 'free';
}

function getWriteLimit(tier: 'free' | 'pro'): number {
  return tier === 'pro'
    ? quotaConfig.pro_tier_writes_per_month
    : quotaConfig.free_tier_writes_per_month;
}

function getReadLimit(tier: 'free' | 'pro'): number {
  return tier === 'pro'
    ? quotaConfig.pro_tier_reads_per_month
    : quotaConfig.free_tier_reads_per_month;
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

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
  const { auth_key_hash } = body as { auth_key_hash: string };
  let userId = registeredUsers.get(auth_key_hash);
  if (!userId) {
    userId = `mock-user-${crypto.randomUUID()}`;
    registeredUsers.set(auth_key_hash, userId);
  }
  jsonResponse(res, 200, { success: true, user_id: userId });
}

/**
 * POST /v1/bundler — JSON-RPC proxy to Pimlico (quota enforced)
 *
 * Mirrors the real proxy.py behavior:
 * - Parses the JSON-RPC method from the request body
 * - Write operations (eth_sendUserOperation) check write quota
 * - Non-write operations are allowed freely
 * - Returns 403 quota_exceeded when limit reached
 */
async function handleBundlerProxy(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = await readBody(req);
  const walletHeader = req.headers['x-wallet-address'] as string | undefined;
  const wallet = walletHeader?.toLowerCase() ?? 'unknown';

  // Parse JSON-RPC method
  let isWrite = false;
  try {
    const payload = JSON.parse(body);
    const rpcMethod = payload.method ?? '';
    isWrite = WRITE_RPC_METHODS.has(rpcMethod);
  } catch {
    // Not valid JSON — forward anyway (mirrors real proxy)
  }

  if (isWrite) {
    const sub = getOrCreateSubscription(wallet);
    const tier = getEffectiveTier(sub);
    const limit = getWriteLimit(tier);

    if (sub.free_writes_used >= limit) {
      jsonResponse(res, 403, {
        error: 'quota_exceeded',
        message: `${tier === 'free' ? 'Free' : 'Pro'} tier write limit reached (${sub.free_writes_used}/${limit} this month)`,
        upgrade_url: 'https://totalreclaw.com/pricing',
      });
      return;
    }

    // Increment write counter
    sub.free_writes_used++;
    sub.updated_at = new Date();
  }

  // Simulate successful Pimlico response
  jsonResponse(res, 200, {
    jsonrpc: '2.0',
    id: 1,
    result: isWrite
      ? `0x${crypto.randomBytes(32).toString('hex')}`  // userOpHash
      : '0x1',  // generic response for non-write calls
  });
}

/**
 * POST /v1/subgraph — GraphQL proxy to Graph Studio (quota enforced)
 *
 * Mirrors the real proxy.py behavior:
 * - All subgraph queries consume read quota
 * - Returns 403 quota_exceeded when limit reached
 */
async function handleSubgraphProxy(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  await readBody(req);  // consume body
  const walletHeader = req.headers['x-wallet-address'] as string | undefined;
  const wallet = walletHeader?.toLowerCase() ?? 'unknown';

  const sub = getOrCreateSubscription(wallet);
  const tier = getEffectiveTier(sub);
  const limit = getReadLimit(tier);

  if (sub.free_reads_used >= limit) {
    jsonResponse(res, 403, {
      error: 'quota_exceeded',
      message: `${tier === 'free' ? 'Free' : 'Pro'} tier read limit reached (${sub.free_reads_used}/${limit} this month)`,
      upgrade_url: 'https://totalreclaw.com/pricing',
    });
    return;
  }

  // Increment read counter
  sub.free_reads_used++;
  sub.updated_at = new Date();

  // Simulate successful subgraph response
  jsonResponse(res, 200, {
    data: {
      factEntities: [],
    },
  });
}

/**
 * GET /v1/billing/status — Subscription and usage info
 */
function handleBillingStatus(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): void {
  const url = new URL(req.url ?? '/', `http://${req.headers.host}`);
  const wallet = url.searchParams.get('wallet_address');

  if (!wallet) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_WALLET',
      error_message: 'wallet_address query parameter is required.',
    });
    return;
  }

  const key = wallet.toLowerCase();
  const sub = subscriptions.get(key);

  if (!sub) {
    jsonResponse(res, 200, {
      success: true,
      wallet_address: key,
      tier: 'free',
      source: null,
      expires_at: null,
      free_writes_used: 0,
      free_writes_limit: quotaConfig.free_tier_writes_per_month,
      free_reads_used: 0,
      free_reads_limit: quotaConfig.free_tier_reads_per_month,
    });
    return;
  }

  const effectiveTier = getEffectiveTier(sub);

  jsonResponse(res, 200, {
    success: true,
    wallet_address: sub.wallet_address,
    tier: effectiveTier,
    source: sub.source,
    expires_at: sub.expires_at ? sub.expires_at.toISOString() : null,
    free_writes_used: sub.free_writes_used,
    free_writes_limit: getWriteLimit(effectiveTier),
    free_reads_used: sub.free_reads_used,
    free_reads_limit: getReadLimit(effectiveTier),
  });
}

/**
 * POST /v1/billing/checkout — Create Stripe checkout session (mock)
 */
async function handleBillingCheckout(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { wallet_address, tier } = body as { wallet_address: string; tier?: string };

  if (tier && tier !== 'pro') {
    jsonResponse(res, 200, {
      success: false,
      error_code: 'INVALID_TIER',
      error_message: "Only 'pro' tier is currently available.",
    });
    return;
  }

  if (!wallet_address) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_WALLET',
      error_message: 'wallet_address is required.',
    });
    return;
  }

  const sessionId = `cs_test_${crypto.randomBytes(16).toString('hex')}`;
  jsonResponse(res, 200, {
    success: true,
    checkout_url: `https://checkout.stripe.com/c/pay/${sessionId}`,
  });
}

/**
 * POST /v1/billing/checkout/crypto — Create Coinbase Commerce charge (mock)
 */
async function handleBillingCheckoutCrypto(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { wallet_address, tier } = body as { wallet_address: string; tier?: string };

  if (tier && tier !== 'pro') {
    jsonResponse(res, 200, {
      success: false,
      error_code: 'INVALID_TIER',
      error_message: "Only 'pro' tier is currently available.",
    });
    return;
  }

  if (!wallet_address) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_WALLET',
      error_message: 'wallet_address is required.',
    });
    return;
  }

  const chargeCode = `MOCK${crypto.randomBytes(8).toString('hex').toUpperCase()}`;
  jsonResponse(res, 200, {
    success: true,
    checkout_url: `https://commerce.coinbase.com/charges/${chargeCode}`,
  });
}

/**
 * POST /v1/billing/webhook/stripe — Stripe webhook processor (mock)
 *
 * Handles checkout.session.completed to upgrade a user to pro tier.
 */
async function handleStripeWebhook(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { type, data } = body as {
    type: string;
    data: { object: Record<string, unknown> };
  };

  if (!type || !data?.object) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_PAYLOAD',
      error_message: 'Missing type or data.object.',
    });
    return;
  }

  const obj = data.object;

  if (type === 'checkout.session.completed') {
    const walletAddr = obj.client_reference_id as string;
    if (!walletAddr) {
      jsonResponse(res, 200, {
        success: true,
        event_type: type,
        status: 'ignored_missing_reference',
      });
      return;
    }

    const wallet = walletAddr.toLowerCase();
    const existing = subscriptions.get(wallet);

    // Upgrade to pro, preserving existing usage counters
    const sub = getOrCreateSubscription(wallet);
    sub.tier = 'pro';
    sub.source = 'stripe';
    sub.stripe_id = (obj.subscription as string) || `sub_${crypto.randomBytes(12).toString('hex')}`;
    sub.stripe_customer_id = (obj.customer as string) || `cus_${crypto.randomBytes(12).toString('hex')}`;
    sub.expires_at = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    sub.updated_at = new Date();
    // NOTE: free_writes_used is NOT reset on upgrade — counter persists

    jsonResponse(res, 200, {
      success: true,
      event_type: type,
      status: 'activated',
    });
    return;
  }

  jsonResponse(res, 200, {
    success: true,
    event_type: type,
    status: 'ignored',
  });
}

// ---------------------------------------------------------------------------
// Mock server lifecycle
// ---------------------------------------------------------------------------

async function startQuotaMockServer(port = 0): Promise<QuotaMockServer> {
  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      if (method === 'GET' && url === '/health') {
        jsonResponse(res, 200, { status: 'ok' });
        return;
      }

      if (method === 'POST' && url === '/v1/register') {
        await handleRegister(req, res);
        return;
      }

      // Proxy endpoints (quota enforced)
      if (method === 'POST' && url === '/v1/bundler') {
        await handleBundlerProxy(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/subgraph') {
        await handleSubgraphProxy(req, res);
        return;
      }

      // Billing endpoints
      if (method === 'GET' && url.startsWith('/v1/billing/status')) {
        handleBillingStatus(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/billing/checkout') {
        await handleBillingCheckout(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/billing/checkout/crypto') {
        await handleBillingCheckoutCrypto(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/billing/webhook/stripe') {
        await handleStripeWebhook(req, res);
        return;
      }

      jsonResponse(res, 404, { error: 'Not found', url });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  return new Promise<QuotaMockServer>((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      const actualPort = addr.port;
      const serverUrl = `http://127.0.0.1:${actualPort}`;

      resolve({
        url: serverUrl,
        port: actualPort,
        stop: () =>
          new Promise<void>((r) => {
            server.close(() => r());
          }),
        reset: () => {
          subscriptions.clear();
          registeredUsers.clear();
          quotaConfig = {
            free_tier_writes_per_month: 3,
            free_tier_reads_per_month: 5,
            pro_tier_writes_per_month: 10000,
            pro_tier_reads_per_month: 100000,
          };
        },
        getSubscription: (wallet: string) => getOrCreateSubscription(wallet),
        setSubscription: (wallet: string, state: Partial<MockSubscription>) => {
          const sub = getOrCreateSubscription(wallet);
          Object.assign(sub, state, { updated_at: new Date() });
        },
        setQuotaConfig: (config: Partial<QuotaConfig>) => {
          Object.assign(quotaConfig, config);
        },
        getQuotaConfig: () => ({ ...quotaConfig }),
      });
    });
  });
}

// ---------------------------------------------------------------------------
// HTTP test helpers
// ---------------------------------------------------------------------------

async function post(
  baseUrl: string,
  path: string,
  body: unknown,
  headers?: Record<string, string>,
): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(headers ?? {}) },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  return { status: res.status, body: json as Record<string, unknown> };
}

async function get(
  baseUrl: string,
  path: string,
): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await fetch(`${baseUrl}${path}`);
  const json = await res.json();
  return { status: res.status, body: json as Record<string, unknown> };
}

/**
 * Send a write operation (eth_sendUserOperation) through the bundler proxy.
 */
async function sendWriteOp(
  baseUrl: string,
  wallet: string,
): Promise<{ status: number; body: Record<string, unknown> }> {
  return post(baseUrl, '/v1/bundler', {
    jsonrpc: '2.0',
    id: 1,
    method: 'eth_sendUserOperation',
    params: [{
      sender: wallet,
      callData: '0x' + crypto.randomBytes(32).toString('hex'),
    }, '0x0000000071727De22E5E9d8BAf0edAc6f37da032'],
  }, {
    'X-Wallet-Address': wallet,
  });
}

/**
 * Send a read-like RPC call (eth_estimateUserOperationGas) through the bundler proxy.
 * This should NOT consume write quota.
 */
async function sendReadRpc(
  baseUrl: string,
  wallet: string,
): Promise<{ status: number; body: Record<string, unknown> }> {
  return post(baseUrl, '/v1/bundler', {
    jsonrpc: '2.0',
    id: 1,
    method: 'eth_estimateUserOperationGas',
    params: [{ sender: wallet }, '0x0000000071727De22E5E9d8BAf0edAc6f37da032'],
  }, {
    'X-Wallet-Address': wallet,
  });
}

/**
 * Send a GraphQL query through the subgraph proxy.
 */
async function sendSubgraphQuery(
  baseUrl: string,
  wallet: string,
): Promise<{ status: number; body: Record<string, unknown> }> {
  return post(baseUrl, '/v1/subgraph', {
    query: '{ factEntities(first: 100, where: { hash_in: ["abc"] }) { id encrypted } }',
    variables: {},
  }, {
    'X-Wallet-Address': wallet,
  });
}

// ---------------------------------------------------------------------------
// Test infrastructure
// ---------------------------------------------------------------------------

interface TestResult {
  id: string;
  name: string;
  passed: boolean;
  message: string;
  durationMs: number;
}

const allResults: TestResult[] = [];

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

// ---------------------------------------------------------------------------
// T621: Free tier quota enforcement
// ---------------------------------------------------------------------------

async function runT621(server: QuotaMockServer): Promise<void> {
  const WALLET = '0xT621' + crypto.randomBytes(18).toString('hex');

  // =========================================================================
  // T621-01: Write quota — N writes succeed, N+1 returns 403
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T621-01';
    const name = 'Write quota — N writes succeed, N+1 returns 403';
    try {
      server.reset();
      const limit = server.getQuotaConfig().free_tier_writes_per_month; // 3

      // First N writes should succeed
      for (let i = 1; i <= limit; i++) {
        const result = await sendWriteOp(server.url, WALLET);
        assert(result.status === 200, `Write ${i}/${limit} should succeed, got status ${result.status}`);
      }

      // Verify counter matches limit
      const sub = server.getSubscription(WALLET);
      assert(
        sub.free_writes_used === limit,
        `Expected free_writes_used=${limit}, got ${sub.free_writes_used}`,
      );

      // N+1th write should fail with 403 quota_exceeded
      const blocked = await sendWriteOp(server.url, WALLET);
      assert(blocked.status === 403, `Write ${limit + 1} should return 403, got ${blocked.status}`);
      assert(
        blocked.body.error === 'quota_exceeded',
        `Expected error=quota_exceeded, got ${blocked.body.error}`,
      );
      assert(
        typeof blocked.body.upgrade_url === 'string',
        'Response should include upgrade_url',
      );
      assert(
        (blocked.body.upgrade_url as string).includes('pricing'),
        `upgrade_url should point to pricing page, got ${blocked.body.upgrade_url}`,
      );

      // Counter should NOT increment past the limit
      const subAfter = server.getSubscription(WALLET);
      assert(
        subAfter.free_writes_used === limit,
        `Counter should stay at ${limit} after rejected write, got ${subAfter.free_writes_used}`,
      );

      allResults.push({
        id, name, passed: true,
        message: `${limit} writes succeeded, write ${limit + 1} correctly returned 403 quota_exceeded`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T621-02: Read quota has separate limit from writes
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T621-02';
    const name = 'Read quota has separate limit from writes';
    try {
      server.reset();
      const readLimit = server.getQuotaConfig().free_tier_reads_per_month; // 5
      const writeLimit = server.getQuotaConfig().free_tier_writes_per_month; // 3

      // Exhaust write quota
      for (let i = 1; i <= writeLimit; i++) {
        await sendWriteOp(server.url, WALLET);
      }

      // Verify writes are blocked
      const writeBlocked = await sendWriteOp(server.url, WALLET);
      assert(writeBlocked.status === 403, `Writes should be blocked after exhausting quota`);

      // Read operations should still work (separate quota)
      for (let i = 1; i <= readLimit; i++) {
        const result = await sendSubgraphQuery(server.url, WALLET);
        assert(result.status === 200, `Read ${i}/${readLimit} should succeed, got status ${result.status}`);
      }

      // Verify read counter
      const sub = server.getSubscription(WALLET);
      assert(
        sub.free_reads_used === readLimit,
        `Expected free_reads_used=${readLimit}, got ${sub.free_reads_used}`,
      );

      // N+1th read should fail
      const readBlocked = await sendSubgraphQuery(server.url, WALLET);
      assert(readBlocked.status === 403, `Read ${readLimit + 1} should return 403, got ${readBlocked.status}`);
      assert(
        readBlocked.body.error === 'quota_exceeded',
        `Expected read error=quota_exceeded, got ${readBlocked.body.error}`,
      );

      allResults.push({
        id, name, passed: true,
        message: `Write quota (${writeLimit}) and read quota (${readLimit}) enforced independently`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T621-03: Non-write RPC calls do NOT consume write quota
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T621-03';
    const name = 'Non-write RPC calls (gas estimation) do not consume write quota';
    try {
      server.reset();

      // Send several gas estimation calls
      for (let i = 0; i < 10; i++) {
        const result = await sendReadRpc(server.url, WALLET);
        assert(result.status === 200, `Gas estimation call ${i + 1} should succeed`);
      }

      // Verify write counter is still 0
      const sub = server.getSubscription(WALLET);
      assert(
        sub.free_writes_used === 0,
        `Write counter should be 0 after gas estimation calls, got ${sub.free_writes_used}`,
      );

      allResults.push({
        id, name, passed: true,
        message: '10 gas estimation calls did not consume write quota (counter=0)',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T621-04: Counter persists across "restarts" (DB-backed)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T621-04';
    const name = 'Counter persists across "restarts" (DB-backed)';
    try {
      server.reset();

      // Write 2 operations
      await sendWriteOp(server.url, WALLET);
      await sendWriteOp(server.url, WALLET);

      const subBefore = server.getSubscription(WALLET);
      assert(
        subBefore.free_writes_used === 2,
        `Expected 2 writes before "restart", got ${subBefore.free_writes_used}`,
      );

      // Simulate "restart": the in-memory usage tracker in old proxy.py would
      // reset here, but DB-backed implementation persists.
      // We verify the subscription state is unchanged — the mock stores state
      // in the subscriptions Map which simulates the DB.
      // In a real scenario, the server process restarts but reads from PostgreSQL.

      // Read the subscription again (simulating post-restart DB query)
      const subAfter = server.getSubscription(WALLET);
      assert(
        subAfter.free_writes_used === 2,
        `After "restart", expected free_writes_used=2, got ${subAfter.free_writes_used}`,
      );

      // Third write should succeed (limit=3)
      const thirdWrite = await sendWriteOp(server.url, WALLET);
      assert(thirdWrite.status === 200, `Third write should succeed (2/3 used)`);

      // Fourth write should fail (limit=3, now at 3/3)
      const fourthWrite = await sendWriteOp(server.url, WALLET);
      assert(fourthWrite.status === 403, `Fourth write should fail (3/3 used)`);

      allResults.push({
        id, name, passed: true,
        message: 'Counter persisted across simulated restart: 2 -> 2 -> 3 (blocked at 4th)',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T621-05: User isolation — one user's quota does not affect another
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T621-05';
    const name = 'User isolation — one user quota does not affect another';
    try {
      server.reset();
      const walletA = '0xAAAA' + crypto.randomBytes(18).toString('hex');
      const walletB = '0xBBBB' + crypto.randomBytes(18).toString('hex');

      // Exhaust walletA's write quota
      for (let i = 0; i < 3; i++) {
        await sendWriteOp(server.url, walletA);
      }
      const blockedA = await sendWriteOp(server.url, walletA);
      assert(blockedA.status === 403, 'WalletA should be blocked');

      // WalletB should still have full quota
      const writeB = await sendWriteOp(server.url, walletB);
      assert(writeB.status === 200, 'WalletB should succeed (independent quota)');

      const subB = server.getSubscription(walletB);
      assert(
        subB.free_writes_used === 1,
        `WalletB should have 1 write, got ${subB.free_writes_used}`,
      );

      allResults.push({
        id, name, passed: true,
        message: 'WalletA blocked at limit; WalletB unaffected with independent counter',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }
}

// ---------------------------------------------------------------------------
// T622: Quota exceeded -> upgrade flow
// ---------------------------------------------------------------------------

async function runT622(server: QuotaMockServer): Promise<void> {
  const WALLET = '0xT622' + crypto.randomBytes(18).toString('hex');

  // =========================================================================
  // T622-01: 403 response includes upgrade_url
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T622-01';
    const name = '403 quota_exceeded response includes upgrade_url';
    try {
      server.reset();

      // Exhaust write quota
      for (let i = 0; i < 3; i++) {
        await sendWriteOp(server.url, WALLET);
      }

      const blocked = await sendWriteOp(server.url, WALLET);
      assert(blocked.status === 403, `Expected 403, got ${blocked.status}`);
      assert(blocked.body.error === 'quota_exceeded', `Expected error=quota_exceeded`);
      assert(
        typeof blocked.body.message === 'string' && (blocked.body.message as string).length > 0,
        'Response should include a human-readable message',
      );
      assert(
        blocked.body.upgrade_url === 'https://totalreclaw.com/pricing',
        `upgrade_url should be https://totalreclaw.com/pricing, got ${blocked.body.upgrade_url}`,
      );

      allResults.push({
        id, name, passed: true,
        message: '403 response has error, message, and upgrade_url fields',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T622-02: GET /v1/billing/status shows usage count and limit
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T622-02';
    const name = 'Billing status shows usage count and limit after quota exhausted';
    try {
      // State continues from T622-01 (wallet at 3/3 writes)
      const statusResult = await get(
        server.url,
        `/v1/billing/status?wallet_address=${encodeURIComponent(WALLET)}`,
      );

      assert(statusResult.status === 200, `Expected 200, got ${statusResult.status}`);
      assert(statusResult.body.success === true, 'Expected success=true');
      assert(statusResult.body.tier === 'free', `Expected tier=free, got ${statusResult.body.tier}`);
      assert(
        statusResult.body.free_writes_used === 3,
        `Expected free_writes_used=3, got ${statusResult.body.free_writes_used}`,
      );
      assert(
        statusResult.body.free_writes_limit === 3,
        `Expected free_writes_limit=3, got ${statusResult.body.free_writes_limit}`,
      );

      allResults.push({
        id, name, passed: true,
        message: `Billing status: tier=free, writes_used=3, writes_limit=3`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T622-03: POST /v1/billing/checkout returns checkout_url (mock Stripe)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T622-03';
    const name = 'Stripe checkout returns checkout_url';
    try {
      const result = await post(server.url, '/v1/billing/checkout', {
        wallet_address: WALLET,
        tier: 'pro',
      });

      assert(result.status === 200, `Expected 200, got ${result.status}`);
      assert(result.body.success === true, 'Expected success=true');
      assert(
        typeof result.body.checkout_url === 'string',
        'Response should include checkout_url string',
      );
      assert(
        (result.body.checkout_url as string).startsWith('https://checkout.stripe.com/'),
        `checkout_url should start with https://checkout.stripe.com/, got ${result.body.checkout_url}`,
      );

      allResults.push({
        id, name, passed: true,
        message: `Stripe checkout URL: ${result.body.checkout_url}`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T622-04: POST /v1/billing/checkout/crypto returns checkout_url (mock Coinbase)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T622-04';
    const name = 'Coinbase Commerce checkout returns checkout_url';
    try {
      const result = await post(server.url, '/v1/billing/checkout/crypto', {
        wallet_address: WALLET,
        tier: 'pro',
      });

      assert(result.status === 200, `Expected 200, got ${result.status}`);
      assert(result.body.success === true, 'Expected success=true');
      assert(
        typeof result.body.checkout_url === 'string',
        'Response should include checkout_url string',
      );
      assert(
        (result.body.checkout_url as string).startsWith('https://commerce.coinbase.com/'),
        `checkout_url should start with https://commerce.coinbase.com/, got ${result.body.checkout_url}`,
      );

      allResults.push({
        id, name, passed: true,
        message: `Coinbase checkout URL: ${result.body.checkout_url}`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T622-05: Invalid tier returns error
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T622-05';
    const name = 'Invalid tier in checkout returns INVALID_TIER error';
    try {
      const result = await post(server.url, '/v1/billing/checkout', {
        wallet_address: WALLET,
        tier: 'enterprise',
      });

      assert(result.body.success === false, 'Expected success=false for invalid tier');
      assert(
        result.body.error_code === 'INVALID_TIER',
        `Expected error_code=INVALID_TIER, got ${result.body.error_code}`,
      );

      allResults.push({
        id, name, passed: true,
        message: 'Invalid tier correctly rejected with INVALID_TIER',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }
}

// ---------------------------------------------------------------------------
// T623: Dynamic limit change (100 -> 200)
// ---------------------------------------------------------------------------

async function runT623(server: QuotaMockServer): Promise<void> {
  const WALLET = '0xT623' + crypto.randomBytes(18).toString('hex');

  // =========================================================================
  // T623-01: User at 80/100, redeploy to 200 limit, user can write 120 more
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T623-01';
    const name = 'Dynamic limit increase: user at 80/100, limit changed to 200, writes resume';
    try {
      server.reset();

      // Set initial limits to 100
      server.setQuotaConfig({ free_tier_writes_per_month: 100 });

      // Simulate user at 80 writes
      server.setSubscription(WALLET, {
        tier: 'free',
        free_writes_used: 80,
      });

      // Verify user can still write (80/100 is below limit)
      const writeBeforeChange = await sendWriteOp(server.url, WALLET);
      assert(writeBeforeChange.status === 200, 'Write at 80/100 should succeed');

      const subAfterOne = server.getSubscription(WALLET);
      assert(
        subAfterOne.free_writes_used === 81,
        `Expected 81 writes after 1 more, got ${subAfterOne.free_writes_used}`,
      );

      // Now "redeploy" with new limit of 200 (simulates env var change)
      server.setQuotaConfig({ free_tier_writes_per_month: 200 });

      // Verify the counter was NOT reset
      const subAfterRedeploy = server.getSubscription(WALLET);
      assert(
        subAfterRedeploy.free_writes_used === 81,
        `Counter should persist at 81 after limit change, got ${subAfterRedeploy.free_writes_used}`,
      );

      // User should now be able to write more (81/200 is far below new limit)
      const writeAfterChange = await sendWriteOp(server.url, WALLET);
      assert(writeAfterChange.status === 200, 'Write at 81/200 should succeed after limit increase');

      const subAfterTwo = server.getSubscription(WALLET);
      assert(
        subAfterTwo.free_writes_used === 82,
        `Expected 82 writes, got ${subAfterTwo.free_writes_used}`,
      );

      allResults.push({
        id, name, passed: true,
        message: 'Counter preserved at 81 after limit change from 100 to 200; writes resumed',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T623-02: User at 100/100 (blocked), limit raised to 200, writes resume
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T623-02';
    const name = 'Blocked user unblocked by limit increase (100/100 -> 200 limit)';
    try {
      server.reset();
      server.setQuotaConfig({ free_tier_writes_per_month: 100 });

      // Set user exactly at limit
      server.setSubscription(WALLET, {
        tier: 'free',
        free_writes_used: 100,
      });

      // Verify blocked
      const blocked = await sendWriteOp(server.url, WALLET);
      assert(blocked.status === 403, 'Write at 100/100 should be blocked');

      // Raise limit to 200
      server.setQuotaConfig({ free_tier_writes_per_month: 200 });

      // Should now succeed
      const unblocked = await sendWriteOp(server.url, WALLET);
      assert(unblocked.status === 200, 'Write at 100/200 should succeed after limit increase');

      // Counter incremented
      const sub = server.getSubscription(WALLET);
      assert(
        sub.free_writes_used === 101,
        `Expected 101, got ${sub.free_writes_used}`,
      );

      allResults.push({
        id, name, passed: true,
        message: 'User unblocked: 100/100 (403) -> limit raised to 200 -> 101/200 (200 OK)',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T623-03: Limit decrease does NOT reduce counter (counter > new limit = blocked)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T623-03';
    const name = 'Limit decrease blocks user when counter exceeds new limit';
    try {
      server.reset();
      server.setQuotaConfig({ free_tier_writes_per_month: 200 });

      // User at 150/200 (OK)
      server.setSubscription(WALLET, {
        tier: 'free',
        free_writes_used: 150,
      });

      const beforeDecrease = await sendWriteOp(server.url, WALLET);
      assert(beforeDecrease.status === 200, 'Write at 150/200 should succeed');

      // Lower limit to 100
      server.setQuotaConfig({ free_tier_writes_per_month: 100 });

      // Now blocked (151/100)
      const afterDecrease = await sendWriteOp(server.url, WALLET);
      assert(afterDecrease.status === 403, 'Write at 151/100 should be blocked after limit decrease');

      // Counter was NOT reset
      const sub = server.getSubscription(WALLET);
      assert(
        sub.free_writes_used === 151,
        `Counter should be 151 (not reset), got ${sub.free_writes_used}`,
      );

      allResults.push({
        id, name, passed: true,
        message: 'Limit decreased from 200 to 100; user at 151 is now blocked',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T623-04: Billing status reflects new limit after config change
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T623-04';
    const name = 'Billing status reflects updated limit after config change';
    try {
      // State continues from T623-03: wallet at 151 writes, limit now 100
      const statusResult = await get(
        server.url,
        `/v1/billing/status?wallet_address=${encodeURIComponent(WALLET)}`,
      );

      assert(statusResult.status === 200, `Expected 200`);
      assert(
        statusResult.body.free_writes_used === 151,
        `Expected free_writes_used=151, got ${statusResult.body.free_writes_used}`,
      );
      assert(
        statusResult.body.free_writes_limit === 100,
        `Expected free_writes_limit=100 (new limit), got ${statusResult.body.free_writes_limit}`,
      );

      allResults.push({
        id, name, passed: true,
        message: 'Billing status shows writes_used=151 and writes_limit=100 (new config)',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }
}

// ---------------------------------------------------------------------------
// T624: Subscription upgrade bypasses free tier
// ---------------------------------------------------------------------------

async function runT624(server: QuotaMockServer): Promise<void> {
  const WALLET = '0xT624' + crypto.randomBytes(18).toString('hex');

  // =========================================================================
  // T624-01: Hit free tier limit (3/3), upgrade to pro, writes resume
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T624-01';
    const name = 'Free tier limit (3/3), Stripe upgrade, writes resume with pro limit';
    try {
      server.reset();

      // Exhaust free tier
      for (let i = 0; i < 3; i++) {
        const result = await sendWriteOp(server.url, WALLET);
        assert(result.status === 200, `Free-tier write ${i + 1} should succeed`);
      }

      // Verify blocked
      const blocked = await sendWriteOp(server.url, WALLET);
      assert(blocked.status === 403, 'Write 4 should be blocked at free tier limit');
      assert(blocked.body.error === 'quota_exceeded', 'Should get quota_exceeded error');

      // Simulate Stripe webhook: checkout.session.completed
      const webhookResult = await post(server.url, '/v1/billing/webhook/stripe', {
        type: 'checkout.session.completed',
        data: {
          object: {
            client_reference_id: WALLET,
            subscription: `sub_test_${crypto.randomBytes(8).toString('hex')}`,
            customer: `cus_test_${crypto.randomBytes(8).toString('hex')}`,
          },
        },
      });

      assert(webhookResult.status === 200, `Webhook should return 200, got ${webhookResult.status}`);
      assert(webhookResult.body.success === true, 'Webhook should succeed');

      // Verify tier changed to pro
      const sub = server.getSubscription(WALLET);
      assert(sub.tier === 'pro', `Expected tier=pro after webhook, got ${sub.tier}`);
      assert(sub.source === 'stripe', `Expected source=stripe, got ${sub.source}`);

      // Write should now succeed (pro tier limit is 10000)
      const proWrite = await sendWriteOp(server.url, WALLET);
      assert(proWrite.status === 200, 'Write should succeed after upgrading to pro');

      allResults.push({
        id, name, passed: true,
        message: 'Free tier blocked at 3/3, upgraded to pro via Stripe webhook, writes resumed',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T624-02: Pro user can write well beyond free tier cap
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T624-02';
    const name = 'Pro user can write well beyond free tier cap';
    try {
      // State continues from T624-01: wallet is pro with 4 writes (3 free + 1 post-upgrade)
      const subBefore = server.getSubscription(WALLET);
      const writesBefore = subBefore.free_writes_used;

      // Write 10 more times (well beyond free limit of 3)
      for (let i = 0; i < 10; i++) {
        const result = await sendWriteOp(server.url, WALLET);
        assert(
          result.status === 200,
          `Pro write ${i + 1} should succeed (total: ${writesBefore + i + 1}), got status ${result.status}`,
        );
      }

      const subAfter = server.getSubscription(WALLET);
      assert(
        subAfter.free_writes_used === writesBefore + 10,
        `Expected ${writesBefore + 10} writes, got ${subAfter.free_writes_used}`,
      );

      // Total writes are now well above free limit of 3
      assert(
        subAfter.free_writes_used > 3,
        `Total writes (${subAfter.free_writes_used}) should exceed free limit (3)`,
      );

      allResults.push({
        id, name, passed: true,
        message: `Pro user at ${subAfter.free_writes_used} writes (far above free limit of 3)`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T624-03: Write counter is NOT reset on upgrade
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T624-03';
    const name = 'Write counter is NOT reset on upgrade (counter persists)';
    try {
      server.reset();

      // User writes 2 facts on free tier
      await sendWriteOp(server.url, WALLET);
      await sendWriteOp(server.url, WALLET);

      const subBeforeUpgrade = server.getSubscription(WALLET);
      assert(
        subBeforeUpgrade.free_writes_used === 2,
        `Expected 2 writes before upgrade, got ${subBeforeUpgrade.free_writes_used}`,
      );

      // Upgrade to pro
      await post(server.url, '/v1/billing/webhook/stripe', {
        type: 'checkout.session.completed',
        data: {
          object: {
            client_reference_id: WALLET,
            subscription: `sub_persist_${crypto.randomBytes(8).toString('hex')}`,
            customer: `cus_persist_${crypto.randomBytes(8).toString('hex')}`,
          },
        },
      });

      // Counter should still show 2 (not reset to 0)
      const subAfterUpgrade = server.getSubscription(WALLET);
      assert(
        subAfterUpgrade.free_writes_used === 2,
        `Counter should persist at 2 after upgrade, got ${subAfterUpgrade.free_writes_used}`,
      );

      // Write one more
      await sendWriteOp(server.url, WALLET);

      const subAfterWrite = server.getSubscription(WALLET);
      assert(
        subAfterWrite.free_writes_used === 3,
        `Expected 3 total writes (2 free + 1 pro), got ${subAfterWrite.free_writes_used}`,
      );

      allResults.push({
        id, name, passed: true,
        message: 'Counter preserved: 2 (free) -> upgrade -> 2 (pro) -> write -> 3',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T624-04: Billing status shows pro tier after upgrade
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T624-04';
    const name = 'Billing status reflects pro tier after upgrade';
    try {
      // State continues from T624-03: wallet is pro with 3 writes
      const statusResult = await get(
        server.url,
        `/v1/billing/status?wallet_address=${encodeURIComponent(WALLET)}`,
      );

      assert(statusResult.status === 200, `Expected 200`);
      assert(statusResult.body.success === true, 'Expected success=true');
      assert(statusResult.body.tier === 'pro', `Expected tier=pro, got ${statusResult.body.tier}`);
      assert(statusResult.body.source === 'stripe', `Expected source=stripe, got ${statusResult.body.source}`);
      assert(
        statusResult.body.free_writes_used === 3,
        `Expected free_writes_used=3, got ${statusResult.body.free_writes_used}`,
      );
      assert(
        statusResult.body.free_writes_limit === 10000,
        `Expected free_writes_limit=10000 (pro), got ${statusResult.body.free_writes_limit}`,
      );
      assert(
        statusResult.body.expires_at !== null && statusResult.body.expires_at !== undefined,
        'Expected non-null expires_at for pro tier',
      );

      allResults.push({
        id, name, passed: true,
        message: 'Status shows tier=pro, source=stripe, writes_limit=10000',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T624-05: Read quota also uses pro tier limit after upgrade
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T624-05';
    const name = 'Read quota uses pro tier limit after upgrade';
    try {
      server.reset();
      server.setQuotaConfig({
        free_tier_reads_per_month: 2,
        pro_tier_reads_per_month: 100000,
      });

      // Exhaust free read quota
      await sendSubgraphQuery(server.url, WALLET);
      await sendSubgraphQuery(server.url, WALLET);

      const blockedRead = await sendSubgraphQuery(server.url, WALLET);
      assert(blockedRead.status === 403, 'Read 3 should be blocked at free limit (2)');

      // Upgrade to pro
      await post(server.url, '/v1/billing/webhook/stripe', {
        type: 'checkout.session.completed',
        data: {
          object: {
            client_reference_id: WALLET,
            subscription: `sub_read_${crypto.randomBytes(8).toString('hex')}`,
            customer: `cus_read_${crypto.randomBytes(8).toString('hex')}`,
          },
        },
      });

      // Read should now succeed (pro limit is 100000)
      const proRead = await sendSubgraphQuery(server.url, WALLET);
      assert(proRead.status === 200, 'Read should succeed after upgrade to pro');

      allResults.push({
        id, name, passed: true,
        message: 'Read quota: blocked at 2/2 free, upgraded to pro, reads resumed',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      allResults.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Main execution
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const startTime = performance.now();

  // Start the mock server
  const server = await startQuotaMockServer();

  console.log('');
  console.log('='.repeat(70));
  console.log('  TotalReclaw Billing Quota & Upgrade E2E Tests (T621-T624)');
  console.log('='.repeat(70));
  console.log(`  Mock Server: ${server.url}`);
  console.log(`  Free Write Limit: ${server.getQuotaConfig().free_tier_writes_per_month}`);
  console.log(`  Free Read Limit:  ${server.getQuotaConfig().free_tier_reads_per_month}`);
  console.log(`  Pro Write Limit:  ${server.getQuotaConfig().pro_tier_writes_per_month}`);
  console.log('='.repeat(70));
  console.log('');

  try {
    // Run all test groups
    console.log('--- T621: Free tier quota enforcement ---');
    console.log('');
    await runT621(server);

    console.log('');
    console.log('--- T622: Quota exceeded -> upgrade flow ---');
    console.log('');
    await runT622(server);

    console.log('');
    console.log('--- T623: Dynamic limit change ---');
    console.log('');
    await runT623(server);

    console.log('');
    console.log('--- T624: Subscription upgrade bypasses free tier ---');
    console.log('');
    await runT624(server);
  } finally {
    await server.stop();
  }

  // -------------------------------------------------------------------------
  // TAP output
  // -------------------------------------------------------------------------

  console.log('');
  console.log(`TAP version 13`);
  console.log(`1..${allResults.length}`);

  let tapIndex = 0;
  for (const result of allResults) {
    tapIndex++;
    const status = result.passed ? 'ok' : 'not ok';
    const duration = result.durationMs.toFixed(1);
    console.log(`${status} ${tapIndex} - [${result.id}] ${result.name} (${duration}ms)`);
    if (!result.passed) {
      console.log(`#   FAIL: ${result.message}`);
    }
  }

  // -------------------------------------------------------------------------
  // Summary
  // -------------------------------------------------------------------------

  const durationSeconds = (performance.now() - startTime) / 1000;
  const passed = allResults.filter((r) => r.passed).length;
  const failed = allResults.filter((r) => !r.passed).length;
  const total = allResults.length;

  console.log('');
  console.log('='.repeat(70));
  console.log(`  RESULTS: ${passed}/${total} passed, ${failed} failed`);
  console.log(`  Duration: ${durationSeconds.toFixed(2)}s`);

  // Per-task summary
  const taskGroups: Record<string, TestResult[]> = {};
  for (const r of allResults) {
    const taskId = r.id.split('-')[0]; // e.g., "T621"
    if (!taskGroups[taskId]) taskGroups[taskId] = [];
    taskGroups[taskId].push(r);
  }

  const taskNames: Record<string, string> = {
    T621: 'Free tier quota enforcement',
    T622: 'Quota exceeded -> upgrade flow',
    T623: 'Dynamic limit change',
    T624: 'Subscription upgrade bypasses free tier',
  };

  for (const [taskId, results] of Object.entries(taskGroups)) {
    const tp = results.filter((r) => r.passed).length;
    const tf = results.filter((r) => !r.passed).length;
    const status = tf === 0 ? 'PASS' : 'FAIL';
    console.log(`  ${taskId} (${taskNames[taskId] ?? taskId}): ${status} - ${tp}/${results.length} passed`);
  }

  console.log('='.repeat(70));
  console.log('');

  // Print failures for easy scanning
  if (failed > 0) {
    console.log('FAILURES:');
    for (const result of allResults) {
      if (!result.passed) {
        console.log(`  [${result.id}] ${result.name}: ${result.message}`);
      }
    }
    console.log('');
  }

  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(2);
});
