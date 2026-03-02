#!/usr/bin/env python3
"""
Regenerate benchmark queries for only the conversations that were actually ingested.

Reads ingest-results.json to identify which conversations were ingested,
filters facts.json to only include facts from those conversations, and
generates ~130 queries across categories using the same LLM infrastructure
as the original generate_synthetic_benchmark.py.

Usage:
    cd ombh
    python scripts/regenerate_queries_for_ingested.py
"""

import asyncio
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Ensure ombh package is importable when running from ombh/ directory
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_OMBH_ROOT = _SCRIPT_DIR.parent
if str(_OMBH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OMBH_ROOT))

from ombh.llm.client import LLMClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BENCHMARK_DIR = _OMBH_ROOT / "synthetic-benchmark"
INGEST_RESULTS = BENCHMARK_DIR / "benchmark-results" / "ingest-results.json"
ALL_FACTS_PATH = BENCHMARK_DIR / "ground-truth" / "facts.json"
FILTERED_FACTS_PATH = BENCHMARK_DIR / "ground-truth" / "facts-ingested.json"
OUTPUT_QUERIES_PATH = BENCHMARK_DIR / "ground-truth" / "queries-ingested.json"

# ---------------------------------------------------------------------------
# Query generation prompts (same structure as generate_synthetic_benchmark.py)
# ---------------------------------------------------------------------------

QUERY_GENERATION_SYSTEM_PROMPT = """You are a test query generator for a memory retrieval system. Given a set of facts from a user's conversations with an AI assistant, generate diverse search queries that the user might ask to recall information.

STRICT rules — violating ANY of these makes the output INVALID:
1. You MUST generate EXACTLY the number of queries requested for each category. Count them before outputting.
2. The "category" field MUST be one of: "factual", "semantic", "cross_conversation", "negative". No other values allowed.
3. Factual queries: Direct questions using similar wording to the facts. MUST have 2-3+ relevant_facts entries.
4. Semantic queries: Rephrase facts using COMPLETELY DIFFERENT wording — synonyms, different sentence structures, indirect references. MUST have 2-3+ relevant_facts entries.
5. Cross-conversation queries: MUST combine facts from BOTH "Primary facts" AND "Other conversation facts" sections. Include fact IDs from BOTH sections in relevant_facts. These are the MOST IMPORTANT queries.
6. Negative queries: Ask about plausible topics NOT covered by ANY fact. relevant_facts MUST be an empty array [].
7. Output ONLY valid JSON — no markdown fences, no explanations, no trailing commas."""


