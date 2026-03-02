import type { TotalReclaw, FactMetadata } from '@totalreclaw/client';
import type { LLMClient } from './agent-end';
import type { ExtractedFact } from '../extraction/prompts';
import {
  PRE_COMPACTION_PROMPT,
  validateExtractionResponse,
} from '../extraction/prompts';

export interface PreCompactInput {
  transcript: string;
  groupFolder: string;
  claudeMdPath?: string;
}

export interface PreCompactOutput {
  factsExtracted: number;
  factsStored: number;
  claudeMdUpdated: boolean;
}

export async function preCompact(
  client: TotalReclaw,
  llmClient: LLMClient | null,
  input: PreCompactInput
): Promise<PreCompactOutput> {
  if (!llmClient) {
    return { factsExtracted: 0, factsStored: 0, claudeMdUpdated: false };
  }

  try {
    const existingMemories = await client.recall('*', 100);
    const namespaceMemories = existingMemories.filter(r => {
      const tags = r.fact.metadata.tags || [];
      return tags.includes(`namespace:${input.groupFolder}`);
    });

    const existingMemoriesStr = namespaceMemories.length > 0
      ? namespaceMemories.map(m => `[ID: ${m.fact.id}] ${m.fact.text}`).join('\n')
      : '(No existing memories)';

    const prompt = PRE_COMPACTION_PROMPT.format({
      conversationHistory: input.transcript,
      existingMemories: existingMemoriesStr,
    });

    const response = await llmClient.generate(prompt.system, prompt.user, {
      responseFormat: { type: 'json_object' },
    });

    const parsed = JSON.parse(response);
    const validation = validateExtractionResponse(parsed);

    if (!validation.valid) {
      console.error('Pre-compact validation failed:', validation.errors);
      return { factsExtracted: 0, factsStored: 0, claudeMdUpdated: false };
    }

    let factsStored = 0;
    for (const fact of validation.facts!) {
      const metadata: FactMetadata = {
        importance: fact.importance / 10,
        source: 'pre_compaction',
        tags: [
          `namespace:${input.groupFolder}`,
          fact.type,
        ],
      };

      switch (fact.action) {
        case 'ADD':
          await client.remember(fact.factText, metadata);
          factsStored++;
          break;

        case 'UPDATE':
        case 'DELETE':
          if (fact.existingFactId) {
            try {
              await client.forget(fact.existingFactId);
              if (fact.action === 'UPDATE') {
                await client.remember(fact.factText, metadata);
                factsStored++;
              }
            } catch {
              // Skip if delete fails
            }
          }
          break;

        case 'NOOP':
          break;
      }
    }

    let claudeMdUpdated = false;
    if (input.claudeMdPath) {
      claudeMdUpdated = await syncToClaudeMd(client, input.groupFolder, input.claudeMdPath);
    }

    return {
      factsExtracted: validation.facts!.length,
      factsStored,
      claudeMdUpdated,
    };
  } catch (error) {
    console.error('preCompact error:', error);
    return { factsExtracted: 0, factsStored: 0, claudeMdUpdated: false };
  }
}

async function syncToClaudeMd(
  client: TotalReclaw,
  namespace: string,
  claudeMdPath: string
): Promise<boolean> {
  const fs = await import('fs/promises');

  try {
    const memories = await client.recall('*', { k: 50 } as any);

    const filtered = memories.filter(m => {
      const tags = m.fact.metadata.tags || [];
      return tags.includes(`namespace:${namespace}`) &&
             (m.fact.metadata.importance || 0.5) >= 0.7;
    });

    if (filtered.length === 0) return false;

    let existing = '';
    try {
      existing = await fs.readFile(claudeMdPath, 'utf-8');
    } catch {
      // File doesn't exist
    }

    if (!existing.includes('## TotalReclaw Sync')) {
      const section = '\n\n## TotalReclaw Sync\n\n' +
        filtered.map(m => `- ${m.fact.text}`).join('\n');

      await fs.writeFile(claudeMdPath, existing + section, 'utf-8');
      return true;
    }

    return false;
  } catch {
    return false;
  }
}
