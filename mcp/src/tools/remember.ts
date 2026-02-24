import { OpenMemory, FactMetadata } from '@openmemory/client';
import {
  REMEMBER_TOOL_DESCRIPTION,
} from '../prompts';

export interface RememberInput {
  fact: string;
  importance?: number;
  namespace?: string;
  metadata?: {
    type?: string;
    expires_at?: string;
  };
}

export interface RememberOutput {
  success: boolean;
  fact_id: string;
  was_duplicate: boolean;
  action: 'created' | 'updated' | 'skipped';
}

export const rememberToolDefinition = {
  name: 'openmemory_remember',
  description: REMEMBER_TOOL_DESCRIPTION,
  inputSchema: {
    type: 'object',
    properties: {
      fact: {
        type: 'string',
        description: 'The fact to remember (atomic, concise)',
      },
      importance: {
        type: 'number',
        minimum: 1,
        maximum: 10,
        default: 5,
        description: 'Importance score 1-10',
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
    required: ['fact'],
  },
};

export async function handleRemember(
  client: OpenMemory,
  args: unknown,
  defaultNamespace: string
): Promise<{ content: Array<{ type: string; text: string }> }> {
  const input = args as RememberInput;

  if (!input.fact || typeof input.fact !== 'string' || input.fact.trim().length === 0) {
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

  if (input.importance !== undefined) {
    if (typeof input.importance !== 'number' || input.importance < 1 || input.importance > 10) {
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
    const importance = (input.importance ?? 5) / 10;
    const namespace = input.namespace || defaultNamespace;

    const metadata: FactMetadata = {
      importance,
      source: 'mcp_remember',
      tags: input.metadata?.type ? [input.metadata.type, `namespace:${namespace}`] : [`namespace:${namespace}`],
    };

    if (input.metadata?.expires_at) {
      metadata.timestamp = new Date(input.metadata.expires_at);
    }

    const factId = await client.remember(input.fact.trim(), metadata);

    const result: RememberOutput = {
      success: true,
      fact_id: factId,
      was_duplicate: false,
      action: 'created',
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
          success: false,
          error: `Failed to store memory: ${message}`,
        }),
      }],
    };
  }
}
