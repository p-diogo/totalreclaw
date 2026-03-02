"""
Export and import functionality for ground truth labels.
"""

from typing import List, Dict, Set, Any
import json
import os


def export_labels(
    labels: Dict[str, Dict[str, Any]],
    output_path: str,
    format: str = 'json'
):
    """
    Export labels to file.

    Args:
        labels: Dictionary mapping evaluator_id to labels
        output_path: Output file path
        format: Output format ('json' or 'csv')

    Example:
        >>> labels = {
        ...     'eval1': {
        ...         'q1_d1': {'query_id': 'q1', 'doc_id': 1, 'is_relevant': True},
        ...             'q1_d2': {'query_id': 'q1', 'doc_id': 2, 'is_relevant': False}
        ...         }
        ...     }
        >>> export_labels(labels, 'labels.json')
    """
    if format == 'json':
        with open(output_path, 'w') as f:
            json.dump(labels, f, indent=2)
    elif format == 'csv':
        import csv
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['evaluator_id', 'query_id', 'doc_id', 'is_relevant', 'timestamp'])

            for evaluator_id, evaluator_labels in labels.items():
                for label in evaluator_labels.values():
                    writer.writerow([
                        evaluator_id,
                        label['query_id'],
                        label['doc_id'],
                        label['is_relevant'],
                        label.get('timestamp', '')
                    ])
    else:
        raise ValueError(f"Unknown format: {format}")


def import_labels(input_path: str, format: str = 'json') -> Dict[str, Dict[str, Any]]:
    """
    Import labels from file.

    Args:
        input_path: Input file path
        format: Input format ('json' or 'csv')

    Returns:
        Dictionary mapping evaluator_id to labels
    """
    if format == 'json':
        with open(input_path, 'r') as f:
            return json.load(f)
    elif format == 'csv':
        import csv
        labels = {}

        with open(input_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                evaluator_id = row['evaluator_id']
                if evaluator_id not in labels:
                    labels[evaluator_id] = {}

                key = f"{row['query_id']}_{row['doc_id']}"
                labels[evaluator_id][key] = {
                    'query_id': row['query_id'],
                    'doc_id': int(row['doc_id']),
                    'is_relevant': row['is_relevant'].lower() == 'true',
                    'timestamp': row.get('timestamp', '')
                }

        return labels
    else:
        raise ValueError(f"Unknown format: {format}")


def merge_evaluator_labels(
    evaluator_labels: List[Dict[str, Dict[str, Any]]],
    num_evaluators: int
) -> Dict[str, Set[int]]:
    """
    Merge labels from multiple evaluators using majority voting.

    Args:
        evaluator_labels: List of label dictionaries (one per evaluator)
        num_evaluators: Number of evaluators

    Returns:
        Dictionary mapping query_id to set of relevant document IDs

    Example:
        >>> eval1 = {'q1_d1': {'query_id': 'q1', 'doc_id': 1, 'is_relevant': True}}
        >>> eval2 = {'q1_d1': {'query_id': 'q1', 'doc_id': 1, 'is_relevant': True}}
        >>> eval3 = {'q1_d1': {'query_id': 'q1', 'doc_id': 1, 'is_relevant': False}}
        >>> merge_evaluator_labels([eval1, eval2, eval3], 3)
        {'q1': {1}}  # 2/3 voted relevant
    """
    from collections import defaultdict

    # Collect all votes
    votes = defaultdict(lambda: defaultdict(int))

    for evaluator_dict in evaluator_labels:
        for key, label in evaluator_dict.items():
            query_id = label['query_id']
            doc_id = label['doc_id']
            if label['is_relevant']:
                votes[query_id][doc_id] += 1

    # Apply majority voting
    ground_truth = {}
    threshold = num_evaluators / 2  # More than half

    for query_id, doc_votes in votes.items():
        relevant_docs = {
            doc_id for doc_id, count in doc_votes.items()
            if count > threshold
        }
        ground_truth[query_id] = relevant_docs

    return ground_truth


def create_ground_truth_summary(
    ground_truth: Dict[str, Set[int]],
    queries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Create summary statistics for ground truth.

    Args:
        ground_truth: Dictionary mapping query_id to relevant documents
        queries: List of query dictionaries

    Returns:
        Summary statistics
    """
    total_relevant = sum(len(docs) for docs in ground_truth.values())
    avg_relevant = total_relevant / len(ground_truth) if ground_truth else 0

    category_counts = {}
    for query in queries:
        category = query.get('category', 'unknown')
        relevant_count = len(ground_truth.get(query['id'], set()))
        if category not in category_counts:
            category_counts[category] = {'count': 0, 'relevant': 0}
        category_counts[category]['count'] += 1
        category_counts[category]['relevant'] += relevant_count

    return {
        'total_queries': len(queries),
        'total_relevant_judgments': total_relevant,
        'avg_relevant_per_query': avg_relevant,
        'categories': category_counts
    }


def validate_labels(
    labels: Dict[str, Dict[str, Any]],
    queries: List[Dict[str, Any]],
    documents: Set[int]
) -> Dict[str, List[str]]:
    """
    Validate labels for consistency and completeness.

    Args:
        labels: Labels dictionary
        queries: List of queries
        documents: Set of valid document IDs

    Returns:
        Dictionary with 'errors' and 'warnings' lists
    """
    errors = []
    warnings = []

    # Check for missing queries
    labeled_queries = set()
    for evaluator_labels in labels.values():
        for label in evaluator_labels.values():
            labeled_queries.add(label['query_id'])

    for query in queries:
        if query['id'] not in labeled_queries:
            warnings.append(f"Query {query['id']} has no labels")

    # Check for invalid document IDs
    for evaluator_id, evaluator_labels in labels.items():
        for key, label in evaluator_labels.items():
            doc_id = label['doc_id']
            if doc_id not in documents:
                errors.append(f"{evaluator_id}: Invalid doc_id {doc_id} in {key}")

    # Check for inconsistent labeling (same doc, different labels for same query)
    query_doc_pairs = defaultdict(lambda: {'relevant': 0, 'irrelevant': 0})
    for evaluator_labels in labels.values():
        for label in evaluator_labels.values():
            key = f"{label['query_id']}_{label['doc_id']}"
            if label['is_relevant']:
                query_doc_pairs[key]['relevant'] += 1
            else:
                query_doc_pairs[key]['irrelevant'] += 1

    for pair, counts in query_doc_pairs.items():
        if counts['relevant'] > 0 and counts['irrelevant'] > 0:
            warnings.append(f"Disagreement on {pair}: {counts['relevant']} relevant, {counts['irrelevant']} irrelevant")

    return {'errors': errors, 'warnings': warnings}
