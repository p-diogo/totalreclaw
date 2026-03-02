"""
Rank-based metrics for evaluating search result ordering.

Includes Mean Reciprocal Rank (MRR), DCG, and NDCG.
"""

from typing import List, Set, Dict, Any
import numpy as np
import math


def calculate_reciprocal_rank(
    ranked_results: List[Any],
    relevant: Set[Any] | List[Any]
) -> float:
    """
    Calculate reciprocal rank: 1/rank of first relevant result.

    Args:
        ranked_results: List of document IDs in ranked order
        relevant: Set or list of relevant document IDs

    Returns:
        Reciprocal rank (0 if no relevant document found)

    Example:
        >>> ranked = [2, 5, 1, 7, 3, 9, 4]  # Relevant: 1, 3, 7
        >>> relevant = {1, 3, 7}
        >>> calculate_reciprocal_rank(ranked, relevant)
        0.5  # First relevant (7) is at rank 1 (0-indexed), so 1/2
    """
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    for rank, doc_id in enumerate(ranked_results, start=1):
        if doc_id in relevant_set:
            return 1.0 / rank

    return 0.0


def calculate_mrr(
    all_ranked_results: List[List[Any]],
    all_relevant: List[Set[Any] | List[Any]]
) -> float:
    """
    Calculate Mean Reciprocal Rank (MRR): average of reciprocal ranks
    across multiple queries.

    MRR = (1 / |Q|) * Σ (1 / rank_i)

    where rank_i is the rank of the first relevant document for query i.

    Args:
        all_ranked_results: List of ranked result lists, one per query
        all_relevant: List of relevant document sets, one per query

    Returns:
        Mean Reciprocal Rank between 0 and 1

    Example:
        >>> ranked_results = [[2, 1, 3], [5, 7, 2], [1, 3, 9]]
        >>> relevant_sets = [{1, 3}, {7}, {3, 9}]
        >>> calculate_mrr(ranked_results, relevant_sets)
        0.61
    """
    if len(all_ranked_results) != len(all_relevant):
        raise ValueError("Number of result lists must match number of relevant sets")

    if len(all_ranked_results) == 0:
        return 0.0

    reciprocal_ranks = []
    for ranked_results, relevant in zip(all_ranked_results, all_relevant):
        rr = calculate_reciprocal_rank(ranked_results, relevant)
        reciprocal_ranks.append(rr)

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def calculate_dcg(
    ranked_results: List[Any],
    relevance_scores: Dict[Any, float],
    k: int = None
) -> float:
    """
    Calculate Discounted Cumulative Gain (DCG).

    DCG = rel_1 + Σ(rel_i / log_2(i)) for i = 2 to k

    Args:
        ranked_results: List of document IDs in ranked order
        relevance_scores: Dictionary mapping doc_id to relevance score
        k: Number of results to consider (None = all)

    Returns:
        DCG score

    Example:
        >>> ranked = [1, 2, 3, 4, 5]
        >>> relevance = {1: 3, 2: 2, 3: 3, 4: 0, 5: 1}
        >>> calculate_dcg(ranked, relevance, k=5)
        7.17
    """
    if k is None:
        k = len(ranked_results)
    else:
        k = min(k, len(ranked_results))

    dcg = 0.0
    for i, doc_id in enumerate(ranked_results[:k], start=1):
        rel = relevance_scores.get(doc_id, 0.0)
        if i == 1:
            dcg += rel
        else:
            dcg += rel / math.log2(i)

    return dcg


def calculate_ndcg(
    ranked_results: List[Any],
    relevance_scores: Dict[Any, float],
    k: int = None
) -> float:
    """
    Calculate Normalized Discounted Cumulative Gain (NDCG).

    NDCG = DCG / IDCG

    where IDCG is the DCG of the ideal ranking (sorted by relevance).

    Args:
        ranked_results: List of document IDs in ranked order
        relevance_scores: Dictionary mapping doc_id to relevance score
        k: Number of results to consider (None = all)

    Returns:
        NDCG score between 0 and 1

    Example:
        >>> ranked = [1, 2, 3, 4, 5]
        >>> relevance = {1: 3, 2: 2, 3: 3, 4: 0, 5: 1}
        >>> calculate_ndcg(ranked, relevance, k=5)
        0.93
    """
    if k is None:
        k = len(ranked_results)

    dcg = calculate_dcg(ranked_results, relevance_scores, k)

    # Calculate ideal DCG
    ideal_ranking = sorted(
        relevance_scores.keys(),
        key=lambda x: relevance_scores[x],
        reverse=True
    )
    idcg = calculate_dcg(ideal_ranking, relevance_scores, k)

    if idcg == 0:
        return 0.0

    return dcg / idcg


def calculate_mean_ndcg(
    all_ranked_results: List[List[Any]],
    all_relevance_scores: List[Dict[Any, float]],
    k: int = None
) -> float:
    """
    Calculate Mean NDCG across multiple queries.

    Args:
        all_ranked_results: List of ranked result lists, one per query
        all_relevance_scores: List of relevance score dicts, one per query
        k: Number of results to consider (None = all)

    Returns:
        Mean NDCG score
    """
    if len(all_ranked_results) != len(all_relevance_scores):
        raise ValueError("Number of result lists must match number of relevance dicts")

    if len(all_ranked_results) == 0:
        return 0.0

    ndcg_scores = []
    for ranked_results, relevance_scores in zip(all_ranked_results, all_relevance_scores):
        ndcg = calculate_ndcg(ranked_results, relevance_scores, k)
        ndcg_scores.append(ndcg)

    return sum(ndcg_scores) / len(ndcg_scores)


def calculate_success_at_k(
    ranked_results: List[Any],
    relevant: Set[Any] | List[Any],
    k: int
) -> float:
    """
    Calculate Success@K: 1 if at least one relevant document appears
    in top K results, 0 otherwise.

    Args:
        ranked_results: List of document IDs in ranked order
        relevant: Set or list of relevant document IDs
        k: Number of top results to consider

    Returns:
        1.0 if relevant document in top K, 0.0 otherwise
    """
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    top_k = ranked_results[:k]
    for doc_id in top_k:
        if doc_id in relevant_set:
            return 1.0

    return 0.0


def calculate_mean_success_rate(
    all_ranked_results: List[List[Any]],
    all_relevant: List[Set[Any] | List[Any]],
    k: int
) -> float:
    """
    Calculate mean success rate at K across multiple queries.

    Args:
        all_ranked_results: List of ranked result lists, one per query
        all_relevant: List of relevant document sets, one per query
        k: Number of top results to consider

    Returns:
        Mean success rate between 0 and 1
    """
    if len(all_ranked_results) != len(all_relevant):
        raise ValueError("Number of result lists must match number of relevant sets")

    if len(all_ranked_results) == 0:
        return 0.0

    success_count = 0
    for ranked_results, relevant in zip(all_ranked_results, all_relevant):
        if calculate_success_at_k(ranked_results, relevant, k) > 0:
            success_count += 1

    return success_count / len(all_ranked_results)
