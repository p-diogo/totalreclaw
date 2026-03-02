"""
Main search evaluation framework.

Coordinates running search algorithms, calculating metrics, and generating results.
"""

from typing import List, Dict, Set, Callable, Any, Optional
from dataclasses import dataclass
import time
import numpy as np

from .results import EvaluationResults, QueryResult, AlgorithmResult
from ..metrics.precision_recall import (
    calculate_precision, calculate_recall, calculate_f1,
    calculate_average_precision
)
from ..metrics.rank_metrics import (
    calculate_reciprocal_rank, calculate_ndcg
)
from ..metrics.latency import calculate_latency_percentiles
from ..metrics.statistical_tests import compare_algorithms
from ..metrics.agreement import calculate_fleiss_kappa


@dataclass
class EvaluationConfig:
    """Configuration for search evaluation."""

    # Dataset
    documents: List[str]
    document_ids: List[int]

    # Ground truth
    ground_truth: Dict[str, Set[int]]  # query_id -> relevant document IDs
    queries: List[Dict[str, Any]]  # List of query dicts with id, text, category

    # Algorithms
    algorithms: Dict[str, Callable]  # name -> search function

    # Metadata
    num_evaluators: int = 3
    fleiss_kappa: float = 0.0

    # Evaluation parameters
    top_k: int = 5


class SearchEvaluator:
    """
    Main evaluator for running search algorithm benchmarks.

    Example:
        >>> config = EvaluationConfig(
        ...     documents=documents,
        ...     document_ids=list(range(len(documents))),
        ...     ground_truth=ground_truth,
        ...     queries=queries,
        ...     algorithms={
        ...             'bm25': bm25_search,
        ...             'vector': vector_search
        ...     }
        ... )
        >>> evaluator = SearchEvaluator(config)
        >>> results = evaluator.run_evaluation()
    """

    def __init__(self, config: EvaluationConfig):
        self.config = config
        self.results = EvaluationResults(
            dataset_size=len(config.documents),
            num_queries=len(config.queries),
            num_evaluators=config.num_evaluators,
            fleiss_kappa=config.fleiss_kappa
        )

        # Extract categories
        self.results.categories = sorted(set(q.get('category', 'unknown') for q in config.queries))

    def run_evaluation(self) -> EvaluationResults:
        """
        Run complete evaluation of all algorithms on all queries.

        Returns:
            EvaluationResults with all metrics calculated
        """
        # Run each algorithm
        for algo_name, algo_func in self.config.algorithms.items():
            print(f"\n=== Evaluating {algo_name} ===")
            algo_result = self._evaluate_algorithm(algo_name, algo_func)
            self.results.add_algorithm_result(algo_result)

        # Calculate pairwise comparisons
        print("\n=== Calculating statistical comparisons ===")
        self._calculate_pairwise_comparisons()

        return self.results

    def _evaluate_algorithm(
        self,
        algo_name: str,
        algo_func: Callable
    ) -> AlgorithmResult:
        """
        Evaluate a single algorithm on all queries.

        Args:
            algo_name: Name of the algorithm
            algo_func: Search function that takes (query, documents, top_k) and returns
                      List of (doc_id, score) tuples

        Returns:
            AlgorithmResult with all query-level metrics
        """
        query_results = []
        latencies = []

        for i, query_info in enumerate(self.config.queries):
            query_id = query_info['id']
            query_text = query_info['text']
            category = query_info.get('category', 'unknown')
            relevant = self.config.ground_truth.get(query_id, set())

            # Run search with timing
            start_time = time.perf_counter()

            try:
                search_results = algo_func(
                    query_text,
                    self.config.documents,
                    self.config.document_ids,
                    top_k=self.config.top_k
                )
            except Exception as e:
                print(f"  Error on query {query_id}: {e}")
                search_results = []

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000

            # Extract document IDs and scores
            retrieved = []
            scores = []
            for item in search_results:
                if isinstance(item, tuple) and len(item) >= 2:
                    retrieved.append(item[0])
                    scores.append(item[1])
                elif isinstance(item, (int, str)):
                    retrieved.append(int(item))
                    scores.append(1.0)

            # Calculate metrics
            precision = calculate_precision(retrieved, relevant)
            recall = calculate_recall(retrieved, relevant)
            f1 = calculate_f1(retrieved, relevant)
            ap = calculate_average_precision(retrieved, relevant)
            rr = calculate_reciprocal_rank(retrieved, relevant)

            # Calculate NDCG if we have relevance scores
            # For binary relevance, use 1 for relevant, 0 for non-relevant
            relevance_scores = {doc_id: (1 if doc_id in relevant else 0) for doc_id in retrieved}
            ndcg = calculate_ndcg(retrieved, relevance_scores, k=len(retrieved))

            query_result = QueryResult(
                query_id=query_id,
                query_text=query_text,
                algorithm_name=algo_name,
                category=category,
                retrieved=retrieved,
                relevant=relevant,
                scores=scores,
                latency_ms=latency_ms,
                precision=precision,
                recall=recall,
                f1=f1,
                ap=ap,
                rr=rr,
                ndcg=ndcg
            )

            query_results.append(query_result)
            latencies.append(latency_ms)

            if (i + 1) % 10 == 0:
                print(f"  Processed {i + 1}/{len(self.config.queries)} queries")

        # Create AlgorithmResult and calculate aggregates
        algo_result = AlgorithmResult(algorithm_name=algo_name, query_results=query_results)
        algo_result.calculate_aggregates()

        # Print summary
        print(f"  Mean F1: {algo_result.mean_f1:.3f}")
        print(f"  Mean Precision: {algo_result.mean_precision:.3f}")
        print(f"  Mean Recall: {algo_result.mean_recall:.3f}")
        print(f"  MRR: {algo_result.mrr:.3f}")
        print(f"  MAP: {algo_result.map_score:.3f}")
        print(f"  Latency p50: {algo_result.latency_p50:.0f}ms")

        return algo_result

    def _calculate_pairwise_comparisons(self):
        """Calculate statistical significance tests between algorithm pairs."""
        # Prepare data: algorithm -> list of F1 scores
        algo_scores = {}
        for name, result in self.results.algorithm_results.items():
            algo_scores[name] = [qr.f1 for qr in result.query_results]

        # Run comparisons
        self.results.pairwise_comparisons = compare_algorithms(algo_scores)

    def run_single_query(
        self,
        query_text: str,
        category: str = 'unknown'
    ) -> Dict[str, QueryResult]:
        """
        Run a single query across all algorithms.

        Useful for ad-hoc testing and debugging.

        Args:
            query_text: Query string
            category: Query category

        Returns:
            Dictionary mapping algorithm name to QueryResult
        """
        results = {}
        query_id = f"ad_hoc_{int(time.time())}"

        for algo_name, algo_func in self.config.algorithms.items():
            start_time = time.perf_counter()

            try:
                search_results = algo_func(
                    query_text,
                    self.config.documents,
                    self.config.document_ids,
                    top_k=self.config.top_k
                )
            except Exception as e:
                print(f"Error in {algo_name}: {e}")
                continue

            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000

            # Extract results
            retrieved = []
            scores = []
            for item in search_results:
                if isinstance(item, tuple) and len(item) >= 2:
                    retrieved.append(item[0])
                    scores.append(item[1])
                elif isinstance(item, (int, str)):
                    retrieved.append(int(item))
                    scores.append(1.0)

            results[algo_name] = QueryResult(
                query_id=query_id,
                query_text=query_text,
                algorithm_name=algo_name,
                category=category,
                retrieved=retrieved,
                relevant=set(),  # No ground truth for ad-hoc queries
                scores=scores,
                latency_ms=latency_ms
            )

        return results


