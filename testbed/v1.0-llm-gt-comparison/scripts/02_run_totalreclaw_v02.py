#!/usr/bin/env python3
"""
TotalReclaw v0.2 E2EE Runner for v1.0 Testbed

This script runs Scenario S5: TotalReclaw v0.2 E2EE evaluation against all test queries.
It imports from testbed/totalreclaw_v02_eval.py and uses the totalreclaw_v02_search function.

Features:
- Loads data from v1.0-llm-gt-comparison/data/ folder
- Runs TotalReclaw v0.2 E2EE evaluation (Scenario S5)
- Captures detailed timing breakdown using return_timing parameter
- Calculates all metrics (Precision@5, Recall@5, F1@5, MRR, MAP, NDCG@5)
- Outputs results/totalreclaw_v02.json with timing breakdown
"""

import json
import sys
import os
import time
import numpy as np
from typing import List, Tuple, Dict, Set, Any

# Add paths for imports - go up 4 levels: scripts/ -> v1.0-llm-gt-comparison/ -> testbed/ -> totalreclaw/
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, _project_root)

# Import TotalReclaw v0.2 E2EE evaluator
from testbed.totalreclaw_v02_eval import totalreclaw_v02_search, PassTiming

# Import metrics
from testbed.src.metrics.precision_recall import (
    calculate_precision, calculate_recall, calculate_f1, calculate_average_precision
)
from testbed.src.metrics.rank_metrics import (
    calculate_reciprocal_rank, calculate_ndcg
)


def load_data(data_dir: str) -> Tuple[List[str], List[Dict], Dict[str, Set[int]], np.ndarray]:
    """
    Load all required data files.

    Args:
        data_dir: Path to v1.0-llm-gt-comparison/data/ directory

    Returns:
        (documents, queries, ground_truth, embeddings)
    """
    # Load memories
    memories_path = os.path.join(data_dir, 'memories.json')
    if not os.path.exists(memories_path):
        # Try processed folder
        memories_path = os.path.join(data_dir, 'processed/memories_1500_final.json')

    with open(memories_path, 'r') as f:
        data = json.load(f)
        if 'memories' in data:
            memories = data['memories']
        else:
            memories = data

    documents = [mem['content'] for mem in memories]

    # Load queries
    queries_path = os.path.join(data_dir, 'queries/test_queries.json')
    with open(queries_path, 'r') as f:
        queries = json.load(f)

    # Load ground truth
    gt_path = os.path.join(data_dir, 'ground_truth/ground_truth_llm.json')
    with open(gt_path, 'r') as f:
        gt_raw = json.load(f)

    ground_truth = {
        qid: set(qdata['relevant'])
        for qid, qdata in gt_raw.items()
    }

    # Load embeddings
    embeddings_path = os.path.join(data_dir, 'processed/embeddings.npy')
    if os.path.exists(embeddings_path):
        embeddings = np.load(embeddings_path)
    else:
        # Compute embeddings if not available
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Computing embeddings...")
        embeddings = model.encode(documents, show_progress_bar=True)
        # Save for future use
        os.makedirs(os.path.dirname(embeddings_path), exist_ok=True)
        np.save(embeddings_path, embeddings)

    return documents, queries, ground_truth, embeddings


def calculate_metrics(
    retrieved: List[int],
    relevant: Set[int],
    k: int = 5
) -> Dict[str, float]:
    """
    Calculate all metrics for a single query.

    Args:
        retrieved: List of retrieved document IDs
        relevant: Set of relevant document IDs
        k: Top-k value

    Returns:
        Dictionary with all metrics
    """
    precision = calculate_precision(retrieved[:k], relevant)
    recall = calculate_recall(retrieved[:k], relevant)
    f1 = calculate_f1(retrieved[:k], relevant)
    ap = calculate_average_precision(retrieved, relevant)
    rr = calculate_reciprocal_rank(retrieved, relevant)

    # NDCG with binary relevance
    relevance_scores = {doc_id: (1 if doc_id in relevant else 0) for doc_id in retrieved}
    ndcg = calculate_ndcg(retrieved, relevance_scores, k=k)

    return {
        'precision@5': precision,
        'recall@5': recall,
        'f1@5': f1,
        'ap': ap,
        'rr': rr,
        'ndcg@5': ndcg
    }


