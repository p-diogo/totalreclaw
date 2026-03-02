"""LangGraph orchestrator for benchmark simulation.

Implements a conversation replay pipeline that:
1. Loads conversations from dataset
2. Simulates each turn through all backends in parallel
3. Extracts facts at configured intervals
4. Queries memories at configured intervals
5. Evaluates downstream quality with LLM judge
6. Collects metrics for reporting
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from ombh.backends.base import BackendStats, Fact, MemoryBackend, RetrievedMemory
from ombh.dataset.loader import Conversation


class SimulationState(TypedDict):
    """State passed through the simulation graph.

    Using TypedDict for LangGraph compatibility.
    """
    # Input
    conversation: Dict[str, Any]
    backends: Dict[str, MemoryBackend]
    config: Dict[str, Any]

    # Progress tracking
    current_session_idx: int
    current_turn_idx: int
    current_turn: Dict[str, Any]

    # Accumulated results
    extracted_facts: List[Dict[str, Any]]
    retrieval_results: Dict[str, List[RetrievedMemory]]
    judge_scores: Dict[str, float]

    # Metrics
    store_latencies: Dict[str, List[float]]
    retrieve_latencies: Dict[str, List[float]]
    total_memories: Dict[str, int]


def create_initial_state(
    conversation: Conversation,
    backends: Dict[str, MemoryBackend],
    config: Dict[str, Any],
) -> SimulationState:
    """Create initial simulation state."""
    return {
        "conversation": {
            "conversation_id": conversation.conversation_id,
            "sessions": [
                {
                    "session_id": s.get("session_id", f"sess_{i}"),
                    "turns": s.get("turns", []),
                    "pre_compaction_moment": s.get("pre_compaction_moment", False),
                }
                for i, s in enumerate(conversation.sessions)
            ],
            "ground_truth_queries": conversation.ground_truth_queries,
            "metadata": conversation.metadata,
        },
        "backends": backends,
        "config": config,
        "current_session_idx": 0,
        "current_turn_idx": 0,
        "current_turn": {},
        "extracted_facts": [],
        "retrieval_results": {},
        "judge_scores": {},
        "store_latencies": {name: [] for name in backends},
        "retrieve_latencies": {name: [] for name in backends},
        "total_memories": {name: 0 for name in backends},
    }


class BenchmarkOrchestrator:
    """Orchestrates the benchmark simulation using LangGraph."""

    def __init__(
        self,
        backends: Dict[str, MemoryBackend],
        config: Dict[str, Any],
    ):
        self.backends = backends
        self.config = config
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph pipeline."""
        graph = StateGraph(SimulationState)

        # Add nodes
        graph.add_node("load_turn", self._load_turn)
        graph.add_node("process_turn", self._process_turn)
        graph.add_node("extract_facts", self._extract_facts)
        graph.add_node("query_memories", self._query_memories)
        graph.add_node("collect_metrics", self._collect_metrics)

        # Set entry point
        graph.set_entry_point("load_turn")

        # Add edges
        graph.add_edge("load_turn", "process_turn")
        graph.add_edge("process_turn", "extract_facts")
        graph.add_edge("extract_facts", "query_memories")
        graph.add_edge("query_memories", "collect_metrics")

        # Conditional edge: continue to next turn or end
        graph.add_conditional_edges(
            "collect_metrics",
            self._should_continue,
            {
                "continue": "load_turn",
                "end": END,
            }
        )

        return graph.compile()

    async def _load_turn(self, state: SimulationState) -> SimulationState:
        """Load the current turn from conversation."""
        conv = state["conversation"]
        session_idx = state["current_session_idx"]
        turn_idx = state["current_turn_idx"]

        sessions = conv.get("sessions", [])
        if session_idx >= len(sessions):
            return state

        session = sessions[session_idx]
        turns = session.get("turns", [])

        if turn_idx < len(turns):
            state["current_turn"] = turns[turn_idx]
        else:
            state["current_turn"] = {}

        return state

    async def _process_turn(self, state: SimulationState) -> SimulationState:
        """Process the current turn through all backends."""
        turn = state["current_turn"]
        if not turn:
            return state

        session_idx = state["current_session_idx"]
        conv = state["conversation"]
        session = conv.get("sessions", [])[session_idx] if session_idx < len(conv.get("sessions", [])) else {}
        session_id = session.get("session_id", f"sess_{session_idx}")

        # Process through all backends in parallel
        async def process_backend(name: str, backend: MemoryBackend):
            # Call session lifecycle hooks
            if turn_idx == 0:
                await backend.on_session_start(session_id, "test_user")

            # Check for pre-compaction moment
            if session.get("pre_compaction_moment", False) and turn_idx == len(session.get("turns", [])) - 1:
                await backend.on_pre_compaction(session_id, "test_user", [])

            return name

        turn_idx = state["current_turn_idx"]
        tasks = [
            process_backend(name, backend)
            for name, backend in state["backends"].items()
        ]
        await asyncio.gather(*tasks)

        return state

    async def _extract_facts(self, state: SimulationState) -> SimulationState:
        """Extract facts from conversation at configured intervals."""
        turn_idx = state["current_turn_idx"]
        interval = state["config"].get("extraction_interval", 5)

        # Only extract every N turns
        if turn_idx % interval != 0:
            return state

        turn = state["current_turn"]
        if not turn:
            return state

        content = turn.get("content", "")
        if not content:
            return state

        # Simulate fact extraction (in real implementation, use LLM)
        # For now, just create a simple fact from the turn
        fact = {
            "fact_text": content[:200],  # Truncate for demo
            "fact_type": "statement",
            "importance": 5,
            "timestamp": turn.get("timestamp"),
        }

        state["extracted_facts"].append(fact)

        # Store in all backends in parallel
        session_idx = state["current_session_idx"]
        conv = state["conversation"]
        sessions = conv.get("sessions", [])
        session = sessions[session_idx] if session_idx < len(sessions) else {}
        session_id = session.get("session_id", f"sess_{session_idx}")

        async def store_fact(name: str, backend: MemoryBackend):
            start = time.monotonic()
            try:
                await backend.store(
                    [Fact(
                        fact_text=fact["fact_text"],
                        fact_type=fact.get("fact_type", "statement"),
                        importance=fact.get("importance", 5),
                    )],
                    session_id,
                    "test_user"
                )
                latency = (time.monotonic() - start) * 1000
                state["store_latencies"][name].append(latency)
                state["total_memories"][name] += 1
            except Exception as e:
                # Log error but continue
                print(f"Store error in {name}: {e}")

        tasks = [
            store_fact(name, backend)
            for name, backend in state["backends"].items()
        ]
        await asyncio.gather(*tasks)

        return state

    async def _query_memories(self, state: SimulationState) -> SimulationState:
        """Query memories at configured intervals."""
        turn_idx = state["current_turn_idx"]
        interval = state["config"].get("query_interval", 10)
        k = state["config"].get("retrieval_k", 8)

        # Only query every N turns
        if turn_idx % interval != 0:
            return state

        turn = state["current_turn"]
        if not turn:
            return state

        query = turn.get("content", "")
        if not query:
            return state

        # Query all backends in parallel
        async def query_backend(name: str, backend: MemoryBackend):
            start = time.monotonic()
            try:
                results = await backend.retrieve(
                    query,
                    k=k,
                    min_importance=5,
                    user_id="test_user"
                )
                latency = (time.monotonic() - start) * 1000
                state["retrieve_latencies"][name].append(latency)
                state["retrieval_results"][name] = results
            except Exception as e:
                print(f"Query error in {name}: {e}")
                state["retrieval_results"][name] = []

        tasks = [
            query_backend(name, backend)
            for name, backend in state["backends"].items()
        ]
        await asyncio.gather(*tasks)

        return state

    async def _collect_metrics(self, state: SimulationState) -> SimulationState:
        """Collect metrics from all backends."""
        # Metrics are collected inline during store/retrieve
        # This node is for any additional metric collection
        return state

    def _should_continue(self, state: SimulationState) -> str:
        """Determine if simulation should continue to next turn."""
        conv = state["conversation"]
        session_idx = state["current_session_idx"]
        turn_idx = state["current_turn_idx"]

        sessions = conv.get("sessions", [])
        if session_idx >= len(sessions):
            return "end"

        session = sessions[session_idx]
        turns = session.get("turns", [])

        # Move to next turn
        next_turn_idx = turn_idx + 1
        next_session_idx = session_idx

        # Check if we need to move to next session
        if next_turn_idx >= len(turns):
            next_session_idx = session_idx + 1
            next_turn_idx = 0

            # Check if we're done with all sessions
            if next_session_idx >= len(sessions):
                return "end"

        # Update state for next iteration
        state["current_turn_idx"] = next_turn_idx
        state["current_session_idx"] = next_session_idx

        return "continue"

    async def run_conversation(
        self,
        conversation: Conversation,
    ) -> Dict[str, BackendStats]:
        """Run a single conversation through all backends."""
        initial_state = create_initial_state(conversation, self.backends, self.config)

        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)

        # Collect final stats from each backend
        results = {}
        for name, backend in self.backends.items():
            stats = await backend.get_stats()

            # Override with collected metrics
            stats.avg_store_latency_ms = (
                sum(final_state["store_latencies"][name]) / len(final_state["store_latencies"][name])
                if final_state["store_latencies"][name] else 0.0
            )
            stats.avg_retrieve_latency_ms = (
                sum(final_state["retrieve_latencies"][name]) / len(final_state["retrieve_latencies"][name])
                if final_state["retrieve_latencies"][name] else 0.0
            )
            stats.total_memories = final_state["total_memories"][name]

            results[name] = stats

        return results

    async def run_batch(
        self,
        conversations: List[Conversation],
    ) -> Dict[str, List[BackendStats]]:
        """Run multiple conversations."""
        results = {name: [] for name in self.backends.keys()}

        for conv in conversations:
            stats = await self.run_conversation(conv)
            for name, stat in stats.items():
                results[name].append(stat)

        return results

    async def reset_all(self) -> None:
        """Reset all backends for a clean benchmark run."""
        await asyncio.gather(*[
            backend.reset()
            for backend in self.backends.values()
        ])
