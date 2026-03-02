#!/usr/bin/env python3
"""
LLM Reranking Bottleneck Benchmark (Scenario S8)

This script isolates and measures the LLM reranking performance bottleneck
using OpenRouter API with the arcee-ai/trinity-large-preview:free model.

Tests varying candidate counts to understand scaling behavior:
- 10 candidates
- 20 candidates
- 30 candidates
- 50 candidates

Measures for each configuration:
- Per-query latency (p50/p95/p99)
- Token counts (input/output from API response)
- API call time
- Total reranking time

Output: results/llm_rerank_benchmark.json
"""

import json
import os
import sys
import time
import statistics
import requests
from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TESTBED_DIR = PROJECT_ROOT / "testbed"
sys.path.insert(0, str(PROJECT_ROOT))

# Paths
CONFIG_DIR = TESTBED_DIR / "config"
DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"
API_KEYS_FILE = CONFIG_DIR / "api_keys.env"

# Model configuration
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "arcee-ai/trinity-large-preview:free"


@dataclass
class LLMMetrics:
    """Metrics for a single LLM reranking call."""
    api_call_time_ms: float
    total_time_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    candidate_count: int
    query_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkConfig:
    """Benchmark configuration for a specific candidate count."""
    candidate_count: int
    latencies_ms: List[float] = field(default_factory=list)
    api_times_ms: List[float] = field(default_factory=list)
    input_tokens: List[int] = field(default_factory=list)
    output_tokens: List[int] = field(default_factory=list)
    total_tokens: List[int] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p50_latency_ms(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def p95_latency_ms(self) -> float:
        if len(self.latencies_ms) < 2:
            return self.avg_latency_ms
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(0.95 * len(sorted_latencies))
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p99_latency_ms(self) -> float:
        if len(self.latencies_ms) < 2:
            return self.avg_latency_ms
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(0.99 * len(sorted_latencies))
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def avg_api_time_ms(self) -> float:
        return statistics.mean(self.api_times_ms) if self.api_times_ms else 0.0

    @property
    def avg_input_tokens(self) -> float:
        return statistics.mean(self.input_tokens) if self.input_tokens else 0.0

    @property
    def avg_output_tokens(self) -> float:
        return statistics.mean(self.output_tokens) if self.output_tokens else 0.0

    @property
    def avg_total_tokens(self) -> float:
        return statistics.mean(self.total_tokens) if self.total_tokens else 0.0

    def add_metrics(self, metrics: LLMMetrics):
        """Add metrics from a single query."""
        self.latencies_ms.append(metrics.total_time_ms)
        self.api_times_ms.append(metrics.api_call_time_ms)
        self.input_tokens.append(metrics.input_tokens)
        self.output_tokens.append(metrics.output_tokens)
        self.total_tokens.append(metrics.total_tokens)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "num_queries": len(self.latencies_ms),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "avg_api_time_ms": round(self.avg_api_time_ms, 2),
            "avg_input_tokens": round(self.avg_input_tokens, 1),
            "avg_output_tokens": round(self.avg_output_tokens, 1),
            "avg_total_tokens": round(self.avg_total_tokens, 1),
        }


