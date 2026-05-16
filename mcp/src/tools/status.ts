/**
 * TotalReclaw MCP - Billing Status Tool
 *
 * Shows subscription/billing status for the user's account.
 * Queries the relay server's billing endpoint.
 */

import { STATUS_TOOL_DESCRIPTION } from '../prompts.js';
import { getClientId } from '../client-id.js';
import { getSessionId } from '../session-id.js';

export const statusToolDefinition = {
  name: 'totalreclaw_status',
  description: STATUS_TOOL_DESCRIPTION,
  inputSchema: {
    type: 'object',
    properties: {
      wallet_address: {
        type: 'string',
        description: 'Smart Account address (derived from recovery phrase)',
      },
    },
    required: ['wallet_address'],
  },
  annotations: {
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
  },
};

export interface BillingFeatures {
  llm_dedup?: boolean;
  custom_extract_interval?: boolean;
  min_extract_interval?: number;
  extraction_interval?: number;
  max_facts_per_extraction?: number;
  max_candidate_pool?: number;
}

export interface BillingStatusResponse {
  tier: string;
  free_writes_used: number;
  free_writes_limit: number;
  expires_at: string | null;
  features?: BillingFeatures;
  // ``period`` disambiguates the limit semantics for the agent: "monthly"
  // means ``free_writes_limit`` resets each calendar month, "lifetime"
  // means it never resets. ``resets_at`` is the next monthly reset.
  period?: 'monthly' | 'lifetime' | null;
  resets_at?: string | null;
  // ``environment`` is "production" or "staging". When the relay doesn't
  // populate it, the client infers from the relay URL
  // (api-staging.* → staging). Surface staging-specific notes ONLY when
  // this is "staging" — production users should see no mention of it.
  environment?: 'production' | 'staging' | null;
}

/**
 * Infer environment from the relay URL when the response doesn't carry
 * an explicit ``environment`` field. The staging relay
 * (``api-staging.totalreclaw.xyz``) doesn't enforce the free-tier quota.
 */
function inferEnvironment(serverUrl: string): 'production' | 'staging' {
  return serverUrl.toLowerCase().includes('api-staging') ? 'staging' : 'production';
}

/** Last raw billing response (for candidate pool caching in index.ts). */
let lastBillingResponse: BillingStatusResponse | null = null;

/** Get the last raw billing response. */
export function getLastBillingResponse(): BillingStatusResponse | null {
  return lastBillingResponse;
}

/**
 * Handle a totalreclaw_status tool call.
 *
 * Fetches billing status from the relay server and formats it for the LLM.
 */
export async function handleStatus(
  serverUrl: string,
  authKey: string,
  args: unknown,
): Promise<{ content: Array<{ type: string; text: string }> }> {
  const input = args as Record<string, unknown>;
  const walletAddress = input?.wallet_address as string;

  if (!walletAddress || typeof walletAddress !== 'string') {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          error: 'wallet_address is required',
        }),
      }],
    };
  }

  try {
    const url = `${serverUrl.replace(/\/+$/, '')}/v1/billing/status?wallet_address=${encodeURIComponent(walletAddress)}`;

    const headers: Record<string, string> = {
      'Authorization': `Bearer ${authKey}`,
      'Content-Type': 'application/json',
      'X-TotalReclaw-Client': getClientId(),
    };
    // Forward QA / observability session tag when set — see internal#127.
    const sid = getSessionId();
    if (sid) headers['X-TotalReclaw-Session'] = sid;
    const response = await fetch(url, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      const body = await response.text().catch(() => '');
      return {
        content: [{
          type: 'text',
          text: JSON.stringify({
            error: `Failed to fetch billing status (HTTP ${response.status})`,
            details: body || response.statusText,
          }),
        }],
      };
    }

    const data = (await response.json()) as BillingStatusResponse;

    // Cache the raw response for candidate pool sizing
    lastBillingResponse = data;

    // Format nicely for the LLM to present
    const tierLabel = data.tier === 'pro' ? 'Pro' : 'Free';
    // Default the free-tier period to "monthly" so older relays that don't
    // yet emit the field still give the agent an unambiguous answer.
    const period = data.period ?? (data.tier === 'free' ? 'monthly' : null);
    const periodSuffix = period === 'monthly' ? '/month' : '';
    const usage = `${data.free_writes_used}/${data.free_writes_limit}${periodSuffix}`;
    const remaining = data.free_writes_limit - data.free_writes_used;
    const environment: 'production' | 'staging' =
      data.environment ?? inferEnvironment(serverUrl);
    const expiresLabel = data.expires_at
      ? `Expires: ${new Date(data.expires_at).toLocaleDateString()}`
      : data.resets_at
        ? `Resets: ${new Date(data.resets_at).toLocaleDateString()}`
        : period === 'monthly'
          ? 'Resets monthly'
          : 'No expiry';
    // Only surface a staging caveat when actually on staging — production
    // users should never see staging mentioned.
    const stagingNote = environment === 'staging'
      ? 'You are on the staging relay (api-staging.totalreclaw.xyz). The free-tier quota is NOT enforced here — writes will succeed past the listed limit. Production (api.totalreclaw.xyz) enforces the 250 writes/month cap.'
      : null;

    // 3.3.1 (internal#130) — echo the SA / scope address back to the
    // agent so the user can see it pre-write. The MCP tool already takes
    // wallet_address as a required input (the SA is derived deterministically
    // from the mnemonic and passed in by the host); surfacing it here makes
    // it visible in the tool response without the user needing to ask
    // separately.
    const formattedLines = [
      `Tier: ${tierLabel}`,
      `Smart Account: ${walletAddress}`,
      `Writes used: ${usage}`,
      `Remaining: ${remaining}`,
      expiresLabel,
    ];
    if (stagingNote) {
      formattedLines.push(`Environment: staging — ${stagingNote}`);
    }
    const formatted = formattedLines.join('\n');

    const payload: Record<string, unknown> = {
      tier: data.tier,
      free_writes_used: data.free_writes_used,
      free_writes_limit: data.free_writes_limit,
      remaining_writes: remaining,
      expires_at: data.expires_at,
      period,
      resets_at: data.resets_at ?? null,
      environment,
      scope_address: walletAddress,
      formatted,
    };
    if (stagingNote) payload.staging_note = stagingNote;

    return {
      content: [{
        type: 'text',
        text: JSON.stringify(payload),
      }],
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          error: `Failed to check billing status: ${message}`,
        }),
      }],
    };
  }
}
