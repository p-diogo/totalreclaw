"""
TotalReclaw Extraction Prompts — Python port of skill/src/extraction/prompts.ts

All prompts are language-agnostic strings. This module provides:
- JSON schemas for structured output validation
- System and user prompts for each extraction trigger
- Helper functions for formatting conversation history / existing memories
- Entity ID generation

The prompts follow the Mem0-style ADD/UPDATE/DELETE/NOOP pattern for
intelligent deduplication and conflict resolution.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


# ============================================================================
# JSON Schemas for Structured Output
# ============================================================================

EXTRACTION_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "factText": {"type": "string", "maxLength": 512},
                    "type": {
                        "type": "string",
                        "enum": ["fact", "preference", "decision", "episodic", "goal"],
                    },
                    "importance": {"type": "integer", "minimum": 1, "maximum": 10},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "action": {
                        "type": "string",
                        "enum": ["ADD", "UPDATE", "DELETE", "NOOP"],
                    },
                    "existingFactId": {"type": "string"},
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                            },
                            "required": ["id", "name", "type"],
                        },
                    },
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subjectId": {"type": "string"},
                                "predicate": {"type": "string"},
                                "objectId": {"type": "string"},
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                            },
                            "required": [
                                "subjectId",
                                "predicate",
                                "objectId",
                                "confidence",
                            ],
                        },
                    },
                    "reasoning": {"type": "string"},
                },
                "required": [
                    "factText",
                    "type",
                    "importance",
                    "confidence",
                    "action",
                    "entities",
                    "relations",
                ],
            },
        },
        "metadata": {
            "type": "object",
            "properties": {
                "totalTurnsAnalyzed": {"type": "integer"},
                "extractionTimestamp": {"type": "string"},
            },
        },
    },
    "required": ["facts"],
}


DEDUP_JUDGE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["ADD", "UPDATE", "DELETE", "NOOP"],
        },
        "existingFactId": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
    },
    "required": ["decision", "confidence", "reasoning"],
}


# ============================================================================
# System Prompts
# ============================================================================

BASE_SYSTEM_PROMPT = """You are a memory extraction engine for an AI assistant. Your job is to analyze conversations and extract structured, atomic facts that should be remembered long-term.

## Extraction Guidelines

1. **Atomicity**: Each fact should be a single, atomic piece of information
   - GOOD: "User prefers TypeScript over JavaScript for new projects"
   - BAD: "User likes TypeScript, uses VS Code, and works at Google"

2. **Types**:
   - **fact**: Objective information about the user/world
   - **preference**: User's likes, dislikes, or preferences
   - **decision**: Choices the user has made
   - **episodic**: Event-based memories (what happened when)
   - **goal**: User's objectives or targets

3. **Importance Scoring (1-10)**:
   - 1-3: Trivial, unlikely to matter (small talk, pleasantries)
   - 4-6: Useful context (tool preferences, working style)
   - 7-8: Important (key decisions, major preferences)
   - 9-10: Critical (core values, non-negotiables, safety info)

4. **Confidence (0-1)**:
   - How certain are you that this is accurate and worth storing?

5. **Entities**: Extract named entities (people, projects, tools, concepts)
   - Use stable IDs: hash of name+type (e.g., "typescript-tool")
   - Types: person, project, tool, preference, concept, location, etc.

6. **Relations**: Extract relationships between entities
   - Common predicates: prefers, uses, works_on, decided_to_use, dislikes, etc.

7. **Actions (Mem0 pattern)**:
   - **ADD**: New fact, no conflict with existing memories
   - **UPDATE**: Modifies or refines an existing fact (provide existingFactId)
   - **DELETE**: Contradicts and replaces an existing fact
   - **NOOP**: Not worth storing or already captured"""

# Serialised schema for embedding in user prompts
_SCHEMA_STR = json.dumps(EXTRACTION_RESPONSE_SCHEMA, indent=2)
_DEDUP_SCHEMA_STR = json.dumps(DEDUP_JUDGE_SCHEMA, indent=2)


# ============================================================================
# Extraction Prompts
# ============================================================================

PRE_COMPACTION_PROMPT = {
    "system": BASE_SYSTEM_PROMPT,
    "user": f"""## Task: Pre-Compaction Memory Extraction

You are reviewing the last 20 turns of conversation before they are compacted. Extract ALL valuable long-term memories.

## Conversation History (last 20 turns):
{{{{CONVERSATION_HISTORY}}}}

## Existing Memories (for deduplication):
{{{{EXISTING_MEMORIES}}}}

