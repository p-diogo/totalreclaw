"""
Data structures for evaluation results.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Any, Optional
from datetime import datetime
import json


@dataclass
class QueryResult:
    """Results for a single query on a single algorithm."""

    query_id: str
    query_text: str
    algorithm_name: str
    category: str

    # Retrieved results (document IDs in ranked order)
    retrieved: List[int] = field(default_factory=list)

    # Ground truth (relevant document IDs)
    relevant: Set[int] = field(default_factory=set)

    # Scores for each retrieved document
    scores: List[float] = field(default_factory=list)

    # Latency in milliseconds
    latency_ms: float = 0.0

    # Metrics
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    ap: float = 0.0  # Average Precision
    rr: float = 0.0  # Reciprocal Rank
    ndcg: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'query_id': self.query_id,
            'query_text': self.query_text,
            'algorithm': self.algorithm_name,
            'category': self.category,
            'retrieved': self.retrieved,
            'relevant': list(self.relevant),
            'scores': self.scores,
            'latency_ms': self.latency_ms,
            'precision': self.precision,
            'recall': self.recall,
            'f1': self.f1,
            'ap': self.ap,
            'rr': self.rr,
            'ndcg': self.ndcg
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueryResult':
        """Create from dictionary."""
        return cls(
            query_id=data['query_id'],
            query_text=data['query_text'],
            algorithm_name=data['algorithm'],
            category=data['category'],
            retrieved=data.get('retrieved', []),
            relevant=set(data.get('relevant', [])),
            scores=data.get('scores', []),
            latency_ms=data.get('latency_ms', 0.0),
            precision=data.get('precision', 0.0),
            recall=data.get('recall', 0.0),
            f1=data.get('f1', 0.0),
            ap=data.get('ap', 0.0),
            rr=data.get('rr', 0.0),
            ndcg=data.get('ndcg', 0.0)
        )


@dataclass
class AlgorithmResult:
    """Aggregated results for a single algorithm across all queries."""

    algorithm_name: str

    # Individual query results
    query_results: List[QueryResult] = field(default_factory=list)

    # Aggregate metrics (mean across all queries)
    mean_precision: float = 0.0
    mean_recall: float = 0.0
    mean_f1: float = 0.0
    map_score: float = 0.0  # Mean Average Precision
    mrr: float = 0.0  # Mean Reciprocal Rank
    mean_ndcg: float = 0.0

    # Latency statistics
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    latency_mean: float = 0.0

    # Per-category metrics
    metrics_by_category: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def calculate_aggregates(self):
        """Calculate aggregate metrics from query results."""
        if not self.query_results:
            return

        # Calculate means
        self.mean_precision = sum(r.precision for r in self.query_results) / len(self.query_results)
        self.mean_recall = sum(r.recall for r in self.query_results) / len(self.query_results)
        self.mean_f1 = sum(r.f1 for r in self.query_results) / len(self.query_results)
        self.map_score = sum(r.ap for r in self.query_results) / len(self.query_results)
        self.mrr = sum(r.rr for r in self.query_results) / len(self.query_results)
        self.mean_ndcg = sum(r.ndcg for r in self.query_results) / len(self.query_results)

        # Calculate latency percentiles
        latencies = [r.latency_ms for r in self.query_results if r.latency_ms > 0]
        if latencies:
            import numpy as np
            self.latency_p50 = float(np.percentile(latencies, 50))
            self.latency_p95 = float(np.percentile(latencies, 95))
            self.latency_p99 = float(np.percentile(latencies, 99))
            self.latency_mean = float(np.mean(latencies))

        # Calculate per-category metrics
        from collections import defaultdict
        category_results = defaultdict(list)
        for r in self.query_results:
            category_results[r.category].append(r)

        self.metrics_by_category = {}
        for category, results in category_results.items():
            self.metrics_by_category[category] = {
                'count': len(results),
                'precision': sum(r.precision for r in results) / len(results),
                'recall': sum(r.recall for r in results) / len(results),
                'f1': sum(r.f1 for r in results) / len(results),
                'mrr': sum(r.rr for r in results) / len(results)
            }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'algorithm': self.algorithm_name,
            'num_queries': len(self.query_results),
            'mean_precision': self.mean_precision,
            'mean_recall': self.mean_recall,
            'mean_f1': self.mean_f1,
            'map': self.map_score,
            'mrr': self.mrr,
            'mean_ndcg': self.mean_ndcg,
            'latency_p50_ms': self.latency_p50,
            'latency_p95_ms': self.latency_p95,
            'latency_p99_ms': self.latency_p99,
            'latency_mean_ms': self.latency_mean,
            'metrics_by_category': self.metrics_by_category
        }


@dataclass
class EvaluationResults:
    """Complete evaluation results for all algorithms."""

    timestamp: datetime = field(default_factory=datetime.now)
    dataset_size: int = 0
    num_queries: int = 0
    num_evaluators: int = 0

    # Ground truth metadata
    fleiss_kappa: float = 0.0
    inter_annotator_agreement: str = ""

    # Results per algorithm
    algorithm_results: Dict[str, AlgorithmResult] = field(default_factory=dict)

    # All query results
    all_query_results: List[QueryResult] = field(default_factory=list)

    # Query categories
    categories: List[str] = field(default_factory=list)

    # Comparison statistics
    pairwise_comparisons: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Go/No-Go decision
    go_no_go_decision: Optional[str] = None
    go_no_go_rationale: str = ""

    def add_algorithm_result(self, result: AlgorithmResult):
        """Add results for an algorithm."""
        self.algorithm_results[result.algorithm_name] = result
        self.all_query_results.extend(result.query_results)

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Get sorted leaderboard by F1 score."""
        leaderboard = []
        for name, result in self.algorithm_results.items():
            leaderboard.append({
                'algorithm': name,
                'f1': result.mean_f1,
                'precision': result.mean_precision,
                'recall': result.mean_recall,
                'mrr': result.mrr,
                'map': result.map_score,
                'latency_p50': result.latency_p50
            })

        leaderboard.sort(key=lambda x: x['f1'], reverse=True)
        return leaderboard

    def get_comparison_table(self) -> str:
        """Generate a markdown comparison table."""
        headers = ['Algorithm', 'Precision', 'Recall', 'F1', 'MRR', 'MAP', 'p50']
        rows = []

        for name, result in self.algorithm_results.items():
            rows.append([
                name,
                f"{result.mean_precision:.3f}",
                f"{result.mean_recall:.3f}",
                f"{result.mean_f1:.3f}",
                f"{result.mrr:.3f}",
                f"{result.map_score:.3f}",
                f"{result.latency_p50:.0f}ms"
            ])

        table = "| " + " | ".join(headers) + " |\n"
        table += "|" + "|".join(["---"] * len(headers)) + "|\n"
        for row in rows:
            table += "| " + " | ".join(row) + " |\n"

        return table

    def to_json(self, filepath: str):
        """Save results to JSON file."""
        data = {
            'timestamp': self.timestamp.isoformat(),
            'dataset_size': self.dataset_size,
            'num_queries': self.num_queries,
            'num_evaluators': self.num_evaluators,
            'fleiss_kappa': self.fleiss_kappa,
            'inter_annotator_agreement': self.inter_annotator_agreement,
            'categories': self.categories,
            'go_no_go_decision': self.go_no_go_decision,
            'go_no_go_rationale': self.go_no_go_rationale,
            'algorithm_results': {
                name: result.to_dict()
                for name, result in self.algorithm_results.items()
            },
            'query_results': [qr.to_dict() for qr in self.all_query_results],
            'pairwise_comparisons': self.pairwise_comparisons
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def from_json(cls, filepath: str) -> 'EvaluationResults':
        """Load results from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        results = cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            dataset_size=data['dataset_size'],
            num_queries=data['num_queries'],
            num_evaluators=data['num_evaluators'],
            fleiss_kappa=data['fleiss_kappa'],
            inter_annotator_agreement=data['inter_annotator_agreement'],
            categories=data['categories'],
            go_no_go_decision=data.get('go_no_go_decision'),
            go_no_go_rationale=data.get('go_no_go_rationale', ''),
            pairwise_comparisons=data.get('pairwise_comparisons', {})
        )

        for name, algo_data in data['algorithm_results'].items():
            algo_result = AlgorithmResult(algorithm_name=name)
            algo_result.mean_precision = algo_data['mean_precision']
            algo_result.mean_recall = algo_data['mean_recall']
            algo_result.mean_f1 = algo_data['mean_f1']
            algo_result.map_score = algo_data['map']
            algo_result.mrr = algo_data['mrr']
            algo_result.mean_ndcg = algo_data['mean_ndcg']
            algo_result.latency_p50 = algo_data['latency_p50_ms']
            algo_result.latency_p95 = algo_data['latency_p95_ms']
            algo_result.latency_p99 = algo_data['latency_p99_ms']
            algo_result.latency_mean = algo_data['latency_mean_ms']
            algo_result.metrics_by_category = algo_data['metrics_by_category']
            results.algorithm_results[name] = algo_result

        results.all_query_results = [
            QueryResult.from_dict(qr_data) for qr_data in data['query_results']
        ]

        return results
