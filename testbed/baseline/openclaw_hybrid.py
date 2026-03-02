"""
OpenClaw Hybrid Search Algorithm

Replicates OpenClaw's official hybrid search algorithm as documented in:
https://docs.openclaw.ai/concepts/memory

Algorithm:
1. Vector search: top (maxResults × candidateMultiplier) by cosine similarity
2. BM25 search: top (maxResults × candidateMultiplier) by FTS5 BM25 rank
3. Convert BM25 rank to score: textScore = 1 / (1 + max(0, bm25Rank))
4. Merge: finalScore = vectorWeight × vectorScore + textWeight × textScore
5. Return top-k results by finalScore

Defaults from OpenClaw docs:
- vectorWeight = 0.7
- textWeight = 0.3
- candidateMultiplier = 4
"""

from typing import List, Tuple
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .bm25_only import simple_tokenize
from .rank_bm25_portable import BM25OkapiPortable


def openclaw_hybrid_search(
    query: str,
    documents: List[str],
    embeddings: np.ndarray,
    top_k: int = 5,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
    candidate_multiplier: int = 4,
    model=None
) -> List[Tuple[int, float]]:
    """
    OpenClaw-style hybrid search with weighted score merging.

    This replicates the default search algorithm used by OpenClaw's memory system.
    It combines semantic (vector) and keyword (BM25) search using weighted scores.

    Args:
        query: The search query string
        documents: List of document strings to search
        embeddings: Pre-computed document embeddings (n_docs, dim)
        top_k: Number of top results to return
        vector_weight: Weight for vector similarity score (default: 0.7)
        text_weight: Weight for text (BM25) score (default: 0.3)
        candidate_multiplier: Multiplier for candidate pool size (default: 4)
        model: Optional pre-loaded embedding model

    Returns:
        List of tuples (doc_index, score) sorted by final score descending

    Example:
        >>> docs = ["API key configuration", "Database setup guide"]
        >>> embeddings = compute_embeddings(docs)
        >>> results = openclaw_hybrid_search("configure API", docs, embeddings)
        >>> len(results)  # 5 results (or less if not enough docs)
    """
    if not documents or len(documents) == 0:
        return []

    if not query or not query.strip():
        return []

    if embeddings is None or len(embeddings) != len(documents):
        raise ValueError("Embeddings must be provided and match document count")

    n_docs = len(documents)
    candidate_count = min(top_k * candidate_multiplier, n_docs)

    # ============ PASS 1: Vector Search ============
    # Load model if not provided
    if model is None:
        from .vector_only import _get_embedding_model
        model = _get_embedding_model()

    # Encode query
    query_embedding = model.encode([query])[0]

    # Calculate cosine similarity
    vector_similarities = cosine_similarity([query_embedding], embeddings)[0]

    # Get top vector candidates
    top_vector_indices = np.argsort(vector_similarities)[::-1][:candidate_count]

    # ============ PASS 2: BM25 Search ============
    # Tokenize corpus and query
    tokenized_corpus = [simple_tokenize(doc) for doc in documents]
    tokenized_query = simple_tokenize(query)

    # Initialize BM25 and get scores
    bm25 = BM25OkapiPortable(tokenized_corpus)
    bm25_scores = bm25.get_scores(tokenized_query)

    # Get top BM25 candidates
    # We use argsort on negative scores to get descending order
    top_bm25_indices = np.argsort(-bm25_scores)[:candidate_count]

    # Convert BM25 rank to score using OpenClaw's formula
    # textScore = 1 / (1 + max(0, bm25Rank))
    # Higher BM25 score = better rank = lower rank number = higher textScore
    bm25_normalized = np.zeros(n_docs)
    for rank, idx in enumerate(top_bm25_indices):
        if bm25_scores[idx] > 0:  # Only rank documents with positive BM25 scores
            bm25_normalized[idx] = 1.0 / (1.0 + rank)

    # ============ PASS 3: Merge Results ============
    # Union of candidates from both searches
    candidate_set = set(top_vector_indices) | set(top_bm25_indices)

    # Calculate final scores
    results = []
    for idx in candidate_set:
        vector_score = vector_similarities[idx]
        text_score = bm25_normalized[idx]

        # Weighted merge (OpenClaw's formula)
        final_score = vector_weight * vector_score + text_weight * text_score

        # Only include results with positive score
        if final_score > 0:
            results.append((int(idx), float(final_score)))

    # Sort by final score descending and return top-k
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def openclaw_hybrid_search_with_decay(
    query: str,
    documents: List[str],
    embeddings: np.ndarray,
    document_timestamps: List[int],
    top_k: int = 5,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
    candidate_multiplier: int = 4,
    temporal_decay_half_life: int = 30,  # days
    current_timestamp: int = None,
    model=None
) -> List[Tuple[int, float]]:
    """
    OpenClaw hybrid search with temporal decay (optional feature).

    This adds OpenClaw's optional temporal decay feature, which boosts recent
    memories. The decay follows an exponential curve with configurable half-life.

    Args:
        query: The search query string
        documents: List of document strings
        embeddings: Pre-computed document embeddings
        document_timestamps: Unix timestamps for each document
        top_k: Number of results to return
        vector_weight: Weight for vector score
        text_weight: Weight for BM25 score
        candidate_multiplier: Multiplier for candidate pool
        temporal_decay_half_life: Half-life in days for decay (default: 30)
        current_timestamp: Current time (defaults to max of document timestamps)
        model: Optional pre-loaded embedding model

    Returns:
        List of tuples (doc_index, score) sorted by final score descending
    """
    import time

    # Get base hybrid search results
    results = openclaw_hybrid_search(
        query=query,
        documents=documents,
        embeddings=embeddings,
        top_k=top_k * candidate_multiplier,  # Get more candidates
        vector_weight=vector_weight,
        text_weight=text_weight,
        candidate_multiplier=candidate_multiplier,
        model=model
    )

    if not results:
        return []

    # Apply temporal decay
    if current_timestamp is None:
        current_timestamp = max(document_timestamps)

    decayed_results = []
    for idx, base_score in results:
        doc_timestamp = document_timestamps[idx]
        age_days = (current_timestamp - doc_timestamp) / (24 * 3600)

        # Exponential decay: score * (0.5)^(age / half_life)
        decay_factor = 0.5 ** (age_days / temporal_decay_half_life)
        decayed_score = base_score * decay_factor

        decayed_results.append((idx, decayed_score))

    # Re-sort by decayed score
    decayed_results.sort(key=lambda x: x[1], reverse=True)
    return decayed_results[:top_k]
