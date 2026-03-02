"""
TotalReclaw Testbed Evaluation Module

Main evaluation framework for running search algorithm benchmarks and generating reports.
"""

from .evaluator import SearchEvaluator, EvaluationConfig
from .results import EvaluationResults, QueryResult, AlgorithmResult
from .report_generator import ReportGenerator
from .go_no_go import GoNoGoDecision, DecisionCriteria

__all__ = [
    'SearchEvaluator',
    'EvaluationConfig',
    'EvaluationResults',
    'QueryResult',
    'AlgorithmResult',
    'ReportGenerator',
    'GoNoGoDecision',
    'DecisionCriteria'
]
