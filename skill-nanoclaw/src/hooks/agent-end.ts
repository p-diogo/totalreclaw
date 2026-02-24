import type { OpenMemory, FactMetadata } from '@openmemory/client';
import type { ExtractedFact } from '../extraction/prompts';
import {
  POST_TURN_PROMPT,
  validateExtractionResponse,
  formatConversationHistory,
} from '../extraction/prompts';

export interface AgentEndInput {
  conversationHistory: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
  groupFolder: string;
  turnCount: number;
}

export interface AgentEndOutput {
  factsExtracted: number;
  factsStored: number;
}

export type LLMClient = {
  generate: (system: string, user: string, options?: { responseFormat?: { type: string } }) => Promise<string>;
};

const EXTRACT_INTERVAL = parseInt(process.env.OPENMEMORY_EXTRACT_INTERVAL || '5', 10);
const MIN_IMPORTANCE = parseInt(process.env.OPENMEMORY_MIN_IMPORTANCE || '6', 10);

export async function agentEnd(
  client: OpenMemory,
  llmClient: LLMClient | null,
  input: AgentEndInput
): Promise<AgentEndOutput> {
  if (input.turnCount % EXTRACT_INTERVAL !== 0) {
    return { factsExtracted: 0, factsStored: 0 };
  }

  if (!llmClient) {
    return { factsExtracted: 0, factsStored: 0 };
  }

  try {
    const history = formatConversationHistory(
      input.conversationHistory.slice(-3).map((t, i) => ({
        role: t.role,
        content: t.content,
        timestamp: new Date(),
      }))
    );

    const existingMemories = await client.recall('*history*', 20);
    const namespaceMemories = existingMemories.filter(r => {
      const tags = r.fact.metadata.tags || [];
      return tags.includes(`namespace:${input.groupFolder}`);
    });

    const existingMemoriesStr = namespaceMemories.length > 0
      ? namespaceMemories.map(m => `[ID: ${m.fact.id}] ${m.fact.text}`).join('\n')
      : '(No existing memories)';

    const prompt = POST_TURN_PROMPT.format({
      conversationHistory: history,
      existingMemories: existingMemoriesStr,
    });

    const response = await llmClient.generate(prompt.system, prompt.user, {
      responseFormat: { type: 'json_object' },
    });

    const parsed = JSON.parse(response);
    const validation = validateExtractionResponse(parsed);

    if (!validation.valid) {
      console.error('Extraction validation failed:', validation.errors);
      return { factsExtracted: 0, factsStored: 0 };
    }

    let factsStored = 0;
    for (const fact of validation.facts!) {
      if (fact.action === 'ADD' && fact.importance >= MIN_IMPORTANCE) {
        const metadata: FactMetadata = {
          importance: fact.importance / 10,
          source: 'agent_end_extraction',
          tags: [
            `namespace:${input.groupFolder}`,
            fact.type,
          ],
        };

        await client.remember(fact.factText, metadata);
        factsStored++;
      }
    }

    return {
      factsExtracted: validation.facts!.length,
      factsStored,
    };
  } catch (error) {
    console.error('agentEnd error:', error);
    return { factsExtracted: 0, factsStored: 0 };
  }
}