def run_evaluation(
    documents: List[str],
    queries: List[Dict],
    ground_truth: Dict[str, Set[int]],
    embeddings: np.ndarray,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Run TotalReclaw v0.2 E2EE evaluation on all queries.

    Args:
        documents: List of document strings
        queries: List of query dictionaries
        ground_truth: Dictionary mapping query_id to relevant doc IDs
        embeddings: Pre-computed document embeddings
        top_k: Number of results to return

    Returns:
        Dictionary with all results and timing breakdowns
    """
    results = {
        'query_results': [],
        'aggregate_metrics': {},
        'timing_breakdown': {
            'pass1_knn_ms': [],
            'pass1_blind_check_ms': [],
            'pass2_decrypt_ms': [],
            'pass2_bm25_ms': [],
            'pass2_rrf_ms': [],
            'total_ms': []
        }
    }

    all_precision = []
    all_recall = []
    all_f1 = []
    all_ap = []
    all_rr = []
    all_ndcg = []

    print(f"\n{'='*70}")
    print("Running TotalReclaw v0.2 E2EE Evaluation (Scenario S5)")
    print(f"{'='*70}\n")
    print(f"Documents: {len(documents)}")
    print(f"Queries: {len(queries)}")
    print(f"Top-K: {top_k}\n")

    for i, query in enumerate(queries):
        query_id = query['id']
        query_text = query['text']
        relevant = ground_truth.get(query_id, set())

        # Run search with timing
        search_results, timing = totalreclaw_v02_search(
            query=query_text,
            documents=documents,
            embeddings=embeddings,
            top_k=top_k,
            return_timing=True
        )

        # Extract document IDs
        retrieved = [doc_id for doc_id, _ in search_results]

        # Calculate metrics
        metrics = calculate_metrics(retrieved, relevant, top_k)

        # Store results
        query_result = {
            'query_id': query_id,
            'query_text': query_text,
            'category': query.get('category', 'unknown'),
            'retrieved': retrieved,
            'relevant': sorted(list(relevant)),
            'metrics': metrics,
            'timing': timing.to_dict()
        }
        results['query_results'].append(query_result)

        # Collect timing data
        for key in ['pass1_knn_ms', 'pass1_blind_check_ms', 'pass2_decrypt_ms',
                    'pass2_bm25_ms', 'pass2_rrf_ms', 'total_ms']:
            results['timing_breakdown'][key].append(getattr(timing, key))

        # Collect metrics for aggregation
        all_precision.append(metrics['precision@5'])
        all_recall.append(metrics['recall@5'])
        all_f1.append(metrics['f1@5'])
        all_ap.append(metrics['ap'])
        all_rr.append(metrics['rr'])
        all_ndcg.append(metrics['ndcg@5'])

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(queries)} queries")

    # Calculate aggregate metrics
    results['aggregate_metrics'] = {
        'precision@5': float(np.mean(all_precision)),
        'recall@5': float(np.mean(all_recall)),
        'f1@5': float(np.mean(all_f1)),
        'map': float(np.mean(all_ap)),
        'mrr': float(np.mean(all_rr)),
        'ndcg@5': float(np.mean(all_ndcg))
    }

    # Calculate timing statistics
    for key in list(results['timing_breakdown'].keys()):
        values = results['timing_breakdown'][key]
        if values is not None and isinstance(values, list):
            results['timing_breakdown'][f'{key}_mean'] = float(np.mean(values))
            results['timing_breakdown'][f'{key}_std'] = float(np.std(values))
            results['timing_breakdown'][f'{key}_min'] = float(np.min(values))
            results['timing_breakdown'][f'{key}_max'] = float(np.max(values))
            # Remove the list
            results['timing_breakdown'][key] = None

    return results


def main():
    """Main entry point."""
    # Determine data directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(script_dir), 'data')

    print(f"Data directory: {data_dir}")

    # Load data
    print("\nLoading data...")
    documents, queries, ground_truth, embeddings = load_data(data_dir)
    print(f"  Loaded {len(documents)} documents")
    print(f"  Loaded {len(queries)} queries")
    print(f"  Loaded ground truth for {len(ground_truth)} queries")
    print(f"  Loaded embeddings shape: {embeddings.shape}")

    # Run evaluation
    start_time = time.time()
    results = run_evaluation(documents, queries, ground_truth, embeddings)
    elapsed = time.time() - start_time

    # Add metadata
    results['metadata'] = {
        'scenario': 'S5',
        'algorithm': 'TotalReclaw v0.2 E2EE',
        'description': 'Two-pass search with real AES-GCM encryption: Remote KNN -> Decrypt -> BM25 -> RRF',
        'evaluation_time_seconds': elapsed,
        'total_queries': len(queries),
        'total_documents': len(documents),
        'top_k': 5,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    # Print summary
    print(f"\n{'='*70}")
    print("RESULTS SUMMARY - TotalReclaw v0.2 E2EE (Scenario S5)")
    print(f"{'='*70}\n")

    agg = results['aggregate_metrics']
    print(f"Precision@5:  {agg['precision@5']:.4f}")
    print(f"Recall@5:     {agg['recall@5']:.4f}")
    print(f"F1@5:         {agg['f1@5']:.4f}")
    print(f"MRR:          {agg['mrr']:.4f}")
    print(f"MAP:          {agg['map']:.4f}")
    print(f"NDCG@5:       {agg['ndcg@5']:.4f}")

    print("\nTiming Breakdown:")
    timing = results['timing_breakdown']
    print(f"  Pass 1 KNN:         {timing['pass1_knn_ms_mean']:.2f}ms (std: {timing['pass1_knn_ms_std']:.2f})")
    print(f"  Pass 1 Blind Check: {timing['pass1_blind_check_ms_mean']:.2f}ms (std: {timing['pass1_blind_check_ms_std']:.2f})")
    print(f"  Pass 2 Decrypt:     {timing['pass2_decrypt_ms_mean']:.2f}ms (std: {timing['pass2_decrypt_ms_std']:.2f})")
    print(f"  Pass 2 BM25:        {timing['pass2_bm25_ms_mean']:.2f}ms (std: {timing['pass2_bm25_ms_std']:.2f})")
    print(f"  Pass 2 RRF:         {timing['pass2_rrf_ms_mean']:.2f}ms (std: {timing['pass2_rrf_ms_std']:.2f})")
    print(f"  Total:              {timing['total_ms_mean']:.2f}ms (std: {timing['total_ms_std']:.2f})")

    print(f"\nEvaluation time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")

    # Save results
    results_dir = os.path.join(os.path.dirname(script_dir), 'results')
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, 'totalreclaw_v02.json')

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to: {output_path}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
