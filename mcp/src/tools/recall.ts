import { OpenMemory } from '@openmemory/client';
import { RECALL_TOOL_DESCRIPTION } from '../prompts';

export interface RecallInput {
  query: string;
  k?: number;
  min_importance?: number;
  namespace?: string;
  include_decay?: boolean;
}

export interface RecallOutput {
  memories: Array<{
    fact_id: string;
    fact_text: string;
    score: number;
    importance: number;
    age_days: number;
    decay_score: number;
  }>;
  latency_ms: number;
}

export const recallToolDefinition = {
  name: 'openmemory_recall',
  description: RECALL_TOOL_DESCRIPTION,
  inputSchema: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'The search query',
      },
      k: {
        type: 'number',
        default: 8,
        description: 'Number of results to return',
      },
      min_importance: {
        type: 'number',
        minimum: 1,
        maximum: 10,
        description: 'Filter by minimum importance',
      },
      namespace: {
        type: 'string',
        description: 'Search within specific namespace',
      },
      include_decay: {
        type: 'boolean',
        default: true,
        description: 'Apply decay scoring',
      },
    },
    required: ['query'],
  },
};

export async function handleRecall(
  client: OpenMemory,
  args: unknown,
  defaultNamespace: string
): Promise<{ content: Array<{ type: string; text: string }> }> {
  const input = args as RecallInput;
  const startTime = Date.now();

  if (!input.query || typeof input.query !== 'string' || input.query.trim().length === 0) {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          memories: [],
          latency_ms: 0,
          error: 'Invalid input: query is required and must be a non-empty string',
        }),
      }],
    };
  }

  try {
    let k = input.k ?? 8;
    if (k < 1) k = 8;
    if (k > 50) k = 50;

    const results = await client.recall(input.query.trim(), k);

    let filtered = results;
    if (input.min_importance !== undefined) {
      const minImp = input.min_importance / 10;
      filtered = results.filter(r =>
        (r.fact.metadata.importance ?? 0.5) >= minImp
      );
    }

    if (input.namespace || defaultNamespace !== 'default') {
      const ns = input.namespace || defaultNamespace;
      filtered = filtered.filter(r =>
        r.fact.metadata.tags?.includes(`namespace:${ns}`)
      );
    }

    const memories = filtered.map(r => {
      const ageMs = Date.now() - r.fact.createdAt.getTime();
      const ageDays = Math.floor(ageMs / (1000 * 60 * 60 * 24));

      return {
        fact_id: r.fact.id,
        fact_text: r.fact.text,
        score: r.score,
        importance: Math.round((r.fact.metadata.importance ?? 0.5) * 10),
        age_days: ageDays,
        decay_score: r.decayAdjustedScore,
      };
    });

    const result: RecallOutput = {
      memories,
      latency_ms: Date.now() - startTime,
    };

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
          memories: [],
          latency_ms: Date.now() - startTime,
          error: `Failed to recall memories: ${message}`,
        }),
      }],
    };
  }
}
