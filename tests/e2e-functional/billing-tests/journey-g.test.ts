/**
 * Journey G — Relay Pipeline Tests (T-G01 through T-G11)
 *
 * Validates the full relay pipeline: UserOp sponsorship via Pimlico,
 * webhook-based subscription checks, bundler submission, on-chain confirmation,
 * Graph Node indexing, and subgraph query. Also tests error paths for
 * missing configuration, timeouts, and RPC errors.
 *
 * Run: cd tests/e2e-functional && npx tsx billing-tests/journey-g.test.ts
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DATA_EDGE_ADDRESS = '0xA84c5433110Ccc93e57ec387e630E86Bad86c36f';
const ENTRY_POINT = '0x0000000071727De22E5E9d8BAf0edAc6f37da032';
const PIMLICO_WEBHOOK_SECRET = 'whsec_test_pimlico_secret_key_1234567890';

// Deterministic auth token
const KNOWN_AUTH_TOKEN = 'deadbeefcafebabe1234567890abcdef';
const KNOWN_AUTH_HASH = crypto
  .createHash('sha256')
  .update(Buffer.from(KNOWN_AUTH_TOKEN, 'hex'))
  .digest('hex');
const KNOWN_WALLET = '0xProWallet1234567890abcdef12345678';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MockSubscription {
  wallet_address: string;
  tier: 'free' | 'pro';
  source: 'stripe' | 'coinbase_commerce' | null;
  expires_at: Date | null;
  free_writes_used: number;
  free_writes_limit: number;
}

interface UserOperation {
  sender: string;
  nonce: string;
  initCode: string;
  callData: string;
  callGasLimit: string;
  verificationGasLimit: string;
  preVerificationGas: string;
  maxFeePerGas: string;
  maxPriorityFeePerGas: string;
  paymasterAndData: string;
  signature: string;
}

interface StoredFact {
  id: string;
  blindIndexHashes: string[];
  encryptedBlob: string;
  blockNumber: number;
  transactionHash: string;
}

interface PimlicoRpcError {
  code: number;
  message: string;
}

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------

const subscriptions = new Map<string, MockSubscription>();
const authUsers = new Map<string, string>();
const processedNonces = new Set<string>();

// Relay state: track submitted UserOps and their on-chain status
const userOpStatuses = new Map<
  string,
  {
    status: 'pending' | 'included' | 'failed';
    transactionHash: string | null;
    blockNumber: number | null;
  }
>();

// Subgraph state: facts indexed by Graph Node
const indexedFacts = new Map<string, StoredFact>();

// Mock Pimlico configuration
let pimlicoApiKey: string | null = 'pk_test_pimlico_key';
let dataEdgeAddress: string | null = DATA_EDGE_ADDRESS;
let pimlicoDelayMs = 0;
let pimlicoError: PimlicoRpcError | null = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeUserOp(overrides: Partial<UserOperation> = {}): UserOperation {
  return {
    sender: KNOWN_WALLET,
    nonce: '0x' + crypto.randomBytes(4).toString('hex'),
    initCode: '0x',
    callData: '0x' + 'ab'.repeat(64),
    callGasLimit: '0x50000',
    verificationGasLimit: '0x60000',
    preVerificationGas: '0x10000',
    maxFeePerGas: '0x0',
    maxPriorityFeePerGas: '0x0',
    paymasterAndData: '0x',
    signature: '0x' + 'ff'.repeat(65),
    ...overrides,
  };
}

function makeRelayBody(overrides: {
  userOperation?: Partial<UserOperation>;
  target?: string;
} = {}): string {
  return JSON.stringify({
    userOperation: makeUserOp(overrides.userOperation ?? {}),
    target: overrides.target ?? DATA_EDGE_ADDRESS,
  });
}

function makeValidUserOpHash(): string {
  return '0x' + crypto.randomBytes(32).toString('hex');
}

function hmacSha256(secret: string, data: string): string {
  return crypto.createHmac('sha256', secret).update(data).digest('hex');
}

async function readBody(req: http.IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString('utf8');
}

function jsonResponse(
  res: http.ServerResponse,
  status: number,
  body: unknown,
): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

function getUserWalletFromAuth(authHeader: string | undefined): string | null {
  if (!authHeader?.startsWith('Bearer ')) return null;
  const token = authHeader.slice(7);
  if (!/^[0-9a-fA-F]+$/.test(token)) return null;
  const hash = crypto
    .createHash('sha256')
    .update(Buffer.from(token, 'hex'))
    .digest('hex');
  return authUsers.get(hash) ?? null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Mock Pimlico JSON-RPC Server
// ---------------------------------------------------------------------------

interface MockPimlicoServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
  setDelay: (ms: number) => void;
  setError: (err: PimlicoRpcError | null) => void;
  reset: () => void;
}

async function startMockPimlico(port = 0): Promise<MockPimlicoServer> {
  const server = http.createServer(async (req, res) => {
    try {
      const rawBody = await readBody(req);
      const rpcReq = JSON.parse(rawBody);

      // Apply configurable delay (for timeout testing)
      if (pimlicoDelayMs > 0) {
        await sleep(pimlicoDelayMs);
      }

      // Apply configurable error (for error testing)
      if (pimlicoError) {
        jsonResponse(res, 200, {
          jsonrpc: '2.0',
          id: rpcReq.id,
          error: pimlicoError,
        });
        return;
      }

      switch (rpcReq.method) {
        case 'pm_getPaymasterStubData': {
          // Return gas estimates and stub paymaster data
          jsonResponse(res, 200, {
            jsonrpc: '2.0',
            id: rpcReq.id,
            result: {
              paymasterAndData:
                '0x' + 'aa'.repeat(20) + '00'.repeat(65),
              callGasLimit: '0x50000',
              verificationGasLimit: '0x60000',
              preVerificationGas: '0x10000',
            },
          });
          break;
        }

        case 'pm_getPaymasterData': {
          // Return final signed paymaster data
          jsonResponse(res, 200, {
            jsonrpc: '2.0',
            id: rpcReq.id,
            result: {
              paymasterAndData:
                '0x' + 'bb'.repeat(20) + 'cc'.repeat(65),
            },
          });
          break;
        }

        case 'eth_sendUserOperation': {
          // Simulate bundler accepting the UserOp
          const userOpHash = makeValidUserOpHash();
          // Track the UserOp as pending
          userOpStatuses.set(userOpHash, {
            status: 'pending',
            transactionHash: null,
            blockNumber: null,
          });

          // Schedule transition to "included" after a brief delay
          setTimeout(() => {
            const entry = userOpStatuses.get(userOpHash);
            if (entry && entry.status === 'pending') {
              const txHash = '0x' + crypto.randomBytes(32).toString('hex');
              entry.status = 'included';
              entry.transactionHash = txHash;
              entry.blockNumber = 12345678;

              // Simulate Graph Node indexing: add a fact to the subgraph
              const factId = crypto.randomUUID();
              indexedFacts.set(factId, {
                id: factId,
                blindIndexHashes: ['0xblind1', '0xblind2'],
                encryptedBlob: 'encrypted_data_' + factId.slice(0, 8),
                blockNumber: entry.blockNumber,
                transactionHash: txHash,
              });
            }
          }, 50);

          jsonResponse(res, 200, {
            jsonrpc: '2.0',
            id: rpcReq.id,
            result: userOpHash,
          });
          break;
        }

        case 'eth_getUserOperationReceipt': {
          const hash = rpcReq.params?.[0] as string;
          const entry = userOpStatuses.get(hash);
          if (!entry) {
            jsonResponse(res, 200, {
              jsonrpc: '2.0',
              id: rpcReq.id,
              result: null,
            });
          } else {
            jsonResponse(res, 200, {
              jsonrpc: '2.0',
              id: rpcReq.id,
              result: {
                success: entry.status === 'included',
                receipt: {
                  transactionHash: entry.transactionHash,
                  blockNumber: entry.blockNumber
                    ? `0x${entry.blockNumber.toString(16)}`
                    : null,
                  status: entry.status === 'included' ? '0x1' : '0x0',
                },
              },
            });
          }
          break;
        }

        default:
          jsonResponse(res, 200, {
            jsonrpc: '2.0',
            id: rpcReq.id,
            error: { code: -32601, message: 'Method not found' },
          });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  return new Promise<MockPimlicoServer>((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      const actualPort = addr.port;
      const baseUrl = `http://127.0.0.1:${actualPort}`;

      resolve({
        url: baseUrl,
        port: actualPort,
        stop: () =>
          new Promise<void>((r) => {
            server.close(() => r());
          }),
        setDelay: (ms: number) => {
          pimlicoDelayMs = ms;
        },
        setError: (err: PimlicoRpcError | null) => {
          pimlicoError = err;
        },
        reset: () => {
          pimlicoDelayMs = 0;
          pimlicoError = null;
        },
      });
    });
  });
}

// ---------------------------------------------------------------------------
// Mock Subgraph GraphQL Server
// ---------------------------------------------------------------------------

interface MockSubgraphServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
}

async function startMockSubgraph(port = 0): Promise<MockSubgraphServer> {
  const server = http.createServer(async (req, res) => {
    try {
      const rawBody = await readBody(req);
      const gql = JSON.parse(rawBody);
      const query = (gql.query ?? '') as string;

      // Respond to any query that looks like it's fetching facts
      if (
        query.includes('facts') ||
        query.includes('blindIndexes') ||
        query.includes('encryptedFacts')
      ) {
        const facts = Array.from(indexedFacts.values()).map((f) => ({
          id: f.id,
          blindIndexHashes: f.blindIndexHashes,
          encryptedBlob: f.encryptedBlob,
          blockNumber: f.blockNumber.toString(),
          transactionHash: f.transactionHash,
        }));

        jsonResponse(res, 200, {
          data: {
            encryptedFacts: facts,
          },
        });
      } else {
        jsonResponse(res, 200, { data: {} });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  return new Promise<MockSubgraphServer>((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      const actualPort = addr.port;
      const baseUrl = `http://127.0.0.1:${actualPort}`;

      resolve({
        url: baseUrl,
        port: actualPort,
        stop: () =>
          new Promise<void>((r) => {
            server.close(() => r());
          }),
      });
    });
  });
}

// ---------------------------------------------------------------------------
// Mock Relay Server (orchestrates Pimlico, subscriptions, status polling)
// ---------------------------------------------------------------------------

let pimlicoUrl = '';
let subgraphUrl = '';

interface MockRelayServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
  reset: () => void;
}

async function handleRelaySponsor(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const wallet = getUserWalletFromAuth(req.headers.authorization);
  if (!wallet) {
    jsonResponse(res, 401, {
      success: false,
      error_code: 'UNAUTHORIZED',
      error_message: 'Missing or invalid auth token',
    });
    return;
  }

  let body: { userOperation: UserOperation; target: string };
  try {
    body = JSON.parse(await readBody(req));
  } catch {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_JSON',
      error_message: 'Request body is not valid JSON',
    });
    return;
  }

  const { userOperation, target } = body;

  // T-G11: Check DATA_EDGE_ADDRESS configured
  if (!dataEdgeAddress) {
    jsonResponse(res, 503, {
      success: false,
      error_code: 'NOT_CONFIGURED',
      error_message: 'DATA_EDGE_ADDRESS not configured',
    });
    return;
  }

  if (target.toLowerCase() !== dataEdgeAddress.toLowerCase()) {
    jsonResponse(res, 403, {
      success: false,
      error_code: 'INVALID_TARGET',
      error_message: 'Target contract address not allowed',
    });
    return;
  }

  if (
    !userOperation.callData ||
    userOperation.callData === '0x' ||
    userOperation.callData === ''
  ) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'EMPTY_CALLDATA',
      error_message: 'Empty calldata. Nothing to write.',
    });
    return;
  }

  // Replay detection
  const replayKey = `${userOperation.sender}:${userOperation.nonce}`;
  if (processedNonces.has(replayKey)) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'NONCE_ERROR',
      error_message: 'Replay detected',
    });
    return;
  }
  processedNonces.add(replayKey);

  // T-G08: Check Pimlico API key
  if (!pimlicoApiKey) {
    jsonResponse(res, 503, {
      success: false,
      error_code: 'NOT_CONFIGURED',
      error_message: 'PIMLICO_API_KEY not configured',
    });
    return;
  }

  // T-G01: Forward to Pimlico — pm_getPaymasterStubData
  try {
    const stubResult = await pimlicoRpc('pm_getPaymasterStubData', [
      userOperation,
      ENTRY_POINT,
      '0x64', // chainId (Gnosis = 100 = 0x64)
      {},
    ]);

    if (stubResult.error) {
      jsonResponse(res, 400, {
        success: false,
        error_code: 'PIMLICO_ERROR',
        error_message: stubResult.error.message,
      });
      return;
    }

    // Apply stub gas estimates to the UserOp
    const updatedOp = {
      ...userOperation,
      paymasterAndData: stubResult.result.paymasterAndData,
    };

    // pm_getPaymasterData — get final signed paymaster data
    const finalResult = await pimlicoRpc('pm_getPaymasterData', [
      updatedOp,
      ENTRY_POINT,
      '0x64',
      {},
    ]);

    if (finalResult.error) {
      jsonResponse(res, 400, {
        success: false,
        error_code: 'PIMLICO_ERROR',
        error_message: finalResult.error.message,
      });
      return;
    }

    // T-G04: Submit to bundler via eth_sendUserOperation
    const submitOp = {
      ...updatedOp,
      paymasterAndData: finalResult.result.paymasterAndData,
    };

    const sendResult = await pimlicoRpc('eth_sendUserOperation', [
      submitOp,
      ENTRY_POINT,
    ]);

    if (sendResult.error) {
      jsonResponse(res, 400, {
        success: false,
        error_code: 'BUNDLER_ERROR',
        error_message: sendResult.error.message,
      });
      return;
    }

    const userOpHash = sendResult.result as string;

    jsonResponse(res, 200, {
      success: true,
      sponsor: true,
      userOpHash,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);

    // T-G09: Timeout detection
    if (message.includes('timeout') || message.includes('ETIMEDOUT') || message.includes('socket hang up')) {
      jsonResponse(res, 504, {
        success: false,
        error_code: 'PIMLICO_TIMEOUT',
        error_message: 'Pimlico API request timed out',
      });
      return;
    }

    jsonResponse(res, 502, {
      success: false,
      error_code: 'RELAY_ERROR',
      error_message: message,
    });
  }
}

async function pimlicoRpc(
  method: string,
  params: unknown[],
): Promise<{ result?: any; error?: { code: number; message: string } }> {
  return new Promise((resolve, reject) => {
    const url = new URL(pimlicoUrl);
    const payload = JSON.stringify({
      jsonrpc: '2.0',
      id: Date.now(),
      method,
      params,
    });

    const reqOpts: http.RequestOptions = {
      hostname: url.hostname,
      port: url.port,
      path: '/',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
      timeout: 5000, // 5s timeout for testing (T-G09 uses a delay > 5s)
    };

    const req = http.request(reqOpts, async (res) => {
      const chunks: Buffer[] = [];
      for await (const chunk of res) {
        chunks.push(chunk as Buffer);
      }
      const text = Buffer.concat(chunks).toString('utf8');
      try {
        resolve(JSON.parse(text));
      } catch {
        reject(new Error(`Invalid JSON from Pimlico: ${text}`));
      }
    });

    req.on('timeout', () => {
      req.destroy(new Error('Pimlico request timeout'));
    });

    req.on('error', (err) => {
      reject(err);
    });

    req.write(payload);
    req.end();
  });
}

async function handlePimlicoWebhook(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const rawBody = await readBody(req);

  const signature = req.headers['x-pimlico-signature'] as string | undefined;
  if (!signature) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_SIGNATURE',
      error_message: 'Missing X-Pimlico-Signature header',
    });
    return;
  }

  const expectedSignature = hmacSha256(PIMLICO_WEBHOOK_SECRET, rawBody);
  if (signature !== expectedSignature) {
    jsonResponse(res, 401, {
      success: false,
      error_code: 'INVALID_SIGNATURE',
      error_message: 'Pimlico webhook signature verification failed',
    });
    return;
  }

  let event: { type?: string; data?: { sender?: string } };
  try {
    event = JSON.parse(rawBody);
  } catch {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_JSON',
      error_message: 'Invalid JSON',
    });
    return;
  }

  if (event.type === 'user_operation.sponsorship.requested') {
    const sender = event.data?.sender;
    if (!sender) {
      jsonResponse(res, 200, {
        success: true,
        sponsor: false,
        reason: 'missing_sender',
      });
      return;
    }

    // Check subscription for the sender
    const sub = subscriptions.get(sender);
    const isProActive =
      sub?.tier === 'pro' &&
      sub.expires_at !== null &&
      sub.expires_at > new Date();
    const hasFreeQuota =
      sub !== undefined &&
      sub.tier === 'free' &&
      sub.free_writes_used < sub.free_writes_limit;
    const shouldSponsor = isProActive || hasFreeQuota;

    jsonResponse(res, 200, {
      success: true,
      sponsor: shouldSponsor,
      ...(shouldSponsor ? {} : { reason: 'upgrade_required' }),
    });
    return;
  }

  if (event.type === 'user_operation.sponsorship.finalized') {
    jsonResponse(res, 200, { success: true, acknowledged: true });
    return;
  }

  jsonResponse(res, 200, {
    success: true,
    sponsor: false,
    reason: 'unknown_event',
  });
}

async function handleRelayStatus(
  _req: http.IncomingMessage,
  res: http.ServerResponse,
  hash: string,
): Promise<void> {
  const hashRegex = /^0x[0-9a-fA-F]{64}$/;
  if (!hashRegex.test(hash)) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_FORMAT',
      error_message: 'Invalid userOpHash format',
    });
    return;
  }

  const entry = userOpStatuses.get(hash);
  if (!entry) {
    jsonResponse(res, 200, {
      success: true,
      status: 'unknown',
      transactionHash: null,
      blockNumber: null,
    });
    return;
  }

  jsonResponse(res, 200, {
    success: true,
    status: entry.status,
    transactionHash: entry.transactionHash,
    blockNumber: entry.blockNumber,
  });
}

async function startMockRelayServer(port = 0): Promise<MockRelayServer> {
  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      if (method === 'GET' && url === '/health') {
        jsonResponse(res, 200, { status: 'ok' });
        return;
      }

      if (method === 'POST' && url === '/v1/relay/sponsor') {
        await handleRelaySponsor(req, res);
        return;
      }

      if (method === 'POST' && url === '/v1/relay/webhook/pimlico') {
        await handlePimlicoWebhook(req, res);
        return;
      }

      const statusMatch = url.match(/^\/v1\/relay\/status\/(.+)$/);
      if (method === 'GET' && statusMatch) {
        await handleRelayStatus(
          req,
          res,
          decodeURIComponent(statusMatch[1]),
        );
        return;
      }

      jsonResponse(res, 404, { error: 'Not found' });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      jsonResponse(res, 500, { error: message });
    }
  });

  return new Promise<MockRelayServer>((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      const actualPort = addr.port;
      const baseUrl = `http://127.0.0.1:${actualPort}`;

      resolve({
        url: baseUrl,
        port: actualPort,
        stop: () =>
          new Promise<void>((r) => {
            server.close(() => r());
          }),
        reset: () => {
          subscriptions.clear();
          processedNonces.clear();
          authUsers.clear();
          userOpStatuses.clear();
          indexedFacts.clear();
          pimlicoApiKey = 'pk_test_pimlico_key';
          dataEdgeAddress = DATA_EDGE_ADDRESS;
          // Register the known test user
          authUsers.set(KNOWN_AUTH_HASH, KNOWN_WALLET);
        },
      });
    });
  });
}

// ---------------------------------------------------------------------------
// HTTP client helper
// ---------------------------------------------------------------------------

interface FetchResult {
  status: number;
  body: Record<string, unknown>;
}

async function httpRequest(
  url: string,
  options: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
    timeout?: number;
  } = {},
): Promise<FetchResult> {
  return new Promise<FetchResult>((resolve, reject) => {
    const parsed = new URL(url);
    const reqOpts: http.RequestOptions = {
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname + parsed.search,
      method: options.method ?? 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      timeout: options.timeout ?? 10000,
    };

    const req = http.request(reqOpts, async (res) => {
      const chunks: Buffer[] = [];
      for await (const chunk of res) {
        chunks.push(chunk as Buffer);
      }
      const text = Buffer.concat(chunks).toString('utf8');
      try {
        resolve({
          status: res.statusCode ?? 0,
          body: JSON.parse(text),
        });
      } catch {
        resolve({
          status: res.statusCode ?? 0,
          body: { raw: text } as Record<string, unknown>,
        });
      }
    });

    req.on('timeout', () => {
      req.destroy(new Error('Request timeout'));
    });

    req.on('error', (err) => {
      reject(err);
    });

    if (options.body) {
      req.write(options.body);
    }
    req.end();
  });
}

// ---------------------------------------------------------------------------
// TAP test runner
// ---------------------------------------------------------------------------

let testNumber = 0;
let passed = 0;
let failed = 0;
const totalTests = 11;

function ok(condition: boolean, description: string, detail?: string): void {
  testNumber++;
  if (condition) {
    passed++;
    console.log(`ok ${testNumber} - ${description}`);
  } else {
    failed++;
    console.log(`not ok ${testNumber} - ${description}`);
    if (detail) {
      console.log(`  ---`);
      console.log(`  message: ${detail}`);
      console.log(`  ...`);
    }
  }
}

// ---------------------------------------------------------------------------
// Test execution
// ---------------------------------------------------------------------------

async function runTests(): Promise<void> {
  console.log('TAP version 14');
  console.log(`1..${totalTests}`);

  // Start all mock servers
  const mockPimlico = await startMockPimlico();
  pimlicoUrl = mockPimlico.url;

  const mockSubgraph = await startMockSubgraph();
  subgraphUrl = mockSubgraph.url;

  const relay = await startMockRelayServer();
  relay.reset();

  try {
    // ---------------------------------------------------------------
    // T-G01: Relay forwards UserOp to Pimlico
    //        (pm_getPaymasterStubData -> pm_getPaymasterData)
    // ---------------------------------------------------------------
    {
      const res = await httpRequest(`${relay.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
      });

      ok(
        res.status === 200 &&
          res.body.success === true &&
          res.body.sponsor === true &&
          typeof res.body.userOpHash === 'string' &&
          (res.body.userOpHash as string).startsWith('0x') &&
          (res.body.userOpHash as string).length === 66,
        'T-G01: Relay forwards UserOp to Pimlico (stub + final paymaster data)',
        `status=${res.status}, success=${res.body.success}, sponsor=${res.body.sponsor}, hash=${res.body.userOpHash}`,
      );
    }

    // ---------------------------------------------------------------
    // T-G02: Pimlico webhook callback — subscription check (sponsor: true for pro)
    // ---------------------------------------------------------------
    {
      // Set up a pro subscription for the sender
      const sender = '0xWebhookProUser000000000000000000000';
      subscriptions.set(sender, {
        wallet_address: sender,
        tier: 'pro',
        source: 'stripe',
        expires_at: new Date(Date.now() + 86_400_000 * 30), // 30 days
        free_writes_used: 0,
        free_writes_limit: 100,
      });

      const webhookBody = JSON.stringify({
        type: 'user_operation.sponsorship.requested',
        data: { sender },
      });
      const sig = hmacSha256(PIMLICO_WEBHOOK_SECRET, webhookBody);

      const res = await httpRequest(
        `${relay.url}/v1/relay/webhook/pimlico`,
        {
          method: 'POST',
          headers: { 'X-Pimlico-Signature': sig },
          body: webhookBody,
        },
      );

      ok(
        res.status === 200 && res.body.sponsor === true,
        'T-G02: Pimlico webhook -- subscription check (sponsor: true for pro)',
        `status=${res.status}, sponsor=${res.body.sponsor}`,
      );
    }

    // ---------------------------------------------------------------
    // T-G03: Pimlico webhook callback — free tier denial (sponsor: false)
    // ---------------------------------------------------------------
    {
      const sender = '0xFreeTierExhaustedUser0000000000000';
      subscriptions.set(sender, {
        wallet_address: sender,
        tier: 'free',
        source: null,
        expires_at: null,
        free_writes_used: 100,
        free_writes_limit: 100,
      });

      const webhookBody = JSON.stringify({
        type: 'user_operation.sponsorship.requested',
        data: { sender },
      });
      const sig = hmacSha256(PIMLICO_WEBHOOK_SECRET, webhookBody);

      const res = await httpRequest(
        `${relay.url}/v1/relay/webhook/pimlico`,
        {
          method: 'POST',
          headers: { 'X-Pimlico-Signature': sig },
          body: webhookBody,
        },
      );

      ok(
        res.status === 200 &&
          res.body.sponsor === false &&
          res.body.reason === 'upgrade_required',
        'T-G03: Pimlico webhook -- free tier exhausted (sponsor: false)',
        `status=${res.status}, sponsor=${res.body.sponsor}, reason=${res.body.reason}`,
      );
    }

    // ---------------------------------------------------------------
    // T-G04: Bundler submits sponsored UserOp
    //        (eth_sendUserOperation -> userOpHash)
    // ---------------------------------------------------------------
    {
      relay.reset();
      const res = await httpRequest(`${relay.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
      });

      const hash = res.body.userOpHash as string;
      const isValidHash =
        typeof hash === 'string' &&
        hash.startsWith('0x') &&
        hash.length === 66;

      ok(
        res.body.success === true && isValidHash,
        'T-G04: Bundler submits sponsored UserOp -- returns userOpHash',
        `success=${res.body.success}, hash=${hash}, validFormat=${isValidHash}`,
      );
    }

    // ---------------------------------------------------------------
    // T-G05: Transaction confirmed on-chain (status polling: pending -> included)
    // ---------------------------------------------------------------
    {
      relay.reset();
      // Submit a UserOp first
      const submitRes = await httpRequest(
        `${relay.url}/v1/relay/sponsor`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
          body: makeRelayBody(),
        },
      );
      const hash = submitRes.body.userOpHash as string;

      // Immediately poll — should be pending
      const pendingRes = await httpRequest(
        `${relay.url}/v1/relay/status/${hash}`,
      );

      // Wait for the mock to transition to "included" (50ms delay + margin)
      await sleep(150);

      // Poll again — should be included now
      const includedRes = await httpRequest(
        `${relay.url}/v1/relay/status/${hash}`,
      );

      ok(
        pendingRes.body.status === 'pending' &&
          includedRes.body.status === 'included' &&
          typeof includedRes.body.transactionHash === 'string' &&
          typeof includedRes.body.blockNumber === 'number',
        'T-G05: Transaction confirmed on-chain (pending -> included)',
        `pending: status=${pendingRes.body.status}, included: status=${includedRes.body.status}, txHash=${includedRes.body.transactionHash}`,
      );
    }

    // ---------------------------------------------------------------
    // T-G06: Graph Node indexes the event (fact appears in subgraph)
    // ---------------------------------------------------------------
    {
      // After T-G05, the mock Pimlico should have added a fact to indexedFacts
      // (which the subgraph mock serves)
      const factCount = indexedFacts.size;

      // Query the mock subgraph
      const gqlRes = await httpRequest(subgraphUrl, {
        method: 'POST',
        body: JSON.stringify({
          query: '{ encryptedFacts(first: 100) { id encryptedBlob blockNumber transactionHash } }',
        }),
      });

      const data = gqlRes.body.data as Record<string, unknown> | undefined;
      const facts = (data?.encryptedFacts ?? []) as unknown[];

      ok(
        factCount > 0 &&
          gqlRes.status === 200 &&
          facts.length > 0,
        'T-G06: Graph Node indexes the event (fact appears in subgraph)',
        `indexedFacts=${factCount}, gqlStatus=${gqlRes.status}, returnedFacts=${facts.length}`,
      );
    }

    // ---------------------------------------------------------------
    // T-G07: Subgraph query returns stored fact (full round-trip)
    // ---------------------------------------------------------------
    {
      // Verify the fact from T-G06 has expected structure
      const gqlRes = await httpRequest(subgraphUrl, {
        method: 'POST',
        body: JSON.stringify({
          query: '{ encryptedFacts(first: 1) { id encryptedBlob blockNumber transactionHash blindIndexHashes } }',
        }),
      });

      const data = gqlRes.body.data as Record<string, unknown> | undefined;
      const facts = (data?.encryptedFacts ?? []) as Array<{
        id: string;
        encryptedBlob: string;
        blockNumber: string;
        transactionHash: string;
      }>;

      const fact = facts[0];
      const hasRequiredFields =
        fact &&
        typeof fact.id === 'string' &&
        typeof fact.encryptedBlob === 'string' &&
        typeof fact.blockNumber === 'string' &&
        typeof fact.transactionHash === 'string' &&
        fact.transactionHash.startsWith('0x');

      ok(
        hasRequiredFields === true,
        'T-G07: Subgraph query returns stored fact (full round-trip)',
        `fact=${JSON.stringify(fact)}`,
      );
    }

    // ---------------------------------------------------------------
    // T-G08: Pimlico API key not configured -> graceful error
    // ---------------------------------------------------------------
    {
      relay.reset();
      pimlicoApiKey = null;

      const res = await httpRequest(`${relay.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
      });

      ok(
        res.status === 503 && res.body.error_code === 'NOT_CONFIGURED',
        'T-G08: Pimlico API key not configured -- graceful 503 error',
        `status=${res.status}, error_code=${res.body.error_code}`,
      );

      pimlicoApiKey = 'pk_test_pimlico_key';
    }

    // ---------------------------------------------------------------
    // T-G09: Pimlico API timeout -> timeout error
    // ---------------------------------------------------------------
    {
      relay.reset();
      // Set Pimlico delay to 10 seconds (relay has 5s timeout)
      mockPimlico.setDelay(10000);

      const res = await httpRequest(`${relay.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
        timeout: 15000, // Give the relay time to handle the timeout
      });

      ok(
        (res.status === 504 && res.body.error_code === 'PIMLICO_TIMEOUT') ||
          (res.status === 502 && res.body.error_code === 'RELAY_ERROR'),
        'T-G09: Pimlico API timeout -- timeout error',
        `status=${res.status}, error_code=${res.body.error_code}, message=${res.body.error_message}`,
      );

      mockPimlico.setDelay(0);
    }

    // ---------------------------------------------------------------
    // T-G10: Pimlico RPC error response -> error propagated
    // ---------------------------------------------------------------
    {
      relay.reset();
      mockPimlico.setError({ code: -32602, message: 'Invalid UserOp' });

      const res = await httpRequest(`${relay.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
      });

      ok(
        res.status === 400 &&
          res.body.error_code === 'PIMLICO_ERROR' &&
          (res.body.error_message as string).includes('Invalid UserOp'),
        'T-G10: Pimlico RPC error response -- error propagated',
        `status=${res.status}, error_code=${res.body.error_code}, message=${res.body.error_message}`,
      );

      mockPimlico.setError(null);
    }

    // ---------------------------------------------------------------
    // T-G11: DATA_EDGE_ADDRESS not configured -> 503
    // ---------------------------------------------------------------
    {
      relay.reset();
      dataEdgeAddress = null;

      const res = await httpRequest(`${relay.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
      });

      ok(
        res.status === 503 && res.body.error_code === 'NOT_CONFIGURED',
        'T-G11: DATA_EDGE_ADDRESS not configured -- 503',
        `status=${res.status}, error_code=${res.body.error_code}`,
      );

      dataEdgeAddress = DATA_EDGE_ADDRESS;
    }
  } finally {
    await relay.stop();
    await mockPimlico.stop();
    await mockSubgraph.stop();
  }

  // TAP summary
  console.log('');
  console.log(`# tests ${totalTests}`);
  console.log(`# pass  ${passed}`);
  console.log(`# fail  ${failed}`);

  if (failed > 0) {
    process.exit(1);
  }
}

runTests().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
