/**
 * Mock Billing & Relay Server
 *
 * In-memory HTTP server implementing the TotalReclaw billing, relay,
 * and registration endpoints needed for billing E2E testing.
 *
 * No external dependencies — uses only node:http and node:crypto.
 *
 * Endpoints:
 *   POST /v1/register                    — Register a user (always succeeds)
 *   POST /v1/relay/sponsor               — Mock relay sponsorship (checks subscription)
 *   POST /v1/relay/webhook/pimlico       — Mock Pimlico webhook
 *   GET  /v1/relay/status/:hash          — Returns configurable relay status
 *   POST /v1/billing/checkout            — Returns fake Stripe checkout URL
 *   POST /v1/billing/checkout/crypto     — Returns fake Coinbase Commerce URL
 *   POST /v1/billing/webhook/stripe      — Simulated Stripe webhook
 *   POST /v1/billing/webhook/coinbase    — Simulated Coinbase webhook
 *   GET  /v1/billing/status              — Returns subscription status
 *   GET  /health                         — Health check
 *
 * Usage:
 *   import { startBillingMockServer } from './mock-billing-server.js';
 *   const server = await startBillingMockServer();
 *   // ... run tests ...
 *   await server.stop();
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MockSubscription {
  wallet_address: string;
  tier: 'free' | 'pro';
  source: 'stripe' | 'coinbase_commerce' | null;
  stripe_id: string | null;
  stripe_customer_id: string | null;
  coinbase_id: string | null;
  expires_at: Date | null;
  free_writes_used: number;
  free_writes_limit: number;
  free_writes_reset_at: Date | null;
  created_at: Date;
  updated_at: Date;
}

export interface RelayStatusEntry {
  hash: string;
  status: 'pending' | 'confirmed' | 'failed';
  blockNumber?: number;
}

export interface BillingMockServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
  /** Clear all subscriptions, relay statuses, and processed charge IDs. */
  reset: () => void;
  /** Get or create a subscription for a wallet address. */
  getSubscription: (wallet: string) => MockSubscription;
  /** Directly set subscription state (bypassing webhooks). */
  setSubscription: (wallet: string, state: Partial<MockSubscription>) => void;
  /** Set a configurable relay status response for a given hash. */
  setRelayStatus: (hash: string, status: RelayStatusEntry) => void;
  /** Get the HMAC webhook secret used for Coinbase signature verification. */
  webhookSecret: string;
  /** Get all processed Coinbase charge IDs (for idempotency testing). */
  getProcessedChargeIds: () => Set<string>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FREE_TIER_LIMIT = 100;
const SUBSCRIPTION_DAYS = 30;
const COINBASE_WEBHOOK_SECRET = 'test-coinbase-webhook-secret-2026';

// ---------------------------------------------------------------------------
// In-memory storage
// ---------------------------------------------------------------------------

/** wallet_address -> MockSubscription */
let subscriptions = new Map<string, MockSubscription>();

/** userOpHash -> RelayStatusEntry */
let relayStatuses = new Map<string, RelayStatusEntry>();

/** Set of Coinbase charge IDs already processed (idempotency). */
let processedChargeIds = new Set<string>();

/** Registered users: auth_key_hash -> user_id */
let registeredUsers = new Map<string, string>();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDefaultSubscription(wallet: string): MockSubscription {
  const now = new Date();
  return {
    wallet_address: wallet,
    tier: 'free',
    source: null,
    stripe_id: null,
    stripe_customer_id: null,
    coinbase_id: null,
    expires_at: null,
    free_writes_used: 0,
    free_writes_limit: FREE_TIER_LIMIT,
    free_writes_reset_at: null,
    created_at: now,
    updated_at: now,
  };
}

function getOrCreateSubscription(wallet: string): MockSubscription {
  let sub = subscriptions.get(wallet);
  if (!sub) {
    sub = makeDefaultSubscription(wallet);
    subscriptions.set(wallet, sub);
  }
  return sub;
}

async function readBody(req: http.IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function readBodyRaw(req: http.IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks);
}

function jsonResponse(
  res: http.ServerResponse,
  status: number,
  body: unknown,
): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

function generateUserOpHash(): string {
  return `0x${crypto.randomBytes(32).toString('hex')}`;
}

function isExpired(sub: MockSubscription): boolean {
  if (!sub.expires_at) return false;
  return sub.expires_at.getTime() < Date.now();
}

/**
 * Monthly reset check: if free_writes_reset_at is before the start of
 * the current calendar month (UTC), reset the counter to 0.
 */
function checkMonthlyReset(sub: MockSubscription): void {
  const now = new Date();
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));

  if (sub.free_writes_reset_at === null || sub.free_writes_reset_at < monthStart) {
    sub.free_writes_used = 0;
    sub.free_writes_reset_at = monthStart;
    sub.updated_at = new Date();
  }
}

