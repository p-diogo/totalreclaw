"""
OpenClaw Mem0 Memory Backend Adapter

HTTP client for OpenClaw instance with Mem0 memory backend (localhost:8082).

Mem0 is a memory layer for AI agents that provides persistent, context-aware
memory storage with semantic search capabilities.

Privacy Score: 0 (server sees plaintext - no E2EE)
"""

import time
from typing import Any, Dict, List, Optional

import httpx

from ombh.backends.base import (
    BackendStats,
    BackendType,
    Fact,
    MemoryBackend,
    RetrievedMemory,
)
from ombh.backends.registry import register_backend


@register_backend(BackendType.OPENCLAW_MEM0)
class OpenClawMem0Backend(MemoryBackend):
    """
    HTTP adapter for OpenClaw with Mem0 memory backend.

    Connects to an OpenClaw instance running on localhost:8082 with
    Mem0 integration configured.

    Mem0 provides:
    - Persistent memory storage
    - Semantic search over memories
    - Entity extraction and tracking
    - Memory categories and metadata

    Note: OpenClaw's Mem0 integration is through a plugin that wraps the
    Mem0 API. This adapter expects OpenClaw to expose memory operations
    through HTTP endpoints that proxy to Mem0.

    TODO: Implement actual HTTP endpoints when OpenClaw Mem0 plugin API is available.
    Current implementation uses stub methods with clear documentation of expected
    API contracts based on standard Mem0 API patterns.
    """

    def __init__(self, base_url: str = "http://localhost:8082", timeout: float = 30.0):
        """
        Initialize the OpenClaw Mem0 backend adapter.

        Args:
            base_url: Base URL of the OpenClaw instance with Mem0 (default: localhost:8082)
            timeout: HTTP request timeout in seconds
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

        # Latency tracking
        self._store_latencies: List[float] = []
        self._retrieve_latencies: List[float] = []
        self._total_memories = 0
        self._tokens_used = 0
        self._cost_estimate = 0.0

    @property
    def backend_type(self) -> BackendType:
        """Return the backend type identifier."""
        return BackendType.OPENCLAW_MEM0

    @property
    def privacy_score(self) -> int:
        """
        Return privacy score (0 = no E2EE, server sees plaintext).

        Mem0 stores memory in its backend (local or cloud) without
        client-side encryption. The OpenClaw server and Mem0 have
        full access to all memory content.
        """
        return 0

    async def store(
        self,
        facts: List[Fact],
        session_id: str,
        user_id: str = "test_user",
    ) -> None:
        """
        Store facts in Mem0 through OpenClaw.

        Mem0's native API (v1) typically uses:
        POST /v1/memories
        {
            "messages": [...],  # Conversation messages to extract memories from
            "user_id": "...",
            "metadata": {...}
        }

        Or direct memory addition:
        POST /v1/memories/add
        {
            "memory": "User prefers dark mode",
            "user_id": "...",
            "metadata": {"category": "preference", "importance": 7}
        }

        Expected OpenClaw API contract (TODO: implement when available):
        POST /api/memory/mem0/store
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

        # TODO: Implement actual HTTP call when OpenClaw Mem0 plugin exposes API
        #
        # Expected flow:
        # 1. OpenClaw receives facts via HTTP
        # 2. Plugin calls Mem0 API to store memories
        # 3. Mem0 extracts entities, creates embeddings, stores in vector DB
        #
        # Mem0 supports multiple backends:
        # - Local: SQLite + local embeddings (free)
        # - Cloud: Qdrant/Pinecone + OpenAI embeddings (paid)
        #
        # For benchmark purposes, we assume local mode with:
        # - No API token costs (local embeddings)
        # - Fast storage latency

        # Simulate storage for benchmark purposes
        self._total_memories += len(facts)

        # Mem0 local mode doesn't use external API tokens
        # If using cloud mode, would track tokens here
        # self._tokens_used += estimated_tokens
        # self._cost_estimate += calculated_cost

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
        Retrieve relevant memories using Mem0 search.

        Mem0's native search API:
        POST /v1/memories/search
        {
            "query": "What does the user prefer for UI?",
            "user_id": "...",
            "limit": 10
        }
        Response:
        {
            "results": [
                {
                    "id": "...",
                    "memory": "User prefers dark mode for coding",
                    "user_id": "...",
                    "metadata": {...},
                    "score": 0.85,
                    "created_at": "...",
                    "updated_at": "..."
                },
                ...
            ]
        }

        Expected OpenClaw API contract (TODO: implement when available):
        POST /api/memory/mem0/search
        {
            "query": "...",
            "k": 8,
            "min_importance": 5,
            "session_id": "...",
            "user_id": "..."
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

        # TODO: Implement actual HTTP call when OpenClaw Mem0 plugin exposes API
        #
        # Expected flow:
        # 1. OpenClaw receives search query via HTTP
        # 2. Plugin calls Mem0 search API
        # 3. Mem0 performs vector similarity search
        # 4. Results returned with relevance scores
        #
        # Mem0 search features:
        # - Semantic vector search
        # - Metadata filtering
        # - Entity-based retrieval
        # - Temporal filtering (recent vs older memories)

        results: List[RetrievedMemory] = []

        latency_ms = (time.monotonic() - start_time) * 1000
        self._retrieve_latencies.append(latency_ms)

        # Keep only last 1000 measurements
        if len(self._retrieve_latencies) > 1000:
            self._retrieve_latencies = self._retrieve_latencies[-1000:]

        return results

    async def get_stats(self) -> BackendStats:
        """
        Get statistics from the Mem0 backend.

        Mem0 tracks:
        - Number of stored memories
        - Vector index size
        - API usage (for cloud mode)

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
            storage_bytes=0,  # TODO: Query Mem0 storage size
            tokens_used=self._tokens_used,
            cost_estimate_usd=self._cost_estimate,
            privacy_score=self.privacy_score,
            custom_metrics={
                "backend": "mem0",
                "mode": "local",  # or "cloud" depending on config
                "vector_store": "qdrant",  # or "pinecone", "chroma", etc.
            },
        )

    async def reset(self) -> None:
        """
        Clear all memory for a clean benchmark run.

        Mem0 reset API:
        DELETE /v1/memories?user_id=...
        """
        self._store_latencies.clear()
        self._retrieve_latencies.clear()
        self._total_memories = 0
        self._tokens_used = 0
        self._cost_estimate = 0.0

        # TODO: Implement actual reset via HTTP API
        # Expected endpoint: DELETE /api/memory/mem0/reset
        # Or: DELETE /v1/memories (direct Mem0 API)

    async def health_check(self) -> bool:
        """
        Verify the OpenClaw instance with Mem0 is responsive.

        Checks the health endpoint and optionally Mem0 connectivity.

        Returns:
            True if backend is healthy, False otherwise
        """
        try:
            # OpenClaw uses /health endpoint
            response = await self._client.get(f"{self._base_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    async def on_session_start(self, session_id: str, user_id: str) -> None:
        """
        Called at the start of a session.

        Mem0 can retrieve user context at session start:
        GET /v1/memories?user_id=...
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

        This is an opportunity to extract and store memories from
        the conversation before context is lost.

        Mem0's typical flow:
        1. Receive conversation messages
        2. Extract key facts using LLM
        3. Store as structured memories with metadata
        """
        pass

    async def close(self) -> None:
        """Close the HTTP client connection."""
        await self._client.aclose()


# Mem0-specific data models for reference
# These would be used when implementing the actual API calls

MEM0_MEMORY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "memory": {"type": "string"},
        "user_id": {"type": "string"},
        "agent_id": {"type": "string"},
        "metadata": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "importance": {"type": "integer", "minimum": 1, "maximum": 10},
                "entities": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string"},
            },
        },
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
    },
}

MEM0_SEARCH_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    **MEM0_MEMORY_SCHEMA["properties"],
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}
