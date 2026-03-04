/**
 * Journey C: Coinbase Commerce Paid Tests (T-C01 through T-C08)
 *
 * Validates the Coinbase Commerce billing flow: charge creation,
 * webhook processing (confirmed, failed), idempotency, expiry stacking,
 * and HMAC-SHA256 signature verification.
 */

import crypto from 'node:crypto';
import type { BillingMockServer } from './mock-billing-server.js';
import type { TestResult } from './journey-a.test.js';

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const TEST_WALLET = '0x71C7656EC7ab88b098defB751B7401B5f6d8976F';
const TEST_WALLET_2 = '0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B';

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

/**
 * Build a Coinbase Commerce webhook payload and compute its HMAC-SHA256 signature.
 */
function buildCoinbaseWebhook(
  secret: string,
  eventType: string,
  chargeId: string,
  walletAddress: string,
): { payload: string; signature: string } {
  const event = {
    event: {
      type: eventType,
      data: {
        id: chargeId,
        code: chargeId,
        metadata: {
          wallet_address: walletAddress,
        },
      },
    },
  };
  const payload = JSON.stringify(event);
  const signature = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  return { payload, signature };
}

/**
 * Send a signed Coinbase Commerce webhook to the mock server.
 */
async function sendCoinbaseWebhook(
  baseUrl: string,
  secret: string,
  eventType: string,
  chargeId: string,
  walletAddress: string,
): Promise<{ status: number; body: Record<string, unknown> }> {
  const { payload, signature } = buildCoinbaseWebhook(
    secret, eventType, chargeId, walletAddress,
  );
  const res = await fetch(`${baseUrl}/v1/billing/webhook/coinbase`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CC-Webhook-Signature': signature,
    },
    body: payload,
  });
  const json = await res.json();
  return { status: res.status, body: json as Record<string, unknown> };
}

// ---------------------------------------------------------------------------
// Test definitions
// ---------------------------------------------------------------------------

