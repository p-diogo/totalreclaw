/**
 * Tests for the prod-vs-staging signal on the MCP ``totalreclaw_status`` tool.
 *
 * The relay's 250/month production cap is NOT enforced by the staging
 * relay (``api-staging.totalreclaw.xyz``). The tool must:
 *   1. Return ``environment="production"`` for the prod relay and emit NO
 *      ``staging_note`` (production users must never see staging mentioned).
 *   2. Return ``environment="staging"`` for the staging relay AND include
 *      a ``staging_note`` explaining the cap is not enforced.
 *   3. Infer ``environment`` from the relay URL when the relay response
 *      doesn't carry the field explicitly.
 */
import { handleStatus, type BillingStatusResponse } from '../src/tools/status.js';

type FetchLike = (url: string, init?: unknown) => Promise<{
  ok: boolean;
  status?: number;
  statusText?: string;
  text?: () => Promise<string>;
  json: () => Promise<BillingStatusResponse>;
}>;

const realFetch = (globalThis as { fetch?: FetchLike }).fetch;

function mockBillingFetch(response: Partial<BillingStatusResponse>): FetchLike {
  const full: BillingStatusResponse = {
    tier: 'free',
    free_writes_used: 30,
    free_writes_limit: 250,
    expires_at: null,
    ...response,
  };
  return async () => ({
    ok: true,
    json: async () => full,
  });
}

function setFetch(fn: FetchLike) {
  (globalThis as { fetch: FetchLike }).fetch = fn;
}

afterEach(() => {
  if (realFetch) {
    (globalThis as { fetch?: FetchLike }).fetch = realFetch;
  } else {
    delete (globalThis as { fetch?: FetchLike }).fetch;
  }
});

async function callStatus(serverUrl: string): Promise<Record<string, unknown>> {
  const result = await handleStatus(serverUrl, 'auth-key-hex', {
    wallet_address: '0xabc123',
  });
  return JSON.parse(result.content[0].text) as Record<string, unknown>;
}

describe('MCP status tool — production environment', () => {
  test('production relay URL omits staging_note', async () => {
    setFetch(mockBillingFetch({}));
    const payload = await callStatus('https://api.totalreclaw.xyz');

    expect(payload.environment).toBe('production');
    expect(payload.tier).toBe('free');
    expect(payload.free_writes_limit).toBe(250);
    expect(payload.period).toBe('monthly');
    // CRITICAL: production users must NEVER see staging mentioned.
    expect(payload).not.toHaveProperty('staging_note');
    expect((payload.formatted as string).toLowerCase()).not.toContain('staging');
  });

  test('relay-provided environment="production" overrides URL inference', async () => {
    setFetch(mockBillingFetch({ environment: 'production' }));
    const payload = await callStatus('https://api-staging.totalreclaw.xyz');

    // Even though the URL says staging, the relay's explicit
    // environment=production wins. (Unlikely in practice but the contract
    // says relay-provided field beats URL inference.)
    expect(payload.environment).toBe('production');
    expect(payload).not.toHaveProperty('staging_note');
  });
});

describe('MCP status tool — staging environment', () => {
  test('staging relay URL emits staging_note', async () => {
    setFetch(mockBillingFetch({
      tier: 'free',
      free_writes_used: 500,  // Past the production cap.
      free_writes_limit: 250,
    }));
    const payload = await callStatus('https://api-staging.totalreclaw.xyz');

    expect(payload.environment).toBe('staging');
    expect(payload).toHaveProperty('staging_note');
    const note = payload.staging_note as string;
    // Note must explain BOTH the staging behavior AND the production cap.
    expect(note.toLowerCase()).toContain('staging');
    expect(note).toMatch(/not enforced/i);
    expect(note).toContain('250');
    expect(note).toContain('api-staging.totalreclaw.xyz');
    expect(note).toContain('api.totalreclaw.xyz');
    // Formatted output must surface the note for the LLM.
    expect((payload.formatted as string).toLowerCase()).toContain('staging');
  });

  test('relay-provided environment="staging" overrides URL inference', async () => {
    setFetch(mockBillingFetch({ environment: 'staging' }));
    const payload = await callStatus('https://api.totalreclaw.xyz');

    expect(payload.environment).toBe('staging');
    expect(payload).toHaveProperty('staging_note');
  });

  test('staging note text is identical across calls (deterministic contract)', async () => {
    setFetch(mockBillingFetch({ environment: 'staging' }));
    const a = await callStatus('https://api-staging.totalreclaw.xyz');
    const b = await callStatus('https://api-staging.totalreclaw.xyz');
    expect(a.staging_note).toBe(b.staging_note);
  });
});

describe('MCP status tool — URL inference fallback', () => {
  test('self-hosted URL defaults to production', async () => {
    setFetch(mockBillingFetch({}));
    const payload = await callStatus('https://my-self-hosted-relay.example.com');
    expect(payload.environment).toBe('production');
    expect(payload).not.toHaveProperty('staging_note');
  });

  test('localhost defaults to production', async () => {
    setFetch(mockBillingFetch({}));
    const payload = await callStatus('http://localhost:8000');
    expect(payload.environment).toBe('production');
  });

  test('case-insensitive staging match', async () => {
    setFetch(mockBillingFetch({}));
    const payload = await callStatus('HTTPS://API-STAGING.totalreclaw.xyz');
    expect(payload.environment).toBe('staging');
  });
});
