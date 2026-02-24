/**
 * OpenMemory Skill - Before Agent Start Hook
 *
 * This hook runs BEFORE the agent processes the user's message.
 * It retrieves relevant memories and injects them into the context.
 *
 * Flow:
 * 1. Retrieve relevant memories using OpenMemory client
 * 2. Rerank with cross-encoder for high-quality results
 * 3. Format memories for context injection
 * 4. Return BeforeAgentStartResult with memories and contextString
 *
 * Target latency: <100ms total
 */

import type { OpenMemory } from '@openmemory/client';
import type { RerankedResult, Fact } from '@openmemory/client';
import type {
  BeforeAgentStartResult,
  OpenClawContext,
  OpenMemorySkillConfig,
} from '../types';
import { CrossEncoderReranker, getCrossEncoderReranker } from '../reranker/cross-encoder';

// ============================================================================
// Types
// ============================================================================

/**
 * Options for the before-agent-start hook
 */
export interface BeforeAgentStartOptions {
  /** OpenMemory client instance */
  client: OpenMemory;
  /** Skill configuration */
  config: OpenMemorySkillConfig;
  /** Cross-encoder reranker instance (optional, will create if not provided) */
  reranker?: CrossEncoderReranker;
  /** Custom context formatter (optional) */
  contextFormatter?: (memories: RerankedResult[]) => string;
  /** Whether to enable debug logging */
  debug?: boolean;
}

/**
 * Internal metrics for performance tracking
 */
interface HookMetrics {
  searchLatencyMs: number;
  rerankLatencyMs: number;
  formatLatencyMs: number;
  totalLatencyMs: number;
  candidatesRetrieved: number;
  memoriesReturned: number;
}

// ============================================================================
// Default Context Formatter
// ============================================================================

/**
 * Format retrieved memories into a context string for injection
 *
 * This format is designed to be:
 * - Clear to the LLM about what these memories represent
 * - Easy to parse visually
 * - Compact to minimize token usage
 */
export function formatMemoriesForContext(memories: RerankedResult[]): string {
  if (memories.length === 0) {
    return '';
  }

  const lines: string[] = [
    '<memory_context>',
    '  <description>Relevant memories about the user retrieved from long-term storage</description>',
    '  <memories>',
  ];

  for (let i = 0; i < memories.length; i++) {
    const memory = memories[i];
    const fact = memory.fact;

    // Format each memory with type and importance indicators
    const memoryType = getMemoryType(fact);
    const typeEmoji = getTypeIndicator(memoryType);
    const importanceBar = getImportanceBar(memory.score);

    lines.push(`    <memory rank="${i + 1}" score="${memory.score.toFixed(2)}">`);
    lines.push(`      <type>${memoryType}</type>`);
    lines.push(`      <importance>${importanceBar}</importance>`);
    lines.push(`      <content>${typeEmoji} ${escapeXml(fact.text)}</content>`);
    lines.push(`    </memory>`);
  }

  lines.push('  </memories>');
  lines.push('</memory_context>');

  return lines.join('\n');
}

/**
 * Get memory type from fact metadata
 */
function getMemoryType(fact: Fact): string {
  // Check tags for type information
  if (fact.metadata?.tags && fact.metadata.tags.length > 0) {
    const typeTag = fact.metadata.tags.find(t =>
      ['fact', 'preference', 'decision', 'episodic', 'goal'].includes(t)
    );
    if (typeTag) return typeTag;
  }
  return 'fact';
}

/**
 * Get a visual indicator for memory type
 */
function getTypeIndicator(type: string): string {
  switch (type) {
    case 'preference':
      return '[PREF]';
    case 'decision':
      return '[DEC]';
    case 'goal':
      return '[GOAL]';
    case 'episodic':
      return '[EPIS]';
    default:
      return '[FACT]';
  }
}

/**
 * Get a visual importance bar
 */
function getImportanceBar(score: number): string {
  const filled = Math.round(score * 5);
  const empty = 5 - filled;
  return '█'.repeat(filled) + '░'.repeat(empty);
}

/**
 * Escape XML special characters
 */
function escapeXml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

// ============================================================================
// Main Hook Function
// ============================================================================

/**
 * Execute the before-agent-start hook
 *
 * This retrieves relevant memories and prepares them for context injection.
 *
 * @param context - OpenClaw context containing user message and history
 * @param options - Hook options including client and configuration
 * @returns BeforeAgentStartResult with memories and formatted context string
 *
 * @example
 * ```typescript
 * const result = await beforeAgentStart(context, {
 *   client: openMemoryClient,
 *   config: skillConfig,
 * });
 *
 * // Inject result.contextString into the agent's context
 * console.log(`Retrieved ${result.memories.length} memories in ${result.latencyMs}ms`);
 * ```
 */
