"""
QMD-Style Hybrid Search Algorithm

Replicates QMD's sophisticated hybrid search with query expansion and RRF fusion.

Based on QMD's architecture from https://github.com/tobi/qmd

Algorithm:
1. Query Expansion: LLM generates 1 variant query
2. Parallel Retrieval: Original (×2 weight) + variant search both BM25 and vector
3. RRF Fusion: score = Σ(1/(k+rank+1)) where k=60
4. Top-Rank Bonus: #1 gets +0.05, #2-3 get +0.02
5. Top 30 candidates → LLM reranking
6. Position-Aware Blending:
   - Rank 1-3:  75% RRF / 25% reranker
   - Rank 4-10: 60% RRF / 40% reranker
   - Rank 11+:  40% RRF / 60% reranker

This is a simplified version for the testbed that omits actual LLM calls
but preserves the algorithmic structure.
"""

from typing import List, Tuple, Optional
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .bm25_only import simple_tokenize
from .rank_bm25_portable import BM25OkapiPortable


def _expand_query(query: str) -> List[str]:
    """
    Generate query variants for better recall.

    In production, this uses an LLM. For the testbed, we use rule-based
    expansion to generate variations without API calls.

    Variations generated:
    1. Synonym replacement (common technical terms)
    2. Abbreviation expansion
    3. Word reordering
    """
    variants = []

    # Common technical synonyms
    synonyms = {
        'api': ['interface', 'endpoint', 'service'],
        'database': ['db', 'storage', 'data store'],
        'authentication': ['auth', 'login', 'signin', 'verification'],
        'configuration': ['config', 'settings', 'setup'],
        'deployment': ['deploy', 'release', 'production'],
        'error': ['exception', 'failure', 'issue', 'bug'],
        'container': ['docker', 'pod', 'orchestration'],
    }

    # Generate synonym-based variant
    query_lower = query.lower()
    variant_words = []
    for word in query_lower.split():
        if word in synonyms:
            variant_words.extend(synonyms[word][:2])  # Add up to 2 synonyms
        else:
            variant_words.append(word)
    if variant_words != query_lower.split():
        variants.append(' '.join(variant_words))

    # Generate abbreviation expansion variant
    abbreviations = {
        'api': 'application programming interface',
        'db': 'database',
        'auth': 'authentication',
        'config': 'configuration',
        'ci/cd': 'continuous integration continuous deployment',
        'cors': 'cross origin resource sharing',
    }

    variant = query_lower
    for abbr, expansion in abbreviations.items():
        variant = variant.replace(abbr, expansion)
    if variant != query_lower:
        variants.append(variant)

    # If no variants generated, return original with slight modification
    if not variants:
        # Word reordering (swap first two words)
        words = query_lower.split()
        if len(words) > 1:
            words[0], words[1] = words[1], words[0]
            variants.append(' '.join(words))

    return variants


def _reciprocal_rank_fusion(
    results_list: List[List[Tuple[int, float]]],
    k: int = 60
) -> List[Tuple[int, float]]:
    """
    Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.

    RRF is robust to score scale differences and works well when combining
    results from different retrieval methods.

    Formula: score(doc) = Σ 1 / (k + rank(doc))

    Args:
        results_list: List of ranked result lists, each containing (doc_idx, score)
        k: RRF constant (default 60, as used in QMD)

    Returns:
        Merged and re-ranked results
    """
    rrf_scores = {}

    for results in results_list:
        for rank, (doc_idx, _) in enumerate(results):
            # RRF formula: 1 / (k + rank), using 0-indexed rank
            rrf_score = 1.0 / (k + rank + 1)
            rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0) + rrf_score

    # Sort by RRF score
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


