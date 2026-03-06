/**
 * Journey 6: Coinbase Commerce + Monthly Reset
 *
 * Tests Coinbase Commerce upgrade, idempotency, charge:failed handling,
 * and monthly reset via direct DB manipulation.
 * 10 assertions.
 */

import {
  IntegrationTestRunner,
  generateTestKeys,
} from '../test-helpers.js';
import {
  buildCoinbaseChargeConfirmed,
  buildCoinbaseChargeFailed,
  computeCoinbaseSignature,
} from '../webhook-helpers.js';
import * as crypto from 'crypto';

export default async function journey6Coinbase(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 6: Coinbase Commerce + Monthly Reset');

  const keys = generateTestKeys();
  const walletAddress = '0x' + crypto.randomBytes(20).toString('hex');

  // ---- 1. Register + exhaust free tier ----
  await runner.register(keys.authKeyHash, keys.salt);
  for (let i = 0; i < 5; i++) {
    await runner.bundlerRpc(
      keys.authKeyHex,
      'eth_sendUserOperation',
      [{ sender: walletAddress, nonce: `0x${i.toString(16)}` }, walletAddress],
      walletAddress,
    );
  }
  const blocked = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x5' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(blocked, 403, 'Free tier exhausted');

  // ---- 2. Simulate charge:confirmed webhook ----
  const chargeId = 'charge_' + crypto.randomBytes(8).toString('hex');
  const confirmedEvent = buildCoinbaseChargeConfirmed(walletAddress, { chargeId });
  const confirmedPayload = JSON.stringify(confirmedEvent);
  const confirmedSig = computeCoinbaseSignature(confirmedPayload);

  const coinbaseResp = await runner.sendCoinbaseWebhook(confirmedPayload, confirmedSig);
  runner.assertStatusCode(coinbaseResp, 200, 'Coinbase webhook accepted');

  // ---- 3. Verify pro activation and source ----
  const statusResp = await runner.billingStatus(keys.authKeyHex, walletAddress);
  const status = await statusResp.json() as { tier?: string; source?: string };
  runner.assertEqual(status.tier, 'pro', 'Tier upgraded to pro via Coinbase');
  runner.assertEqual(status.source, 'coinbase_commerce', 'Source is coinbase_commerce');

  // ---- 4. Writes succeed as pro ----
  const proWrite = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x10' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(proWrite, 200, 'Coinbase pro: write succeeds');

  // ---- 5. Idempotency: replay same charge_id ----
  // The coinbase_service checks coinbase_id == charge_id and returns early.
  const replayPayload = JSON.stringify(buildCoinbaseChargeConfirmed(walletAddress, { chargeId }));
  const replaySig = computeCoinbaseSignature(replayPayload);
  const replayResp = await runner.sendCoinbaseWebhook(replayPayload, replaySig);
  runner.assertStatusCode(replayResp, 200, 'Replay webhook accepted (idempotent)');

  // ---- 6. charge:failed does not change tier ----
  const failedChargeId = 'charge_fail_' + crypto.randomBytes(4).toString('hex');
  const failedEvent = buildCoinbaseChargeFailed(walletAddress, { chargeId: failedChargeId });
  const failedPayload = JSON.stringify(failedEvent);
  const failedSig = computeCoinbaseSignature(failedPayload);

  const failedResp = await runner.sendCoinbaseWebhook(failedPayload, failedSig);
  runner.assertStatusCode(failedResp, 200, 'Failed charge webhook accepted');
  const statusAfterFail = await runner.billingStatus(keys.authKeyHex, walletAddress);
  const statusFail = await statusAfterFail.json() as { tier?: string };
  runner.assertEqual(statusFail.tier, 'pro', 'Tier still pro after failed charge');

  // ---- 7-8. Monthly reset test via direct DB manipulation ----
  // Downgrade to free, set counter to 5 (exhausted), and set reset_at to last month.
  // The check_and_increment_free_usage() method checks free_writes_reset_at
  // against the current month start; if older, it resets the counter to 0.
  await runner.dbQuery(
    `UPDATE subscriptions SET
      tier = 'free',
      source = NULL,
      free_writes_used = 5,
      free_writes_reset_at = '2026-01-01T00:00:00Z',
      expires_at = NULL
    WHERE wallet_address = $1`,
    [walletAddress],
  );

  // Next write should succeed because monthly reset triggers (counter resets to 0, then increments to 1).
  const resetWrite = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x20' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(resetWrite, 200, 'Monthly reset: write succeeds after period change');

  // ---- 9. Verify counter reset in billing status ----
  const statusAfterReset = await runner.billingStatus(keys.authKeyHex, walletAddress);
  const resetStatus = await statusAfterReset.json() as { free_writes_used?: number };
  runner.assertEqual(resetStatus.free_writes_used, 1, 'Counter reset to 1 after monthly reset');
}
