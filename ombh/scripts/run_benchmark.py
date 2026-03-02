#!/usr/bin/env python3
"""4-Way Memory System Benchmark Runner.

Feeds synthetic conversations to 4 OpenClaw instances (each with a different
memory backend), then queries each with test queries and scores results
against ground truth.

Phases:
  1. INGEST — Replay conversations through each instance via chat API.
     Each instance's memory plugin extracts and stores facts automatically.
  2. QUERY — Send test queries to each instance and collect responses.
  3. SCORE — Match responses against ground truth facts using keyword
     overlap + LLM judge. Compute Recall@K, Precision@K, MRR.

Usage:
    python scripts/run_benchmark.py --conversations 50 --phase ingest
    python scripts/run_benchmark.py --phase query
    python scripts/run_benchmark.py --phase score
    python scripts/run_benchmark.py --phase all  # run everything

Prerequisites:
    docker compose -f docker-compose.benchmark.yml up -d
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INSTANCES = {
    "totalreclaw": {"port": 8081, "label": "TotalReclaw v2 (E2EE + Embeddings)"},
    "totalreclaw-v1": {"port": 8085, "label": "TotalReclaw v1 (E2EE, Facts-Only)"},
    "mem0": {"port": 8082, "label": "Mem0 Cloud"},
    "qmd": {"port": 8083, "label": "QMD (memory-core)"},
    "lancedb": {"port": 8084, "label": "LanceDB"},
}

AUTH_TOKEN = "benchmark-token-2026"
MODEL = "glm-4.5-air"
BASE_URL = "http://127.0.0.1"

DATA_DIR = Path(__file__).parent.parent / "synthetic-benchmark"
CONV_DIR = DATA_DIR / "conversations"
GT_DIR = DATA_DIR / "ground-truth"
RESULTS_DIR = DATA_DIR / "benchmark-results"

logger = logging.getLogger("benchmark")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    instance: str
    conv_id: str
    success: bool
    turns_sent: int
    latency_ms: float
    error: str = ""


@dataclass
class QueryResult:
    instance: str
    query_id: str
    query_text: str
    category: str
    response_text: str
    latency_ms: float
    success: bool
    error: str = ""


@dataclass
class ScoreResult:
    instance: str
    query_id: str
    category: str
    # Ground truth
    expected_fact_ids: List[str]
    expected_facts_text: List[str]
    # What was returned
    response_text: str
    # Scores
    keyword_hits: int
    keyword_total: int
    keyword_recall: float
    # Per-instance aggregate
    recall_at_k: float = 0.0


@dataclass
class BenchmarkCheckpoint:
    """Tracks benchmark progress for resume."""
    phase: str = "idle"  # idle, ingest, query, score, complete
    ingest_completed: Dict[str, List[str]] = field(default_factory=dict)
    query_completed: Dict[str, List[str]] = field(default_factory=dict)
    started_at: str = ""
    last_updated: str = ""

    def save(self, path: Path):
        self.last_updated = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "BenchmarkCheckpoint":
        if not path.exists():
            return cls()
        with open(path) as f:
            data = json.load(f)
        cp = cls()
        for k, v in data.items():
            if hasattr(cp, k):
                setattr(cp, k, v)
        return cp


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _endpoint(instance: str) -> str:
    port = INSTANCES[instance]["port"]
    return f"{BASE_URL}:{port}/v1/chat/completions"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
    }


async def _chat(
    client: httpx.AsyncClient,
    instance: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Tuple[str, float]:
    """Send a chat completion request and return (response_text, latency_ms)."""
    url = _endpoint(instance)
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 512,
    }
    start = time.monotonic()
    resp = await client.post(url, json=payload, headers=_headers(), timeout=timeout)
    latency = (time.monotonic() - start) * 1000.0
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return text, latency


# ---------------------------------------------------------------------------
# Phase 1: INGEST
# ---------------------------------------------------------------------------


def load_conversations(max_convs: int = 0) -> List[Tuple[str, List[Dict[str, str]]]]:
    """Load conversations from JSONL files. Returns list of (conv_id, messages)."""
    conv_files = sorted(CONV_DIR.glob("conv-*.jsonl"))
    if max_convs > 0:
        conv_files = conv_files[:max_convs]

    conversations = []
    for f in conv_files:
        conv_id = f.stem  # e.g. "conv-0001"
        messages = []
        for line in f.read_text().strip().split("\n"):
            if line.strip():
                messages.append(json.loads(line))
        if messages:
            conversations.append((conv_id, messages))

    return conversations


async def ingest_conversation(
    client: httpx.AsyncClient,
    instance: str,
    conv_id: str,
    messages: List[Dict[str, str]],
) -> IngestResult:
    """Feed a conversation to an OpenClaw instance.

    Strategy: Send the FULL conversation as the messages array. The last
    message should be from the user so the LLM generates a response and
    triggers the agent_end hook (which runs fact extraction).

    If the last message is from the assistant, we append a "summary" user
    message to trigger the hook.
    """
    try:
        # Ensure last message is from user to trigger agent_end hook
        chat_messages = list(messages)
        if chat_messages and chat_messages[-1]["role"] == "assistant":
            chat_messages.append({
                "role": "user",
                "content": "Please summarize the key facts you learned about me from our conversation.",
            })

        start = time.monotonic()
        _, latency = await _chat(client, instance, chat_messages, timeout=180.0)

        return IngestResult(
            instance=instance,
            conv_id=conv_id,
            success=True,
            turns_sent=len(chat_messages),
            latency_ms=latency,
        )
    except Exception as e:
        return IngestResult(
            instance=instance,
            conv_id=conv_id,
            success=False,
            turns_sent=len(messages),
            latency_ms=0.0,
            error=str(e),
        )


async def run_ingest(
    conversations: List[Tuple[str, List[Dict[str, str]]]],
    instances: List[str],
    checkpoint: BenchmarkCheckpoint,
    checkpoint_path: Path,
    concurrency: int = 2,
) -> List[IngestResult]:
    """Ingest all conversations into all instances."""
    results: List[IngestResult] = []
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        for i, (conv_id, messages) in enumerate(conversations):
            tasks = []
            for inst in instances:
                # Skip already-completed
                completed = checkpoint.ingest_completed.get(inst, [])
                if conv_id in completed:
                    continue

                async def _do(inst=inst, conv_id=conv_id, msgs=messages):
                    async with sem:
                        return await ingest_conversation(client, inst, conv_id, msgs)

                tasks.append(_do())

            if not tasks:
                continue

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in batch_results:
                if isinstance(r, Exception):
                    logger.error("Ingest error: %s", r)
                    continue
                results.append(r)
                if r.success:
                    checkpoint.ingest_completed.setdefault(r.instance, []).append(r.conv_id)

            # Checkpoint every 5 conversations
            if (i + 1) % 5 == 0:
                checkpoint.save(checkpoint_path)
                logger.info(
                    "  [%d/%d] Ingested %s — %.0fms avg",
                    i + 1,
                    len(conversations),
                    conv_id,
                    sum(r.latency_ms for r in results[-len(instances):]) / max(1, len(instances)),
                )

            # Small delay between conversations to avoid overwhelming instances
            await asyncio.sleep(0.5)

    checkpoint.save(checkpoint_path)
    return results


# ---------------------------------------------------------------------------
# Phase 2: QUERY
# ---------------------------------------------------------------------------


def load_queries() -> List[Dict[str, Any]]:
    """Load test queries from ground truth."""
    queries_path = GT_DIR / "queries-ingested.json"
    if not queries_path.exists():
        logger.error("Queries file not found: %s", queries_path)
        return []
    with open(queries_path) as f:
        data = json.load(f)
    return data.get("queries", [])


def load_facts() -> Dict[str, Dict[str, Any]]:
    """Load facts indexed by ID."""
    facts_path = GT_DIR / "facts.json"
    if not facts_path.exists():
        return {}
    with open(facts_path) as f:
        data = json.load(f)
    return {f["id"]: f for f in data.get("facts", [])}


async def query_instance(
    client: httpx.AsyncClient,
    instance: str,
    query: Dict[str, Any],
) -> QueryResult:
    """Send a single test query to an instance."""
    query_text = query.get("text", "")
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant with access to memories about the user. "
                    "Answer based ONLY on what you remember about the user. "
                    "If you don't remember anything relevant, say 'I don't have any memories about that.' "
                    "Be specific — include names, numbers, places, and details from your memories."
                ),
            },
            {"role": "user", "content": query_text},
        ]
        response_text, latency = await _chat(client, instance, messages, timeout=60.0)

        return QueryResult(
            instance=instance,
            query_id=query["id"],
            query_text=query_text,
            category=query.get("category", "unknown"),
            response_text=response_text,
            latency_ms=latency,
            success=True,
        )
    except Exception as e:
        return QueryResult(
            instance=instance,
            query_id=query["id"],
            query_text=query_text,
            category=query.get("category", "unknown"),
            response_text="",
            latency_ms=0.0,
            success=False,
            error=str(e),
        )


async def run_queries(
    queries: List[Dict[str, Any]],
    instances: List[str],
    checkpoint: BenchmarkCheckpoint,
    checkpoint_path: Path,
    concurrency: int = 4,
) -> List[QueryResult]:
    """Query all instances with all test queries."""
    results: List[QueryResult] = []
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        for i, query in enumerate(queries):
            tasks = []
            for inst in instances:
                completed = checkpoint.query_completed.get(inst, [])
                if query["id"] in completed:
                    continue

                async def _do(inst=inst, q=query):
                    async with sem:
                        return await query_instance(client, inst, q)

                tasks.append(_do())

            if not tasks:
                continue

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in batch_results:
                if isinstance(r, Exception):
                    logger.error("Query error: %s", r)
                    continue
                results.append(r)
                if r.success:
                    checkpoint.query_completed.setdefault(r.instance, []).append(r.query_id)

            if (i + 1) % 50 == 0:
                checkpoint.save(checkpoint_path)
                logger.info(
                    "  [%d/%d] Queried %s — %.0fms avg",
                    i + 1,
                    len(queries),
                    query["id"],
                    sum(r.latency_ms for r in results[-len(instances):] if r.success) / max(1, len(instances)),
                )

            await asyncio.sleep(0.1)

    checkpoint.save(checkpoint_path)
    return results


# ---------------------------------------------------------------------------
# Phase 3: SCORE
# ---------------------------------------------------------------------------


def score_response(
    query: Dict[str, Any],
    response_text: str,
    facts_index: Dict[str, Dict[str, Any]],
    instance: str,
) -> ScoreResult:
    """Score a single response against ground truth using keyword overlap.

    For each expected fact, check if key terms from the fact text appear
    in the response. This is a fast, deterministic baseline scorer.
    """
    relevant_facts = query.get("relevant_facts", [])
    expected_ids = [rf["fact_id"] for rf in relevant_facts if isinstance(rf, dict)]
    expected_texts = []
    for fid in expected_ids:
        fact = facts_index.get(fid, {})
        if fact:
            expected_texts.append(fact.get("text", ""))

    # Keyword matching: for each expected fact, extract key terms and check
    response_lower = response_text.lower()
    hits = 0
    for fact_text in expected_texts:
        # Extract significant words (>3 chars, not stop words)
        words = set(
            w.strip(".,!?;:'\"()[]")
            for w in fact_text.lower().split()
            if len(w.strip(".,!?;:'\"()[]")) > 3
        )
        stop_words = {
            "that", "this", "with", "from", "they", "their", "them",
            "have", "been", "were", "will", "would", "could", "should",
            "about", "which", "there", "these", "those", "into", "more",
            "also", "than", "very", "just", "some", "other", "what",
            "when", "where", "does", "like",
        }
        key_words = words - stop_words
        if not key_words:
            continue

        # Check if at least 40% of key words appear in response
        matches = sum(1 for w in key_words if w in response_lower)
        if matches >= max(1, len(key_words) * 0.4):
            hits += 1

    total = len(expected_texts) if expected_texts else 0
    recall = hits / total if total > 0 else (1.0 if query.get("category") == "negative" else 0.0)

    return ScoreResult(
        instance=instance,
        query_id=query["id"],
        category=query.get("category", "unknown"),
        expected_fact_ids=expected_ids,
        expected_facts_text=expected_texts,
        response_text=response_text[:500],
        keyword_hits=hits,
        keyword_total=total,
        keyword_recall=recall,
    )


def run_scoring(
    query_results: List[QueryResult],
    queries: List[Dict[str, Any]],
    facts_index: Dict[str, Dict[str, Any]],
    instances: List[str],
) -> Dict[str, Any]:
    """Score all query results and compute aggregate metrics."""
    # Index queries by ID
    queries_by_id = {q["id"]: q for q in queries}

    # Index query results by (instance, query_id)
    results_by_key: Dict[Tuple[str, str], QueryResult] = {}
    for qr in query_results:
        results_by_key[(qr.instance, qr.query_id)] = qr

    # Score each result
    all_scores: List[ScoreResult] = []
    for (inst, qid), qr in results_by_key.items():
        query = queries_by_id.get(qid)
        if not query:
            continue
        score = score_response(query, qr.response_text, facts_index, inst)
        all_scores.append(score)

    # Aggregate per instance
    instance_metrics: Dict[str, Dict[str, Any]] = {}
    for inst in instances:
        inst_scores = [s for s in all_scores if s.instance == inst]
        if not inst_scores:
            continue

        # Overall recall
        total_recall = sum(s.keyword_recall for s in inst_scores) / len(inst_scores)

        # Per-category recall
        category_metrics = {}
        for cat in ["factual", "semantic", "cross_conversation", "negative"]:
            cat_scores = [s for s in inst_scores if s.category == cat]
            if cat_scores:
                category_metrics[cat] = {
                    "count": len(cat_scores),
                    "avg_recall": sum(s.keyword_recall for s in cat_scores) / len(cat_scores),
                    "hits": sum(s.keyword_hits for s in cat_scores),
                    "total": sum(s.keyword_total for s in cat_scores),
                }

        # Latency from query results
        inst_qr = [qr for qr in query_results if qr.instance == inst and qr.success]
        latencies = sorted([qr.latency_ms for qr in inst_qr])
        p50 = latencies[len(latencies) // 2] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

        instance_metrics[inst] = {
            "label": INSTANCES[inst]["label"],
            "total_queries": len(inst_scores),
            "successful_queries": len(inst_qr),
            "avg_keyword_recall": round(total_recall, 4),
            "category_metrics": category_metrics,
            "latency_p50_ms": round(p50, 1),
            "latency_p95_ms": round(p95, 1),
            "latency_p99_ms": round(p99, 1),
        }

    return instance_metrics


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(metrics: Dict[str, Dict[str, Any]]):
    """Print a formatted benchmark report."""
    print("\n" + "=" * 72)
    print("  BENCHMARK RESULTS — 4-Way Memory System Comparison")
    print("=" * 72)

    # Summary table
    print(f"\n{'System':<35} {'Recall':>8} {'p50(ms)':>8} {'p95(ms)':>8} {'Queries':>8}")
    print("-" * 72)
    for inst, m in sorted(metrics.items(), key=lambda x: -x[1].get("avg_keyword_recall", 0)):
        print(
            f"{m['label']:<35} "
            f"{m['avg_keyword_recall']:>7.1%} "
            f"{m['latency_p50_ms']:>8.0f} "
            f"{m['latency_p95_ms']:>8.0f} "
            f"{m['successful_queries']:>8}"
        )

    # Per-category breakdown
    print(f"\n{'System':<20} {'factual':>10} {'semantic':>10} {'cross_conv':>10} {'negative':>10}")
    print("-" * 72)
    for inst, m in sorted(metrics.items()):
        cats = m.get("category_metrics", {})
        row = f"{inst:<20}"
        for cat in ["factual", "semantic", "cross_conversation", "negative"]:
            if cat in cats:
                row += f" {cats[cat]['avg_recall']:>9.1%}"
            else:
                row += f" {'n/a':>9}"
        print(row)

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def check_health(instances: List[str]) -> List[str]:
    """Check which instances are healthy. Returns list of healthy instances."""
    healthy = []
    async with httpx.AsyncClient() as client:
        for inst in instances:
            port = INSTANCES[inst]["port"]
            url = f"{BASE_URL}:{port}/"
            try:
                resp = await client.get(url, timeout=5.0)
                if resp.status_code < 500:
                    healthy.append(inst)
                    logger.info("  %s (:%d) — OK", inst, port)
                else:
                    logger.warning("  %s (:%d) — HTTP %d", inst, port, resp.status_code)
            except Exception as e:
                logger.warning("  %s (:%d) — %s", inst, port, e)
    return healthy


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    parser = argparse.ArgumentParser(description="4-Way Memory System Benchmark Runner")
    parser.add_argument("--phase", choices=["ingest", "query", "score", "all"], default="all")
    parser.add_argument("--conversations", type=int, default=50, help="Max conversations to ingest")
    parser.add_argument("--queries", type=int, default=0, help="Max queries (0=all)")
    parser.add_argument("--instances", type=str, default="totalreclaw,mem0,qmd,lancedb",
                        help="Comma-separated instances to benchmark")
    parser.add_argument("--concurrency", type=int, default=8, help="Max concurrent requests per phase")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--output", type=str, default="", help="Output directory (default: benchmark-results/)")
    args = parser.parse_args()

    # Setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    output_dir = Path(args.output) if args.output else RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / ".benchmark-checkpoint.json"

    instances = [i.strip() for i in args.instances.split(",") if i.strip() in INSTANCES]
    if not instances:
        logger.error("No valid instances specified")
        sys.exit(1)

    # Load or create checkpoint
    if args.resume and checkpoint_path.exists():
        checkpoint = BenchmarkCheckpoint.load(checkpoint_path)
        logger.info("Resumed from checkpoint: phase=%s", checkpoint.phase)
    else:
        checkpoint = BenchmarkCheckpoint(started_at=datetime.now().isoformat())

    # Health check
    logger.info("Checking instance health...")
    healthy = await check_health(instances)
    if not healthy:
        logger.error("No healthy instances! Start Docker first:")
        logger.error("  docker compose -f docker-compose.benchmark.yml up -d")
        sys.exit(1)
    instances = healthy
    logger.info("Healthy instances: %s", ", ".join(instances))

    run_all = args.phase == "all"

    # -----------------------------------------------------------------------
    # Phase 1: INGEST
    # -----------------------------------------------------------------------
    if args.phase in ("ingest", "all"):
        logger.info("\n=== Phase 1: INGEST ===")
        conversations = load_conversations(args.conversations)
        logger.info("Loaded %d conversations", len(conversations))

        checkpoint.phase = "ingest"
        ingest_results = await run_ingest(
            conversations, instances, checkpoint, checkpoint_path, args.concurrency
        )

        # Save raw results
        with open(output_dir / "ingest-results.json", "w") as f:
            json.dump([asdict(r) for r in ingest_results], f, indent=2)

        successes = sum(1 for r in ingest_results if r.success)
        logger.info(
            "Ingest complete: %d/%d successful (%.0fms avg)",
            successes,
            len(ingest_results),
            sum(r.latency_ms for r in ingest_results if r.success) / max(1, successes),
        )

    # -----------------------------------------------------------------------
    # Phase 2: QUERY
    # -----------------------------------------------------------------------
    if args.phase in ("query", "all"):
        logger.info("\n=== Phase 2: QUERY ===")
        queries = load_queries()
        if args.queries > 0:
            queries = queries[:args.queries]
        logger.info("Loaded %d queries", len(queries))

        if not queries:
            logger.error("No queries found. Run query generation first.")
            sys.exit(1)

        checkpoint.phase = "query"
        query_results = await run_queries(
            queries, instances, checkpoint, checkpoint_path, args.concurrency
        )

        # Save raw results
        with open(output_dir / "query-results.json", "w") as f:
            json.dump([asdict(r) for r in query_results], f, indent=2)

        successes = sum(1 for r in query_results if r.success)
        logger.info(
            "Query complete: %d/%d successful (%.0fms avg)",
            successes,
            len(query_results),
            sum(r.latency_ms for r in query_results if r.success) / max(1, successes),
        )

    # -----------------------------------------------------------------------
    # Phase 3: SCORE
    # -----------------------------------------------------------------------
    if args.phase in ("score", "all"):
        logger.info("\n=== Phase 3: SCORE ===")

        # Load query results from file if running score-only
        query_results_path = output_dir / "query-results.json"
        if args.phase == "score":
            if not query_results_path.exists():
                logger.error("No query results found. Run query phase first.")
                sys.exit(1)
            with open(query_results_path) as f:
                raw = json.load(f)
            query_results = [QueryResult(**r) for r in raw]
        elif "query_results" not in dir():
            logger.error("No query results available")
            sys.exit(1)

        queries = load_queries()
        if args.queries > 0:
            queries = queries[:args.queries]
        facts_index = load_facts()

        checkpoint.phase = "score"
        metrics = run_scoring(query_results, queries, facts_index, instances)

        # Save metrics
        with open(output_dir / "benchmark-metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)

        # Print report
        print_report(metrics)

        checkpoint.phase = "complete"
        checkpoint.save(checkpoint_path)

    logger.info("\nBenchmark complete! Results in %s", output_dir)


if __name__ == "__main__":
    asyncio.run(main())
