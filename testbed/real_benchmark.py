#!/usr/bin/env python3
"""
Real Benchmark for TotalReclaw vs Baselines

Uses actual WhatsApp/Slack data with real embeddings.
Compares: TotalReclaw E2EE (LSH), BM25-only, Vector-only, Hybrid (BM25+Vector+RRF)

Outputs recall@k metrics, latency, and storage comparisons.
"""

import json
import math
import random
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

BASE_DIR = Path(__file__).parent
PROCESSED_DIR = BASE_DIR / "v2-realworld-data" / "processed"


@dataclass
class BenchmarkResult:
    backend_name: str
    recall_at_8: float
    recall_at_20: float
    recall_at_100: float
    mrr: float
    avg_latency_ms: float
    p95_latency_ms: float
    storage_bytes: int
    privacy_score: int
    total_memories: int
    queries_run: int
    raw_recalls: List[float] = field(default_factory=list)
    raw_latencies: List[float] = field(default_factory=list)


def simple_tokenize(text: str) -> List[str]:
    """Simple tokenization for BM25."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = text.split()
    return [t for t in tokens if len(t) >= 2]


def load_memories_and_embeddings():
    """Load all memories and embeddings from processed data."""
    memories = []

    wa_path = PROCESSED_DIR / "whatsapp_memories.json"
    if wa_path.exists():
        with open(wa_path) as f:
            wa_data = json.load(f)
        memories.extend(wa_data.get("memories", []))
        print(f"Loaded {len(wa_data.get('memories', []))} WhatsApp memories")

    slack_path = PROCESSED_DIR / "slack_memories.json"
    if slack_path.exists():
        with open(slack_path) as f:
            slack_data = json.load(f)
        memories.extend(slack_data.get("memories", []))
        print(f"Loaded {len(slack_data.get('memories', []))} Slack memories")

    emb_path = PROCESSED_DIR / "combined_embeddings.npy"
    if emb_path.exists():
        embeddings = np.load(emb_path)
        print(f"Loaded combined embeddings: {embeddings.shape}")
    else:
        wa_emb = np.load(PROCESSED_DIR / "embeddings.npy")
        slack_emb_path = PROCESSED_DIR / "slack_embeddings.npy"
        if slack_emb_path.exists():
            slack_emb = np.load(slack_emb_path)
            embeddings = np.vstack([wa_emb, slack_emb])
        else:
            embeddings = wa_emb
        print(f"Combined embeddings: {embeddings.shape}")

    return memories, embeddings


def compute_true_top_k(
    query_vec: np.ndarray, embeddings: np.ndarray, k: int, exclude_idx: int
) -> Set[int]:
    """Compute true top-k using cosine similarity."""
    similarities = (embeddings @ query_vec.reshape(-1, 1)).flatten()
    top_indices = np.argsort(similarities)[::-1]
    result = set()
    for idx in top_indices:
        if idx != exclude_idx and len(result) < k:
            result.add(int(idx))
    return result


class BM25Index:
    """Simple BM25 implementation."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avg_doc_length = 0.0
        self.doc_lengths: List[int] = []
        self.term_doc_freqs: Dict[str, int] = {}
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.doc_ids: List[int] = []

    def index(self, documents: List[Tuple[int, str]]):
        """Index documents."""
        self.doc_count = len(documents)
        self.doc_ids = [doc_id for doc_id, _ in documents]
        self.doc_lengths = []
        self.doc_term_freqs = []
        self.term_doc_freqs = {}

        total_length = 0
        term_seen: Dict[str, Set[int]] = {}

        for doc_id, text in documents:
            tokens = simple_tokenize(text)
            self.doc_lengths.append(len(tokens))
            total_length += len(tokens)

            term_freqs: Dict[str, int] = {}
            for token in tokens:
                term_freqs[token] = term_freqs.get(token, 0) + 1
                if token not in term_seen:
                    term_seen[token] = set()
                term_seen[token].add(doc_id)

            self.doc_term_freqs.append(term_freqs)

        self.avg_doc_length = total_length / self.doc_count if self.doc_count > 0 else 0

        for term, doc_set in term_seen.items():
            self.term_doc_freqs[term] = len(doc_set)

    def _idf(self, term: str) -> float:
        df = self.term_doc_freqs.get(term, 0)
        if df == 0:
            return 0
        return math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)

    def search(self, query: str, top_k: int = 20) -> List[Tuple[int, float]]:
        """Search for query."""
        query_terms = simple_tokenize(query)
        scores = []

        for i, term_freqs in enumerate(self.doc_term_freqs):
            score = 0.0
            doc_length = self.doc_lengths[i]

            for term in query_terms:
                tf = term_freqs.get(term, 0)
                if tf == 0:
                    continue

                idf = self._idf(term)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * (doc_length / self.avg_doc_length)
                    if self.avg_doc_length > 0
                    else 1
                )
                score += idf * (numerator / denominator)

            if score > 0:
                scores.append((self.doc_ids[i], score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class LSHIndex:
    """Random Hyperplane LSH for approximate nearest neighbor search."""

    def __init__(self, n_bits: int = 64, n_tables: int = 12, seed: int = 42):
        self.n_bits = n_bits
        self.n_tables = n_tables
        self.hyperplanes: List[np.ndarray] = []
        self.hash_codes: List[np.ndarray] = []
        self._seed = seed

    def build(self, embeddings: np.ndarray):
        """Build LSH index."""
        np.random.seed(self._seed)
        n, dim = embeddings.shape

        self.hyperplanes = [
            np.random.randn(self.n_bits, dim).astype(np.float32)
            for _ in range(self.n_tables)
        ]

        self.hash_codes = []
        for t in range(self.n_tables):
            projections = embeddings @ self.hyperplanes[t].T
            binary = (projections > 0).astype(np.uint8)
            self.hash_codes.append(binary)

    def search(
        self, query: np.ndarray, embeddings: np.ndarray, k: int = 3000
    ) -> List[int]:
        """Search using Hamming distance across all tables."""
        query = query.reshape(1, -1).astype(np.float32)

        all_candidates: Set[int] = set()
        k_per_table = k // self.n_tables + 10

        for t in range(self.n_tables):
            proj = query @ self.hyperplanes[t].T
            query_hash = (proj > 0).astype(np.uint8)[0]

            distances = np.sum(query_hash != self.hash_codes[t], axis=1)
            top_idx = np.argsort(distances)[:k_per_table]
            all_candidates.update(top_idx.tolist())

        return list(all_candidates)


def reciprocal_rank_fusion(
    results_list: List[List[Tuple[int, float]]], k: int = 60
) -> List[Tuple[int, float]]:
    """RRF fusion for combining ranked lists."""
    rrf_scores: Dict[int, float] = {}

    for results in results_list:
        for rank, (doc_idx, _) in enumerate(results):
            rrf_score = 1.0 / (k + rank + 1)
            rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0) + rrf_score

    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


def run_benchmark():
    """Run the complete benchmark."""
    print("=" * 80)
    print("TotalReclaw Real Benchmark")
    print("=" * 80)

    memories, embeddings = load_memories_and_embeddings()

    n_memories = len(memories)
    n_embeddings = embeddings.shape[0]
    print(f"\nTotal memories: {n_memories}")
    print(f"Total embeddings: {n_embeddings}")

    if n_memories != n_embeddings:
        print(
            f"WARNING: Mismatch between memories ({n_memories}) and embeddings ({n_embeddings})"
        )
        n_memories = min(n_memories, n_embeddings)
        memories = memories[:n_memories]
        embeddings = embeddings[:n_memories]

    embeddings = embeddings / (
        np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
    )

    documents = [(i, m["content"]) for i, m in enumerate(memories)]

    bm25 = BM25Index()
    print("\nBuilding BM25 index...")
    bm25.index(documents)
    print(f"  Indexed {bm25.doc_count} documents")

    lsh = LSHIndex(n_bits=64, n_tables=12, seed=42)
    print("\nBuilding LSH index...")
    lsh.build(embeddings)
    print(f"  Built {lsh.n_tables} tables with {lsh.n_bits} bits each")

    n_queries = 200
    seed = 42
    np.random.seed(seed)
    query_indices = np.random.choice(
        n_memories, size=min(n_queries, n_memories), replace=False
    )

    ground_truth = {}
    print(f"\nComputing ground truth for {len(query_indices)} queries...")
    for i, idx in enumerate(query_indices):
        query_vec = embeddings[idx]
        ground_truth[idx] = {
            "query_text": memories[idx]["content"][:200],
            "true_top_8": compute_true_top_k(query_vec, embeddings, 8, idx),
            "true_top_20": compute_true_top_k(query_vec, embeddings, 20, idx),
            "true_top_100": compute_true_top_k(query_vec, embeddings, 100, idx),
        }
        if (i + 1) % 50 == 0:
            print(f"  Computed {i + 1}/{len(query_indices)}")

    results = {}

    print("\n" + "=" * 80)
    print("Benchmarking: BM25-only (keyword baseline)")
    print("=" * 80)

    bm25_recalls_8 = []
    bm25_recalls_20 = []
    bm25_recalls_100 = []
    bm25_latencies = []
    bm25_mrr = []

    for idx in query_indices:
        gt = ground_truth[idx]
        query_text = gt["query_text"]

        start = time.perf_counter()
        results_100 = bm25.search(query_text, top_k=100)
        latency = (time.perf_counter() - start) * 1000
        bm25_latencies.append(latency)

        result_ids = set(r[0] for r in results_100[:8])
        bm25_recalls_8.append(len(result_ids & gt["true_top_8"]) / 8)

        result_ids = set(r[0] for r in results_100[:20])
        bm25_recalls_20.append(len(result_ids & gt["true_top_20"]) / 20)

        result_ids = set(r[0] for r in results_100[:100])
        bm25_recalls_100.append(len(result_ids & gt["true_top_100"]) / 100)

        for rank, (doc_idx, _) in enumerate(results_100[:20]):
            if doc_idx in gt["true_top_8"]:
                bm25_mrr.append(1.0 / (rank + 1))
                break
        else:
            bm25_mrr.append(0)

    results["bm25_only"] = BenchmarkResult(
        backend_name="BM25-only",
        recall_at_8=statistics.mean(bm25_recalls_8),
        recall_at_20=statistics.mean(bm25_recalls_20),
        recall_at_100=statistics.mean(bm25_recalls_100),
        mrr=statistics.mean(bm25_mrr),
        avg_latency_ms=statistics.mean(bm25_latencies),
        p95_latency_ms=sorted(bm25_latencies)[int(len(bm25_latencies) * 0.95)]
        if len(bm25_latencies) >= 20
        else max(bm25_latencies),
        storage_bytes=n_memories * 500,
        privacy_score=0,
        total_memories=n_memories,
        queries_run=len(query_indices),
        raw_recalls=bm25_recalls_8,
        raw_latencies=bm25_latencies,
    )

    print(f"  Recall@8: {results['bm25_only'].recall_at_8:.3f}")
    print(f"  Recall@20: {results['bm25_only'].recall_at_20:.3f}")
    print(f"  Recall@100: {results['bm25_only'].recall_at_100:.3f}")
    print(f"  MRR: {results['bm25_only'].mrr:.3f}")
    print(
        f"  Latency: {results['bm25_only'].avg_latency_ms:.2f}ms (p95: {results['bm25_only'].p95_latency_ms:.2f}ms)"
    )

    print("\n" + "=" * 80)
    print("Benchmarking: Vector-only (semantic baseline)")
    print("=" * 80)

    vec_recalls_8 = []
    vec_recalls_20 = []
    vec_recalls_100 = []
    vec_latencies = []
    vec_mrr = []

    for idx in query_indices:
        gt = ground_truth[idx]
        query_vec = embeddings[idx]

        start = time.perf_counter()
        similarities = (embeddings @ query_vec).flatten()
        top_indices = np.argsort(similarities)[::-1]
        top_100 = [int(i) for i in top_indices if i != idx][:100]
        latency = (time.perf_counter() - start) * 1000
        vec_latencies.append(latency)

        result_ids = set(top_100[:8])
        vec_recalls_8.append(len(result_ids & gt["true_top_8"]) / 8)

        result_ids = set(top_100[:20])
        vec_recalls_20.append(len(result_ids & gt["true_top_20"]) / 20)

        result_ids = set(top_100[:100])
        vec_recalls_100.append(len(result_ids & gt["true_top_100"]) / 100)

        for rank, doc_idx in enumerate(top_100[:20]):
            if doc_idx in gt["true_top_8"]:
                vec_mrr.append(1.0 / (rank + 1))
                break
        else:
            vec_mrr.append(0)

    results["vector_only"] = BenchmarkResult(
        backend_name="Vector-only",
        recall_at_8=statistics.mean(vec_recalls_8),
        recall_at_20=statistics.mean(vec_recalls_20),
        recall_at_100=statistics.mean(vec_recalls_100),
        mrr=statistics.mean(vec_mrr),
        avg_latency_ms=statistics.mean(vec_latencies),
        p95_latency_ms=sorted(vec_latencies)[int(len(vec_latencies) * 0.95)]
        if len(vec_latencies) >= 20
        else max(vec_latencies),
        storage_bytes=n_memories * 384 * 4,
        privacy_score=0,
        total_memories=n_memories,
        queries_run=len(query_indices),
        raw_recalls=vec_recalls_8,
        raw_latencies=vec_latencies,
    )

    print(f"  Recall@8: {results['vector_only'].recall_at_8:.3f}")
    print(f"  Recall@20: {results['vector_only'].recall_at_20:.3f}")
    print(f"  Recall@100: {results['vector_only'].recall_at_100:.3f}")
    print(f"  MRR: {results['vector_only'].mrr:.3f}")
    print(
        f"  Latency: {results['vector_only'].avg_latency_ms:.2f}ms (p95: {results['vector_only'].p95_latency_ms:.2f}ms)"
    )

    print("\n" + "=" * 80)
    print("Benchmarking: Hybrid (BM25 + Vector + RRF)")
    print("=" * 80)

    hybrid_recalls_8 = []
    hybrid_recalls_20 = []
    hybrid_recalls_100 = []
    hybrid_latencies = []
    hybrid_mrr = []

    for idx in query_indices:
        gt = ground_truth[idx]
        query_text = gt["query_text"]
        query_vec = embeddings[idx]

        start = time.perf_counter()

        bm25_results = bm25.search(query_text, top_k=50)

        similarities = (embeddings @ query_vec).flatten()
        top_vec_idx = np.argsort(similarities)[::-1]
        vec_results = [(int(i), similarities[i]) for i in top_vec_idx if i != idx][:50]

        fused = reciprocal_rank_fusion([bm25_results, vec_results])
        top_100 = [r[0] for r in fused[:100]]

        latency = (time.perf_counter() - start) * 1000
        hybrid_latencies.append(latency)

        result_ids = set(top_100[:8])
        hybrid_recalls_8.append(len(result_ids & gt["true_top_8"]) / 8)

        result_ids = set(top_100[:20])
        hybrid_recalls_20.append(len(result_ids & gt["true_top_20"]) / 20)

        result_ids = set(top_100[:100])
        hybrid_recalls_100.append(len(result_ids & gt["true_top_100"]) / 100)

        for rank, doc_idx in enumerate(top_100[:20]):
            if doc_idx in gt["true_top_8"]:
                hybrid_mrr.append(1.0 / (rank + 1))
                break
        else:
            hybrid_mrr.append(0)

    results["hybrid"] = BenchmarkResult(
        backend_name="Hybrid (BM25+Vector+RRF)",
        recall_at_8=statistics.mean(hybrid_recalls_8),
        recall_at_20=statistics.mean(hybrid_recalls_20),
        recall_at_100=statistics.mean(hybrid_recalls_100),
        mrr=statistics.mean(hybrid_mrr),
        avg_latency_ms=statistics.mean(hybrid_latencies),
        p95_latency_ms=sorted(hybrid_latencies)[int(len(hybrid_latencies) * 0.95)]
        if len(hybrid_latencies) >= 20
        else max(hybrid_latencies),
        storage_bytes=n_memories * (500 + 384 * 4),
        privacy_score=0,
        total_memories=n_memories,
        queries_run=len(query_indices),
        raw_recalls=hybrid_recalls_8,
        raw_latencies=hybrid_latencies,
    )

    print(f"  Recall@8: {results['hybrid'].recall_at_8:.3f}")
    print(f"  Recall@20: {results['hybrid'].recall_at_20:.3f}")
    print(f"  Recall@100: {results['hybrid'].recall_at_100:.3f}")
    print(f"  MRR: {results['hybrid'].mrr:.3f}")
    print(
        f"  Latency: {results['hybrid'].avg_latency_ms:.2f}ms (p95: {results['hybrid'].p95_latency_ms:.2f}ms)"
    )

    print("\n" + "=" * 80)
    print("Benchmarking: TotalReclaw E2EE (LSH + client rerank)")
    print("=" * 80)

    om_recalls_8 = []
    om_recalls_20 = []
    om_recalls_100 = []
    om_latencies = []
    om_mrr = []

    for idx in query_indices:
        gt = ground_truth[idx]
        query_text = gt["query_text"]
        query_vec = embeddings[idx]

        start = time.perf_counter()

        candidates = lsh.search(query_vec, embeddings, k=3000)

        if idx in candidates:
            candidates.remove(idx)

        candidate_vecs = embeddings[candidates]
        similarities = (candidate_vecs @ query_vec).flatten()
        sorted_idx = np.argsort(similarities)[::-1]
        top_100 = [candidates[i] for i in sorted_idx[:100]]

        latency = (time.perf_counter() - start) * 1000
        om_latencies.append(latency)

        result_ids = set(top_100[:8])
        om_recalls_8.append(len(result_ids & gt["true_top_8"]) / 8)

        result_ids = set(top_100[:20])
        om_recalls_20.append(len(result_ids & gt["true_top_20"]) / 20)

        result_ids = set(top_100[:100])
        om_recalls_100.append(len(result_ids & gt["true_top_100"]) / 100)

        for rank, doc_idx in enumerate(top_100[:20]):
            if doc_idx in gt["true_top_8"]:
                om_mrr.append(1.0 / (rank + 1))
                break
        else:
            om_mrr.append(0)

    lsh_storage = n_memories * lsh.n_tables * lsh.n_bits // 8
    enc_storage = n_memories * (500 + 384 * 4 + 32 + 16)

    results["totalreclaw_e2ee"] = BenchmarkResult(
        backend_name="TotalReclaw E2EE",
        recall_at_8=statistics.mean(om_recalls_8),
        recall_at_20=statistics.mean(om_recalls_20),
        recall_at_100=statistics.mean(om_recalls_100),
        mrr=statistics.mean(om_mrr),
        avg_latency_ms=statistics.mean(om_latencies),
        p95_latency_ms=sorted(om_latencies)[int(len(om_latencies) * 0.95)]
        if len(om_latencies) >= 20
        else max(om_latencies),
        storage_bytes=enc_storage + lsh_storage,
        privacy_score=100,
        total_memories=n_memories,
        queries_run=len(query_indices),
        raw_recalls=om_recalls_8,
        raw_latencies=om_latencies,
    )

    print(f"  Recall@8: {results['totalreclaw_e2ee'].recall_at_8:.3f}")
    print(f"  Recall@20: {results['totalreclaw_e2ee'].recall_at_20:.3f}")
    print(f"  Recall@100: {results['totalreclaw_e2ee'].recall_at_100:.3f}")
    print(f"  MRR: {results['totalreclaw_e2ee'].mrr:.3f}")
    print(
        f"  Latency: {results['totalreclaw_e2ee'].avg_latency_ms:.2f}ms (p95: {results['totalreclaw_e2ee'].p95_latency_ms:.2f}ms)"
    )
    print(f"  Candidates retrieved: ~3000")

    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)

    print(
        f"\n{'Backend':<25} {'Recall@8':>10} {'Recall@20':>11} {'Recall@100':>12} {'MRR':>8} {'Latency':>12} {'Privacy':>8}"
    )
    print("-" * 95)

    for name, r in results.items():
        print(
            f"{r.backend_name:<25} {r.recall_at_8:>10.3f} {r.recall_at_20:>11.3f} {r.recall_at_100:>12.3f} {r.mrr:>8.3f} {r.avg_latency_ms:>8.2f}ms {r.privacy_score:>8}"
        )

    output = {
        "metadata": {
            "total_memories": n_memories,
            "n_queries": len(query_indices),
            "embedding_dim": embeddings.shape[1],
            "lsh_config": {
                "n_bits": lsh.n_bits,
                "n_tables": lsh.n_tables,
            },
        },
        "results": {
            name: {
                "backend_name": r.backend_name,
                "recall_at_8": r.recall_at_8,
                "recall_at_20": r.recall_at_20,
                "recall_at_100": r.recall_at_100,
                "mrr": r.mrr,
                "avg_latency_ms": r.avg_latency_ms,
                "p95_latency_ms": r.p95_latency_ms,
                "storage_bytes": r.storage_bytes,
                "privacy_score": r.privacy_score,
            }
            for name, r in results.items()
        },
    }

    output_path = BASE_DIR / "benchmark_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")

    return results


if __name__ == "__main__":
    run_benchmark()
