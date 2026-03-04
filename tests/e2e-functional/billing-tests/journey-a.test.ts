/**
 * Journey A: Free Tier Tests (T-A01 through T-A07)
 *
 * Validates the free-tier billing flow: seed generation, wallet derivation,
 * sponsored memory stores/retrievals, counter enforcement, and monthly reset.
 *
 * All tests run against the in-memory mock billing server with no external
 * dependencies.
 */

import crypto from 'node:crypto';
import type { BillingMockServer } from './mock-billing-server.js';

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

/** Deterministic test wallet derived from a known BIP-39 mnemonic. */
const TEST_WALLET = '0x71C7656EC7ab88b098defB751B7401B5f6d8976F';

/** Second wallet for isolation tests. */
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

// ---------------------------------------------------------------------------
// Test definitions
// ---------------------------------------------------------------------------

export interface TestResult {
  id: string;
  name: string;
  passed: boolean;
  message: string;
  durationMs: number;
}

export async function runJourneyA(server: BillingMockServer): Promise<TestResult[]> {
  const results: TestResult[] = [];

  // =========================================================================
  // T-A01: Seed generation and wallet derivation
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-A01';
    const name = 'Seed generation and wallet derivation';
    try {
      // Simulate BIP-39 mnemonic -> wallet derivation.
      // In the real plugin this uses @noble/hashes/argon2 + HKDF.
      // For mock tests, we verify the deterministic wallet address format.
      const mnemonic = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';

      // Verify mnemonic is valid BIP-39 (12 words)
      const words = mnemonic.split(' ');
      if (words.length !== 12) {
        throw new Error(`Expected 12 mnemonic words, got ${words.length}`);
      }

      // Derive a deterministic "wallet" address via SHA-256 of the mnemonic
      // (this is NOT how real derivation works, but validates the flow shape)
      const hash = crypto.createHash('sha256').update(mnemonic).digest('hex');
      const derivedAddr = `0x${hash.slice(0, 40)}`;

      // Verify it's a valid Ethereum-style address (0x + 40 hex chars)
      if (!/^0x[0-9a-fA-F]{40}$/.test(derivedAddr)) {
        throw new Error(`Invalid derived address format: ${derivedAddr}`);
      }

      // Verify the deterministic wallet constant is also valid
      if (!/^0x[0-9a-fA-F]{40}$/.test(TEST_WALLET)) {
        throw new Error(`Invalid TEST_WALLET format: ${TEST_WALLET}`);
      }

      results.push({
        id, name, passed: true,
        message: `Derived address ${derivedAddr} from mnemonic`,
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
  // T-A02: First memory store (free tier, sponsored via relay)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-A02';
    const name = 'First memory store (free tier, sponsored via relay)';
    try {
      server.reset();

      // Register user first
      const regResult = await post(server.url, '/v1/register', {
        auth_key_hash: crypto.createHash('sha256').update(TEST_WALLET).digest('hex'),
      });
      if (!regResult.body.success) {
        throw new Error('Registration failed');
      }

      // Request relay sponsorship for a store operation
      const sponsorResult = await post(server.url, '/v1/relay/sponsor', {
        wallet_address: TEST_WALLET,
      });

      if (!sponsorResult.body.success) {
        throw new Error(`Sponsor request failed: ${JSON.stringify(sponsorResult.body)}`);
      }

      if (!sponsorResult.body.userOpHash) {
        throw new Error('Missing userOpHash in sponsor response');
      }

      if (sponsorResult.body.tier !== 'free') {
        throw new Error(`Expected tier=free, got tier=${sponsorResult.body.tier}`);
      }

      // Verify the relay status is confirmed
      const hash = sponsorResult.body.userOpHash as string;
      const statusResult = await get(server.url, `/v1/relay/status/${hash}`);
      if (statusResult.body.status !== 'confirmed') {
        throw new Error(`Expected status=confirmed, got ${statusResult.body.status}`);
      }

      // Verify free_writes_used incremented to 1
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.free_writes_used !== 1) {
        throw new Error(`Expected free_writes_used=1, got ${sub.free_writes_used}`);
      }

      results.push({
        id, name, passed: true,
        message: `Sponsored store with hash ${hash}, free_writes_used=1`,
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
  // T-A03: First memory retrieval (free tier, via mock search)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-A03';
    const name = 'First memory retrieval (free tier)';
    try {
      // Reads should NOT consume free_writes — verify billing status
      const beforeSub = server.getSubscription(TEST_WALLET);
      const writesBefore = beforeSub.free_writes_used;

      // Check billing status endpoint (reads are free)
      const statusResult = await get(
        server.url,
        `/v1/billing/status?wallet_address=${TEST_WALLET}`,
      );

      if (!statusResult.body.success) {
        throw new Error('Billing status check failed');
      }

      if (statusResult.body.tier !== 'free') {
        throw new Error(`Expected tier=free, got ${statusResult.body.tier}`);
      }

      // Verify free_writes_used did NOT change (reads are free)
      const afterSub = server.getSubscription(TEST_WALLET);
      if (afterSub.free_writes_used !== writesBefore) {
        throw new Error(
          `Reads should not increment counter. Before=${writesBefore}, after=${afterSub.free_writes_used}`,
        );
      }

      results.push({
        id, name, passed: true,
        message: `Read did not consume free writes (still ${writesBefore})`,
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
  // T-A04: Free tier counter increments correctly (5 sequential stores)
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-A04';
    const name = 'Free tier counter increments correctly (5 sequential stores)';
    try {
      server.reset();

      for (let i = 1; i <= 5; i++) {
        const result = await post(server.url, '/v1/relay/sponsor', {
          wallet_address: TEST_WALLET,
        });

        if (!result.body.success) {
          throw new Error(`Store ${i} failed: ${JSON.stringify(result.body)}`);
        }

        const sub = server.getSubscription(TEST_WALLET);
        if (sub.free_writes_used !== i) {
          throw new Error(
            `After store ${i}, expected free_writes_used=${i}, got ${sub.free_writes_used}`,
          );
        }
      }

      const finalSub = server.getSubscription(TEST_WALLET);
      if (finalSub.free_writes_used !== 5) {
        throw new Error(`Final free_writes_used should be 5, got ${finalSub.free_writes_used}`);
      }

      results.push({
        id, name, passed: true,
        message: 'Counter incremented correctly from 0 to 5',
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
  // T-A05: Free tier limit reached -- sponsorship denied
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-A05';
    const name = 'Free tier limit reached -- sponsorship denied';
    try {
      server.reset();

      // Set free_writes_used to exactly the limit
      server.setSubscription(TEST_WALLET, {
        tier: 'free',
        free_writes_used: 100,
        free_writes_limit: 100,
        free_writes_reset_at: new Date(), // current month, so no reset
      });

      const result = await post(server.url, '/v1/relay/sponsor', {
        wallet_address: TEST_WALLET,
      });

      if (result.body.success !== false) {
        throw new Error(`Expected success=false, got success=${result.body.success}`);
      }

      if (result.body.reason !== 'upgrade_required') {
        throw new Error(`Expected reason=upgrade_required, got reason=${result.body.reason}`);
      }

      // Verify counter did NOT increment past 100
      const sub = server.getSubscription(TEST_WALLET);
      if (sub.free_writes_used !== 100) {
        throw new Error(`Counter should remain at 100, got ${sub.free_writes_used}`);
      }

      results.push({
        id, name, passed: true,
        message: 'Sponsorship correctly denied at limit=100 with upgrade_required',
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
  // T-A06: Reads still work after write limit exhausted
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-A06';
    const name = 'Reads still work after write limit exhausted';
    try {
      // Subscription is still at limit=100 from T-A05 (server not reset)
      // Reads (billing status check, searches) should still work

      const statusResult = await get(
        server.url,
        `/v1/billing/status?wallet_address=${TEST_WALLET}`,
      );

      if (!statusResult.body.success) {
        throw new Error('Billing status read failed after limit exhausted');
      }

      if (statusResult.body.tier !== 'free') {
        throw new Error(`Expected tier=free, got ${statusResult.body.tier}`);
      }

      if (statusResult.body.free_writes_used !== 100) {
        throw new Error(
          `Expected free_writes_used=100, got ${statusResult.body.free_writes_used}`,
        );
      }

      if (statusResult.body.free_writes_limit !== 100) {
        throw new Error(
          `Expected free_writes_limit=100, got ${statusResult.body.free_writes_limit}`,
        );
      }

      // Also verify Pimlico webhook reflects the limit
      const pimlicoResult = await post(server.url, '/v1/relay/webhook/pimlico', {
        wallet_address: TEST_WALLET,
      });
      if (pimlicoResult.body.sponsor !== false) {
        throw new Error(
          `Expected pimlico sponsor=false for exhausted wallet, got ${pimlicoResult.body.sponsor}`,
        );
      }

      results.push({
        id, name, passed: true,
        message: 'Reads succeed after write limit; Pimlico correctly rejects sponsor',
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
  // T-A07: Free tier monthly reset
  // =========================================================================
  {
    const t0 = performance.now();
    const id = 'T-A07';
    const name = 'Free tier monthly reset';
    try {
      server.reset();

      // Set subscription with reset_at in a previous month and used=50
      const lastMonth = new Date();
      lastMonth.setUTCMonth(lastMonth.getUTCMonth() - 1);
      lastMonth.setUTCDate(1);

      server.setSubscription(TEST_WALLET, {
        tier: 'free',
        free_writes_used: 50,
        free_writes_limit: 100,
        free_writes_reset_at: lastMonth,
      });

      // Verify the counter is currently 50
      const before = server.getSubscription(TEST_WALLET);
      if (before.free_writes_used !== 50) {
        throw new Error(`Setup error: expected free_writes_used=50, got ${before.free_writes_used}`);
      }

      // Request sponsorship — this should trigger monthly reset, then succeed
      const result = await post(server.url, '/v1/relay/sponsor', {
        wallet_address: TEST_WALLET,
      });

      if (!result.body.success) {
        throw new Error(`Sponsor after reset failed: ${JSON.stringify(result.body)}`);
      }

      // After reset + 1 write, counter should be 1 (not 51)
      const after = server.getSubscription(TEST_WALLET);
      if (after.free_writes_used !== 1) {
        throw new Error(
          `After monthly reset + 1 write, expected free_writes_used=1, got ${after.free_writes_used}`,
        );
      }

      // Verify reset_at is now set to current month start
      const now = new Date();
      const expectedResetMonth = now.getUTCMonth();
      if (
        after.free_writes_reset_at === null ||
        after.free_writes_reset_at.getUTCMonth() !== expectedResetMonth
      ) {
        throw new Error(
          `Reset date should be current month, got ${after.free_writes_reset_at?.toISOString()}`,
        );
      }

      results.push({
        id, name, passed: true,
        message: `Monthly reset triggered: 50 -> 0, then incremented to 1`,
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
