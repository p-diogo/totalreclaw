/**
 * Regression tests for #439 — MCP managed-service write path must resolve
 * chain + DataEdge from the relay's authoritative billing response, and
 * thread both into the on-chain write config.
 *
 * Before this fix the MCP server:
 *   1. never threaded any chainId into getSubgraphConfig → every managed
 *      write (free AND pro) fell to the getSubgraphConfig default 84532
 *      (Base Sepolia — retired at ops-1), including pro (the local
 *      `chainId=100` flip was a dead write, never read).
 *   2. never threaded dataEdgeAddress → writes hit the PROD DataEdge
 *      (0xC445…) even on staging, so the staging subgraph never saw them.
 *   3. never read billing.chain_id / billing.data_edge_address at all.
 *
 * Sibling of the OpenClaw plugin fixes #402 (chain_id verbatim) and #460
 * (data_edge_address verbatim). The client-consistency contract is: consume
 * the relay's authoritative values verbatim.
 */

import {
  resolveChainConfig,
  buildSubgraphOverrides,
  fetchChainConfig,
} from '../src/subgraph/chain-config.js';
import { getSubgraphConfig, resolveOwnerAccount } from '../src/subgraph/store.js';

const STAGING_DATA_EDGE = '0xE7a4D2677B686e13775Ba9092631089e35F0BB91';
const PROD_DATA_EDGE = '0xC445af1D4EB9fce4e1E61fE96ea7B8feBF03c5ca';

describe('resolveChainConfig — verbatim billing consumption (#439)', () => {
  it('reads chain_id + data_edge_address verbatim from a free-tier billing response', () => {
    const resolved = resolveChainConfig({
      tier: 'free',
      chain_id: 100,
      data_edge_address: STAGING_DATA_EDGE,
    });
    expect(resolved.chainId).toBe(100);
    expect(resolved.dataEdgeAddress).toBe(STAGING_DATA_EDGE);
  });

  it('defaults chainId to 100 (Gnosis, post-ops-1) when billing omits chain_id', () => {
    // RED under the old code: default was 84532 (Base Sepolia).
    const resolved = resolveChainConfig({ tier: 'free' });
    expect(resolved.chainId).toBe(100);
    expect(resolved.dataEdgeAddress).toBeUndefined();
  });

  it('defaults chainId to 100 when billing is null (relay unreachable)', () => {
    const resolved = resolveChainConfig(null);
    expect(resolved.chainId).toBe(100);
    expect(resolved.dataEdgeAddress).toBeUndefined();
  });

  it('ignores a malformed data_edge_address (falls through to env/default)', () => {
    const resolved = resolveChainConfig({
      chain_id: 100,
      data_edge_address: 'not-an-address',
    });
    expect(resolved.dataEdgeAddress).toBeUndefined();
  });

  it('ignores a non-hex / wrong-length data_edge_address', () => {
    expect(resolveChainConfig({ data_edge_address: '0x1234' }).dataEdgeAddress).toBeUndefined();
    expect(resolveChainConfig({ data_edge_address: 42 as unknown as string }).dataEdgeAddress).toBeUndefined();
  });

  it('ignores a non-numeric chain_id (falls to 100)', () => {
    expect(resolveChainConfig({ chain_id: 'gnosis' as unknown as number }).chainId).toBe(100);
  });
});

describe('buildSubgraphOverrides — threads chain + DataEdge into the write config (#439)', () => {
  const base = {
    relayUrl: 'https://api-staging.totalreclaw.xyz',
    mnemonic: 'test test test',
    authKeyHex: 'aa',
    walletAddress: '0x2c0CF74B2b76110708CA431796367779e3738250',
    chainId: 100,
    dataEdgeAddress: STAGING_DATA_EDGE,
  };

  const savedEnv = process.env.TOTALRECLAW_DATA_EDGE_ADDRESS;
  afterEach(() => {
    if (savedEnv === undefined) delete process.env.TOTALRECLAW_DATA_EDGE_ADDRESS;
    else process.env.TOTALRECLAW_DATA_EDGE_ADDRESS = savedEnv;
  });

  it('the final write config carries chainId 100 + the staging DataEdge', () => {
    delete process.env.TOTALRECLAW_DATA_EDGE_ADDRESS;
    // RED under the old code: getSubgraphConfig({4 keys}) → chainId 84532 + prod DataEdge.
    const cfg = getSubgraphConfig(buildSubgraphOverrides(base));
    expect(cfg.chainId).toBe(100);
    expect(cfg.dataEdgeAddress).toBe(STAGING_DATA_EDGE);
    // Sanity: the passthrough keys survive.
    expect(cfg.relayUrl).toBe(base.relayUrl);
    expect(cfg.walletAddress).toBe(base.walletAddress);
    expect(cfg.authKeyHex).toBe(base.authKeyHex);
  });

  it('env TOTALRECLAW_DATA_EDGE_ADDRESS wins over the billing-derived DataEdge', () => {
    process.env.TOTALRECLAW_DATA_EDGE_ADDRESS = PROD_DATA_EDGE;
    const cfg = getSubgraphConfig(buildSubgraphOverrides(base));
    // billing said staging, but the explicit env override must win.
    expect(cfg.dataEdgeAddress).toBe(PROD_DATA_EDGE);
    // chainId still threaded from billing.
    expect(cfg.chainId).toBe(100);
  });

  it('omits dataEdgeAddress when billing did not supply one (env/default takes over)', () => {
    delete process.env.TOTALRECLAW_DATA_EDGE_ADDRESS;
    const overrides = buildSubgraphOverrides({ ...base, dataEdgeAddress: undefined });
    expect('dataEdgeAddress' in overrides).toBe(false);
    // chainId is always threaded.
    expect(overrides.chainId).toBe(100);
  });
});