## Instructions:
1. Review each turn carefully for extractable information
2. Extract atomic facts, preferences, decisions, episodic memories, and goals
3. For each fact, determine if it's NEW (ADD), modifies existing (UPDATE), contradicts existing (DELETE), or is redundant (NOOP)
4. Score importance based on long-term relevance
5. Extract entities and relations

## Output Format:
Return a JSON object matching this schema:
{_SCHEMA_STR}

Focus on quality over quantity. Better to have 5 highly accurate facts than 20 noisy ones.""",
}


POST_TURN_PROMPT = {
    "system": BASE_SYSTEM_PROMPT,
    "user": f"""## Task: Quick Turn Extraction

You are doing a lightweight extraction after a few turns. Focus ONLY on high-importance items.

## Recent Turns (last 3):
{{{{CONVERSATION_HISTORY}}}}

## Existing Memories (top matches):
{{{{EXISTING_MEMORIES}}}}

## Instructions:
1. Extract ONLY items with importance >= 7 (critical preferences, key decisions)
2. Skip trivial information - this is a quick pass
3. Use ADD/UPDATE/DELETE/NOOP appropriately
4. Be aggressive about NOOP for low-value content

## Output Format:
Return a JSON object matching this schema:
{_SCHEMA_STR}

Remember: Less is more. Only extract what truly matters.""",
}


EXPLICIT_COMMAND_PROMPT = {
    "system": BASE_SYSTEM_PROMPT,
    "user": f"""## Task: Explicit Memory Storage

The user has explicitly requested to remember something. This is a HIGH PRIORITY extraction.

## User's Explicit Request:
{{{{USER_REQUEST}}}}

## Conversation Context:
{{{{CONVERSATION_CONTEXT}}}}

## Instructions:
1. Parse what the user wants remembered
2. Boost importance by +1 (explicit requests matter more)
3. Extract as atomic fact(s) with appropriate type
4. Check against existing memories for UPDATE/DELETE
5. Set confidence HIGH (user explicitly wants this stored)

## Output Format:
Return a JSON object matching this schema:
{_SCHEMA_STR}

This is user-initiated storage - ensure accuracy and capture their intent precisely.""",
}


# ============================================================================
# Deduplication Prompts
# ============================================================================

DEDUP_JUDGE_PROMPT = {
    "system": """You are a memory deduplication judge. Your job is to determine if a new fact should be added as new, update an existing fact, delete/replace an existing fact, or be ignored as redundant.

## Decision Rules:

1. **ADD**: The fact is genuinely new information not covered by existing memories
2. **UPDATE**: The fact refines, clarifies, or partially modifies an existing fact
3. **DELETE**: The fact directly contradicts an existing fact and should replace it
4. **NOOP**: The fact is already fully captured by existing memories

Be strict about NOOP - if the information is essentially the same, mark it as NOOP.""",

    "user": f"""## New Fact to Evaluate:
{{{{NEW_FACT}}}}

## Similar Existing Facts:
{{{{EXISTING_FACTS}}}}

## Instructions:
1. Compare the new fact against each existing fact
2. Determine the appropriate action (ADD/UPDATE/DELETE/NOOP)
3. If UPDATE or DELETE, identify which existing fact to modify
4. Provide your confidence (0-1) and reasoning

## Output Format:
Return a JSON object matching this schema:
{_DEDUP_SCHEMA_STR}""",
}


CONTRADICTION_DETECTION_PROMPT = {
    "system": """You are a contradiction detector for memory facts. Determine if two facts contradict each other.

## Contradiction Types:
1. **Direct negation**: "User likes X" vs "User dislikes X"
2. **Mutually exclusive values**: "User uses VS Code" vs "User uses IntelliJ exclusively"
3. **Temporal replacement**: "User works at Google" vs "User now works at Meta"

Not all differences are contradictions - some facts can coexist (context-dependent preferences).""",

    "user": """## Fact A (new):
{{FACT_A}}

## Fact B (existing):
{{FACT_B}}

## Task:
Determine if these facts contradict each other. If they do, which one should be kept?

## Output Format:
{
  "isContradiction": boolean,
  "contradictionType": "direct_negation" | "mutually_exclusive" | "temporal_replacement" | "none",
  "shouldKeep": "A" | "B" | "both",
  "reasoning": string
}""",
}


ENTITY_EXTRACTION_PROMPT = {
    "system": """You are an entity extractor. Extract named entities from text with their types.

## Entity Types:
- **person**: Named individuals
- **project**: Projects, codebases, products
- **tool**: Software tools, libraries, frameworks
- **preference**: Named preferences (e.g., "TypeScript" as a preference entity)
- **concept**: Abstract concepts, methodologies
- **location**: Physical or virtual locations
- **organization**: Companies, teams, groups

