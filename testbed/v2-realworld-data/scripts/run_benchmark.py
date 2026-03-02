#!/usr/bin/env python3
"""
V2 Benchmark Runner - TotalReclaw v0.6 Evaluation

Runs all algorithms against the v2 real-world data testbed.
"""

import json
import sys
import time
import os
import numpy as np
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict

# This script is at /Users/pdiogo/Documents/code/totalreclaw/testbed/v2-realworld-data/scripts/
# Need to go up TWO levels to get to testbed/
SCRIPT_DIR = Path(__file__).resolve().parent
V2_DIR = SCRIPT_DIR.parent
TESTBED_ROOT = V2_DIR.parent  # goes up two levels to testbed/
PROJECT_ROOT = TESTBED_ROOT.parent  # goes to totalreclaw/

# Setup sys.path for imports
sys.path.insert(0, str(TESTBED_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# Set PYTHONPATH for subprocess imports
os.environ['PYTHONPATH'] = str(TESTBED_ROOT) + ':' + str(PROJECT_ROOT)

# Now we can import from testbed package
from testbed.baseline.bm25_only import bm25_only_search
from testbed.baseline.vector_only import vector_only_search, _get_embedding_model
from testbed.baseline.openclaw_hybrid import openclaw_hybrid_search
from testbed.baseline.qmd_hybrid import qmd_hybrid_search

# Import TotalReclaw evaluators
from testbed.totalreclaw_v02_eval import totalreclaw_v02_search
from testbed.totalreclaw_v05_eval import totalreclaw_v05_search
from testbed.totalreclaw_v06_eval import totalreclaw_v06_search

# Import metrics
from testbed.src.metrics.precision_recall import (
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_average_precision
)
from testbed.src.metrics.rank_metrics import (
    calculate_reciprocal_rank,
    calculate_ndcg,
    calculate_mrr,
    calculate_mean_ndcg
)
from testbed.src.metrics.latency import calculate_latency_statistics

# Data paths
DATA_DIR = V2_DIR
RESULTS_DIR = V2_DIR / "results"

DATA_PATHS = {
    "memories": DATA_DIR / "processed" / "whatsapp_memories.json",
    "queries": DATA_DIR / "ground_truth" / "test_queries.json",
    "ground_truth": DATA_DIR / "ground_truth" / "ground_truth_eval.json",
    "embeddings": DATA_DIR / "processed" / "embeddings.npy",
}

EVAL_K = 5


def load_data() -> Tuple[List[str], List[Dict], Dict[str, List[int]], np.ndarray]:
    """Load all required data files."""
    print("Loading data files...")

    # Load memories
    with open(DATA_PATHS["memories"], 'r') as f:
        memories_data = json.load(f)
        documents = [mem["content"] for mem in memories_data["memories"]]

    # Load queries
    with open(DATA_PATHS["queries"], 'r') as f:
        queries_data = json.load(f)
        queries = queries_data["queries"]

    # Load ground truth
    with open(DATA_PATHS["ground_truth"], 'r') as f:
        ground_truth = json.load(f)

    # Load embeddings
    embeddings = np.load(DATA_PATHS["embeddings"])

    print(f"  Loaded {len(documents)} documents")
    print(f"  Loaded {len(queries)} queries")
    print(f"  Loaded ground truth for {len(ground_truth)} queries")
    print(f"  Loaded embeddings: shape {embeddings.shape}")

    # Handle embedding mismatch
    if len(documents) != embeddings.shape[0]:
        print(f"\n  WARNING: Embedding count ({embeddings.shape[0]}) != document count ({len(documents)})")
        if embeddings.shape[0] > len(documents):
            embeddings = embeddings[:len(documents)]
            print(f"  Truncated embeddings to {embeddings.shape[0]}")
        else:
            print(f"  Generating embeddings for {len(documents) - embeddings.shape[0]} documents...")
            model = _get_embedding_model()
            new_embs = model.encode(documents[embeddings.shape[0]:], show_progress_bar=True)
            embeddings = np.vstack([embeddings, new_embs])
            print(f"  New embeddings shape: {embeddings.shape}")

    return documents, queries, ground_truth, embeddings


def calculate_ndcg_at_k(ranked_results: List[int], relevant: List[int], k: int) -> float:
    """Calculate NDCG@k for a single query."""
    if not relevant:
        return 0.0

    relevance_scores = {doc_id: 1.0 if doc_id in relevant else 0.0 for doc_id in ranked_results}
    return calculate_ndcg(ranked_results[:k], relevance_scores, k)


def run_algorithm(
    name: str,
    search_func,
    queries: List[Dict],
    documents: List[str],
    embeddings: np.ndarray,
    ground_truth: Dict[str, List[int]],
    model=None
) -> Dict[str, Any]:
    """Run a single algorithm on all queries."""
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"{'='*60}")

    all_precisions = []
    all_recalls = []
    all_f1s = []
    all_aps = []
    all_rrs = []
    all_ndcgs = []
    latencies = []
    per_query_results = {}

    for query_obj in queries:
        query_id = query_obj["id"]
        query_text = query_obj["text"]
        relevant_docs = ground_truth.get(query_id, [])

        if not relevant_docs:
            per_query_results[query_id] = {
                "query": query_text,
                "relevant_count": 0,
                "retrieved": [],
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "ap": 0.0,
                "rr": 0.0,
                "ndcg": 0.0,
                "latency_ms": 0.0,
            }
            continue

        # Run search with timing
        start_time = time.perf_counter()

        # Different algorithms have different signatures
        try:
            if name in ["BM25-Only", "Vector-Only"]:
                results = search_func(query_text, documents, embeddings, EVAL_K)
            elif name in ["OpenClaw-Hybrid", "QMD-Hybrid"]:
                results = search_func(query_text, documents, embeddings, EVAL_K, model)
            elif name == "TotalReclaw-v0.2":
                results = totalreclaw_v02_search(query_text, documents, embeddings, EVAL_K)
            elif name == "TotalReclaw-v0.5":
                results = totalreclaw_v05_search(query_text, documents, list(range(len(documents))), embeddings, EVAL_K)
            elif name == "TotalReclaw-v0.6":
                results = totalreclaw_v06_search(query_text, documents, embeddings, EVAL_K)
            else:
                results = search_func(query_text, documents, embeddings, EVAL_K)
        except Exception as e:
            print(f"  Error on query {query_id}: {e}")
            results = []

        latency_ms = (time.perf_counter() - start_time) * 1000
        latencies.append(latency_ms)

        # Extract document IDs
        retrieved_ids = [doc_id for doc_id, _ in results] if results else []

        # Calculate metrics
        retrieved_set = set(retrieved_ids) if retrieved_ids else set()

        precision = calculate_precision_at_k(retrieved_ids, relevant_docs, EVAL_K)
        recall = calculate_recall_at_k(retrieved_ids, relevant_docs, EVAL_K)
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        ap = calculate_average_precision(retrieved_ids, relevant_docs)
        rr = calculate_reciprocal_rank(retrieved_ids, relevant_docs)
        ndcg = calculate_ndcg_at_k(retrieved_ids, relevant_docs, EVAL_K)

        all_precisions.append(precision)
        all_recalls.append(recall)
        all_f1s.append(f1)
        all_aps.append(ap)
        all_rrs.append(rr)
        all_ndcgs.append(ndcg)

        per_query_results[query_id] = {
            "query": query_text,
            "relevant_count": len(relevant_docs),
            "retrieved": retrieved_ids,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "ap": ap,
            "rr": rr,
            "ndcg": ndcg,
            "latency_ms": latency_ms,
        }

    # Calculate aggregate statistics
    latency_stats = calculate_latency_statistics(latencies)

    aggregate_metrics = {
        "precision_at_5": float(np.mean(all_precisions)) if all_precisions else 0.0,
        "recall_at_5": float(np.mean(all_recalls)) if all_recalls else 0.0,
        "f1_at_5": float(np.mean(all_f1s)) if all_f1s else 0.0,
        "mrr": float(np.mean(all_rrs)) if all_rrs else 0.0,
        "map": float(np.mean(all_aps)) if all_aps else 0.0,
        "ndcg_at_5": float(np.mean(all_ndcgs)) if all_ndcgs else 0.0,
        "latency": {
            "p50_ms": latency_stats["p50"],
            "p95_ms": latency_stats["p95"],
            "p99_ms": latency_stats["p99"],
            "mean_ms": latency_stats["mean"],
            "min_ms": latency_stats["min"],
            "max_ms": latency_stats["max"],
        },
        "queries_evaluated": len([q for q in queries if ground_truth.get(q["id"])]),
    }

    # Print summary
    print(f"\nResults Summary:")
    print(f"  Precision@5: {aggregate_metrics['precision_at_5']:.4f}")
    print(f"  Recall@5:    {aggregate_metrics['recall_at_5']:.4f}")
    print(f"  F1@5:        {aggregate_metrics['f1_at_5']:.4f}")
    print(f"  MRR:         {aggregate_metrics['mrr']:.4f}")
    print(f"  MAP:         {aggregate_metrics['map']:.4f}")
    print(f"  NDCG@5:      {aggregate_metrics['ndcg_at_5']:.4f}")
    print(f"  Latency p50: {aggregate_metrics['latency']['p50_ms']:.2f}ms")

    return {
        "algorithm_name": name,
        "aggregate_metrics": aggregate_metrics,
        "per_query_results": per_query_results,
    }


def save_results(results: Dict[str, Any], output_path: Path):
    """Save results to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")


def main():
    """Main entry point."""
    print("="*80)
    print("V2 BENCHMARK - TotalReclaw v0.6 Evaluation")
    print("="*80)

    # Load data
    documents, queries, ground_truth, embeddings = load_data()

    # Load embedding model
    print("\nLoading embedding model...")
    model = _get_embedding_model()

    # Store all results
    all_results = {}

    # 1. BM25-Only
    result = run_algorithm(
        "BM25-Only",
        lambda q, d, e, k: bm25_only_search(q, d, top_k=k),
        queries, documents, embeddings, ground_truth
    )
    all_results["bm25_only"] = result
    save_results(result, RESULTS_DIR / "baselines_bm25.json")

    # 2. Vector-Only
    result = run_algorithm(
        "Vector-Only",
        lambda q, d, e, k: vector_only_search(q, e, top_k=k),
        queries, documents, embeddings, ground_truth
    )
    all_results["vector_only"] = result
    save_results(result, RESULTS_DIR / "baselines_vector.json")

    # 3. OpenClaw Hybrid
    result = run_algorithm(
        "OpenClaw-Hybrid",
        lambda q, d, e, k, m: openclaw_hybrid_search(q, d, e, top_k=k, model=m),
        queries, documents, embeddings, ground_truth, model
    )
    all_results["openclaw_hybrid"] = result
    save_results(result, RESULTS_DIR / "baselines_openclaw.json")

    # 4. QMD Hybrid
    result = run_algorithm(
        "QMD-Hybrid",
        lambda q, d, e, k, m: qmd_hybrid_search(q, d, e, top_k=k, model=m, use_query_expansion=True, use_reranking=True),
        queries, documents, embeddings, ground_truth, model
    )
    all_results["qmd_hybrid"] = result
    save_results(result, RESULTS_DIR / "baselines_qmd.json")

    # 5. TotalReclaw v0.2
    result = run_algorithm(
        "TotalReclaw-v0.2",
        None,
        queries, documents, embeddings, ground_truth
    )
    all_results["totalreclaw_v02"] = result
    save_results(result, RESULTS_DIR / "totalreclaw_v02.json")

    # 6. TotalReclaw v0.5
    result = run_algorithm(
        "TotalReclaw-v0.5",
        None,
        queries, documents, embeddings, ground_truth
    )
    all_results["totalreclaw_v05"] = result
    save_results(result, RESULTS_DIR / "totalreclaw_v05.json")

    # 7. TotalReclaw v0.6
    result = run_algorithm(
        "TotalReclaw-v0.6",
        None,
        queries, documents, embeddings, ground_truth
    )
    all_results["totalreclaw_v06"] = result
    save_results(result, RESULTS_DIR / "totalreclaw_v06.json")

    # Combine baselines
    baselines_combined = {
        "scenarios": {
            "S1_bm25_only": {
                "name": "BM25-Only",
                "results": all_results["bm25_only"]["aggregate_metrics"],
            },
            "S2_vector_only": {
                "name": "Vector-Only",
                "results": all_results["vector_only"]["aggregate_metrics"],
            },
            "S3_openclaw_hybrid": {
                "name": "OpenClaw-Hybrid",
                "results": all_results["openclaw_hybrid"]["aggregate_metrics"],
            },
            "S4_qmd_hybrid": {
                "name": "QMD-Hybrid",
                "results": all_results["qmd_hybrid"]["aggregate_metrics"],
            },
        },
        "metadata": {
            "testbed_version": "v2-realworld-data",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "num_queries": len(queries),
            "num_documents": len(documents),
        },
    }
    save_results(baselines_combined, RESULTS_DIR / "baselines.json")

    # Print comparison table
    print("\n" + "="*80)
    print("COMPARISON TABLE")
    print("="*80)
    print(f"{'Algorithm':<25} {'P@5':<8} {'R@5':<8} {'F1@5':<8} {'MRR':<8} {'MAP':<8} {'NDCG@5':<10} {'p50(ms)':<10}")
    print("-"*80)

    algorithms = [
        ("BM25-Only", all_results["bm25_only"]),
        ("Vector-Only", all_results["vector_only"]),
        ("OpenClaw-Hybrid", all_results["openclaw_hybrid"]),
        ("QMD-Hybrid", all_results["qmd_hybrid"]),
        ("TotalReclaw-v0.2", all_results["totalreclaw_v02"]),
        ("TotalReclaw-v0.5", all_results["totalreclaw_v05"]),
        ("TotalReclaw-v0.6", all_results["totalreclaw_v06"]),
    ]

    for name, result in algorithms:
        m = result["aggregate_metrics"]
        print(
            f"{name:<25} "
            f"{m['precision_at_5']:<8.4f} "
            f"{m['recall_at_5']:<8.4f} "
            f"{m['f1_at_5']:<8.4f} "
            f"{m['mrr']:<8.4f} "
            f"{m['map']:<8.4f} "
            f"{m['ndcg_at_5']:<10.4f} "
            f"{m['latency']['p50_ms']:<10.2f}"
        )

    print("="*80)
    print("\nBENCHMARK COMPLETE!")


if __name__ == "__main__":
    main()
