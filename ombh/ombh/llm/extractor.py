"""
Fact Extractor — Uses LLMClient + extraction prompts to extract structured
facts from raw conversations.

This is the Python counterpart of skill/src/extraction/extractor.ts.
It is designed for the OMBH benchmark harness: given raw conversation text,
it calls the LLM with the appropriate extraction prompt and returns a list
of validated, structured facts.

Usage:
    from ombh.llm.client import LLMClient
    from ombh.llm.extractor import FactExtractor

    client = LLMClient()
    extractor = FactExtractor(client)
    facts = await extractor.extract_from_conversation(raw_text)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ombh.llm.client import LLMClient
from ombh.llm.prompts import (
    BENCHMARK_EXTRACTION_PROMPT,
    PRE_COMPACTION_PROMPT,
    POST_TURN_PROMPT,
    EXPLICIT_COMMAND_PROMPT,
    DEDUP_JUDGE_PROMPT,
    ENTITY_EXTRACTION_PROMPT,
    format_prompt,
    format_conversation_history,
    format_existing_memories,
    generate_entity_id,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class ExtractedEntity:
    """An entity extracted from text."""
    id: str
    name: str
    type: str

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "type": self.type}


@dataclass
class ExtractedRelation:
    """A relation between two entities."""
    subject_id: str
    predicate: str
    object_id: str
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subjectId": self.subject_id,
            "predicate": self.predicate,
            "objectId": self.object_id,
            "confidence": self.confidence,
        }


@dataclass
class ExtractedFact:
    """A single extracted fact with metadata."""
    fact_text: str
    type: str  # fact, preference, decision, episodic, goal
    importance: int  # 1-10
    confidence: float  # 0-1
    action: str = "ADD"  # ADD, UPDATE, DELETE, NOOP
    existing_fact_id: Optional[str] = None
    entities: List[ExtractedEntity] = field(default_factory=list)
    relations: List[ExtractedRelation] = field(default_factory=list)
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factText": self.fact_text,
            "type": self.type,
            "importance": self.importance,
            "confidence": self.confidence,
            "action": self.action,
            "existingFactId": self.existing_fact_id,
            "entities": [e.to_dict() for e in self.entities],
            "relations": [r.to_dict() for r in self.relations],
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> Optional["ExtractedFact"]:
        """
        Parse a single fact from the LLM's JSON response.

        Returns None if the fact is invalid / missing required fields.
        """
        try:
            fact_text = raw.get("factText", "")
            if not fact_text or not isinstance(fact_text, str):
                return None

            fact_type = raw.get("type", "fact")
            valid_types = {"fact", "preference", "decision", "episodic", "goal"}
            if fact_type not in valid_types:
                fact_type = "fact"

            importance = raw.get("importance", 5)
            if not isinstance(importance, (int, float)):
                importance = 5
            importance = max(1, min(10, int(round(importance))))

            confidence = raw.get("confidence", 0.8)
            if not isinstance(confidence, (int, float)):
                confidence = 0.8
            confidence = max(0.0, min(1.0, float(confidence)))

            action = raw.get("action", "ADD")
            valid_actions = {"ADD", "UPDATE", "DELETE", "NOOP"}
            if action not in valid_actions:
                action = "ADD"

            # Parse entities
            entities = []
            for ent_raw in raw.get("entities", []):
                if isinstance(ent_raw, dict):
                    name = ent_raw.get("name", "")
                    ent_type = ent_raw.get("type", "concept")
                    ent_id = ent_raw.get("id") or generate_entity_id(name, ent_type)
                    if name:
                        entities.append(ExtractedEntity(
                            id=ent_id, name=name, type=ent_type
                        ))

            # Parse relations
            relations = []
            for rel_raw in raw.get("relations", []):
                if isinstance(rel_raw, dict):
                    subject = rel_raw.get("subjectId", "")
                    predicate = rel_raw.get("predicate", "")
                    obj = rel_raw.get("objectId", "")
                    rel_conf = rel_raw.get("confidence", 0.5)
                    if subject and predicate and obj:
                        relations.append(ExtractedRelation(
                            subject_id=subject,
                            predicate=predicate,
                            object_id=obj,
                            confidence=max(0.0, min(1.0, float(rel_conf))),
                        ))

            return cls(
                fact_text=fact_text.strip()[:512],
                type=fact_type,
                importance=importance,
                confidence=confidence,
                action=action,
                existing_fact_id=raw.get("existingFactId"),
                entities=entities,
                relations=relations,
                reasoning=raw.get("reasoning"),
            )

        except Exception as e:
            logger.warning("Failed to parse extracted fact: %s -- raw: %s", e, raw)
            return None


@dataclass
class ExtractionResult:
    """Result of a fact extraction call."""
    facts: List[ExtractedFact]
    raw_response: str
    processing_time_ms: float
    parse_errors: List[str] = field(default_factory=list)

    @property
    def fact_count(self) -> int:
        return len(self.facts)

    @property
    def avg_importance(self) -> float:
        if not self.facts:
            return 0.0
        return sum(f.importance for f in self.facts) / len(self.facts)

    @property
    def avg_confidence(self) -> float:
        if not self.facts:
            return 0.0
        return sum(f.confidence for f in self.facts) / len(self.facts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": [f.to_dict() for f in self.facts],
            "fact_count": self.fact_count,
            "avg_importance": self.avg_importance,
            "avg_confidence": self.avg_confidence,
            "processing_time_ms": self.processing_time_ms,
            "parse_errors": self.parse_errors,
        }


# ============================================================================
# Fact Extractor
# ============================================================================

class FactExtractor:
    """
    Main extraction class that calls the LLM and parses structured facts.

    Args:
        llm_client:   An LLMClient instance
        min_importance: Minimum importance to include in results (default 1)
        temperature:   Override temperature for extraction calls
    """

    def __init__(
        self,
        llm_client: LLMClient,
        min_importance: int = 1,
        temperature: Optional[float] = None,
    ):
        self._llm = llm_client
        self._min_importance = min_importance
        self._temperature = temperature  # None = use client default

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_from_conversation(
        self,
        conversation_text: str,
        existing_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> ExtractionResult:
        """
        Extract facts from raw conversation text.

        This is the primary method for the E2E benchmark. It uses the
        BENCHMARK_EXTRACTION_PROMPT which is optimised for cold-start
        extraction (no prior context).

        Falls back to heuristic extraction when the LLM is unavailable.

        Args:
            conversation_text: Raw conversation messages as a single string
            existing_memories: Optional list of existing memories for dedup context

        Returns:
            ExtractionResult with parsed facts
        """
        import time as _time

        start = _time.monotonic()

        try:
            # Build prompt
            prompt = format_prompt(
                BENCHMARK_EXTRACTION_PROMPT,
                CONVERSATION=conversation_text,
            )

            # Call LLM
            raw_response = await self._llm.complete(
                system=prompt["system"],
                user=prompt["user"],
                temperature=self._temperature,
            )

            processing_ms = (_time.monotonic() - start) * 1000

            # Parse response
            facts, errors = self._parse_response(raw_response)

            # Filter by minimum importance
            facts = [f for f in facts if f.importance >= self._min_importance]

            return ExtractionResult(
                facts=facts,
                raw_response=raw_response,
                processing_time_ms=processing_ms,
                parse_errors=errors,
            )

        except Exception as llm_error:
            # Fallback to heuristic extraction when LLM is unavailable
            logger.warning(
                "LLM extraction failed, using heuristic fallback: %s",
                str(llm_error)[:200],
            )
            return self._heuristic_extract(conversation_text, _time.monotonic() - start)

    def _heuristic_extract(
        self, conversation_text: str, elapsed_s: float
    ) -> ExtractionResult:
        """
        Fallback heuristic extraction when the LLM is unavailable.

        Splits conversation into meaningful sentences and creates one fact
        per substantive sentence. This is NOT as good as LLM extraction
        but allows the full E2EE pipeline (encrypt -> store -> blind search
        -> decrypt -> rerank) to be exercised for benchmarking.
        """
        facts: List[ExtractedFact] = []
        lines = conversation_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line or len(line) < 30:
                continue

            # Skip system messages, timestamps-only, and greetings
            lower = line.lower()
            if any(
                skip in lower
                for skip in [
                    "joined the channel",
                    "left the channel",
                    "set the topic",
                    "pinned a message",
                    "this message was deleted",
                    "retention polic",
                ]
            ):
                continue

            # Remove sender prefix if present (e.g., "user_056: ")
            text = re.sub(r"^[\w_]+:\s*", "", line)
            if len(text) < 25:
                continue

            # Truncate very long lines
            text = text[:512]

            # Determine a basic importance score based on heuristics
            importance = 5
            if any(kw in lower for kw in ["important", "critical", "urgent", "deadline", "decision"]):
                importance = 8
            elif any(kw in lower for kw in ["prefer", "like", "love", "hate", "dislike"]):
                importance = 7
            elif any(kw in lower for kw in ["remember", "don't forget", "note that", "fyi"]):
                importance = 7
            elif any(kw in lower for kw in ["meeting", "call", "schedule", "plan"]):
                importance = 6
            elif len(text) < 40:
                importance = 4

            # Determine fact type
            fact_type = "fact"
            if any(kw in lower for kw in ["prefer", "like", "love", "hate", "favorite"]):
                fact_type = "preference"
            elif any(kw in lower for kw in ["decided", "decision", "chose", "picked"]):
                fact_type = "decision"
            elif any(kw in lower for kw in ["goal", "plan", "want to", "aim to"]):
                fact_type = "goal"

            if importance >= self._min_importance:
                facts.append(
                    ExtractedFact(
                        fact_text=text,
                        type=fact_type,
                        importance=importance,
                        confidence=0.6,
                        action="ADD",
                        entities=[],
                        relations=[],
                        reasoning="heuristic_extraction",
                    )
                )

        # Limit to top facts by importance (avoid overwhelming storage)
        facts.sort(key=lambda f: f.importance, reverse=True)
        facts = facts[:20]

        return ExtractionResult(
            facts=facts,
            raw_response="(heuristic extraction - LLM unavailable)",
            processing_time_ms=elapsed_s * 1000,
            parse_errors=["LLM unavailable, used heuristic fallback"],
        )

    async def extract_pre_compaction(
        self,
        conversation_turns: List[Dict[str, Any]],
        existing_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> ExtractionResult:
        """
        Pre-compaction extraction: comprehensive pass over last 20 turns.

        Args:
            conversation_turns: List of turn dicts with role/content/timestamp
            existing_memories: Existing memories for dedup

        Returns:
            ExtractionResult
        """
        import time as _time

        start = _time.monotonic()

        history_str = format_conversation_history(conversation_turns[-20:])
        memories_str = format_existing_memories(existing_memories or [])

        prompt = format_prompt(
            PRE_COMPACTION_PROMPT,
            CONVERSATION_HISTORY=history_str,
            EXISTING_MEMORIES=memories_str,
        )

        raw_response = await self._llm.complete(
            system=prompt["system"],
            user=prompt["user"],
            temperature=self._temperature,
        )

        processing_ms = (_time.monotonic() - start) * 1000
        facts, errors = self._parse_response(raw_response)
        facts = [f for f in facts if f.importance >= self._min_importance]

        return ExtractionResult(
            facts=facts,
            raw_response=raw_response,
            processing_time_ms=processing_ms,
            parse_errors=errors,
        )

    async def extract_post_turn(
        self,
        conversation_turns: List[Dict[str, Any]],
        existing_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> ExtractionResult:
        """
        Post-turn extraction: lightweight pass over last 3 turns.

        Only extracts high-importance items (>= 7).
        """
        import time as _time

        start = _time.monotonic()

        history_str = format_conversation_history(conversation_turns[-3:])
        memories_str = format_existing_memories(existing_memories or [])

        prompt = format_prompt(
            POST_TURN_PROMPT,
            CONVERSATION_HISTORY=history_str,
            EXISTING_MEMORIES=memories_str,
        )

        raw_response = await self._llm.complete(
            system=prompt["system"],
            user=prompt["user"],
            temperature=self._temperature,
        )

        processing_ms = (_time.monotonic() - start) * 1000
        facts, errors = self._parse_response(raw_response)
        # Post-turn is strict: only importance >= 7
        facts = [f for f in facts if f.importance >= max(7, self._min_importance)]

        return ExtractionResult(
            facts=facts,
            raw_response=raw_response,
            processing_time_ms=processing_ms,
            parse_errors=errors,
        )

    async def extract_explicit(
        self,
        user_request: str,
        conversation_context: str = "",
    ) -> ExtractionResult:
        """
        Explicit command extraction: user explicitly asked to remember something.
        """
        import time as _time

        start = _time.monotonic()

        prompt = format_prompt(
            EXPLICIT_COMMAND_PROMPT,
            USER_REQUEST=user_request,
            CONVERSATION_CONTEXT=conversation_context,
        )

        raw_response = await self._llm.complete(
            system=prompt["system"],
            user=prompt["user"],
            temperature=self._temperature,
        )

        processing_ms = (_time.monotonic() - start) * 1000
        facts, errors = self._parse_response(raw_response)

        # Boost importance for explicit requests
        for fact in facts:
            fact.importance = min(10, fact.importance + 1)

        return ExtractionResult(
            facts=facts,
            raw_response=raw_response,
            processing_time_ms=processing_ms,
            parse_errors=errors,
        )

    # ------------------------------------------------------------------
    # Response Parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self, raw_response: str
    ) -> tuple[List[ExtractedFact], List[str]]:
        """
        Parse the LLM's JSON response into ExtractedFact objects.

        Handles:
        - Direct JSON
        - JSON wrapped in markdown code blocks
        - Partial / malformed responses (best effort)

        Returns:
            Tuple of (list of facts, list of error messages)
        """
        errors: List[str] = []

        # Try to extract JSON from the response
        json_str = raw_response.strip()

        # Handle markdown code blocks: ```json ... ``` or ``` ... ```
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", json_str)
        if code_block_match:
            json_str = code_block_match.group(1).strip()

        # Attempt JSON parse
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Try to find a JSON object anywhere in the response
            obj_match = re.search(r"\{[\s\S]*\}", json_str)
            if obj_match:
                try:
                    parsed = json.loads(obj_match.group(0))
                except json.JSONDecodeError:
                    errors.append(f"Failed to parse LLM response as JSON: {e}")
                    return [], errors
            else:
                errors.append(f"No JSON object found in LLM response: {e}")
                return [], errors

        # Extract the facts array
        if not isinstance(parsed, dict):
            errors.append("Response is not a JSON object")
            return [], errors

        raw_facts = parsed.get("facts")
        if not isinstance(raw_facts, list):
            errors.append('Response does not contain a "facts" array')
            return [], errors

        # Parse individual facts
        facts: List[ExtractedFact] = []
        for i, raw_fact in enumerate(raw_facts):
            if not isinstance(raw_fact, dict):
                errors.append(f"facts[{i}] is not an object")
                continue

            fact = ExtractedFact.from_raw(raw_fact)
            if fact is not None:
                facts.append(fact)
            else:
                errors.append(f"facts[{i}] failed validation")

        return facts, errors