describe('buildSubgraphOverrides — bundle-mode signing (Option E Phase 2 / #581, P2-13)', () => {
  const bundlePrivateKeyHex = '1ab42cc412b618bdea3a599e3c9bae199ebf030895b039e9db1e30dafb12b727';

  it('threads ownerPrivateKeyHex instead of mnemonic when the caller is bundle-configured', () => {
    const overrides = buildSubgraphOverrides({
      relayUrl: 'https://api-staging.totalreclaw.xyz',
      ownerPrivateKeyHex: bundlePrivateKeyHex,
      authKeyHex: 'aa',
      walletAddress: '0x2c0CF74B2b76110708CA431796367779e3738250',
      chainId: 100,
      dataEdgeAddress: STAGING_DATA_EDGE,
    });
    expect(overrides.ownerPrivateKeyHex).toBe(bundlePrivateKeyHex);
    expect('mnemonic' in overrides).toBe(false);
    // The resulting config can actually resolve a signer — proves the
    // wiring is load-bearing, not just a field being copied.
    const cfg = getSubgraphConfig(overrides);
    expect(() => resolveOwnerAccount(cfg)).not.toThrow();
  });

  it('threads mnemonic (not ownerPrivateKeyHex) when the caller is mnemonic-configured', () => {
    const overrides = buildSubgraphOverrides({
      relayUrl: 'https://api-staging.totalreclaw.xyz',
      mnemonic: 'test test test',
      authKeyHex: 'aa',
      walletAddress: '0x2c0CF74B2b76110708CA431796367779e3738250',
      chainId: 100,
      dataEdgeAddress: STAGING_DATA_EDGE,
    });
    expect(overrides.mnemonic).toBe('test test test');
    expect('ownerPrivateKeyHex' in overrides).toBe(false);
  });
});

describe('fetchChainConfig — the single billing-fetch path shared by mnemonic-mode and bundle-mode init (P2-13)', () => {
  const STAGING_HEADERS = { 'X-TotalReclaw-Client': 'test-client' };

  function mockFetchOk(body: Record<string, unknown>): typeof fetch {
    return jest.fn().mockResolvedValue({
      ok: true,
      json: async () => body,
    }) as unknown as typeof fetch;
  }

  function mockFetchUnreachable(): typeof fetch {
    return jest.fn().mockRejectedValue(new Error('network unreachable')) as unknown as typeof fetch;
  }

  it(
    'REGRESSION (Lesson 1): a bundle-configured client on a staging-configured relay ' +
      'resolves the STAGING DataEdge, never the core prod default — proving the billing ' +
      'fetch actually ran instead of being skipped because the bundle already "knows" chain_id',
    async () => {
      const fetchImpl = mockFetchOk({
        tier: 'free',
        chain_id: 100,
        data_edge_address: STAGING_DATA_EDGE,
      });
      const resolved = await fetchChainConfig({
        serverUrl: 'https://api-staging.totalreclaw.xyz',
        smartAccountAddress: '0x2c0CF74B2b76110708CA431796367779e3738250',
        authKeyHex: 'aa',
        headers: STAGING_HEADERS,
        // Bundle-mode's fallback would be bundle.account.chain_id (also 100
        // under the single-chain policy) — the point of this test is that
        // dataEdgeAddress, which the bundle can NEVER supply on its own,
        // came from the billing call.
        fallbackChainId: 100,
        fetchImpl,
      });
      expect(resolved.dataEdgeAddress).toBe(STAGING_DATA_EDGE);
      expect(resolved.dataEdgeAddress).not.toBe(PROD_DATA_EDGE);
      expect(fetchImpl).toHaveBeenCalledTimes(1);
      const [calledUrl] = (fetchImpl as jest.Mock).mock.calls[0];
      expect(String(calledUrl)).toContain('/v1/billing/status');
      expect(String(calledUrl)).toContain('wallet_address=');
    },
  );

  it('falls back to fallbackChainId (the bundle\'s own account.chain_id) when billing is unreachable — never silently 84532', async () => {
    const resolved = await fetchChainConfig({
      serverUrl: 'https://api-staging.totalreclaw.xyz',
      smartAccountAddress: '0x2c0CF74B2b76110708CA431796367779e3738250',
      authKeyHex: 'aa',
      fallbackChainId: 100,
      fetchImpl: mockFetchUnreachable(),
    });
    expect(resolved.chainId).toBe(100);
    expect(resolved.dataEdgeAddress).toBeUndefined();
  });

  it('falls back when billing responds non-200', async () => {
    const fetchImpl = jest.fn().mockResolvedValue({ ok: false, status: 500 }) as unknown as typeof fetch;
    const resolved = await fetchChainConfig({
      serverUrl: 'https://api-staging.totalreclaw.xyz',
      smartAccountAddress: '0x2c0CF74B2b76110708CA431796367779e3738250',
      authKeyHex: 'aa',
      fallbackChainId: 100,
      fetchImpl,
    });
    expect(resolved.chainId).toBe(100);
  });

  it('sends the auth key as a Bearer token and merges extra headers', async () => {
    const fetchImpl = mockFetchOk({ tier: 'free', chain_id: 100 });
    await fetchChainConfig({
      serverUrl: 'https://api-staging.totalreclaw.xyz',
      smartAccountAddress: '0x2c0CF74B2b76110708CA431796367779e3738250',
      authKeyHex: 'deadbeef',
      headers: STAGING_HEADERS,
      fallbackChainId: 100,
      fetchImpl,
    });
    const [, requestInit] = (fetchImpl as jest.Mock).mock.calls[0];
    expect(requestInit.headers.Authorization).toBe('Bearer deadbeef');
    expect(requestInit.headers['X-TotalReclaw-Client']).toBe('test-client');
  });
});
