"""
TotalReclaw LLM Client Module

Provides a thin Python wrapper around OpenAI-compatible APIs for:
- Fact extraction from conversations
- Deduplication judging
- Entity and relation extraction

Designed for use in the OMBH benchmark harness and E2E pipeline.
"""

from ombh.llm.client import LLMClient, LLMUsageStats
from ombh.llm.prompts import (
    EXTRACTION_RESPONSE_SCHEMA,
    DEDUP_JUDGE_SCHEMA,
    BASE_SYSTEM_PROMPT,
    PRE_COMPACTION_PROMPT,
    POST_TURN_PROMPT,
    EXPLICIT_COMMAND_PROMPT,
    DEDUP_JUDGE_PROMPT,
    CONTRADICTION_DETECTION_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
    BENCHMARK_EXTRACTION_PROMPT,
    format_prompt,
    format_conversation_history,
    format_existing_memories,
    generate_entity_id,
)
from ombh.llm.extractor import FactExtractor, ExtractedFact

__all__ = [
    # Client
    "LLMClient",
    "LLMUsageStats",
    # Prompts
    "EXTRACTION_RESPONSE_SCHEMA",
    "DEDUP_JUDGE_SCHEMA",
    "BASE_SYSTEM_PROMPT",
    "PRE_COMPACTION_PROMPT",
    "POST_TURN_PROMPT",
    "EXPLICIT_COMMAND_PROMPT",
    "DEDUP_JUDGE_PROMPT",
    "CONTRADICTION_DETECTION_PROMPT",
    "ENTITY_EXTRACTION_PROMPT",
    "BENCHMARK_EXTRACTION_PROMPT",
    "format_prompt",
    "format_conversation_history",
    "format_existing_memories",
    "generate_entity_id",
    # Extractor
    "FactExtractor",
    "ExtractedFact",
]
