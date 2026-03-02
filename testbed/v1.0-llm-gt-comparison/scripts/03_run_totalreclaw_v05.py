#!/usr/bin/env python3
"""
TotalReclaw v0.5 E2EE Runner for v1.0 Testbed

This script runs Scenarios S6 and S7:
- S6: TotalReclaw v0.5 E2EE (no LLM) - 3-pass without LLM reranking
- S7: TotalReclaw v0.5 E2EE (with LLM) - Full 3-pass with LLM reranking

Features:
- Loads OpenRouter API key from config/api_keys.env
- Uses real LLM via OpenRouter API with model: arcee-ai/trinity-large-preview:free
- Runs two scenarios (with and without LLM reranking)
- Captures timing breakdown for each scenario
- Calculates all metrics (Precision@5, Recall@5, F1@5, MRR, MAP, NDCG@5)
- Outputs results/totalreclaw_v05.json with both scenarios
"""

import json
import sys
import os
import time
import numpy as np
import requests
from typing import List, Tuple, Dict, Set, Any, Optional
from dotenv import load_dotenv

# Add paths for imports - go up 4 levels: scripts/ -> v1.0-llm-gt-comparison/ -> testbed/ -> totalreclaw/
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.insert(0, _project_root)

# Import TotalReclaw v0.5 E2EE evaluator
from testbed.totalreclaw_v05_eval import (
    totalreclaw_v05_search_with_timing,
    V05TimingBreakdown
)

# Import metrics
from testbed.src.metrics.precision_recall import (
    calculate_precision, calculate_recall, calculate_f1, calculate_average_precision
)
from testbed.src.metrics.rank_metrics import (
    calculate_reciprocal_rank, calculate_ndcg
)

# OpenRouter API configuration
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "arcee-ai/trinity-large-preview:free"


def load_openrouter_key() -> Optional[str]:
    """
    Load OpenRouter API key from config/api_keys.env.

    Returns:
        API key string or None if not found
    """
    # Try multiple possible locations for the env file
    env_paths = [
        os.path.join(_project_root, 'config/api_keys.env'),
        os.path.join(_project_root, 'testbed/config/api_keys.env'),
        os.path.join(_project_root, '../config/api_keys.env'),
    ]

    for env_path in env_paths:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            key = os.getenv('OPENROUTER_API_KEY')
            if key:
                return key

    # Fallback: check environment variable directly
    return os.getenv('OPENROUTER_API_KEY')


def call_openrouter_llm(
    query: str,
    documents: List[Tuple[int, str]],
    api_key: str
) -> List[Tuple[int, float]]:
    """
    Call OpenRouter API for LLM reranking.

    Args:
        query: Search query
        documents: List of (doc_id, content) tuples to rerank
        api_key: OpenRouter API key

    Returns:
        List of (doc_id, relevance_score) tuples
    """
    # Build prompt
    doc_list = "\n".join([
        f"[{i}] {doc[:200]}..." if len(doc) > 200 else f"[{i}] {doc}"
        for i, (_, doc) in enumerate(documents)
    ])

    prompt = f"""You are a search result reranker. Given the following query and documents, rank the documents by their relevance to the query.

Query: {query}

Documents:
{doc_list}

Return only a comma-separated list of the most relevant document indices (e.g., "3,1,5,2,4"). Return ALL indices in order of relevance."""

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': OPENROUTER_MODEL,
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.0,
            },
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

        # Extract reranked indices
        content = result['choices'][0]['message']['content'].strip()

        # Parse indices
        try:
            indices = [int(x.strip()) for x in content.split(',')]
        except ValueError:
            # Fallback: extract numbers
            import re
            indices = [int(x) for x in re.findall(r'\d+', content)]

        # Convert to (doc_id, score) format with descending scores
        reranked = []
        for rank, idx in enumerate(indices):
            if 0 <= idx < len(documents):
                doc_id = documents[idx][0]
                score = 1.0 - (rank * 0.01)  # Simple decay scoring
                reranked.append((doc_id, score))

        return reranked

    except Exception as e:
        print(f"  Warning: LLM API call failed: {e}, using original order")
        # Fallback: return original order with simple scoring
        return [(doc_id, 1.0 - i * 0.01) for i, (doc_id, _) in enumerate(documents)]


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


