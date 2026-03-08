/**
 * Journey D — Unauthorized / Attack Scenario Tests (T-D01 through T-D15)
 *
 * Validates that the relay server rejects invalid, unauthorized, and malicious
 * requests with appropriate HTTP status codes and error codes. All 15 tests
 * run against an in-process mock HTTP server with no external dependencies.
 *
 * Run: cd tests/e2e-functional && npx tsx billing-tests/journey-d.test.ts
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DATA_EDGE_ADDRESS = '0xA84c5433110Ccc93e57ec387e630E86Bad86c36f';
const PIMLICO_WEBHOOK_SECRET = 'whsec_test_pimlico_secret_key_1234567890';
const STRIPE_WEBHOOK_SECRET = 'whsec_test_stripe_secret_key_9876543210';

// Deterministic auth token whose SHA-256 hash maps to a known wallet
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

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------

const subscriptions = new Map<string, MockSubscription>();
const processedNonces = new Set<string>();
const authUsers = new Map<string, string>(); // authKeyHash -> walletAddress

let simulateDbError = false;
let pimlicoApiKey: string | null = 'pk_test_pimlico_key';
let dataEdgeAddress: string | null = DATA_EDGE_ADDRESS;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeUserOp(overrides: Partial<UserOperation> = {}): UserOperation {
  return {
    sender: '0x1234567890abcdef1234567890abcdef12345678',
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
  // Validate token is valid hex
  if (!/^[0-9a-fA-F]+$/.test(token)) return null;
  const hash = crypto
    .createHash('sha256')
    .update(Buffer.from(token, 'hex'))
    .digest('hex');
  return authUsers.get(hash) ?? null;
}

// ---------------------------------------------------------------------------
// Mock Relay Server — Route Handlers
// ---------------------------------------------------------------------------

async function handleRelaySponsor(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  // T-D01 / T-D02: Auth check
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

  // T-D05: Validate target contract
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

  // T-D06: Empty calldata
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

  // T-D07: Validate calldata length (must be at least 4 bytes / 8 hex chars
  //        after 0x prefix for a valid protobuf-encoded ABI call)
  const calldataHex = userOperation.callData.startsWith('0x')
    ? userOperation.callData.slice(2)
    : userOperation.callData;
  if (calldataHex.length < 8) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_CALLDATA',
      error_message: 'Calldata too short to contain valid protobuf',
    });
    return;
  }

  // T-D14: Database error during subscription check -> fail closed
  if (simulateDbError) {
    jsonResponse(res, 200, {
      success: false,
      sponsor: false,
      error_code: 'DB_ERROR',
      error_message: 'Subscription check failed -- failing closed',
    });
    return;
  }

  // T-D03: Check subscription / free tier
  const sub = subscriptions.get(wallet);
  if (sub) {
    const isProActive =
      sub.tier === 'pro' &&
      sub.expires_at !== null &&
      sub.expires_at > new Date();
    const hasFreeQuota =
      sub.tier === 'free' && sub.free_writes_used < sub.free_writes_limit;

    if (!isProActive && !hasFreeQuota) {
      jsonResponse(res, 200, {
        success: false,
        sponsor: false,
        error_code: 'QUOTA_EXCEEDED',
        error_message:
          'Pro expired and free tier exhausted. Upgrade required.',
      });
      return;
    }
  }

  // T-D04: Replay detection (nonce-based)
  const replayKey = `${userOperation.sender}:${userOperation.nonce}`;
  if (processedNonces.has(replayKey)) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'NONCE_ERROR',
      error_message:
        'UserOperation with this nonce already processed (replay detected)',
    });
    return;
  }
  processedNonces.add(replayKey);

  // Check Pimlico API key
  if (!pimlicoApiKey) {
    jsonResponse(res, 503, {
      success: false,
      error_code: 'NOT_CONFIGURED',
      error_message: 'PIMLICO_API_KEY not configured',
    });
    return;
  }

  // All checks passed — simulate successful sponsorship
  const userOpHash = '0x' + crypto.randomBytes(32).toString('hex');
  jsonResponse(res, 200, {
    success: true,
    sponsor: true,
    userOpHash,
  });
}

async function handlePimlicoWebhook(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const rawBody = await readBody(req);

  // T-D08: Missing signature
  const signature = req.headers['x-pimlico-signature'] as string | undefined;
  if (!signature) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_SIGNATURE',
      error_message: 'Missing X-Pimlico-Signature header',
    });
    return;
  }

  // T-D09: Invalid signature
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
      error_message: 'Webhook body is not valid JSON',
    });
    return;
  }

  // T-D10: Unknown event type
  const knownEvents = [
    'user_operation.sponsorship.requested',
    'user_operation.sponsorship.finalized',
  ];
  if (!event.type || !knownEvents.includes(event.type)) {
    jsonResponse(res, 200, {
      success: true,
      sponsor: false,
      error_code: 'UNKNOWN_EVENT',
      error_message: `Unknown event type: ${event.type ?? 'undefined'}`,
    });
    return;
  }

  // T-D11: Missing sender address
  if (!event.data?.sender) {
    jsonResponse(res, 200, {
      success: true,
      sponsor: false,
      error_code: 'MISSING_SENDER',
      error_message: 'Webhook payload missing sender address',
    });
    return;
  }

  // Check subscription for the sender
  const sub = subscriptions.get(event.data.sender);
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
}

async function handleStripeWebhook(
  req: http.IncomingMessage,
  res: http.ServerResponse,
): Promise<void> {
  const rawBody = await readBody(req);

  // T-D12: Missing Stripe-Signature
  const sigHeader = req.headers['stripe-signature'] as string | undefined;
  if (!sigHeader) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'MISSING_SIGNATURE',
      error_message: 'Missing Stripe-Signature header',
    });
    return;
  }

  // T-D13: Parse and validate Stripe signature (t=timestamp,v1=hmac format)
  const parts = sigHeader.split(',');
  const tPart = parts.find((p) => p.startsWith('t='));
  const v1Part = parts.find((p) => p.startsWith('v1='));

  if (!tPart || !v1Part) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_SIGNATURE',
      error_message: 'Malformed Stripe-Signature header',
    });
    return;
  }

  const timestamp = tPart.slice(2);
  const providedSig = v1Part.slice(3);
  const signedPayload = `${timestamp}.${rawBody}`;
  const expectedSig = crypto
    .createHmac('sha256', STRIPE_WEBHOOK_SECRET)
    .update(signedPayload)
    .digest('hex');

  if (providedSig !== expectedSig) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_SIGNATURE',
      error_message: 'Stripe webhook signature verification failed',
    });
    return;
  }

  jsonResponse(res, 200, {
    success: true,
    event_type: 'checkout.session.completed',
  });
}

async function handleRelayStatus(
  _req: http.IncomingMessage,
  res: http.ServerResponse,
  hash: string,
): Promise<void> {
  // T-D15: Validate userOpHash format — must be 0x + 64 hex chars (66 total)
  const hashRegex = /^0x[0-9a-fA-F]{64}$/;
  if (!hashRegex.test(hash)) {
    jsonResponse(res, 400, {
      success: false,
      error_code: 'INVALID_FORMAT',
      error_message:
        'Invalid userOpHash format. Expected 0x-prefixed, 66-char hex string.',
    });
    return;
  }

  jsonResponse(res, 200, {
    success: true,
    status: 'pending',
    transactionHash: null,
    blockNumber: null,
  });
}

// ---------------------------------------------------------------------------
// Server lifecycle
// ---------------------------------------------------------------------------

interface MockRelayServer {
  url: string;
  port: number;
  stop: () => Promise<void>;
  reset: () => void;
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

      if (method === 'POST' && url === '/v1/billing/webhook/stripe') {
        await handleStripeWebhook(req, res);
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
          simulateDbError = false;
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

    req.on('error', reject);
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
const totalTests = 15;

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

  const server = await startMockRelayServer();
  server.reset();

  try {
    // ---------------------------------------------------------------
    // T-D01: No auth header -> relay rejected (401)
    // ---------------------------------------------------------------
    {
      const res = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        body: makeRelayBody(),
      });
      ok(
        res.status === 401,
        'T-D01: No auth header -- relay rejected (401)',
        `Expected status 401, got ${res.status}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D02: Invalid signature -> relay rejected (401)
    // ---------------------------------------------------------------
    {
      const res = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: {
          Authorization: 'Bearer 0000000000000000badtoken00000000',
        },
        body: makeRelayBody(),
      });
      ok(
        res.status === 401,
        'T-D02: Invalid signature -- relay rejected (401)',
        `Expected status 401, got ${res.status}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D03: Expired pro + exhausted free tier -> sponsorship denied
    // ---------------------------------------------------------------
    {
      // Set up subscription: pro expired yesterday, free tier exhausted
      subscriptions.set(KNOWN_WALLET, {
        wallet_address: KNOWN_WALLET,
        tier: 'pro',
        source: 'stripe',
        expires_at: new Date(Date.now() - 86_400_000), // expired yesterday
        free_writes_used: 100,
        free_writes_limit: 100,
      });

      const res = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
      });
      ok(
        res.status === 200 && res.body.sponsor === false,
        'T-D03: Expired pro + exhausted free tier -- sponsorship denied',
        `Expected 200 + sponsor=false, got ${res.status} + sponsor=${res.body.sponsor}`,
      );

      subscriptions.delete(KNOWN_WALLET);
    }

    // ---------------------------------------------------------------
    // T-D04: Replay attack — same UserOp nonce -> nonce error
    // ---------------------------------------------------------------
    {
      const fixedNonce = '0xdeadbeef';
      const fixedSender = '0xReplaySender000000000000000000000000';

      // First request succeeds
      const first = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody({
          userOperation: { nonce: fixedNonce, sender: fixedSender },
        }),
      });

      // Second request with same nonce + sender = replay
      const replay = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody({
          userOperation: { nonce: fixedNonce, sender: fixedSender },
        }),
      });

      ok(
        first.body.success === true &&
          replay.status === 400 &&
          replay.body.error_code === 'NONCE_ERROR',
        'T-D04: Replay attack -- same UserOp nonce -- nonce error',
        `first.success=${first.body.success}, replay: status=${replay.status} error_code=${replay.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D05: UserOp targeting wrong contract -> 403
    // ---------------------------------------------------------------
    {
      const wrongTarget = '0x0000000000000000000000000000000000BADBAD';
      const res = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody({ target: wrongTarget }),
      });
      ok(
        res.status === 403,
        'T-D05: UserOp targeting wrong contract -- 403',
        `Expected status 403, got ${res.status}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D06: Empty calldata -> 400
    // ---------------------------------------------------------------
    {
      const res = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody({ userOperation: { callData: '0x' } }),
      });
      ok(
        res.status === 400 && res.body.error_code === 'EMPTY_CALLDATA',
        'T-D06: Empty calldata -- 400',
        `Expected 400/EMPTY_CALLDATA, got ${res.status}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D07: Malformed calldata (invalid protobuf) -> rejected
    // ---------------------------------------------------------------
    {
      // Only 1 byte of hex after 0x — too short for any valid protobuf ABI call
      const res = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody({ userOperation: { callData: '0xab' } }),
      });
      ok(
        res.status === 400 && res.body.error_code === 'INVALID_CALLDATA',
        'T-D07: Malformed calldata (too short for protobuf) -- rejected',
        `Expected 400/INVALID_CALLDATA, got ${res.status}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D08: Pimlico webhook missing signature -> 400
    // ---------------------------------------------------------------
    {
      const webhookBody = JSON.stringify({
        type: 'user_operation.sponsorship.requested',
        data: { sender: '0xabc123' },
      });
      const res = await httpRequest(
        `${server.url}/v1/relay/webhook/pimlico`,
        {
          method: 'POST',
          body: webhookBody,
          // No X-Pimlico-Signature header
        },
      );
      ok(
        res.status === 400 && res.body.error_code === 'MISSING_SIGNATURE',
        'T-D08: Pimlico webhook missing signature -- 400',
        `Expected 400/MISSING_SIGNATURE, got ${res.status}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D09: Pimlico webhook invalid signature -> 401
    // ---------------------------------------------------------------
    {
      const webhookBody = JSON.stringify({
        type: 'user_operation.sponsorship.requested',
        data: { sender: '0xabc123' },
      });
      const res = await httpRequest(
        `${server.url}/v1/relay/webhook/pimlico`,
        {
          method: 'POST',
          headers: { 'X-Pimlico-Signature': 'totally_wrong_signature' },
          body: webhookBody,
        },
      );
      ok(
        res.status === 401 && res.body.error_code === 'INVALID_SIGNATURE',
        'T-D09: Pimlico webhook invalid signature -- 401',
        `Expected 401/INVALID_SIGNATURE, got ${res.status}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D10: Pimlico webhook unknown event type -> sponsorship denied
    // ---------------------------------------------------------------
    {
      const webhookBody = JSON.stringify({
        type: 'user_operation.some_unknown_event',
        data: { sender: '0xabc123' },
      });
      const sig = hmacSha256(PIMLICO_WEBHOOK_SECRET, webhookBody);
      const res = await httpRequest(
        `${server.url}/v1/relay/webhook/pimlico`,
        {
          method: 'POST',
          headers: { 'X-Pimlico-Signature': sig },
          body: webhookBody,
        },
      );
      ok(
        res.status === 200 &&
          res.body.sponsor === false &&
          res.body.error_code === 'UNKNOWN_EVENT',
        'T-D10: Pimlico webhook unknown event type -- sponsorship denied',
        `Expected 200/sponsor=false/UNKNOWN_EVENT, got ${res.status}/${res.body.sponsor}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D11: Pimlico webhook missing sender address -> sponsorship denied
    // ---------------------------------------------------------------
    {
      const webhookBody = JSON.stringify({
        type: 'user_operation.sponsorship.requested',
        data: {}, // no sender field
      });
      const sig = hmacSha256(PIMLICO_WEBHOOK_SECRET, webhookBody);
      const res = await httpRequest(
        `${server.url}/v1/relay/webhook/pimlico`,
        {
          method: 'POST',
          headers: { 'X-Pimlico-Signature': sig },
          body: webhookBody,
        },
      );
      ok(
        res.status === 200 &&
          res.body.sponsor === false &&
          res.body.error_code === 'MISSING_SENDER',
        'T-D11: Pimlico webhook missing sender address -- sponsorship denied',
        `Expected 200/sponsor=false/MISSING_SENDER, got ${res.status}/${res.body.sponsor}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D12: Stripe webhook missing signature -> 400
    // ---------------------------------------------------------------
    {
      const stripeBody = JSON.stringify({
        type: 'checkout.session.completed',
        data: { object: { client_reference_id: '0xWallet' } },
      });
      const res = await httpRequest(
        `${server.url}/v1/billing/webhook/stripe`,
        {
          method: 'POST',
          body: stripeBody,
          // No Stripe-Signature header
        },
      );
      ok(
        res.status === 400 && res.body.error_code === 'MISSING_SIGNATURE',
        'T-D12: Stripe webhook missing signature -- 400',
        `Expected 400/MISSING_SIGNATURE, got ${res.status}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D13: Stripe webhook invalid signature -> 400
    // ---------------------------------------------------------------
    {
      const stripeBody = JSON.stringify({
        type: 'checkout.session.completed',
        data: { object: { client_reference_id: '0xWallet' } },
      });
      const res = await httpRequest(
        `${server.url}/v1/billing/webhook/stripe`,
        {
          method: 'POST',
          headers: {
            'Stripe-Signature': 't=12345,v1=completely_wrong_signature_here',
          },
          body: stripeBody,
        },
      );
      ok(
        res.status === 400 && res.body.error_code === 'INVALID_SIGNATURE',
        'T-D13: Stripe webhook invalid signature -- 400',
        `Expected 400/INVALID_SIGNATURE, got ${res.status}/${res.body.error_code}`,
      );
    }

    // ---------------------------------------------------------------
    // T-D14: Database error during subscription check -> fail closed
    // ---------------------------------------------------------------
    {
      server.reset();
      simulateDbError = true;

      const res = await httpRequest(`${server.url}/v1/relay/sponsor`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KNOWN_AUTH_TOKEN}` },
        body: makeRelayBody(),
      });
      ok(
        res.status === 200 &&
          res.body.sponsor === false &&
          res.body.error_code === 'DB_ERROR',
        'T-D14: Database error during subscription check -- fail closed (sponsor: false)',
        `Expected 200/sponsor=false/DB_ERROR, got ${res.status}/${res.body.sponsor}/${res.body.error_code}`,
      );

      simulateDbError = false;
    }

    // ---------------------------------------------------------------
    // T-D15: UserOp hash format validation -> 400
    // ---------------------------------------------------------------
    {
      // Invalid: not hex, no 0x prefix
      const res1 = await httpRequest(
        `${server.url}/v1/relay/status/not-a-valid-hash`,
      );

      // Invalid: too short
      const res2 = await httpRequest(
        `${server.url}/v1/relay/status/0xabcdef`,
      );

      // Valid format should return 200 (0x + 64 hex chars = 66 total)
      const validHash = '0x' + 'ab'.repeat(32);
      const res3 = await httpRequest(
        `${server.url}/v1/relay/status/${validHash}`,
      );

      ok(
        res1.status === 400 &&
          res1.body.error_code === 'INVALID_FORMAT' &&
          res2.status === 400 &&
          res2.body.error_code === 'INVALID_FORMAT' &&
          res3.status === 200,
        'T-D15: UserOp hash format validation -- 400 for invalid, 200 for valid',
        `invalid1: ${res1.status}/${res1.body.error_code}, invalid2: ${res2.status}/${res2.body.error_code}, valid: ${res3.status}`,
      );
    }
  } finally {
    await server.stop();
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
