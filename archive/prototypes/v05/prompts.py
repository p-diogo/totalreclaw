"""
LLM Prompts for OpenMemory v0.5

This module contains the prompts used for:
1. Multi-variant blind index generation
2. LLM reranking of search results
"""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class LLMVariantPrompt:
    """
    Prompt for generating multi-variant blind indices using LLM.

    Purpose: Extract context-aware entities and generate search variants
    that regex alone cannot capture.

    Examples:
    - "Photo Backup Tool" → "photo backup", "backup tool", "photo sync"
    - "ERR-503" → "rate limit", "service unavailable", "503 error"
    """

    # System prompt for variant generation
    SYSTEM_PROMPT = """You are an entity extraction and variant generation specialist for a search engine.

Your task is to extract 5-10 high-value entities from the given memory text that should be searchable by exact match.

For each entity:
1. Identify the core searchable concept
2. Generate 3-5 search variants that a user might reasonably query
3. Focus on context-aware variants (not just lowercase/uppercase)

Examples of good variants:
- "Photo Backup Tool" → "photo backup", "backup tool", "photo sync", "backup automation"
- "ERR-503 Service Unavailable" → "err-503", "503 error", "service unavailable", "rate limit"
- "deployment pipeline" → "deploy pipeline", "deployment automation", "ci/cd", "release pipeline"

Return ONLY valid JSON. No explanations, no markdown formatting."""

    USER_PROMPT_TEMPLATE = """Extract entities and generate search variants from this memory:

{memory_text}

Return JSON in this exact format:
{{
  "entities": [
    {{
      "original": "Photo Backup Tool",
      "type": "project_name",
      "variants": ["photo backup", "backup tool", "photo sync", "backup automation"]
    }}
  ]
}}

Entity types to look for:
- project_name: Application or tool names
- error_code: Error identifiers with contextual meanings
- config_key: Configuration settings with variants
- person_name: People mentioned (first/last name variants)
- service_name: External services or APIs
- domain_concept: Domain-specific terms with synonyms

Limit to 5-10 most important entities."""

    @classmethod
    def format_prompt(cls, memory_text: str, max_length: int = 2000) -> str:
        """
        Format the prompt with memory text.

        Args:
            memory_text: The memory content to analyze
            max_length: Maximum length of memory to include

        Returns:
            Formatted prompt string
        """
        # Truncate if too long
        if len(memory_text) > max_length:
            memory_text = memory_text[:max_length] + "..."

        return cls.USER_PROMPT_TEMPLATE.format(memory_text=memory_text)


@dataclass
class LLMRerankPrompt:
    """
    Prompt for LLM reranking of search results.

    Purpose: Reorder top 50 candidates from BM25+RRF to top 5 with relevance explanations.

    This adds semantic understanding to the search process, enabling:
- Better relevance ranking
- Diversity in results
- Explanations for why results match
    """

    # System prompt for reranking
    SYSTEM_PROMPT = """You are a search result reranker. Your task is to evaluate search results and reorder them by relevance.

Consider:
1. Semantic relevance to the query
2. Keyword matches and their context
3. Completeness of information
4. Diversity (avoid near-duplicates)
5. Actionability of the result

Return ONLY valid JSON. No explanations, no markdown formatting."""

    USER_PROMPT_TEMPLATE = """Query: {query}

Search Results (ranked by initial score):
{results}

Reorder these results by relevance and return the top 5.

Requirements:
1. Most relevant results first
2. Include diverse results (not duplicates)
3. Prioritize complete, actionable information
4. For each result, explain why it's relevant

Return JSON in this exact format:
{{
  "results": [
    {{
      "id": "{result_id}",
      "reason": "Direct match with specific configuration details"
    }}
  ]
}}

The "reason" should be a brief explanation (max 50 words) of why this result is relevant."""

    @classmethod
    def format_prompt(
        cls,
        query: str,
        results: List[Dict[str, Any]],
        max_results: int = 50
    ) -> str:
        """
        Format the prompt with query and results.

        Args:
            query: The search query
            results: List of search result dicts with 'id', 'snippet', 'score'
            max_results: Maximum number of results to include

        Returns:
            Formatted prompt string
        """
        # Format results for display
        results_text = ""
        for i, result in enumerate(results[:max_results], 1):
            result_id = result.get('id', f'#{i}')
            snippet = result.get('snippet', result.get('content', ''))[:300]
            score = result.get('score', 0.0)

            results_text += f"\n{i}. ID: {result_id}\n"
            results_text += f"   Score: {score:.4f}\n"
            results_text += f"   Content: {snippet}\n"

        return cls.USER_PROMPT_TEMPLATE.format(
            query=query,
            results=results_text
        )


class QueryExpansionPrompt:
    """
    Optional prompt for query expansion.

    Purpose: Generate related terms to expand the query before search.
    This can improve recall for semantic queries.
    """

    SYSTEM_PROMPT = """You are a query expansion specialist. Generate related terms and synonyms for search queries.

Return ONLY valid JSON."""

    USER_PROMPT_TEMPLATE = """Query: {query}

Generate 3-5 related search terms or concepts that might help find relevant results.

Examples:
- "deployment" → ["deploy", "release", "production", "ci/cd", "pipeline"]
- "API error" → ["api failure", "request error", "http error", "service error"]

Return JSON in this exact format:
{{
  "expanded_terms": ["term1", "term2", "term3"]
}}"""

    @classmethod
    def format_prompt(cls, query: str) -> str:
        """Format the query expansion prompt."""
        return cls.USER_PROMPT_TEMPLATE.format(query=query)