export async function runJourneyC(server: BillingMockServer): Promise<TestResult[]> {
  const results: TestResult[] = [];

  // =========================================================================
  // T-C01: Create Coinbase Commerce charge -> returns hosted URL
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C01';
    const name = 'Create Coinbase Commerce charge -> returns hosted URL';
    try {
      server.reset();

      const result = await post(server.url, '/v1/billing/checkout/crypto', {
        wallet_address: TEST_WALLET,
        tier: 'pro',
      });

      if (!result.body.success) {
        throw new Error(`Crypto checkout failed: ${JSON.stringify(result.body)}`);
      }

      const checkoutUrl = result.body.checkout_url as string;
      if (!checkoutUrl) {
        throw new Error('Missing checkout_url in response');
      }

      if (!checkoutUrl.startsWith('https://commerce.coinbase.com/charges/')) {
        throw new Error(`Unexpected checkout URL format: ${checkoutUrl}`);
      }

      if (!result.body.charge_code) {
        throw new Error('Missing charge_code in response');
      }

      results.push({
        id, name, passed: true,
        message: `Charge URL: ${checkoutUrl}`,
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
  // T-C02: Coinbase webhook charge:confirmed -> activates pro for 30 days
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C02';
    const name = 'Coinbase webhook charge:confirmed -> activates pro for 30 days';
    try {
      server.reset();

      const chargeId = `charge_${crypto.randomBytes(12).toString('hex')}`;

      const result = await sendCoinbaseWebhook(
        server.url,
        server.webhookSecret,
        'charge:confirmed',
        chargeId,
        TEST_WALLET,
      );

      if (!result.body.success) {
        throw new Error(`Webhook failed: ${JSON.stringify(result.body)}`);
      }

      if (result.body.event_type !== 'charge:confirmed') {
        throw new Error(`Expected event_type=charge:confirmed, got ${result.body.event_type}`);
      }

      if (result.body.status !== 'activated') {
        throw new Error(`Expected status=activated, got ${result.body.status}`);
      }

      // Verify subscription was activated
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.tier !== 'pro') {
        throw new Error(`Expected tier=pro, got ${sub.tier}`);
      }
      if (sub.source !== 'coinbase_commerce') {
        throw new Error(`Expected source=coinbase_commerce, got ${sub.source}`);
      }
      if (sub.coinbase_id !== chargeId) {
        throw new Error(`Expected coinbase_id=${chargeId}, got ${sub.coinbase_id}`);
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
        message: `Pro activated via Coinbase: charge=${chargeId}, expires=${sub.expires_at.toISOString()}`,
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
  // T-C03: Coinbase pro user stores memories -> succeeds
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C03';
    const name = 'Coinbase pro user stores memories -> succeeds';
    try {
      // Wallet is pro from T-C02. Sponsor should succeed with tier=pro.
      const result = await post(server.url, '/v1/relay/sponsor', {
        wallet_address: TEST_WALLET,
      });

      if (!result.body.success) {
        throw new Error(`Pro store failed: ${JSON.stringify(result.body)}`);
      }

      if (result.body.tier !== 'pro') {
        throw new Error(`Expected tier=pro, got ${result.body.tier}`);
      }

      // Free counter should not be incremented
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.free_writes_used !== 0) {
        throw new Error(
          `Pro tier should not increment free counter. Expected 0, got ${sub.free_writes_used}`,
        );
      }

      results.push({
        id, name, passed: true,
        message: 'Coinbase pro user stored memory without incrementing free counter',
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
  // T-C04: Coinbase subscription expires after 30 days -> falls to free tier
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C04';
    const name = 'Coinbase subscription expires after 30 days -> falls to free tier';
    try {
      server.reset();

      // Set up a Coinbase pro subscription that expired yesterday
      const pastDate = new Date(Date.now() - 24 * 60 * 60 * 1000);
      server.setSubscription(TEST_WALLET, {
        tier: 'pro',
        source: 'coinbase_commerce',
        coinbase_id: `charge_expired_${crypto.randomBytes(8).toString('hex')}`,
        expires_at: pastDate,
        free_writes_used: 0,
        free_writes_limit: 100,
        free_writes_reset_at: new Date(),
      });

      // Check billing status -- should report as free
      const statusResult = await get(
        server.url,
        `/v1/billing/status?wallet_address=${TEST_WALLET}`,
      );

      if (statusResult.body.tier !== 'free') {
        throw new Error(`Expected effective tier=free, got ${statusResult.body.tier}`);
      }

      // Sponsor request should use free tier logic
      const sponsorResult = await post(server.url, '/v1/relay/sponsor', {
        wallet_address: TEST_WALLET,
      });

      if (!sponsorResult.body.success) {
        throw new Error(`Sponsor should succeed as free tier: ${JSON.stringify(sponsorResult.body)}`);
      }

      // Verify free tier behavior (counter incremented)
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.free_writes_used !== 1) {
        throw new Error(`Expected free_writes_used=1 (free tier), got ${sub.free_writes_used}`);
      }

      results.push({
        id, name, passed: true,
        message: 'Expired Coinbase pro falls to free tier correctly',
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
  // T-C05: Coinbase charge extension (stacking) -- extends from current expiry
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C05';
    const name = 'Coinbase charge extension (stacking) -- extends from current expiry';
    try {
      server.reset();

      // Set up a pro subscription with 20 days remaining
      const twentyDaysFromNow = new Date(Date.now() + 20 * 24 * 60 * 60 * 1000);
      server.setSubscription(TEST_WALLET, {
        tier: 'pro',
        source: 'coinbase_commerce',
        coinbase_id: `charge_first_${crypto.randomBytes(8).toString('hex')}`,
        expires_at: twentyDaysFromNow,
      });

      const originalExpiry = twentyDaysFromNow.getTime();

      // Send a second charge:confirmed webhook (should stack)
      const newChargeId = `charge_stack_${crypto.randomBytes(8).toString('hex')}`;
      const result = await sendCoinbaseWebhook(
        server.url,
        server.webhookSecret,
        'charge:confirmed',
        newChargeId,
        TEST_WALLET,
      );

      if (!result.body.success) {
        throw new Error(`Stacking webhook failed: ${JSON.stringify(result.body)}`);
      }

      // Verify new expiry is ~50 days from now (20 remaining + 30 new)
      const sub = server.getSubscription(TEST_WALLET);
      if (!sub.expires_at) {
        throw new Error('expires_at should be set after stacking');
      }

      // The new expiry should be originalExpiry + 30 days
      const thirtyDaysMs = 30 * 24 * 60 * 60 * 1000;
      const expectedExpiry = originalExpiry + thirtyDaysMs;
      const delta = Math.abs(sub.expires_at.getTime() - expectedExpiry);

      if (delta > 60_000) { // 1 minute tolerance
        throw new Error(
          `Stacked expiry should be original + 30 days. ` +
          `Expected ~${new Date(expectedExpiry).toISOString()}, ` +
          `got ${sub.expires_at.toISOString()} (delta=${delta}ms)`,
        );
      }

      // Verify it stacked from the current expiry, not from now
      const fiftyDaysMs = 50 * 24 * 60 * 60 * 1000;
      const fromNowDelta = sub.expires_at.getTime() - Date.now();
      if (Math.abs(fromNowDelta - fiftyDaysMs) > 60_000) {
        // Should be ~50 days from now (20 remaining + 30 new)
        throw new Error(
          `Total remaining should be ~50 days, got ~${Math.round(fromNowDelta / (24 * 60 * 60 * 1000))} days`,
        );
      }

      results.push({
        id, name, passed: true,
        message: `Stacked: original expiry + 30d = ${sub.expires_at.toISOString()}`,
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
  // T-C06: Coinbase webhook charge:failed -> no subscription change
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C06';
    const name = 'Coinbase webhook charge:failed -> no subscription change';
    try {
      server.reset();

      // Set up a free tier user
      server.setSubscription(TEST_WALLET, {
        tier: 'free',
        free_writes_used: 10,
        free_writes_limit: 100,
      });

      const beforeSub = server.getSubscription(TEST_WALLET);
      const tierBefore = beforeSub.tier;
      const writesBefore = beforeSub.free_writes_used;

      // Send charge:failed webhook
      const chargeId = `charge_failed_${crypto.randomBytes(8).toString('hex')}`;
      const result = await sendCoinbaseWebhook(
        server.url,
        server.webhookSecret,
        'charge:failed',
        chargeId,
        TEST_WALLET,
      );

      if (!result.body.success) {
        throw new Error(`Webhook should succeed (200 OK): ${JSON.stringify(result.body)}`);
      }

      if (result.body.status !== 'failed') {
        throw new Error(`Expected status=failed, got ${result.body.status}`);
      }

      // Verify NO subscription change
      const afterSub = server.getSubscription(TEST_WALLET);
      if (afterSub.tier !== tierBefore) {
        throw new Error(`Tier should not change on failed charge. Before=${tierBefore}, after=${afterSub.tier}`);
      }
      if (afterSub.free_writes_used !== writesBefore) {
        throw new Error(
          `Writes counter should not change. Before=${writesBefore}, after=${afterSub.free_writes_used}`,
        );
      }
      if (afterSub.coinbase_id !== null) {
        throw new Error(`coinbase_id should remain null on failed charge, got ${afterSub.coinbase_id}`);
      }

      results.push({
        id, name, passed: true,
        message: 'Failed charge did not modify subscription',
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
  // T-C07: Coinbase webhook idempotency (duplicate charge_id -> no double activation)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C07';
    const name = 'Coinbase webhook idempotency (duplicate charge_id)';
    try {
      server.reset();

      const chargeId = `charge_idempotent_${crypto.randomBytes(8).toString('hex')}`;

      // First webhook: activate pro
      const result1 = await sendCoinbaseWebhook(
        server.url,
        server.webhookSecret,
        'charge:confirmed',
        chargeId,
        TEST_WALLET,
      );

      if (!result1.body.success) {
        throw new Error(`First webhook failed: ${JSON.stringify(result1.body)}`);
      }
      if (result1.body.status !== 'activated') {
        throw new Error(`First webhook should activate, got ${result1.body.status}`);
      }

      // Capture the state after first activation
      const afterFirst = server.getSubscription(TEST_WALLET);
      const firstExpiry = afterFirst.expires_at?.getTime();
      if (!firstExpiry) {
        throw new Error('expires_at should be set after first activation');
      }

      // Second webhook: same charge_id -> should be idempotent (no double activation)
      const result2 = await sendCoinbaseWebhook(
        server.url,
        server.webhookSecret,
        'charge:confirmed',
        chargeId,
        TEST_WALLET,
      );

      if (!result2.body.success) {
        throw new Error(`Second webhook failed: ${JSON.stringify(result2.body)}`);
      }
      if (result2.body.status !== 'already_processed') {
        throw new Error(`Second webhook should be already_processed, got ${result2.body.status}`);
      }

      // Verify expiry did NOT change (no stacking on duplicate)
      const afterSecond = server.getSubscription(TEST_WALLET);
      if (!afterSecond.expires_at) {
        throw new Error('expires_at should still be set');
      }

      const expiryDelta = Math.abs(afterSecond.expires_at.getTime() - firstExpiry);
      if (expiryDelta > 1000) { // 1 second tolerance
        throw new Error(
          `Duplicate charge should not change expiry. ` +
          `Before=${new Date(firstExpiry).toISOString()}, ` +
          `after=${afterSecond.expires_at.toISOString()} (delta=${expiryDelta}ms)`,
        );
      }

      // Verify the charge was tracked in processed IDs
      const processedIds = server.getProcessedChargeIds();
      if (!processedIds.has(chargeId)) {
        throw new Error(`charge_id should be in processed set`);
      }

      results.push({
        id, name, passed: true,
        message: `Idempotent: duplicate charge ${chargeId} did not re-activate`,
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
  // T-C08: Coinbase webhook invalid signature -> rejected with 400
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-C08';
    const name = 'Coinbase webhook invalid signature -> rejected with 400';
    try {
      server.reset();

      const chargeId = `charge_badsig_${crypto.randomBytes(8).toString('hex')}`;

      // Build a valid-looking payload but sign it with the wrong secret
      const event = {
        event: {
          type: 'charge:confirmed',
          data: {
            id: chargeId,
            code: chargeId,
            metadata: {
              wallet_address: TEST_WALLET,
            },
          },
        },
      };
      const payload = JSON.stringify(event);

      // Sign with a WRONG secret
      const wrongSignature = crypto
        .createHmac('sha256', 'this-is-the-wrong-secret')
        .update(payload)
        .digest('hex');

      const res = await fetch(`${server.url}/v1/billing/webhook/coinbase`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CC-Webhook-Signature': wrongSignature,
        },
        body: payload,
      });

      const json = await res.json() as Record<string, unknown>;

      if (res.status !== 400) {
        throw new Error(`Expected HTTP 400, got ${res.status}`);
      }

      if (json.success !== false) {
        throw new Error(`Expected success=false for invalid signature, got ${json.success}`);
      }

      if (json.error_code !== 'INVALID_SIGNATURE') {
        throw new Error(`Expected error_code=INVALID_SIGNATURE, got ${json.error_code}`);
      }

      // Verify NO subscription was created
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.tier !== 'free') {
        throw new Error(`Invalid signature should not activate pro. Got tier=${sub.tier}`);
      }
      if (sub.coinbase_id !== null) {
        throw new Error(`coinbase_id should be null after invalid sig, got ${sub.coinbase_id}`);
      }

      // Also test with completely missing signature header
      const noSigRes = await fetch(`${server.url}/v1/billing/webhook/coinbase`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
      });

      if (noSigRes.status !== 400) {
        throw new Error(`Missing signature should return 400, got ${noSigRes.status}`);
      }

      results.push({
        id, name, passed: true,
        message: 'Invalid and missing signatures correctly rejected with 400',
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
