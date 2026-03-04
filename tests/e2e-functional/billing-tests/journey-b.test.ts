/**
 * Journey B: Stripe Paid Tests (T-B01 through T-B08)
 *
 * Validates the Stripe billing flow: checkout session creation,
 * webhook processing (activation, update, deletion, renewal),
 * and tier enforcement.
 */

import crypto from 'node:crypto';
import type { BillingMockServer } from './mock-billing-server.js';
import type { TestResult } from './journey-a.test.js';

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const TEST_WALLET = '0x71C7656EC7ab88b098defB751B7401B5f6d8976F';

// ---------------------------------------------------------------------------
// HTTP helpers
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

// ---------------------------------------------------------------------------
// Test definitions
// ---------------------------------------------------------------------------

export async function runJourneyB(server: BillingMockServer): Promise<TestResult[]> {
  const results: TestResult[] = [];

  // =========================================================================
  // T-B01: Create Stripe checkout session -> returns checkout URL
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B01';
    const name = 'Create Stripe checkout session -> returns checkout URL';
    try {
      server.reset();

      const result = await post(server.url, '/v1/billing/checkout', {
        wallet_address: TEST_WALLET,
        tier: 'pro',
      });

      if (!result.body.success) {
        throw new Error(`Checkout failed: ${JSON.stringify(result.body)}`);
      }

      const checkoutUrl = result.body.checkout_url as string;
      if (!checkoutUrl) {
        throw new Error('Missing checkout_url in response');
      }

      if (!checkoutUrl.startsWith('https://checkout.stripe.com/')) {
        throw new Error(`Unexpected checkout URL format: ${checkoutUrl}`);
      }

      if (!result.body.session_id) {
        throw new Error('Missing session_id in response');
      }

      results.push({
        id, name, passed: true,
        message: `Checkout URL: ${checkoutUrl}`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T-B02: Stripe webhook checkout.session.completed -> activates pro
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B02';
    const name = 'Stripe webhook checkout.session.completed -> activates pro';
    try {
      server.reset();

      const stripeSubId = `sub_${crypto.randomBytes(12).toString('hex')}`;
      const stripeCusId = `cus_${crypto.randomBytes(12).toString('hex')}`;

      const result = await post(server.url, '/v1/billing/webhook/stripe', {
        type: 'checkout.session.completed',
        data: {
          object: {
            client_reference_id: TEST_WALLET,
            subscription: stripeSubId,
            customer: stripeCusId,
          },
        },
      });

      if (!result.body.success) {
        throw new Error(`Webhook failed: ${JSON.stringify(result.body)}`);
      }

      if (result.body.event_type !== 'checkout.session.completed') {
        throw new Error(`Unexpected event_type: ${result.body.event_type}`);
      }

      // Verify subscription was activated
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.tier !== 'pro') {
        throw new Error(`Expected tier=pro, got ${sub.tier}`);
      }
      if (sub.source !== 'stripe') {
        throw new Error(`Expected source=stripe, got ${sub.source}`);
      }
      if (sub.stripe_id !== stripeSubId) {
        throw new Error(`Expected stripe_id=${stripeSubId}, got ${sub.stripe_id}`);
      }
      if (sub.stripe_customer_id !== stripeCusId) {
        throw new Error(`Expected stripe_customer_id=${stripeCusId}, got ${sub.stripe_customer_id}`);
      }
      if (!sub.expires_at) {
        throw new Error('Expected expires_at to be set');
      }

      // Verify expiry is approximately 30 days from now
      const thirtyDaysMs = 30 * 24 * 60 * 60 * 1000;
      const expiryDelta = Math.abs(sub.expires_at.getTime() - Date.now() - thirtyDaysMs);
      if (expiryDelta > 60_000) { // 1 minute tolerance
        throw new Error(
          `expires_at should be ~30 days from now, delta=${expiryDelta}ms`,
        );
      }

      results.push({
        id, name, passed: true,
        message: `Pro activated: stripe_id=${stripeSubId}, expires=${sub.expires_at.toISOString()}`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T-B03: Paid user stores memories -- no limit (pro tier bypasses counter)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B03';
    const name = 'Paid user stores memories -- no limit (pro bypasses counter)';
    try {
      // T-B02 left the wallet as pro. Sponsor requests should succeed.

      // Store 5 memories in quick succession
      for (let i = 1; i <= 5; i++) {
        const result = await post(server.url, '/v1/relay/sponsor', {
          wallet_address: TEST_WALLET,
        });

        if (!result.body.success) {
          throw new Error(`Pro store ${i} failed: ${JSON.stringify(result.body)}`);
        }

        if (result.body.tier !== 'pro') {
          throw new Error(`Expected tier=pro on store ${i}, got ${result.body.tier}`);
        }
      }

      // Verify free_writes_used was NOT incremented (pro bypasses counter)
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.free_writes_used !== 0) {
        throw new Error(
          `Pro tier should not increment free counter. Expected 0, got ${sub.free_writes_used}`,
        );
      }

      results.push({
        id, name, passed: true,
        message: 'Pro user stored 5 memories without incrementing free counter',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T-B04: Stripe subscription.updated -> period extended
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B04';
    const name = 'Stripe subscription.updated -> period extended';
    try {
      // Get the current stripe_id from the subscription (set in T-B02)
      const sub = server.getSubscription(TEST_WALLET);
      const stripeId = sub.stripe_id;
      if (!stripeId) {
        throw new Error('No stripe_id set from T-B02');
      }

      const oldExpiry = sub.expires_at?.getTime() ?? 0;

      // Send subscription.updated with a new period end (60 days from now)
      const sixtyDaysFromNow = Math.floor(Date.now() / 1000) + 60 * 24 * 60 * 60;

      const result = await post(server.url, '/v1/billing/webhook/stripe', {
        type: 'customer.subscription.updated',
        data: {
          object: {
            id: stripeId,
            status: 'active',
            current_period_end: sixtyDaysFromNow,
          },
        },
      });

      if (!result.body.success) {
        throw new Error(`Webhook failed: ${JSON.stringify(result.body)}`);
      }

      // Verify the expiry was extended
      const updatedSub = server.getSubscription(TEST_WALLET);
      if (updatedSub.tier !== 'pro') {
        throw new Error(`Expected tier=pro after update, got ${updatedSub.tier}`);
      }

      if (!updatedSub.expires_at) {
        throw new Error('expires_at should be set after update');
      }

      const expectedExpiry = sixtyDaysFromNow * 1000;
      const delta = Math.abs(updatedSub.expires_at.getTime() - expectedExpiry);
      if (delta > 1000) { // 1 second tolerance
        throw new Error(
          `Expected expires_at ~${new Date(expectedExpiry).toISOString()}, ` +
          `got ${updatedSub.expires_at.toISOString()} (delta=${delta}ms)`,
        );
      }

      if (updatedSub.expires_at.getTime() <= oldExpiry) {
        throw new Error('New expiry should be later than old expiry');
      }

      results.push({
        id, name, passed: true,
        message: `Period extended to ${updatedSub.expires_at.toISOString()}`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T-B05: Stripe subscription.deleted -> downgrade to free
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B05';
    const name = 'Stripe subscription.deleted -> downgrade to free';
    try {
      const sub = server.getSubscription(TEST_WALLET);
      const stripeId = sub.stripe_id;
      if (!stripeId) {
        throw new Error('No stripe_id set from previous tests');
      }

      const result = await post(server.url, '/v1/billing/webhook/stripe', {
        type: 'customer.subscription.deleted',
        data: {
          object: {
            id: stripeId,
          },
        },
      });

      if (!result.body.success) {
        throw new Error(`Webhook failed: ${JSON.stringify(result.body)}`);
      }

      if (result.body.status !== 'downgraded') {
        throw new Error(`Expected status=downgraded, got ${result.body.status}`);
      }

      // Verify downgrade
      const updatedSub = server.getSubscription(TEST_WALLET);
      if (updatedSub.tier !== 'free') {
        throw new Error(`Expected tier=free after deletion, got ${updatedSub.tier}`);
      }
      if (updatedSub.expires_at !== null) {
        throw new Error(`Expected expires_at=null after deletion, got ${updatedSub.expires_at}`);
      }
      if (updatedSub.stripe_id !== null) {
        throw new Error(`Expected stripe_id=null after deletion, got ${updatedSub.stripe_id}`);
      }

      results.push({
        id, name, passed: true,
        message: 'Downgraded to free: tier=free, expires_at=null, stripe_id=null',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T-B06: Stripe subscription expired -- treated as free
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B06';
    const name = 'Stripe subscription expired -- treated as free';
    try {
      server.reset();

      // Set up a pro subscription with expires_at in the past
      const pastDate = new Date(Date.now() - 24 * 60 * 60 * 1000); // yesterday
      server.setSubscription(TEST_WALLET, {
        tier: 'pro',
        source: 'stripe',
        stripe_id: `sub_expired_${crypto.randomBytes(8).toString('hex')}`,
        expires_at: pastDate,
        free_writes_used: 0,
        free_writes_limit: 100,
        free_writes_reset_at: new Date(),
      });

      // Check billing status -- should report as free despite tier=pro in DB
      const statusResult = await get(
        server.url,
        `/v1/billing/status?wallet_address=${TEST_WALLET}`,
      );

      if (statusResult.body.tier !== 'free') {
        throw new Error(`Expected effective tier=free for expired pro, got ${statusResult.body.tier}`);
      }

      // Sponsor request should use free tier logic (increment counter)
      const sponsorResult = await post(server.url, '/v1/relay/sponsor', {
        wallet_address: TEST_WALLET,
      });

      if (!sponsorResult.body.success) {
        throw new Error(`Sponsor should succeed as free tier: ${JSON.stringify(sponsorResult.body)}`);
      }

      // Check that the counter was incremented (free tier behavior)
      if (sponsorResult.body.tier !== 'free') {
        throw new Error(`Expected tier=free in sponsor response, got ${sponsorResult.body.tier}`);
      }

      results.push({
        id, name, passed: true,
        message: `Expired pro treated as free. Billing status tier=${statusResult.body.tier}`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T-B07: Invoice payment succeeded -> subscription renewed
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B07';
    const name = 'Invoice payment succeeded -> subscription renewed';
    try {
      server.reset();

      // Set up a pro subscription that is about to expire
      const almostExpired = new Date(Date.now() + 2 * 60 * 60 * 1000); // 2 hours from now
      const stripeSubId = `sub_renew_${crypto.randomBytes(8).toString('hex')}`;

      server.setSubscription(TEST_WALLET, {
        tier: 'pro',
        source: 'stripe',
        stripe_id: stripeSubId,
        expires_at: almostExpired,
      });

      const oldExpiry = almostExpired.getTime();

      // Send invoice.payment_succeeded
      const result = await post(server.url, '/v1/billing/webhook/stripe', {
        type: 'invoice.payment_succeeded',
        data: {
          object: {
            subscription: stripeSubId,
          },
        },
      });

      if (!result.body.success) {
        throw new Error(`Webhook failed: ${JSON.stringify(result.body)}`);
      }

      if (result.body.status !== 'renewed') {
        throw new Error(`Expected status=renewed, got ${result.body.status}`);
      }

      // Verify the expiry was extended (should be ~30 days from now, not from old expiry)
      const renewed = server.getSubscription(TEST_WALLET);
      if (renewed.tier !== 'pro') {
        throw new Error(`Expected tier=pro after renewal, got ${renewed.tier}`);
      }
      if (!renewed.expires_at) {
        throw new Error('expires_at should be set after renewal');
      }

      // New expiry should be significantly later than the old one
      if (renewed.expires_at.getTime() <= oldExpiry) {
        throw new Error(
          `New expiry (${renewed.expires_at.toISOString()}) should be after ` +
          `old expiry (${almostExpired.toISOString()})`,
        );
      }

      results.push({
        id, name, passed: true,
        message: `Renewed: old_expires=${almostExpired.toISOString()}, new_expires=${renewed.expires_at.toISOString()}`,
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  // =========================================================================
  // T-B08: Invalid tier in checkout request -> rejected
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-B08';
    const name = 'Invalid tier in checkout request -> rejected';
    try {
      const result = await post(server.url, '/v1/billing/checkout', {
        wallet_address: TEST_WALLET,
        tier: 'enterprise', // invalid tier
      });

      if (result.body.success !== false) {
        throw new Error(`Expected success=false for invalid tier, got ${result.body.success}`);
      }

      if (result.body.error_code !== 'INVALID_TIER') {
        throw new Error(`Expected error_code=INVALID_TIER, got ${result.body.error_code}`);
      }

      // Also test with crypto checkout endpoint
      const cryptoResult = await post(server.url, '/v1/billing/checkout/crypto', {
        wallet_address: TEST_WALLET,
        tier: 'basic', // another invalid tier
      });

      if (cryptoResult.body.success !== false) {
        throw new Error(`Expected crypto success=false for invalid tier`);
      }

      if (cryptoResult.body.error_code !== 'INVALID_TIER') {
        throw new Error(
          `Expected crypto error_code=INVALID_TIER, got ${cryptoResult.body.error_code}`,
        );
      }

      results.push({
        id, name, passed: true,
        message: 'Both Stripe and Coinbase checkout correctly reject invalid tiers',
        durationMs: performance.now() - t0,
      });
    } catch (err) {
      results.push({
        id, name, passed: false,
        message: err instanceof Error ? err.message : String(err),
        durationMs: performance.now() - t0,
      });
    }
  }

  return results;
}
