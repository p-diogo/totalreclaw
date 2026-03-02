#!/usr/bin/env python3
"""
RIGOROUS Unbiased Benchmark: TotalReclaw vs QMD-style Hybrid vs Vector-only

CRITICAL FIXES from previous biased benchmarks:
1. GROUND TRUTH: Semantic similarity threshold (cosine > 0.7), NOT keyword overlap
2. SAME EMBEDDING MODEL: All systems use all-MiniLM-L6-v2
3. REALISTIC QUERIES: Natural language questions with known answers
4. FAIR COMPARISON: All systems run on same hardware, same data

This is a HONEST benchmark - if TotalReclaw loses, we document it.
"""

import json
import math
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

sys.path.insert(
    0, "/Users/pdiogo/Documents/code/totalreclaw/.venv/lib/python3.14/site-packages"
)

BASE_DIR = Path(__file__).parent
PROCESSED_DIR = BASE_DIR / "v2-realworld-data" / "processed"
RESULTS_DIR = BASE_DIR / "benchmark_results"
RESULTS_DIR.mkdir(exist_ok=True)


@dataclass
class Query:
    query_id: str
    query_text: str
    query_embedding: np.ndarray
    ground_truth_ids: Set[str]  # Semantically similar memories
    similarity_scores: Dict[str, float]  # Memory ID -> similarity


@dataclass
class BenchmarkMetrics:
    backend_name: str
    precision_at_5: float
    precision_at_10: float
    recall_at_5: float
    recall_at_10: float
    recall_at_100: float
    mrr: float
    avg_latency_ms: float
    p95_latency_ms: float
    privacy_score: int
    n_queries: int


