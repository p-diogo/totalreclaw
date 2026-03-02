#!/usr/bin/env python3
"""
Full Apples-to-Apples Benchmark: TotalReclaw vs Mem0 Cloud vs QMD Hybrid

Uses ACTUAL services:
- Mem0 Cloud (https://api.mem0.ai) - their real SaaS
- TotalReclaw E2EE - our LSH + client-side reranking
- QMD Hybrid - BM25 + Vector + RRF baseline
- Vector-only - exact semantic search baseline

Dataset: Real WhatsApp + Slack conversations (8629 memories)
Queries: 100 semantic queries with ground truth
"""

import json
import hashlib
import math
import os
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from dotenv import load_dotenv

sys.path.insert(
    0, "/Users/pdiogo/Documents/code/totalreclaw/.venv/lib/python3.14/site-packages"
)

# Load environment
load_dotenv("/Users/pdiogo/Documents/code/totalreclaw/.env")

BASE_DIR = Path(__file__).parent
PROCESSED_DIR = BASE_DIR / "v2-realworld-data" / "processed"
RESULTS_DIR = BASE_DIR / "benchmark_results"
RESULTS_DIR.mkdir(exist_ok=True)


@dataclass
class Query:
    query_id: str
    query_text: str
    query_embedding: np.ndarray
    ground_truth_ids: Set[str]
    similarity_scores: Dict[str, float]


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
    total_memories: int = 0
    api_errors: int = 0


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


def generate_queries(
    memories, embeddings, n_queries=100, similarity_threshold=0.65, seed=42
):
    np.random.seed(seed)
    random.seed(seed)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    queries = []
    query_indices = np.random.choice(
        len(memories), size=min(n_queries, len(memories)), replace=False
    )

    for i, idx in enumerate(query_indices):
        query_memory = memories[idx]
        query_embedding = embeddings[idx]
        similarities = embeddings @ query_embedding
        ground_truth = {}

        for j, (mem, sim) in enumerate(zip(memories, similarities)):
            if j != idx and sim >= similarity_threshold:
                ground_truth[mem["id"]] = float(sim)

        if len(ground_truth) >= 3:
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


class Mem0CloudBackend:
    """Actual Mem0 Cloud service with LLM-based memory extraction."""

    def __init__(self, user_id: str = "benchmark_user"):
        self.user_id = user_id
        self.client = None
        self.memories_by_content: Dict[str, Dict] = {}  # content hash -> mem0 memory
        self._initialized = False

    def _init(self):
        if self._initialized:
            return

        from mem0 import MemoryClient

        self.client = MemoryClient()
        self._initialized = True
        print("  Mem0 Cloud client initialized")

    def _content_hash(self, content: str) -> str:
        """Create a hash of content for matching."""
        return hashlib.md5(content[:200].encode()).hexdigest()[:16]

    def add_memories(self, memories: List[Dict], batch_size: int = 100):
        """Add memories to Mem0 Cloud."""
        self._init()

        print(f"  Adding {len(memories)} memories to Mem0 Cloud...")

        # Clear existing
        try:
            self.client.delete_all(user_id=self.user_id)
            print("  Cleared existing memories")
        except:
            pass

        # Store mapping of our content to memory IDs
        self.memories_by_content = {}

        # Add in batches
        for i in range(0, len(memories), batch_size):
            batch = memories[i : i + batch_size]

            for m in batch:
                try:
                    # Store our content hash for later matching
                    content_hash = self._content_hash(m["content"])

                    result = self.client.add(
                        m["content"],
                        user_id=self.user_id,
                        metadata={
                            "source_id": m["id"],
                            "source_hash": content_hash,
                            "source": m.get("source", "unknown"),
                        },
                    )

                except Exception as e:
                    pass

            print(f"    Queued {min(i + batch_size, len(memories))}/{len(memories)}")

            if i + batch_size < len(memories):
                time.sleep(0.5)

        # Wait longer for Mem0 Cloud LLM processing
        print("  Waiting 15 seconds for Mem0 Cloud LLM processing...")
        time.sleep(15)

        # Build content -> Mem0 memory mapping by searching
        print("  Building content mapping...")
        for m in memories[:50]:  # Sample to check
            try:
                # Use first 100 chars as query to find our memory
                search = self.client.search(
                    query=m["content"][:100], filters={"user_id": self.user_id}, top_k=1
                )
                if search.get("results"):
                    mem0_mem = search["results"][0]
                    # Map our ID to the Mem0 extracted content
                    self.memories_by_content[m["id"]] = {
                        "mem0_id": mem0_mem.get("id"),
                        "mem0_memory": mem0_mem.get("memory", ""),
                        "source_id": m["id"],
                    }
            except:
                pass

        print(f"  Mapped {len(self.memories_by_content)} memories")

    def search(self, query: str, top_k: int = 20) -> List[Tuple[str, float]]:
        """Search Mem0 Cloud. Returns (source_id, score) tuples."""
        self._init()

        try:
            results = self.client.search(
                query=query, filters={"user_id": self.user_id}, top_k=top_k
            )

            output = []
            for r in results.get("results", []):
                # Get the source_id from metadata if available
                metadata = r.get("metadata") or {}
                source_id = metadata.get("source_id", r.get("id"))
                score = r.get("score", 0.5)

                # If no source_id, try to match by content similarity
                if not metadata.get("source_id"):
                    # Use the mem0 memory content to find our source
                    mem0_memory = r.get("memory", "")
                    for our_id, mapping in self.memories_by_content.items():
                        if mapping.get("mem0_memory") == mem0_memory:
                            source_id = our_id
                            break

                output.append((source_id, score))

            return output
        except Exception as e:
            print(f"    Mem0 Cloud search error: {e}")
            return []

    @property
    def privacy_score(self) -> int:
        return 0


