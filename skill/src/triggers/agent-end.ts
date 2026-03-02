/**
 * TotalReclaw Skill - Agent End Hook
 *
 * This hook runs AFTER the agent completes its turn.
 * It extracts facts from the recent conversation and stores them.
 *
 * Flow:
 * 1. Check turn counter (only extract every N turns)
 * 2. Extract facts from recent conversation
 * 3. Deduplicate against existing memories
 * 4. Store high-importance facts
 * 5. Return AgentEndResult with stats
 *
 * This hook is ASYNC and does NOT block the user.
 */

import type { TotalReclaw } from '@totalreclaw/client';
import type {
  AgentEndResult,
  OpenClawContext,
  TotalReclawSkillConfig,
  ExtractedFact,
  SkillState,
} from '../types';
import {
  FactExtractor,
  createFactExtractor,
  isExplicitMemoryCommand,
  type LLMClient,
  type VectorStoreClient,
} from '../extraction';

// ============================================================================
// Types
// ============================================================================

/**
 * Options for the agent-end hook
 */
export interface AgentEndOptions {
  /** TotalReclaw client instance */
  client: TotalReclaw;
  /** Skill configuration */
  config: TotalReclawSkillConfig;
  /** Skill state (for turn tracking) */
  state: SkillState;
  /** LLM client for extraction */
  llmClient: LLMClient;
  /** Vector store client for deduplication (optional) */
  vectorStoreClient?: VectorStoreClient;
  /** Custom fact extractor (optional) */
  extractor?: FactExtractor;
  /** Whether to enable debug logging */
  debug?: boolean;
  /** Whether to run asynchronously (don't await completion) */
  async?: boolean;
}

/**
 * Internal extraction result
 */
interface ExtractionResult {
  factsExtracted: number;
  factsStored: number;
  factsSkipped: number;
  processingTimeMs: number;
}

// ============================================================================
// Main Hook Function
// ============================================================================

/**
 * Execute the agent-end hook
 *
 * This extracts facts from the conversation and stores them asynchronously.
 *
 * @param context - OpenClaw context containing user message and history
 * @param options - Hook options including client and configuration
 * @returns AgentEndResult with extraction and storage stats
 *
 * @example
 * ```typescript
 * const result = await agentEnd(context, {
 *   client: openMemoryClient,
 *   config: skillConfig,
 *   state: skillState,
 *   llmClient: myLLMClient,
 * });
 *
 * console.log(`Extracted ${result.factsExtracted} facts, stored ${result.factsStored}`);
 * ```
 */
