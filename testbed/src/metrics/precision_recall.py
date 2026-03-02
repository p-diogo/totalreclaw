"""
Precision, Recall, F1 Score, and Average Precision metrics.

These metrics measure the accuracy of retrieved results compared to ground truth.
"""

from typing import List, Set, Dict, Any
import numpy as np


def calculate_precision(
    retrieved: Set[Any] | List[Any],
    relevant: Set[Any] | List[Any]
) -> float:
    """
    Calculate precision: |Relevant Retrieved| / |All Retrieved|

    Args:
        retrieved: Set or list of retrieved document IDs
        relevant: Set or list of relevant document IDs

    Returns:
        Precision score between 0 and 1

    Example:
        >>> retrieved = {1, 2, 3, 4, 5}
        >>> relevant = {1, 3, 5, 7, 9}
        >>> calculate_precision(retrieved, relevant)
        0.6  # 3 out of 5 retrieved are relevant
    """
    retrieved_set = set(retrieved) if not isinstance(retrieved, set) else retrieved
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    if len(retrieved_set) == 0:
        return 0.0

    relevant_retrieved = retrieved_set & relevant_set
    return len(relevant_retrieved) / len(retrieved_set)


def calculate_recall(
    retrieved: Set[Any] | List[Any],
    relevant: Set[Any] | List[Any]
) -> float:
    """
    Calculate recall: |Relevant Retrieved| / |All Relevant|

    Args:
        retrieved: Set or list of retrieved document IDs
        relevant: Set or list of relevant document IDs

    Returns:
        Recall score between 0 and 1

    Example:
        >>> retrieved = {1, 2, 3, 4, 5}
        >>> relevant = {1, 3, 5, 7, 9}
        >>> calculate_recall(retrieved, relevant)
        0.6  # 3 out of 5 relevant were retrieved
    """
    retrieved_set = set(retrieved) if not isinstance(retrieved, set) else retrieved
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    if len(relevant_set) == 0:
        return 0.0

    relevant_retrieved = retrieved_set & relevant_set
    return len(relevant_retrieved) / len(relevant_set)


def calculate_f1(
    retrieved: Set[Any] | List[Any],
    relevant: Set[Any] | List[Any]
) -> float:
    """
    Calculate F1 score: 2 × (Precision × Recall) / (Precision + Recall)

    Args:
        retrieved: Set or list of retrieved document IDs
        relevant: Set or list of relevant document IDs

    Returns:
        F1 score between 0 and 1

    Example:
        >>> retrieved = {1, 2, 3, 4, 5}
        >>> relevant = {1, 3, 5, 7, 9}
        >>> calculate_f1(retrieved, relevant)
        0.6
    """
    precision = calculate_precision(retrieved, relevant)
    recall = calculate_recall(retrieved, relevant)

    if precision + recall == 0:
        return 0.0

    return 2 * (precision * recall) / (precision + recall)


def calculate_average_precision(
    ranked_results: List[Any],
    relevant: Set[Any] | List[Any]
) -> float:
    """
    Calculate Average Precision (AP): average of precision scores at each
    relevant document position.

    AP is a ranking metric that considers the order of results.

    Args:
        ranked_results: List of document IDs in ranked order
        relevant: Set or list of relevant document IDs

    Returns:
        Average Precision score between 0 and 1

    Example:
        >>> ranked = [7, 2, 9, 4, 3, 8]  # Relevant items: 2, 3, 7, 9
        >>> relevant = {2, 3, 7, 9}
        >>> calculate_average_precision(ranked, relevant)
        0.79  # Average precision at each relevant position
    """
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    if len(relevant_set) == 0:
        return 0.0

    precisions = []
    num_relevant_found = 0

    for i, doc_id in enumerate(ranked_results, start=1):
        if doc_id in relevant_set:
            num_relevant_found += 1
            precision_at_i = num_relevant_found / i
            precisions.append(precision_at_i)

    if len(precisions) == 0:
        return 0.0

    return sum(precisions) / len(relevant_set)


def calculate_precision_at_k(
    ranked_results: List[Any],
    relevant: Set[Any] | List[Any],
    k: int
) -> float:
    """
    Calculate Precision@K: precision of top K results.

    Args:
        ranked_results: List of document IDs in ranked order
        relevant: Set or list of relevant document IDs
        k: Number of top results to consider

    Returns:
        Precision@K score between 0 and 1

    Example:
        >>> ranked = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        >>> relevant = {1, 3, 5, 7, 9}
        >>> calculate_precision_at_k(ranked, relevant, 5)
        0.6  # 3 out of top 5 are relevant
    """
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    top_k = ranked_results[:k]
    if len(top_k) == 0:
        return 0.0

    relevant_in_top_k = sum(1 for doc_id in top_k if doc_id in relevant_set)
    return relevant_in_top_k / k


def calculate_recall_at_k(
    ranked_results: List[Any],
    relevant: Set[Any] | List[Any],
    k: int
) -> float:
    """
    Calculate Recall@K: recall of top K results.

    Args:
        ranked_results: List of document IDs in ranked order
        relevant: Set or list of relevant document IDs
        k: Number of top results to consider

    Returns:
        Recall@K score between 0 and 1
    """
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    if len(relevant_set) == 0:
        return 0.0

    top_k = ranked_results[:k]
    relevant_in_top_k = sum(1 for doc_id in top_k if doc_id in relevant_set)
    return relevant_in_top_k / len(relevant_set)


def calculate_mean_metrics(
    all_results: List[Dict[str, Any]],
    metric_names: List[str] = None
) -> Dict[str, float]:
    """
    Calculate mean values across multiple query results.

    Args:
        all_results: List of result dictionaries with metric values
        metric_names: List of metric names to average (default: all)

    Returns:
        Dictionary of mean metric values

    Example:
        >>> results = [
        ...     {'precision': 0.8, 'recall': 0.7, 'f1': 0.75},
        ...     {'precision': 0.9, 'recall': 0.6, 'f1': 0.7}
        ... ]
        >>> calculate_mean_metrics(results)
        {'precision': 0.85, 'recall': 0.65, 'f1': 0.725}
    """
    if not all_results:
        return {}

    if metric_names is None:
        # Extract all metric names from first result
        metric_names = list(all_results[0].keys())

    means = {}
    for name in metric_names:
        values = [r.get(name, 0) for r in all_results if name in r]
        if values:
            means[name] = sum(values) / len(values)
        else:
            means[name] = 0.0

    return means
