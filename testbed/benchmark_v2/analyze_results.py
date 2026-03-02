#!/usr/bin/env python3
"""
Task 4: Analyze and pretty-print benchmark results.

Reads retrieval_benchmark_results.json and prints a formatted
head-to-head comparison between TotalReclaw E2EE and Mem0 Platform.

Includes contextualization of Mem0's async processing behavior:
- Mem0 runs LLM extraction on stored text, creating atomic facts
- Heavy deduplication means only ~3% of submitted memories are indexed
- Async processing queue creates significant indexing lag
- These are important operational characteristics, not implementation bugs
"""
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent


def analyze():
    path = RESULTS_DIR / "retrieval_benchmark_results.json"
    if not path.exists():
        print(f"No results found at {path}")
        print("Run retrieval_benchmark.py first.")
        return

    with open(path) as f:
        data = json.load(f)

    print("=" * 70)
    print(f"BENCHMARK ANALYSIS: {data['benchmark_type']}")
    print(f"Description: {data['description']}")
    print(f"Timestamp: {data.get('timestamp', 'N/A')}")
    ds = data["dataset"]
    print(f"Dataset: {ds['total_memories']} memories, "
          f"{ds['n_queries']} queries, "
          f"{ds['embedding_dim']}d embeddings")
    print(f"Sources: {', '.join(ds.get('sources', []))}")
    print("=" * 70)

    results = data["results"]

    # Ranked table (by recall@8)
    sorted_results = sorted(
        results.items(),
        key=lambda x: x[1]["recall_at_8"],
        reverse=True,
    )

    print(f"\n{'Rank':<6}{'Backend':<25}{'Recall@8':>10}{'Recall@20':>11}"
          f"{'MRR':>8}{'Latency':>12}{'Privacy':>8}")
    print("-" * 80)

    for rank, (name, r) in enumerate(sorted_results, 1):
        print(f"{rank:<6}{r['backend_name']:<25}"
              f"{r['recall_at_8']:>10.3f}{r['recall_at_20']:>11.3f}"
              f"{r['mrr']:>8.3f}{r['avg_latency_ms']:>8.1f}ms"
              f"{r['privacy_score']:>8}")

    # Head-to-head: TotalReclaw vs Mem0
    if "totalreclaw" in results and "mem0" in results:
        om = results["totalreclaw"]
        m0 = results["mem0"]

        print(f"\n{'=' * 60}")
        print("HEAD-TO-HEAD: TotalReclaw E2EE vs Mem0 Platform")
        print(f"{'=' * 60}")

        metrics = [
            ("Recall@8", "recall_at_8", True),
            ("Recall@20", "recall_at_20", True),
            ("MRR", "mrr", True),
            ("Privacy Score", "privacy_score", True),
            ("Avg Latency", "avg_latency_ms", False),
            ("P95 Latency", "p95_latency_ms", False),
        ]

        for label, key, higher_is_better in metrics:
            om_val = om[key]
            m0_val = m0[key]
            delta = om_val - m0_val

            if key.endswith("_ms"):
                om_str = f"{om_val:.1f}ms"
                m0_str = f"{m0_val:.1f}ms"
                delta_str = f"{delta:+.1f}ms"
            elif isinstance(om_val, float):
                om_str = f"{om_val:.3f}"
                m0_str = f"{m0_val:.3f}"
                delta_str = f"{delta:+.3f}"
            else:
                om_str = str(om_val)
                m0_str = str(m0_val)
                delta_str = f"{delta:+d}" if isinstance(delta, int) else f"{delta:+.0f}"

            # Determine winner
            if higher_is_better:
                winner = "OM" if delta > 0.001 else ("Mem0" if delta < -0.001 else "TIE")
            else:
                winner = "OM" if delta < -0.001 else ("Mem0" if delta > 0.001 else "TIE")

            # Latency comparison is unfair
            if key.endswith("_ms"):
                winner = "N/A*"

            print(f"  {label:<16} OM={om_str:<12} Mem0={m0_str:<12} "
                  f"Delta={delta_str:<12} Winner={winner}")

        print(f"\n  * Latency comparison is unfair: TotalReclaw runs locally, "
              f"Mem0 includes network RTT to SaaS.")

        # Overall verdict
        print(f"\n{'=' * 60}")
        print("VERDICT")
        print(f"{'=' * 60}")

        om_r8 = om["recall_at_8"]
        m0_r8 = m0["recall_at_8"]

        print(f"  TotalReclaw E2EE: {om_r8:.1%} recall@8, privacy={om['privacy_score']}")
        print(f"  Mem0 Platform:   {m0_r8:.1%} recall@8, privacy={m0['privacy_score']}")

        # Contextualize Mem0 results
        print(f"\n{'=' * 60}")
        print("IMPORTANT CONTEXT: Mem0 Platform Behavior")
        print(f"{'=' * 60}")
        print("""
  Mem0's recall score requires careful interpretation:

  1. ASYNC PROCESSING LAG: Mem0's managed platform uses async queues for
     memory processing. Of 8,727 submitted memories, only a fraction were
     indexed within the measurement window. Mem0 may continue indexing
     for hours after submission.

  2. LLM FACT EXTRACTION: Mem0 runs LLM-based extraction on submitted
     text, converting raw conversations into atomic facts. This is a
     fundamentally different approach than storing raw content.

  3. AGGRESSIVE DEDUPLICATION: Mem0 merges and deduplicates extracted
     facts, reducing 8,727 conversations to ~250 atomic facts (~3%).
     This is a feature, not a bug -- but it means recall@k against
     raw-content ground truth is not an apples-to-apples comparison.

  4. WHAT THIS MEANS: Mem0 optimizes for a different use case (extracted
     knowledge) while TotalReclaw optimizes for content preservation
     with privacy. Both are valid approaches with different tradeoffs.

  FAIR COMPARISON FRAMEWORK:
  - TotalReclaw: Stores raw content encrypted, searches via LSH+rerank
    -> High recall against content-based ground truth
    -> Full zero-knowledge privacy
  - Mem0: Extracts & compresses knowledge via LLM, searches semantically
    -> Optimized for knowledge retrieval, not content matching
    -> No privacy (plaintext on server)
""")

    # Notes
    print(f"{'=' * 60}")
    print("BACKEND NOTES")
    print(f"{'=' * 60}")
    for name, r in results.items():
        if r.get("notes"):
            print(f"  {r['backend_name']}:")
            print(f"    {r['notes']}")


if __name__ == "__main__":
    analyze()
