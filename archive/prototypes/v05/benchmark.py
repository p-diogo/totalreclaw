"""
Performance benchmarks for OpenMemory v0.5

Measures:
- Multi-variant blind index generation latency
- Three-pass search latency breakdown
- Accuracy metrics (F1, MRR) vs baselines
"""

import time
import numpy as np
from typing import List, Dict, Any, Callable
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class BenchmarkResult:
    """Result from a benchmark run."""
    name: str
    latency_ms: float
    operations_per_second: float
    metadata: Dict[str, Any]


@dataclass
class SearchMetrics:
    """Search quality metrics."""
    precision: float
    recall: float
    f1: float
    mrr: float  # Mean Reciprocal Rank
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float


class OpenMemoryBenchmark:
    """
    Benchmark suite for OpenMemory v0.5.

    Compares:
    - v0.2 (two-pass) vs v0.5 (three-pass)
    - With/without LLM features
    - Latency breakdown by pass
    """

    def __init__(self, client_v02, client_v05, server, embedding_model):
        """
        Initialize benchmark.

        Args:
            client_v02: OpenMemory v0.2 client
            client_v05: OpenMemory v0.5 client
            server: Mock server instance
            embedding_model: Embedding model
        """
        self.client_v02 = client_v02
        self.client_v05 = client_v05
        self.server = server
        self.embedding_model = embedding_model

        self.results = defaultdict(list)

    def benchmark_blind_index_generation(
        self,
        memories: List[str],
        use_llm: bool = False
    ) -> BenchmarkResult:
        """
        Benchmark blind index generation.

        Args:
            memories: List of memory texts
            use_llm: Whether to use LLM for variant generation

        Returns:
            BenchmarkResult with timing
        """
        from openmemory_v05.multi_variant_indices import MultiVariantBlindIndexGenerator

        blind_key = self.client_v05.crypto.derive_keys().blind_key
        generator = MultiVariantBlindIndexGenerator(
            blind_key=blind_key,
            llm_client=self.client_v05.llm_client if use_llm else None
        )

        start = time.time()
        for memory in memories:
            generator.generate_blind_indices(memory, use_llm=use_llm)
        elapsed = time.time() - start

        latency_ms = (elapsed / len(memories)) * 1000
        ops_per_sec = len(memories) / elapsed

        return BenchmarkResult(
            name=f"blind_index_generation_{'llm' if use_llm else 'regex'}",
            latency_ms=latency_ms,
            operations_per_second=ops_per_sec,
            metadata={
                "num_memories": len(memories),
                "use_llm": use_llm
            }
        )

    def benchmark_search(
        self,
        queries: List[str],
        ground_truth: Dict[str, List[str]],
        client,
        use_llm_rerank: bool = False
    ) -> SearchMetrics:
        """
        Benchmark search quality and latency.

        Args:
            queries: List of search queries
            ground_truth: Dict mapping query -> relevant memory IDs
            client: Client to test (v0.2 or v0.5)
            use_llm_rerank: Whether to use LLM reranking (v0.5 only)

        Returns:
            SearchMetrics with quality and latency
        """
        latencies = []
        all_precisions = []
        all_recalls = []
        all_f1s = []
        all_rrs = []  # Reciprocal ranks

        for query in queries:
            start = time.time()

            # Search
            results = client.search(
                query,
                self.server,
                top_k=5,
                use_llm_rerank=use_llm_rerank
            )

            elapsed = time.time() - start
            latencies.append(elapsed * 1000)  # Convert to ms

            # Calculate metrics
            relevant_ids = set(ground_truth.get(query, []))
            retrieved_ids = {r.memory_id for r in results}

            # Precision, Recall, F1
            if retrieved_ids:
                precision = len(relevant_ids & retrieved_ids) / len(retrieved_ids)
            else:
                precision = 0.0

            if relevant_ids:
                recall = len(relevant_ids & retrieved_ids) / len(relevant_ids)
            else:
                recall = 1.0  # No relevant docs, perfect recall

            if precision + recall > 0:
                f1 = 2 * (precision * recall) / (precision + recall)
            else:
                f1 = 0.0

            all_precisions.append(precision)
            all_recalls.append(recall)
            all_f1s.append(f1)

            # Reciprocal Rank
            rr = 0.0
            for rank, result in enumerate(results, 1):
                if result.memory_id in relevant_ids:
                    rr = 1.0 / rank
                    break
            all_rrs.append(rr)

        # Calculate aggregates
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)

        return SearchMetrics(
            precision=np.mean(all_precisions),
            recall=np.mean(all_recalls),
            f1=np.mean(all_f1s),
            mrr=np.mean(all_rrs),
            latency_p50_ms=latencies_sorted[int(n * 0.5)],
            latency_p95_ms=latencies_sorted[int(n * 0.95)],
            latency_p99_ms=latencies_sorted[int(n * 0.99)]
        )

    def benchmark_three_pass_breakdown(
        self,
        query: str,
        client_v05
    ) -> Dict[str, float]:
        """
        Break down latency by pass for three-pass search.

        Args:
            query: Search query
            client_v05: v0.5 client

        Returns:
            Dict with timing for each pass
        """
        timings = {}

        # Generate query embedding
        start = time.time()
        query_vector = client_v05._generate_embedding(query)
        timings["query_embedding"] = (time.time() - start) * 1000

        # Generate blind indices
        start = time.time()
        query_blind_hashes = list(
            client_v05.blind_index_gen.generate_query_blind_indices(query)
        )
        timings["blind_index_gen"] = (time.time() - start) * 1000

        # Pass 1: Remote search
        start = time.time()
        candidates = self.server.search(
            vault_id=client_v05.vault_id,
            query_vector=query_vector,
            blind_hashes=query_blind_hashes,
            limit=250
        )
        timings["pass1_remote"] = (time.time() - start) * 1000

        # Pass 2: Local reranking
        stored_memories = {
            c['memory_id']: (c['ciphertext'], c['nonce'])
            for c in candidates
        }
        pass1_candidates = [
            (c['memory_id'], c['vector_score'], c['is_blind_match'])
            for c in candidates
        ]

        start = time.time()
        pass2_results = client_v05.search_engine.pass2_local_rerank(
            candidates=pass1_candidates,
            query=query,
            stored_memories=stored_memories,
            top_k=50
        )
        timings["pass2_local"] = (time.time() - start) * 1000

        # Pass 3: LLM reranking
        if client_v05.reranker:
            candidates_llm = [
                {'id': r.memory_id, 'snippet': r.content[:700], 'score': r.score}
                for r in pass2_results[:50]
            ]

            start = time.time()
            pass3_results = client_v05.reranker.rerank(query, candidates_llm)
            timings["pass3_llm"] = (time.time() - start) * 1000
        else:
            timings["pass3_llm"] = 0.0

        timings["total"] = sum(timings.values())

        return timings

    def run_full_benchmark(
        self,
        memories: List[str],
        queries: List[str],
        ground_truth: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Run complete benchmark suite.

        Args:
            memories: List of memories to store
            queries: List of search queries
            ground_truth: Ground truth relevance

        Returns:
            Dict with all benchmark results
        """
        # Store memories
        for memory in memories:
            self.client_v05.store_memory(memory, self.server)

        results = {
            "blind_index_generation": {},
            "search_metrics": {},
            "latency_breakdown": {}
        }

        # Benchmark blind index generation
        print("Benchmarking blind index generation...")
        results["blind_index_generation"]["regex"] = self.benchmark_blind_index_generation(
            memories[:10],  # Sample for speed
            use_llm=False
        )

        if self.client_v05.llm_client:
            results["blind_index_generation"]["llm"] = self.benchmark_blind_index_generation(
                memories[:10],
                use_llm=True
            )

        # Benchmark search - v0.2
        print("Benchmarking v0.2 search...")
        results["search_metrics"]["v02"] = self.benchmark_search(
            queries,
            ground_truth,
            self.client_v02,
            use_llm_rerank=False
        )

        # Benchmark search - v0.5 without LLM
        print("Benchmarking v0.5 search (no LLM)...")
        results["search_metrics"]["v05_no_llm"] = self.benchmark_search(
            queries,
            ground_truth,
            self.client_v05,
            use_llm_rerank=False
        )

        # Benchmark search - v0.5 with LLM
        if self.client_v05.llm_client:
            print("Benchmarking v0.5 search (with LLM)...")
            results["search_metrics"]["v05_with_llm"] = self.benchmark_search(
                queries,
                ground_truth,
                self.client_v05,
                use_llm_rerank=True
            )

        # Latency breakdown
        print("Measuring three-pass latency breakdown...")
        results["latency_breakdown"]["sample_query"] = self.benchmark_three_pass_breakdown(
            queries[0] if queries else "test query",
            self.client_v05
        )

        return results

    def print_results(self, results: Dict[str, Any]):
        """Print benchmark results in a readable format."""
        print("\n" + "="*60)
        print("OPENMEMORY v0.5 BENCHMARK RESULTS")
        print("="*60)

        # Blind index generation
        print("\nBlind Index Generation:")
        for name, result in results["blind_index_generation"].items():
            print(f"  {name}:")
            print(f"    Latency: {result.latency_ms:.2f} ms/op")
            print(f"    Throughput: {result.operations_per_second:.2f} ops/sec")

        # Search metrics
        print("\nSearch Quality Metrics:")
        for name, metrics in results["search_metrics"].items():
            print(f"  {name}:")
            print(f"    F1: {metrics.f1:.4f}")
            print(f"    MRR: {metrics.mrr:.4f}")
            print(f"    Latency p50: {metrics.latency_p50_ms:.2f} ms")
            print(f"    Latency p95: {metrics.latency_p95_ms:.2f} ms")

        # Latency breakdown
        print("\nThree-Pass Latency Breakdown:")
        breakdown = results["latency_breakdown"]["sample_query"]
        for pass_name, timing in breakdown.items():
            print(f"  {pass_name}: {timing:.2f} ms")
        print(f"  TOTAL: {breakdown['total']:.2f} ms")

        print("="*60)


def run_demo_benchmark():
    """Run a demo benchmark with sample data."""
    from openmemory_v02.client import OpenMemoryClientV02
    from openmemory_v05.client import OpenMemoryClientV05
    from openmemory_v02.server import MockOpenMemoryServer

    # Setup
    master_password = "demo_password_for_benchmark"
    embedding_model = MockEmbeddingModel()

    client_v02 = OpenMemoryClientV02(
        master_password=master_password,
        embedding_model=embedding_model
    )

    client_v05 = OpenMemoryClientV05(
        master_password=master_password,
        embedding_model=embedding_model,
        llm_client=MockLLMClient()
    )

    server = MockOpenMemoryServer()
    server.create_vault(vault_id=client_v05.vault_id)
    client_v02.vault_id = client_v05.vault_id

    # Sample data
    memories = [
        "API Configuration:\n- Base URL: https://api.example.com/v1\n- Rate limit: 100 req/min\n- Contact: sarah@example.com",
        "Deployment Pipeline:\n- Use Docker containers\n- Deploy to production via CI/CD\n- Error 503 indicates rate limit exceeded",
        "Error Codes:\n- ERR-503: Service Unavailable\n- ERR-404: Not Found\n- ERR-500: Internal Server Error",
    ]

    queries = [
        "API configuration",
        "deployment",
        "error 503",
    ]

    ground_truth = {
        "API configuration": ["memory_0"],  # Would be actual IDs
        "deployment": ["memory_1"],
        "error 503": ["memory_1", "memory_2"],
    }

    # Run benchmark
    benchmark = OpenMemoryBenchmark(client_v02, client_v05, server, embedding_model)
    results = benchmark.run_full_benchmark(memories, queries, ground_truth)
    benchmark.print_results(results)


class MockEmbeddingModel:
    """Mock embedding model for demo."""
    def encode(self, texts):
        import hashlib
        embeddings = []
        for text in texts:
            hash_val = hashlib.md5(text.encode()).digest()
            emb = [(b - 128) / 128.0 for b in hash_val for _ in range(24)]
            embeddings.append(emb[:384])
        return np.array(embeddings)


class MockLLMClient:
    """Mock LLM client for demo."""
    def complete(self, prompt):
        if "variant" in prompt.lower():
            return '{"entities": [{"original": "test", "type": "config", "variants": ["test", "config"]}]}'
        return '{"results": [{"id": "1", "reason": "Relevant"}]}'


if __name__ == "__main__":
    run_demo_benchmark()
