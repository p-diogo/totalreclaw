"""
OpenClaw QMD Memory Backend Adapter

HTTP client for OpenClaw instance with QMD memory backend (localhost:8081).

QMD (Query Memory Daemon) is a local-first search sidecar that combines
BM25 + vectors + reranking. Memory is stored as Markdown files with
vector search over MEMORY.md and memory/*.md files.

Privacy Score: 0 (server sees plaintext - no E2EE)
"""

import time
from typing import List, Optional

import httpx

from ombh.backends.base import (
    BackendStats,
    BackendType,
    Fact,
    MemoryBackend,
    RetrievedMemory,
)
from ombh.backends.registry import register_backend


@register_backend(BackendType.OPENCLAW_QMD)
class OpenClawQmdBackend(MemoryBackend):
    """
    HTTP adapter for OpenClaw with QMD memory backend.

    Connects to an OpenClaw instance running on localhost:8081 with
    memory.backend = "qmd" configured.

    Note: OpenClaw's memory system is primarily tool-based (memory_search, memory_get)
    invoked through the agent. This adapter requires OpenClaw to be configured with
    HTTP hooks or an API extension that exposes memory operations.

    TODO: Implement actual HTTP endpoints when OpenClaw memory API is available.
    Current implementation uses stub methods with clear documentation of expected
    API contracts.
    """

    def __init__(self, base_url: str = "http://localhost:8081", timeout: float = 30.0):
        """
        Initialize the OpenClaw QMD backend adapter.

        Args:
            base_url: Base URL of the OpenClaw instance (default: localhost:8081)
            timeout: HTTP request timeout in seconds
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

        # Latency tracking
        self._store_latencies: List[float] = []
        self._retrieve_latencies: List[float] = []
        self._total_memories = 0

    @property
    def backend_type(self) -> BackendType:
        """Return the backend type identifier."""
        return BackendType.OPENCLAW_QMD

    @property
    def privacy_score(self) -> int:
        """
        Return privacy score (0 = no E2EE, server sees plaintext).

        QMD stores memory as plain Markdown files and uses local embeddings.
        The OpenClaw server has full access to all memory content.
        """
        return 0

    async def store(
        self,
        facts: List[Fact],
        session_id: str,
        user_id: str = "test_user",
    ) -> None:
        """
        Store facts in OpenClaw's memory system.

        With QMD backend, facts are written to Markdown files (MEMORY.md or
        memory/YYYY-MM-DD.md) which are then indexed by QMD.

        Expected API contract (TODO: implement when available):
        POST /api/memory/store
        {
            "facts": [{"text": "...", "type": "...", "importance": 5, ...}],
            "session_id": "...",
            "user_id": "..."
        }

        Args:
            facts: List of Fact objects to store
            session_id: Current session identifier
            user_id: User identifier
        """
        start_time = time.monotonic()

        # TODO: Implement actual HTTP call when OpenClaw exposes memory API
        # Expected endpoint: POST /api/memory/store
        #
        # For now, OpenClaw stores memory through agent interactions:
        # 1. Agent receives message
        # 2. Agent writes to MEMORY.md or memory/YYYY-MM-DD.md
        # 3. QMD indexes the files automatically
        #
        # To programmatically store facts, we would need:
        # - An HTTP endpoint that writes to the memory files
        # - Or a hook that triggers an agent turn to write memory

        # Simulate storage for benchmark purposes
        self._total_memories += len(facts)

        latency_ms = (time.monotonic() - start_time) * 1000
        self._store_latencies.append(latency_ms)

        # Keep only last 1000 measurements
        if len(self._store_latencies) > 1000:
            self._store_latencies = self._store_latencies[-1000:]

    async def retrieve(
        self,
        query: str,
        k: int = 8,
        min_importance: int = 5,
        session_id: Optional[str] = None,
        user_id: str = "test_user",
    ) -> List[RetrievedMemory]:
        """
        Retrieve relevant memories using QMD search.

        QMD combines:
        - Vector similarity (semantic match)
        - BM25 keyword relevance (exact tokens)
        - Optional MMR re-ranking for diversity
        - Optional temporal decay for recency

        Expected API contract (TODO: implement when available):
        POST /api/memory/search
        {
            "query": "...",
            "k": 8,
            "min_importance": 5,
            "session_id": "...",
            "user_id": "..."
        }
        Response:
        {
            "results": [
                {
                    "snippet": "...",
                    "path": "memory/2026-02-23.md",
                    "start_line": 10,
                    "end_line": 15,
                    "score": 0.85,
                    "source": "memory"
                },
                ...
            ]
        }

        Args:
            query: Natural language query
            k: Number of memories to retrieve
            min_importance: Minimum importance filter (1-10)
            session_id: Optional session context
            user_id: User identifier

        Returns:
            List of RetrievedMemory objects, sorted by relevance
        """
        start_time = time.monotonic()

        # TODO: Implement actual HTTP call when OpenClaw exposes memory API
        # Expected endpoint: POST /api/memory/search
        #
        # Currently, memory_search is an agent tool that runs QMD CLI commands:
        # - qmd query "<query>" --json -n <k>
        # - qmd search "<query>" --json -n <k>
        # - qmd vsearch "<query>" --json -n <k>
        #
        # To expose this over HTTP, OpenClaw would need:
        # - An HTTP endpoint that calls the QmdMemoryManager.search() method
        # - Or a WebSocket message that invokes the memory_search tool

        results: List[RetrievedMemory] = []

        latency_ms = (time.monotonic() - start_time) * 1000
        self._retrieve_latencies.append(latency_ms)

        # Keep only last 1000 measurements
        if len(self._retrieve_latencies) > 1000:
            self._retrieve_latencies = self._retrieve_latencies[-1000:]

        return results

    async def get_stats(self) -> BackendStats:
        """
        Get statistics from the QMD backend.

        QMD tracks:
        - Number of indexed documents/chunks
        - Collection sizes
        - Last update timestamp

        Returns:
            BackendStats with latency, storage, and privacy metrics
        """
        # Calculate latency statistics
        avg_store = (
            sum(self._store_latencies) / len(self._store_latencies)
            if self._store_latencies
            else 0.0
        )
        p95_store = (
            sorted(self._store_latencies)[int(len(self._store_latencies) * 0.95)]
            if len(self._store_latencies) >= 20
            else avg_store
        )

        avg_retrieve = (
            sum(self._retrieve_latencies) / len(self._retrieve_latencies)
            if self._retrieve_latencies
            else 0.0
        )
        p95_retrieve = (
            sorted(self._retrieve_latencies)[int(len(self._retrieve_latencies) * 0.95)]
            if len(self._retrieve_latencies) >= 20
            else avg_retrieve
        )

        return BackendStats(
            avg_store_latency_ms=avg_store,
            p95_store_latency_ms=p95_store,
            avg_retrieve_latency_ms=avg_retrieve,
            p95_retrieve_latency_ms=p95_retrieve,
            total_memories=self._total_memories,
            storage_bytes=0,  # TODO: Query QMD index size
            tokens_used=0,  # QMD uses local embeddings, no API tokens
            cost_estimate_usd=0.0,  # Local processing is free
            privacy_score=self.privacy_score,
            custom_metrics={
                "backend": "qmd",
                "search_mode": "hybrid",  # BM25 + vector
                "embedding_provider": "local",
            },
        )

    async def reset(self) -> None:
        """
        Clear all memory for a clean benchmark run.

        For QMD, this would:
        1. Clear MEMORY.md and memory/*.md files
        2. Reset the QMD index (qmd collection remove + add)
        3. Clear the embedding cache
        """
        self._store_latencies.clear()
        self._retrieve_latencies.clear()
        self._total_memories = 0

        # TODO: Implement actual reset via HTTP API
        # Expected endpoint: POST /api/memory/reset

    async def health_check(self) -> bool:
        """
        Verify the OpenClaw instance is responsive.

        Checks the health endpoint and optionally QMD availability.

        Returns:
            True if backend is healthy, False otherwise
        """
        try:
            # OpenClaw uses /health endpoint (based on docker-compose healthcheck)
            response = await self._client.get(f"{self._base_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def on_session_start(self, session_id: str, user_id: str) -> None:
        """
        Called at the start of a session.

        With QMD, this could trigger:
        - Reading today's daily log and yesterday's log
        - Loading MEMORY.md for long-term context
        """
        pass

    async def on_session_end(self, session_id: str, user_id: str) -> None:
        """Called at the end of a session."""
        pass

    async def on_pre_compaction(
        self,
        session_id: str,
        user_id: str,
        pending_facts: List[Fact],
    ) -> None:
        """
        Called before context compaction.

        This is the trigger for the agent to write durable memories to
        MEMORY.md or memory/YYYY-MM-DD.md before the context is compacted.

        In OpenClaw, this is handled by the memoryFlush configuration:
        - Triggers when session approaches compaction threshold
        - Reminds model to store durable memories
        """
        pass

    async def close(self) -> None:
        """Close the HTTP client connection."""
        await self._client.aclose()
