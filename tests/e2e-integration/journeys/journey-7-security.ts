/**
 * Journey 7: Security & Attack Scenarios
 *
 * Tests authentication enforcement, webhook signature validation,
 * cross-user isolation, input validation, and quota bypass prevention.
 * 10 assertions.
 */

import {
  IntegrationTestRunner,
  generateTestKeys,
  buildFact,
  SERVER_URL,
} from '../test-helpers.js';
import * as crypto from 'crypto';

export default async function journey7Security(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 7: Security & Attack Scenarios');

  // ---- 1. No auth header -> 401 ----
  const noAuthResp = await fetch(`${SERVER_URL}/v1/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: 'fake', trapdoors: ['abc'] }),
  });
  runner.assertStatusCode(noAuthResp, 401, 'No auth header returns 401');

  // ---- 2. Short/invalid token -> 401 ----
  const shortTokenResp = await fetch(`${SERVER_URL}/v1/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer abc123',
    },
    body: JSON.stringify({ user_id: 'fake', trapdoors: ['abc'] }),
  });
  runner.assertStatusCode(shortTokenResp, 401, 'Short token returns 401');

  // ---- 3. Unregistered valid-length token -> 401 ----
  const fakeToken = crypto.randomBytes(32).toString('hex');
  const unregResp = await fetch(`${SERVER_URL}/v1/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${fakeToken}`,
    },
    body: JSON.stringify({ user_id: 'fake', trapdoors: ['abc'] }),
  });
  runner.assertStatusCode(unregResp, 401, 'Unregistered token returns 401');

  // ---- 4. Wrong Stripe webhook signature -> 400 ----
  const stripePayload = JSON.stringify({ type: 'checkout.session.completed', data: {} });
  const badStripeResp = await runner.sendStripeWebhook(stripePayload, 't=12345,v1=badsignature');
  runner.assertStatusCodeOneOf(badStripeResp, [400, 401, 403], 'Bad Stripe signature rejected');

  // ---- 5. Wrong Coinbase webhook signature -> 400 ----
  const coinbasePayload = JSON.stringify({ event: { type: 'charge:confirmed', data: {} } });
  const badCoinbaseResp = await runner.sendCoinbaseWebhook(coinbasePayload, 'bad_signature_hex');
  runner.assertStatusCodeOneOf(badCoinbaseResp, [400, 401, 403], 'Bad Coinbase signature rejected');

  // ---- 6. Non-write RPC bypasses write quota after exhaustion ----
  const quotaKeys = generateTestKeys();
  const quotaWallet = '0x' + crypto.randomBytes(20).toString('hex');
  await runner.register(quotaKeys.authKeyHash, quotaKeys.salt);

  // Exhaust 5 free writes
  for (let i = 0; i < 5; i++) {
    await runner.bundlerRpc(
      quotaKeys.authKeyHex,
      'eth_sendUserOperation',
      [{ sender: quotaWallet, nonce: `0x${i.toString(16)}` }, quotaWallet],
      quotaWallet,
    );
  }
  // Verify write blocked
  const blockedResp = await runner.bundlerRpc(
    quotaKeys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: quotaWallet, nonce: '0x5' }, quotaWallet],
    quotaWallet,
  );
  runner.assertStatusCode(blockedResp, 403, 'Write blocked after quota exhaustion');

  // Non-write RPC should still succeed
  const gasResp = await runner.bundlerRpc(
    quotaKeys.authKeyHex,
    'eth_estimateUserOperationGas',
    [{ sender: quotaWallet }, quotaWallet],
    quotaWallet,
  );
  runner.assertStatusCode(gasResp, 200, 'Non-write RPC bypasses write quota');

  // ---- 7. Register with empty auth_key_hash -> error ----
  const emptyRegResp = await fetch(`${SERVER_URL}/v1/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auth_key_hash: '', salt: 'a'.repeat(64) }),
  });
  const emptyRegBody = await emptyRegResp.json() as { success?: boolean };
  runner.assert(!emptyRegBody.success, 'Empty auth_key_hash rejected');

  // ---- 8. Cross-user isolation: user A cannot search user B's facts ----
  const keysA = generateTestKeys();
  const keysB = generateTestKeys();

  const regA = await runner.register(keysA.authKeyHash, keysA.salt);
  const regABody = (await regA.json()) as { user_id?: string };
  const userIdA = regABody.user_id!;

  await runner.register(keysB.authKeyHash, keysB.salt);

  // User A stores a fact
  const factA = buildFact('secret data only for user A eyes only', keysA.encryptionKey, keysA.dedupKey);
  await runner.store(keysA.authKeyHex, userIdA, [factA]);

  // User B tries to search for user A's facts using A's blind indices
  // (even if B knows the trapdoors, they should get no results because
  // the server scopes search to the authenticated user_id)
  const searchByB = await runner.search(
    keysB.authKeyHex,
    userIdA, // trying to access A's user_id
    factA.blind_indices,
  );
  // Should either return 0 results (server scopes by auth user) or 403/401
  if (searchByB.status === 200) {
    const searchBBody = (await searchByB.json()) as { results?: unknown[] };
    runner.assertEqual(searchBBody.results?.length ?? 0, 0, 'Cross-user: B gets 0 results for A');
  } else {
    runner.assertStatusCodeOneOf(searchByB, [401, 403], 'Cross-user: B request rejected');
  }

  // ---- 9. SQL injection attempt in search trapdoors ----
  const sqlKeys = generateTestKeys();
  const sqlReg = await runner.register(sqlKeys.authKeyHash, sqlKeys.salt);
  const sqlRegBody = (await sqlReg.json()) as { user_id?: string };
  const sqlUserId = sqlRegBody.user_id!;

  const sqlInjectionTrapdoors = [
    "'; DROP TABLE facts; --",
    "1' OR '1'='1",
    "' UNION SELECT * FROM users --",
  ];
  const sqlSearchResp = await runner.search(sqlKeys.authKeyHex, sqlUserId, sqlInjectionTrapdoors);
  // Server should handle gracefully (200 with empty results, or 400/422)
  runner.assert(
    sqlSearchResp.status === 200 || sqlSearchResp.status === 400 || sqlSearchResp.status === 422,
    'SQL injection in trapdoors handled safely',
  );

  // ---- 10. Oversized request body handling ----
  // Generate a very large body (> 1MB of trapdoors)
  const hugeTrapdoors = Array.from({ length: 10000 }, () => crypto.randomBytes(32).toString('hex'));
  const oversizedResp = await runner.search(sqlKeys.authKeyHex, sqlUserId, hugeTrapdoors);
  // Server should either process it (200) or reject with 413/422/400
  runner.assert(
    [200, 400, 413, 422].includes(oversizedResp.status),
    'Oversized request handled gracefully',
  );
}
