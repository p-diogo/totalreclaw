/**
 * Journey E — Cross-Device Recovery Tests
 *
 * Validates that a user can store memories on one device and recover them
 * on another using the same BIP-39 seed. Also verifies that a wrong seed
 * cannot decrypt another user's data.
 *
 * Tests:
 *   T-E01: Store memories on Device A
 *   T-E02: Recover memories on Device B (same seed)
 *   T-E03: Subscription survives cross-device recovery
 *   T-E04: Wrong seed cannot read other user's memories
 *
 * Run: cd tests/e2e-functional && npx tsx billing-tests/journey-e.test.ts
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MockSubscription {
  wallet_address: string;
  tier: 'free' | 'pro';
  source: 'stripe' | 'coinbase_commerce' | null;
  stripe_id: string | null;
  coinbase_id: string | null;
  expires_at: Date | null;
  free_writes_used: number;
  free_writes_limit: number;
  free_writes_reset_at: Date | null;
}

interface StoredFact {
  id: string;
  owner: string;
  encrypted_blob: string;
  blind_indices: string[];
  encrypted_embedding?: string;
  timestamp: string;
  content_fp?: string;
  decay_score: number;
}

// ---------------------------------------------------------------------------
// In-memory state
// ---------------------------------------------------------------------------

const subscriptions = new Map<string, MockSubscription>();
const facts = new Map<string, StoredFact[]>(); // owner (wallet) -> facts
const users = new Map<string, { user_id: string; wallet_address: string }>(); // auth_key_hash -> user record

// ---------------------------------------------------------------------------
// Deterministic test seeds (valid BIP-39 mnemonics)
// ---------------------------------------------------------------------------

// We use two distinct but valid-looking test seed phrases.
// Since we cannot actually generate valid BIP-39 in this test without the
// dependency, we simulate the crypto derivation deterministically.

const SEED_A = 'device-a-test-seed-phrase';
const SEED_B_WRONG = 'device-b-wrong-seed-phrase';

// Deterministic key derivation simulation
function deriveTestKeys(seed: string): {
  authKey: string;
  encryptionKey: Buffer;
  dedupKey: Buffer;
  walletAddress: string;
  authKeyHash: string;
} {
  // Derive deterministic keys from seed using HKDF-like chain with SHA-256
  const seedBuf = Buffer.from(seed, 'utf8');
  const authKey = crypto.createHash('sha256').update(Buffer.concat([seedBuf, Buffer.from('auth')])).digest();
  const encryptionKey = crypto.createHash('sha256').update(Buffer.concat([seedBuf, Buffer.from('encryption')])).digest();
  const dedupKey = crypto.createHash('sha256').update(Buffer.concat([seedBuf, Buffer.from('dedup')])).digest();
  const walletRaw = crypto.createHash('sha256').update(Buffer.concat([seedBuf, Buffer.from('wallet')])).digest();
  const walletAddress = '0x' + walletRaw.subarray(0, 20).toString('hex');
  const authKeyHash = crypto.createHash('sha256').update(authKey).digest('hex');

  return {
    authKey: authKey.toString('hex'),
    encryptionKey,
    dedupKey,
    walletAddress,
    authKeyHash,
  };
}

// AES-256-GCM encrypt/decrypt
function testEncrypt(plaintext: string, key: Buffer): string {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv, { authTagLength: 16 });
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, ciphertext]).toString('base64');
}

function testDecrypt(encryptedBase64: string, key: Buffer): string {
  const combined = Buffer.from(encryptedBase64, 'base64');
  const iv = combined.subarray(0, 12);
  const tag = combined.subarray(12, 28);
  const ciphertext = combined.subarray(28);
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv, { authTagLength: 16 });
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
}

function generateBlindIndex(token: string): string {
  return crypto.createHash('sha256').update(token.toLowerCase()).digest('hex');
}

// ---------------------------------------------------------------------------
// Mock HTTP Server
// ---------------------------------------------------------------------------

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
  });
}

function json(res: http.ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

function resetState(): void {
  subscriptions.clear();
  facts.clear();
  users.clear();
}

async function startMockServer(): Promise<{ url: string; server: http.Server; stop: () => Promise<void> }> {
  const server = http.createServer(async (req, res) => {
    try {
      const url = req.url ?? '/';
      const method = req.method ?? 'GET';

      // ---------------------------------------------------------------
      // POST /v1/register
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/register') {
        const body = JSON.parse(await readBody(req));
        const { auth_key_hash } = body;
        let record = users.get(auth_key_hash);
        if (!record) {
          record = {
            user_id: `user-${crypto.randomUUID().slice(0, 8)}`,
            wallet_address: body.wallet_address || '',
          };
          users.set(auth_key_hash, record);
        }
        json(res, 200, { success: true, user_id: record.user_id });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/store — Store encrypted facts keyed by owner (wallet)
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/store') {
        const body = JSON.parse(await readBody(req));
        const { owner, facts: incoming } = body as {
          owner: string;
          facts: Array<{
            id: string;
            encrypted_blob: string;
            blind_indices: string[];
            encrypted_embedding?: string;
            timestamp: string;
            content_fp?: string;
            decay_score?: number;
          }>;
        };

        const ownerKey = owner.toLowerCase();
        if (!facts.has(ownerKey)) {
          facts.set(ownerKey, []);
        }
        const store = facts.get(ownerKey)!;
        const ids: string[] = [];

        for (const f of incoming) {
          store.push({
            id: f.id,
            owner: ownerKey,
            encrypted_blob: f.encrypted_blob,
            blind_indices: f.blind_indices,
            encrypted_embedding: f.encrypted_embedding,
            timestamp: f.timestamp || new Date().toISOString(),
            content_fp: f.content_fp,
            decay_score: f.decay_score ?? 1.0,
          });
          ids.push(f.id);
        }

        json(res, 200, { success: true, ids });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/search — Search by blind trapdoor intersection
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/search') {
        const body = JSON.parse(await readBody(req));
        const { owner, trapdoors, max_candidates } = body as {
          owner: string;
          trapdoors: string[];
          max_candidates?: number;
        };

        const ownerKey = owner.toLowerCase();
        const store = facts.get(ownerKey) || [];
        const trapdoorSet = new Set(trapdoors);
        const limit = max_candidates || 100;

        const matches = store
          .map((fact) => {
            const matchCount = fact.blind_indices.filter((idx) => trapdoorSet.has(idx)).length;
            return { fact, matchCount };
          })
          .filter(({ matchCount }) => matchCount > 0)
          .sort((a, b) => b.matchCount - a.matchCount)
          .slice(0, limit);

        const results = matches.map(({ fact }) => ({
          fact_id: fact.id,
          encrypted_blob: fact.encrypted_blob,
          decay_score: fact.decay_score,
          timestamp: new Date(fact.timestamp).getTime(),
          encrypted_embedding: fact.encrypted_embedding,
        }));

        json(res, 200, { success: true, results });
        return;
      }

      // ---------------------------------------------------------------
      // GET /v1/billing/status — Subscription status by wallet
      // ---------------------------------------------------------------
      if (method === 'GET' && url.startsWith('/v1/billing/status')) {
        const parsedUrl = new URL(url, `http://${req.headers.host}`);
        const wallet = (parsedUrl.searchParams.get('wallet_address') || '').toLowerCase();
        const sub = subscriptions.get(wallet);

        if (!sub) {
          json(res, 200, {
            success: true,
            wallet_address: wallet,
            tier: 'free',
            source: null,
            expires_at: null,
            free_writes_used: 0,
            free_writes_limit: 100,
          });
          return;
        }

        json(res, 200, {
          success: true,
          wallet_address: sub.wallet_address,
          tier: sub.tier,
          source: sub.source,
          expires_at: sub.expires_at?.toISOString() ?? null,
          free_writes_used: sub.free_writes_used,
          free_writes_limit: sub.free_writes_limit,
        });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/billing/checkout — Create Stripe checkout URL
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/billing/checkout') {
        const body = JSON.parse(await readBody(req));
        const { wallet_address } = body;
        json(res, 200, {
          success: true,
          checkout_url: `https://checkout.stripe.com/test/session_${wallet_address.slice(2, 10)}`,
        });
        return;
      }

      // ---------------------------------------------------------------
      // POST /v1/relay/sponsor — Check subscription, return success/failure
      // ---------------------------------------------------------------
      if (method === 'POST' && url === '/v1/relay/sponsor') {
        const body = JSON.parse(await readBody(req));
        const wallet = (body.wallet_address || '').toLowerCase();
        const sub = subscriptions.get(wallet);

        // Pro tier: always sponsor
        if (sub && sub.tier === 'pro') {
          json(res, 200, { success: true, sponsored: true });
          return;
        }

        // Free tier: check quota
        const used = sub?.free_writes_used ?? 0;
        const limit = sub?.free_writes_limit ?? 100;
        if (used >= limit) {
          json(res, 200, { success: false, reason: 'upgrade_required' });
          return;
        }

        // Increment free writes
        if (sub) {
          sub.free_writes_used += 1;
        } else {
          subscriptions.set(wallet, {
            wallet_address: wallet,
            tier: 'free',
            source: null,
            stripe_id: null,
            coinbase_id: null,
            expires_at: null,
            free_writes_used: 1,
            free_writes_limit: 100,
            free_writes_reset_at: null,
          });
        }

        json(res, 200, { success: true, sponsored: true });
        return;
      }

      json(res, 404, { error: 'Not found' });
    } catch (err) {
      json(res, 500, { error: err instanceof Error ? err.message : String(err) });
    }
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address() as { port: number };
      const url = `http://127.0.0.1:${addr.port}`;
      resolve({
        url,
        server,
        stop: () => new Promise<void>((r) => server.close(() => r())),
      });
    });
  });
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function httpPost(url: string, body: unknown): Promise<{ status: number; data: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const postData = JSON.stringify(body);
    const req = http.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf8');
          resolve({ status: res.statusCode ?? 500, data: JSON.parse(raw) });
        });
      },
    );
    req.on('error', reject);
    req.write(postData);
    req.end();
  });
}

async function httpGet(url: string): Promise<{ status: number; data: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = http.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname + parsed.search,
        method: 'GET',
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf8');
          resolve({ status: res.statusCode ?? 500, data: JSON.parse(raw) });
        });
      },
    );
    req.on('error', reject);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// TAP test runner
// ---------------------------------------------------------------------------

let testNumber = 0;
let passed = 0;
let failed = 0;

function ok(condition: boolean, description: string, detail?: string): void {
  testNumber++;
  if (condition) {
    console.log(`ok ${testNumber} - ${description}`);
    passed++;
  } else {
    console.log(`not ok ${testNumber} - ${description}`);
    if (detail) console.log(`  ---\n  message: ${detail}\n  ...`);
    failed++;
  }
}

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const TEST_FACTS = [
  'User prefers dark mode for all applications',
  'User lives in Lisbon, Portugal',
  'User is allergic to shellfish',
  'User works as a software engineer at Acme Corp',
  'User has a dog named Max',
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

async function runTests(): Promise<void> {
  const mock = await startMockServer();

  try {
    const keysA = deriveTestKeys(SEED_A);
    const keysWrong = deriveTestKeys(SEED_B_WRONG);

    // Verify deterministic derivation: same seed -> same wallet
    const keysA2 = deriveTestKeys(SEED_A);
    ok(
      keysA.walletAddress === keysA2.walletAddress,
      'T-E01 prereq: Same seed produces same wallet address',
      `${keysA.walletAddress} !== ${keysA2.walletAddress}`,
    );
    ok(
      keysA.encryptionKey.equals(keysA2.encryptionKey),
      'T-E01 prereq: Same seed produces same encryption key',
    );

    // Verify different seeds produce different wallets
    ok(
      keysA.walletAddress !== keysWrong.walletAddress,
      'T-E01 prereq: Different seeds produce different wallet addresses',
      `Both produced ${keysA.walletAddress}`,
    );

    // -----------------------------------------------------------------
    // T-E01: Store memories on Device A
    // -----------------------------------------------------------------

    // Register user A
    const regA = await httpPost(`${mock.url}/v1/register`, {
      auth_key_hash: keysA.authKeyHash,
      wallet_address: keysA.walletAddress,
    });
    ok(regA.data.success === true, 'T-E01: Register Device A succeeds');

    // Store 5 encrypted facts
    const encryptedFacts = TEST_FACTS.map((text, i) => {
      const encrypted = testEncrypt(text, keysA.encryptionKey);
      const tokens = text.toLowerCase().split(/\s+/).filter((t) => t.length >= 2);
      const blindIndices = tokens.map((t) => generateBlindIndex(t));
      return {
        id: `fact-${i + 1}`,
        encrypted_blob: encrypted,
        blind_indices: blindIndices,
        timestamp: new Date().toISOString(),
        content_fp: crypto.createHmac('sha256', keysA.dedupKey).update(text.toLowerCase()).digest('hex'),
        decay_score: 1.0,
      };
    });

    const storeResult = await httpPost(`${mock.url}/v1/store`, {
      owner: keysA.walletAddress,
      facts: encryptedFacts,
    });
    ok(storeResult.data.success === true, 'T-E01: Store 5 facts on Device A succeeds');

    const storedIds = storeResult.data.ids as string[];
    ok(storedIds.length === 5, 'T-E01: All 5 fact IDs returned', `Got ${storedIds.length}`);

    // Verify facts are in the store
    const ownerKey = keysA.walletAddress.toLowerCase();
    const storedForA = facts.get(ownerKey) || [];
    ok(storedForA.length === 5, 'T-E01: 5 facts stored in mock for wallet A', `Got ${storedForA.length}`);

    // Record wallet W for cross-reference
    const walletW = keysA.walletAddress;

    // -----------------------------------------------------------------
    // T-E02: Recover memories on Device B (same seed S -> same wallet W)
    // -----------------------------------------------------------------

    // Re-derive keys from the SAME seed (simulating a new device)
    const keysDeviceB = deriveTestKeys(SEED_A);

    ok(
      keysDeviceB.walletAddress === walletW,
      'T-E02: Same seed produces same wallet W on Device B',
      `${keysDeviceB.walletAddress} !== ${walletW}`,
    );

    // Register on "Device B" (should get same/compatible user)
    const regB = await httpPost(`${mock.url}/v1/register`, {
      auth_key_hash: keysDeviceB.authKeyHash,
      wallet_address: keysDeviceB.walletAddress,
    });
    ok(regB.data.success === true, 'T-E02: Register Device B succeeds');

    // Search for facts using a trapdoor from fact #1 ("dark mode")
    const searchTrapdoor = generateBlindIndex('dark');
    const searchResult = await httpPost(`${mock.url}/v1/search`, {
      owner: keysDeviceB.walletAddress,
      trapdoors: [searchTrapdoor],
      max_candidates: 100,
    });
    ok(searchResult.data.success === true, 'T-E02: Search on Device B succeeds');

    const searchResults = searchResult.data.results as Array<{ encrypted_blob: string; fact_id: string }>;
    ok(
      searchResults.length >= 1,
      'T-E02: At least 1 fact matches trapdoor "dark"',
      `Got ${searchResults.length}`,
    );

    // Decrypt ALL stored facts with Device B's key (same as Device A's)
    let decryptedCount = 0;
    const decryptedTexts: string[] = [];
    for (const stored of storedForA) {
      try {
        const plaintext = testDecrypt(stored.encrypted_blob, keysDeviceB.encryptionKey);
        decryptedTexts.push(plaintext);
        decryptedCount++;
      } catch {
        // decryption failed
      }
    }

    ok(
      decryptedCount === 5,
      'T-E02: Device B decrypts all 5 facts with same seed',
      `Decrypted ${decryptedCount}/5`,
    );

    // Verify the decrypted content matches the originals
    const allMatch = TEST_FACTS.every((original) => decryptedTexts.includes(original));
    ok(
      allMatch,
      'T-E02: All decrypted facts match original plaintext',
      `Missing: ${TEST_FACTS.filter((t) => !decryptedTexts.includes(t)).join(', ')}`,
    );

    // -----------------------------------------------------------------
    // T-E03: Subscription survives cross-device recovery
    // -----------------------------------------------------------------

    // Set up a pro subscription for wallet W
    subscriptions.set(walletW.toLowerCase(), {
      wallet_address: walletW.toLowerCase(),
      tier: 'pro',
      source: 'stripe',
      stripe_id: 'sub_test_123',
      coinbase_id: null,
      expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000), // 30 days
      free_writes_used: 50,
      free_writes_limit: 100,
      free_writes_reset_at: null,
    });

    // Check subscription from Device A
    const statusA = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(walletW)}`,
    );
    ok(statusA.data.tier === 'pro', 'T-E03: Device A sees pro subscription');
    ok(statusA.data.source === 'stripe', 'T-E03: Device A sees stripe source');

    // Check subscription from Device B (same wallet)
    const statusB = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(keysDeviceB.walletAddress)}`,
    );
    ok(
      statusB.data.tier === 'pro',
      'T-E03: Device B sees same pro subscription (same wallet)',
      `Got tier: ${statusB.data.tier}`,
    );
    ok(
      statusB.data.source === 'stripe',
      'T-E03: Device B sees same stripe source',
    );

    // Relay sponsor check from Device B should succeed (pro tier)
    const sponsorB = await httpPost(`${mock.url}/v1/relay/sponsor`, {
      wallet_address: keysDeviceB.walletAddress,
    });
    ok(
      sponsorB.data.success === true && sponsorB.data.sponsored === true,
      'T-E03: Device B relay sponsorship succeeds (pro subscription)',
    );

    // -----------------------------------------------------------------
    // T-E04: Wrong seed cannot read other user's memories
    // -----------------------------------------------------------------

    // Verify different wallet
    ok(
      keysWrong.walletAddress !== walletW,
      'T-E04: Wrong seed produces different wallet address',
      `Wrong wallet ${keysWrong.walletAddress} === ${walletW}`,
    );

    // Search from wrong wallet — no facts exist for this wallet
    const wrongSearch = await httpPost(`${mock.url}/v1/search`, {
      owner: keysWrong.walletAddress,
      trapdoors: [searchTrapdoor],
      max_candidates: 100,
    });
    const wrongResults = wrongSearch.data.results as Array<{ encrypted_blob: string }>;
    ok(
      wrongResults.length === 0,
      'T-E04: Wrong seed wallet has 0 facts (different owner namespace)',
      `Got ${wrongResults.length} results`,
    );

    // Even if attacker somehow gets the ciphertext, wrong key fails decryption
    let decryptionFailed = false;
    try {
      testDecrypt(storedForA[0].encrypted_blob, keysWrong.encryptionKey);
      decryptionFailed = false; // Should not reach here
    } catch {
      decryptionFailed = true;
    }
    ok(
      decryptionFailed,
      'T-E04: AES-GCM decryption with wrong key throws authentication error',
    );

    // Verify wrong seed gets no subscription
    const statusWrong = await httpGet(
      `${mock.url}/v1/billing/status?wallet_address=${encodeURIComponent(keysWrong.walletAddress)}`,
    );
    ok(
      statusWrong.data.tier === 'free',
      'T-E04: Wrong seed wallet has free tier (no subscription)',
      `Got tier: ${statusWrong.data.tier}`,
    );

    // Wrong seed cannot access Device A's subscription
    ok(
      statusWrong.data.source === null || statusWrong.data.source === undefined,
      'T-E04: Wrong seed wallet has no payment source',
    );
  } finally {
    await mock.stop();
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

console.log('TAP version 14');
console.log('1..23');

runTests()
  .then(() => {
    console.log(`\n# Tests: ${testNumber}`);
    console.log(`# Pass:  ${passed}`);
    console.log(`# Fail:  ${failed}`);
    if (failed > 0) process.exit(1);
  })
  .catch((err) => {
    console.log(`Bail out! ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  });
