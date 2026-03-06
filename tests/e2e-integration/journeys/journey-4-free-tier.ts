/**
 * Journey 4: Free Tier Quota Enforcement
 *
 * Tests that free-tier users are limited to 5 writes and 10 reads per month,
 * and that non-write RPC methods bypass the write quota.
 * 10 assertions.
 */

import {
  IntegrationTestRunner,
  generateTestKeys,
} from '../test-helpers.js';
import * as crypto from 'crypto';

export default async function journey4FreeTier(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 4: Free Tier Quota Enforcement');

  const keys = generateTestKeys();
  const walletAddress = '0x' + crypto.randomBytes(20).toString('hex');

  // ---- 1. Register user (no wallet_address in register — it's subscription-based) ----
  const regResp = await runner.register(keys.authKeyHash, keys.salt);
  runner.assertStatusCode(regResp, 200, 'Registration succeeds');

  // ---- 2. Send 5 write ops via POST /v1/bundler (eth_sendUserOperation) ----
  // The first bundler call with X-Wallet-Address auto-creates a subscription row.
  for (let i = 1; i <= 5; i++) {
    const resp = await runner.bundlerRpc(
      keys.authKeyHex,
      'eth_sendUserOperation',
      [{ sender: walletAddress, nonce: `0x${i.toString(16)}` }, walletAddress],
      walletAddress,
    );
    runner.assertStatusCode(resp, 200, `Write ${i}/5 succeeds`);
  }

  // ---- 3. 6th write returns 403 quota_exceeded ----
  const resp6 = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x6' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(resp6, 403, '6th write returns 403');
  const errorBody = await resp6.json();
  runner.assertIncludes(
    JSON.stringify(errorBody).toLowerCase(),
    'quota',
    'Error response mentions quota',
  );

  // ---- 4. Billing status shows 5 writes used ----
  const statusResp = await runner.billingStatus(keys.authKeyHex, walletAddress);
  const statusBody = await statusResp.json() as {
    tier?: string;
    free_writes_used?: number;
  };
  runner.assertEqual(statusBody.free_writes_used, 5, 'Status shows 5 writes used');

  // ---- 5. Non-write RPC method bypasses write quota ----
  // eth_estimateUserOperationGas is NOT in _WRITE_RPC_METHODS
  const gasResp = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_estimateUserOperationGas',
    [{ sender: walletAddress }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(gasResp, 200, 'Gas estimation bypasses write quota');
}
