/**
 * Webhook signature and event-builder helpers for E2E integration tests.
 *
 * Provides:
 * - Stripe webhook signature computation (t=<ts>,v1=<hmac>)
 * - Coinbase Commerce HMAC-SHA256 signature computation
 * - Event payload builders for both providers
 *
 * The webhook secrets MUST match the environment variables configured
 * in docker-compose.yml for the server container.
 */

import * as crypto from 'crypto';

// ---------------------------------------------------------------------------
// Secrets — must match the server's env (docker-compose.yml)
// ---------------------------------------------------------------------------

export const STRIPE_WEBHOOK_SECRET = 'whsec_test_secret_for_e2e';
export const COINBASE_WEBHOOK_SECRET = 'coinbase_webhook_secret_for_e2e';

// ---------------------------------------------------------------------------
// Stripe Signature
// ---------------------------------------------------------------------------

/**
 * Compute a Stripe webhook signature for a payload string.
 *
 * Stripe signature format:
 *   t=<unix_ts>,v1=HMAC-SHA256(secret, "<ts>.<payload>")
 *
 * @param payload - The raw JSON body string.
 * @returns Signature header value and the timestamp used.
 */
export function computeStripeSignature(payload: string): {
  signature: string;
  timestamp: number;
} {
  const timestamp = Math.floor(Date.now() / 1000);
  const signedPayload = `${timestamp}.${payload}`;
  const hmac = crypto
    .createHmac('sha256', STRIPE_WEBHOOK_SECRET)
    .update(signedPayload)
    .digest('hex');
  return {
    signature: `t=${timestamp},v1=${hmac}`,
    timestamp,
  };
}

// ---------------------------------------------------------------------------
// Coinbase Commerce Signature
// ---------------------------------------------------------------------------

/**
 * Compute a Coinbase Commerce webhook signature.
 *
 * Coinbase Commerce signs: HMAC-SHA256(secret, raw_body) -> hex.
 * Sent in the X-CC-Webhook-Signature header.
 *
 * @param payload - The raw JSON body string.
 * @returns The hex-encoded HMAC signature.
 */
export function computeCoinbaseSignature(payload: string): string {
  return crypto
    .createHmac('sha256', COINBASE_WEBHOOK_SECRET)
    .update(payload)
    .digest('hex');
}

// ---------------------------------------------------------------------------
// Stripe Event Builders
// ---------------------------------------------------------------------------

/**
 * Build a checkout.session.completed Stripe event.
 *
 * The server handler reads:
 * - event.type
 * - event.data.object.client_reference_id  (wallet_address)
 * - event.data.object.subscription          (stripe subscription ID)
 * - event.data.object.customer              (stripe customer ID)
 */
export function buildStripeCheckoutCompleted(
  walletAddress: string,
  opts?: {
    subscriptionId?: string;
    customerId?: string;
  },
): object {
  return {
    id: `evt_${crypto.randomUUID().replace(/-/g, '')}`,
    type: 'checkout.session.completed',
    data: {
      object: {
        id: `cs_${crypto.randomUUID().replace(/-/g, '')}`,
        client_reference_id: walletAddress,
        subscription: opts?.subscriptionId ?? `sub_${crypto.randomUUID().replace(/-/g, '')}`,
        customer: opts?.customerId ?? `cus_${crypto.randomUUID().replace(/-/g, '')}`,
        mode: 'subscription',
        payment_status: 'paid',
      },
    },
  };
}

/**
 * Build a customer.subscription.deleted Stripe event.
 *
 * The server handler reads:
 * - event.type
 * - event.data.object.id (stripe subscription ID — looked up in subscriptions table)
 */
export function buildStripeSubscriptionDeleted(
  walletAddress: string,
  opts?: { subscriptionId?: string },
): object {
  return {
    id: `evt_${crypto.randomUUID().replace(/-/g, '')}`,
    type: 'customer.subscription.deleted',
    data: {
      object: {
        id: opts?.subscriptionId ?? `sub_${crypto.randomUUID().replace(/-/g, '')}`,
        status: 'canceled',
        // Note: the server handler looks up the wallet via stripe_id in DB,
        // not from the event payload directly.
      },
    },
  };
}

/**
 * Build a customer.subscription.updated Stripe event.
 *
 * The server handler reads:
 * - event.data.object.id (stripe subscription ID)
 * - event.data.object.status (active, past_due, canceled, etc.)
 * - event.data.object.current_period_end (unix timestamp)
 */
export function buildStripeSubscriptionUpdated(
  opts: {
    subscriptionId: string;
    status?: string;
    currentPeriodEnd?: number;
  },
): object {
  return {
    id: `evt_${crypto.randomUUID().replace(/-/g, '')}`,
    type: 'customer.subscription.updated',
    data: {
      object: {
        id: opts.subscriptionId,
        status: opts.status ?? 'active',
        current_period_end: opts.currentPeriodEnd ?? Math.floor(Date.now() / 1000) + 30 * 86400,
      },
    },
  };
}

/**
 * Build an invoice.payment_succeeded Stripe event.
 */
export function buildStripeInvoicePaid(
  opts: {
    subscriptionId: string;
  },
): object {
  return {
    id: `evt_${crypto.randomUUID().replace(/-/g, '')}`,
    type: 'invoice.payment_succeeded',
    data: {
      object: {
        id: `in_${crypto.randomUUID().replace(/-/g, '')}`,
        subscription: opts.subscriptionId,
        status: 'paid',
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Coinbase Commerce Event Builders
// ---------------------------------------------------------------------------

/**
 * Build a charge:confirmed Coinbase Commerce event.
 *
 * The server handler reads:
 * - event.event.type
 * - event.event.data.id (charge ID)
 * - event.event.data.metadata.wallet_address
 */
export function buildCoinbaseChargeConfirmed(
  walletAddress: string,
  opts?: { chargeId?: string },
): object {
  return {
    event: {
      type: 'charge:confirmed',
      data: {
        id: opts?.chargeId ?? crypto.randomUUID(),
        code: opts?.chargeId ?? crypto.randomUUID().slice(0, 8).toUpperCase(),
        metadata: {
          wallet_address: walletAddress,
        },
        timeline: [
          { status: 'NEW', time: new Date().toISOString() },
          { status: 'PENDING', time: new Date().toISOString() },
          { status: 'COMPLETED', time: new Date().toISOString() },
        ],
      },
    },
  };
}

/**
 * Build a charge:failed Coinbase Commerce event.
 */
export function buildCoinbaseChargeFailed(
  walletAddress: string,
  opts?: { chargeId?: string },
): object {
  return {
    event: {
      type: 'charge:failed',
      data: {
        id: opts?.chargeId ?? crypto.randomUUID(),
        code: opts?.chargeId ?? crypto.randomUUID().slice(0, 8).toUpperCase(),
        metadata: {
          wallet_address: walletAddress,
        },
        timeline: [
          { status: 'NEW', time: new Date().toISOString() },
          { status: 'EXPIRED', time: new Date().toISOString() },
        ],
      },
    },
  };
}

/**
 * Build a charge:pending Coinbase Commerce event.
 */
export function buildCoinbaseChargePending(
  walletAddress: string,
  opts?: { chargeId?: string },
): object {
  return {
    event: {
      type: 'charge:pending',
      data: {
        id: opts?.chargeId ?? crypto.randomUUID(),
        code: opts?.chargeId ?? crypto.randomUUID().slice(0, 8).toUpperCase(),
        metadata: {
          wallet_address: walletAddress,
        },
      },
    },
  };
}