export async function agentEnd(
  context: OpenClawContext,
  options: AgentEndOptions
): Promise<AgentEndResult> {
  const startTime = Date.now();

  // Update turn counter
  options.state.turnCount++;

  if (options.debug) {
    console.log(`[TotalReclaw] Agent end hook - Turn ${options.state.turnCount}`);
  }

  try {
    // Step 1: Check if we should extract this turn
    const shouldExtract = shouldExtractThisTurn(context, options);

    if (!shouldExtract) {
      if (options.debug) {
        console.log(`[TotalReclaw] Skipping extraction this turn`);
      }

      return {
        factsExtracted: 0,
        factsStored: 0,
        processingTimeMs: Date.now() - startTime,
      };
    }

    // Step 2: Run extraction (can be async)
    if (options.async) {
      // Fire and forget - don't await
      runExtractionAsync(context, options).catch(error => {
        console.error('[TotalReclaw] Async extraction failed:', error);
      });

      return {
        factsExtracted: 0, // Will be updated asynchronously
        factsStored: 0,
        processingTimeMs: Date.now() - startTime,
      };
    }

    // Step 3: Run extraction synchronously
    const result = await runExtraction(context, options);

    return {
      factsExtracted: result.factsExtracted,
      factsStored: result.factsStored,
      processingTimeMs: Date.now() - startTime,
    };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';
    console.error('[TotalReclaw] agentEnd hook failed:', errorMsg);

    return {
      factsExtracted: 0,
      factsStored: 0,
      processingTimeMs: Date.now() - startTime,
    };
  }
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Determine if we should extract facts this turn
 */
function shouldExtractThisTurn(
  context: OpenClawContext,
  options: AgentEndOptions
): boolean {
  const { config, state } = options;

  // Always extract for explicit memory commands
  if (isExplicitMemoryCommand(context.userMessage)) {
    if (options.debug) {
      console.log(`[TotalReclaw] Explicit memory command detected`);
    }
    return true;
  }

  // Check if turn counter matches extraction interval
  if (state.turnCount % config.autoExtractEveryTurns === 0) {
    return true;
  }

  // Check if we have pending extractions
  if (state.pendingExtractions.length > 0) {
    return true;
  }

  return false;
}

/**
 * Run extraction asynchronously (fire and forget)
 */
async function runExtractionAsync(
  context: OpenClawContext,
  options: AgentEndOptions
): Promise<void> {
  const result = await runExtraction(context, options);

  if (options.debug) {
    console.log(
      `[TotalReclaw] Async extraction completed: ${result.factsExtracted} extracted, ` +
      `${result.factsStored} stored, ${result.factsSkipped} skipped`
    );
  }
}

/**
 * Run the actual extraction and storage
 */
async function runExtraction(
  context: OpenClawContext,
  options: AgentEndOptions
): Promise<ExtractionResult> {
  const result: ExtractionResult = {
    factsExtracted: 0,
    factsStored: 0,
    factsSkipped: 0,
    processingTimeMs: 0,
  };

  const startTime = Date.now();

  try {
    // Get or create fact extractor
    const extractor = options.extractor || createFactExtractor(
      options.llmClient,
      options.vectorStoreClient,
      {
        minImportance: options.config.minImportanceForAutoStore,
        postTurnWindow: 3, // Last 3 turns
      }
    );

    // Determine extraction trigger
    const trigger = isExplicitMemoryCommand(context.userMessage) ? 'explicit' : 'post_turn';

    // Extract facts from conversation
    const extractionResult = await extractor.extractFacts(context, trigger);
    result.factsExtracted = extractionResult.facts.length;

    if (options.debug) {
      console.log(`[TotalReclaw] Extracted ${result.factsExtracted} facts in ${extractionResult.processingTimeMs}ms`);
    }

    // Filter and store facts
    for (const fact of extractionResult.facts) {
      // Skip NOOP facts
      if (fact.action === 'NOOP') {
        result.factsSkipped++;
        continue;
      }

      // Skip low importance facts (unless explicit command)
      if (trigger !== 'explicit' && fact.importance < options.config.minImportanceForAutoStore) {
        result.factsSkipped++;
        continue;
      }

      // Store the fact
      try {
        await storeFact(fact, options);
        result.factsStored++;

        if (options.debug) {
          console.log(`[TotalReclaw] Stored fact: "${fact.factText}" (importance: ${fact.importance})`);
        }
      } catch (storeError) {
        console.error(`[TotalReclaw] Failed to store fact:`, storeError);
        result.factsSkipped++;
      }
    }

    // Update state
    options.state.lastExtraction = new Date();
    options.state.pendingExtractions = [];
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';
    console.error('[TotalReclaw] Extraction failed:', errorMsg);
  }

  result.processingTimeMs = Date.now() - startTime;
  return result;
}

/**
 * Store a single fact in TotalReclaw
 */
async function storeFact(
  fact: ExtractedFact,
  options: AgentEndOptions
): Promise<void> {
  const { client, config } = options;

  switch (fact.action) {
    case 'ADD':
      // Store new fact
      await client.remember(fact.factText, {
        importance: fact.importance / 10, // Normalize to 0-1
        source: 'extracted',
        tags: [fact.type],
      });
      break;

    case 'UPDATE':
      // Delete old and add new (simple update strategy)
      if (fact.existingFactId) {
        try {
          await client.forget(fact.existingFactId);
        } catch {
          // Ignore if old fact doesn't exist
        }
      }
      await client.remember(fact.factText, {
        importance: fact.importance / 10,
        source: 'extracted',
        tags: [fact.type],
      });
      break;

    case 'DELETE':
      // Delete existing fact
      if (fact.existingFactId) {
        await client.forget(fact.existingFactId);
      }
      break;

    case 'NOOP':
    default:
      // Do nothing
      break;
  }
}

// ============================================================================
// Exports
// ============================================================================

export default agentEnd;
