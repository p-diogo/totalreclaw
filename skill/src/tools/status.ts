/**
 * TotalReclaw Skill - Status Tool
 *
 * Tool for checking billing/subscription status in TotalReclaw.
 * This is the totalreclaw_status tool implementation.
 *
 * Unlike other tools that use the TotalReclaw client (protobuf API),
 * this tool calls the REST billing endpoint directly.
 *
 * @example
 * ```typescript
 * const result = await statusTool('https://api.totalreclaw.xyz', 'deadbeef...');
 * // result: { success: true, tier: 'free', formatted: '...' }
 * ```
 */

import { debugLog } from '../debug';

/**
 * Result of the status tool operation
 */
export interface StatusToolResult {
  /** Whether the operation succeeded */
  success: boolean;
  /** Current subscription tier */
  tier?: string;
  /** Number of writes used this month */
  free_writes_used?: number;
  /** Monthly write limit */
  free_writes_limit?: number;
  /** Number of reads used this month */
  free_reads_used?: number;
  /** Monthly read limit */
  free_reads_limit?: number;
  /** When the free tier counters reset */
  free_writes_reset_at?: string;
  /** Upgrade URL (if on free tier) */
  upgrade_url?: string;
  /**
   * Smart Account / scope address (echoed back from the wallet_address
   * input). Surfaced so users + agents can see their on-chain identity
   * before any chain write completes. Internal#130.
   */
  scope_address?: string;
  /** "production" or "staging". Inferred from the relay URL when absent. */
  environment?: 'production' | 'staging';
  /** Caveat surfaced ONLY on staging (quota not enforced there). */
  staging_note?: string;
  /** Human-readable formatted summary */
  formatted?: string;
  /** Error message (if failed) */
  error?: string;
}

/**
 * Infer environment from the relay URL when the response doesn't carry
 * an explicit ``environment`` field. The staging relay
 * (``api-staging.totalreclaw.xyz``) doesn't enforce the free-tier quota.
 */
function inferEnvironment(serverUrl: string): 'production' | 'staging' {
  return serverUrl.toLowerCase().includes('api-staging') ? 'staging' : 'production';
}

const STAGING_NOTE =
  'You are on the staging relay (api-staging.totalreclaw.xyz). The free-tier quota is NOT enforced here — writes will succeed past the listed limit. Production (api.totalreclaw.xyz) enforces the 250 writes/month cap.';

/**
 * Fetch billing/subscription status from the TotalReclaw server
 *
 * @param serverUrl - The TotalReclaw server URL
 * @param authKeyHex - Hex-encoded auth key for Bearer token
 * @returns Result containing success status and billing information
 *
 * @example
 * ```typescript
 * const result = await statusTool(
 *   'https://api.totalreclaw.xyz',
 *   'deadbeef0123456789abcdef...',
 * );
 *
 * if (result.success) {
 *   console.log(result.formatted);
 * }
 * ```
 */
export async function statusTool(
  serverUrl: string,
  authKeyHex: string,
  walletAddress?: string,
): Promise<StatusToolResult> {
  if (!serverUrl) {
    return {
      success: false,
      error: 'Server URL is not configured',
    };
  }

  if (!authKeyHex) {
    return {
      success: false,
      error: 'Auth credentials are not available. Please initialize the skill first.',
    };
  }

  try {
    const baseUrl = `${serverUrl.replace(/\/+$/, '')}/v1/billing/status`;
    const url = walletAddress ? `${baseUrl}?wallet_address=${encodeURIComponent(walletAddress)}` : baseUrl;

    const headers: Record<string, string> = {
      'Authorization': `Bearer ${authKeyHex}`,
      'Accept': 'application/json',
      'X-TotalReclaw-Client': 'openclaw-plugin',
    };
    // QA / observability session tag — see internal#127.
    const rawSid = process.env.TOTALRECLAW_SESSION_ID;
    if (rawSid && rawSid.trim()) headers['X-TotalReclaw-Session'] = rawSid.trim();

    const response = await fetch(url, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      return {
        success: false,
        error: `Failed to fetch billing status (HTTP ${response.status}): ${body || response.statusText}`,
      };
    }

    const data = await response.json() as Record<string, unknown>;

    const tier = (data.tier as string) || 'free';
    const freeWritesUsed = (data.free_writes_used as number) ?? 0;
    const freeWritesLimit = (data.free_writes_limit as number) ?? 0;
    const freeReadsUsed = (data.free_reads_used as number) ?? 0;
    const freeReadsLimit = (data.free_reads_limit as number) ?? 0;
    const freeWritesResetAt = data.free_writes_reset_at as string | undefined;
    const upgradeUrl = data.upgrade_url as string | undefined;
    const environment: 'production' | 'staging' =
      (data.environment as 'production' | 'staging' | undefined) ?? inferEnvironment(serverUrl);

    // Build formatted summary
    const tierLabel = tier === 'pro' ? 'Pro' : 'Free';
    const lines: string[] = [
      `Tier: ${tierLabel}`,
      `Writes: ${freeWritesUsed}/${freeWritesLimit} used`,
      `Reads: ${freeReadsUsed}/${freeReadsLimit} used`,
    ];

    if (freeWritesResetAt) {
      lines.push(`Resets: ${new Date(freeWritesResetAt).toLocaleDateString()}`);
    }

    // 3.3.1 (internal#130) — surface the SA / scope address pre-write.
    if (walletAddress) {
      lines.push(`Smart Account: ${walletAddress}`);
    }

    if (tier !== 'pro' && upgradeUrl) {
      lines.push(`Upgrade: ${upgradeUrl}`);
    }

    // Mention staging ONLY when on staging; production users should never
    // see staging surfaced.
    if (environment === 'staging') {
      lines.push(`Environment: staging — ${STAGING_NOTE}`);
    }

    return {
      success: true,
      tier,
      free_writes_used: freeWritesUsed,
      free_writes_limit: freeWritesLimit,
      free_reads_used: freeReadsUsed,
      free_reads_limit: freeReadsLimit,
      free_writes_reset_at: freeWritesResetAt,
      upgrade_url: upgradeUrl,
      scope_address: walletAddress,
      environment,
      ...(environment === 'staging' ? { staging_note: STAGING_NOTE } : {}),
      formatted: lines.join('\n'),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error occurred';
    debugLog(`Status tool failed: ${message}`);
    return {
      success: false,
      error: `Failed to check billing status: ${message}`,
    };
  }
}

/**
 * Create a bound status tool function
 *
 * Useful for creating a tool that's pre-bound to server URL and auth key.
 *
 * @param serverUrl - The TotalReclaw server URL
 * @param authKeyHex - Hex-encoded auth key for Bearer token
 * @returns A function that returns StatusToolResult
 */
export function createStatusTool(
  serverUrl: string,
  authKeyHex: string,
  walletAddress?: string,
): () => Promise<StatusToolResult> {
  return () => statusTool(serverUrl, authKeyHex, walletAddress);
}

export default statusTool;
