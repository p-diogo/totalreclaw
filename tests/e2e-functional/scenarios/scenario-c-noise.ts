/**
 * Scenario C: Greeting/Noise Resilience (15 turns)
 *
 * Validates that the relevance threshold gate (B2) prevents noise injection
 * on conversational filler, while still injecting on genuine recall queries.
 *
 * Strategy:
 *   1. Seed 3 facts via explicit totalreclaw_remember tool calls (turns 1-3)
 *   2. Fire 7 noise messages that should NOT trigger injection (turns 4-10)
 *   3. Ask 3 recall questions that SHOULD trigger injection (turns 11-13)
 *   4. Close with 2 more noise messages (turns 14-15)
 *
 * Validates:
 *   - B2: Relevance threshold (cosine < 0.3 = no injection)
 *   - Token savings from skipping noise turns
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md section 3.3
 */

import type { ConversationScenario } from '../types.js';

const scenarioC: ConversationScenario = {
  id: 'scenario-c-noise',
  name: 'Greeting/Noise Resilience',
  description:
    'Noise resilience test validating B2 relevance threshold gate prevents injection on filler messages while allowing injection on genuine recall queries across 15 turns.',
  pluginPath: '../../skill/plugin/index.js',
  triggerCompaction: false,
  turns: [
    // --- Turns 1-3: Seed facts via explicit tool calls ---
    {
      index: 0,
      userMessage: 'Hey, can you remember that I prefer dark mode in all applications? My eyes are really sensitive to bright screens.',
      assistantResponse: 'Got it, I have saved your dark mode preference.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: {
            text: 'I prefer dark mode in all applications',
          },
        },
      ],
    },
    {
      index: 1,
      userMessage: 'Also, please remember that my favorite programming language is Python. I use it for almost everything.',
      assistantResponse: 'Noted, Python is your go-to language.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: {
            text: 'My favorite programming language is Python',
          },
        },
      ],
    },
    {
      index: 2,
      userMessage: 'One more thing -- I have a cat named Luna. She is a calico and she is the best.',
      assistantResponse: 'Adorable! I have saved that you have a calico cat named Luna.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: {
            text: 'I have a cat named Luna',
          },
        },
      ],
    },

    // --- Turns 4-10: Noise messages (B2: should NOT trigger injection) ---
    {
      index: 3,
      userMessage: 'thanks',
      assistantResponse: 'You are welcome!',
    },
    {
      index: 4,
      userMessage: 'ok',
      assistantResponse: 'Alright!',
    },
    {
      index: 5,
      userMessage: 'got it',
      assistantResponse: 'Sounds good.',
    },
    {
      index: 6,
      userMessage: 'sure thing',
      assistantResponse: 'Of course!',
    },
    {
      index: 7,
      userMessage: 'lol',
      assistantResponse: 'Ha!',
    },
    {
      index: 8,
      userMessage: 'yeah that makes sense',
      assistantResponse: 'Glad it is clear.',
    },
    {
      index: 9,
      userMessage: 'cool cool cool',
      assistantResponse: 'Indeed!',
    },

    // --- Turns 11-13: Recall questions (should inject relevant memories) ---
    {
      index: 10,
      userMessage: 'Tell me about my cat',
      assistantResponse: 'You have a calico cat named Luna!',
    },
    {
      index: 11,
      userMessage: 'What programming language do I use?',
      assistantResponse: 'Your favorite programming language is Python.',
    },
    {
      index: 12,
      userMessage: 'Do I prefer light mode or dark mode?',
      assistantResponse: 'You prefer dark mode in all your applications.',
    },

    // --- Turns 14-15: More noise (B2: should NOT trigger injection) ---
    {
      index: 13,
      userMessage: 'haha nice',
      assistantResponse: 'Glad you think so!',
    },
    {
      index: 14,
      userMessage: 'bye!',
      assistantResponse: 'See you later!',
    },
  ],
};

export default scenarioC;
