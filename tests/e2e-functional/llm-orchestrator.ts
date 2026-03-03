/**
 * LLM Orchestrator for Scenario H: LLM-Driven Freeform Conversation
 *
 * Uses the Anthropic SDK to call Claude API, generating realistic user messages
 * based on a persona prompt and conversation history. The orchestrator drives
 * a 30-turn conversation through the conversation driver, creating natural
 * interaction patterns that no human-scripted scenario can replicate.
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 3.8)
 */

import Anthropic from '@anthropic-ai/sdk';
import type { Turn, TurnResult } from './types.js';

// ─── Persona Prompt ───

const PERSONA_PROMPT = `You are a user having a conversation with an AI assistant.
Your persona:
- Name: Alex Chen
- Age: 32
- Job: Product designer at a fintech startup
- Location: Austin, TX (recently moved from Chicago)
- Hobbies: rock climbing, photography, making sourdough bread
- Dietary: vegetarian, lactose intolerant
- Pet: a golden retriever named Max
- Goal: learning Spanish, training for a half-marathon
- Recent: just got engaged, planning a wedding for fall 2026

Instructions:
- Have a natural, flowing conversation
- Mention personal details gradually over multiple turns
- Sometimes ask the assistant to remember specific things
- Sometimes ask "do you remember..." questions
- Include some short replies like "thanks", "ok", "got it" (about 20% of turns)
- Change topics naturally every 5-8 turns
- After turn 20, start asking recall questions about things mentioned earlier
- Be specific with details (dates, names, numbers) -- these are testable

Output ONLY the next user message, nothing else.`;

// ─── Types ───

/** A minimal conversation driver interface that the orchestrator calls into. */
export interface ConversationDriver {
  /**
   * Process a single turn: send the user message, run hooks, capture metrics.
   * Returns the injected context (if any), tool results, and updated history.
   */
  processTurn(turn: Turn): Promise<TurnResult>;
}

interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
}

// ─── API Key Check ───

/**
 * Check whether the Anthropic API key is available.
 * Returns true if the key is set, false otherwise.
 */
export function isApiKeyAvailable(): boolean {
  return Boolean(process.env.ANTHROPIC_API_KEY);
}

// ─── Message Generation ───

/**
 * Generate the next user message using the Claude API.
 *
 * Sends the full conversation history plus a meta-instruction to the persona,
 * which responds with the next natural user message.
 *
 * @param conversationHistory - All messages exchanged so far (user + assistant)
 * @param turnIndex - The 0-based index of the turn being generated
 * @returns The generated user message text
 */
export async function generateNextUserMessage(
  conversationHistory: ConversationMessage[],
  turnIndex: number,
): Promise<string> {
  const client = new Anthropic();

  // Build the messages array for the API call.
  // The conversation history represents the ongoing conversation between
  // "Alex" (user) and the AI assistant. We add a final user message that
  // instructs the persona to generate the next line.
  const messages: Anthropic.MessageParam[] = [];

  // Add conversation history
  for (const msg of conversationHistory) {
    messages.push({
      role: msg.role,
      content: msg.content,
    });
  }

  // Add the meta-instruction as the final user message.
  // If the history is empty or ends with an assistant message, this works directly.
  // If the history ends with a user message, we need to merge or add an assistant turn.
  if (messages.length === 0 || messages[messages.length - 1].role === 'assistant') {
    messages.push({
      role: 'user',
      content: `[Turn ${turnIndex + 1}/30. Generate the next message from Alex.]`,
    });
  } else {
    // History ends with a user message — add a minimal assistant acknowledgment
    // so we can follow with the meta-instruction as a user message.
    messages.push({
      role: 'assistant',
      content: 'I understand. What would you like to talk about next?',
    });
    messages.push({
      role: 'user',
      content: `[Turn ${turnIndex + 1}/30. Generate the next message from Alex.]`,
    });
  }

  const response = await client.messages.create({
    model: 'claude-3-5-haiku-20241022',
    max_tokens: 300,
    system: PERSONA_PROMPT,
    messages,
  });

  // Extract text from the response
  const textBlock = response.content.find(
    (block): block is Anthropic.TextBlock => block.type === 'text',
  );

  if (!textBlock) {
    throw new Error('Claude API returned no text content');
  }

  return textBlock.text.trim();
}

// ─── Scenario Runner ───

/**
 * Run the full LLM-driven freeform scenario (Scenario H).
 *
 * Generates user messages dynamically via the Claude API, feeds them through
 * the conversation driver, captures the assistant's injected context as the
 * "response", and builds up the conversation history turn by turn.
 *
 * @param driver - The conversation driver that processes each turn
 * @param maxTurns - Maximum number of turns to generate (default: 30)
 * @returns An array of Turn objects representing the full conversation
 */
export async function runLlmDrivenScenario(
  driver: ConversationDriver,
  maxTurns: number = 30,
): Promise<Turn[]> {
  // Check for API key before starting
  if (!isApiKeyAvailable()) {
    console.warn(
      '[llm-orchestrator] ANTHROPIC_API_KEY not set. Skipping Scenario H (LLM-Driven Freeform).',
    );
    return [];
  }

  const conversationHistory: ConversationMessage[] = [];
  const generatedTurns: Turn[] = [];

  console.log(`[llm-orchestrator] Starting LLM-driven scenario (${maxTurns} turns)...`);

  for (let i = 0; i < maxTurns; i++) {
    try {
      // 1. Generate the next user message via Claude API
      const userMessage = await generateNextUserMessage(conversationHistory, i);

      console.log(`[llm-orchestrator] Turn ${i + 1}/${maxTurns}: "${truncate(userMessage, 80)}"`);

      // 2. Create the turn object
      const turn: Turn = {
        index: i,
        userMessage,
      };

      // 3. Feed the turn through the conversation driver
      const result = await driver.processTurn(turn);

      // 4. Record the assistant's response (injected context or a generic ack)
      const assistantResponse = result.injectedContext
        ? `[Memory context injected: ${truncate(result.injectedContext, 200)}]`
        : '[No memory context injected for this turn]';

      turn.assistantResponse = assistantResponse;
      generatedTurns.push(turn);

      // 5. Update conversation history for the next turn generation
      conversationHistory.push({ role: 'user', content: userMessage });
      conversationHistory.push({ role: 'assistant', content: assistantResponse });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error(
        `[llm-orchestrator] Error at turn ${i + 1}: ${errorMessage}`,
      );

      // If we hit a rate limit or API error, wait briefly and continue
      if (errorMessage.includes('rate_limit') || errorMessage.includes('429')) {
        console.warn('[llm-orchestrator] Rate limited. Waiting 5 seconds...');
        await sleep(5000);
        // Retry this turn
        i--;
        continue;
      }

      // For other errors, record a fallback turn and continue
      const fallbackTurn: Turn = {
        index: i,
        userMessage: `[Error generating message: ${errorMessage}]`,
      };
      generatedTurns.push(fallbackTurn);
      conversationHistory.push({ role: 'user', content: 'Tell me something interesting.' });
      conversationHistory.push({
        role: 'assistant',
        content: 'I can help with that. What topics interest you?',
      });
    }
  }

  console.log(
    `[llm-orchestrator] Completed ${generatedTurns.length}/${maxTurns} turns.`,
  );

  return generatedTurns;
}

// ─── Utilities ───

/** Truncate a string to a maximum length, appending "..." if truncated. */
function truncate(s: string, maxLen: number): string {
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen - 3) + '...';
}

/** Sleep for a given number of milliseconds. */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
