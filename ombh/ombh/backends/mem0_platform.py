"""
Mem0 Managed Platform Backend Adapter

Uses the Mem0 MemoryClient SDK (v1.0.4+) to interact with Mem0's managed
platform (app.mem0.ai). This is a REAL implementation -- not a stub.

Privacy Score: 0 (server sees all plaintext -- no E2EE)

API Notes (mem0ai 1.0.4, v2 API):
- search() and get_all() require filters={"user_id": "..."} (not user_id=)
- add() accepts user_id= directly
- delete_all() accepts user_id= directly
- search() returns {"results": [{...}, ...]} with "memory", "score", etc.
- Mem0 rephrases stored text via LLM extraction
- async_mode=False makes add() synchronous (returns result immediately)
"""

import os
import time
from typing import Any, Dict, List, Optional

from ombh.backends.base import (
    BackendStats,
    BackendType,
    Fact,
    MemoryBackend,
    RetrievedMemory,
)
from ombh.backends.registry import register_backend


@register_backend(BackendType.OPENCLAW_MEM0)
class Mem0PlatformBackend(MemoryBackend):
    """
    Real Mem0 managed platform adapter using MemoryClient SDK.

    Requires MEM0_API_KEY environment variable or constructor param.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_id: str = "benchmark_user",
    ):
        self._api_key = api_key or os.environ.get("MEM0_API_KEY")
        if not self._api_key:
            raise ValueError("MEM0_API_KEY required (env var or constructor param)")

        self._user_id = user_id

        # Lazy import to avoid requiring mem0ai unless this adapter is used
        from mem0 import MemoryClient
        self._client = MemoryClient(api_key=self._api_key)

        # Metrics tracking
        self._store_latencies: List[float] = []
        self._retrieve_latencies: List[float] = []
        self._total_memories = 0
        self._total_api_calls = 0

    @property
    def backend_type(self) -> BackendType:
        return BackendType.OPENCLAW_MEM0

    @property
    def privacy_score(self) -> int:
        return 0  # Mem0 sees all plaintext

    async def store(
        self,
        facts: List[Fact],
        session_id: str,
        user_id: str = "benchmark_user",
    ) -> None:
        """Store facts in Mem0 as individual memory strings."""
        uid = user_id or self._user_id

        for fact in facts:
            start = time.monotonic()
            try:
                self._client.add(
                    fact.fact_text,
                    user_id=uid,
                    metadata={
                        "fact_type": fact.fact_type,
                        "importance": fact.importance,
                        "session_id": session_id,
                        "source": "totalreclaw_benchmark",
                    },
                    async_mode=False,  # Synchronous for reliable benchmarking
                )
                self._total_memories += 1
                self._total_api_calls += 1
            except Exception as e:
                print(f"  [Mem0] Store error: {e}")

            latency_ms = (time.monotonic() - start) * 1000
            self._store_latencies.append(latency_ms)

        # Keep rolling window
        if len(self._store_latencies) > 10000:
            self._store_latencies = self._store_latencies[-10000:]

    async def retrieve(
        self,
        query: str,
        k: int = 8,
        min_importance: int = 5,
        session_id: Optional[str] = None,
        user_id: str = "benchmark_user",
    ) -> List[RetrievedMemory]:
        """Search Mem0 and return results mapped to our interface."""
        uid = user_id or self._user_id
        start = time.monotonic()

        try:
            search_result = self._client.search(
                query,
                filters={"user_id": uid},
                limit=k,
            )
            self._total_api_calls += 1
            # v2 API returns {"results": [...]}
            results = search_result.get("results", []) if isinstance(search_result, dict) else search_result
        except Exception as e:
            print(f"  [Mem0] Search error: {e}")
            results = []

        latency_ms = (time.monotonic() - start) * 1000
        self._retrieve_latencies.append(latency_ms)

        if len(self._retrieve_latencies) > 10000:
            self._retrieve_latencies = self._retrieve_latencies[-10000:]

        # Map Mem0 results to our RetrievedMemory format
        memories = []
        for r in results:
            memory_text = r.get("memory", "")
            score = r.get("score", 0.0)
            metadata = r.get("metadata", {}) or {}

            fact = Fact(
                fact_text=memory_text,
                fact_type=metadata.get("fact_type", "unknown"),
                importance=metadata.get("importance", 5),
                entities=[],
                timestamp=None,
                metadata=metadata,
            )
            memories.append(RetrievedMemory(
                fact=fact,
                score=score,
                source_session_id=metadata.get("session_id"),
                retrieval_latency_ms=latency_ms,
            ))

        return memories

    async def get_stats(self) -> BackendStats:
        """Return collected metrics."""
        avg_store = (
            sum(self._store_latencies) / len(self._store_latencies)
            if self._store_latencies else 0.0
        )
        p95_store = (
            sorted(self._store_latencies)[int(len(self._store_latencies) * 0.95)]
            if len(self._store_latencies) >= 20 else avg_store
        )
        avg_retrieve = (
            sum(self._retrieve_latencies) / len(self._retrieve_latencies)
            if self._retrieve_latencies else 0.0
        )
        p95_retrieve = (
            sorted(self._retrieve_latencies)[int(len(self._retrieve_latencies) * 0.95)]
            if len(self._retrieve_latencies) >= 20 else avg_retrieve
        )

        return BackendStats(
            avg_store_latency_ms=avg_store,
            p95_store_latency_ms=p95_store,
            avg_retrieve_latency_ms=avg_retrieve,
            p95_retrieve_latency_ms=p95_retrieve,
            total_memories=self._total_memories,
            storage_bytes=0,  # Not tracked by Mem0 API
            tokens_used=0,
            cost_estimate_usd=0.0,  # Free tier
            privacy_score=self.privacy_score,
            custom_metrics={
                "backend": "mem0_platform",
                "mode": "managed",
                "total_api_calls": self._total_api_calls,
            },
        )

    async def reset(self) -> None:
        """Delete all memories for the benchmark user."""
        try:
            self._client.delete_all(user_id=self._user_id)
        except Exception as e:
            print(f"  [Mem0] Reset error: {e}")

        self._store_latencies.clear()
        self._retrieve_latencies.clear()
        self._total_memories = 0
        self._total_api_calls = 0

    async def health_check(self) -> bool:
        """Verify Mem0 API is reachable by listing memories."""
        try:
            self._client.get_all(filters={"user_id": "health_check_probe"})
            return True
        except Exception:
            return False
