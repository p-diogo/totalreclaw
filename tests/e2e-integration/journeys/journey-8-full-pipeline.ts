/**
 * Journey 8: Full Relay Pipeline
 *
 * Tests the full relay proxy flow: register -> bundler proxy -> subgraph proxy,
 * mock request verification, error injection, and recovery.
 * 7 assertions.
 */

import {
  IntegrationTestRunner,
  generateTestKeys,
  SERVER_URL,
  MOCK_SERVICES_URL,
} from '../test-helpers.js';
import * as crypto from 'crypto';

export default async function journey8FullPipeline(runner: IntegrationTestRunner): Promise<void> {
  runner.startJourney('Journey 8: Full Relay Pipeline');

  const keys = generateTestKeys();
  const walletAddress = '0x' + crypto.randomBytes(20).toString('hex');

  // ---- 1. Register user ----
  const regResp = await runner.register(keys.authKeyHash, keys.salt);
  runner.assertStatusCode(regResp, 200, 'Registration succeeds');

  // ---- 2. Reset mock services to clean state ----
  await runner.resetMocks();

  // ---- 3. Send UserOp via POST /v1/bundler and verify mock response ----
  const bundlerResp = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x1' }, walletAddress],
    walletAddress,
  );
  runner.assertStatusCode(bundlerResp, 200, 'Bundler proxy returns 200');
  const bundlerData = (await bundlerResp.json()) as { result?: string; error?: unknown };
  runner.assert(
    typeof bundlerData.result === 'string' && bundlerData.result.includes('fake_userop_hash'),
    'Got mock userOpHash from bundler',
  );

  // ---- 4. Send GraphQL query via POST /v1/subgraph ----
  const subgraphResp = await runner.subgraphQuery(
    keys.authKeyHex,
    '{ facts(first: 10) { id } }',
    {},
    walletAddress,
  );
  runner.assertStatusCode(subgraphResp, 200, 'Subgraph proxy returns 200');

  // ---- 5. Verify mock-services received forwarded requests ----
  const requests = (await runner.getMockRequests()) as Array<{ path: string; method: string; body: unknown }>;
  const bundlerRequests = requests.filter((r) => r.path === '/bundler');
  const subgraphRequests = requests.filter((r) => r.path === '/subgraph');
  runner.assert(bundlerRequests.length >= 1, 'Mock received bundler request');
  runner.assert(subgraphRequests.length >= 1, 'Mock received subgraph request');

  // ---- 6. Configure mock bundler to return error, verify propagation ----
  await runner.configureMock({ bundler: { error: true } });
  const errorResp = await runner.bundlerRpc(
    keys.authKeyHex,
    'eth_sendUserOperation',
    [{ sender: walletAddress, nonce: '0x2' }, walletAddress],
    walletAddress,
  );
  // Mock returns JSON-RPC error (status 200 with error field in body)
  const errorData = (await errorResp.json()) as { error?: { code?: number; message?: string } };
  runner.assert(
    errorData.error != null && errorData.error.message === 'Mock error',
    'Error from mock bundler propagated correctly',
  );
}
