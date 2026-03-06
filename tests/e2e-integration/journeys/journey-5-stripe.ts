/**
 * Journey 5: Stripe Upgrade Lifecycle
 *
 * Tests free -> exhaust -> upgrade via Stripe webhook -> pro writes -> cancel -> back to free.
 * 10 assertions.
 */

import {
  IntegrationTestRunner,
  generateTestKeys,
} from '../test-helpers.js';
import {
  buildStripeCheckoutCompleted,
  buildStripeSubscriptionDeleted,
  computeStripeSignature,
} from '../webhook-helpers.js';
import * as crypto from 'crypto';

export default async function journey5Stripe(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 5: Stripe Upgrade Flow');

  const keys = generateTestKeys();
  const walletAddress = '0x' + crypto.randomBytes(20).toString('hex');

  // ---- 1. Register user ----
  await runner.register(keys.authKeyHash, keys.salt);

  // ---- 2. Exhaust free tier (5 writes) ----
  for (let i = 0; i < 5; i++) {
    await runner.bundlerRpc(
      keys.authKeyHex,
      'eth_sendUserOperation',
      [{ sender: walletAddress, nonce: `0x${i.toString(16)}` }, walletAddress],
      walletAddress,
    );
  }

  // ---- 3. Verify 6th write fails (403) ----
  const blocked = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x5' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(blocked, 403, 'Pre-upgrade: 6th write blocked');

  // ---- 4. Simulate Stripe checkout.session.completed webhook ----
  // Use a known subscriptionId so we can reference it for deletion later.
  const subscriptionId = `sub_${crypto.randomUUID().replace(/-/g, '')}`;
  const customerId = `cus_${crypto.randomUUID().replace(/-/g, '')}`;
  const checkoutEvent = buildStripeCheckoutCompleted(walletAddress, {
    subscriptionId,
    customerId,
  });
  const checkoutPayload = JSON.stringify(checkoutEvent);
  const { signature: checkoutSig } = computeStripeSignature(checkoutPayload);

  const stripeResp = await runner.sendStripeWebhook(checkoutPayload, checkoutSig);
  runner.assertStatusCode(stripeResp, 200, 'Stripe checkout webhook accepted');
  const webhookBody = await stripeResp.json() as { success?: boolean; event_type?: string };
  runner.assertEqual(webhookBody.event_type, 'checkout.session.completed', 'Webhook response confirms event type');

  // ---- 5. Verify tier is now pro via billing status ----
  const statusResp = await runner.billingStatus(keys.authKeyHex, walletAddress);
  const status = await statusResp.json() as {
    tier?: string;
    source?: string;
  };
  runner.assertEqual(status.tier, 'pro', 'Tier upgraded to pro');
  runner.assertEqual(status.source, 'stripe', 'Source is stripe');

  // ---- 6. Write succeeds as pro user ----
  const proWrite = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x10' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(proWrite, 200, 'Pro tier: write succeeds');

  // ---- 7. Batch writes all succeed (pro has high limit) ----
  let allProSucceeded = true;
  for (let i = 0; i < 10; i++) {
    const resp = await runner.bundlerRpc(
      keys.authKeyHex,
      'eth_sendUserOperation',
      [{ sender: walletAddress, nonce: `0x${(0x11 + i).toString(16)}` }, walletAddress],
      walletAddress,
    );
    if (resp.status !== 200) allProSucceeded = false;
  }
  runner.assert(allProSucceeded, 'All 10 pro writes succeeded');

  // ---- 8. Simulate customer.subscription.deleted webhook ----
  // The handler looks up wallet by stripe_id in DB, so we use the same subscriptionId.
  const deleteEvent = buildStripeSubscriptionDeleted(walletAddress, { subscriptionId });
  const deletePayload = JSON.stringify(deleteEvent);
  const { signature: deleteSig } = computeStripeSignature(deletePayload);

  const cancelResp = await runner.sendStripeWebhook(deletePayload, deleteSig);
  runner.assertStatusCode(cancelResp, 200, 'Subscription deletion webhook accepted');

  // ---- 9. Verify tier reverted to free ----
  const statusResp2 = await runner.billingStatus(keys.authKeyHex, walletAddress);
  const status2 = await statusResp2.json() as { tier?: string };
  runner.assertEqual(status2.tier, 'free', 'Tier reverted to free after cancellation');

  // ---- 10. Next write fails (free_writes_used counter persisted from before upgrade) ----
  const postCancel = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x20' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(postCancel, 403, 'Post-cancellation: write blocked (counter persisted)');
}
