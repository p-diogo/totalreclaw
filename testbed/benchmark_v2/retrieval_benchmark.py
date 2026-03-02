#!/usr/bin/env python3
"""
Retrieval-Only Benchmark: TotalReclaw E2EE vs Mem0 Platform

Fair comparison: Same 8,727 memories loaded into both systems as raw text.
Same 200 queries. Measures recall@k against ground truth (exact cosine similarity).

This isolates SEARCH QUALITY -- both systems receive the same content.

Backends tested:
1. TotalReclaw E2EE (LSH + client-side rerank) -- privacy=100
2. Mem0 Platform (managed, vector search) -- privacy=0
3. Vector-only baseline (brute-force cosine) -- privacy=0

USAGE:
  # Full benchmark (ingest + query + local baselines):
  python retrieval_benchmark.py

  # Skip Mem0 ingestion (assume already ingested):
  python retrieval_benchmark.py --skip-ingest

  # Only ingest into Mem0 (no benchmarking):
  python retrieval_benchmark.py --ingest-only

  # Skip Mem0 entirely (local baselines only):
  python retrieval_benchmark.py --skip-mem0

IMPORTANT NOTES ON MEM0 BEHAVIOR:
- Mem0 runs LLM extraction on stored text, splitting conversations into
  atomic facts. A single submitted memory may become 0, 1, or many Mem0 memories.
- Mem0 deduplicates across memories. Final count may differ from submitted count.
- We track original memory index via metadata for matching back to ground truth.
- Mem0 has network latency (SaaS). Focus on RECALL, not latency.
- Free tier: 10K memories, 1K searches.
"""

import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from dotenv import load_dotenv

# Load .env
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BASE_DIR = PROJECT_ROOT / "testbed"
PROCESSED_DIR = BASE_DIR / "v2-realworld-data" / "processed"
OUTPUT_DIR = BASE_DIR / "benchmark_v2"


@dataclass
class BenchmarkResult:
    backend_name: str
    recall_at_8: float
    recall_at_20: float
    mrr: float
    avg_latency_ms: float
    p95_latency_ms: float
    privacy_score: int
    total_memories: int
    queries_run: int
    raw_recalls_8: List[float] = field(default_factory=list)
    raw_recalls_20: List[float] = field(default_factory=list)
    raw_latencies: List[float] = field(default_factory=list)
    notes: str = ""


# ---- Data Loading -------------------------------------------------------

def load_memories_and_embeddings():
    """Load all memories and embeddings from processed data."""
    memories = []

    wa_path = PROCESSED_DIR / "whatsapp_memories.json"
    if wa_path.exists():
        with open(wa_path) as f:
            wa_data = json.load(f)
        memories.extend(wa_data.get("memories", []))
        print(f"  Loaded {len(wa_data.get('memories', []))} WhatsApp memories")

    slack_path = PROCESSED_DIR / "slack_memories.json"
    if slack_path.exists():
        with open(slack_path) as f:
            slack_data = json.load(f)
        memories.extend(slack_data.get("memories", []))
        print(f"  Loaded {len(slack_data.get('memories', []))} Slack memories")

    # Load embeddings
    emb_path = PROCESSED_DIR / "combined_embeddings.npy"
    if emb_path.exists():
        embeddings = np.load(emb_path)
    else:
        wa_emb = np.load(PROCESSED_DIR / "embeddings.npy")
        slack_emb_path = PROCESSED_DIR / "slack_embeddings.npy"
        if slack_emb_path.exists():
            slack_emb = np.load(slack_emb_path)
            embeddings = np.vstack([wa_emb, slack_emb])
        else:
            embeddings = wa_emb

    return memories, embeddings


def compute_ground_truth(query_vec, embeddings, k, exclude_idx):
    """Compute true top-k using exact cosine similarity."""
    sims = (embeddings @ query_vec.reshape(-1, 1)).flatten()
    top = np.argsort(sims)[::-1]
    result = set()
    for idx in top:
        if idx != exclude_idx and len(result) < k:
            result.add(int(idx))
    return result


