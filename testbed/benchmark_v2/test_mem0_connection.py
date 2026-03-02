#!/usr/bin/env python3
"""
Task 1: Verify Mem0 API connection and basic operations.

Tests: add, search, get_all, delete_all on the Mem0 managed platform (v2 API).

Key API findings (mem0ai 1.0.4):
- search() and get_all() require filters={"user_id": "..."} (not user_id= directly)
- add() accepts user_id= directly
- delete_all() accepts user_id= directly
- search() returns {"results": [{...}, ...]}
- Mem0 rephrases stored text via LLM extraction
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def test_mem0_connection():
    api_key = os.environ.get("MEM0_API_KEY")
    assert api_key, "MEM0_API_KEY not found in .env"
    assert api_key.startswith("m0-"), f"MEM0_API_KEY should start with 'm0-', got: {api_key[:5]}..."
    print(f"  API key found: {api_key[:8]}...{api_key[-4:]}")

    from mem0 import MemoryClient
    client = MemoryClient(api_key=api_key)

    test_user = "benchmark_connection_test"

    # Cleanup any leftover data from previous runs
    try:
        client.delete_all(user_id=test_user)
    except Exception:
        pass
    time.sleep(3)  # Wait for deletion to propagate

    # Test add (synchronous mode for immediate feedback)
    print("\n[1] Testing add()...")
    result = client.add(
        "Test memory: user prefers Python over JavaScript",
        user_id=test_user,
        metadata={"source": "connection_test", "memory_index": 0},
        async_mode=False,
    )
    print(f"  Add result keys: {list(result.keys())}")
    assert result is not None, "Add returned None"
    assert "results" in result, f"Expected 'results' key, got: {list(result.keys())}"
    print(f"  Memory stored: '{result['results'][0].get('memory', '?')}'")

    # Give Mem0 time to index (async processing on their side)
    print("  Waiting 5s for Mem0 indexing...")
    time.sleep(5)

    # Test search (v2 API requires filters=)
    print("\n[2] Testing search()...")
    search_result = client.search(
        "What programming language does user prefer?",
        filters={"user_id": test_user},
        limit=5,
    )
    print(f"  Search result keys: {list(search_result.keys())}")
    results = search_result.get("results", [])
    print(f"  Search returned {len(results)} results")
    assert len(results) > 0, "Search returned no results"

    first = results[0]
    print(f"  Result keys: {list(first.keys())}")
    assert "memory" in first, f"Missing 'memory' field in result: {list(first.keys())}"
    print(f"  Top result: memory='{first['memory']}', score={first.get('score', 'N/A')}")

    # Test get_all (v2 API requires filters=)
    print("\n[3] Testing get_all()...")
    all_result = client.get_all(filters={"user_id": test_user})
    all_mems = all_result.get("results", [])
    print(f"  get_all returned {len(all_mems)} memories")
    assert len(all_mems) >= 1, f"Expected at least 1 memory, got {len(all_mems)}"

    # Test delete_all
    print("\n[4] Testing delete_all()...")
    client.delete_all(user_id=test_user)
    time.sleep(1)
    remaining = client.get_all(filters={"user_id": test_user})
    remaining_count = len(remaining.get("results", []))
    print(f"  After cleanup: {remaining_count} memories remaining")

    print("\n--- Mem0 connection test PASSED ---")


if __name__ == "__main__":
    test_mem0_connection()
