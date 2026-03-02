#!/usr/bin/env python3
"""
Baseline Runner Script - v1.0 LLM Ground Truth Comparison

Runs all 4 baseline algorithms against the 150 test queries using LLM ground truth.
Calcululates comprehensive metrics including Precision@5, Recall@5, F1@5, MRR, MAP,
NDCG@5, and latency percentiles (p50/p95/p99).

Outputs unified results to results/baselines.json
"""

import json
import sys
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict

# Add project root to path (parent of testbed)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from testbed.baseline.bm25_only import bm25_only_search
from testbed.baseline.vector_only import vector_only_search
from testbed.baseline.openclaw_hybrid import openclaw_hybrid_search
from testbed.baseline.qmd_hybrid import qmd_hybrid_search

from testbed.src.metrics.precision_recall import (
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_f1,
    calculate_average_precision
)
from testbed.src.metrics.rank_metrics import (
    calculate_reciprocal_rank,
    calculate_ndcg,
    calculate_mrr,
    calculate_mean_ndcg
)
from testbed.src.metrics.latency import calculate_latency_statistics


# ==================== Configuration ====================

# Data paths
TESTBED_DIR = PROJECT_ROOT / "testbed"
DATA_DIR = TESTBED_DIR / "v1.0-llm-gt-comparison" / "data"
RESULTS_DIR = TESTBED_DIR / "v1.0-llm-gt-comparison" / "results"

DATA_PATHS = {
    "memories": DATA_DIR / "memories.json",
    "queries": DATA_DIR / "queries" / "test_queries.json",
    "ground_truth": DATA_DIR / "ground_truth" / "ground_truth_llm.json",
    "embeddings": DATA_DIR / "embeddings.npy",  # Use the copied embeddings
}

OUTPUT_PATH = RESULTS_DIR / "baselines.json"

# Algorithm configurations
ALGORITHMS = {
    "bm25_only": {
        "name": "BM25-Only",
        "func": lambda q, docs, emb, top_k, model: bm25_only_search(q, docs, top_k=top_k),
    },
    "vector_only": {
        "name": "Vector-Only",
        "func": lambda q, docs, emb, top_k, model: vector_only_search(q, emb, top_k=top_k),
    },
    "openclaw_hybrid": {
        "name": "OpenClaw-Hybrid",
        "func": lambda q, docs, emb, top_k, model: openclaw_hybrid_search(q, docs, emb, top_k=top_k, model=model),
    },
    "qmd_hybrid": {
        "name": "QMD-Hybrid",
        "func": lambda q, docs, emb, top_k, model: qmd_hybrid_search(q, docs, emb, top_k=top_k, model=model, use_query_expansion=True, use_reranking=True),
    },
}

EVAL_K = 5  # Top-K for evaluation


# ==================== Data Loading ====================

def load_data() -> Tuple[List[str], List[Dict], Dict[str, Set[int]], np.ndarray]:
    """
    Load all required data files.

    Returns:
        Tuple of (documents, queries, ground_truth, embeddings)
    """
    print("Loading data files...")

    # Load memories
    with open(DATA_PATHS["memories"], 'r') as f:
        memories_data = json.load(f)
        documents = [mem["content"] for mem in memories_data["memories"]]

    # Load queries
    with open(DATA_PATHS["queries"], 'r') as f:
        queries = json.load(f)

    # Load ground truth
    with open(DATA_PATHS["ground_truth"], 'r') as f:
        gt_raw = json.load(f)
        ground_truth = {
            qid: set(data.get("relevant", []))
            for qid, data in gt_raw.items()
        }

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
            # Truncate embeddings to match documents
            embeddings = embeddings[:len(documents)]
            print(f"  Truncated embeddings to {embeddings.shape[0]}")
        else:
            # Generate missing embeddings
            print(f"  Generating embeddings for {len(documents) - embeddings.shape[0]} documents...")
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            new_embs = model.encode(documents[embeddings.shape[0]:], show_progress_bar=True)
            embeddings = np.vstack([embeddings, new_embs])
            print(f"  New embeddings shape: {embeddings.shape}")

    # Ground truth stats
    rel_counts = [len(v) for v in ground_truth.values()]
    print(f"\nGround Truth Statistics:")
    print(f"  Queries with 0 relevant: {sum(1 for c in rel_counts if c == 0)}")
    print(f"  Queries with >0 relevant: {sum(1 for c in rel_counts if c > 0)}")
    print(f"  Avg relevant per query: {np.mean(rel_counts):.1f}")
    print(f"  Total relevant judgments: {sum(rel_counts)}")

    return documents, queries, ground_truth, embeddings


# ==================== Evaluation Functions ====================

def calculate_ndcg_at_k(
    ranked_results: List[int],
    relevant: Set[int],
    k: int
) -> float:
    """Calculate NDCG@k for a single query."""
    if not relevant:
        return 0.0

    # Create relevance scores (binary: 1 for relevant, 0 for not)
    relevance_scores = {doc_id: 1.0 if doc_id in relevant else 0.0 for doc_id in ranked_results}

    # Use the existing rank_metrics calculate_ndcg function
    return calculate_ndcg(ranked_results[:k], relevance_scores, k)