# ---- LSH Index -----------------------------------------------------------

class LSHIndex:
    """Random Hyperplane LSH for approximate nearest neighbor search."""

    def __init__(self, n_bits=64, n_tables=12, seed=42):
        self.n_bits = n_bits
        self.n_tables = n_tables
        self._seed = seed
        self.hyperplanes = []
        self.hash_codes = []

    def build(self, embeddings):
        np.random.seed(self._seed)
        n, dim = embeddings.shape
        self.hyperplanes = [
            np.random.randn(self.n_bits, dim).astype(np.float32)
            for _ in range(self.n_tables)
        ]
        self.hash_codes = []
        for t in range(self.n_tables):
            proj = embeddings @ self.hyperplanes[t].T
            self.hash_codes.append((proj > 0).astype(np.uint8))

    def search(self, query_vec, embeddings, k=3000):
        query = query_vec.reshape(1, -1).astype(np.float32)
        candidates = set()
        k_per = k // self.n_tables + 10
        for t in range(self.n_tables):
            proj = query @ self.hyperplanes[t].T
            qhash = (proj > 0).astype(np.uint8)[0]
            dists = np.sum(qhash != self.hash_codes[t], axis=1)
            top_idx = np.argsort(dists)[:k_per]
            candidates.update(top_idx.tolist())
        return list(candidates)


# ---- Mem0 Platform Backend -----------------------------------------------

class Mem0Benchmark:
    """Wrapper for Mem0 MemoryClient for benchmark use.

    Uses the v2 API (mem0ai 1.0.4+):
    - search() requires filters={"user_id": "..."}
    - get_all() requires filters={"user_id": "..."}
    - add() and delete_all() use user_id= directly
    """

    def __init__(self, api_key: str, user_id: str = "benchmark_retrieval"):
        from mem0 import MemoryClient
        self.client = MemoryClient(api_key=api_key)
        self.user_id = user_id
        self.submit_count = 0

    def reset(self):
        """Delete all memories for benchmark user."""
        print("  Resetting Mem0 (deleting all memories)...")
        try:
            self.client.delete_all(user_id=self.user_id)
        except Exception as e:
            print(f"  Reset warning: {e}")
        self.submit_count = 0

    def get_memory_count(self) -> int:
        """Get current memory count via pagination."""
        try:
            result = self.client.get_all(
                filters={"user_id": self.user_id},
                page=1,
                page_size=1,
            )
            if isinstance(result, dict) and "count" in result:
                return result["count"]
            return len(result.get("results", []))
        except Exception as e:
            print(f"  Count error: {e}")
            return -1

    def ingest_all(self, memories: List[Dict]):
        """Ingest all memories using async mode (fire-and-forget).

        Mem0 async mode queues each memory for background processing.
        Processing includes LLM-based fact extraction and deduplication.
        Final stored count will differ from submitted count.
        """
        total = len(memories)
        errors = 0
        rate_limited = 0
        start_time = time.time()

        for i, mem in enumerate(memories):
            try:
                self.client.add(
                    mem["content"],
                    user_id=self.user_id,
                    metadata={
                        "source": mem.get("source", "benchmark"),
                        "memory_index": mem.get("_index", i),
                    },
                    async_mode=True,
                )
                self.submit_count += 1
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate" in err_str.lower():
                    rate_limited += 1
                    time.sleep(2.0)
                    try:
                        self.client.add(
                            mem["content"],
                            user_id=self.user_id,
                            metadata={
                                "source": mem.get("source", "benchmark"),
                                "memory_index": mem.get("_index", i),
                            },
                            async_mode=True,
                        )
                        self.submit_count += 1
                    except Exception:
                        errors += 1
                elif "quota" in err_str.lower() or "10000" in err_str or "limit" in err_str.lower():
                    print(f"  QUOTA REACHED at index {i}: {e}")
                    break
                else:
                    errors += 1
                    if errors <= 5:
                        print(f"  Store error #{errors} at index {i}: {e}")

            # Progress reporting
            if (i + 1) % 500 == 0 or i + 1 == total:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total - i - 1) / rate if rate > 0 else 0
                print(f"  [{i+1}/{total}] {rate:.1f} mem/s, "
                      f"errors={errors}, rate_limited={rate_limited}, "
                      f"elapsed={elapsed:.0f}s, ETA={eta:.0f}s")

        elapsed = time.time() - start_time
        print(f"  Ingestion complete: {self.submit_count} submitted, "
              f"{errors} errors, {rate_limited} rate limited, "
              f"{elapsed:.0f}s elapsed")
        return self.submit_count, errors

    def search(self, query: str, k: int = 20) -> List[Dict]:
        """Search and return results with scores."""
        try:
            result = self.client.search(
                query,
                filters={"user_id": self.user_id},
                limit=k,
            )
            if isinstance(result, dict):
                return result.get("results", [])
            return result if isinstance(result, list) else []
        except Exception as e:
            print(f"  Search error: {e}")
            return []