class OpenRouterLLMClient:
    """Client for OpenRouter API."""

    def __init__(self, api_key: str, model: str = MODEL):
        self.api_key = api_key
        self.model = model
        self.api_url = OPENROUTER_API_URL

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        max_tokens: int = 500
    ) -> Tuple[List[int], LLMMetrics]:
        """
        Rerank candidates using LLM.

        Args:
            query: Search query
            candidates: List of candidate dicts with 'id' and 'content' keys
            max_tokens: Maximum tokens for response

        Returns:
            (reranked_ids, metrics) where reranked_ids is list of doc IDs
        """
        total_start = time.perf_counter()

        # Build the reranking prompt
        prompt = self._build_rerank_prompt(query, candidates)

        # Make API call
        api_start = time.perf_counter()
        response_data = self._call_api(prompt, max_tokens)
        api_time = (time.perf_counter() - api_start) * 1000

        # Parse response to get reranked order
        reranked_ids = self._parse_rerank_response(response_data, candidates)

        # Extract token usage
        usage = response_data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        total_time = (time.perf_counter() - total_start) * 1000

        metrics = LLMMetrics(
            api_call_time_ms=api_time,
            total_time_ms=total_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            candidate_count=len(candidates),
            query_id=""
        )

        return reranked_ids, metrics

    def _build_rerank_prompt(self, query: str, candidates: List[Dict]) -> str:
        """Build the reranking prompt."""
        # Truncate candidate content to fit in context
        candidate_descriptions = []
        for i, cand in enumerate(candidates):
            content = cand.get('content', '')[:300].replace('\n', ' ')
            candidate_descriptions.append(
                f"[{cand['id']}] {content}"
            )

        candidates_text = "\n".join(candidate_descriptions)

        prompt = f"""You are a search result reranker. Given the query and candidate documents below,
reorder them by relevance. Return ONLY the IDs in order of relevance (most relevant first).

Query: "{query}"

Candidates:
{candidates_text}

Return the IDs in reranked order (comma-separated, most relevant first).
Example format: id1, id2, id3, id4, id5
"""
        return prompt

    def _call_api(self, prompt: str, max_tokens: int) -> Dict[str, Any]:
        """Make the API call to OpenRouter."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://totalreclaw.ai",
        }

        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }

        response = requests.post(
            self.api_url,
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        return response.json()

    def _parse_rerank_response(
        self,
        response_data: Dict[str, Any],
        candidates: List[Dict]
    ) -> List[int]:
        """Parse the API response to extract reranked document IDs."""
        try:
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Extract IDs from response
            # Try to find comma-separated numbers
            import re
            numbers = re.findall(r'\d+', content)

            if numbers:
                # Filter to valid candidate IDs
                candidate_ids = {cand['id'] for cand in candidates}
                reranked = [int(n) for n in numbers if int(n) in candidate_ids]

                # If we got some results, return them
                if reranked:
                    return reranked

            # Fallback: return original order
            return [cand['id'] for cand in candidates]

        except Exception as e:
            print(f"  Warning: Failed to parse rerank response: {e}")
            return [cand['id'] for cand in candidates]


def load_api_key() -> str:
    """Load OpenRouter API key from config file."""
    if API_KEYS_FILE.exists():
        with open(API_KEYS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('OPENROUTER_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")

    # Fallback: check environment variable
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if api_key:
        return api_key

    raise FileNotFoundError(
        f"OpenRouter API key not found. Please create {API_KEYS_FILE} with:\n"
        "OPENROUTER_API_KEY=sk-or-v1-your-key-here\n"
        "Or set the OPENROUTER_API_KEY environment variable."
    )


def load_sample_queries(num_queries: int = 20) -> List[Dict]:
    """Load a sample of queries for benchmarking."""
    queries_file = DATA_DIR / "queries" / "test_queries.json"

    if not queries_file.exists():
        raise FileNotFoundError(f"Queries file not found: {queries_file}")

    with open(queries_file, 'r') as f:
        all_queries = json.load(f)

    return all_queries[:num_queries]


def load_sample_documents(num_docs: int = 100) -> List[Dict]:
    """Load sample documents for candidate generation."""
    # Try memories.json first, then fall back to memories_1500_final.json
    memories_file = DATA_DIR / "memories.json"

    if not memories_file.exists():
        memories_file = DATA_DIR / "processed" / "memories_1500_final.json"

    if not memories_file.exists():
        raise FileNotFoundError(f"Memories file not found. Tried: {DATA_DIR}/memories.json and {memories_file}")

    with open(memories_file, 'r') as f:
        data = json.load(f)
        documents = data.get('memories', data)

    return documents[:num_docs]


def generate_candidates(
    query: str,
    documents: List[Dict],
    candidate_count: int
) -> List[Dict[str, Any]]:
    """
    Generate candidate documents for reranking.

    In production, this would be the output of Pass 2 (BM25 + RRF).
    For benchmarking, we simulate this by selecting random documents.
    """
    import random

    # Create a deterministic seed based on query
    seed = hash(query) % 10000
    random.seed(seed)

    # Select random candidates
    if len(documents) <= candidate_count:
        candidates = documents[:]
    else:
        candidates = random.sample(documents, candidate_count)

    # Format for LLM
    return [
        {
            'id': i,  # Use index as ID
            'content': doc.get('content', str(doc))
        }
        for i, doc in enumerate(candidates)
    ]


def run_benchmark(
    client: OpenRouterLLMClient,
    queries: List[Dict],
    documents: List[Dict],
    candidate_counts: List[int]
) -> Dict[str, BenchmarkConfig]:
    """Run the benchmark for all candidate count configurations."""

    configs = {
        f"candidates_{count}": BenchmarkConfig(candidate_count=count)
        for count in candidate_counts
    }

    total_runs = len(queries) * len(candidate_counts)
    current_run = 0

    print(f"Running LLM rerank benchmark:")
    print(f"  Model: {client.model}")
    print(f"  Queries: {len(queries)}")
    print(f"  Candidate counts: {candidate_counts}")
    print(f"  Total runs: {total_runs}")
    print()

    for candidate_count in candidate_counts:
        config_key = f"candidates_{candidate_count}"
        config = configs[config_key]

        print(f"Testing with {candidate_count} candidates...")

        for i, query in enumerate(queries):
            query_id = query.get('id', f'q{i:03d}')
            query_text = query['text']

            # Generate candidates
            candidates = generate_candidates(query_text, documents, candidate_count)

            try:
                # Run reranking
                reranked_ids, metrics = client.rerank(query_text, candidates)

                # Update metrics with query_id
                metrics.query_id = query_id
                config.add_metrics(metrics)

                current_run += 1
                progress = (current_run / total_runs) * 100

                print(f"  [{i+1}/{len(queries)}] {query_id}: {metrics.total_time_ms:.0f}ms "
                      f"({metrics.input_tokens}+{metrics.output_tokens} tokens) "
                      f"[{progress:.0f}% complete]")

            except Exception as e:
                print(f"  [{i+1}/{len(queries)}] {query_id}: ERROR - {e}")
                continue

        print(f"  Avg latency: {config.avg_latency_ms:.0f}ms "
              f"(p50: {config.p50_latency_ms:.0f}ms, "
              f"p95: {config.p95_latency_ms:.0f}ms)")
        print()

    return configs


def analyze_scaling(configs: Dict[str, BenchmarkConfig]) -> Dict[str, Any]:
    """Analyze how latency scales with candidate count."""

    sorted_configs = sorted(
        [(k, v) for k, v in configs.items()],
        key=lambda x: x[1].candidate_count
    )

    analysis = {
        "scaling_factor": {},
        "bottleneck_identified": False,
        "recommendation": ""
    }

    # Calculate scaling factors
    if len(sorted_configs) >= 2:
        base_config = sorted_configs[0][1]
        base_count = base_config.candidate_count
        base_latency = base_config.avg_latency_ms

        scaling_factors = []

        for config_key, config in sorted_configs[1:]:
            ratio = config.candidate_count / base_count
            latency_ratio = config.avg_latency_ms / base_latency if base_latency > 0 else 0

            scaling_factors.append({
                "from_count": base_count,
                "to_count": config.candidate_count,
                "count_ratio": ratio,
                "latency_ratio": latency_ratio,
                "scaling_type": "linear" if abs(latency_ratio - ratio) < 0.3 * ratio else "non-linear"
            })

        analysis["scaling_factor"] = scaling_factors

    # Identify bottleneck
    avg_latencies = [c.avg_latency_ms for c in configs.values()]
    max_latency = max(avg_latencies)

    if max_latency > 5000:  # 5 seconds is too slow
        analysis["bottleneck_identified"] = True

    # Generate recommendation
    if max_latency > 5000:
        analysis["recommendation"] = (
            "LLM reranking is a significant bottleneck at high candidate counts. "
            "Consider: (1) Limiting reranking to top-20 candidates, "
            "(2) Using a faster model, or (3) Implementing cache for frequent queries."
        )
    elif max_latency > 2000:
        analysis["recommendation"] = (
            "LLM reranking adds moderate latency. Acceptable for low-QPS scenarios, "
            "but consider optimization for production use."
        )
    else:
        analysis["recommendation"] = (
            "LLM reranking performance is acceptable for the tested candidate counts. "
            "Can be used in production with appropriate rate limiting."
        )

    return analysis


def save_results(
    configs: Dict[str, BenchmarkConfig],
    analysis: Dict[str, Any],
    model: str,
    output_path: Path
):
    """Save benchmark results to JSON file."""

    results = {
        "model": model,
        "api_url": OPENROUTER_API_URL,
        "timestamp": time.time(),
        "configurations": {
            key: config.to_dict()
            for key, config in configs.items()
        },
        "analysis": analysis
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {output_path}")


def main():
    """Main entry point for the LLM rerank benchmark."""

    print("=" * 70)
    print("LLM RERANKING BOTTLENECK BENCHMARK (Scenario S8)")
    print("=" * 70)
    print()

    # Load API key
    try:
        api_key = load_api_key()
        print(f"API key loaded from: {API_KEYS_FILE}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nPlease create the API keys file:")
        print(f"  {API_KEYS_FILE}")
        print("With content:")
        print("  OPENROUTER_API_KEY=sk-or-v1-your-key-here")
        sys.exit(1)

    # Create LLM client
    client = OpenRouterLLMClient(api_key)

    # Load data
    print("Loading test data...")
    queries = load_sample_queries(num_queries=20)
    documents = load_sample_documents(num_docs=100)
    print(f"  Loaded {len(queries)} queries")
    print(f"  Loaded {len(documents)} documents")
    print()

    # Candidate counts to test
    candidate_counts = [10, 20, 30, 50]

    # Run benchmark
    start_time = time.time()
    configs = run_benchmark(client, queries, documents, candidate_counts)
    elapsed = time.time() - start_time

    # Analyze scaling
    analysis = analyze_scaling(configs)

    # Save results
    output_path = RESULTS_DIR / "llm_rerank_benchmark.json"
    save_results(configs, analysis, MODEL, output_path)

    # Print summary
    print()
    print("=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)
    print(f"Total time: {elapsed:.1f} seconds")
    print(f"Model: {MODEL}")
    print()

    print("Results Summary:")
    print("-" * 70)
    print(f"{'Candidates':<12} {'Queries':<8} {'Avg Latency':<12} {'p50':<10} {'p95':<10} {'p99':<10}")
    print("-" * 70)

    for key in sorted(configs.keys(), key=lambda k: configs[k].candidate_count):
        config = configs[key]
        print(f"{config.candidate_count:<12} "
              f"{len(config.latencies_ms):<8} "
              f"{config.avg_latency_ms:<12.0f} "
              f"{config.p50_latency_ms:<10.0f} "
              f"{config.p95_latency_ms:<10.0f} "
              f"{config.p99_latency_ms:<10.0f}")

    print("-" * 70)
    print()

    print("Analysis:")
    print(f"  Bottleneck identified: {analysis['bottleneck_identified']}")
    print(f"  Recommendation: {analysis['recommendation']}")
    print()

    # Print token usage
    print("Token Usage:")
    for key in sorted(configs.keys(), key=lambda k: configs[k].candidate_count):
        config = configs[key]
        print(f"  {key}: "
              f"Avg {config.avg_input_tokens:.0f} input + "
              f"{config.avg_output_tokens:.0f} output = "
              f"{config.avg_total_tokens:.0f} total tokens")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