def run_scenario(
    scenario_name: str,
    scenario_id: str,
    use_llm_reranking: bool,
    api_key: Optional[str],
    documents: List[str],
    queries: List[Dict],
    ground_truth: Dict[str, Set[int]],
    embeddings: np.ndarray,
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Run a single scenario evaluation.

    Args:
        scenario_name: Human-readable scenario name
        scenario_id: Scenario identifier (S6 or S7)
        use_llm_reranking: Whether to use LLM reranking
        api_key: OpenRouter API key (required if use_llm_reranking=True)
        documents: List of document strings
        queries: List of query dictionaries
        ground_truth: Dictionary mapping query_id to relevant doc IDs
        embeddings: Pre-computed document embeddings
        top_k: Number of results to return

    Returns:
        Dictionary with all results and timing breakdowns
    """
    results = {
        'scenario_id': scenario_id,
        'scenario_name': scenario_name,
        'use_llm_reranking': use_llm_reranking,
        'query_results': [],
        'aggregate_metrics': {},
        'timing_breakdown': {
            'pass1_knn_ms': [],
            'pass1_blind_check_ms': [],
            'pass2_decrypt_ms': [],
            'pass2_bm25_ms': [],
            'pass2_rrf_ms': [],
            'pass3_llm_rerank_ms': [],
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
    print(f"Running {scenario_name} (Scenario {scenario_id})")
    print(f"{'='*70}\n")
    print(f"Documents: {len(documents)}")
    print(f"Queries: {len(queries)}")
    print(f"Top-K: {top_k}")
    print(f"LLM Reranking: {use_llm_reranking}\n")

    if use_llm_reranking and not api_key:
        print("WARNING: LLM reranking requested but no API key provided!")
        print("Falling back to non-LLM mode...")
        use_llm_reranking = False

    for i, query in enumerate(queries):
        query_id = query['id']
        query_text = query['text']
        relevant = ground_truth.get(query_id, set())

        # Run search with timing
        search_results, timing = totalreclaw_v05_search_with_timing(
            query=query_text,
            docs=documents,
            ids=list(range(len(documents))),
            embeddings=embeddings,
            top_k=top_k,
            use_llm_reranking=use_llm_reranking,
            master_password="test-master-password-v05"
        )

        # If using real LLM reranking, call OpenRouter API
        if use_llm_reranking and api_key:
            # Get top 50 candidates from v0.2 results
            v02_top50 = totalreclaw_v05_search_with_timing(
                query=query_text,
                docs=documents,
                ids=list(range(len(documents))),
                embeddings=embeddings,
                top_k=50,
                use_llm_reranking=False,
                master_password="test-master-password-v05"
            )[0]

            # Prepare documents for reranking
            candidates = [(doc_id, documents[doc_id]) for doc_id, _ in v02_top50]

            # Call LLM API
            t_llm_start = time.perf_counter()
            reranked = call_openrouter_llm(query_text, candidates, api_key)
            t_llm_end = time.perf_counter()

            # Update timing with actual LLM call time
            timing.pass3_llm_rerank_ms = (t_llm_end - t_llm_start) * 1000

            # Take top-k from reranked results
            search_results = reranked[:top_k]

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
                    'pass2_bm25_ms', 'pass2_rrf_ms', 'pass3_llm_rerank_ms', 'total_ms']:
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
        if isinstance(results['timing_breakdown'][key], list):
            values = results['timing_breakdown'][key]
            if values:
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

    # Load OpenRouter API key
    api_key = load_openrouter_key()
    if api_key:
        print(f"OpenRouter API key: {'✓ Found'[:8]}...{api_key[-4:]}")
    else:
        print("Warning: OpenRouter API key not found in config/api_keys.env")
        print("S7 will run without LLM reranking")

    # Load data
    print("\nLoading data...")
    documents, queries, ground_truth, embeddings = load_data(data_dir)
    print(f"  Loaded {len(documents)} documents")
    print(f"  Loaded {len(queries)} queries")
    print(f"  Loaded ground truth for {len(ground_truth)} queries")
    print(f"  Loaded embeddings shape: {embeddings.shape}")

    all_results = {
        'scenarios': {}
    }

    # Run S6: TotalReclaw v0.5 E2EE (no LLM)
    start_s6 = time.time()
    s6_results = run_scenario(
        scenario_name="TotalReclaw v0.5 E2EE (no LLM)",
        scenario_id="S6",
        use_llm_reranking=False,
        api_key=None,
        documents=documents,
        queries=queries,
        ground_truth=ground_truth,
        embeddings=embeddings,
        top_k=5
    )
    s6_elapsed = time.time() - start_s6
    s6_results['evaluation_time_seconds'] = s6_elapsed
    all_results['scenarios']['S6'] = s6_results

    # Run S7: TotalReclaw v0.5 E2EE (with LLM)
    start_s7 = time.time()
    s7_results = run_scenario(
        scenario_name="TotalReclaw v0.5 E2EE (with LLM)",
        scenario_id="S7",
        use_llm_reranking=True,
        api_key=api_key,
        documents=documents,
        queries=queries,
        ground_truth=ground_truth,
        embeddings=embeddings,
        top_k=5
    )
    s7_elapsed = time.time() - start_s7
    s7_results['evaluation_time_seconds'] = s7_elapsed
    all_results['scenarios']['S7'] = s7_results

    # Add metadata
    all_results['metadata'] = {
        'algorithm': 'TotalReclaw v0.5 E2EE',
        'description': 'Three-pass search: Remote KNN -> Decrypt -> BM25 -> RRF -> LLM Rerank',
        'total_queries': len(queries),
        'total_documents': len(documents),
        'top_k': 5,
        'openrouter_model': OPENROUTER_MODEL,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    # Print summary
    print(f"\n{'='*70}")
    print("RESULTS SUMMARY - TotalReclaw v0.5 E2EE")
    print(f"{'='*70}\n")

    for scenario_id, scenario_data in all_results['scenarios'].items():
        agg = scenario_data['aggregate_metrics']
        timing = scenario_data['timing_breakdown']

        print(f"Scenario {scenario_id}: {scenario_data['scenario_name']}")
        print(f"  Precision@5:  {agg['precision@5']:.4f}")
        print(f"  Recall@5:     {agg['recall@5']:.4f}")
        print(f"  F1@5:         {agg['f1@5']:.4f}")
        print(f"  MRR:          {agg['mrr']:.4f}")
        print(f"  MAP:          {agg['map']:.4f}")
        print(f"  NDCG@5:       {agg['ndcg@5']:.4f}")
        print(f"  Timing:")
        if timing.get('pass3_llm_rerank_ms_mean'):
            print(f"    Pass 1 KNN:         {timing['pass1_knn_ms_mean']:.2f}ms")
            print(f"    Pass 2 Decrypt:     {timing['pass2_decrypt_ms_mean']:.2f}ms")
            print(f"    Pass 2 BM25:        {timing['pass2_bm25_ms_mean']:.2f}ms")
            print(f"    Pass 2 RRF:         {timing['pass2_rrf_ms_mean']:.2f}ms")
            print(f"    Pass 3 LLM Rerank:  {timing['pass3_llm_rerank_ms_mean']:.2f}ms")
            print(f"    Total:              {timing['total_ms_mean']:.2f}ms")
        else:
            print(f"    Total:              {timing['total_ms_mean']:.2f}ms")
        print(f"  Eval time:     {scenario_data['evaluation_time_seconds']:.1f}s")
        print()

    print(f"{'='*70}")

    # Save results
    results_dir = os.path.join(os.path.dirname(script_dir), 'results')
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, 'totalreclaw_v05.json')

    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults saved to: {output_path}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
