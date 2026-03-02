"""LangGraph nodes for the simulation pipeline.

These nodes are used by the orchestrator to process conversations
through the memory backends.
"""

import asyncio
import time
from typing import Any, Dict, List

from ombh.backends.base import Fact, MemoryBackend, RetrievedMemory


class LoadConversationNode:
    """Load conversation data into state."""

    def __init__(self):
        pass

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Load conversation from state (already loaded by orchestrator)."""
        return state


class TurnSimulatorNode:
    """Simulate a single turn in the conversation."""

    def __init__(self, backends: Dict[str, MemoryBackend]):
        self.backends = backends

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process current turn through all backends."""
        turn = state.get("current_turn", {})
        if not turn:
            return state

        session_idx = state.get("current_session_idx", 0)
        conv = state.get("conversation", {})
        sessions = conv.get("sessions", [])
        session = sessions[session_idx] if session_idx < len(sessions) else {}
        session_id = session.get("session_id", f"sess_{session_idx}")
        turn_idx = state.get("current_turn_idx", 0)

        # Call session lifecycle hooks on first turn
        async def call_session_start(name: str, backend: MemoryBackend):
            if turn_idx == 0:
                await backend.on_session_start(session_id, "test_user")

        await asyncio.gather(*[
            call_session_start(name, backend)
            for name, backend in self.backends.items()
        ])

        return state


class ExtractionNode:
    """Extract facts from conversation turn."""

    def __init__(self, interval: int = 5):
        self.interval = interval

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract facts every N turns."""
        turn_idx = state.get("current_turn_idx", 0)

        if turn_idx % self.interval != 0:
            return state

        turn = state.get("current_turn", {})
        content = turn.get("content", "")

        if not content:
            return state

        # Create fact from turn (simplified - real impl uses LLM)
        fact = Fact(
            fact_text=content[:200],
            fact_type="statement",
            importance=5,
        )

        # Store in all backends
        session_idx = state.get("current_session_idx", 0)
        conv = state.get("conversation", {})
        sessions = conv.get("sessions", [])
        session = sessions[session_idx] if session_idx < len(sessions) else {}
        session_id = session.get("session_id", f"sess_{session_idx}")

        latencies = state.get("store_latencies", {})

        async def store_in_backend(name: str, backend: MemoryBackend):
            start = time.monotonic()
            try:
                await backend.store([fact], session_id, "test_user")
                latency = (time.monotonic() - start) * 1000
                if name not in latencies:
                    latencies[name] = []
                latencies[name].append(latency)

                total = state.get("total_memories", {})
                total[name] = total.get(name, 0) + 1
                state["total_memories"] = total
            except Exception as e:
                print(f"Store error in {name}: {e}")

        await asyncio.gather(*[
            store_in_backend(name, backend)
            for name, backend in self.backends.items()
        ])

        state["store_latencies"] = latencies

        # Track extracted facts
        extracted = state.get("extracted_facts", [])
        extracted.append({
            "fact_text": fact.fact_text,
            "turn_idx": turn_idx,
            "session_id": session_id,
        })
        state["extracted_facts"] = extracted

        return state


class QueryNode:
    """Query memories from backends."""

    def __init__(self, interval: int = 10, k: int = 8):
        self.interval = interval
        self.k = k

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Query memories every N turns."""
        turn_idx = state.get("current_turn_idx", 0)

        if turn_idx % self.interval != 0:
            return state

        turn = state.get("current_turn", {})
        query = turn.get("content", "")

        if not query:
            return state

        latencies = state.get("retrieve_latencies", {})
        results = state.get("retrieval_results", {})

        async def query_backend(name: str, backend: MemoryBackend):
            start = time.monotonic()
            try:
                memories = await backend.retrieve(
                    query,
                    k=self.k,
                    min_importance=5,
                    user_id="test_user"
                )
                latency = (time.monotonic() - start) * 1000
                if name not in latencies:
                    latencies[name] = []
                latencies[name].append(latency)
                results[name] = memories
            except Exception as e:
                print(f"Query error in {name}: {e}")
                results[name] = []

        await asyncio.gather(*[
            query_backend(name, backend)
            for name, backend in self.backends.items()
        ])

        state["retrieve_latencies"] = latencies
        state["retrieval_results"] = results

        return state


class DownstreamJudgeNode:
    """Evaluate downstream task quality with LLM."""

    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        self.model = model

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Judge quality of retrieved memories.

        TODO: Implement LLM-based judging.
        For now, use a simple heuristic based on retrieval scores.
        """
        results = state.get("retrieval_results", {})
        scores = state.get("judge_scores", {})

        for name, memories in results.items():
            if not memories:
                scores[name] = 0.0
                continue

            # Simple heuristic: average score of top results
            avg_score = sum(m.score for m in memories[:3]) / min(3, len(memories))
            scores[name] = avg_score * 100  # Convert to 0-100 scale

        state["judge_scores"] = scores
        return state


class MetricsCollectorNode:
    """Collect metrics from all backends."""

    def __init__(self, backends: Dict[str, MemoryBackend]):
        self.backends = backends

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Collect final metrics from backends."""
        # Metrics are collected during store/retrieve operations
        # This node aggregates them for reporting

        metrics = state.get("metrics", {})

        for name in self.backends.keys():
            store_latencies = state.get("store_latencies", {}).get(name, [])
            retrieve_latencies = state.get("retrieve_latencies", {}).get(name, [])

            metrics[name] = {
                "total_stores": len(store_latencies),
                "total_queries": len(retrieve_latencies),
                "avg_store_latency_ms": sum(store_latencies) / len(store_latencies) if store_latencies else 0,
                "avg_retrieve_latency_ms": sum(retrieve_latencies) / len(retrieve_latencies) if retrieve_latencies else 0,
                "total_memories": state.get("total_memories", {}).get(name, 0),
                "judge_score": state.get("judge_scores", {}).get(name, 0),
            }

        state["metrics"] = metrics
        return state


class PreCompactionNode:
    """Handle pre-compaction memory flush."""

    def __init__(self, backends: Dict[str, MemoryBackend]):
        self.backends = backends

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger pre-compaction flush if needed."""
        conv = state.get("conversation", {})
        session_idx = state.get("current_session_idx", 0)
        turn_idx = state.get("current_turn_idx", 0)

        sessions = conv.get("sessions", [])
        if session_idx >= len(sessions):
            return state

        session = sessions[session_idx]
        is_pre_compaction = session.get("pre_compaction_moment", False)
        turns = session.get("turns", [])
        is_last_turn = turn_idx == len(turns) - 1

        if is_pre_compaction and is_last_turn:
            session_id = session.get("session_id", f"sess_{session_idx}")
            pending_facts = [
                Fact(fact_text=f.get("fact_text", ""))
                for f in state.get("extracted_facts", [])
            ]

            await asyncio.gather(*[
                backend.on_pre_compaction(session_id, "test_user", pending_facts)
                for backend in self.backends.values()
            ])

        return state
