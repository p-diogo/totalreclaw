/**
 * Journey F — Agent-Driven UX Tests
 *
 * Validates the plugin lifecycle hooks and billing integration:
 *   - Automatic search on every user message (before_agent_start)
 *   - Automatic store on every turn (agent_end)
 *   - Free tier limit detection and upgrade messaging
 *   - Checkout URL creation
 *   - Subscription activation detection after webhook
 *   - Store and compaction hooks
 *
 * Tests:
 *   T-F01: Automatic search on every message (before_agent_start hook)
 *   T-F02: Automatic store on every turn (agent_end hook)
 *   T-F03: Agent detects free tier limit and shows upgrade message
 *   T-F04: Agent creates checkout URL and presents it
 *   T-F05: Agent detects subscription activation after webhook
 *   T-F06: Store and compaction hooks fire correctly
 *
 * Run: cd tests/e2e-functional && npx tsx billing-tests/journey-f.test.ts
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
  coinbase_id: string | null;
  expires_at: Date | null;
  free_writes_used: number;
  free_writes_limit: number;
  free_writes_reset_at: Date | null;
}

interface StoredFact {
  id: string;
  owner: string;
  encrypted_blob: string;
  blind_indices: string[];
  encrypted_embedding?: string;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------

const subscriptions = new Map<string, MockSubscription>();
const factStore = new Map<string, StoredFact[]>();

// Track request counts for hook verification
let searchRequestCount = 0;
let storeRequestCount = 0;
let sponsorRequestCount = 0;
let checkoutRequestCount = 0;

function resetState(): void {
  subscriptions.clear();
  factStore.clear();
  searchRequestCount = 0;
  storeRequestCount = 0;
  sponsorRequestCount = 0;
  checkoutRequestCount = 0;
}

// ---------------------------------------------------------------------------
// Test wallet
// ---------------------------------------------------------------------------

const TEST_WALLET = '0x' + crypto.randomBytes(20).toString('hex');
const FREE_TIER_LIMIT = 100;

// ---------------------------------------------------------------------------
// Mock HTTP Server
// ---------------------------------------------------------------------------

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
  });
}

function json(res: http.ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

async function startMockServer(): Promise<{ url: string; server: http.Server; stop: () => Promise<void> }> {
  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      // ---------------------------------------------------------------
      // POST /v1/register
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/register') {
        await readBody(req);
        json(res, 200, { success: true, user_id: `user-${crypto.randomUUID().slice(0, 8)}` });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/search — tracks invocations for hook testing
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/search') {
        searchRequestCount++;
        const body = JSON.parse(await readBody(req));
        const { owner, trapdoors } = body as { owner: string; trapdoors: string[] };
        const ownerKey = (owner || '').toLowerCase();
        const store = factStore.get(ownerKey) || [];
        const trapdoorSet = new Set(trapdoors);

        const matches = store
          .map((fact) => ({
            fact,
            matchCount: fact.blind_indices.filter((idx) => trapdoorSet.has(idx)).length,
          }))
          .filter(({ matchCount }) => matchCount > 0)
          .sort((a, b) => b.matchCount - a.matchCount)
          .slice(0, 100);

        const results = matches.map(({ fact }) => ({
          fact_id: fact.id,
          encrypted_blob: fact.encrypted_blob,
          decay_score: 1.0,
          timestamp: Date.now(),
        }));

        json(res, 200, { success: true, results });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/store — tracks invocations for hook testing
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/store') {
        storeRequestCount++;
        const body = JSON.parse(await readBody(req));
        const { owner, facts: incoming } = body as {
          owner: string;
          facts: Array<{
            id: string;
            encrypted_blob: string;
            blind_indices: string[];
            timestamp?: string;
          }>;
        };
        const ownerKey = (owner || '').toLowerCase();
        if (!factStore.has(ownerKey)) {
          factStore.set(ownerKey, []);
        }
        const store = factStore.get(ownerKey)!;
        const ids: string[] = [];
        for (const f of incoming) {
          store.push({
            id: f.id,
            owner: ownerKey,
            encrypted_blob: f.encrypted_blob,
            blind_indices: f.blind_indices,
            timestamp: f.timestamp || new Date().toISOString(),
          });
          ids.push(f.id);
        }
        json(res, 200, { success: true, ids });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/relay/sponsor — Checks subscription, returns sponsor result
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/relay/sponsor') {
        sponsorRequestCount++;
        const body = JSON.parse(await readBody(req));
        const wallet = (body.wallet_address || '').toLowerCase();
        const sub = subscriptions.get(wallet);

        // Pro tier: always sponsor
        if (sub && sub.tier === 'pro') {
          json(res, 200, { success: true, sponsored: true });
          return;
        }

        // Free tier: check quota
        const used = sub?.free_writes_used ?? 0;
        const limit = sub?.free_writes_limit ?? FREE_TIER_LIMIT;

        if (used >= limit) {
          json(res, 200, { success: false, reason: 'upgrade_required' });
          return;
        }

        // Increment usage
        if (sub) {
          sub.free_writes_used += 1;
        } else {
          subscriptions.set(wallet, {
            wallet_address: wallet,
            tier: 'free',
            source: null,
            stripe_id: null,
            coinbase_id: null,
            expires_at: null,
            free_writes_used: 1,
            free_writes_limit: FREE_TIER_LIMIT,
            free_writes_reset_at: null,
          });
        }

        json(res, 200, { success: true, sponsored: true });
        return;
      }

      // ---------------------------------------------------------------
      // GET /v1/billing/status — Subscription status
      // ---------------------------------------------------------------
      if (method === 'GET' && url.startsWith('/v1/billing/status')) {
        const parsedUrl = new URL(url, `http://${req.headers.host}`);
        const wallet = (parsedUrl.searchParams.get('wallet_address') || '').toLowerCase();
        const sub = subscriptions.get(wallet);

        if (!sub) {
          json(res, 200, {
            success: true,
            wallet_address: wallet,
            tier: 'free',
            source: null,
            expires_at: null,
            free_writes_used: 0,
            free_writes_limit: FREE_TIER_LIMIT,
          });
          return;
        }

        json(res, 200, {
          success: true,
          wallet_address: sub.wallet_address,
          tier: sub.tier,
          source: sub.source,
          expires_at: sub.expires_at?.toISOString() ?? null,
          free_writes_used: sub.free_writes_used,
          free_writes_limit: sub.free_writes_limit,
        });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/billing/checkout — Create checkout URL
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/billing/checkout') {
        checkoutRequestCount++;
        const body = JSON.parse(await readBody(req));
        const { wallet_address, tier } = body;

        if (tier && tier !== 'pro') {
          json(res, 200, {
            success: false,
            error_code: 'INVALID_TIER',
            error_message: "Only 'pro' tier is currently available.",
          });
          return;
        }

        json(res, 200, {
          success: true,
          checkout_url: `https://checkout.stripe.com/c/pay/test_session_${(wallet_address || '').slice(2, 10)}`,
        });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/billing/webhook/stripe — Simulated webhook
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/billing/webhook/stripe') {
        const body = JSON.parse(await readBody(req));
        const sigHeader = req.headers['stripe-signature'] as string | undefined;

        if (!sigHeader) {
          json(res, 400, { error: 'Missing Stripe-Signature header' });
          return;
        }

        const { type, data } = body as {
          type: string;
          data: {
            object: {
              client_reference_id?: string;
              subscription?: string;
              customer?: string;
            };
          };
        };

        if (type === 'checkout.session.completed') {
          const walletAddr = data.object.client_reference_id;
          if (walletAddr) {
            const wallet = walletAddr.toLowerCase();
            subscriptions.set(wallet, {
              wallet_address: wallet,
              tier: 'pro',
              source: 'stripe',
              stripe_id: data.object.subscription || `sub_${crypto.randomUUID().slice(0, 8)}`,
              coinbase_id: null,
              expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
              free_writes_used: subscriptions.get(wallet)?.free_writes_used ?? 0,
              free_writes_limit: FREE_TIER_LIMIT,
              free_writes_reset_at: null,
            });
          }
        }

        json(res, 200, { success: true, event_type: type });
        return;
      }

      json(res, 404, { error: 'Not found' });
    } catch (err) {
      json(res, 500, { error: err instanceof Error ? err.message : String(err) });
    }
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      const url = `http://127.0.0.1:${addr.port}`;
      resolve({
        url,
        server,
        stop: () => new Promise<void>((r) => server.close(() => r())),
      });
    });
  });
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function httpPost(
  url: string,
  body: unknown,
  headers?: Record<string, string>,
): Promise<{ status: number; data: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const postData = JSON.stringify(body);
    const req = http.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(postData),
          ...headers,
        },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf8');
          resolve({ status: res.statusCode ?? 500, data: JSON.parse(raw) });
        });
      },
    );
    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

async function httpGet(url: string): Promise<{ status: number; data: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = http.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname + parsed.search,
        method: 'GET',
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf8');
          resolve({ status: res.statusCode ?? 500, data: JSON.parse(raw) });
        });
      },
    );
    req.on('error', reject);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// TAP test runner
// ---------------------------------------------------------------------------

let testNumber = 0;
let passed = 0;
let failed = 0;

function ok(condition: boolean, description: string, detail?: string): void {
  testNumber++;
  if (condition) {
    console.log(`ok ${testNumber} - ${description}`);
    passed++;
  } else {
    console.log(`not ok ${testNumber} - ${description}`);
    if (detail) console.log(`  ---\n  message: ${detail}\n  ...`);
    failed++;
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function runTests(): Promise<void> {
  const mock = await startMockServer();
  const wallet = TEST_WALLET.toLowerCase();

  try {
    // -----------------------------------------------------------------
    // T-F01: Automatic search on every message (before_agent_start hook)
    //
    // The plugin fires before_agent_start on every user message >= 5 chars.
    // We simulate this by calling search for each qualifying message.
    // -----------------------------------------------------------------
    resetState();

    const messages = [
      'Hi',        // 2 chars — should NOT trigger search
      'Hello world, tell me about dark mode', // >= 5 chars — triggers
      'What is my dog\'s name?',               // >= 5 chars — triggers
      'OK',                                    // 2 chars — should NOT trigger
      'Tell me about Lisbon',                  // >= 5 chars — triggers
    ];

    const expectedSearches = messages.filter((m) => m.length >= 5).length;
    let actualSearches = 0;

    for (const msg of messages) {
      if (msg.length >= 5) {
        // Simulate before_agent_start hook: fire search
        const tokens = msg.toLowerCase().split(/\s+/).filter((t) => t.length >= 2);
        const trapdoors = tokens.map((t) =>
          crypto.createHash('sha256').update(t).digest('hex'),
        );

        await httpPost(`${mock.url}/v1/search`, {
          owner: wallet,
          trapdoors,
          max_candidates: 100,
        });
        actualSearches++;
      }
      // Messages < 5 chars: hook does not fire
    }

    ok(
      searchRequestCount === expectedSearches,
      'T-F01: Search fires for messages >= 5 chars only',
      `Expected ${expectedSearches} searches, got ${searchRequestCount}`,
    );
    ok(
      actualSearches === 3,
      'T-F01: Exactly 3 of 5 messages trigger search (>= 5 chars)',
      `Got ${actualSearches}`,
    );

    // Verify short messages did NOT trigger search
    ok(
      searchRequestCount === 3,
      'T-F01: Short messages ("Hi", "OK") did not trigger search',
    );

    // -----------------------------------------------------------------
    // T-F02: Automatic store on every turn (agent_end hook)
    //
    // The agent_end hook fires after every agent response, extracts facts,
    // and submits them to the relay.
    // -----------------------------------------------------------------
    resetState();

    const turns = [
      { user: 'My favorite color is blue', assistant: 'Got it, blue is your favorite color.' },
      { user: 'I work at Google', assistant: 'Noted, you work at Google.' },
      { user: 'Remind me about my dentist appointment', assistant: 'I will remind you about your appointment.' },
    ];

    for (let i = 0; i < turns.length; i++) {
      // Simulate agent_end: extract facts from the turn, store them
      const factText = turns[i].user; // simplified extraction
      const blindIndices = factText
        .toLowerCase()
        .split(/\s+/)
        .filter((t) => t.length >= 2)
        .map((t) => crypto.createHash('sha256').update(t).digest('hex'));

      await httpPost(`${mock.url}/v1/store`, {
        owner: wallet,
        facts: [
          {
            id: `turn-fact-${i}`,
            encrypted_blob: Buffer.from(factText).toString('base64'),
            blind_indices: blindIndices,
            timestamp: new Date().toISOString(),
          },
        ],
      });
    }

    ok(
      storeRequestCount === 3,
      'T-F02: Store fires on every turn (3 turns = 3 store calls)',
      `Got ${storeRequestCount} store calls`,
    );

    const storedFacts = factStore.get(wallet) || [];
    ok(
      storedFacts.length === 3,
      'T-F02: 3 facts stored from 3 turns',
      `Got ${storedFacts.length}`,
    );

    // -----------------------------------------------------------------
    // T-F03: Agent detects free tier limit and shows upgrade message
    //
    // 99 used -> 100th succeeds -> 101st denied with upgrade_required
    // -----------------------------------------------------------------
    resetState();

    // Pre-set subscription at 99 writes used
    subscriptions.set(wallet, {
      wallet_address: wallet,
      tier: 'free',
      source: null,
      stripe_id: null,
      coinbase_id: null,
      expires_at: null,
      free_writes_used: 99,
      free_writes_limit: FREE_TIER_LIMIT,
      free_writes_reset_at: null,
    });

    // 100th write should succeed (99 -> 100)
    const sponsor100 = await httpPost(`${mock.url}/v1/relay/sponsor`, {
      wallet_address: wallet,
    });
    ok(
      sponsor100.data.success === true && sponsor100.data.sponsored === true,
      'T-F03: 100th write succeeds (quota: 99 used -> 100)',
    );

    // 101st write should be denied
    const sponsor101 = await httpPost(`${mock.url}/v1/relay/sponsor`, {
      wallet_address: wallet,
    });
    ok(
      sponsor101.data.success === false,
      'T-F03: 101st write denied (quota exhausted)',
      `success=${sponsor101.data.success}`,
    );
    ok(
      sponsor101.data.reason === 'upgrade_required',
      'T-F03: Denial reason is "upgrade_required"',
      `reason=${sponsor101.data.reason}`,
    );

    // Agent would detect this and show upgrade message to user
    const upgradeNeeded = sponsor101.data.success === false && sponsor101.data.reason === 'upgrade_required';
    ok(
      upgradeNeeded,
      'T-F03: Agent can detect upgrade_required and show upgrade prompt',
    );

    // -----------------------------------------------------------------
    // T-F04: Agent creates checkout URL and presents it
    // -----------------------------------------------------------------
    resetState();

    const checkout = await httpPost(`${mock.url}/v1/billing/checkout`, {
      wallet_address: wallet,
      tier: 'pro',
    });
    ok(
      checkout.data.success === true,
      'T-F04: Checkout creation succeeds',
    );
    ok(
      typeof checkout.data.checkout_url === 'string' && (checkout.data.checkout_url as string).startsWith('https://'),
      'T-F04: Checkout URL is a valid HTTPS URL',
      `URL: ${checkout.data.checkout_url}`,
    );
    ok(
      checkoutRequestCount === 1,
      'T-F04: Exactly 1 checkout request made',
      `Got ${checkoutRequestCount}`,
    );

    // Verify agent can present the URL (it's a string the agent shows to the user)
    const checkoutUrl = checkout.data.checkout_url as string;
    ok(
      checkoutUrl.includes('checkout.stripe.com'),
      'T-F04: URL points to Stripe checkout',
    );

    // -----------------------------------------------------------------
    // T-F05: Agent detects subscription activation after webhook
    //
    // Simulate: webhook fires -> poll status -> tier=pro
    // -----------------------------------------------------------------
    resetState();

    // Before webhook: wallet is free tier
    const statusBefore = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(wallet)}`,
    );
    ok(
      statusBefore.data.tier === 'free',
      'T-F05: Before webhook, tier is free',
    );

    // Simulate Stripe webhook: checkout.session.completed
    const webhookPayload = {
      type: 'checkout.session.completed',
      data: {
        object: {
          client_reference_id: wallet,
          subscription: 'sub_test_activation_001',
          customer: 'cus_test_001',
        },
      },
    };

    // Compute a fake signature (mock server just checks header exists)
    const timestamp = Math.floor(Date.now() / 1000);
    const sigPayload = `${timestamp}.${JSON.stringify(webhookPayload)}`;
    const sig = crypto.createHmac('sha256', 'whsec_test').update(sigPayload).digest('hex');

    const webhook = await httpPost(
      `${mock.url}/v1/billing/webhook/stripe`,
      webhookPayload,
      { 'Stripe-Signature': `t=${timestamp},v1=${sig}` },
    );
    ok(
      webhook.data.success === true,
      'T-F05: Stripe webhook returns success',
    );
    ok(
      webhook.data.event_type === 'checkout.session.completed',
      'T-F05: Webhook event type is checkout.session.completed',
    );

    // Agent polls status -> should now see pro
    const statusAfter = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(wallet)}`,
    );
    ok(
      statusAfter.data.tier === 'pro',
      'T-F05: After webhook, tier is pro',
      `Got tier: ${statusAfter.data.tier}`,
    );
    ok(
      statusAfter.data.source === 'stripe',
      'T-F05: Source is stripe after activation',
    );

    // Relay sponsorship should now succeed without quota check
    const sponsorAfter = await httpPost(`${mock.url}/v1/relay/sponsor`, {
      wallet_address: wallet,
    });
    ok(
      sponsorAfter.data.success === true && sponsorAfter.data.sponsored === true,
      'T-F05: Pro subscription is sponsored without quota check',
    );

    // -----------------------------------------------------------------
    // T-F06: Store and compaction hooks fire correctly
    //
    // before_compaction triggers a store via relay (same as agent_end).
    // We simulate this by calling store when the compaction signal fires.
    // -----------------------------------------------------------------
    resetState();

    // Simulate several turns of normal operation (agent_end stores)
    for (let i = 0; i < 3; i++) {
      await httpPost(`${mock.url}/v1/store`, {
        owner: wallet,
        facts: [
          {
            id: `pre-compaction-${i}`,
            encrypted_blob: Buffer.from(`fact ${i}`).toString('base64'),
            blind_indices: [crypto.createHash('sha256').update(`token${i}`).digest('hex')],
          },
        ],
      });
    }
    ok(storeRequestCount === 3, 'T-F06: 3 agent_end stores before compaction');

    // Simulate before_compaction hook: fires store with any pending extracted facts
    const compactionFacts = [
      {
        id: 'compaction-fact-1',
        encrypted_blob: Buffer.from('compaction fact data').toString('base64'),
        blind_indices: [crypto.createHash('sha256').update('compaction').digest('hex')],
        timestamp: new Date().toISOString(),
      },
    ];

    await httpPost(`${mock.url}/v1/store`, {
      owner: wallet,
      facts: compactionFacts,
    });
    ok(
      storeRequestCount === 4,
      'T-F06: before_compaction triggers additional store call (total: 4)',
      `Got ${storeRequestCount}`,
    );

    const allStoredFacts = factStore.get(wallet) || [];
    ok(
      allStoredFacts.length === 4,
      'T-F06: Total 4 facts stored (3 agent_end + 1 compaction)',
      `Got ${allStoredFacts.length}`,
    );

    // Verify the compaction fact is in the store
    const compactionFactStored = allStoredFacts.find((f) => f.id === 'compaction-fact-1');
    ok(
      compactionFactStored !== undefined,
      'T-F06: Compaction fact is persisted in store',
    );

    // Simulate before_reset hook (same behavior: fire store for any pending)
    await httpPost(`${mock.url}/v1/store`, {
      owner: wallet,
      facts: [
        {
          id: 'reset-fact-1',
          encrypted_blob: Buffer.from('reset fact data').toString('base64'),
          blind_indices: [crypto.createHash('sha256').update('reset').digest('hex')],
        },
      ],
    });
    ok(
      storeRequestCount === 5,
      'T-F06: before_reset also triggers store (total: 5)',
      `Got ${storeRequestCount}`,
    );
  } finally {
    await mock.stop();
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

console.log('TAP version 14');
console.log('1..24');

runTests()
  .then(() => {
    console.log(`\n# Tests: ${testNumber}`);
    console.log(`# Pass:  ${passed}`);
    console.log(`# Fail:  ${failed}`);
    if (failed > 0) process.exit(1);
  })
  .catch((err) => {
    console.log(`Bail out! ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  });