def run_single_algorithm(
    algorithm_id: str,
    algorithm_config: Dict,
    queries: List[Dict],
    documents: List[str],
    embeddings: np.ndarray,
    ground_truth: Dict[str, Set[int]],
    model=None
) -> Dict[str, Any]:
    """
    Run a single algorithm on all queries.

    Returns:
        Dictionary with comprehensive metrics
    """
    print(f"\n{'='*60}")
    print(f"Running: {algorithm_config['name']}")
    print(f"{'='*60}")

    search_func = algorithm_config["func"]

    # Store per-query results
    all_precisions = []
    all_recalls = []
    all_f1s = []
    all_aps = []
    all_rrs = []  # Reciprocal ranks
    all_ndcgs = []
    latencies = []
    per_query_results = {}

    for query_obj in queries:
        query_id = query_obj["id"]
        query_text = query_obj["text"]
        relevant_docs = ground_truth.get(query_id, set())

        # Skip if no ground truth
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
        results = search_func(query_text, documents, embeddings, EVAL_K, model)
        latency_ms = (time.perf_counter() - start_time) * 1000
        latencies.append(latency_ms)

        # Extract just document IDs from results
        retrieved_ids = [doc_id for doc_id, _ in results]

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

        # Store per-query results
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
        "queries_evaluated": len([q for q in queries if ground_truth.get(q["id"], set())]),
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
    print(f"  Latency p95: {aggregate_metrics['latency']['p95_ms']:.2f}ms")
    print(f"  Latency p99: {aggregate_metrics['latency']['p99_ms']:.2f}ms")

    return {
        "algorithm_name": algorithm_config["name"],
        "algorithm_id": algorithm_id,
        "aggregate_metrics": aggregate_metrics,
        "per_query_results": per_query_results,
    }


def run_all_baselines(
    documents: List[str],
    queries: List[Dict],
    ground_truth: Dict[str, Set[int]],
    embeddings: np.ndarray
) -> Dict[str, Any]:
    """
    Run all baseline algorithms and compile results.

    Returns:
        Complete results dictionary ready for JSON output
    """
    print("\n" + "="*80)
    print("BASELINE ALGORITHM EVALUATION")
    print("="*80)
    print(f"Documents: {len(documents)}")
    print(f"Queries: {len(queries)}")
    print(f"Embedding dimension: {embeddings.shape[1]}")
    print(f"Top-K: {EVAL_K}")
    print("="*80)

    # Load embedding model once for vector-based algorithms
    from testbed.baseline.vector_only import _get_embedding_model
    print("\nLoading embedding model...")
    model = _get_embedding_model()

    start_time = time.time()

    # Run each algorithm
    results = {}
    for algo_id, algo_config in ALGORITHMS.items():
        result = run_single_algorithm(
            algorithm_id=algo_id,
            algorithm_config=algo_config,
            queries=queries,
            documents=documents,
            embeddings=embeddings,
            ground_truth=ground_truth,
            model=model
        )
        results[algo_id] = result

    total_time = time.time() - start_time

    # Scenario IDs mapping
    scenario_ids = {
        "bm25_only": "S1_bm25_only",
        "vector_only": "S2_vector_only",
        "openclaw_hybrid": "S3_openclaw_hybrid",
        "qmd_hybrid": "S4_qmd_hybrid",
    }

    # Compile final output with required "scenarios" structure
    output = {
        "scenarios": {},
        "metadata": {
            "testbed_version": "v1.0-llm-gt-comparison",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_evaluation_time_seconds": round(total_time, 2),
            "num_queries": len(queries),
            "num_documents": len(documents),
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dimension": int(embeddings.shape[1]),
            "top_k": EVAL_K,
            "ground_truth_stats": {
                "queries_with_zero_relevant": sum(1 for v in ground_truth.values() if len(v) == 0),
                "queries_with_relevant": sum(1 for v in ground_truth.values() if len(v) > 0),
                "avg_relevant_per_query": float(np.mean([len(v) for v in ground_truth.values()])),
                "total_relevant_judgments": sum(len(v) for v in ground_truth.values()),
            },
        },
    }

    # Add scenarios with algorithm results
    for algo_id, result in results.items():
        scenario_id = scenario_ids[algo_id]
        output["scenarios"][scenario_id] = {
            "name": result["algorithm_name"],
            "algorithm_id": algo_id,
            "results": result["aggregate_metrics"],
        }

    # Print comparison table
    print("\n" + "="*80)
    print("COMPARISON TABLE")
    print("="*80)
    print(f"{'Scenario':<25} {'P@5':<8} {'R@5':<8} {'F1@5':<8} {'MRR':<8} {'MAP':<8} {'NDCG@5':<10} {'p50(ms)':<10}")
    print("-"*80)

    for scenario_id, scenario_data in output["scenarios"].items():
        m = scenario_data["results"]
        print(
            f"{scenario_id + ': ' + scenario_data['name']:<25} "
            f"{m['precision_at_5']:<8.4f} "
            f"{m['recall_at_5']:<8.4f} "
            f"{m['f1_at_5']:<8.4f} "
            f"{m['mrr']:<8.4f} "
            f"{m['map']:<8.4f} "
            f"{m['ndcg_at_5']:<10.4f} "
            f"{m['latency']['p50_ms']:<10.2f}"
        )

    print("="*80)

    return output


def save_results(results: Dict[str, Any], output_path: Path):
    """Save results to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")


# ==================== Main Entry Point ====================

def main():
    """Main entry point for baseline evaluation."""
    print("="*80)
    print("BASELINE RUNNER - v1.0 LLM Ground Truth Comparison")
    print("="*80)

    # Load data
    documents, queries, ground_truth, embeddings = load_data()

    # Run evaluation
    results = run_all_baselines(
        documents=documents,
        queries=queries,
        ground_truth=ground_truth,
        embeddings=embeddings
    )

    # Save results
    save_results(results, OUTPUT_PATH)

    print("\n" + "="*80)
    print("BASELINE EVALUATION COMPLETE")
    print("="*80)


if __name__ == "__main__":
    main()
