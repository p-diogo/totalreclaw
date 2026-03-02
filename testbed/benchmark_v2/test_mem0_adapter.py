#!/usr/bin/env python3
"""
Task 2: Test the real Mem0 adapter against the managed platform.

Verifies the Mem0PlatformBackend class implements the MemoryBackend ABC correctly.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Add ombh to path
sys.path.insert(0, str(PROJECT_ROOT / "ombh"))


async def test_mem0_adapter():
    from ombh.backends.mem0_platform import Mem0PlatformBackend
    from ombh.backends.base import Fact, BackendType

    api_key = os.environ["MEM0_API_KEY"]
    test_user = "adapter_test_user"
    backend = Mem0PlatformBackend(api_key=api_key, user_id=test_user)

    # Health check
    print("[1] Health check...")
    healthy = await backend.health_check()
    assert healthy, "Backend not healthy"
    print("  PASSED")

    # Reset (clean slate)
    print("\n[2] Reset...")
    await backend.reset()
    time.sleep(2)  # Wait for deletion to propagate
    print("  PASSED")

    # Store facts
    print("\n[3] Store facts...")
    facts = [
        Fact(fact_text="User prefers Python over JavaScript", fact_type="preference", importance=8),
        Fact(fact_text="User lives in Lisbon, Portugal", fact_type="personal", importance=7),
        Fact(fact_text="User is building an encrypted memory system called TotalReclaw", fact_type="project", importance=9),
    ]
    await backend.store(facts, session_id="test_session", user_id=test_user)
    print(f"  Stored {len(facts)} facts")

    # Allow Mem0 indexing time
    print("  Waiting 5s for Mem0 indexing...")
    time.sleep(5)

    # Retrieve
    print("\n[4] Retrieve...")
    results = await backend.retrieve(
        "What programming language does the user prefer?",
        k=3,
        user_id=test_user,
    )
    assert len(results) > 0, "No results returned"
    print(f"  Retrieved {len(results)} results")
    for r in results:
        print(f"    score={r.score:.3f}: {r.fact.fact_text}")

    # Verify top result is about Python
    top_text = results[0].fact.fact_text.lower()
    assert "python" in top_text, f"Expected Python in top result, got: {top_text}"
    print("  Top result contains 'python' -- PASSED")

    # Test another query
    print("\n[5] Retrieve (location query)...")
    results2 = await backend.retrieve(
        "Where does the user live?",
        k=3,
        user_id=test_user,
    )
    assert len(results2) > 0, "No results returned for location query"
    top_text2 = results2[0].fact.fact_text.lower()
    assert "lisbon" in top_text2 or "portugal" in top_text2, \
        f"Expected Lisbon/Portugal in top result, got: {top_text2}"
    print(f"  Top result: {results2[0].fact.fact_text} -- PASSED")

    # Stats
    print("\n[6] Stats...")
    stats = await backend.get_stats()
    print(f"  total_memories={stats.total_memories}")
    print(f"  avg_store_latency={stats.avg_store_latency_ms:.1f}ms")
    print(f"  avg_retrieve_latency={stats.avg_retrieve_latency_ms:.1f}ms")
    print(f"  privacy_score={stats.privacy_score}")
    assert stats.total_memories == 3, f"Expected 3 memories, got {stats.total_memories}"
    assert stats.privacy_score == 0, "Mem0 should have privacy_score=0"
    print("  PASSED")

    # Backend type
    print("\n[7] Backend type...")
    assert backend.backend_type == BackendType.OPENCLAW_MEM0
    print(f"  backend_type={backend.backend_type.value} -- PASSED")

    # Cleanup
    print("\n[8] Cleanup...")
    await backend.reset()
    print("  PASSED")

    print("\n--- All Mem0 adapter tests PASSED ---")


if __name__ == "__main__":
    asyncio.run(test_mem0_adapter())
