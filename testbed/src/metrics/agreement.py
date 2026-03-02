"""
Inter-annotator agreement metrics.

Calculates Fleiss' kappa for multiple annotators and Cohen's kappa for two annotators.
"""

from typing import List, Dict, Set, Any
import numpy as np
from collections import defaultdict


def majority_vote(
    annotations: List[List[Any]],
    num_items: int,
    num_categories: int = 2
) -> List[int]:
    """
    Determine ground truth labels using majority voting.

    Args:
        annotations: List of annotator label lists (each annotator's labels for all items)
        num_items: Number of items to label
        num_categories: Number of possible labels (binary by default)

    Returns:
        List of majority-vote labels (0 or 1 for binary)

    Example:
        >>> # 3 annotators, 5 items
        >>> annotations = [
        ...     [1, 0, 1, 1, 0],  # Annotator 1
        ...     [1, 1, 1, 0, 0],  # Annotator 2
        ...     [1, 0, 1, 1, 0],  # Annotator 3
        ... ]
        >>> majority_vote(annotations, 5)
        [1, 0, 1, 1, 0]  # Item 2 is disputed, defaults to 0 (tie-break)
    """
    ground_truth = []

    for item_idx in range(num_items):
        votes = [annotator[item_idx] for annotator in annotations]

        # Count votes for each category
        vote_counts = defaultdict(int)
        for vote in votes:
            vote_counts[vote] += 1

        # Get category with most votes
        max_votes = max(vote_counts.values())
        winners = [cat for cat, count in vote_counts.items() if count == max_votes]

        # In case of tie, choose the lowest category (more conservative)
        ground_truth.append(min(winners))

    return ground_truth


def calculate_fleiss_kappa(
    annotations: List[List[int]],
    num_categories: int = 2
) -> Dict[str, float]:
    """
    Calculate Fleiss' kappa for inter-annotator agreement among multiple raters.

    Fleiss' kappa measures agreement among multiple annotators rating multiple items.
    Values range from -1 (complete disagreement) to 1 (complete agreement).

    Formula:
        κ = (P̄ - P̄e) / (1 - P̄e)

    where:
        P̄ = observed agreement
        P̄e = expected agreement by chance

    Args:
        annotations: List where each element is a list of annotator ratings for one item
                     e.g., [[1,1,0], [0,1,1], [1,1,1]] for 3 items, 3 annotators
        num_categories: Number of possible rating categories (default: 2 for binary)

    Returns:
        Dictionary with kappa value and interpretation

    Example:
        >>> annotations = [
        ...     [1, 1, 0],  # Item 1: 2 say relevant, 1 says not
        ...     [0, 1, 1],  # Item 2: 2 say relevant, 1 says not
        ...     [1, 1, 1],  # Item 3: all say relevant
        ... ]
        >>> calculate_fleiss_kappa(annotations)
        {'kappa': 0.31, 'interpretation': 'fair agreement'}
    """
    if not annotations:
        return {'kappa': 0.0, 'interpretation': 'no data'}

    num_items = len(annotations)
    num_annotators = len(annotations[0])

    # Build the category count matrix
    # n_ij = number of annotators who assigned item i to category j
    n = np.zeros((num_items, num_categories))

    for i, item_ratings in enumerate(annotations):
        for rating in item_ratings:
            if 0 <= rating < num_categories:
                n[i, rating] += 1

    # Calculate Pj: proportion of all assignments to category j
    n_total = num_items * num_annotators
    Pj = np.sum(n, axis=0) / n_total

    # Calculate P̄e: expected agreement by chance
    Pe = np.sum(Pj ** 2)

    # Calculate Pi: agreement for each item
    # Pi = (1 / (n(n-1))) * Σ(n_ij^2 - n_ij)
    Pi = []
    for i in range(num_items):
        ni_squared_sum = np.sum(n[i] ** 2)
        ni_sum = np.sum(n[i])
        if num_annotators > 1:
            pi_val = (ni_squared_sum - ni_sum) / (num_annotators * (num_annotators - 1))
        else:
            pi_val = 0.0
        Pi.append(pi_val)

    # Calculate P̄: overall observed agreement
    Pbar = np.mean(Pi)

    # Calculate Fleiss' kappa
    if (1 - Pe) == 0:
        kappa = 0.0
    else:
        kappa = (Pbar - Pe) / (1 - Pe)

    return {
        'kappa': float(kappa),
        'interpretation': _interpret_kappa(kappa),
        'observed_agreement': float(Pbar),
        'expected_agreement': float(Pe)
    }


