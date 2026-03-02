"""
TotalReclaw Testbed - Evaluation Framework

Main entry point for running search algorithm evaluations.
"""

__version__ = "0.1.0"

from .evaluation import SearchEvaluator, EvaluationConfig, EvaluationResults
from .evaluation import ReportGenerator, GoNoGoDecision, DecisionCriteria
from .metrics import *
from .queries import QueryGenerator
from .labeling import LabelingInterface

__all__ = [
    'SearchEvaluator',
    'EvaluationConfig',
    'EvaluationResults',
    'ReportGenerator',
    'GoNoGoDecision',
    'DecisionCriteria',
    'QueryGenerator',
    'LabelingInterface'
]