def build_query_generation_prompt(
    facts_batch: List[Dict[str, Any]],
    queries_per_batch: int,
    cross_conv_facts: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build prompt to generate test queries from a batch of facts."""
    facts_text = "\n".join(
        f"[{f['id']}] ({f['type']}, importance={f['importance']}): {f['text']}"
        for f in facts_batch
    )

    # Calculate target distribution
    n_factual = max(1, round(queries_per_batch * 0.30))
    n_semantic = max(1, round(queries_per_batch * 0.40))
    n_cross = max(1, round(queries_per_batch * 0.20))
    n_negative = max(1, queries_per_batch - n_factual - n_semantic - n_cross)
    # Trim if over budget
    while n_factual + n_semantic + n_cross + n_negative > queries_per_batch and n_negative > 0:
        n_negative -= 1
    while n_factual + n_semantic + n_cross + n_negative > queries_per_batch and n_cross > 0:
        n_cross -= 1

    # Build cross-conversation context
    cross_section = ""
    if cross_conv_facts:
        cross_text = "\n".join(
            f"[{f['id']}] ({f['type']}, importance={f['importance']}): {f['text']}"
            for f in cross_conv_facts
        )
        cross_section = f"""

Other conversation facts (from DIFFERENT conversations — use these for cross_conversation queries):
{cross_text}

IMPORTANT for cross_conversation queries: Create questions that naturally combine or compare
information from the primary facts above AND these other conversation facts. For example:
- "What are all the places the user has traveled to?" (combining travel facts from multiple conversations)
- "Does the user prefer working remotely or in-office?" (combining work-related facts from different conversations)
- "What programming languages and tools does the user use?" (combining tech facts from multiple conversations)
Include fact IDs from BOTH sections in the relevant_facts list for cross_conversation queries."""

    return f"""Generate EXACTLY {queries_per_batch} test queries based on these facts.

Primary facts (from this conversation batch):
{facts_text}
{cross_section}

REQUIRED distribution — count carefully before outputting:
- EXACTLY {n_factual} queries with category "factual": Direct questions about specific primary facts using similar wording. Each MUST have 2-3+ entries in relevant_facts.
- EXACTLY {n_semantic} queries with category "semantic": Rephrase facts using COMPLETELY DIFFERENT words, synonyms, and indirect references. Each MUST have 2-3+ entries in relevant_facts.
- EXACTLY {n_cross} queries with category "cross_conversation": Questions that naturally combine information from BOTH the primary facts AND the other conversation facts. You MUST include fact IDs from BOTH sections in relevant_facts. Example: "What are all the user's hobbies?" combining hobby facts from different conversations.
- EXACTLY {n_negative} queries with category "negative": Questions about plausible topics NOT covered by ANY listed fact. relevant_facts MUST be exactly [].

VERIFY before outputting: Count each category. You need exactly {n_factual} factual + {n_semantic} semantic + {n_cross} cross_conversation + {n_negative} negative = {queries_per_batch} total.

For each query, provide relevance scores (0.0-1.0) for EVERY fact that is relevant:
- 1.0 = perfectly relevant (fact directly answers the query)
- 0.7-0.9 = highly relevant (fact is closely related)
- 0.4-0.6 = partially relevant (fact provides some context)
- Omit facts with relevance < 0.4

IMPORTANT: Reference as many facts as possible per query. Most factual and semantic queries should have 2-3+ relevant facts.

Output format:
{{
  "queries": [
    {{
      "text": "natural search question",
      "category": "factual|semantic|cross_conversation|negative",
      "relevant_facts": [
        {{"fact_id": "fact-XXXX", "relevance": 0.95}},
        {{"fact_id": "fact-YYYY", "relevance": 0.6}}
      ]
    }}
  ]
}}"""


def parse_json_response(response: str) -> Dict[str, Any]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    import re
    text = response.strip()
    # Strip markdown code blocks
    code_match = re.match(r"^```(?:json)?\s*([\s\S]*?)```$", text)
    if code_match:
        text = code_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.error("Failed to parse JSON from response: %s...", text[:200])
        return {}


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def get_ingested_conversation_ids() -> Set[str]:
    """Read ingest-results.json and return IDs of successfully ingested conversations."""
    with open(INGEST_RESULTS) as f:
        data = json.load(f)
    conv_ids = set()
    for entry in data:
        if entry.get("success"):
            conv_ids.add(entry["conv_id"])
    return conv_ids


def filter_facts_for_ingested(ingested_ids: Set[str]) -> List[Dict[str, Any]]:
    """Load facts.json and return only facts whose ALL source_conversations are ingested."""
    with open(ALL_FACTS_PATH) as f:
        data = json.load(f)
    all_facts = data.get("facts", [])

    eligible = []
    for f in all_facts:
        sources = f.get("source_conversations", [])
        if sources and all(s in ingested_ids for s in sources):
            eligible.append(f)

    return eligible


def save_filtered_facts(facts: List[Dict[str, Any]], ingested_ids: Set[str]) -> None:
    """Save filtered facts to facts-ingested.json."""
    output = {
        "metadata": {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "total_facts": len(facts),
            "ingested_conversations": sorted(ingested_ids),
            "description": "Facts filtered to only include those from ingested conversations",
        },
        "facts": facts,
    }
    with open(FILTERED_FACTS_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d filtered facts to %s", len(facts), FILTERED_FACTS_PATH)


async def generate_queries(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate queries from filtered facts using the LLM client."""
    # Use the same extraction client config as generate_synthetic_benchmark.py
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not or_key:
        raise ValueError("OPENROUTER_API_KEY not set. Check .env file.")

    client = LLMClient(
        api_key=or_key,
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-4.1-mini",
        fallback_models=["openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct"],
        temperature=0.3,
        max_tokens=4096,
        request_json=True,
        timeout=180.0,
    )

    rng = random.Random(42)

    # Build index of facts by source conversation for cross-conv sampling
    facts_by_conv: Dict[str, List[Dict[str, Any]]] = {}
    for f in facts:
        for conv_id in f.get("source_conversations", []):
            facts_by_conv.setdefault(conv_id, []).append(f)

    # We want ~130 queries total. With 415 facts, we'll use batch_size=10
    # and queries_per_batch=3, giving us ~42 batches * 3 = ~126 queries.
    # Adjust to hit our target.
    batch_size = 10
    queries_per_batch = 3
    total_batches = (len(facts) + batch_size - 1) // batch_size

    # Estimate: total_batches * queries_per_batch ~ 42 * 3 = 126
    # We want ~130, so let's use queries_per_batch=3 for most and 4 for some
    # Actually let's just use 3 across the board and adjust if needed
    logger.info(
        "Generating queries: %d facts, batch_size=%d, queries_per_batch=%d, estimated_batches=%d",
        len(facts), batch_size, queries_per_batch, total_batches,
    )

    all_queries: List[Dict[str, Any]] = []
    query_counter = 0

    for batch_idx in range(total_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(facts))
        facts_batch = facts[batch_start:batch_end]

        # Collect conversation IDs from this batch
        batch_conv_ids: Set[str] = set()
        for f in facts_batch:
            for conv_id in f.get("source_conversations", []):
                batch_conv_ids.add(conv_id)

        # Sample facts from OTHER conversations for cross-conversation queries
        other_conv_ids = [c for c in facts_by_conv if c not in batch_conv_ids]
        cross_conv_facts: List[Dict[str, Any]] = []
        if other_conv_ids:
            sample_convs = rng.sample(other_conv_ids, min(3, len(other_conv_ids)))
            for conv_id in sample_convs:
                conv_facts = facts_by_conv[conv_id]
                sample_size = min(3, len(conv_facts))
                cross_conv_facts.extend(rng.sample(conv_facts, sample_size))

        prompt = build_query_generation_prompt(
            facts_batch,
            queries_per_batch,
            cross_conv_facts=cross_conv_facts if cross_conv_facts else None,
        )

        logger.info(
            "[%d/%d] Generating queries for facts %d-%d...",
            batch_idx + 1, total_batches, batch_start + 1, batch_end,
        )

        try:
            response = await client.complete(
                system=QUERY_GENERATION_SYSTEM_PROMPT,
                user=prompt,
                max_tokens=4096,
            )

            parsed = parse_json_response(response)
            queries = parsed.get("queries", [])

            for raw_query in queries:
                query_counter += 1
                query = {
                    "id": f"query-i{query_counter:04d}",
                    "text": raw_query.get("text", ""),
                    "category": raw_query.get("category", "factual"),
                    "relevant_facts": raw_query.get("relevant_facts", []),
                    "source_fact_batch": [f["id"] for f in facts_batch],
                }
                if query["text"]:
                    all_queries.append(query)

        except Exception as e:
            logger.error("Error generating queries for batch %d: %s", batch_idx, e)

        # Small delay to avoid rate limits
        await asyncio.sleep(0.3)

    logger.info("Generated %d queries (before negatives)", len(all_queries))

    # --- Generate negative queries separately ---
    # With queries_per_batch=3, the distribution math trims negatives to 0.
    # Generate ~14 negative queries in a dedicated pass to reach ~10% of total.
    n_negative_target = max(10, round(len(all_queries) * 0.11))
    logger.info("Generating %d negative queries...", n_negative_target)

    # Sample a representative subset of facts to show what IS covered
    sample_size = min(50, len(facts))
    sample_facts = rng.sample(facts, sample_size)
    sample_text = "\n".join(
        f"[{f['id']}] ({f['type']}): {f['text']}" for f in sample_facts
    )

    negative_prompt = f"""Generate EXACTLY {n_negative_target} NEGATIVE test queries for a memory retrieval system.

These queries should ask about plausible topics that are NOT covered by any of the user's stored facts. The queries should sound natural and realistic, but the memory system should correctly return NO results for them.

Here is a representative sample of what the user's memory DOES contain (do NOT ask about these topics):
{sample_text}

Guidelines:
- Ask about plausible personal topics: pets, specific travel destinations, medical info, family members, specific hobbies, etc.
- Make them sound like real recall queries a user might ask
- Each query must have relevant_facts as an empty array []
- Category MUST be "negative" for ALL queries

Output format:
{{
  "queries": [
    {{
      "text": "natural search question about a topic NOT in the facts",
      "category": "negative",
      "relevant_facts": []
    }}
  ]
}}"""

    try:
        response = await client.complete(
            system="You generate test queries for evaluating a memory retrieval system. Output ONLY valid JSON.",
            user=negative_prompt,
            max_tokens=4096,
        )
        parsed = parse_json_response(response)
        neg_queries = parsed.get("queries", [])

        for raw_query in neg_queries:
            query_counter += 1
            query = {
                "id": f"query-i{query_counter:04d}",
                "text": raw_query.get("text", ""),
                "category": "negative",  # Force category
                "relevant_facts": [],     # Force empty
                "source_fact_batch": [],
            }
            if query["text"]:
                all_queries.append(query)

        logger.info("Added %d negative queries", len(neg_queries))
    except Exception as e:
        logger.error("Error generating negative queries: %s", e)

    logger.info("Generated %d queries total (including negatives)", len(all_queries))
    logger.info(
        "LLM usage: %d calls, %d tokens, avg %.0fms",
        client.usage.total_calls,
        client.usage.total_tokens,
        client.usage.avg_latency_ms,
    )

    return all_queries


def validate_queries(queries: List[Dict[str, Any]], eligible_fact_ids: Set[str]) -> Dict[str, Any]:
    """Validate generated queries and compute statistics."""
    category_dist: Dict[str, int] = {}
    invalid_fact_refs = 0
    total_refs = 0

    for q in queries:
        cat = q.get("category", "unknown")
        category_dist[cat] = category_dist.get(cat, 0) + 1

        for ref in q.get("relevant_facts", []):
            total_refs += 1
            if ref.get("fact_id") not in eligible_fact_ids:
                invalid_fact_refs += 1

    return {
        "total_queries": len(queries),
        "category_distribution": category_dist,
        "total_fact_references": total_refs,
        "invalid_fact_references": invalid_fact_refs,
        "avg_facts_per_query": round(total_refs / max(len(queries), 1), 2),
    }


def save_queries(queries: List[Dict[str, Any]], stats: Dict[str, Any]) -> None:
    """Save queries to queries-ingested.json."""
    output = {
        "metadata": {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "total_queries": len(queries),
            "description": "Queries generated from facts of ingested conversations only",
            "generation_stats": stats,
        },
        "queries": queries,
    }
    with open(OUTPUT_QUERIES_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d queries to %s", len(queries), OUTPUT_QUERIES_PATH)


async def main():
    start_time = time.time()

    # Step 1: Identify ingested conversations
    logger.info("Step 1: Identifying ingested conversations...")
    ingested_ids = get_ingested_conversation_ids()
    logger.info("Found %d ingested conversations: %s", len(ingested_ids), sorted(ingested_ids))

    # Step 2: Filter facts
    logger.info("Step 2: Filtering facts to ingested conversations...")
    eligible_facts = filter_facts_for_ingested(ingested_ids)
    logger.info("Eligible facts: %d (out of 8268 total)", len(eligible_facts))

    # Step 3: Save filtered facts
    logger.info("Step 3: Saving filtered facts...")
    save_filtered_facts(eligible_facts, ingested_ids)

    # Step 4: Generate queries
    logger.info("Step 4: Generating queries from %d eligible facts...", len(eligible_facts))
    queries = await generate_queries(eligible_facts)

    # Step 5: Validate and save
    eligible_fact_ids = {f["id"] for f in eligible_facts}
    stats = validate_queries(queries, eligible_fact_ids)

    logger.info("Step 5: Saving queries...")
    save_queries(queries, stats)

    elapsed = time.time() - start_time

    # Print summary
    print("\n" + "=" * 60)
    print("QUERY REGENERATION SUMMARY")
    print("=" * 60)
    print(f"\nIngested conversations: {len(ingested_ids)}")
    print(f"Eligible facts: {len(eligible_facts)}")
    print(f"Queries generated: {stats['total_queries']}")
    print(f"\nCategory distribution:")
    for cat, count in sorted(stats["category_distribution"].items()):
        pct = count / max(stats["total_queries"], 1) * 100
        print(f"  {cat}: {count} ({pct:.1f}%)")
    print(f"\nAvg facts per query: {stats['avg_facts_per_query']}")
    print(f"Invalid fact references: {stats['invalid_fact_references']}")
    print(f"\nTime elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"\nOutput files:")
    print(f"  Filtered facts: {FILTERED_FACTS_PATH}")
    print(f"  Queries: {OUTPUT_QUERIES_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
