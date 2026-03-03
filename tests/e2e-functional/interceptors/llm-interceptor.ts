/**
 * LLM API Mock Interceptor
 *
 * Monkey-patches `globalThis.fetch` to intercept calls to LLM API endpoints
 * (OpenAI, Anthropic) and return mock extraction responses. This enables
 * testing the full extraction -> store -> search -> recall pipeline without
 * requiring a real LLM API key.
 *
 * Two types of intercepted calls:
 *   A) Plugin extraction calls (OpenAI format) -- from the plugin's extractor.
 *      Returns OpenAI chat completion format with extracted facts JSON.
 *   B) Orchestrator calls (Anthropic format) -- from llm-orchestrator.ts for
 *      Scenario H. Returns Anthropic message format with pre-scripted Alex Chen
 *      user messages.
 *
 * Mock extraction logic (type A):
 *   - Parses user messages from the conversation text in the request body
 *   - Filters out short/noise messages (greetings, filler)
 *   - Returns each substantive user message as an extracted fact
 *   - Facts have importance=7 (above the >=6 threshold in the extractor)
 */

const LLM_API_HOSTS = [
  'api.openai.com',
  'api.anthropic.com',
  'api.z.ai',
  'generativelanguage.googleapis.com',
  'api.mistral.ai',
  'api.groq.com',
  'api.deepseek.com',
  'openrouter.ai',
  'api.x.ai',
  'api.together.xyz',
  'api.cerebras.ai',
];

const NOISE_PATTERNS = [
  /^(hi|hey|hello|bye|thanks|thank you|ok|okay|sure|yeah|yes|no|great|cool|lol|haha|nice|got it)\b/i,
  /^.{0,15}$/,  // Very short messages (< 16 chars)
];

// ---------------------------------------------------------------------------
// Pre-scripted Alex Chen messages for Scenario H (Anthropic orchestrator)
// ---------------------------------------------------------------------------

/**
 * 30 pre-scripted messages matching the Alex Chen persona from llm-orchestrator.ts.
 * Mix of: personal facts, recall questions, short replies, topic shifts.
 * ~20% are short noise replies. After turn 20, recall questions appear.
 */
const ALEX_CHEN_MESSAGES: string[] = [
  // Turn 0-4: Introduction, personal facts (product design, Austin)
  "Hey! I'm Alex, I just started a new role as a product designer at a fintech startup here in Austin. We moved from Chicago about three months ago.",
  "Yeah, the move was a big change. My fiancee and I are still getting settled. We just got engaged actually -- planning the wedding for fall 2026.",
  "thanks",
  "I've been trying to keep up with my hobbies despite the move. I go rock climbing at Austin Bouldering Project every Tuesday and Thursday evening.",
  "Oh, and I'm vegetarian and lactose intolerant, so finding good restaurants in a new city has been an adventure. Any suggestions for Austin?",

  // Turn 5-9: Hobbies, pets, goals
  "I also got really into sourdough bread baking during the pandemic. My starter is named Gerald -- he's almost 4 years old now. I feed him every morning at 7am.",
  "My golden retriever Max loves Austin so much more than Chicago. He's 3 years old and absolutely obsessed with the off-leash areas at Zilker Park.",
  "ok got it",
  "One of my big goals right now is learning Spanish. I've been using Duolingo for 127 days straight and I just started a conversational class on Wednesday evenings.",
  "I'm also training for my first half-marathon -- the Austin Half in February 2027. Right now I can run about 7 miles comfortably.",

  // Turn 10-14: Work details, photography, daily routine
  "At work we're building a peer-to-peer payments app targeting college students. I'm leading the design for the onboarding flow. We use Figma and have a design system called Prism.",
  "Photography is another big hobby of mine. I shoot on a Fujifilm X-T5 and I'm really into street photography and architecture shots.",
  "sure",
  "My typical morning routine is: wake up at 6:15, feed Max, feed Gerald the sourdough starter, go for a 3-mile run, then start work by 8:30. I work remotely on Mondays and Fridays.",
  "For the wedding, we're looking at venues in the Hill Country. Our budget is around $35,000 and we want something outdoors with a max of 120 guests.",

  // Turn 15-19: More facts, preferences, details
  "My favorite programming language for prototyping is Python, even though I mainly work in Figma. I like building small tools to automate my design workflow.",
  "I prefer dark mode for everything -- apps, websites, IDE. Light mode physically hurts my eyes, especially at night.",
  "nice",
  "We adopted Max from Austin Pets Alive when we first visited Austin last year. That trip is actually what convinced us to move here. He was the first dog we saw.",
  "My fiancee's name is Jordan. She works as a data engineer at a healthcare company. She's the one who got me into rock climbing actually.",

  // Turn 20-24: Recall questions + new facts
  "Hey, do you remember what gym I go rock climbing at? I want to tell a friend about it.",
  "What was the name of my sourdough starter again? I was telling a coworker about it and blanked for a second.",
  "Do you remember what half-marathon I'm training for and when it is?",
  "yeah thanks",
  "Can you remind me what our wedding budget is? Jordan and I are reviewing our spreadsheet tonight.",

  // Turn 25-29: More recall + final facts
  "What camera do I shoot with? My friend wants to get into photography and I want to recommend the same one.",
  "Do you remember what design tool and design system we use at work?",
  "I just signed up for a pottery class on Saturday mornings at the community center. Figured I'd try something completely new.",
  "What day did I say I do my Spanish conversational class?",
  "Do you remember where we adopted Max from? I want to write them a thank-you note for our one-year adoption anniversary.",
];

let anthropicTurnCounter = 0;

