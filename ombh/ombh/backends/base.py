"""
MemoryBackend Abstract Base Class

Every memory system must implement this interface for fair comparison.
All methods are async to support both local and remote backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class BackendType(Enum):
    """Supported backend types."""
    TOTALRECLAW_E2EE = "totalreclaw_e2ee"
    OPENCLAW_QMD = "openclaw_qmd"
    OPENCLAW_MEM0 = "openclaw_mem0"


@dataclass
class Fact:
    """A memory fact to be stored."""
    fact_text: str
    fact_type: str = "preference"  # preference, event, relationship, etc.
    importance: int = 5  # 1-10 scale
    entities: List[str] = field(default_factory=list)
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_text": self.fact_text,
            "fact_type": self.fact_type,
            "importance": self.importance,
            "entities": self.entities,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Fact":
        return cls(
            fact_text=data["fact_text"],
            fact_type=data.get("fact_type", "preference"),
            importance=data.get("importance", 5),
            entities=data.get("entities", []),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None,
            metadata=data.get("metadata", {}),
        )


@dataclass
class RetrievedMemory:
    """A retrieved memory with relevance score."""
    fact: Fact
    score: float  # 0.0 - 1.0 relevance
    source_session_id: Optional[str] = None
    retrieval_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact": self.fact.to_dict(),
            "score": self.score,
            "source_session_id": self.source_session_id,
            "retrieval_latency_ms": self.retrieval_latency_ms,
        }


@dataclass
class BackendStats:
    """Statistics from a backend."""
    # Latency metrics
    avg_store_latency_ms: float = 0.0
    p95_store_latency_ms: float = 0.0
    avg_retrieve_latency_ms: float = 0.0
    p95_retrieve_latency_ms: float = 0.0

    # Storage metrics
    total_memories: int = 0
    storage_bytes: int = 0

    # Cost metrics
    tokens_used: int = 0
    cost_estimate_usd: float = 0.0

    # Privacy score (0-100, 100 = fully private)
    privacy_score: int = 0

    # Additional metrics
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_store_latency_ms": self.avg_store_latency_ms,
            "p95_store_latency_ms": self.p95_store_latency_ms,
            "avg_retrieve_latency_ms": self.avg_retrieve_latency_ms,
            "p95_retrieve_latency_ms": self.p95_retrieve_latency_ms,
            "total_memories": self.total_memories,
            "storage_bytes": self.storage_bytes,
            "tokens_used": self.tokens_used,
            "cost_estimate_usd": self.cost_estimate_usd,
            "privacy_score": self.privacy_score,
            "custom_metrics": self.custom_metrics,
        }


class MemoryBackend(ABC):
    """
    Abstract base class for memory backends.

    Every memory system (TotalReclaw, QMD, Mem0) must implement this interface
    to ensure fair apples-to-apples comparison in the benchmark harness.
    """

    @property
    @abstractmethod
    def backend_type(self) -> BackendType:
        """Return the type of this backend."""
        pass

    @property
    @abstractmethod
    def privacy_score(self) -> int:
        """
        Return privacy score (0-100).

        - 100: Fully E2EE, server never sees plaintext (TotalReclaw)
        - 0: All data in plaintext on server (QMD, Mem0)
        """
        pass

    @abstractmethod
    async def store(
        self,
        facts: List[Fact],
        session_id: str,
        user_id: str = "test_user",
    ) -> None:
        """
        Store facts in the memory system.

        Args:
            facts: List of Fact objects to store
            session_id: Current session identifier
            user_id: User identifier (default: test_user for benchmarks)
        """
        pass

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        k: int = 8,
        min_importance: int = 5,
        session_id: Optional[str] = None,
        user_id: str = "test_user",
    ) -> List[RetrievedMemory]:
        """
        Retrieve relevant memories for a query.

        Args:
            query: Natural language query
            k: Number of memories to retrieve
            min_importance: Minimum importance filter (1-10)
            session_id: Optional session context
            user_id: User identifier

        Returns:
            List of RetrievedMemory objects, sorted by relevance
        """
        pass

    @abstractmethod
    async def get_stats(self) -> BackendStats:
        """
        Get statistics from the backend.

        Returns:
            BackendStats with latency, storage, cost, and privacy metrics
        """
        pass

    @abstractmethod
    async def reset(self) -> None:
        """
        Clear all memory for a clean benchmark run.

        This is called between benchmark runs to ensure fair comparison.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verify the backend is responsive.

        Returns:
            True if backend is healthy, False otherwise
        """
        pass

    # Optional hooks for lifecycle events

    async def on_session_start(self, session_id: str, user_id: str) -> None:
        """Called at the start of a session. Optional."""
        pass

    async def on_session_end(self, session_id: str, user_id: str) -> None:
        """Called at the end of a session. Optional."""
        pass

    async def on_pre_compaction(
        self,
        session_id: str,
        user_id: str,
        pending_facts: List[Fact],
    ) -> None:
        """
        Called before context compaction.

        This is the trigger for full extraction and batch upload.
        """
        pass
