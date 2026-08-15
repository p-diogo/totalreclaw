/**
 * Chain + DataEdge resolution for the managed-service (subgraph) write path.
 *
 * Client-consistency contract (#439, sibling of the OpenClaw plugin #402/#460):
 * the relay returns authoritative `chain_id` + `data_edge_address` in
 * `GET /v1/billing/status`; chain-aware clients consume them verbatim so a
 * future chain change needs zero client release. Both tiers run on Gnosis
 * (chain 100) after ops-1 — the legacy Free → Base Sepolia (84532) routing
 * was retired, so the local default here is 100, not 84532.
 */

import type { SubgraphStoreConfig } from './store.js';

/** Default chain when billing is silent — Gnosis mainnet (single-chain, both tiers). */
const DEFAULT_CHAIN_ID = 100;

/** A DataEdge address is a 20-byte hex string. Reject anything else. */
const DATA_EDGE_RE = /^0x[0-9a-fA-F]{40}$/;

export interface ResolvedChainConfig {
  /** Chain to submit the write to (verbatim from billing, else Gnosis 100). */
  chainId: number;
  /** DataEdge contract from billing, or undefined to fall through to env/default. */
  dataEdgeAddress?: string;
}

/**
 * Resolve chain + DataEdge from a `/v1/billing/status` response.
 *
 * - `chain_id`: used verbatim when a finite number; otherwise Gnosis (100).
 * - `data_edge_address`: used only when a valid `0x…40hex` string; otherwise
 *   left undefined so the caller falls through to env / the store default.
 */
export function resolveChainConfig(
  billing: Record<string, unknown> | null | undefined,
): ResolvedChainConfig {
  let chainId = DEFAULT_CHAIN_ID;
  const rawChain = billing?.chain_id;
  if (typeof rawChain === 'number' && Number.isFinite(rawChain)) {
    chainId = rawChain;
  }

  let dataEdgeAddress: string | undefined;
  const rawEdge = billing?.data_edge_address;
  if (typeof rawEdge === 'string' && DATA_EDGE_RE.test(rawEdge)) {
    dataEdgeAddress = rawEdge;
  }

  return { chainId, dataEdgeAddress };
}

export interface WriteConfigInput {
  relayUrl: string;
  /**
   * Exactly one of `mnemonic` / `ownerPrivateKeyHex` must be set (Option E
   * Phase 2 / #581, P2-13). Mnemonic-mode clients set `mnemonic`;
   * bundle-mode clients (no mnemonic anywhere in the process — derived-
   * bundle-v1.md §4.6 point 1) set `ownerPrivateKeyHex` from
   * `bundle.signing.private_key` instead. `store.ts`'s
   * `resolveOwnerAccount` prefers `ownerPrivateKeyHex` when both happen to
   * be present (never expected in practice, but privateKey is the more
   * direct source of truth so it wins rather than erroring).
   */
  mnemonic?: string;
  /** Bundle-mode signing key — 64 lowercase hex chars, no `0x` prefix. */
  ownerPrivateKeyHex?: string;
  authKeyHex: string;
  walletAddress: string;
  chainId: number;
  dataEdgeAddress?: string;
}

/**
 * Build the `getSubgraphConfig` override object for a managed-service write,
 * threading the billing-resolved chainId + DataEdge alongside the relay creds.
 *
 * Precedence for DataEdge: an explicit `TOTALRECLAW_DATA_EDGE_ADDRESS` env var
 * must win. Because a passed override key supersedes env inside
 * getSubgraphConfig's merge, we inject the billing-derived DataEdge ONLY when
 * the env override is unset — mirroring the plugin's env || billing || default
 * ordering.
 */
