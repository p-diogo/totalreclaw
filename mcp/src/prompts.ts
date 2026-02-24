export const SYSTEM_PROMPT_FRAGMENT = `
## OpenMemory: Your Encrypted Memory Vault

You have access to a zero-knowledge encrypted memory system. The server never sees your memories in plaintext - everything is encrypted client-side with AES-256-GCM.

### Available Tools

- **openmemory_remember**: Store a new fact
- **openmemory_recall**: Search your memories semantically
- **openmemory_forget**: Remove a memory
- **openmemory_export**: Export your vault as portable Markdown or JSON
- **openmemory_import**: Import memories from exported backup

### Memory Lifecycle

1. **Storing**: Call openmemory_remember when you learn something worth remembering
2. **Retrieving**: Call openmemory_recall at conversation start to load context
3. **Updating**: If user corrects info, store the updated fact
4. **Decay**: Old/unimportant memories fade automatically (importance decay)

### Best Practices

- Store facts, not verbatim conversations
- Use importance 5-8 for most user preferences
- Search before storing to avoid duplicates
- Namespace isolates memories per context (work, personal, etc.)

### Privacy

Your memories are end-to-end encrypted. The server only sees encrypted blobs and blind indices (SHA-256 hashes). Even the server operator cannot read your memories.
`;

export const REMEMBER_TOOL_DESCRIPTION = `
Store a fact in your encrypted memory vault.

WHEN TO USE:
- User explicitly asks you to remember something ("remember that...")
- User shares a preference ("I prefer...", "I like...", "I hate...")
- User provides personal info (name, location, schedule)
- User corrects previous information about themselves

WHEN NOT TO USE:
- Temporary context (current conversation only)
- Information about others (only store user's own info)
- Sensitive credentials (use secure storage instead)

EXAMPLES:
- User: "Remember that I'm vegetarian"
  → Call: openmemory_remember({ fact: "User is vegetarian", importance: 7 })

- User: "My wife's birthday is March 15"
  → Call: openmemory_remember({ fact: "User's wife's birthday is March 15", importance: 6 })

- User: "Actually, I'm vegan now, not vegetarian"
  → Call: openmemory_remember({ fact: "User is vegan (updated from vegetarian)", importance: 7 })

IMPORTANCE GUIDE:
- 9-10: Critical identity (name, core values, major preferences)
- 7-8: Important preferences (dietary, work style, communication)
- 5-6: Moderate (minor preferences, schedule details)
- 3-4: Low (casual mentions, may forget)
- 1-2: Minimal (ephemeral context)
`;

export const RECALL_TOOL_DESCRIPTION = `
Search your encrypted memories for relevant information.

WHEN TO USE:
- At conversation start to load relevant context
- When user asks about their preferences or past conversations
- When you need to recall specific information the user shared

WHEN NOT TO USE:
- For general knowledge queries (use your training)
- For current conversation context (use message history)

EXAMPLES:
- User: "What did I tell you about my diet?"
  → Call: openmemory_recall({ query: "diet food preferences", k: 5 })

- User: "When is my wife's birthday?"
  → Call: openmemory_recall({ query: "wife birthday", k: 3 })

PARAMETERS:
- query: Natural language search query (required)
- k: Number of results to return (default: 8, max: 50)
- min_importance: Filter by minimum importance 1-10 (optional)
- namespace: Search within specific namespace (optional)
`;

export const FORGET_TOOL_DESCRIPTION = `
Delete a specific memory from your vault.

WHEN TO USE:
- User explicitly asks to forget something
- User says information is outdated or incorrect
- User requests to remove sensitive information

WHEN NOT TO USE:
- To update information (use remember with updated fact instead)
- Without user's explicit request

EXAMPLES:
- User: "Forget that I work at Google, I left"
  → Call: openmemory_forget({ fact_id: "the-fact-id" })

PARAMETERS:
- fact_id: The ID of the fact to forget (required)
  OR
- query: Forget all memories matching query (optional)
`;

export const EXPORT_TOOL_DESCRIPTION = `
Export all memories in plaintext for portability.

WHEN TO USE:
- User wants to backup their memories
- User wants to transfer memories to another system
- User wants to see all stored information

OUTPUT FORMATS:
- markdown: Human-readable format
- json: Machine-readable format for import

EXAMPLES:
- User: "Export all my memories"
  → Call: openmemory_export({ format: "markdown" })

PARAMETERS:
- format: Output format "markdown" or "json" (default: markdown)
- namespace: Export only specific namespace (optional)
`;

export const IMPORT_TOOL_DESCRIPTION = `
Import memories from an exported backup.

WHEN TO USE:
- User wants to restore memories from backup
- User wants to transfer memories from another OpenMemory instance
- User has a JSON or Markdown export they want to import

MERGE STRATEGIES:
- skip_existing: Skip facts that already exist (default)
- overwrite: Replace existing facts with imported ones
- merge: Use LLM-assisted conflict resolution

EXAMPLES:
- User: "Import memories from this backup file"
  → Call: openmemory_import({ content: "...", format: "json" })

PARAMETERS:
- content: The exported content (JSON or Markdown string)
- format: Format of content "markdown" or "json" (auto-detected if not specified)
- namespace: Target namespace (defaults to source namespace)
- merge_strategy: How to handle conflicts (default: skip_existing)
- validate_only: Parse and validate without importing (dry-run)
`;