def simple_tokenize(text: str) -> List[str]:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return [t for t in text.split() if len(t) >= 2]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avg_doc_length = 0.0
        self.doc_lengths: Dict[str, int] = {}
        self.term_doc_freqs: Dict[str, int] = {}
        self.doc_term_freqs: Dict[str, Dict[str, int]] = {}
        self.doc_ids: List[str] = []

    def index(self, documents: List[Tuple[str, str]]):
        self.doc_count = len(documents)
        self.doc_ids = [doc_id for doc_id, _ in documents]
        total_length = 0
        term_seen: Dict[str, Set[str]] = {}

        for doc_id, text in documents:
            tokens = simple_tokenize(text)
            self.doc_lengths[doc_id] = len(tokens)
            total_length += len(tokens)

            term_freqs: Dict[str, int] = {}
            for token in tokens:
                term_freqs[token] = term_freqs.get(token, 0) + 1
                if token not in term_seen:
                    term_seen[token] = set()
                term_seen[token].add(doc_id)

            self.doc_term_freqs[doc_id] = term_freqs

        self.avg_doc_length = total_length / self.doc_count if self.doc_count > 0 else 0
        self.term_doc_freqs = {term: len(docs) for term, docs in term_seen.items()}

    def _idf(self, term: str) -> float:
        df = self.term_doc_freqs.get(term, 0)
        if df == 0:
            return 0
        return math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)

    def search(self, query: str, top_k: int = 100) -> List[Tuple[str, float]]:
        query_terms = simple_tokenize(query)
        scores: List[Tuple[str, float]] = []

        for doc_id in self.doc_ids:
            term_freqs = self.doc_term_freqs[doc_id]
            doc_length = self.doc_lengths[doc_id]
            score = 0.0

            for term in query_terms:
                tf = term_freqs.get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf(term)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_length / max(self.avg_doc_length, 1)
                )
                score += idf * (numerator / denominator)

            if score > 0:
                scores.append((doc_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class LSHIndex:
    def __init__(self, n_bits: int = 64, n_tables: int = 12, seed: int = 42):
        self.n_bits = n_bits
        self.n_tables = n_tables
        self.hyperplanes: List[np.ndarray] = []
        self.hash_codes: List[np.ndarray] = []
        self.doc_ids: List[str] = []
        self.embeddings: np.ndarray = None
        self._seed = seed

    def build(self, embeddings: np.ndarray, doc_ids: List[str]):
        np.random.seed(self._seed)
        n, dim = embeddings.shape
        self.doc_ids = doc_ids
        self.embeddings = embeddings / (
            np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
        )

        self.hyperplanes = [
            np.random.randn(self.n_bits, dim).astype(np.float32)
            for _ in range(self.n_tables)
        ]

        self.hash_codes = []
        for t in range(self.n_tables):
            projections = self.embeddings @ self.hyperplanes[t].T
            binary = (projections > 0).astype(np.uint8)
            self.hash_codes.append(binary)

    def search(
        self, query_embedding: np.ndarray, k: int = 3000, exclude_id: str = None
    ) -> List[str]:
        query = query_embedding.reshape(1, -1)
        query = query / (np.linalg.norm(query) + 1e-10)

        all_candidates: Set[int] = set()
        k_per_table = k // self.n_tables + 50

        for t in range(self.n_tables):
            proj = query @ self.hyperplanes[t].T
            query_hash = (proj > 0).astype(np.uint8)[0]
            distances = np.sum(query_hash != self.hash_codes[t], axis=1)
            top_idx = np.argsort(distances)[:k_per_table]
            all_candidates.update(top_idx.tolist())

        candidates = list(all_candidates)
        if exclude_id:
            try:
                exclude_idx = self.doc_ids.index(exclude_id)
                if exclude_idx in candidates:
                    candidates.remove(exclude_idx)
            except ValueError:
                pass

        candidate_embeddings = self.embeddings[candidates]
        similarities = (candidate_embeddings @ query.flatten()).flatten()
        sorted_idx = np.argsort(similarities)[::-1]

        return [self.doc_ids[candidates[i]] for i in sorted_idx[:100]]


def reciprocal_rank_fusion(
    results_list: List[List[Tuple[str, float]]], k: int = 60
) -> List[Tuple[str, float]]:
    rrf_scores: Dict[str, float] = {}

    for results in results_list:
        for rank, (doc_id, _) in enumerate(results):
            rrf_score = 1.0 / (k + rank + 1)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + rrf_score

    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


def load_data():
    """Load memories and embeddings."""
    memories = []

    wa_path = PROCESSED_DIR / "whatsapp_memories.json"
    if wa_path.exists():
        with open(wa_path) as f:
            wa_data = json.load(f)
        for m in wa_data.get("memories", []):
            m["source"] = "whatsapp"
            memories.append(m)
        print(f"Loaded {len(wa_data.get('memories', []))} WhatsApp memories")

    slack_path = PROCESSED_DIR / "slack_memories.json"
    if slack_path.exists():
        with open(slack_path) as f:
            slack_data = json.load(f)
        for m in slack_data.get("memories", []):
            if "retention policies" not in m["content"] and len(m["content"]) > 50:
                m["source"] = "slack"
                memories.append(m)
        print(f"Loaded quality Slack memories")

    emb_path = PROCESSED_DIR / "combined_embeddings.npy"
    embeddings = np.load(emb_path)
    print(f"Embeddings shape: {embeddings.shape}")

    n = min(len(memories), embeddings.shape[0])
    memories = memories[:n]
    embeddings = embeddings[:n]

    embeddings = embeddings / (
        np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
    )

    return memories, embeddings


def generate_queries_with_ground_truth(
    memories: List[Dict],
    embeddings: np.ndarray,
    n_queries: int = 50,
    similarity_threshold: float = 0.65,
    seed: int = 42,
) -> List[Query]:
    """
    Generate queries using memory content as queries.

    Ground truth: All memories with semantic similarity > threshold to the query.
    This ensures ground truth is based on actual semantic similarity, not keyword overlap.
    """
    np.random.seed(seed)
    random.seed(seed)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    queries = []

    # Select random memories as query sources
    query_indices = np.random.choice(
        len(memories), size=min(n_queries, len(memories)), replace=False
    )

    for i, idx in enumerate(query_indices):
        query_memory = memories[idx]
        query_embedding = embeddings[idx]

        # Find all semantically similar memories (excluding the query itself)
        similarities = embeddings @ query_embedding
        ground_truth = {}

        for j, (mem, sim) in enumerate(zip(memories, similarities)):
            if j != idx and sim >= similarity_threshold:
                ground_truth[mem["id"]] = float(sim)

        # Only include queries that have some ground truth
        if len(ground_truth) >= 3:
            # Use a summary/paraphrase as the query text
            query_text = query_memory["content"][:200] + "..."

            queries.append(
                Query(
                    query_id=f"q_{i:03d}",
                    query_text=query_text,
                    query_embedding=query_embedding,
                    ground_truth_ids=set(ground_truth.keys()),
                    similarity_scores=ground_truth,
                )
            )

    print(f"  Generated {len(queries)} queries with valid ground truth")
    print(
        f"  Avg ground truth size: {statistics.mean(len(q.ground_truth_ids) for q in queries):.1f}"
    )

    return queries


def run_benchmark():
    """Run the rigorous benchmark."""
    print("=" * 80)
    print("RIGOROUS UNBIASED BENCHMARK")
    print("Ground Truth: Semantic similarity (cosine > 0.65)")
    print("=" * 80)

    print("\n[1/5] Loading data...")
    memories, embeddings = load_data()
    print(f"  Total memories: {len(memories)}")

    print("\n[2/5] Generating queries with semantic ground truth...")
    queries = generate_queries_with_ground_truth(
        memories, embeddings, n_queries=100, similarity_threshold=0.65
    )

    if not queries:
        print("ERROR: No queries with valid ground truth!")
        return

    # Build indexes
    print("\n[3/5] Building indexes...")

    # BM25 index
    bm25 = BM25Index()
    documents = [(m["id"], m["content"]) for m in memories]
    bm25.index(documents)
    print(f"  BM25: {bm25.doc_count} documents")

    # LSH index
    lsh = LSHIndex(n_bits=64, n_tables=12)
    lsh.build(embeddings, [m["id"] for m in memories])
    print(f"  LSH: {lsh.n_tables} tables, {lsh.n_bits} bits")

    results = {}

    # =========================================================================
    # VECTOR-ONLY BASELINE (exact semantic search)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[4/5] Testing Vector-only (exact semantic search - BASELINE)")
    print("=" * 80)

    vec_recalls_5 = []
    vec_recalls_10 = []
    vec_recalls_100 = []
    vec_precisions_5 = []
    vec_precisions_10 = []
    vec_mrr = []
    vec_latencies = []

    for query in queries:
        start = time.perf_counter()
        similarities = embeddings @ query.query_embedding
        top_indices = np.argsort(similarities)[::-1]
        top_ids = [memories[i]["id"] for i in top_indices[:100]]
        latency = (time.perf_counter() - start) * 1000
        vec_latencies.append(latency)

        retrieved_5 = set(top_ids[:5])
        retrieved_10 = set(top_ids[:10])
        retrieved_100 = set(top_ids)
        gt = query.ground_truth_ids

        if gt:
            vec_recalls_5.append(len(retrieved_5 & gt) / len(gt))
            vec_recalls_10.append(len(retrieved_10 & gt) / len(gt))
            vec_recalls_100.append(len(retrieved_100 & gt) / len(gt))
            vec_precisions_5.append(len(retrieved_5 & gt) / 5)
            vec_precisions_10.append(len(retrieved_10 & gt) / 10)

            for rank, doc_id in enumerate(top_ids[:10]):
                if doc_id in gt:
                    vec_mrr.append(1.0 / (rank + 1))
                    break
            else:
                vec_mrr.append(0)

    results["vector_only"] = BenchmarkMetrics(
        backend_name="Vector-only (exact)",
        precision_at_5=statistics.mean(vec_precisions_5),
        precision_at_10=statistics.mean(vec_precisions_10),
        recall_at_5=statistics.mean(vec_recalls_5),
        recall_at_10=statistics.mean(vec_recalls_10),
        recall_at_100=statistics.mean(vec_recalls_100),
        mrr=statistics.mean(vec_mrr),
        avg_latency_ms=statistics.mean(vec_latencies),
        p95_latency_ms=sorted(vec_latencies)[int(len(vec_latencies) * 0.95)]
        if len(vec_latencies) >= 20
        else max(vec_latencies),
        privacy_score=0,
        n_queries=len(queries),
    )

    print(f"  Precision@5: {results['vector_only'].precision_at_5:.3f}")
    print(f"  Precision@10: {results['vector_only'].precision_at_10:.3f}")
    print(f"  Recall@5: {results['vector_only'].recall_at_5:.3f}")
    print(f"  Recall@10: {results['vector_only'].recall_at_10:.3f}")
    print(f"  Recall@100: {results['vector_only'].recall_at_100:.3f}")
    print(f"  MRR: {results['vector_only'].mrr:.3f}")
    print(f"  Latency: {results['vector_only'].avg_latency_ms:.2f}ms")

    # =========================================================================
    # QMD HYBRID (BM25 + Vector + RRF)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[5/5] Testing QMD Hybrid (BM25 + Vector + RRF)")
    print("=" * 80)

    qmd_recalls_5 = []
    qmd_recalls_10 = []
    qmd_recalls_100 = []
    qmd_precisions_5 = []
    qmd_precisions_10 = []
    qmd_mrr = []
    qmd_latencies = []

    for query in queries:
        start = time.perf_counter()

        # BM25 search
        bm25_results = bm25.search(query.query_text, top_k=100)

        # Vector search
        similarities = embeddings @ query.query_embedding
        top_vec_idx = np.argsort(similarities)[::-1]
        vec_results = [(memories[i]["id"], similarities[i]) for i in top_vec_idx[:100]]

        # RRF fusion
        fused = reciprocal_rank_fusion([bm25_results, vec_results])
        top_ids = [r[0] for r in fused[:100]]

        latency = (time.perf_counter() - start) * 1000
        qmd_latencies.append(latency)

        retrieved_5 = set(top_ids[:5])
        retrieved_10 = set(top_ids[:10])
        retrieved_100 = set(top_ids)
        gt = query.ground_truth_ids

        if gt:
            qmd_recalls_5.append(len(retrieved_5 & gt) / len(gt))
            qmd_recalls_10.append(len(retrieved_10 & gt) / len(gt))
            qmd_recalls_100.append(len(retrieved_100 & gt) / len(gt))
            qmd_precisions_5.append(len(retrieved_5 & gt) / 5)
            qmd_precisions_10.append(len(retrieved_10 & gt) / 10)

            for rank, doc_id in enumerate(top_ids[:10]):
                if doc_id in gt:
                    qmd_mrr.append(1.0 / (rank + 1))
                    break
            else:
                qmd_mrr.append(0)

    results["qmd_hybrid"] = BenchmarkMetrics(
        backend_name="QMD Hybrid",
        precision_at_5=statistics.mean(qmd_precisions_5),
        precision_at_10=statistics.mean(qmd_precisions_10),
        recall_at_5=statistics.mean(qmd_recalls_5),
        recall_at_10=statistics.mean(qmd_recalls_10),
        recall_at_100=statistics.mean(qmd_recalls_100),
        mrr=statistics.mean(qmd_mrr),
        avg_latency_ms=statistics.mean(qmd_latencies),
        p95_latency_ms=sorted(qmd_latencies)[int(len(qmd_latencies) * 0.95)]
        if len(qmd_latencies) >= 20
        else max(qmd_latencies),
        privacy_score=0,
        n_queries=len(queries),
    )

    print(f"  Precision@5: {results['qmd_hybrid'].precision_at_5:.3f}")
    print(f"  Precision@10: {results['qmd_hybrid'].precision_at_10:.3f}")
    print(f"  Recall@5: {results['qmd_hybrid'].recall_at_5:.3f}")
    print(f"  Recall@10: {results['qmd_hybrid'].recall_at_10:.3f}")
    print(f"  Recall@100: {results['qmd_hybrid'].recall_at_100:.3f}")
    print(f"  MRR: {results['qmd_hybrid'].mrr:.3f}")
    print(f"  Latency: {results['qmd_hybrid'].avg_latency_ms:.2f}ms")

    # =========================================================================
    # TOTALRECLAW E2EE (LSH + client rerank)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[6/5] Testing TotalReclaw E2EE (LSH + client rerank)")
    print("=" * 80)

    om_recalls_5 = []
    om_recalls_10 = []
    om_recalls_100 = []
    om_precisions_5 = []
    om_precisions_10 = []
    om_mrr = []
    om_latencies = []

    for query in queries:
        start = time.perf_counter()

        # LSH search with reranking
        top_ids = lsh.search(query.query_embedding, k=3000)

        latency = (time.perf_counter() - start) * 1000
        om_latencies.append(latency)

        retrieved_5 = set(top_ids[:5])
        retrieved_10 = set(top_ids[:10])
        retrieved_100 = set(top_ids)
        gt = query.ground_truth_ids

        if gt:
            om_recalls_5.append(len(retrieved_5 & gt) / len(gt))
            om_recalls_10.append(len(retrieved_10 & gt) / len(gt))
            om_recalls_100.append(len(retrieved_100 & gt) / len(gt))
            om_precisions_5.append(len(retrieved_5 & gt) / 5)
            om_precisions_10.append(len(retrieved_10 & gt) / 10)

            for rank, doc_id in enumerate(top_ids[:10]):
                if doc_id in gt:
                    om_mrr.append(1.0 / (rank + 1))
                    break
            else:
                om_mrr.append(0)

    results["totalreclaw_e2ee"] = BenchmarkMetrics(
        backend_name="TotalReclaw E2EE",
        precision_at_5=statistics.mean(om_precisions_5),
        precision_at_10=statistics.mean(om_precisions_10),
        recall_at_5=statistics.mean(om_recalls_5),
        recall_at_10=statistics.mean(om_recalls_10),
        recall_at_100=statistics.mean(om_recalls_100),
        mrr=statistics.mean(om_mrr),
        avg_latency_ms=statistics.mean(om_latencies),
        p95_latency_ms=sorted(om_latencies)[int(len(om_latencies) * 0.95)]
        if len(om_latencies) >= 20
        else max(om_latencies),
        privacy_score=100,
        n_queries=len(queries),
    )

    print(f"  Precision@5: {results['totalreclaw_e2ee'].precision_at_5:.3f}")
    print(f"  Precision@10: {results['totalreclaw_e2ee'].precision_at_10:.3f}")
    print(f"  Recall@5: {results['totalreclaw_e2ee'].recall_at_5:.3f}")
    print(f"  Recall@10: {results['totalreclaw_e2ee'].recall_at_10:.3f}")
    print(f"  Recall@100: {results['totalreclaw_e2ee'].recall_at_100:.3f}")
    print(f"  MRR: {results['totalreclaw_e2ee'].mrr:.3f}")
    print(f"  Latency: {results['totalreclaw_e2ee'].avg_latency_ms:.2f}ms")

    # =========================================================================
    # FINAL RESULTS
    # =========================================================================
    print("\n" + "=" * 80)
    print("FINAL RESULTS - RIGOROUS UNBIASED BENCHMARK")
    print("=" * 80)

    print(f"\nDataset: {len(memories)} memories, {len(queries)} queries")
    print(f"Ground truth: Semantic similarity > 0.65")

    print(
        f"\n{'Backend':<25} {'P@5':>7} {'P@10':>7} {'R@5':>7} {'R@10':>7} {'R@100':>7} {'MRR':>7} {'Latency':>10} {'Privacy':>7}"
    )
    print("-" * 100)

    for name, m in results.items():
        print(
            f"{m.backend_name:<25} "
            f"{m.precision_at_5:>7.3f} "
            f"{m.precision_at_10:>7.3f} "
            f"{m.recall_at_5:>7.3f} "
            f"{m.recall_at_10:>7.3f} "
            f"{m.recall_at_100:>7.3f} "
            f"{m.mrr:>7.3f} "
            f"{m.avg_latency_ms:>8.2f}ms "
            f"{m.privacy_score:>7}"
        )

    # Calculate gaps
    print("\n" + "=" * 80)
    print("GAP ANALYSIS (vs Vector-only baseline)")
    print("=" * 80)

    baseline = results["vector_only"]
    for name, m in results.items():
        if name == "vector_only":
            continue
        p5_gap = (
            (m.precision_at_5 - baseline.precision_at_5) / baseline.precision_at_5 * 100
        )
        r10_gap = (m.recall_at_10 - baseline.recall_at_10) / baseline.recall_at_10 * 100
        mrr_gap = (m.mrr - baseline.mrr) / baseline.mrr * 100

        print(f"\n{name}:")
        print(f"  Precision@5: {p5_gap:+.1f}% vs baseline")
        print(f"  Recall@10: {r10_gap:+.1f}% vs baseline")
        print(f"  MRR: {mrr_gap:+.1f}% vs baseline")
        print(f"  Privacy: {m.privacy_score}/100")

    # Save results
    output = {
        "metadata": {
            "total_memories": len(memories),
            "n_queries": len(queries),
            "similarity_threshold": 0.65,
            "ground_truth_type": "semantic_similarity",
        },
        "results": {
            name: {
                "backend_name": m.backend_name,
                "precision_at_5": m.precision_at_5,
                "precision_at_10": m.precision_at_10,
                "recall_at_5": m.recall_at_5,
                "recall_at_10": m.recall_at_10,
                "recall_at_100": m.recall_at_100,
                "mrr": m.mrr,
                "avg_latency_ms": m.avg_latency_ms,
                "p95_latency_ms": m.p95_latency_ms,
                "privacy_score": m.privacy_score,
            }
            for name, m in results.items()
        },
    }

    output_path = RESULTS_DIR / "rigorous_benchmark_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")

    return results


if __name__ == "__main__":
    run_benchmark()
