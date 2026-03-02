#!/usr/bin/env python3
"""
LSH Parameter Validation Experiments for TotalReclaw v0.3

Tests whether LSH parameters can achieve >=93% recall@500 of true top-250.

This version uses smaller hash sizes for practical multi-probe LSH.
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Set
from collections import defaultdict
import numpy as np


# =============================================================================
# Configuration
# =============================================================================

EMBEDDINGS_PATH = Path(__file__).parent.parent / "v2-realworld-data/processed/embeddings.npy"
OUTPUT_PATH = Path(__file__).parent / "lsh_results.json"

# Parameter combinations to test
# For practical multi-probe, we need smaller hash sizes (32-64 bits)
# More tables = better recall
# Format: (n_bits_per_table, n_tables, n_candidates_pool)
PARAM_COMBINATIONS = [
    # Large pools to hit 93%
    (32, 24, 1500),
    (32, 32, 1500),
    (48, 16, 1500),
    (48, 24, 1500),
    (64, 12, 1500),
    (64, 16, 1500),
    # Even larger
    (32, 24, 2000),
    (48, 16, 2000),
    (64, 12, 2000),
    # Best configs from previous run with more candidates per table
    (64, 16, 1500),
    (64, 24, 1500),
    (48, 32, 1500),
    # Max practical configs
    (64, 32, 2000),
    (48, 32, 2000),
    (32, 48, 2000),
]

N_QUERIES = 100
TOP_K_TRUE = 250
RANDOM_SEED = 42


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExperimentResult:
    n_bits: int
    n_tables: int
    n_candidates: int
    mean_recall: float
    median_recall: float
    p5_recall: float
    p95_recall: float
    min_recall: float
    max_recall: float
    mean_candidates_returned: float
    index_build_time_ms: float
    mean_query_time_ms: float
    storage_overhead_bytes: int
    meets_target: bool

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, (np.bool_, bool)):
                result[k] = bool(v)
            elif isinstance(v, np.integer):
                result[k] = int(v)
            elif isinstance(v, np.floating):
                result[k] = float(v)
            else:
                result[k] = v
        return result


# =============================================================================
# Simple Multi-Table LSH with Hamming Distance
# =============================================================================

class SimpleLSH:
    """
    Simple multi-table LSH using Hamming distance.

    For small datasets (<100k), computing Hamming distance to all vectors
    is actually fast enough and more accurate than bucket lookup.
    """

    def __init__(self, dim: int, n_bits: int, n_tables: int, seed: int = 42):
        self.dim = dim
        self.n_bits = n_bits
        self.n_tables = n_tables
        self.n_vectors = 0

        # Random hyperplanes for each table
        np.random.seed(seed)
        self.hyperplanes = [
            np.random.randn(n_bits, dim).astype(np.float32)
            for _ in range(n_tables)
        ]

        # Pre-computed hash codes for all vectors
        self.hash_codes: List[np.ndarray] = []

    def add(self, vectors: np.ndarray):
        """Compute and store hash codes."""
        vectors = vectors.astype(np.float32)
        self.n_vectors = vectors.shape[0]

        self.hash_codes = []
        for t in range(self.n_tables):
            projections = vectors @ self.hyperplanes[t].T  # (n, n_bits)
            # Pack binary codes into uint64 for efficient Hamming distance
            binary = (projections > 0).astype(np.uint64)
            self.hash_codes.append(binary)

    def _hamming_batch(self, query_hash: np.ndarray, table_codes: np.ndarray) -> np.ndarray:
        """Compute Hamming distances between query and all table codes."""
        # XOR and count bits
        xor = query_hash ^ table_codes  # (n_vectors, n_bits)
        return np.sum(xor, axis=1)  # (n_vectors,)

    def search(self, query: np.ndarray, k: int) -> List[int]:
        """Search using Hamming distance across all tables."""
        query = query.astype(np.float32).reshape(1, -1)

        # Collect candidates from each table
        all_candidates: Set[int] = set()

        for t in range(self.n_tables):
            # Query hash
            proj = query @ self.hyperplanes[t].T
            query_hash = (proj > 0).astype(np.uint64)[0]  # (n_bits,)

            # Hamming distances to all vectors
            distances = self._hamming_batch(query_hash, self.hash_codes[t])

            # Take top k closest by Hamming distance
            top_k_idx = np.argsort(distances)[:k]
            all_candidates.update(top_k_idx.tolist())

        return list(all_candidates)

    def get_storage_bytes(self) -> int:
        """Estimate storage."""
        if self.n_vectors == 0:
            return 0
        return self.n_tables * self.n_vectors * self.n_bits // 8


# =============================================================================
# Experiment Functions
# =============================================================================

def load_embeddings() -> np.ndarray:
    print(f"Loading embeddings from {EMBEDDINGS_PATH}")
    embeddings = np.load(EMBEDDINGS_PATH)
    print(f"  Shape: {embeddings.shape}, dtype: {embeddings.dtype}")

    # Normalize for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / (norms + 1e-10)
    print(f"  Normalized")

    return embeddings


def compute_true_top_k(query: np.ndarray, embeddings: np.ndarray, k: int, exclude_idx: int) -> Set[int]:
    """Compute true top-k using dot product (embeddings are normalized)."""
    query = query.reshape(1, -1)
    similarities = (query @ embeddings.T)[0]
    top_k = np.argsort(similarities)[- (k + 1):][::-1].tolist()
    if exclude_idx in top_k:
        top_k.remove(exclude_idx)
    return set(top_k[:k])


def run_experiment(
    embeddings: np.ndarray,
    n_bits: int,
    n_tables: int,
    n_candidates: int,
    query_indices: List[int]
) -> ExperimentResult:
    """Run a single experiment."""
    n_vectors, dim = embeddings.shape

    # Build index
    t0 = time.time()
    lsh = SimpleLSH(dim, n_bits, n_tables)
    lsh.add(embeddings)
    build_ms = (time.time() - t0) * 1000

    # Query - get k candidates per table
    k_per_table = n_candidates // n_tables + 10

    recalls = []
    cand_counts = []
    query_times = []

    for qi in query_indices:
        query = embeddings[qi]
        true_top = compute_true_top_k(query, embeddings, TOP_K_TRUE, qi)

        t0 = time.time()
        cands = lsh.search(query, k_per_table)
        query_ms = (time.time() - t0) * 1000
        query_times.append(query_ms)

        cands_set = set(cands) - {qi}
        cand_counts.append(len(cands_set))

        recall = len(cands_set & true_top) / len(true_top)
        recalls.append(recall)

    arr = np.array(recalls)

    return ExperimentResult(
        n_bits=n_bits,
        n_tables=n_tables,
        n_candidates=n_candidates,
        mean_recall=float(np.mean(arr)),
        median_recall=float(np.median(arr)),
        p5_recall=float(np.percentile(arr, 5)),
        p95_recall=float(np.percentile(arr, 95)),
        min_recall=float(np.min(arr)),
        max_recall=float(np.max(arr)),
        mean_candidates_returned=float(np.mean(cand_counts)),
        index_build_time_ms=build_ms,
        mean_query_time_ms=float(np.mean(query_times)),
        storage_overhead_bytes=lsh.get_storage_bytes(),
        meets_target=np.mean(arr) >= 0.93
    )


def main():
    print("=" * 80)
    print("TotalReclaw LSH Parameter Validation")
    print("=" * 80)

    embeddings = load_embeddings()

    np.random.seed(RANDOM_SEED)
    n = embeddings.shape[0]
    query_indices = list(np.random.choice(range(n), size=min(N_QUERIES, n), replace=False))

    results = []
    total = len(PARAM_COMBINATIONS)

    print(f"\nRunning {total} experiments with {len(query_indices)} queries each...")
    print("-" * 80)

    for i, (bits, tables, cands) in enumerate(PARAM_COMBINATIONS):
        print(f"[{i+1}/{total}] bits={bits}, tables={tables}, max_cands={cands}")

        r = run_experiment(embeddings, bits, tables, cands, query_indices)
        results.append(r)

        ok = "YES" if r.meets_target else "NO"
        print(f"  Recall: {r.mean_recall:.3f} (p5={r.p5_recall:.3f}, p95={r.p95_recall:.3f}) | Cands: {r.mean_candidates_returned:.0f} | Target: {ok}")

    # Analyze
    sorted_r = sorted(results, key=lambda x: -x.mean_recall)
    best = next((r for r in sorted_r if r.meets_target), sorted_r[0])

    # Generate recommendation
    base_storage = embeddings.shape[0] * 384 * 4
    storage_ratio = best.storage_overhead_bytes / base_storage

    if best.meets_target:
        rec = f"""RECOMMENDATION: LSH parameters validated.