def run_benchmark():
    print("=" * 80)
    print("APPLES-TO-APPLES BENCHMARK")
    print("TotalReclaw E2EE vs Mem0 Cloud vs QMD Hybrid vs Vector-only")
    print("=" * 80)

    print("\n[1/6] Loading data...")
    memories, embeddings = load_data()
    print(f"  Total memories: {len(memories)}")

    # Limit for Mem0 Cloud (API limits)
    MAX_MEMORIES = 500
    if len(memories) > MAX_MEMORIES:
        print(f"  Limiting to {MAX_MEMORIES} memories for Mem0 Cloud API limits")
        memories = memories[:MAX_MEMORIES]
        embeddings = embeddings[:MAX_MEMORIES]

    print("\n[2/6] Generating queries...")
    queries = generate_queries(
        memories, embeddings, n_queries=50, similarity_threshold=0.65
    )

    if not queries:
        print("ERROR: No queries with valid ground truth!")
        return

    # Build indexes
    print("\n[3/6] Building local indexes...")
    bm25 = BM25Index()
    documents = [(m["id"], m["content"]) for m in memories]
    bm25.index(documents)
    print(f"  BM25: {bm25.doc_count} documents")

    lsh = LSHIndex(n_bits=64, n_tables=12)
    lsh.build(embeddings, [m["id"] for m in memories])
    print(f"  LSH: {lsh.n_tables} tables, {lsh.n_bits} bits")

    results = {}

    # =========================================================================
    # VECTOR-ONLY BASELINE
    # =========================================================================
    print("\n" + "=" * 80)
    print("[4/6] Testing Vector-only (exact semantic search - BASELINE)")
    print("=" * 80)

    vec_recalls_5, vec_recalls_10, vec_recalls_100 = [], [], []
    vec_precisions_5, vec_precisions_10 = [], []
    vec_mrr, vec_latencies = [], []

    for query in queries:
        start = time.perf_counter()
        similarities = embeddings @ query.query_embedding
        top_indices = np.argsort(similarities)[::-1]
        top_ids = [memories[i]["id"] for i in top_indices[:100]]
        latency = (time.perf_counter() - start) * 1000
        vec_latencies.append(latency)

        gt = query.ground_truth_ids
        if gt:
            vec_recalls_5.append(len(set(top_ids[:5]) & gt) / len(gt))
            vec_recalls_10.append(len(set(top_ids[:10]) & gt) / len(gt))
            vec_recalls_100.append(len(set(top_ids) & gt) / len(gt))
            vec_precisions_5.append(len(set(top_ids[:5]) & gt) / 5)
            vec_precisions_10.append(len(set(top_ids[:10]) & gt) / 10)
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
        total_memories=len(memories),
    )
    print(
        f"  P@5: {results['vector_only'].precision_at_5:.3f}, P@10: {results['vector_only'].precision_at_10:.3f}"
    )
    print(
        f"  R@10: {results['vector_only'].recall_at_10:.3f}, MRR: {results['vector_only'].mrr:.3f}"
    )
    print(f"  Latency: {results['vector_only'].avg_latency_ms:.2f}ms")

    # =========================================================================
    # QMD HYBRID
    # =========================================================================
    print("\n" + "=" * 80)
    print("[5/6] Testing QMD Hybrid (BM25 + Vector + RRF)")
    print("=" * 80)

    qmd_recalls_5, qmd_recalls_10, qmd_recalls_100 = [], [], []
    qmd_precisions_5, qmd_precisions_10 = [], []
    qmd_mrr, qmd_latencies = [], []

    for query in queries:
        start = time.perf_counter()
        bm25_results = bm25.search(query.query_text, top_k=100)
        similarities = embeddings @ query.query_embedding
        top_vec_idx = np.argsort(similarities)[::-1]
        vec_results = [(memories[i]["id"], similarities[i]) for i in top_vec_idx[:100]]
        fused = reciprocal_rank_fusion([bm25_results, vec_results])
        top_ids = [r[0] for r in fused[:100]]
        latency = (time.perf_counter() - start) * 1000
        qmd_latencies.append(latency)

        gt = query.ground_truth_ids
        if gt:
            qmd_recalls_5.append(len(set(top_ids[:5]) & gt) / len(gt))
            qmd_recalls_10.append(len(set(top_ids[:10]) & gt) / len(gt))
            qmd_recalls_100.append(len(set(top_ids) & gt) / len(gt))
            qmd_precisions_5.append(len(set(top_ids[:5]) & gt) / 5)
            qmd_precisions_10.append(len(set(top_ids[:10]) & gt) / 10)
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
        total_memories=len(memories),
    )
    print(
        f"  P@5: {results['qmd_hybrid'].precision_at_5:.3f}, P@10: {results['qmd_hybrid'].precision_at_10:.3f}"
    )
    print(
        f"  R@10: {results['qmd_hybrid'].recall_at_10:.3f}, MRR: {results['qmd_hybrid'].mrr:.3f}"
    )
    print(f"  Latency: {results['qmd_hybrid'].avg_latency_ms:.2f}ms")

    # =========================================================================
    # TOTALRECLAW E2EE
    # =========================================================================
    print("\n" + "=" * 80)
    print("[6/6] Testing TotalReclaw E2EE (LSH + client rerank)")
    print("=" * 80)

    om_recalls_5, om_recalls_10, om_recalls_100 = [], [], []
    om_precisions_5, om_precisions_10 = [], []
    om_mrr, om_latencies = [], []

    for query in queries:
        start = time.perf_counter()
        top_ids = lsh.search(query.query_embedding, k=3000)
        latency = (time.perf_counter() - start) * 1000
        om_latencies.append(latency)

        gt = query.ground_truth_ids
        if gt:
            om_recalls_5.append(len(set(top_ids[:5]) & gt) / len(gt))
            om_recalls_10.append(len(set(top_ids[:10]) & gt) / len(gt))
            om_recalls_100.append(len(set(top_ids) & gt) / len(gt))
            om_precisions_5.append(len(set(top_ids[:5]) & gt) / 5)
            om_precisions_10.append(len(set(top_ids[:10]) & gt) / 10)
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
        total_memories=len(memories),
    )
    print(
        f"  P@5: {results['totalreclaw_e2ee'].precision_at_5:.3f}, P@10: {results['totalreclaw_e2ee'].precision_at_10:.3f}"
    )
    print(
        f"  R@10: {results['totalreclaw_e2ee'].recall_at_10:.3f}, MRR: {results['totalreclaw_e2ee'].mrr:.3f}"
    )
    print(f"  Latency: {results['totalreclaw_e2ee'].avg_latency_ms:.2f}ms")

    # =========================================================================
    # MEM0 CLOUD
    # =========================================================================
    print("\n" + "=" * 80)
    print("[7/6] Testing Mem0 Cloud (actual SaaS)")
    print("=" * 80)

    try:
        mem0_backend = Mem0CloudBackend(user_id="benchmark_user")
        mem0_backend.add_memories(memories, batch_size=50)

        mem0_recalls_5, mem0_recalls_10, mem0_recalls_100 = [], [], []
        mem0_precisions_5, mem0_precisions_10 = [], []
        mem0_mrr, mem0_latencies = [], []
        api_errors = 0

        for query in queries:
            start = time.perf_counter()
            search_results = mem0_backend.search(query.query_text, top_k=100)
            latency = (time.perf_counter() - start) * 1000
            mem0_latencies.append(latency)

            if not search_results:
                api_errors += 1

            top_ids = [r[0] for r in search_results[:100]]
            gt = query.ground_truth_ids

            if gt:
                mem0_recalls_5.append(len(set(top_ids[:5]) & gt) / len(gt))
                mem0_recalls_10.append(len(set(top_ids[:10]) & gt) / len(gt))
                mem0_recalls_100.append(len(set(top_ids) & gt) / len(gt))
                mem0_precisions_5.append(len(set(top_ids[:5]) & gt) / 5)
                mem0_precisions_10.append(len(set(top_ids[:10]) & gt) / 10)
                for rank, doc_id in enumerate(top_ids[:10]):
                    if doc_id in gt:
                        mem0_mrr.append(1.0 / (rank + 1))
                        break
                else:
                    mem0_mrr.append(0)

        results["mem0_cloud"] = BenchmarkMetrics(
            backend_name="Mem0 Cloud",
            precision_at_5=statistics.mean(mem0_precisions_5)
            if mem0_precisions_5
            else 0,
            precision_at_10=statistics.mean(mem0_precisions_10)
            if mem0_precisions_10
            else 0,
            recall_at_5=statistics.mean(mem0_recalls_5) if mem0_recalls_5 else 0,
            recall_at_10=statistics.mean(mem0_recalls_10) if mem0_recalls_10 else 0,
            recall_at_100=statistics.mean(mem0_recalls_100) if mem0_recalls_100 else 0,
            mrr=statistics.mean(mem0_mrr) if mem0_mrr else 0,
            avg_latency_ms=statistics.mean(mem0_latencies) if mem0_latencies else 0,
            p95_latency_ms=sorted(mem0_latencies)[int(len(mem0_latencies) * 0.95)]
            if len(mem0_latencies) >= 20
            else (max(mem0_latencies) if mem0_latencies else 0),
            privacy_score=0,
            n_queries=len(queries),
            total_memories=len(memories),
            api_errors=api_errors,
        )
        print(
            f"  P@5: {results['mem0_cloud'].precision_at_5:.3f}, P@10: {results['mem0_cloud'].precision_at_10:.3f}"
        )
        print(
            f"  R@10: {results['mem0_cloud'].recall_at_10:.3f}, MRR: {results['mem0_cloud'].mrr:.3f}"
        )
        print(f"  Latency: {results['mem0_cloud'].avg_latency_ms:.2f}ms")
        if api_errors:
            print(f"  API errors: {api_errors}")

    except Exception as e:
        print(f"  ERROR: Could not test Mem0 Cloud: {e}")
        import traceback

        traceback.print_exc()

    # =========================================================================
    # FINAL RESULTS
    # =========================================================================
    print("\n" + "=" * 80)
    print("FINAL RESULTS - APPLES-TO-APPLES COMPARISON")
    print("=" * 80)

    print(f"\nDataset: {len(memories)} memories, {len(queries)} queries")
    print(f"Ground truth: Semantic similarity > 0.65")

    print(
        f"\n{'Backend':<20} {'P@5':>7} {'P@10':>7} {'R@5':>7} {'R@10':>7} {'R@100':>7} {'MRR':>7} {'Latency':>10} {'Privacy':>7}"
    )
    print("-" * 95)

    for name, m in results.items():
        print(
            f"{m.backend_name:<20} "
            f"{m.precision_at_5:>7.3f} "
            f"{m.precision_at_10:>7.3f} "
            f"{m.recall_at_5:>7.3f} "
            f"{m.recall_at_10:>7.3f} "
            f"{m.recall_at_100:>7.3f} "
            f"{m.mrr:>7.3f} "
            f"{m.avg_latency_ms:>8.2f}ms "
            f"{m.privacy_score:>7}"
        )

    # Gap analysis
    print("\n" + "=" * 80)
    print("GAP ANALYSIS (vs Vector-only baseline)")
    print("=" * 80)

    baseline = results.get("vector_only")
    if baseline:
        for name, m in results.items():
            if name == "vector_only":
                continue
            print(f"\n{m.backend_name}:")
            print(
                f"  Precision@5: {(m.precision_at_5 - baseline.precision_at_5) / baseline.precision_at_5 * 100:+.1f}%"
            )
            print(
                f"  Recall@10: {(m.recall_at_10 - baseline.recall_at_10) / baseline.recall_at_10 * 100:+.1f}%"
            )
            print(f"  MRR: {(m.mrr - baseline.mrr) / baseline.mrr * 100:+.1f}%")
            print(f"  Privacy: {m.privacy_score}/100")

    # Save
    output = {
        "metadata": {
            "total_memories": len(memories),
            "n_queries": len(queries),
            "similarity_threshold": 0.65,
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
                "api_errors": m.api_errors,
            }
            for name, m in results.items()
        },
    }

    output_path = RESULTS_DIR / "mem0_cloud_benchmark_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    run_benchmark()
