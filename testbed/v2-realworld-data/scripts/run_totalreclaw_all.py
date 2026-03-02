#!/usr/bin/env python3
"""
V2 Benchmark Runner - TotalReclaw algorithms only (v0.2, v0.5, v0.6)
"""

import json
import sys
import time
import os
import numpy as np
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
V2_DIR = SCRIPT_DIR.parent
TESTBED_ROOT = V2_DIR.parent
PROJECT_ROOT = TESTBED_ROOT.parent

# Setup sys.path for imports
sys.path.insert(0, str(TESTBED_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# Set PYTHONPATH
os.environ['PYTHONPATH'] = str(TESTBED_ROOT) + ':' + str(PROJECT_ROOT)

print("Importing modules...")
from testbed.totalreclaw_v02_eval import totalreclaw_v02_search
from testbed.totalreclaw_v05_eval import totalreclaw_v05_search
from testbed.totalreclaw_v06_eval import totalreclaw_v06_search
from testbed.src.metrics.precision_recall import (
    calculate_precision_at_k, calculate_recall_at_k, calculate_average_precision
)
from testbed.src.metrics.rank_metrics import (
    calculate_reciprocal_rank, calculate_ndcg, calculate_mean_ndcg
)
from testbed.src.metrics.latency import calculate_latency_statistics
print("  Imports OK")

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


def load_data():
    print("Loading data files...")
    with open(DATA_PATHS["memories"], 'r') as f:
        memories_data = json.load(f)
        documents = [mem["content"] for mem in memories_data["memories"]]

    with open(DATA_PATHS["queries"], 'r') as f:
        queries_data = json.load(f)
        queries = queries_data["queries"]

    with open(DATA_PATHS["ground_truth"], 'r') as f:
        ground_truth = json.load(f)

    embeddings = np.load(DATA_PATHS["embeddings"])

    print(f"  Loaded {len(documents)} documents, {len(queries)} queries")
    print(f"  Embeddings shape: {embeddings.shape}")

    return documents, queries, ground_truth, embeddings


def calculate_ndcg_at_k(ranked_results, relevant, k):
    if not relevant:
        return 0.0
    relevance_scores = {doc_id: 1.0 if doc_id in relevant else 0.0 for doc_id in ranked_results}
    return calculate_ndcg(ranked_results[:k], relevance_scores, k)


def run_algorithm(name, search_fn, queries, documents, embeddings, ground_truth):
    print("\n" + "="*60)
    print(f"Running: {name}")
    print("="*60)

    all_precisions = []
    all_recalls = []
    all_f1s = []
    all_aps = []
    all_rrs = []
    all_ndcgs = []
    latencies = []

    for i, query_obj in enumerate(queries):
        query_id = query_obj["id"]
        query_text = query_obj["text"]
        relevant_docs = ground_truth.get(query_id, [])

        if not relevant_docs:
            continue

        try:
            start_time = time.perf_counter()

            if name == "TotalReclaw-v0.2":
                results = search_fn(query_text, documents, embeddings, EVAL_K)
            elif name == "TotalReclaw-v0.5":
                results = search_fn(query_text, documents, list(range(len(documents))), embeddings, EVAL_K)
            elif name == "TotalReclaw-v0.6":
                results = search_fn(query_text, documents, embeddings, EVAL_K)
            else:
                results = []

            latency_ms = (time.perf_counter() - start_time) * 1000
            latencies.append(latency_ms)

            retrieved_ids = [doc_id for doc_id, _ in results] if results else []

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

            if (i + 1) % 10 == 0:
                print(f"  Processed {i+1}/{len(queries)} queries...")

        except Exception as e:
            print(f"  Error on query {query_id}: {e}")
            import traceback
            traceback.print_exc()
            break

    if not all_precisions:
        print("  No queries processed successfully!")
        return None

    latency_stats = calculate_latency_statistics(latencies)

    aggregate_metrics = {
        "precision_at_5": float(np.mean(all_precisions)),
        "recall_at_5": float(np.mean(all_recalls)),
        "f1_at_5": float(np.mean(all_f1s)),
        "mrr": float(np.mean(all_rrs)),
        "map": float(np.mean(all_aps)),
        "ndcg_at_5": float(np.mean(all_ndcgs)),
        "latency": {
            "p50_ms": latency_stats["p50"],
            "p95_ms": latency_stats["p95"],
            "p99_ms": latency_stats["p99"],
            "mean_ms": latency_stats["mean"],
            "min_ms": latency_stats["min"],
            "max_ms": latency_stats["max"],
        },
        "queries_evaluated": len(all_precisions),
    }

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
    }


def main():
    print("="*80)
    print("V2 BENCHMARK - TotalReclaw v0.2, v0.5, v0.6")
    print("="*80)

    documents, queries, ground_truth, embeddings = load_data()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = {}

    # Run v0.2
    result = run_algorithm("TotalReclaw-v0.2", totalreclaw_v02_search, queries, documents, embeddings, ground_truth)
    if result:
        all_results["totalreclaw_v02"] = result
        with open(RESULTS_DIR / "totalreclaw_v02.json", 'w') as f:
            json.dump(result, f, indent=2)

    # Run v0.5
    result = run_algorithm("TotalReclaw-v0.5", totalreclaw_v05_search, queries, documents, embeddings, ground_truth)
    if result:
        all_results["totalreclaw_v05"] = result
        with open(RESULTS_DIR / "totalreclaw_v05.json", 'w') as f:
            json.dump(result, f, indent=2)

    # Run v0.6
    result = run_algorithm("TotalReclaw-v0.6", totalreclaw_v06_search, queries, documents, embeddings, ground_truth)
    if result:
        all_results["totalreclaw_v06"] = result
        with open(RESULTS_DIR / "totalreclaw_v06.json", 'w') as f:
            json.dump(result, f, indent=2)

    # Print comparison table
    print("\n" + "="*80)
    print("COMPARISON TABLE - TotalReclaw Versions")
    print("="*80)
    print(f"{'Algorithm':<20} {'P@5':<8} {'R@5':<8} {'F1@5':<8} {'MRR':<8} {'MAP':<8} {'NDCG@5':<10} {'p50(ms)':<10}")
    print("-"*80)

    for name, result in all_results.items():
        m = result["aggregate_metrics"]
        display_name = result["algorithm_name"]
        print(
            f"{display_name:<20} "
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
