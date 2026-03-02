"""
Memory backend adapters for OMBH.

Available backends:
- TotalReclawE2EEBackend: TotalReclaw with E2EE (localhost:8080) - Privacy Score: 100
- OpenClawQmdBackend: OpenClaw with QMD memory backend (localhost:8081) - Privacy Score: 0
- OpenClawMem0Backend: OpenClaw with Mem0 memory backend (localhost:8082) - Privacy Score: 0
"""

from ombh.backends.base import (
    BackendType,
    BackendStats,
    Fact,
    MemoryBackend,
    RetrievedMemory,
)
from ombh.backends.registry import (
    get_backend,
    is_registered,
    list_backends,
    register_backend,
)

# Import backends to trigger registration
from ombh.backends.totalreclaw_e2ee import TotalReclawE2EEBackend
from ombh.backends.openclaw_qmd import OpenClawQmdBackend
from ombh.backends.openclaw_mem0 import OpenClawMem0Backend

__all__ = [
    # Base classes and types
    "BackendType",
    "BackendStats",
    "Fact",
    "MemoryBackend",
    "RetrievedMemory",
    # Registry functions
    "get_backend",
    "is_registered",
    "list_backends",
    "register_backend",
    # Backend implementations
    "TotalReclawE2EEBackend",
    "OpenClawQmdBackend",
    "OpenClawMem0Backend",
]
