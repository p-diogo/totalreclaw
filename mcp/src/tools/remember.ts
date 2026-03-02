import { TotalReclaw, FactMetadata } from '@totalreclaw/client';
import {
  REMEMBER_TOOL_DESCRIPTION,
} from '../prompts.js';

// ── Single-fact input (backward compat) ──────────────────────────────────────

export interface RememberInputSingle {
  fact: string;
  importance?: number;
  namespace?: string;
  metadata?: {
    type?: string;
    expires_at?: string;
  };
}

// ── Batch-fact input (new) ───────────────────────────────────────────────────

export interface BatchFact {
  text: string;
  importance?: number;
  type?: 'fact' | 'preference' | 'decision' | 'episodic' | 'goal';
}

export interface RememberInputBatch {
  facts: BatchFact[];
  namespace?: string;
}

// ── Union type for the handler ───────────────────────────────────────────────

export type RememberInput = RememberInputSingle | RememberInputBatch;

export interface RememberOutput {
  success: boolean;
  fact_id: string;
  was_duplicate: boolean;
  action: 'created' | 'updated' | 'skipped';
}

export interface BatchRememberOutput {
  success: boolean;
  results: RememberOutput[];
  total: number;
  created: number;
  skipped: number;
}

export const rememberToolDefinition = {
  name: 'totalreclaw_remember',
  description: REMEMBER_TOOL_DESCRIPTION,
  inputSchema: {
    type: 'object',
    properties: {
      fact: {
        type: 'string',
        description: 'A single fact to remember (atomic, concise). Use this OR the facts array.',
      },
      facts: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            text: {
              type: 'string',
              description: 'The atomic fact text',
            },
            importance: {
              type: 'number',
              minimum: 1,
              maximum: 10,
              description: 'Importance score 1-10',
            },
            type: {
              type: 'string',
              enum: ['fact', 'preference', 'decision', 'episodic', 'goal'],
              description: 'Category of the fact',
            },
          },
          required: ['text'],
        },
        description: 'Array of facts to store in a single call (preferred for multiple facts)',
      },
      importance: {
        type: 'number',
        minimum: 1,
        maximum: 10,
        default: 5,
        description: 'Importance score 1-10 (only for single-fact mode)',
      },
      namespace: {
        type: 'string',
        description: 'Optional namespace for isolation (e.g., "work", "personal")',
      },
      metadata: {
        type: 'object',
        properties: {
          type: {
            type: 'string',
            enum: ['fact', 'preference', 'decision', 'episodic', 'goal'],
          },
          expires_at: {
            type: 'string',
            description: 'ISO timestamp for time-limited facts',
          },
        },
      },
    },
  },
  annotations: {
    readOnlyHint: false,
    destructiveHint: false,
    idempotentHint: true,
  },
};

// Notify callback type for cache invalidation
export type OnRememberCallback = () => void;

let _onRememberCallback: OnRememberCallback | null = null;

export function setOnRememberCallback(cb: OnRememberCallback): void {
  _onRememberCallback = cb;
}

// ── Internal: store a single fact ────────────────────────────────────────────

async function storeSingleFact(
  client: TotalReclaw,
  text: string,
  importance: number,
  factType: string | undefined,
  namespace: string,
  expiresAt?: string
): Promise<RememberOutput> {
  const metadata: FactMetadata = {
    importance: importance / 10,
    source: 'mcp_remember',
    tags: factType
      ? [factType, `namespace:${namespace}`]
      : [`namespace:${namespace}`],
  };

  if (expiresAt) {
    metadata.timestamp = new Date(expiresAt);
  }

  const factId = await client.remember(text.trim(), metadata);

  return {
    success: true,
    fact_id: factId,
    was_duplicate: false,
    action: 'created',
  };
}

// ── Handler ──────────────────────────────────────────────────────────────────

export async function handleRemember(
  client: TotalReclaw,
  args: unknown,
  defaultNamespace: string
): Promise<{ content: Array<{ type: string; text: string }> }> {
  const input = args as Record<string, unknown>;

  // Determine if this is batch or single mode
  const isBatch = Array.isArray(input?.facts) && (input.facts as unknown[]).length > 0;
  const isSingle = typeof input?.fact === 'string';

  if (!isBatch && !isSingle) {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          success: false,
          error: 'Invalid input: provide either a "fact" string or a "facts" array',
        }),
      }],
    };
  }

  const namespace = (input.namespace as string) || defaultNamespace;

  // ── Batch mode ─────────────────────────────────────────────────────────────
  if (isBatch) {
    const factsArray = input.facts as BatchFact[];
    const results: RememberOutput[] = [];
    let created = 0;
    let skipped = 0;

    for (const f of factsArray) {
      if (!f.text || typeof f.text !== 'string' || f.text.trim().length === 0) {
        results.push({
          success: false,
          fact_id: '',
          was_duplicate: false,
          action: 'skipped',
        });
        skipped++;
        continue;
      }

      const imp = f.importance ?? 5;
      if (typeof imp !== 'number' || imp < 1 || imp > 10) {
        results.push({
          success: false,
          fact_id: '',
          was_duplicate: false,
          action: 'skipped',
        });
        skipped++;
        continue;
      }

      try {
        const result = await storeSingleFact(
          client,
          f.text,
          imp,
          f.type,
          namespace
        );
        results.push(result);
        created++;
      } catch (error) {
        results.push({
          success: false,
          fact_id: '',
          was_duplicate: false,
          action: 'skipped',
        });
        skipped++;
      }
    }

    const batchResult: BatchRememberOutput = {
      success: created > 0,
      results,
      total: factsArray.length,
      created,
      skipped,
    };

    if (_onRememberCallback && created > 0) {
      _onRememberCallback();
    }

    return {
      content: [{
        type: 'text',
        text: JSON.stringify(batchResult),
      }],
    };
  }

  // ── Single-fact mode (backward compat) ─────────────────────────────────────
  const singleInput = input as unknown as RememberInputSingle;

  if (!singleInput.fact || typeof singleInput.fact !== 'string' || singleInput.fact.trim().length === 0) {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          success: false,
          error: 'Invalid input: fact is required and must be a non-empty string',
        }),
      }],
    };
  }

  if (singleInput.importance !== undefined) {
    if (typeof singleInput.importance !== 'number' || singleInput.importance < 1 || singleInput.importance > 10) {
      return {
        content: [{
          type: 'text',
          text: JSON.stringify({
            success: false,
            error: 'Invalid input: importance must be a number between 1 and 10',
          }),
        }],
      };
    }
  }

  try {
    const result = await storeSingleFact(
      client,
      singleInput.fact,
      singleInput.importance ?? 5,
      singleInput.metadata?.type,
      namespace,
      singleInput.metadata?.expires_at
    );

    if (_onRememberCallback) {
      _onRememberCallback();
    }

    return {
      content: [{
        type: 'text',
        text: JSON.stringify(result),
      }],
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error occurred';
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          success: false,
          error: `Failed to store memory: ${message}`,
        }),
      }],
    };
  }
}