let llmOriginalFetch: typeof globalThis.fetch | null = null;
let extractionCallCount = 0;

/**
 * Install the LLM mock interceptor.
 *
 * MUST be installed AFTER the GraphQL interceptor (if used), because
 * we chain to whatever `globalThis.fetch` is at install time.
 */
export function installLLMInterceptor(): void {
  if (llmOriginalFetch !== null) return; // Already installed

  llmOriginalFetch = globalThis.fetch;

  globalThis.fetch = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    const isLLMAPI = LLM_API_HOSTS.some((host) => url.includes(host));

    if (!isLLMAPI || !init?.body) {
      return llmOriginalFetch!(input, init);
    }

    let body: Record<string, unknown>;
    try {
      body = JSON.parse(init.body as string);
    } catch {
      return llmOriginalFetch!(input, init);
    }

    // Detect if this is a chat completion call
    const isChatCompletion =
      url.includes('/chat/completions') || url.includes('/messages');

    if (!isChatCompletion) {
      return llmOriginalFetch!(input, init);
    }

    // -----------------------------------------------------------------------
    // Type B: Anthropic orchestrator calls (Scenario H)
    // Detected by: URL contains api.anthropic.com AND endpoint is /messages
    // (but NOT /chat/completions which would be OpenAI-compatible proxying)
    // -----------------------------------------------------------------------
    const isAnthropicCall =
      url.includes('api.anthropic.com') && url.includes('/messages');

    if (isAnthropicCall) {
      const messageIndex = anthropicTurnCounter % ALEX_CHEN_MESSAGES.length;
      const messageText = ALEX_CHEN_MESSAGES[messageIndex];
      anthropicTurnCounter++;

      const anthropicResponse = JSON.stringify({
        id: `msg_mock_${String(messageIndex + 1).padStart(3, '0')}`,
        type: 'message',
        role: 'assistant',
        content: [{ type: 'text', text: messageText }],
        model: 'claude-3-5-haiku-20241022',
        stop_reason: 'end_turn',
        stop_sequence: null,
        usage: { input_tokens: 100, output_tokens: 50 },
      });

      return new Response(anthropicResponse, {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // -----------------------------------------------------------------------
    // Type A: Plugin extraction calls (OpenAI format)
    // -----------------------------------------------------------------------
    extractionCallCount++;

    // Extract conversation text from the messages
    const messages = (body.messages as Array<{ role: string; content: string }>) ?? [];
    const userContent =
      messages.find((m) => m.role === 'user')?.content ?? '';

    // Parse user messages from the conversation text
    // The extractor formats them as: [user]: message text
    const userMessages = extractUserMessages(userContent);

    // Generate mock extraction facts
    const facts = userMessages
      .filter((msg) => !isNoise(msg))
      .map((msg) => ({
        text: msg.slice(0, 256),
        type: classifyFact(msg),
        importance: 7,
      }));

    // Return mock OpenAI response format
    const responseBody = JSON.stringify({
      choices: [
        {
          message: {
            content: JSON.stringify(facts),
          },
        },
      ],
    });

    return new Response(responseBody, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
}

/**
 * Uninstall the LLM mock interceptor.
 */
export function uninstallLLMInterceptor(): void {
  if (llmOriginalFetch !== null) {
    globalThis.fetch = llmOriginalFetch;
    llmOriginalFetch = null;
  }
}

/**
 * Get the number of LLM extraction calls intercepted.
 */
export function getExtractionCallCount(): number {
  return extractionCallCount;
}

/**
 * Reset the extraction call counter.
 */
export function resetExtractionCallCount(): void {
  extractionCallCount = 0;
}

/**
 * Reset the Anthropic turn counter (pre-scripted message index).
 * Call between scenarios to restart the Alex Chen message sequence.
 */
export function resetAnthropicTurnCounter(): void {
  anthropicTurnCounter = 0;
}

/**
 * Get the next pre-scripted Alex Chen message (for the HTTP-based mock).
 * Used by mock-server.ts to serve /v1/messages for the Anthropic SDK,
 * which bypasses globalThis.fetch and uses its own HTTP client.
 */
export function getNextAlexChenMessage(): { index: number; text: string } {
  const index = anthropicTurnCounter % ALEX_CHEN_MESSAGES.length;
  const text = ALEX_CHEN_MESSAGES[index];
  anthropicTurnCounter++;
  return { index, text };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Extract user messages from the conversation text passed to the extractor.
 * Format: "[user]: message text\n\n[assistant]: response text"
 */
function extractUserMessages(text: string): string[] {
  const messages: string[] = [];
  const lines = text.split('\n');

  for (const line of lines) {
    const match = line.match(/^\[user\]:\s*(.+)/i);
    if (match) {
      messages.push(match[1].trim());
    }
  }

  return messages;
}

/**
 * Check if a message is noise/filler that should not be extracted.
 */
function isNoise(message: string): boolean {
  return NOISE_PATTERNS.some((pattern) => pattern.test(message.trim()));
}

/**
 * Simple heuristic to classify a fact type based on content.
 */
function classifyFact(
  message: string,
): 'fact' | 'preference' | 'decision' | 'episodic' | 'goal' {
  const lower = message.toLowerCase();
  if (
    lower.includes('prefer') ||
    lower.includes('like') ||
    lower.includes('love') ||
    lower.includes('favorite') ||
    lower.includes('obsessed')
  ) {
    return 'preference';
  }
  if (lower.includes('decided') || lower.includes('chose') || lower.includes('picked')) {
    return 'decision';
  }
  if (lower.includes('want to') || lower.includes('planning to') || lower.includes('goal')) {
    return 'goal';
  }
  return 'fact';
}
