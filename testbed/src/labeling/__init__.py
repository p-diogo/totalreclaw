"""
Ground truth labeling interface for TotalReclaw testbed.

Web-based interface for evaluators to label query-document relevance.
"""

from .interface import LabelingInterface, Label, QueryDocumentPair
from .export_import import export_labels, import_labels, merge_evaluator_labels

__all__ = [
    'LabelingInterface',
    'Label',
    'QueryDocumentPair',
    'export_labels',
    'import_labels',
    'merge_evaluator_labels'
]