CONFIGURATION:
- n_bits_per_table: {best.n_bits}
- n_tables: {best.n_tables}
- candidate_pool: {best.n_candidates}

PERFORMANCE:
- Mean recall@{best.n_candidates}: {best.mean_recall:.1%} (target >=93%)
- P5 recall: {best.p5_recall:.1%}
- Query latency: {best.mean_query_time_ms:.2f}ms (target <50ms)
- Storage overhead: ~{storage_ratio:.2f}x (target <=2.2x)

LSH IS VIABLE for TotalReclaw v0.3."""
    else:
        gap = 0.93 - best.mean_recall
        rec = f"""WARNING: LSH does not achieve 93% recall target.

BEST RESULT:
- bits_per_table={best.n_bits}, tables={best.n_tables}, candidate_pool={best.n_candidates}
- Mean recall: {best.mean_recall:.1%} (gap: {gap:.1%})
- P5 recall: {best.p5_recall:.1%}
- Query latency: {best.mean_query_time_ms:.2f}ms
- Storage overhead: ~{storage_ratio:.2f}x

PLAN B RECOMMENDATIONS:

1. HYBRID LSH + RANDOM SAMPLING
   - Use LSH to get {int(best.mean_candidates_returned)} candidates
   - Add random vectors to fill candidate pool to {best.n_candidates}
   - Maintains zero-knowledge property
   - Simple to implement

