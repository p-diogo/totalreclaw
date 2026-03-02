"""
TotalReclaw Benchmark Harness (OMBH)

A standalone, reproducible benchmark framework for comparing memory systems.
Runs identical multi-session conversations through three memory systems:
- TotalReclaw E2EE (Crypto/LSH)
- Native OpenClaw QMD
- OpenClaw + Mem0 Plugin

Produces publication-grade leaderboards on:
- Accuracy, Latency, Storage, Cost, Downstream Quality, Privacy
"""

__version__ = "0.1.0"
__author__ = "TotalReclaw Team"

from ombh.backends.base import MemoryBackend
from ombh.backends.registry import get_backend, list_backends

__all__ = [
    "MemoryBackend",
    "get_backend",
    "list_backends",
]