function computeHmacSha256(secret: string, payload: string | Buffer): string {
  return crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
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

async function handleRelaySponsor(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { wallet_address } = body as { wallet_address: string };

  if (!wallet_address) {
    jsonResponse(res, 400, { success: false, reason: 'missing_wallet' });
    return;
  }

  const sub = getOrCreateSubscription(wallet_address);

  // Pro tier: check expiry
  if (sub.tier === 'pro') {
    if (isExpired(sub)) {
      // Expired pro -> treat as free
    } else {
      // Pro tier, not expired -> sponsor unconditionally
      const hash = generateUserOpHash();
      relayStatuses.set(hash, { hash, status: 'confirmed' });
      jsonResponse(res, 200, { success: true, userOpHash: hash, tier: 'pro' });
      return;
    }
  }

  // Free tier logic
  checkMonthlyReset(sub);

  if (sub.free_writes_used >= sub.free_writes_limit) {
    jsonResponse(res, 200, {
      success: false,
      reason: 'upgrade_required',
      free_writes_used: sub.free_writes_used,
      free_writes_limit: sub.free_writes_limit,
    });
    return;
  }

  // Increment and sponsor
  sub.free_writes_used++;
  sub.updated_at = new Date();

  const hash = generateUserOpHash();
  relayStatuses.set(hash, { hash, status: 'confirmed' });
  jsonResponse(res, 200, {
    success: true,
    userOpHash: hash,
    tier: 'free',
    free_writes_used: sub.free_writes_used,
    free_writes_limit: sub.free_writes_limit,
  });
}

async function handlePimlicoWebhook(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const body = JSON.parse(await readBody(req));
  const { wallet_address } = body as { wallet_address: string };

  if (!wallet_address) {
    jsonResponse(res, 400, { success: false, reason: 'missing_wallet' });
    return;
  }

  const sub = getOrCreateSubscription(wallet_address);

  // Check if the wallet has sponsorship eligibility
  if (sub.tier === 'pro' && !isExpired(sub)) {
    jsonResponse(res, 200, { sponsor: true, tier: 'pro' });
    return;
  }

  // Free tier: check limits
  checkMonthlyReset(sub);
  if (sub.free_writes_used < sub.free_writes_limit) {
    jsonResponse(res, 200, { sponsor: true, tier: 'free' });
    return;
  }

  jsonResponse(res, 200, { sponsor: false, reason: 'upgrade_required' });
}

function handleRelayStatus(
  res: http.ServerResponse,
  hash: string,
): void {
  const entry = relayStatuses.get(hash);
  if (!entry) {
    jsonResponse(res, 200, {
      success: true,
      status: 'unknown',
      hash,
    });
    return;
  }

  jsonResponse(res, 200, {
    success: true,
    status: entry.status,
    hash: entry.hash,
    blockNumber: entry.blockNumber,
  });
}

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
  const checkoutUrl = `https://checkout.stripe.com/c/pay/${sessionId}`;

  jsonResponse(res, 200, {
    success: true,
    checkout_url: checkoutUrl,
    session_id: sessionId,
  });
}

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
  const hostedUrl = `https://commerce.coinbase.com/charges/${chargeCode}`;

  jsonResponse(res, 200, {
    success: true,
    checkout_url: hostedUrl,
    charge_code: chargeCode,
  });
}

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

  switch (type) {
    case 'checkout.session.completed': {
      const wallet = obj.client_reference_id as string;
      const stripeSubId = (obj.subscription as string) || `sub_${crypto.randomBytes(12).toString('hex')}`;
      const stripeCusId = (obj.customer as string) || `cus_${crypto.randomBytes(12).toString('hex')}`;

      if (!wallet) {
        jsonResponse(res, 400, {
          success: false,
          error_code: 'MISSING_WALLET',
          error_message: 'client_reference_id (wallet) is required.',
        });
        return;
      }

      const sub = getOrCreateSubscription(wallet);
      sub.tier = 'pro';
      sub.source = 'stripe';
      sub.stripe_id = stripeSubId;
      sub.stripe_customer_id = stripeCusId;
      // Default: 30 days from now, unless current_period_end is provided
      const periodEnd = obj.current_period_end as number | undefined;
      sub.expires_at = periodEnd
        ? new Date(periodEnd * 1000)
        : new Date(Date.now() + SUBSCRIPTION_DAYS * 24 * 60 * 60 * 1000);
      sub.updated_at = new Date();

      jsonResponse(res, 200, {
        success: true,
        event_type: type,
        status: 'activated',
      });
      break;
    }

    case 'customer.subscription.updated': {
      const stripeId = obj.id as string;
      const status = obj.status as string;
      const periodEnd = obj.current_period_end as number | undefined;

      // Find subscription by stripe_id
      let targetSub: MockSubscription | undefined;
      for (const sub of subscriptions.values()) {
        if (sub.stripe_id === stripeId) {
          targetSub = sub;
          break;
        }
      }

      if (!targetSub) {
        jsonResponse(res, 200, {
          success: true,
          event_type: type,
          status: 'skipped',
          message: 'No matching subscription found.',
        });
        return;
      }

      // Map Stripe status to our tier
      targetSub.tier = ['active', 'trialing', 'past_due'].includes(status) ? 'pro' : 'free';
      if (periodEnd) {
        targetSub.expires_at = new Date(periodEnd * 1000);
      }
      targetSub.updated_at = new Date();

      jsonResponse(res, 200, {
        success: true,
        event_type: type,
        status: 'updated',
      });
      break;
    }

    case 'customer.subscription.deleted': {
      const stripeId = obj.id as string;

      let targetSub: MockSubscription | undefined;
      for (const sub of subscriptions.values()) {
        if (sub.stripe_id === stripeId) {
          targetSub = sub;
          break;
        }
      }

      if (!targetSub) {
        jsonResponse(res, 200, {
          success: true,
          event_type: type,
          status: 'skipped',
        });
        return;
      }

      targetSub.tier = 'free';
      targetSub.expires_at = null;
      targetSub.stripe_id = null;
      targetSub.updated_at = new Date();

      jsonResponse(res, 200, {
        success: true,
        event_type: type,
        status: 'downgraded',
      });
      break;
    }

    case 'invoice.payment_succeeded': {
      const stripeSubId = obj.subscription as string;
      if (!stripeSubId) {
        jsonResponse(res, 200, {
          success: true,
          event_type: type,
          status: 'skipped',
        });
        return;
      }

      let targetSub: MockSubscription | undefined;
      for (const sub of subscriptions.values()) {
        if (sub.stripe_id === stripeSubId) {
          targetSub = sub;
          break;
        }
      }

      if (!targetSub) {
        jsonResponse(res, 200, {
          success: true,
          event_type: type,
          status: 'skipped',
        });
        return;
      }

      // Renew: extend 30 days from now
      targetSub.tier = 'pro';
      targetSub.expires_at = new Date(Date.now() + SUBSCRIPTION_DAYS * 24 * 60 * 60 * 1000);
      targetSub.updated_at = new Date();

      jsonResponse(res, 200, {
        success: true,
        event_type: type,
        status: 'renewed',
      });
      break;
    }

    default:
      jsonResponse(res, 200, {
        success: true,
        event_type: type,
        status: 'ignored',
      });
  }
}

