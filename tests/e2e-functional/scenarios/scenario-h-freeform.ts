/**
 * Scenario H: LLM-Driven Freeform Conversation (30 turns)
 *
 * This scenario is fully dynamic: turns are generated at runtime by the
 * LLM orchestrator (llm-orchestrator.ts) using the Claude API with the
 * Alex Chen persona.
 *
 * The turns array starts empty and is populated during execution. The
 * `useLlmOrchestrator` flag signals the test runner to delegate turn
 * generation to the orchestrator rather than reading from the static array.
 *
 * Validates:
 * - Realistic injection rates (30-85% of turns)
 * - B2: Noise filtering (short replies should not trigger injection)
 * - Hook latency under realistic, unpredictable conversation patterns (p95 < 500ms)
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 3.8)
 * See: tests/e2e-functional/llm-orchestrator.ts for the orchestrator implementation
 */

import type { ConversationScenario } from '../types.js';

export const scenarioH: ConversationScenario & { useLlmOrchestrator: boolean } = {
  id: 'H',
  name: 'LLM-Driven Freeform',
  description:
    'Fully dynamic conversation driven by Claude API with the Alex Chen persona. ' +
    'The orchestrator generates user messages based on conversation history, ' +
    'producing a natural multi-turn interaction that tests memory injection, ' +
    'noise filtering, and retrieval quality under realistic conditions. ' +
    '30 turns with a mix of factual statements, recall questions, and noise.',
  pluginPath: '../../skill/plugin/index.js',
  turns: [], // Populated at runtime by llm-orchestrator
  useLlmOrchestrator: true,
};