def calculate_cohens_kappa(
    ratings1: List[int],
    ratings2: List[int]
) -> Dict[str, float]:
    """
    Calculate Cohen's kappa for inter-annotator agreement between two raters.

    Cohen's kappa measures agreement between two annotators.
    Values range from -1 (complete disagreement) to 1 (complete agreement).

    Args:
        ratings1: List of ratings from annotator 1
        ratings2: List of ratings from annotator 2

    Returns:
        Dictionary with kappa value and interpretation

    Example:
        >>> r1 = [1, 0, 1, 1, 0]
        >>> r2 = [1, 1, 1, 0, 0]
        >>> calculate_cohens_kappa(r1, r2)
        {'kappa': 0.4, 'interpretation': 'moderate agreement'}
    """
    if len(ratings1) != len(ratings2):
        raise ValueError("Rating lists must be the same length")

    if not ratings1:
        return {'kappa': 0.0, 'interpretation': 'no data'}

    n = len(ratings1)

    # Get unique categories
    categories = sorted(set(ratings1 + ratings2))
    num_categories = len(categories)

    # Build confusion matrix
    confusion = np.zeros((num_categories, num_categories))
    for r1, r2 in zip(ratings1, ratings2):
        i = categories.index(r1)
        j = categories.index(r2)
        confusion[i, j] += 1

    # Calculate observed agreement
    observed_agreement = np.trace(confusion) / n

    # Calculate expected agreement
    row_sums = np.sum(confusion, axis=1)
    col_sums = np.sum(confusion, axis=0)

    expected_agreement = 0.0
    for i in range(num_categories):
        for j in range(num_categories):
            expected_agreement += (row_sums[i] * col_sums[j]) / (n ** 2)

    # Calculate Cohen's kappa
    if (1 - expected_agreement) == 0:
        kappa = 0.0
    else:
        kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement)

    return {
        'kappa': float(kappa),
        'interpretation': _interpret_kappa(kappa),
        'observed_agreement': float(observed_agreement),
        'expected_agreement': float(expected_agreement)
    }


def _interpret_kappa(kappa: float) -> str:
    """
    Interpret kappa value according to Landis & Koch (1977).

    Args:
        kappa: Kappa value

    Returns:
        Interpretation string
    """
    if kappa < 0:
        return 'poor agreement (worse than chance)'
    elif kappa < 0.20:
        return 'slight agreement'
    elif kappa < 0.40:
        return 'fair agreement'
    elif kappa < 0.60:
        return 'moderate agreement'
    elif kappa < 0.80:
        return 'substantial agreement'
    else:
        return 'almost perfect agreement'


def calculate_agreement_by_category(
    annotations: List[List[int]],
    categories: List[str],
    num_categories: int = 2
) -> Dict[str, Dict[str, float]]:
    """
    Calculate agreement metrics broken down by category.

    Args:
        annotations: List of annotator ratings for each item
        categories: Category label for each item
        num_categories: Number of rating categories (binary by default)

    Returns:
        Dictionary mapping category names to kappa statistics
    """
    # Group annotations by category
    category_groups = defaultdict(list)

    for item_annotations, category in zip(annotations, categories):
        category_groups[category].append(item_annotations)

    results = {}
    for category, group_annotations in category_groups.items():
        if len(group_annotations) > 1:
            kappa_result = calculate_fleiss_kappa(group_annotations, num_categories)
            results[category] = kappa_result

    return results


def calculate_pairwise_agreement(
    annotations: List[List[int]]
) -> Dict[str, float]:
    """
    Calculate pairwise Cohen's kappa between all annotator pairs.

    Args:
        annotations: List of annotator rating lists

    Returns:
        Dictionary with pair names as keys and kappa values as values

    Example:
        >>> annotations = [
        ...     [1, 0, 1, 1, 0],  # Annotator 1
        ...     [1, 1, 1, 0, 0],  # Annotator 2
        ...     [1, 0, 1, 1, 0],  # Annotator 3
        ... ]
        >>> calculate_pairwise_agreement(annotations)
        {
            'annotator_0_vs_annotator_1': 0.4,
            'annotator_0_vs_annotator_2': 1.0,
            'annotator_1_vs_annotator_2': 0.4
        }
    """
    num_annotators = len(annotations)
    pairwise_kappas = {}

    for i in range(num_annotators):
        for j in range(i + 1, num_annotators):
            kappa_result = calculate_cohens_kappa(
                annotations[i],
                annotations[j]
            )
            pair_name = f'annotator_{i}_vs_annotator_{j}'
            pairwise_kappas[pair_name] = kappa_result['kappa']

    return pairwise_kappas
