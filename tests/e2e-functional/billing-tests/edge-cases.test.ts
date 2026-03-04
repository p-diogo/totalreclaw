/**
 * Cross-Journey Edge Cases Tests
 *
 * Validates billing edge cases across journeys:
 *   - Mixed payment sources (Stripe + Coinbase)
 *   - Wallet address case sensitivity
 *   - Default billing status for unknown wallets
 *   - Webhook validation edge cases
 *   - Pimlico error handling
 *
 * Tests:
 *   T-X01: Mixed payment sources — Stripe pro then Coinbase extension
 *   T-X03: Wallet address case sensitivity (0xabcd vs 0xAbCd)
 *   T-X04: Billing status endpoint — no subscription row -> free tier defaults
 *   T-X05: Stripe webhook checkout.session.completed with missing client_reference_id
 *   T-X06: Pimlico webhook sponsorship.finalized -> acknowledged, no side effects
 *   T-X07: Coinbase webhook missing wallet_address in metadata -> 400 error
 *   T-X08: Pimlico HTTP 500 -> relay returns clear error (not crash)
 *
 * Note: T-X02 (concurrent race condition) is skipped — needs real PG, Tier 2 only.
 *
 * Run: cd tests/e2e-functional && npx tsx billing-tests/edge-cases.test.ts
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

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------

const subscriptions = new Map<string, MockSubscription>();
const FREE_TIER_LIMIT = 100;

// Track Pimlico webhook invocations
let pimlicoWebhookCount = 0;

function resetState(): void {
  subscriptions.clear();
  pimlicoWebhookCount = 0;
}

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

async function startMockServer(): Promise<{
  url: string;
  server: http.Server;
  stop: () => Promise<void>;
  pimlicoErrorMode: { enabled: boolean };
}> {
  // Shared flag to simulate Pimlico outage
  const pimlicoErrorMode = { enabled: false };

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
      // GET /v1/billing/status — With case-normalized wallet lookup
      // ---------------------------------------------------------------
      if (method === 'GET' && url.startsWith('/v1/billing/status')) {
        const parsedUrl = new URL(url, `http://${req.headers.host}`);
        const rawWallet = parsedUrl.searchParams.get('wallet_address') || '';
        const wallet = rawWallet.toLowerCase(); // Case normalization

        const sub = subscriptions.get(wallet);

        if (!sub) {
          // No subscription row -> free tier defaults
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
      // POST /v1/billing/checkout — Create Stripe checkout
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/billing/checkout') {
        const body = JSON.parse(await readBody(req));
        json(res, 200, {
          success: true,
          checkout_url: `https://checkout.stripe.com/test/${(body.wallet_address || '').slice(2, 10)}`,
        });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/billing/webhook/stripe — Stripe webhook
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/billing/webhook/stripe') {
        const rawBody = await readBody(req);
        const sigHeader = req.headers['stripe-signature'] as string | undefined;

        if (!sigHeader) {
          json(res, 400, { error: 'Missing Stripe-Signature header' });
          return;
        }

        const body = JSON.parse(rawBody);
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

          // T-X05: Missing client_reference_id -> 200 OK but no subscription created
          if (!walletAddr) {
            json(res, 200, {
              success: true,
              event_type: type,
              status: 'ignored_missing_reference',
            });
            return;
          }

          const wallet = walletAddr.toLowerCase();
          const existing = subscriptions.get(wallet);

          subscriptions.set(wallet, {
            wallet_address: wallet,
            tier: 'pro',
            source: 'stripe',
            stripe_id: data.object.subscription || `sub_${crypto.randomUUID().slice(0, 8)}`,
            coinbase_id: existing?.coinbase_id ?? null,
            expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
            free_writes_used: existing?.free_writes_used ?? 0,
            free_writes_limit: FREE_TIER_LIMIT,
            free_writes_reset_at: null,
          });
        }

        json(res, 200, { success: true, event_type: type });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/billing/webhook/coinbase — Coinbase Commerce webhook
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/billing/webhook/coinbase') {
        const rawBody = await readBody(req);
        const sigHeader = req.headers['x-cc-webhook-signature'] as string | undefined;

        if (!sigHeader) {
          json(res, 400, { error: 'Missing X-CC-Webhook-Signature header' });
          return;
        }

        const body = JSON.parse(rawBody);
        const { event } = body as {
          event: {
            type: string;
            data: {
              id?: string;
              metadata?: {
                wallet_address?: string;
              };
            };
          };
        };

        // T-X07: Missing wallet_address in metadata -> 400
        if (!event.data.metadata?.wallet_address) {
          json(res, 400, {
            error: 'Missing wallet_address in event metadata',
            error_code: 'INVALID_WEBHOOK_PAYLOAD',
          });
          return;
        }

        if (event.type === 'charge:confirmed') {
          const wallet = event.data.metadata.wallet_address.toLowerCase();
          const existing = subscriptions.get(wallet);

          // Coinbase expiry extension: new_expires = max(current_expires, now) + 30 days
          const now = new Date();
          const currentExpiry = existing?.expires_at ?? null;
          const baseDate = currentExpiry && currentExpiry > now ? currentExpiry : now;
          const newExpiry = new Date(baseDate.getTime() + 30 * 24 * 60 * 60 * 1000);

          subscriptions.set(wallet, {
            wallet_address: wallet,
            tier: 'pro',
            source: 'coinbase_commerce',
            stripe_id: existing?.stripe_id ?? null,
            coinbase_id: event.data.id || `chrg_${crypto.randomUUID().slice(0, 8)}`,
            expires_at: newExpiry,
            free_writes_used: existing?.free_writes_used ?? 0,
            free_writes_limit: FREE_TIER_LIMIT,
            free_writes_reset_at: null,
          });
        }

        json(res, 200, { success: true, event_type: event.type });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/relay/webhook/pimlico — Pimlico sponsorship webhook
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/relay/webhook/pimlico') {
        pimlicoWebhookCount++;
        const body = JSON.parse(await readBody(req));

        // Acknowledge the webhook, no subscription side effects
        json(res, 200, {
          success: true,
          event_type: body.type || 'sponsorship.finalized',
          status: 'acknowledged',
        });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/relay/sponsor — With Pimlico error simulation
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/relay/sponsor') {
        const body = JSON.parse(await readBody(req));
        const wallet = (body.wallet_address || '').toLowerCase();

        // T-X08: Simulate Pimlico HTTP 500
        if (pimlicoErrorMode.enabled) {
          json(res, 502, {
            success: false,
            error_code: 'PAYMASTER_ERROR',
            error_message: 'Pimlico paymaster returned HTTP 500: Internal Server Error',
          });
          return;
        }

        const sub = subscriptions.get(wallet);

        if (sub && sub.tier === 'pro') {
          json(res, 200, { success: true, sponsored: true });
          return;
        }

        const used = sub?.free_writes_used ?? 0;
        const limit = sub?.free_writes_limit ?? FREE_TIER_LIMIT;
        if (used >= limit) {
          json(res, 200, { success: false, reason: 'upgrade_required' });
          return;
        }

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
        pimlicoErrorMode,
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
// Stripe signature helper
// ---------------------------------------------------------------------------

function makeStripeSig(body: string): string {
  const timestamp = Math.floor(Date.now() / 1000);
  const sig = crypto.createHmac('sha256', 'whsec_test').update(`${timestamp}.${body}`).digest('hex');
  return `t=${timestamp},v1=${sig}`;
}

// ---------------------------------------------------------------------------
// Coinbase signature helper
// ---------------------------------------------------------------------------

function makeCoinbaseSig(body: string): string {
  return crypto.createHmac('sha256', 'coinbase_webhook_secret').update(body).digest('hex');
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function runTests(): Promise<void> {
  const mock = await startMockServer();

  try {
    // -----------------------------------------------------------------
    // T-X01: Mixed payment sources — Stripe pro then Coinbase extension
    //
    // Stripe subscription expires in 15 days. Coinbase payment should
    // extend from the Stripe period end (not now) + 30 days.
    // Source should change to coinbase_commerce.
    // -----------------------------------------------------------------
    resetState();

    const walletX01 = '0x' + 'a1b2c3d4e5'.repeat(4);
    const walletX01Lower = walletX01.toLowerCase();

    // Step 1: Set up Stripe subscription expiring in 15 days
    const stripeExpiry = new Date(Date.now() + 15 * 24 * 60 * 60 * 1000);
    subscriptions.set(walletX01Lower, {
      wallet_address: walletX01Lower,
      tier: 'pro',
      source: 'stripe',
      stripe_id: 'sub_stripe_x01',
      coinbase_id: null,
      expires_at: stripeExpiry,
      free_writes_used: 25,
      free_writes_limit: FREE_TIER_LIMIT,
      free_writes_reset_at: null,
    });

    // Verify initial state
    const statusBeforeCoinbase = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(walletX01)}`,
    );
    ok(
      statusBeforeCoinbase.data.tier === 'pro',
      'T-X01: Initial Stripe subscription is pro',
    );
    ok(
      statusBeforeCoinbase.data.source === 'stripe',
      'T-X01: Initial source is stripe',
    );

    // Step 2: Coinbase webhook fires (user paid with crypto)
    const coinbasePayload = JSON.stringify({
      event: {
        type: 'charge:confirmed',
        data: {
          id: 'chrg_coinbase_x01',
          metadata: {
            wallet_address: walletX01,
          },
        },
      },
    });

    const coinbaseWebhook = await httpPost(
      `${mock.url}/v1/billing/webhook/coinbase`,
      JSON.parse(coinbasePayload),
      { 'X-CC-Webhook-Signature': makeCoinbaseSig(coinbasePayload) },
    );
    ok(
      coinbaseWebhook.data.success === true,
      'T-X01: Coinbase webhook succeeds',
    );

    // Step 3: Verify expiry extended from Stripe period end + 30 days
    const sub = subscriptions.get(walletX01Lower)!;

    // The new expiry should be approximately stripeExpiry + 30 days
    // (since stripeExpiry > now, base = stripeExpiry)
    const expectedExpiry = new Date(stripeExpiry.getTime() + 30 * 24 * 60 * 60 * 1000);
    const expiryDiffMs = Math.abs(sub.expires_at!.getTime() - expectedExpiry.getTime());
    ok(
      expiryDiffMs < 1000, // within 1 second tolerance
      'T-X01: Expiry extends from Stripe period end + 30 days',
      `Expected ~${expectedExpiry.toISOString()}, got ${sub.expires_at?.toISOString()}, diff=${expiryDiffMs}ms`,
    );

    // Step 4: Source should change to coinbase_commerce
    ok(
      sub.source === 'coinbase_commerce',
      'T-X01: Source changes to coinbase_commerce after Coinbase payment',
      `Got source: ${sub.source}`,
    );

    // Step 5: Tier is still pro
    ok(
      sub.tier === 'pro',
      'T-X01: Tier remains pro after mixed payments',
    );

    // Step 6: Coinbase ID is set
    ok(
      sub.coinbase_id === 'chrg_coinbase_x01',
      'T-X01: Coinbase charge ID is recorded',
    );

    // Step 7: Stripe ID is preserved
    ok(
      sub.stripe_id === 'sub_stripe_x01',
      'T-X01: Stripe subscription ID is preserved',
    );

    // -----------------------------------------------------------------
    // T-X03: Wallet address case sensitivity
    //
    // 0xabcd and 0xAbCd should resolve to the same subscription.
    // -----------------------------------------------------------------
    resetState();

    const walletLower = '0xabcdef1234567890abcdef1234567890abcdef12';
    const walletMixed = '0xAbCdEf1234567890ABCDEF1234567890AbCdEf12';

    // Create subscription with lowercase wallet
    subscriptions.set(walletLower, {
      wallet_address: walletLower,
      tier: 'pro',
      source: 'stripe',
      stripe_id: 'sub_case_test',
      coinbase_id: null,
      expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000),
      free_writes_used: 10,
      free_writes_limit: FREE_TIER_LIMIT,
      free_writes_reset_at: null,
    });

    // Query with mixed-case wallet
    const statusMixed = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(walletMixed)}`,
    );
    ok(
      statusMixed.data.tier === 'pro',
      'T-X03: Mixed-case wallet 0xAbCd resolves to same subscription as 0xabcd',
      `Got tier: ${statusMixed.data.tier}`,
    );
    ok(
      statusMixed.data.source === 'stripe',
      'T-X03: Source matches for case-insensitive lookup',
    );
    ok(
      statusMixed.data.free_writes_used === 10,
      'T-X03: free_writes_used matches (same record)',
      `Got: ${statusMixed.data.free_writes_used}`,
    );

    // Query with exact lowercase wallet
    const statusLower = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(walletLower)}`,
    );
    ok(
      statusLower.data.tier === statusMixed.data.tier,
      'T-X03: Both casing variants return identical tier',
    );

    // -----------------------------------------------------------------
    // T-X04: Billing status endpoint — no subscription row -> free tier
    // -----------------------------------------------------------------
    resetState();

    const unknownWallet = '0x' + crypto.randomBytes(20).toString('hex');
    const statusUnknown = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(unknownWallet)}`,
    );
    ok(
      statusUnknown.data.success === true,
      'T-X04: Status endpoint returns success for unknown wallet',
    );
    ok(
      statusUnknown.data.tier === 'free',
      'T-X04: Unknown wallet defaults to free tier',
    );
    ok(
      statusUnknown.data.source === null || statusUnknown.data.source === undefined,
      'T-X04: Unknown wallet has null source',
    );
    ok(
      statusUnknown.data.free_writes_used === 0,
      'T-X04: Unknown wallet has 0 free_writes_used',
    );
    ok(
      statusUnknown.data.free_writes_limit === FREE_TIER_LIMIT,
      'T-X04: Unknown wallet has default free_writes_limit (100)',
      `Got: ${statusUnknown.data.free_writes_limit}`,
    );
    ok(
      statusUnknown.data.expires_at === null || statusUnknown.data.expires_at === undefined,
      'T-X04: Unknown wallet has null expires_at',
    );

    // -----------------------------------------------------------------
    // T-X05: Stripe webhook with missing client_reference_id
    //
    // Should return 200 OK but NOT create a subscription.
    // -----------------------------------------------------------------
    resetState();

    const webhookNoRef = {
      type: 'checkout.session.completed',
      data: {
        object: {
          // client_reference_id is MISSING
          subscription: 'sub_orphaned',
          customer: 'cus_orphaned',
        },
      },
    };
    const webhookNoRefStr = JSON.stringify(webhookNoRef);

    const resultNoRef = await httpPost(
      `${mock.url}/v1/billing/webhook/stripe`,
      webhookNoRef,
      { 'Stripe-Signature': makeStripeSig(webhookNoRefStr) },
    );

    ok(
      resultNoRef.status === 200,
      'T-X05: Webhook returns 200 OK even with missing client_reference_id',
      `Status: ${resultNoRef.status}`,
    );
    ok(
      resultNoRef.data.success === true,
      'T-X05: Webhook response success=true',
    );
    ok(
      subscriptions.size === 0,
      'T-X05: No subscription created when client_reference_id is missing',
      `Subscriptions: ${subscriptions.size}`,
    );

    // -----------------------------------------------------------------
    // T-X06: Pimlico webhook sponsorship.finalized -> acknowledged, no side effects
    // -----------------------------------------------------------------
    resetState();

    const pimlicoPayload = {
      type: 'sponsorship.finalized',
      data: {
        userOpHash: '0x' + crypto.randomBytes(32).toString('hex'),
        wallet_address: '0x' + crypto.randomBytes(20).toString('hex'),
        status: 'success',
      },
    };

    const pimlicoResult = await httpPost(
      `${mock.url}/v1/relay/webhook/pimlico`,
      pimlicoPayload,
    );

    ok(
      pimlicoResult.status === 200,
      'T-X06: Pimlico webhook returns 200',
    );
    ok(
      pimlicoResult.data.success === true,
      'T-X06: Pimlico webhook acknowledged',
    );
    ok(
      pimlicoResult.data.status === 'acknowledged',
      'T-X06: Response status is "acknowledged"',
    );
    ok(
      pimlicoWebhookCount === 1,
      'T-X06: Pimlico webhook handler was invoked',
    );

    // No subscription side effects
    ok(
      subscriptions.size === 0,
      'T-X06: No subscriptions created from Pimlico webhook',
      `Subscriptions: ${subscriptions.size}`,
    );

    // -----------------------------------------------------------------
    // T-X07: Coinbase webhook missing wallet_address in metadata -> 400
    // -----------------------------------------------------------------
    resetState();

    const coinbaseNoWallet = JSON.stringify({
      event: {
        type: 'charge:confirmed',
        data: {
          id: 'chrg_no_wallet',
          metadata: {
            // wallet_address is MISSING
          },
        },
      },
    });

    const resultNoWallet = await httpPost(
      `${mock.url}/v1/billing/webhook/coinbase`,
      JSON.parse(coinbaseNoWallet),
      { 'X-CC-Webhook-Signature': makeCoinbaseSig(coinbaseNoWallet) },
    );

    ok(
      resultNoWallet.status === 400,
      'T-X07: Coinbase webhook returns 400 when wallet_address missing',
      `Status: ${resultNoWallet.status}`,
    );
    ok(
      resultNoWallet.data.error !== undefined,
      'T-X07: Error message is present in response',
    );
    ok(
      subscriptions.size === 0,
      'T-X07: No subscription created from invalid Coinbase webhook',
    );

    // -----------------------------------------------------------------
    // T-X08: Pimlico HTTP 500 -> relay returns clear error (not crash)
    // -----------------------------------------------------------------
    resetState();

    const walletX08 = '0x' + crypto.randomBytes(20).toString('hex');

    // Enable Pimlico error mode
    mock.pimlicoErrorMode.enabled = true;

    const sponsorError = await httpPost(`${mock.url}/v1/relay/sponsor`, {
      wallet_address: walletX08,
    });

    ok(
      sponsorError.status === 502,
      'T-X08: Relay returns 502 when Pimlico is down',
      `Status: ${sponsorError.status}`,
    );
    ok(
      sponsorError.data.success === false,
      'T-X08: success=false in error response',
    );
    ok(
      sponsorError.data.error_code === 'PAYMASTER_ERROR',
      'T-X08: Error code is PAYMASTER_ERROR',
      `Got: ${sponsorError.data.error_code}`,
    );
    ok(
      typeof sponsorError.data.error_message === 'string' &&
        (sponsorError.data.error_message as string).includes('500'),
      'T-X08: Error message mentions HTTP 500',
      `Message: ${sponsorError.data.error_message}`,
    );

    // Disable error mode and verify normal operation resumes
    mock.pimlicoErrorMode.enabled = false;

    const sponsorRecovered = await httpPost(`${mock.url}/v1/relay/sponsor`, {
      wallet_address: walletX08,
    });
    ok(
      sponsorRecovered.data.success === true,
      'T-X08: Relay recovers after Pimlico comes back online',
    );
  } finally {
    await mock.stop();
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

console.log('TAP version 14');
console.log('1..34');

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
