"""CLI entry point for OMBH."""

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ombh.backends.base import BackendStats, BackendType
from ombh.backends.registry import get_backend, list_backends
from ombh.dataset.loader import Conversation
from ombh.dataset.synthetic import SyntheticGenerator
from ombh.reports.dashboard import BenchmarkResult, DashboardConfig, DashboardGenerator
from ombh.simulator.orchestrator import BenchmarkOrchestrator


def load_config(config_path: Optional[Path] = None) -> dict:
    """Load configuration from file."""
    if config_path is None:
        config_path = Path(__file__).parent / "config" / "config.yaml"

    if not config_path.exists():
        return {
            "extraction_interval": 5,
            "query_interval": 10,
            "retrieval_k": 8,
        }

    with open(config_path) as f:
        return yaml.safe_load(f)


def generate_synthetic_conversations(num_conversations: int, seed: int) -> List[Conversation]:
    """Generate synthetic conversations for benchmarking."""
    generator = SyntheticGenerator(seed=seed)
    conversations = []

    for i in range(num_conversations):
        conv_data = generator.generate_conversation(
            conversation_id=f"bench_{i:04d}",
            num_sessions=random.randint(3, 5),
            turns_per_session=random.randint(15, 25),
        )
        conversations.append(
            Conversation(
                conversation_id=conv_data["conversation_id"],
                sessions=conv_data["sessions"],
                ground_truth_queries=conv_data["ground_truth_queries"],
                metadata=conv_data.get("metadata"),
            )
        )

    return conversations


def stats_to_benchmark_result(
    name: str, stats: BackendStats, accuracy: float = 0.0
) -> BenchmarkResult:
    """Convert BackendStats to BenchmarkResult for dashboard."""
    return BenchmarkResult(
        backend_name=name,
        accuracy=accuracy,
        latency_ms=stats.avg_retrieve_latency_ms or 50.0,
        storage_bytes=stats.storage_bytes or 0,
        cost_usd=stats.cost_estimate_usd or 0.0,
        privacy_score=stats.privacy_score,
    )


async def run_benchmark(
    systems: list[str],
    dataset: str,
    num_conversations: int,
    output: Path,
    config: dict,
    seed: int = 42,
    dry_run: bool = False,
) -> None:
    """Run the benchmark."""
    print(f"Running benchmark with systems: {systems}")
    print(f"Dataset: {dataset}")
    print(f"Number of conversations: {num_conversations}")
    print(f"Output: {output}")
    print(f"Seed: {seed}")
    print(f"Dry run: {dry_run}")
    print()

    random.seed(seed)

    backends: Dict[str, Any] = {}
    for sys_name in systems:
        backend_type = BackendType(sys_name)
        backend = get_backend(backend_type)

        print(f"Checking {sys_name} health...")
        if dry_run:
            backends[sys_name] = backend
            print(f"  {sys_name}: OK (dry run)")
        elif await backend.health_check():
            backends[sys_name] = backend
            print(f"  {sys_name}: OK")
        else:
            print(f"  WARNING: {sys_name} backend unhealthy, skipping...")

    if not backends:
        print("ERROR: No healthy backends available")
        sys.exit(1)

    print(f"\nGenerating {num_conversations} synthetic conversations...")
    conversations = generate_synthetic_conversations(num_conversations, seed)
    print(f"Generated {len(conversations)} conversations")

    orchestrator = BenchmarkOrchestrator(backends=backends, config=config)

    print("\nResetting backends...")
    await orchestrator.reset_all()

    print("Running simulation...")
    all_results: Dict[str, List[BenchmarkResult]] = {name: [] for name in backends}

    for i, conv in enumerate(conversations):
        if (i + 1) % 5 == 0 or i == 0:
            print(f"  Processing conversation {i + 1}/{len(conversations)}...")

        if dry_run:
            for name, backend in backends.items():
                stats = await backend.get_stats()
                result = stats_to_benchmark_result(name, stats)
                all_results[name].append(result)
        else:
            stats_dict = await orchestrator.run_conversation(conv)
            for name, stats in stats_dict.items():
                result = stats_to_benchmark_result(name, stats)
                all_results[name].append(result)

    print(f"\nGenerating dashboard at {output}...")
    dashboard = DashboardGenerator()
    dashboard_config = DashboardConfig(
        title="TotalReclaw Benchmark Results",
        dataset=dataset,
        num_conversations=num_conversations,
        seed=seed,
    )
    dashboard.generate(all_results, output, dashboard_config)

    print(f"\nBenchmark complete!")
    print(f"Results saved to: {output}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="TotalReclaw Benchmark Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--systems",
        type=str,
        default="totalreclaw_e2ee,openclaw_qmd,openclaw_mem0",
        help="Comma-separated list of systems to benchmark",
    )

    parser.add_argument(
        "--dataset",
        type=str,
        default="anchor+locomo+synthetic",
        help="Dataset(s) to use (comma or + separated)",
    )

    parser.add_argument(
        "--num-conversations",
        type=int,
        default=10,
        help="Number of conversations to run",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="reports/benchmark.html",
        help="Output path for reports",
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to config file",
    )

    parser.add_argument(
        "--list-systems",
        action="store_true",
        help="List available systems",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without requiring server connection",
    )

    args = parser.parse_args()

    if args.list_systems:
        print("Available systems:")
        for sys_name in list_backends():
            print(f"  - {sys_name}")
        return

    config = load_config(Path(args.config) if args.config else None)

    asyncio.run(
        run_benchmark(
            systems=args.systems.split(","),
            dataset=args.dataset,
            num_conversations=args.num_conversations,
            output=Path(args.output),
            config=config,
            seed=args.seed,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