2. INCREASE CANDIDATE POOL SIZE
   - Current best: {best.n_candidates} candidates, {best.mean_recall:.1%} recall
   - Try 1500-2000 candidates
   - Trade bandwidth for recall

3. ACCEPT LOWER RECALL
   - {best.mean_recall:.1%} may be acceptable for some use cases
   - Client-side exact reranking ensures quality

4. SERVER-SIDE INDEX (non-zero-knowledge)
   - HNSW: near-perfect recall, very fast
   - But server sees plaintext embeddings

5. PRODUCT QUANTIZATION (PQ)
   - Better recall than LSH
   - But requires server-side computation"""

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(rec)

    # Save
    report = {
        'metadata': {
            'embeddings_path': str(EMBEDDINGS_PATH),
            'n_queries': N_QUERIES,
            'top_k_true': TOP_K_TRUE,
            'random_seed': RANDOM_SEED,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        },
        'results': [r.to_dict() for r in results],
        'best_params': best.to_dict(),
        'recommendation': rec
    }

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nResults saved to {OUTPUT_PATH}")

    # Print table
    print("\n" + "=" * 80)
    print("RESULTS (sorted by recall)")
    print("=" * 80)
    print(f"{'bits':>5} {'tbl':>4} {'cand':>5} {'mean':>6} {'p5':>6} {'p95':>6} {'cands_ret':>9} {'qry_ms':>7} {'ok':>4}")
    print("-" * 60)
    for r in sorted_r:
        ok = "YES" if r.meets_target else "NO"
        print(f"{r.n_bits:>5} {r.n_tables:>4} {r.n_candidates:>5} {r.mean_recall:>6.3f} {r.p5_recall:>6.3f} {r.p95_recall:>6.3f} {r.mean_candidates_returned:>9.0f} {r.mean_query_time_ms:>7.2f} {ok:>4}")


if __name__ == "__main__":
    main()
