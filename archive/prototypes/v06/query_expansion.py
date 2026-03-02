"""
Query Expansion for OpenMemory v0.6

Implements LLM-based query expansion to improve search recall.
Generates semantically related terms and alternative phrasings.

Based on the v0.6 specification:
- Local LLM execution (llama3.2:3b or similar)
- 500ms timeout with fallback to no expansion
- Generates 2-4 related terms per query
"""

import json
import re
import subprocess
import time
from typing import List, Optional, Literal
from dataclasses import dataclass


@dataclass
class ExpandedQuery:
    """
    Result of query expansion.

    Attributes:
        original: Original user query
        expanded_terms: List of semantically related terms
        expanded_queries: Full query variations combining original + terms
        confidence: Confidence score (0-1) from LLM
        expansion_time_ms: Time taken for expansion
    """

    original: str
    expanded_terms: List[str]
    expanded_queries: List[str]
    confidence: float = 0.0
    expansion_time_ms: float = 0.0


# Default expansion prompt from spec
_DEFAULT_EXPANSION_PROMPT = """You are a query expansion assistant for a memory search system.

Given a user's search query, generate 2-4 semantically related search terms
that might help find relevant memories. Focus on:
- Synonyms
- Related concepts
- Alternative phrasings
- Technical terms if applicable

Query: "{user_query}"

Return ONLY a JSON array of terms, nothing else.
Example: ["term1", "term2", "term3"]"""


# Model configuration
ModelType = Literal["local", "ollama", "openai", "none"]


def expand_query(
    query: str,
    model: str = "local",
    model_name: Optional[str] = None,
    timeout_ms: int = 500,
    max_expansions: int = 3,
    prompt_template: Optional[str] = None,
    api_key: Optional[str] = None,
) -> ExpandedQuery:
    """
    Expand a query with semantically related terms using an LLM.

    Args:
        query: Original search query
        model: Model type - "local" (ollama), "ollama", "openai", or "none"
        model_name: Model name (e.g., "llama3.2:3b", "gpt-3.5-turbo")
        timeout_ms: Maximum time to wait for expansion (ms)
        max_expansions: Maximum number of expanded terms to return
        prompt_template: Custom prompt template (use {user_query} placeholder)
        api_key: API key for remote models

    Returns:
        ExpandedQuery with original and expanded terms
    """
    start_time = time.perf_counter()

    if not query or not query.strip():
        return ExpandedQuery(
            original=query,
            expanded_terms=[],
            expanded_queries=[],
            confidence=0.0,
            expansion_time_ms=0.0,
        )

    if model == "none":
        # Skip expansion
        return ExpandedQuery(
            original=query,
            expanded_terms=[],
            expanded_queries=[query],
            confidence=1.0,
            expansion_time_ms=0.0,
        )

    # Default model names
    if model_name is None:
        model_name = "llama3.2:3b" if model in ("local", "ollama") else "gpt-3.5-turbo"

    # Prepare prompt
    prompt = prompt_template or _DEFAULT_EXPANSION_PROMPT
    full_prompt = prompt.format(user_query=query)

    # Try expansion with timeout
    expanded_terms = []
    confidence = 0.0

    try:
        if model in ("local", "ollama"):
            expanded_terms = _expand_with_ollama(full_prompt, model_name, timeout_ms)
        elif model == "openai":
            expanded_terms = _expand_with_openai(full_prompt, model_name, api_key, timeout_ms)
        else:
            expanded_terms = []

        if expanded_terms:
            confidence = 0.8  # Default confidence when LLM responds
        else:
            confidence = 0.0

    except Exception as e:
        # Fallback to no expansion on error
        confidence = 0.0

    # Limit to max_expansions
    expanded_terms = expanded_terms[:max_expansions]

    # Generate expanded queries
    expanded_queries = [query]  # Always include original
    for term in expanded_terms:
        # Combine with original for broader search
        expanded_queries.append(f"{query} {term}")
        # Also include standalone term
        expanded_queries.append(term)

    expansion_time = (time.perf_counter() - start_time) * 1000

    return ExpandedQuery(
        original=query,
        expanded_terms=expanded_terms,
        expanded_queries=expanded_queries,
        confidence=confidence,
        expansion_time_ms=expansion_time,
    )


def _expand_with_ollama(prompt: str, model: str, timeout_ms: int) -> List[str]:
    """
    Expand query using local Ollama model.

    Args:
        prompt: Expansion prompt
        model: Model name
        timeout_ms: Timeout in milliseconds

    Returns:
        List of expanded terms
    """
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )

        response = result.stdout.strip()

        # Parse JSON response
        terms = _parse_json_response(response)
        return terms

    except subprocess.TimeoutExpired:
        # Timeout - return empty
        return []
    except FileNotFoundError:
        # Ollama not installed
        return []
    except Exception:
        return []


def _expand_with_openai(
    prompt: str,
    model: str,
    api_key: Optional[str],
    timeout_ms: int
) -> List[str]:
    """
    Expand query using OpenAI API.

    Args:
        prompt: Expansion prompt
        model: Model name
        api_key: OpenAI API key
        timeout_ms: Timeout in milliseconds

    Returns:
        List of expanded terms
    """
    if not api_key:
        return []

    try:
        import requests

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.3,
            },
            timeout=timeout_ms / 1000,
        )

        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return _parse_json_response(content)

        return []

    except Exception:
        return []


def _parse_json_response(response: str) -> List[str]:
    """
    Parse JSON array from LLM response.

    Handles various response formats:
    - Pure JSON array: ["term1", "term2"]
    - Markdown code block: ```json\n["term1"]\n```
    - Text with embedded JSON: Here are terms: ["term1"]

    Args:
        response: Raw LLM response text

    Returns:
        List of extracted terms
    """
    # Try to extract JSON array
    # First, look for code blocks
    code_block_match = re.search(r'```(?:json)?\s*\n?\s*\[(.*?)\]\s*```', response, re.DOTALL)
    if code_block_match:
        json_str = '[' + code_block_match.group(1) + ']'
    else:
        # Look for any array in the response
        array_match = re.search(r'\[(.*?)\]', response, re.DOTALL)
        if array_match:
            json_str = '[' + array_match.group(1) + ']'
        else:
            # Try parsing the whole response
            json_str = response.strip()

    try:
        terms = json.loads(json_str)
        if isinstance(terms, list):
            # Filter to strings only
            return [str(t).strip() for t in terms if t]
        return []
    except json.JSONDecodeError:
        return []


def expand_query_batch(
    queries: List[str],
    model: str = "local",
    model_name: Optional[str] = None,
    timeout_ms: int = 500,
    max_expansions: int = 3,
) -> List[ExpandedQuery]:
    """
    Expand multiple queries in batch.

    Args:
        queries: List of queries to expand
        model: Model type
        model_name: Model name
        timeout_ms: Timeout per query
        max_expansions: Maximum expansions per query

    Returns:
        List of ExpandedQuery results
    """
    return [
        expand_query(q, model, model_name, timeout_ms, max_expansions)
        for q in queries
    ]
