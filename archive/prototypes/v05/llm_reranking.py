"""
LLM Reranking for OpenMemory v0.5

Implements Pass 3 of the three-pass search:
- Reranks top 50 candidates from Pass 2
- Returns top 5 with relevance explanations
"""

import json
import re
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

from .prompts import LLMRerankPrompt


@dataclass
class RerankedResult:
    """A reranked search result."""
    id: str
    content: str
    score: float
    explanation: str
    rank: int


class LLMReranker:
    """
    LLM-based reranking for search results.

    This implements Pass 3 of the three-pass search:
    - Pass 1: Remote vector search (server)
    - Pass 2: Local BM25 + RRF (client)
    - Pass 3: LLM reranking (client, this module)

    Zero-Knowledge Properties:
    - LLM operates locally on decrypted candidates
    - Uses the same LLM the agent already has
    - No additional infrastructure required
    """

    def __init__(self, llm_client, max_candidates: int = 50, top_k: int = 5):
        """
        Initialize LLM reranker.

        Args:
            llm_client: Client for the agent's LLM
            max_candidates: Maximum candidates to consider for reranking
            top_k: Number of results to return after reranking
        """
        self.llm_client = llm_client
        self.max_candidates = max_candidates
        self.top_k = top_k

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        use_llm: bool = True
    ) -> List[RerankedResult]:
        """
        Rerank candidates using LLM.

        Args:
            query: The original search query
            candidates: List of candidate results from Pass 2
            use_llm: Whether to use LLM (False for fallback)

        Returns:
            List of RerankedResult objects (top_k results)
        """
        if not candidates:
            return []

        # Limit candidates
        candidates = candidates[:self.max_candidates]

        if use_llm:
            return self._llm_rerank(query, candidates)
        else:
            return self._fallback_rerank(query, candidates)

    def _llm_rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[RerankedResult]:
        """
        Rerank using LLM.

        Args:
            query: Search query
            candidates: Candidate results

        Returns:
            Reranked top-k results
        """
        # Format prompt
        prompt = LLMRerankPrompt.format_prompt(query, candidates, self.max_candidates)

        # Call LLM
        response = self._call_llm(prompt)

        # Parse response
        reranked_ids = self._parse_rerank_response(response)

        # Build results with explanations
        results = []
        seen_ids = set()

        for rank, item in enumerate(reranked_ids[:self.top_k], 1):
            result_id = item.get('id')

            if result_id in seen_ids:
                continue
            seen_ids.add(result_id)

            # Find the candidate
            candidate = next((c for c in candidates if c.get('id') == result_id), None)

            if candidate:
                results.append(RerankedResult(
                    id=result_id,
                    content=candidate.get('snippet', candidate.get('content', '')),
                    score=candidate.get('score', 0.0),
                    explanation=item.get('reason', 'Relevant match'),
                    rank=rank
                ))

        # Fill remaining slots with original top results
        if len(results) < self.top_k:
            for candidate in candidates:
                if candidate.get('id') not in seen_ids:
                    results.append(RerankedResult(
                        id=candidate.get('id', ''),
                        content=candidate.get('snippet', candidate.get('content', '')),
                        score=candidate.get('score', 0.0),
                        explanation='High-scoring result',
                        rank=len(results) + 1
                    ))

                    if len(results) >= self.top_k:
                        break

        return results

    def _fallback_rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[RerankedResult]:
        """
        Fallback reranking without LLM (uses original scores).

        Args:
            query: Search query (not used in fallback)
            candidates: Candidate results

        Returns:
            Top-k results by original score
        """
        results = []

        for rank, candidate in enumerate(candidates[:self.top_k], 1):
            # Generate simple explanation
            explanation = self._generate_fallback_explanation(
                query,
                candidate.get('content', candidate.get('snippet', ''))
            )

            results.append(RerankedResult(
                id=candidate.get('id', ''),
                content=candidate.get('snippet', candidate.get('content', '')),
                score=candidate.get('score', 0.0),
                explanation=explanation,
                rank=rank
            ))

        return results

    def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM with the prompt.

        Args:
            prompt: The formatted prompt

        Returns:
            LLM response text
        """
        if hasattr(self.llm_client, 'complete'):
            return self.llm_client.complete(prompt)
        elif hasattr(self.llm_client, 'generate'):
            return self.llm_client.generate(prompt)
        elif callable(self.llm_client):
            return self.llm_client(prompt)
        else:
            raise ValueError(
                "LLM client must have 'complete', 'generate' method, or be callable"
            )

    def _parse_rerank_response(self, response: str) -> List[Dict[str, str]]:
        """
        Parse LLM reranking response.

        Args:
            response: LLM response text

        Returns:
            List of dicts with 'id' and 'reason'
        """
        results = []

        try:
            # Try to parse as JSON
            data = json.loads(response)

            for item in data.get('results', []):
                results.append({
                    'id': item.get('id', ''),
                    'reason': item.get('reason', '')
                })

        except json.JSONDecodeError:
            # Fallback: extract IDs and reasons from text
            # Look for patterns like "ID: xxx" or quoted IDs
            id_matches = re.findall(r'ID[:\s]+([^\s,}]+)', response, re.IGNORECASE)
            quote_matches = re.findall(r'"([^"]+)"', response)

            for i, match in enumerate(id_matches[:5]):
                results.append({'id': match, 'reason': f'Result {i + 1}'})

        return results

    def _generate_fallback_explanation(self, query: str, content: str) -> str:
        """
        Generate a simple explanation for fallback mode.

        Args:
            query: Search query
            content: Result content

        Returns:
            Explanation string
        """
        query_lower = query.lower()
        content_lower = content.lower()

        # Check for exact matches
        if query_lower in content_lower:
            return f"Contains query term '{query}'"

        # Check for word matches
        query_words = set(query_lower.split())
        content_words = set(content_lower.split())

        matches = query_words & content_words

        if matches:
            return f"Contains related terms: {', '.join(list(matches)[:3])}"

        return "Semantically similar result"


class HybridReranker:
    """
    Hybrid reranker that combines LLM with traditional signals.

    Uses LLM for top results, falls back to BM25 scores for remaining.
    """

    def __init__(
        self,
        llm_client,
        llm_top_k: int = 3,
        total_top_k: int = 5
    ):
        """
        Initialize hybrid reranker.

        Args:
            llm_client: LLM client
            llm_top_k: Number of results to rerank with LLM
            total_top_k: Total results to return
        """
        self.llm_client = llm_client
        self.llm_top_k = llm_top_k
        self.total_top_k = total_top_k

        self.llm_reranker = LLMReranker(
            llm_client,
            max_candidates=50,
            top_k=llm_top_k
        )

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]]
    ) -> List[RerankedResult]:
        """
        Hybrid reranking: LLM for top results, BM25 for rest.

        Args:
            query: Search query
            candidates: Candidate results

        Returns:
            Reranked results
        """
        if not candidates:
            return []

        # LLM rerank top results
        llm_results = self.llm_reranker._llm_rerank(
            query,
            candidates[:50]
        )

        # Fill remaining slots with original BM25 scores
        results = list(llm_results)
        seen_ids = {r.id for r in results}

        for candidate in candidates:
            if candidate.get('id') not in seen_ids:
                results.append(RerankedResult(
                    id=candidate.get('id', ''),
                    content=candidate.get('snippet', candidate.get('content', '')),
                    score=candidate.get('score', 0.0),
                    explanation='High BM25 score',
                    rank=len(results) + 1
                ))

                seen_ids.add(candidate.get('id', ''))

                if len(results) >= self.total_top_k:
                    break

        return results[:self.total_top_k]