def create_ground_truth_from_labels(
    labels: Dict[str, Dict[int, bool]],
    num_evaluators: int = 3
) -> Dict[str, Set[int]]:
    """
    Create ground truth from multiple evaluators' labels using majority voting.

    Args:
        labels: Dictionary mapping query_id to {doc_id: label} dict
                where labels are lists of bool from multiple evaluators
        num_evaluators: Number of evaluators

    Returns:
        Dictionary mapping query_id to set of relevant document IDs

    Example:
        >>> labels = {
        ...     'q1': {
        ...         1: [True, True, False],  # 2/3 say relevant
        ...         2: [False, False, True],  # 1/3 say relevant
        ...         3: [True, True, True]     # 3/3 say relevant
        ...     }
        ... }
        >>> create_ground_truth_from_labels(labels)
        {'q1': {1, 3}}  # Only docs with majority vote for relevant
    """
    from ..metrics.agreement import majority_vote

    ground_truth = {}

    for query_id, doc_labels in labels.items():
        relevant_docs = set()

        for doc_id, labels_list in doc_labels.items():
            if len(labels_list) == num_evaluators:
                # Use majority vote
                if sum(labels_list) > num_evaluators / 2:
                    relevant_docs.add(doc_id)

        ground_truth[query_id] = relevant_docs

    return ground_truth


def load_ground_truth_from_file(filepath: str) -> Dict[str, Set[int]]:
    """
    Load ground truth from JSON file.

    Expected format:
    {
        "query_id": {
            "relevant": [doc_id1, doc_id2, ...],
            "category": "contextual"
        },
        ...
    }

    Args:
        filepath: Path to ground truth JSON file

    Returns:
        Dictionary mapping query_id to set of relevant document IDs
    """
    import json

    with open(filepath, 'r') as f:
        data = json.load(f)

    ground_truth = {}
    for query_id, query_data in data.items():
        ground_truth[query_id] = set(query_data['relevant'])

    return ground_truth


def save_ground_truth_to_file(
    ground_truth: Dict[str, Set[int]],
    queries: List[Dict[str, Any]],
    filepath: str
):
    """
    Save ground truth to JSON file.

    Args:
        ground_truth: Dictionary mapping query_id to set of relevant document IDs
        queries: List of query dictionaries
        filepath: Output file path
    """
    import json

    data = {}
    for query in queries:
        query_id = query['id']
        data[query_id] = {
            'text': query['text'],
            'category': query.get('category', 'unknown'),
            'relevant': sorted(list(ground_truth.get(query_id, set())))
        }

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
