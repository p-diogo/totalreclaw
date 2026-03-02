"""
Search Implementation for OpenMemory v0.6

Implements the full search flow with:
1. Query expansion (optional LLM-based)
2. Full corpus BM25 search
3. Vector KNN search (encrypted embeddings)
4. RRF fusion for final ranking

Based on the v0.6 specification.
"""

import time
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .bm25_index import BM25Index
from .query_expansion import expand_query, ExpandedQuery


@dataclass
class SearchTiming:
    """
    Timing breakdown for v0.6 search.

    Attributes:
        expansion_ms: Time for query expansion
        bm25_ms: Time for BM25 search
        vector_ms: Time for vector KNN search
        decrypt_ms: Time to decrypt candidates
        fusion_ms: Time for RRF fusion
        total_ms: Total search time
    """

    expansion_ms: float = 0.0
    bm25_ms: float = 0.0
    vector_ms: float = 0.0
    decrypt_ms: float = 0.0
    fusion_ms: float = 0.0
    total_ms: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for logging."""
        return {
            "expansion_ms": self.expansion_ms,
            "bm25_ms": self.bm25_ms,
            "vector_ms": self.vector_ms,
            "decrypt_ms": self.decrypt_ms,
            "fusion_ms": self.fusion_ms,
            "total_ms": self.total_ms,
        }


@dataclass
class SearchResult:
    """
    Single search result.

    Attributes:
        doc_id: Document identifier
        score: Final fused score
        bm25_score: BM25 component score
        vector_score: Vector component score
        content: Decrypted document content
    """

    doc_id: int
    score: float
    bm25_score: float = 0.0
    vector_score: float = 0.0
    content: str = ""


def search_v06(
    query: str,
    bm25_index: BM25Index,
    embeddings: np.ndarray,
    documents: List[str],
    top_k: int = 5,
    expand_query: bool = True,
    expansion_model: str = "none",
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
    rrf_k: int = 60,
    encryption_key: Optional[bytes] = None,
    encrypted_documents: Optional[List[Any]] = None,
) -> Tuple[List[Tuple[int, float]], SearchTiming]:
    """
    OpenMemory v0.6 search with full corpus BM25 + optional query expansion.

    This implements the v0.6 search flow:
    1. (Optional) Expand query with LLM
    2. BM25 search on full corpus
    3. Vector KNN search on embeddings
    4. RRF fusion of results

    Args:
        query: Search query string
        bm25_index: Pre-built BM25 index
        embeddings: Document embeddings (numpy array)
        documents: Plaintext documents (for final results)
        top_k: Number of results to return
        expand_query: Whether to use LLM query expansion
        expansion_model: Model for expansion ("local", "ollama", "none")
        bm25_weight: Weight for BM25 scores in fusion (0-1)
        vector_weight: Weight for vector scores in fusion (0-1)
        rrf_k: RRF constant (default 60)
        encryption_key: Key for decrypting documents (if using encrypted storage)
        encrypted_documents: Encrypted document storage (if applicable)

    Returns:
        Tuple of (results, timing) where:
        - results: List of (doc_id, score) tuples
        - timing: SearchTiming breakdown
    """
    timing = SearchTiming()
    start_time = time.perf_counter()

    if not query or not query.strip():
        return [], timing

    # ===== Step 1: Query Expansion (Optional) =====
    expansion_start = time.perf_counter()

    queries_to_search = [query]

    if expand_query and expansion_model != "none":
        expanded = expand_query(query, model=expansion_model, timeout_ms=500)
        queries_to_search = expanded.expanded_queries[:4]  # Limit to 4 queries
        timing.expansion_ms = (time.perf_counter() - expansion_start) * 1000
    else:
        timing.expansion_ms = 0.0

    # ===== Step 2: BM25 Search (Full Corpus) =====
    bm25_start = time.perf_counter()

    bm25_results = {}  # doc_id -> max score across all query variations

    for q in queries_to_search:
        results = bm25_index.search(q, top_k=len(documents))
        for doc_id, score in results:
            # Take max score across query variations
            if doc_id not in bm25_results or score > bm25_results[doc_id]:
                bm25_results[doc_id] = score

    timing.bm25_ms = (time.perf_counter() - bm25_start) * 1000

    # ===== Step 3: Vector KNN Search =====
    vector_start = time.perf_counter()

    # For stub: use cosine similarity directly
    # In production, this would be server-side HNSW on encrypted embeddings
    vector_results = {}

    if len(embeddings) > 0:
        # Simple embedding generation for query (placeholder)
        # In production, use actual embedding model
        query_embedding = _get_query_embedding(query, embeddings.shape[1])

        similarities = cosine_similarity([query_embedding], embeddings)[0]

        # Get top 250 candidates (like v0.2 pass 1)
        limit = min(250, len(similarities))
        top_indices = np.argsort(similarities)[::-1][:limit]

        for idx in top_indices:
            if similarities[idx] > 0:
                vector_results[int(idx)] = float(similarities[idx])

    timing.vector_ms = (time.perf_counter() - vector_start) * 1000

    # ===== Step 4: RRF Fusion =====
    fusion_start = time.perf_counter()

    final_results = _rrf_fusion(
        bm25_results,
        vector_results,
        bm25_weight,
        vector_weight,
        rrf_k
    )

    timing.fusion_ms = (time.perf_counter() - fusion_start) * 1000

    # ===== Step 5: Return Top-K =====
    top_results = final_results[:top_k]

    timing.total_ms = (time.perf_counter() - start_time) * 1000

    return top_results, timing


def _get_query_embedding(query: str, embedding_dim: int) -> np.ndarray:
    """
    Generate a query embedding.

    This is a stub that returns a random vector.
    In production, this would use the actual embedding model.

    Args:
        query: Query string
        embedding_dim: Dimension of embeddings

    Returns:
        Query embedding vector
    """
    # Stub: return random vector
    # In production, use: model.encode([query])[0]
    np.random.seed(hash(query) % 2**32)
    return np.random.rand(embedding_dim)


def _rrf_fusion(
    bm25_results: Dict[int, float],
    vector_results: Dict[int, float],
    bm25_weight: float,
    vector_weight: float,
    k: int
) -> List[Tuple[int, float]]:
    """
    Reciprocal Rank Fusion (RRF) of BM25 and vector results.

    RRF formula: score = bm25_weight / (k + rank_bm25) + vector_weight / (k + rank_vector)

    Args:
        bm25_results: Dict of doc_id -> BM25 score
        vector_results: Dict of doc_id -> vector score
        bm25_weight: Weight for BM25 component
        vector_weight: Weight for vector component
        k: RRF constant

    Returns:
        List of (doc_id, fused_score) sorted by score descending
    """
    # Convert scores to ranks
    bm25_ranked = sorted(bm25_results.items(), key=lambda x: x[1], reverse=True)
    vector_ranked = sorted(vector_results.items(), key=lambda x: x[1], reverse=True)

    bm25_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(bm25_ranked)}
    vector_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(vector_ranked)}

    # Calculate RRF scores
    fused_scores = {}

    all_doc_ids = set(bm25_results.keys()) | set(vector_results.keys())

    for doc_id in all_doc_ids:
        score = 0.0

        bm25_rank = bm25_ranks.get(doc_id)
        vector_rank = vector_ranks.get(doc_id)

        if bm25_rank is not None:
            score += bm25_weight / (k + bm25_rank + 1)

        if vector_rank is not None:
            score += vector_weight / (k + vector_rank + 1)

        if score > 0:
            fused_scores[doc_id] = score

    # Sort by fused score
    sorted_results = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)

    return sorted_results


def hybrid_search_v06(
    query: str,
    documents: List[str],
    embeddings: np.ndarray,
    top_k: int = 5,
    expand_query: bool = True,
) -> Tuple[List[Tuple[int, float]], SearchTiming]:
    """
    Convenience function that builds BM25 index and searches.

    This is a simpler interface for evaluation that:
    1. Builds a BM25 index from documents
    2. Runs v0.6 search

    Args:
        query: Search query
        documents: List of document strings
        embeddings: Pre-computed document embeddings
        top_k: Number of results
        expand_query: Whether to expand query

    Returns:
        (results, timing) tuple
    """
    # Build BM25 index
    bm25_index = BM25Index()
    for doc_id, doc in enumerate(documents):
        bm25_index.add_document(doc_id, doc)

    # Run search
    return search_v06(
        query=query,
        bm25_index=bm25_index,
        embeddings=embeddings,
        documents=documents,
        top_k=top_k,
        expand_query=expand_query,
    )