export async function beforeAgentStart(
  context: OpenClawContext,
  options: BeforeAgentStartOptions
): Promise<BeforeAgentStartResult> {
  const startTime = Date.now();
  const metrics: HookMetrics = {
    searchLatencyMs: 0,
    rerankLatencyMs: 0,
    formatLatencyMs: 0,
    totalLatencyMs: 0,
    candidatesRetrieved: 0,
    memoriesReturned: 0,
  };

  try {
    // Step 1: Build search query from user message and recent context
    const searchQuery = buildSearchQuery(context);

    if (options.debug) {
      console.log(`[OpenMemory] Searching for: "${searchQuery}"`);
    }

    // Step 2: Retrieve candidate memories from OpenMemory
    const searchStart = Date.now();
    const candidates = await options.client.recall(
      searchQuery,
      options.config.maxMemoriesInContext * 3 // Get more candidates for reranking
    );
    metrics.searchLatencyMs = Date.now() - searchStart;
    metrics.candidatesRetrieved = candidates.length;

    if (options.debug) {
      console.log(`[OpenMemory] Retrieved ${candidates.length} candidates in ${metrics.searchLatencyMs}ms`);
    }

    // If no candidates, return empty result early
    if (candidates.length === 0) {
      return {
        memories: [],
        contextString: '',
        latencyMs: Date.now() - startTime,
      };
    }

    // Step 3: Rerank with cross-encoder for high-quality results
    const rerankStart = Date.now();
    const reranker = options.reranker || getCrossEncoderReranker();

    // Ensure reranker is loaded
    if (!reranker.isReady()) {
      await reranker.load(options.config.rerankerModel);
    }

    // Extract facts from reranked results for cross-encoder
    const candidateFacts: Fact[] = candidates.map(r => r.fact);

    // Rerank using cross-encoder
    const rerankedResults = await reranker.rerank(
      searchQuery,
      candidateFacts,
      options.config.maxMemoriesInContext
    );
    metrics.rerankLatencyMs = Date.now() - rerankStart;

    if (options.debug) {
      console.log(`[OpenMemory] Reranked in ${metrics.rerankLatencyMs}ms`);
    }

    // Convert CrossEncoderResult back to RerankedResult format
    const memories: RerankedResult[] = rerankedResults.map(result => ({
      fact: result.fact,
      score: result.score,
      vectorScore: result.vectorScore,
      textScore: result.textScore,
      decayAdjustedScore: result.decayAdjustedScore,
    }));

    // Step 4: Format memories for context injection
    const formatStart = Date.now();
    const formatter = options.contextFormatter || formatMemoriesForContext;
    const contextString = formatter(memories);
    metrics.formatLatencyMs = Date.now() - formatStart;
    metrics.memoriesReturned = memories.length;

    // Calculate total latency
    metrics.totalLatencyMs = Date.now() - startTime;

    if (options.debug) {
      console.log(`[OpenMemory] Hook completed in ${metrics.totalLatencyMs}ms`);
      console.log(`  - Search: ${metrics.searchLatencyMs}ms`);
      console.log(`  - Rerank: ${metrics.rerankLatencyMs}ms`);
      console.log(`  - Format: ${metrics.formatLatencyMs}ms`);
    }

    return {
      memories,
      contextString,
      latencyMs: metrics.totalLatencyMs,
    };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';
    console.error('[OpenMemory] beforeAgentStart hook failed:', errorMsg);

    // Return empty result on error to avoid blocking the agent
    return {
      memories: [],
      contextString: '',
      latencyMs: Date.now() - startTime,
    };
  }
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Build a search query from the OpenClaw context
 *
 * Combines:
 * - Current user message (primary signal)
 * - Recent conversation history (context signal)
 */
function buildSearchQuery(context: OpenClawContext): string {
  const parts: string[] = [];

  // Add current user message (most important)
  if (context.userMessage) {
    parts.push(context.userMessage);
  }

  // Add recent conversation history for context
  // Limit to last 2 turns to keep query focused
  const recentHistory = context.history.slice(-2);
  for (const turn of recentHistory) {
    // Only add if not too long
    if (turn.content.length < 200) {
      parts.push(turn.content);
    }
  }

  // Join with newlines and truncate to reasonable length
  const query = parts.join('\n').slice(0, 500);

  return query;
}

// ============================================================================
// Exports
// ============================================================================

export default beforeAgentStart;