export function buildSubgraphOverrides(
  input: WriteConfigInput,
): Partial<SubgraphStoreConfig> {
  const overrides: Partial<SubgraphStoreConfig> = {
    relayUrl: input.relayUrl,
    authKeyHex: input.authKeyHex,
    walletAddress: input.walletAddress,
  };

  // Exactly one signing source is threaded through — never both, and never
  // neither (store.ts's resolveOwnerAccount throws an actionable error if
  // neither ends up present on the final merged config).
  if (input.ownerPrivateKeyHex) {
    overrides.ownerPrivateKeyHex = input.ownerPrivateKeyHex;
  } else if (input.mnemonic) {
    overrides.mnemonic = input.mnemonic;
  }

  // Only thread a finite chainId — never let an undefined clobber the store's
  // Gnosis (100) default via the spread merge.
  if (typeof input.chainId === 'number' && Number.isFinite(input.chainId)) {
    overrides.chainId = input.chainId;
  }

  if (input.dataEdgeAddress && !process.env.TOTALRECLAW_DATA_EDGE_ADDRESS) {
    overrides.dataEdgeAddress = input.dataEdgeAddress;
  }

  return overrides;
}

// ---------------------------------------------------------------------------
// Billing fetch — the SINGLE code path both mnemonic-mode and bundle-mode
// state construction call to resolve chain + DataEdge (Option E Phase 2 /
// #581, P2-13, "Lesson 1" from the Hermes round: a bundle-configured client
// MUST NOT skip this call and assume chain resolution is complete just
// because the bundle carries `account.chain_id`. The bundle has no
// `data_edge_address` field at all — that value ONLY ever comes from the
// relay's `/v1/billing/status` response. Factoring the fetch into one
// function that every init path calls means there is no code path that can
// "forget" to call it — the mnemonic path and the bundle path share this
// exact function, not a copy of it.
//
// `fallbackChainId` is what to return if the billing call fails or is
// unreachable: mnemonic-mode passes 100 (Gnosis, the __init__-seeded
// default); bundle-mode passes `bundle.account.chain_id` (the bundle's own
// authoritative value — falling back to the free-tier default would target
// the WRONG CHAIN outright, not just the wrong environment's DataEdge; see
// `python/src/totalreclaw/client.py::_chain_id_fallback`'s docstring for the
// identical rationale on the Python side).
// ---------------------------------------------------------------------------

export interface FetchChainConfigOptions {
  serverUrl: string;
  smartAccountAddress: string;
  authKeyHex: string;
  /** Extra headers (client id, session tag, …) merged with Authorization. */
  headers?: Record<string, string>;
  /** Chain id to return when the billing call fails/is unreachable. */
  fallbackChainId: number;
  timeoutMs?: number;
  /** Injectable for tests; defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
  /** Best-effort logger for the tier/chain line other init paths already print. */
  onResolved?: (billing: Record<string, unknown>, resolved: ResolvedChainConfig) => void;
}

const DEFAULT_BILLING_TIMEOUT_MS = 5000;

export async function fetchChainConfig(
  opts: FetchChainConfigOptions,
): Promise<ResolvedChainConfig> {
  const doFetch = opts.fetchImpl ?? fetch;
  try {
    const billingUrl = `${opts.serverUrl.replace(/\/+$/, '')}/v1/billing/status?wallet_address=${encodeURIComponent(opts.smartAccountAddress)}`;
    const resp = await doFetch(billingUrl, {
      method: 'GET',
      headers: {
        ...(opts.headers ?? {}),
        Authorization: `Bearer ${opts.authKeyHex}`,
      },
      signal: AbortSignal.timeout(opts.timeoutMs ?? DEFAULT_BILLING_TIMEOUT_MS),
    });
    if (resp.ok) {
      const billing = (await resp.json()) as Record<string, unknown>;
      const resolved = resolveChainConfig(billing);
      opts.onResolved?.(billing, resolved);
      return resolved;
    }
  } catch {
    // Best-effort — network, timeout, or auth issues all fall back below.
  }
  return { chainId: opts.fallbackChainId, dataEdgeAddress: undefined };
}
