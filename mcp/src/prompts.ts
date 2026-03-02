// ── Layer 1: Server Instructions ──────────────────────────────────────────────
// Returned in the MCP `initialize` response. Clients SHOULD inject this into the
// system prompt, giving the LLM persistent behavioral guidance for the session.

export const SERVER_INSTRUCTIONS = `
You have access to TotalReclaw, a zero-knowledge encrypted memory vault that persists across conversations.

## CRITICAL: Automatic Memory Behaviors

### At Conversation Start
ALWAYS call totalreclaw_recall at the beginning of EVERY new conversation with a brief summary of the user's first message as the query. This loads relevant context from past conversations. Present recalled memories naturally as context -- do not announce "I found these memories" or list them explicitly unless the user asks.

### During Conversation
When the user shares ANY of the following, call totalreclaw_remember to store it:
- Personal preferences ("I prefer...", "I like...", "I hate...")
- Personal information (name, location, occupation, family details)
- Decisions or goals ("I decided to...", "I want to...")
- Corrections to previous information ("Actually, I'm vegan now")
- Important events or dates ("My birthday is...", "I started a new job")
- Technical preferences (programming language, tools, frameworks)

Do NOT store:
- Temporary/transient context (weather, current task details)
- Information about third parties the user hasn't asked to remember
- Sensitive credentials (passwords, API keys, tokens)

### Memory Hygiene
- Before storing a new fact, check recalled memories to avoid duplicates
- When the user corrects information, store the correction (the system handles deduplication)
- Use importance 7-9 for core identity/preferences, 4-6 for moderate facts, 1-3 for minor details
`;

// Keep backward-compat export name (some callers may still reference it)
export const SYSTEM_PROMPT_FRAGMENT = SERVER_INSTRUCTIONS;

// ── Layer 2: Enhanced Tool Descriptions ──────────────────────────────────────

export const REMEMBER_TOOL_DESCRIPTION = `Store one or more facts in the encrypted memory vault.

Call this tool whenever the user shares personal information, preferences, decisions, or important facts worth remembering across conversations.

IMPORTANT: Extract atomic facts, not entire conversation snippets.
Good: "User is vegan"
Bad: "User said they recently became vegan and prefer organic food from local farms"

The facts parameter accepts an array, so you can store multiple facts in a single call.

Each fact needs:
- text: The atomic fact (required)
- importance: 1-10 scale (optional, default 5)
  - 9-10: Core identity (name, fundamental values)
  - 7-8: Important preferences (diet, work style)
  - 5-6: Moderate facts (schedule, minor preferences)
  - 3-4: Low priority (casual mentions)
  - 1-2: Ephemeral (likely to change)
- type: Category (optional) -- "fact", "preference", "decision", "episodic", "goal"

The vault handles deduplication automatically. If a similar fact exists, it will be updated rather than duplicated.`;

export const RECALL_TOOL_DESCRIPTION = `Search your encrypted memory vault for relevant past context.

IMPORTANT: You SHOULD call this tool at the START of every conversation with a query based on the user's first message. This ensures continuity across sessions.

Use this tool when:
- Starting a new conversation (query = summary of user's first message)
- User asks about their preferences or past information
- User references something from a previous conversation
- You need context about the user's background

Parameters:
- query: Natural language search (required). Keep it concise -- 5-15 words work best.
- k: Number of results (default 8, max 50). Use 3-5 for quick lookups, 8-12 for broad context.

The results are end-to-end encrypted. The server never sees plaintext.`;

export const FORGET_TOOL_DESCRIPTION = `Delete a specific memory from your vault.

WHEN TO USE:
- User explicitly asks to forget something
- User says information is outdated or incorrect
- User requests to remove sensitive information

WHEN NOT TO USE:
- To update information (use remember with updated fact instead)
- Without user's explicit request

EXAMPLES:
- User: "Forget that I work at Google, I left"
  -> Call: totalreclaw_forget({ fact_id: "the-fact-id" })

PARAMETERS:
- fact_id: The ID of the fact to forget (required)
  OR
- query: Forget all memories matching query (optional)`;

export const EXPORT_TOOL_DESCRIPTION = `Export all memories in plaintext for portability.

WHEN TO USE:
- User wants to backup their memories
- User wants to transfer memories to another system
- User wants to see all stored information

OUTPUT FORMATS:
- markdown: Human-readable format
- json: Machine-readable format for import

EXAMPLES:
- User: "Export all my memories"
  -> Call: totalreclaw_export({ format: "markdown" })

PARAMETERS:
- format: Output format "markdown" or "json" (default: markdown)
- namespace: Export only specific namespace (optional)`;

export const IMPORT_TOOL_DESCRIPTION = `Import memories from an exported backup.

WHEN TO USE:
- User wants to restore memories from backup
- User wants to transfer memories from another TotalReclaw instance
- User has a JSON or Markdown export they want to import

MERGE STRATEGIES:
- skip_existing: Skip facts that already exist (default)
- overwrite: Replace existing facts with imported ones
- merge: Use LLM-assisted conflict resolution

EXAMPLES:
- User: "Import memories from this backup file"
  -> Call: totalreclaw_import({ content: "...", format: "json" })

PARAMETERS:
- content: The exported content (JSON or Markdown string)
- format: Format of content "markdown" or "json" (auto-detected if not specified)
- namespace: Target namespace (defaults to source namespace)
- merge_strategy: How to handle conflicts (default: skip_existing)
- validate_only: Parse and validate without importing (dry-run)`;

// ── Layer 5: Prompt Fallback Templates ───────────────────────────────────────

export const PROMPT_DEFINITIONS = [
  {
    name: 'totalreclaw_start',
    title: 'Start with Memory',
    description:
      'Load your memory context for this conversation. Use this if memories were not loaded automatically.',
    arguments: [
      {
        name: 'topic',
        description: 'Optional topic to focus memory recall on',
        required: false,
      },
    ],
  },
  {
    name: 'totalreclaw_save',
    title: 'Save to Memory',
    description:
      'Extract and save important facts from this conversation to your memory vault.',
    arguments: [] as Array<{ name: string; description: string; required: boolean }>,
  },
];

export function getPromptMessages(
  promptName: string,
  args?: Record<string, string>
): Array<{ role: string; content: { type: string; text: string } }> {
  switch (promptName) {
    case 'totalreclaw_start': {
      const topic = args?.topic || 'recent context';
      return [
        {
          role: 'user',
          content: {
            type: 'text',
            text: `Please recall my relevant memories about ${topic} and use them to personalize our conversation.`,
          },
        },
      ];
    }

    case 'totalreclaw_save':
      return [
        {
          role: 'user',
          content: {
            type: 'text',
            text: `Review our conversation and extract any important facts, preferences, decisions, or personal information I shared. Store each one using totalreclaw_remember with appropriate importance scores. Extract atomic facts, not summaries.`,
          },
        },
      ];

    case 'totalreclaw_instructions':
      return [
        {
          role: 'assistant',
          content: { type: 'text', text: SERVER_INSTRUCTIONS },
        },
      ];

    default:
      throw new Error(`Unknown prompt: ${promptName}`);
  }
}