## ID Generation:
Generate stable IDs by combining normalized name + type (lowercase, no spaces).
Example: "TypeScript" + "tool" -> "typescript-tool" """,

    "user": """## Text to Analyze:
{{TEXT}}

## Output Format:
{
  "entities": [
    {
      "id": "string (normalized-name-type)",
      "name": "string (original name)",
      "type": "string (entity type)"
    }
  ]
}""",
}


# ============================================================================
# Benchmark-Specific Extraction Prompt (Simplified for E2E Pipeline)
# ============================================================================

BENCHMARK_EXTRACTION_PROMPT = {
    "system": BASE_SYSTEM_PROMPT,
    "user": f"""## Task: Extract Long-Term Memory Facts from Conversation

Analyse the following raw conversation messages and extract ALL facts, preferences, decisions, events, and goals worth remembering long-term.

## Raw Conversation:
{{{{CONVERSATION}}}}

## Instructions:
1. Extract atomic facts - each one a single piece of information
2. Score importance 1-10 (focus on items >= 4)
3. Score confidence 0-1
4. All facts should have action "ADD" (no existing memories to compare against)
5. Extract entities and relations where possible

## Output Format:
Return a JSON object matching this schema:
{_SCHEMA_STR}

Focus on quality over quantity. Better to have 5 highly accurate facts than 20 noisy ones.""",
}


# ============================================================================
# Helper Functions
# ============================================================================

def format_prompt(
    prompt_template: Dict[str, str],
    **replacements: str,
) -> Dict[str, str]:
    """
    Format a prompt template by replacing {{PLACEHOLDER}} tokens.

    Args:
        prompt_template: Dict with "system" and "user" keys
        **replacements: Key-value pairs where key matches PLACEHOLDER name

    Returns:
        Dict with "system" and "user" keys, placeholders replaced

    Example:
        formatted = format_prompt(
            PRE_COMPACTION_PROMPT,
            CONVERSATION_HISTORY="User: Hello...",
            EXISTING_MEMORIES="(none)",
        )
    """
    system = prompt_template["system"]
    user = prompt_template["user"]

    for key, value in replacements.items():
        placeholder = "{{" + key + "}}"
        system = system.replace(placeholder, value)
        user = user.replace(placeholder, value)

    return {"system": system, "user": user}


def format_conversation_history(
    turns: List[Dict[str, Any]],
) -> str:
    """
    Format conversation turns for injection into prompts.

    Each turn should have: role, content, and optionally timestamp.

    Args:
        turns: List of dicts with "role", "content", and optionally "timestamp"

    Returns:
        Formatted string of conversation history
    """
    lines = []
    for i, turn in enumerate(turns):
        role = turn.get("role", "user").upper()
        content = turn.get("content", "")
        timestamp = turn.get("timestamp")

        if timestamp:
            if isinstance(timestamp, datetime):
                ts_str = timestamp.isoformat()
            else:
                ts_str = str(timestamp)
            lines.append(f"[{i + 1}] {role} ({ts_str}):\n{content}")
        else:
            lines.append(f"[{i + 1}] {role}:\n{content}")

    return "\n\n".join(lines)


def format_existing_memories(
    memories: List[Dict[str, Any]],
) -> str:
    """
    Format existing memories for deduplication context in prompts.

    Each memory should have: id, factText (or fact_text), type, importance.

    Args:
        memories: List of memory dicts

    Returns:
        Formatted string of existing memories
    """
    if not memories:
        return "(No existing memories found)"

    lines = []
    for i, mem in enumerate(memories):
        fact_text = mem.get("factText") or mem.get("fact_text", "")
        mem_type = mem.get("type", "unknown")
        importance = mem.get("importance", 5)
        mem_id = mem.get("id", f"mem_{i}")

        lines.append(
            f"[{i + 1}] ID: {mem_id}\n"
            f"    Type: {mem_type}\n"
            f"    Importance: {importance}\n"
            f"    Fact: {fact_text}"
        )

    return "\n\n".join(lines)


def generate_entity_id(name: str, entity_type: str) -> str:
    """
    Generate a stable entity ID from name and type.

    Normalizes to lowercase, replaces non-alphanumeric chars with hyphens.

    Args:
        name: Entity name (e.g., "TypeScript")
        entity_type: Entity type (e.g., "tool")

    Returns:
        Stable ID string (e.g., "typescript-tool")
    """
    normalized = re.sub(r"[^a-z0-9]", "-", name.lower())
    # Collapse multiple hyphens and strip leading/trailing
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return f"{normalized}-{entity_type}"
