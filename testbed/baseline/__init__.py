"""
TotalReclaw Baseline Search Algorithms

This module implements the 4 plaintext baseline search algorithms that TotalReclaw
will be compared against in the testbed.

Algorithms:
1. BM25-Only: Pure keyword search using rank-bm25
2. Vector-Only: Pure semantic search using cosine similarity
3. OpenClaw Hybrid: Replicate official OpenClaw algorithm
4. QMD-Style Hybrid: Replicate QMD's sophisticated approach
"""

__version__ = "1.0.0"

from .bm25_only import bm25_only_search
from .vector_only import vector_only_search
from .openclaw_hybrid import openclaw_hybrid_search
from .qmd_hybrid import qmd_hybrid_search

__all__ = [
    "bm25_only_search",
    "vector_only_search",
    "openclaw_hybrid_search",
    "qmd_hybrid_search",
]