async function handleCoinbaseWebhook(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const rawBody = await readBodyRaw(req);
  const sigHeader = req.headers['x-cc-webhook-signature'] as string | undefined;

  // Signature verification
  if (!sigHeader) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_SIGNATURE',
      error_message: 'Missing X-CC-Webhook-Signature header.',
    });
    return;
  }

  const expectedSig = computeHmacSha256(COINBASE_WEBHOOK_SECRET, rawBody);
  const sigValid = crypto.timingSafeEqual(
    Buffer.from(expectedSig, 'hex'),
    Buffer.from(sigHeader, 'hex'),
  );

  if (!sigValid) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_SIGNATURE',
      error_message: 'Invalid webhook signature.',
    });
    return;
  }

  // Parse event
  let event: Record<string, unknown>;
  try {
    event = JSON.parse(rawBody.toString('utf8'));
  } catch {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_PAYLOAD',
      error_message: 'Malformed JSON payload.',
    });
    return;
  }

  const eventWrapper = event.event as Record<string, unknown> | undefined;
  if (!eventWrapper) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_PAYLOAD',
      error_message: 'Missing event wrapper.',
    });
    return;
  }

  const eventType = eventWrapper.type as string;
  const eventData = eventWrapper.data as Record<string, unknown> | undefined;
  const chargeId = (eventData?.id || eventData?.code) as string | undefined;
  const metadata = eventData?.metadata as Record<string, string> | undefined;
  const walletAddress = metadata?.wallet_address;

  if (!walletAddress) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_WALLET',
      error_message: 'Missing wallet_address in metadata.',
    });
    return;
  }

  switch (eventType) {
    case 'charge:confirmed': {
      if (!chargeId) {
        jsonResponse(res, 400, {
          success: false,
          error_code: 'MISSING_CHARGE_ID',
          error_message: 'Missing charge ID.',
        });
        return;
      }

      // Idempotency: if this charge was already processed, skip
      if (processedChargeIds.has(chargeId)) {
        jsonResponse(res, 200, {
          success: true,
          event_type: eventType,
          status: 'already_processed',
        });
        return;
      }

      const sub = getOrCreateSubscription(walletAddress);

      // If existing subscription has same coinbase_id, skip (secondary idempotency check)
      if (sub.coinbase_id === chargeId) {
        jsonResponse(res, 200, {
          success: true,
          event_type: eventType,
          status: 'already_processed',
        });
        return;
      }

      // Calculate new expiry: max(current_expires, now) + 30 days
      const now = new Date();
      let baseDate = now;
      if (sub.expires_at && sub.expires_at > now) {
        baseDate = sub.expires_at;
      }
      const newExpires = new Date(baseDate.getTime() + SUBSCRIPTION_DAYS * 24 * 60 * 60 * 1000);

      sub.tier = 'pro';
      sub.source = 'coinbase_commerce';
      sub.coinbase_id = chargeId;
      sub.expires_at = newExpires;
      sub.updated_at = new Date();

      processedChargeIds.add(chargeId);

      jsonResponse(res, 200, {
        success: true,
        event_type: eventType,
        status: 'activated',
        wallet_address: walletAddress,
        expires_at: newExpires.toISOString(),
      });
      break;
    }

    case 'charge:failed': {
      // No subscription change on failure
      jsonResponse(res, 200, {
        success: true,
        event_type: eventType,
        status: 'failed',
        wallet_address: walletAddress,
      });
      break;
    }

    case 'charge:pending': {
      jsonResponse(res, 200, {
        success: true,
        event_type: eventType,
        status: 'pending',
        wallet_address: walletAddress,
      });
      break;
    }

    default:
      jsonResponse(res, 200, {
        success: true,
        event_type: eventType,
        status: 'ignored',
      });
  }
}

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

  const sub = subscriptions.get(wallet);

  if (!sub) {
    jsonResponse(res, 200, {
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

  // Check if pro subscription has expired
  let effectiveTier = sub.tier;
  if (effectiveTier === 'pro' && sub.expires_at && sub.expires_at < new Date()) {
    effectiveTier = 'free';
  }

  jsonResponse(res, 200, {
    success: true,
    wallet_address: sub.wallet_address,
    tier: effectiveTier,
    source: sub.source,
    expires_at: sub.expires_at ? sub.expires_at.toISOString() : null,
    free_writes_used: sub.free_writes_used,
    free_writes_limit: sub.free_writes_limit,
  });
}

// ---------------------------------------------------------------------------
// Server lifecycle
// ---------------------------------------------------------------------------

export async function startBillingMockServer(port = 0): Promise<BillingMockServer> {
  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      // Health check
      if (method === 'GET' && url === '/health') {
        jsonResponse(res, 200, { status: 'ok' });
        return;
      }

      // Registration
      if (method === 'POST' && url === '/v1/register') {
        await handleRegister(req, res);
        return;
      }

      // Relay sponsor
      if (method === 'POST' && url === '/v1/relay/sponsor') {
        await handleRelaySponsor(req, res);
        return;
      }

      // Pimlico webhook
      if (method === 'POST' && url === '/v1/relay/webhook/pimlico') {
        await handlePimlicoWebhook(req, res);
        return;
      }

      // Relay status
      const relayStatusMatch = url.match(/^\/v1\/relay\/status\/([^?]+)/);
      if (method === 'GET' && relayStatusMatch) {
        handleRelayStatus(res, decodeURIComponent(relayStatusMatch[1]));
        return;
      }

      // Billing checkout (Stripe)
      if (method === 'POST' && url === '/v1/billing/checkout') {
        await handleBillingCheckout(req, res);
        return;
      }

      // Billing checkout (Coinbase Commerce)
      if (method === 'POST' && url === '/v1/billing/checkout/crypto') {
        await handleBillingCheckoutCrypto(req, res);
        return;
      }

      // Stripe webhook
      if (method === 'POST' && url === '/v1/billing/webhook/stripe') {
        await handleStripeWebhook(req, res);
        return;
      }

      // Coinbase webhook
      if (method === 'POST' && url === '/v1/billing/webhook/coinbase') {
        await handleCoinbaseWebhook(req, res);
        return;
      }

      // Billing status
      if (method === 'GET' && url.startsWith('/v1/billing/status')) {
        handleBillingStatus(req, res);
        return;
      }

      jsonResponse(res, 404, { error: 'Not found', url });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  return new Promise<BillingMockServer>((resolve) => {
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
          relayStatuses.clear();
          processedChargeIds.clear();
          registeredUsers.clear();
        },
        getSubscription: (wallet: string) => getOrCreateSubscription(wallet),
        setSubscription: (wallet: string, state: Partial<MockSubscription>) => {
          const sub = getOrCreateSubscription(wallet);
          Object.assign(sub, state, { updated_at: new Date() });
        },
        setRelayStatus: (hash: string, entry: RelayStatusEntry) => {
          relayStatuses.set(hash, entry);
        },
        webhookSecret: COINBASE_WEBHOOK_SECRET,
        getProcessedChargeIds: () => new Set(processedChargeIds),
      });
    });
  });
}
