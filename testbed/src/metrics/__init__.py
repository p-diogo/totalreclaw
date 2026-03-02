"""
TotalReclaw Testbed Metrics Module

Core metrics for evaluating search accuracy:
- Precision, Recall, F1 Score
- Mean Reciprocal Rank (MRR)
- Latency percentiles (p50, p95, p99)
- Statistical significance tests
- Inter-annotator agreement (Fleiss' kappa)
"""

from .precision_recall import (
    calculate_precision,
    calculate_recall,
    calculate_f1,
    calculate_average_precision
)

from .rank_metrics import (
    calculate_mrr,
    calculate_reciprocal_rank,
    calculate_dcg,
    calculate_ndcg
)

from .latency import (
    calculate_latency_percentiles,
    calculate_percentile
)

from .agreement import (
    calculate_fleiss_kappa,
    calculate_cohens_kappa,
    majority_vote
)

from .statistical_tests import (
    paired_ttest,
    wilcoxon_signed_rank_test,
    bootstrap_confidence_interval
)

__all__ = [
    'calculate_precision',
    'calculate_recall',
    'calculate_f1',
    'calculate_average_precision',
    'calculate_mrr',
    'calculate_reciprocal_rank',
    'calculate_dcg',
    'calculate_ndcg',
    'calculate_latency_percentiles',
    'calculate_percentile',
    'calculate_fleiss_kappa',
    'calculate_cohens_kappa',
    'majority_vote',
    'paired_ttest',
    'wilcoxon_signed_rank_test',
    'bootstrap_confidence_interval'
]