# ---- Result Matching -----------------------------------------------------

def extract_memory_indices_from_results(search_results: List[Dict]) -> List[int]:
    """Extract original memory indices from Mem0 search results.

    Uses metadata.memory_index which we stored during ingestion.
    Mem0 may split one memory into multiple, so the same index may appear
    multiple times. We deduplicate by taking first occurrence.
    """
    seen = set()
    indices = []
    for sr in search_results:
        metadata = sr.get("metadata", {}) or {}
        idx = metadata.get("memory_index")
        if idx is not None and isinstance(idx, (int, float)):
            idx = int(idx)
            if idx not in seen:
                seen.add(idx)
                indices.append(idx)
    return indices


# ---- Main Benchmark ------------------------------------------------------

def run_retrieval_benchmark(
    skip_mem0: bool = False,
    skip_ingest: bool = False,
    ingest_only: bool = False,
):
    print("=" * 80)
    print("RETRIEVAL-ONLY BENCHMARK: TotalReclaw E2EE vs Mem0 Platform")
    print("=" * 80)
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if skip_mem0:
        print("  MODE: Skipping Mem0 (local baselines only)")
    elif skip_ingest:
        print("  MODE: Skipping Mem0 ingestion (using existing data)")
    elif ingest_only:
        print("  MODE: Ingestion only (no benchmarking)")

    # ---- Load data ----
    print("\n[1/6] Loading data...")
    memories, embeddings = load_memories_and_embeddings()
    n = min(len(memories), embeddings.shape[0])
    memories = memories[:n]
    embeddings = embeddings[:n]
    embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10)

    for i, m in enumerate(memories):
        m["_index"] = i

    print(f"  Total: {n} memories, {embeddings.shape[1]}d embeddings")

    # ---- Mem0 ingestion (if needed) ----
    api_key = os.environ.get("MEM0_API_KEY")
    mem0 = None
    if not skip_mem0 and api_key:
        mem0 = Mem0Benchmark(api_key=api_key, user_id="benchmark_retrieval_v2")

        if not skip_ingest:
            # Check existing state
            existing_count = mem0.get_memory_count()
            print(f"\n[2/6] Mem0 ingestion...")
            print(f"  Existing memories in Mem0: {existing_count}")

            if existing_count > 100:
                print(f"  Found {existing_count} existing memories. Skipping ingestion.")
                print(f"  (Use --reset to force re-ingestion)")
            else:
                if existing_count > 0:
                    mem0.reset()
                    time.sleep(5)

                print(f"  Ingesting {n} memories (async mode, ~0.5s each)...")
                print(f"  Estimated time: {n * 0.5 / 60:.0f} minutes")
                submitted, errors = mem0.ingest_all(memories)
                print(f"  Submitted: {submitted}, Errors: {errors}")

                # Wait for async processing
                wait_time = 120  # 2 minutes for Mem0 to process async queue
                print(f"  Waiting {wait_time}s for Mem0 async processing...")
                time.sleep(wait_time)

            final_count = mem0.get_memory_count()
            print(f"  Mem0 final memory count: {final_count}")
            print(f"  Dedup/split ratio: {final_count}/{n} = {final_count/n:.2f}x")

        if ingest_only:
            final_count = mem0.get_memory_count()
            print(f"\n  Ingestion complete. Mem0 has {final_count} memories.")
            print(f"  Run without --ingest-only to benchmark.")
            return {}
    elif skip_mem0:
        print("\n[2/6] Skipping Mem0 (--skip-mem0)")
    else:
        print("\n[2/6] Skipping Mem0 (no MEM0_API_KEY)")

    # ---- Build local indices ----
    print("\n[3/6] Building local indices...")
    lsh = LSHIndex(n_bits=64, n_tables=12, seed=42)
    lsh.build(embeddings)
    print(f"  LSH: {lsh.n_tables} tables x {lsh.n_bits} bits")

    # ---- Generate queries + ground truth ----
    n_queries = 200
    np.random.seed(42)
    query_indices = np.random.choice(n, size=min(n_queries, n), replace=False)

    print(f"\n[4/6] Computing ground truth for {len(query_indices)} queries...")
    ground_truth = {}
    for i, idx in enumerate(query_indices):
        qvec = embeddings[idx]
        ground_truth[idx] = {
            "query_text": memories[idx]["content"][:300],
            "true_top_8": compute_ground_truth(qvec, embeddings, 8, idx),
            "true_top_20": compute_ground_truth(qvec, embeddings, 20, idx),
        }
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(query_indices)}")

    results = {}

    # ---- Benchmark: TotalReclaw E2EE (LSH) ----
    print("\n[5/6] Benchmarking TotalReclaw E2EE (LSH + cosine rerank)...")
    om_r8, om_r20, om_lat, om_mrr = [], [], [], []
    for idx in query_indices:
        gt = ground_truth[idx]
        qvec = embeddings[idx]

        start = time.perf_counter()
        candidates = lsh.search(qvec, embeddings, k=3000)
        if idx in candidates:
            candidates.remove(idx)
        cvecs = embeddings[candidates]
        sims = (cvecs @ qvec).flatten()
        sorted_idx = np.argsort(sims)[::-1]
        top_20 = [candidates[i] for i in sorted_idx[:20]]
        latency = (time.perf_counter() - start) * 1000
        om_lat.append(latency)

        r8 = set(top_20[:8])
        om_r8.append(len(r8 & gt["true_top_8"]) / 8)
        r20 = set(top_20)
        om_r20.append(len(r20 & gt["true_top_20"]) / 20)

        for rank, doc_idx in enumerate(top_20):
            if doc_idx in gt["true_top_8"]:
                om_mrr.append(1.0 / (rank + 1))
                break
        else:
            om_mrr.append(0)

    results["totalreclaw"] = BenchmarkResult(
        backend_name="TotalReclaw E2EE",
        recall_at_8=statistics.mean(om_r8),
        recall_at_20=statistics.mean(om_r20),
        mrr=statistics.mean(om_mrr),
        avg_latency_ms=statistics.mean(om_lat),
        p95_latency_ms=sorted(om_lat)[int(len(om_lat) * 0.95)],
        privacy_score=100,
        total_memories=n,
        queries_run=len(query_indices),
        raw_recalls_8=om_r8,
        raw_recalls_20=om_r20,
        raw_latencies=om_lat,
        notes="LSH 64bits x 12tables, 3000 candidates, cosine rerank",
    )
    print(f"  Recall@8={results['totalreclaw'].recall_at_8:.3f}  "
          f"Recall@20={results['totalreclaw'].recall_at_20:.3f}  "
          f"MRR={results['totalreclaw'].mrr:.3f}  "
          f"Latency={results['totalreclaw'].avg_latency_ms:.1f}ms")

    # ---- Benchmark: Mem0 Platform ----
    if mem0 is not None and not skip_mem0:
        print("\n[5b/6] Benchmarking Mem0 Platform (managed, vector search)...")

        mem0_count = mem0.get_memory_count()
        print(f"  Mem0 has {mem0_count} memories stored")

        if mem0_count < 10:
            print(f"  WARNING: Only {mem0_count} memories in Mem0. "
                  f"Results may be unreliable. Run --ingest-only first.")

        mem0_r8, mem0_r20, mem0_lat, mem0_mrr = [], [], [], []
        match_stats = {"with_index": 0, "no_index": 0, "empty_results": 0}

        for qi, idx in enumerate(query_indices):
            gt = ground_truth[idx]
            query_text = gt["query_text"]

            start = time.perf_counter()
            search_results = mem0.search(query_text, k=20)
            latency = (time.perf_counter() - start) * 1000
            mem0_lat.append(latency)

            if not search_results:
                match_stats["empty_results"] += 1
                mem0_r8.append(0.0)
                mem0_r20.append(0.0)
                mem0_mrr.append(0.0)
                continue

            # Extract original memory indices from metadata
            matched_indices = extract_memory_indices_from_results(search_results)
            match_stats["with_index"] += sum(
                1 for sr in search_results
                if (sr.get("metadata") or {}).get("memory_index") is not None
            )
            match_stats["no_index"] += sum(
                1 for sr in search_results
                if (sr.get("metadata") or {}).get("memory_index") is None
            )

            # Compute recall
            r8 = set(matched_indices[:8])
            mem0_r8.append(len(r8 & gt["true_top_8"]) / 8)
            r20 = set(matched_indices[:20])
            mem0_r20.append(len(r20 & gt["true_top_20"]) / 20)

            for rank, doc_idx in enumerate(matched_indices[:20]):
                if doc_idx in gt["true_top_8"]:
                    mem0_mrr.append(1.0 / (rank + 1))
                    break
            else:
                mem0_mrr.append(0)

            if (qi + 1) % 50 == 0:
                avg_r8 = statistics.mean(mem0_r8)
                print(f"  Queried {qi+1}/{len(query_indices)}, "
                      f"running recall@8={avg_r8:.3f}")

        results["mem0"] = BenchmarkResult(
            backend_name="Mem0 Platform",
            recall_at_8=statistics.mean(mem0_r8),
            recall_at_20=statistics.mean(mem0_r20),
            mrr=statistics.mean(mem0_mrr),
            avg_latency_ms=statistics.mean(mem0_lat),
            p95_latency_ms=sorted(mem0_lat)[int(len(mem0_lat) * 0.95)],
            privacy_score=0,
            total_memories=n,
            queries_run=len(query_indices),
            raw_recalls_8=mem0_r8,
            raw_recalls_20=mem0_r20,
            raw_latencies=mem0_lat,
            notes=(f"Managed platform, async ingestion, "
                   f"mem0_stored={mem0_count}, "
                   f"match_stats={match_stats}"),
        )
        print(f"  Recall@8={results['mem0'].recall_at_8:.3f}  "
              f"Recall@20={results['mem0'].recall_at_20:.3f}  "
              f"MRR={results['mem0'].mrr:.3f}  "
              f"Latency={results['mem0'].avg_latency_ms:.1f}ms")
        print(f"  Match stats: {match_stats}")

    # ---- Vector-only baseline ----
    print("\n[6/6] Benchmarking Vector-only baseline...")
    vec_r8, vec_r20, vec_lat, vec_mrr = [], [], [], []
    for idx in query_indices:
        gt = ground_truth[idx]
        qvec = embeddings[idx]
        start = time.perf_counter()
        sims = (embeddings @ qvec).flatten()
        top = np.argsort(sims)[::-1]
        top_20 = [int(i) for i in top if i != idx][:20]
        latency = (time.perf_counter() - start) * 1000
        vec_lat.append(latency)

        r8 = set(top_20[:8])
        vec_r8.append(len(r8 & gt["true_top_8"]) / 8)
        r20 = set(top_20)
        vec_r20.append(len(r20 & gt["true_top_20"]) / 20)

        for rank, doc_idx in enumerate(top_20):
            if doc_idx in gt["true_top_8"]:
                vec_mrr.append(1.0 / (rank + 1))
                break
        else:
            vec_mrr.append(0)

    results["vector_only"] = BenchmarkResult(
        backend_name="Vector-only (baseline)",
        recall_at_8=statistics.mean(vec_r8),
        recall_at_20=statistics.mean(vec_r20),
        mrr=statistics.mean(vec_mrr),
        avg_latency_ms=statistics.mean(vec_lat),
        p95_latency_ms=sorted(vec_lat)[int(len(vec_lat) * 0.95)],
        privacy_score=0,
        total_memories=n,
        queries_run=len(query_indices),
        raw_recalls_8=vec_r8,
        raw_recalls_20=vec_r20,
        raw_latencies=vec_lat,
        notes="Brute-force cosine similarity (perfect recall ceiling)",
    )

    # ---- Print final results ----
    print("\n" + "=" * 80)
    print("FINAL RESULTS -- Retrieval-Only Comparison")
    print("=" * 80)
    print(f"\nDataset: {n} memories (WhatsApp + Slack)")
    print(f"Queries: {len(query_indices)}")
    print(f"Ground truth: exact cosine similarity top-k\n")

    header = (f"{'Backend':<25} {'Recall@8':>10} {'Recall@20':>11} "
              f"{'MRR':>8} {'Latency':>12} {'Privacy':>8}")
    print(header)
    print("-" * 80)
    for name in ["totalreclaw", "mem0", "vector_only"]:
        if name in results:
            r = results[name]
            print(f"{r.backend_name:<25} {r.recall_at_8:>10.3f} "
                  f"{r.recall_at_20:>11.3f} {r.mrr:>8.3f} "
                  f"{r.avg_latency_ms:>8.1f}ms {r.privacy_score:>8}")

    # Head-to-head
    if "totalreclaw" in results and "mem0" in results:
        om = results["totalreclaw"]
        m0 = results["mem0"]
        print(f"\n{'='*50}")
        print("HEAD-TO-HEAD: TotalReclaw vs Mem0")
        print(f"{'='*50}")
        print(f"  Recall@8:  OM {om.recall_at_8:.3f} vs Mem0 {m0.recall_at_8:.3f}  "
              f"(delta: {om.recall_at_8 - m0.recall_at_8:+.3f})")
        print(f"  Recall@20: OM {om.recall_at_20:.3f} vs Mem0 {m0.recall_at_20:.3f}  "
              f"(delta: {om.recall_at_20 - m0.recall_at_20:+.3f})")
        print(f"  MRR:       OM {om.mrr:.3f} vs Mem0 {m0.mrr:.3f}  "
              f"(delta: {om.mrr - m0.mrr:+.3f})")
        print(f"  Privacy:   OM {om.privacy_score} vs Mem0 {m0.privacy_score}")
        print(f"  Latency:   OM {om.avg_latency_ms:.1f}ms vs Mem0 {m0.avg_latency_ms:.1f}ms "
              f"(note: Mem0 includes network RTT)")

    # ---- Save results ----
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "retrieval_benchmark_results.json"
    output = {
        "benchmark_type": "retrieval_only",
        "description": "Same raw text stored in both systems. Measures search quality.",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": {
            "total_memories": n,
            "n_queries": len(query_indices),
            "embedding_dim": int(embeddings.shape[1]),
            "sources": ["whatsapp", "slack"],
        },
        "results": {
            name: {
                "backend_name": r.backend_name,
                "recall_at_8": r.recall_at_8,
                "recall_at_20": r.recall_at_20,
                "mrr": r.mrr,
                "avg_latency_ms": r.avg_latency_ms,
                "p95_latency_ms": r.p95_latency_ms,
                "privacy_score": r.privacy_score,
                "total_memories": r.total_memories,
                "queries_run": r.queries_run,
                "notes": r.notes,
            }
            for name, r in results.items()
        },
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    return results


if __name__ == "__main__":
    skip_mem0 = "--skip-mem0" in sys.argv
    skip_ingest = "--skip-ingest" in sys.argv
    ingest_only = "--ingest-only" in sys.argv

    run_retrieval_benchmark(
        skip_mem0=skip_mem0,
        skip_ingest=skip_ingest,
        ingest_only=ingest_only,
    )