def _apply_top_rank_bonus(results: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
    """
    Apply top-rank bonus as per QMD algorithm.
    #1 gets +0.05, #2-3 get +0.02
    """
    if not results:
        return results

    bonus_results = []
    for rank, (idx, score) in enumerate(results):
        bonus = 0.0
        if rank == 0:
            bonus = 0.05
        elif rank in [1, 2]:
            bonus = 0.02
        bonus_results.append((idx, score + bonus))

    return bonus_results


def _llm_rerank(
    query: str,
    documents: List[str],
    candidates: List[Tuple[int, float]],
    top_n: int = 30
) -> List[Tuple[int, float]]:
    """
    LLM-based reranking of top candidates.

    In production, this uses a local GGUF model (qwen3-reranker-0.6b-q8_0).
    For the testbed, we use a heuristic approximation based on:
    1. Exact query term matches
    2. Query term density
    3. Document length penalty (prefer concise answers)

    Args:
        query: Original search query
        documents: All document strings
        candidates: Candidate (doc_idx, score) tuples from RRF
        top_n: Number of candidates to rerank

    Returns:
        Reranked candidates with new scores
    """
    if not candidates:
        return []

    # Get top candidates
    top_candidates = candidates[:top_n]
    query_lower = query.lower()
    query_terms = set(simple_tokenize(query))

    reranked = []
    for doc_idx, rrf_score in top_candidates:
        doc = documents[doc_idx].lower()

        # Heuristic reranking score
        rerank_score = rrf_score

        # Boost for exact phrase match
        if query_lower in doc:
            rerank_score *= 1.5

        # Boost for query term density
        doc_tokens = simple_tokenize(doc)
        if doc_tokens:
            term_overlap = len(query_terms & set(doc_tokens))
            density = term_overlap / len(doc_tokens)
            rerank_score *= (1 + density)

        # Penalty for very long documents (prefer concise)
        if len(doc) > 1000:
            rerank_score *= 0.9
        elif len(doc) < 200:
            rerank_score *= 1.1

        reranked.append((doc_idx, rerank_score))

    # Re-sort by rerank score
    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked


def _position_aware_blending(
    rrf_results: List[Tuple[int, float]],
    rerank_results: List[Tuple[int, float]]
) -> List[Tuple[int, float]]:
    """
    Position-aware blending as per QMD algorithm.

    Blending ratios:
    - Rank 1-3:  75% RRF / 25% reranker
    - Rank 4-10: 60% RRF / 40% reranker
    - Rank 11+:  40% RRF / 60% reranker

    This prevents the reranker from destroying high-confidence retrieval results.
    """
    # Create score dictionaries
    rrf_scores = {idx: score for idx, score in rrf_results}
    rerank_scores = {idx: score for idx, score in rerank_results}

    # Get all unique document indices
    all_indices = set(rrf_scores.keys()) | set(rerank_scores.keys())

    blended = []
    for idx in all_indices:
        rrf_score = rrf_scores.get(idx, 0)
        rerank_score = rerank_scores.get(idx, 0)

        # Find rank in each result list
        rrf_rank = next((i for i, (doc_idx, _) in enumerate(rrf_results) if doc_idx == idx), float('inf'))
        rerank_rank = next((i for i, (doc_idx, _) in enumerate(rerank_results) if doc_idx == idx), float('inf'))

        # Determine blending ratio based on RRF rank
        if rrf_rank < 3:
            rrf_weight, rerank_weight = 0.75, 0.25
        elif rrf_rank < 10:
            rrf_weight, rerank_weight = 0.60, 0.40
        else:
            rrf_weight, rerank_weight = 0.40, 0.60

        # Normalize scores (assuming they're on similar scales)
        # Use min-max normalization if scores vary widely
        max_rrf = max([s for _, s in rrf_results]) if rrf_results else 1
        max_rerank = max([s for _, s in rerank_results]) if rerank_results else 1

        normalized_rrf = rrf_score / max_rrf if max_rrf > 0 else 0
        normalized_rerank = rerank_score / max_rerank if max_rerank > 0 else 0

        # Blend
        blended_score = rrf_weight * normalized_rrf + rerank_weight * normalized_rerank
        blended.append((idx, blended_score))

    # Sort by blended score
    blended.sort(key=lambda x: x[1], reverse=True)
    return blended


def qmd_hybrid_search(
    query: str,
    documents: List[str],
    embeddings: np.ndarray,
    top_k: int = 5,
    candidate_multiplier: int = 4,
    rrf_k: int = 60,
    use_query_expansion: bool = True,
    use_reranking: bool = True,
    model=None
) -> List[Tuple[int, float]]:
    """
    QMD-style hybrid search with query expansion and RRF fusion.

    This implements the sophisticated algorithm from QMD:
    1. Query expansion (generates variants)
    2. Parallel BM25 and vector search on original + variants
    3. RRF fusion with top-rank bonus
    4. LLM reranking (simulated)
    5. Position-aware blending

    Args:
        query: The search query string
        documents: List of document strings
        embeddings: Pre-computed document embeddings
        top_k: Number of results to return
        candidate_multiplier: Multiplier for candidate pool
        rrf_k: RRF constant (default 60 per QMD)
        use_query_expansion: Whether to use query expansion
        use_reranking: Whether to use LLM reranking
        model: Optional pre-loaded embedding model

    Returns:
        List of tuples (doc_index, score) sorted by final score

    Example:
        >>> docs = ["API configuration", "Database setup"]
        >>> embeddings = compute_embeddings(docs)
        >>> results = qmd_hybrid_search("configure API", docs, embeddings)
        >>> len(results)  # 5 results
    """
    if not documents or len(documents) == 0:
        return []

    if not query or not query.strip():
        return []

    if embeddings is None or len(embeddings) != len(documents):
        raise ValueError("Embeddings must match document count")

    # Load model if not provided
    if model is None:
        from .vector_only import _get_embedding_model
        model = _get_embedding_model()

    # ========== STEP 1: Query Expansion ==========
    query_variants = [query]
    if use_query_expansion:
        variants = _expand_query(query)
        query_variants.extend(variants)

    # ========== STEP 2: Parallel Retrieval ==========
    all_results = []

    for variant_query in query_variants:
        # Vector search for this variant
        query_embedding = model.encode([variant_query])[0]
        vector_similarities = cosine_similarity([query_embedding], embeddings)[0]

        # Get top vector results
        candidate_count = min(top_k * candidate_multiplier, len(documents))
        top_vector = [(i, vector_similarities[i])
                      for i in np.argsort(vector_similarities)[::-1][:candidate_count]
                      if vector_similarities[i] > 0]

        # BM25 search for this variant
        tokenized_corpus = [simple_tokenize(doc) for doc in documents]
        tokenized_query = simple_tokenize(variant_query)
        bm25 = BM25OkapiPortable(tokenized_corpus)
        bm25_scores = bm25.get_scores(tokenized_query)

        # Get top BM25 results
        top_bm25 = [(i, bm25_scores[i])
                    for i in np.argsort(-bm25_scores)[:candidate_count]
                    if bm25_scores[i] > 0]

        # Add to all results (original query gets 2x weight)
        weight = 2.0 if variant_query == query else 1.0
        all_results.append([(idx, score * weight) for idx, score in top_vector])
        all_results.append([(idx, score * weight) for idx, score in top_bm25])

    # ========== STEP 3: RRF Fusion ==========
    rrf_results = _reciprocal_rank_fusion(all_results, k=rrf_k)

    # ========== STEP 4: Top-Rank Bonus ==========
    rrf_results = _apply_top_rank_bonus(rrf_results)

    # ========== STEP 5: LLM Reranking ==========
    if use_reranking:
        rerank_candidates = min(30, len(rrf_results))
        rerank_results = _llm_rerank(query, documents, rrf_results, top_n=rerank_candidates)

        # ========== STEP 6: Position-Aware Blending ==========
        final_results = _position_aware_blending(rrf_results, rerank_results)
    else:
        final_results = rrf_results

    # Return top-k
    return final_results[:top_k]
