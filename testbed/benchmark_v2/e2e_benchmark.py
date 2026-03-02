#!/usr/bin/env python3
"""
End-to-End Pipeline Benchmark: TotalReclaw E2EE vs Mem0 Platform

Tests the FULL pipeline: Raw conversations -> Fact extraction -> Storage -> Retrieval.

Unlike the retrieval-only benchmark (retrieval_benchmark.py) which loads the same
pre-extracted facts into both systems, this benchmark tests each system's complete
pipeline including their own extraction layer:

    +-----------+------------------------------------+--------------------------------------+
    |   Step    |              Mem0                  |            TotalReclaw                |
    +-----------+------------------------------------+--------------------------------------+
    | Input     | Raw conversation messages          | Same raw conversation messages       |
    | Extraction| Mem0's internal LLM (gpt-4.1-nano) | TotalReclaw's prompts + LLM (T055)   |
    | Storage   | Mem0's vector store (plaintext)    | TotalReclaw's E2EE + LSH blind index  |
    | Retrieval | Mem0's vector search               | TotalReclaw's LSH -> rerank pipeline  |
    | Output    | Retrieved facts                    | Retrieved facts                      |
    +-----------+------------------------------------+--------------------------------------+

Metrics measured:
    1. Extraction quality: fact count, avg importance, avg confidence
    2. Retrieval quality:  Recall@8, Recall@20, MRR (against ground truth)
    3. Privacy score:      TotalReclaw=100 (E2EE), Mem0=0 (plaintext SaaS)
    4. Latency:            End-to-end time per operation

IMPORTANT NOTES:
- Mem0 free tier: 10,000 memories and 1,000 searches/month. Keep data within limits.
- Mem0 client.add(messages=...) does extraction internally; we just send raw text.
- TotalReclaw uses the LLM wrapper (ombh.llm) to call extraction prompts + E2EE pipeline.
- We subsample conversations to stay within free-tier limits.
- Ground truth is based on cosine similarity of embeddings generated from the raw content.
"""

import asyncio
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from dotenv import load_dotenv

# ---- Path setup ----
PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "ombh" / ".env")

# Add ombh to path
sys.path.insert(0, str(PROJECT_ROOT / "ombh"))

BASE_DIR = PROJECT_ROOT / "testbed"
PROCESSED_DIR = BASE_DIR / "v2-realworld-data" / "processed"
OUTPUT_DIR = BASE_DIR / "benchmark_v2"

# ---- Configuration ----

# Maximum conversations to process (stay within Mem0 free-tier limits)
MAX_CONVERSATIONS = 500

# Maximum queries to run (Mem0: 1000 searches/month)
MAX_QUERIES = 200

# Sleep between Mem0 API calls to avoid rate limiting
MEM0_RATE_LIMIT_SLEEP = 0.2

# Concurrency for TotalReclaw LLM extraction calls
OM_EXTRACTION_CONCURRENCY = 3

# Random seed for reproducibility
SEED = 42


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class ConversationChunk:
    """A single conversation chunk (group of messages)."""
    id: str
    content: str  # Raw conversation text
    source: str  # whatsapp, slack, telegram
    chat_name: str
    participants: List[str]
    timestamp_start: str
    timestamp_end: str
    message_count: int


@dataclass
class ExtractionMetrics:
    """Metrics about a system's fact extraction."""
    total_facts: int = 0
    avg_importance: float = 0.0
    avg_confidence: float = 0.0
    total_extraction_time_ms: float = 0.0
    facts_per_conversation: float = 0.0
    extraction_errors: int = 0


@dataclass
class RetrievalMetrics:
    """Metrics about retrieval quality."""
    recall_at_8: float = 0.0
    recall_at_20: float = 0.0
    mrr: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    queries_run: int = 0
    raw_recalls_8: List[float] = field(default_factory=list)
    raw_recalls_20: List[float] = field(default_factory=list)
    raw_latencies: List[float] = field(default_factory=list)


@dataclass
class E2EBenchmarkResult:
    """Complete E2E benchmark result for one system."""
    system_name: str
    privacy_score: int
    extraction: ExtractionMetrics = field(default_factory=ExtractionMetrics)
    retrieval: RetrievalMetrics = field(default_factory=RetrievalMetrics)
    total_conversations: int = 0
    total_time_s: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_name": self.system_name,
            "privacy_score": self.privacy_score,
            "extraction": {
                "total_facts": self.extraction.total_facts,
                "avg_importance": self.extraction.avg_importance,
                "avg_confidence": self.extraction.avg_confidence,
                "total_extraction_time_ms": self.extraction.total_extraction_time_ms,
                "facts_per_conversation": self.extraction.facts_per_conversation,
                "extraction_errors": self.extraction.extraction_errors,
            },
            "retrieval": {
                "recall_at_8": self.retrieval.recall_at_8,
                "recall_at_20": self.retrieval.recall_at_20,
                "mrr": self.retrieval.mrr,
                "avg_latency_ms": self.retrieval.avg_latency_ms,
                "p95_latency_ms": self.retrieval.p95_latency_ms,
                "queries_run": self.retrieval.queries_run,
            },
            "total_conversations": self.total_conversations,
            "total_time_s": self.total_time_s,
            "notes": self.notes,
        }


# ============================================================================
# Data Loading
# ============================================================================

def load_raw_conversations(max_count: int = MAX_CONVERSATIONS) -> List[ConversationChunk]:
    """
    Load raw conversation chunks from processed data.

    Prioritises WhatsApp (richest personal data), then Slack.
    Filters out very short or system messages.
    """
    conversations: List[ConversationChunk] = []

    # WhatsApp first (personal conversations, richer for fact extraction)
    wa_path = PROCESSED_DIR / "whatsapp_memories.json"
    if wa_path.exists():
        with open(wa_path) as f:
            wa_data = json.load(f)
        for mem in wa_data.get("memories", []):
            content = mem.get("content", "")
            # Skip very short messages (not enough signal for extraction)
            if len(content) < 50 or mem.get("message_count", 0) < 2:
                continue
            conversations.append(ConversationChunk(
                id=mem["id"],
                content=content,
                source="whatsapp",
                chat_name=mem.get("chat_name", ""),
                participants=mem.get("participants", []),
                timestamp_start=mem.get("timestamp_start", ""),
                timestamp_end=mem.get("timestamp_end", ""),
                message_count=mem.get("message_count", 0),
            ))
        print(f"  Loaded {len(conversations)} WhatsApp conversations (filtered)")

    # Slack
    slack_path = PROCESSED_DIR / "slack_memories.json"
    if slack_path.exists():
        with open(slack_path) as f:
            slack_data = json.load(f)
        slack_count = 0
        for mem in slack_data.get("memories", []):
            content = mem.get("content", "")
            # Skip system messages and short content
            if len(content) < 50 or mem.get("message_count", 0) < 2:
                continue
            # Skip "retention policy" system messages
            if "retention policies" in content.lower():
                continue
            conversations.append(ConversationChunk(
                id=mem["id"],
                content=content,
                source="slack",
                chat_name=mem.get("channel_name", ""),
                participants=mem.get("participants", []),
                timestamp_start=mem.get("timestamp_start", ""),
                timestamp_end=mem.get("timestamp_end", ""),
                message_count=mem.get("message_count", 0),
            ))
            slack_count += 1
        print(f"  Loaded {slack_count} Slack conversations (filtered)")

    # Subsample if needed (deterministic)
    np.random.seed(SEED)
    if len(conversations) > max_count:
        indices = np.random.choice(len(conversations), size=max_count, replace=False)
        conversations = [conversations[i] for i in sorted(indices)]
        print(f"  Subsampled to {len(conversations)} conversations")

    print(f"  Total conversations for benchmark: {len(conversations)}")
    return conversations


def load_embeddings_for_ground_truth() -> Tuple[List[Dict], np.ndarray]:
    """
    Load pre-computed embeddings for ground truth calculation.

    Returns (memories_list, embeddings_matrix).
    """
    memories = []
    wa_path = PROCESSED_DIR / "whatsapp_memories.json"
    if wa_path.exists():
        with open(wa_path) as f:
            wa_data = json.load(f)
        memories.extend(wa_data.get("memories", []))

    slack_path = PROCESSED_DIR / "slack_memories.json"
    if slack_path.exists():
        with open(slack_path) as f:
            slack_data = json.load(f)
        memories.extend(slack_data.get("memories", []))

    # Load embeddings
    emb_path = PROCESSED_DIR / "combined_embeddings.npy"
    if emb_path.exists():
        embeddings = np.load(emb_path)
    else:
        wa_emb = np.load(PROCESSED_DIR / "embeddings.npy")
        slack_emb_path = PROCESSED_DIR / "slack_embeddings.npy"
        if slack_emb_path.exists():
            slack_emb = np.load(slack_emb_path)
            embeddings = np.vstack([wa_emb, slack_emb])
        else:
            embeddings = wa_emb

    n = min(len(memories), embeddings.shape[0])
    memories = memories[:n]
    embeddings = embeddings[:n]
    embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10)

    return memories, embeddings


def generate_retrieval_queries(
    conversations: List[ConversationChunk],
    n_queries: int = MAX_QUERIES,
) -> List[Dict[str, str]]:
    """
    Generate retrieval queries from conversations.

    Strategy: take the first sentence/line of a conversation as a query,
    and the full conversation content as what should be retrievable.
    This tests whether the system can retrieve relevant stored facts
    when given a partial cue.
    """
    queries = []
    np.random.seed(SEED + 1)

    # Shuffle and pick
    indices = np.random.permutation(len(conversations))

    for idx in indices:
        if len(queries) >= n_queries:
            break

        conv = conversations[idx]
        content = conv.content.strip()

        # Extract first meaningful line as query
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if not lines:
            continue

        # Take first line (or first 200 chars) as query
        query_text = lines[0][:200]

        # Skip very short queries
        if len(query_text) < 20:
            continue

        queries.append({
            "query": query_text,
            "source_id": conv.id,
            "full_content": content,
        })

    print(f"  Generated {len(queries)} retrieval queries")
    return queries


# ============================================================================
# Mem0 E2E Pipeline
# ============================================================================

async def run_mem0_e2e(
    conversations: List[ConversationChunk],
    queries: List[Dict[str, str]],
) -> E2EBenchmarkResult:
    """
    Run the Mem0 end-to-end pipeline.

    Mem0's client.add(messages=[...]) handles extraction + storage internally.
    It uses gpt-4.1-nano for fact extraction under the hood.
    """
    api_key = os.environ.get("MEM0_API_KEY")
    if not api_key:
        print("  SKIP: MEM0_API_KEY not set")
        return E2EBenchmarkResult(
            system_name="Mem0 Platform",
            privacy_score=0,
            notes="SKIPPED: MEM0_API_KEY not set",
        )

    from mem0 import MemoryClient

    result = E2EBenchmarkResult(
        system_name="Mem0 Platform",
        privacy_score=0,
        total_conversations=len(conversations),
    )

    client = MemoryClient(api_key=api_key)
    user_id = "e2e_benchmark_v2"

    # ---- Reset ----
    print("  Resetting Mem0...")
    try:
        client.delete_all(user_id=user_id)
    except Exception as e:
        print(f"  Reset warning: {e}")
    time.sleep(3)

    # ---- Extraction + Storage (Mem0 does both in one call) ----
    print(f"  Ingesting {len(conversations)} conversations into Mem0...")
    extraction_start = time.time()
    total_stored = 0
    errors = 0
    rate_limited = 0

    for i, conv in enumerate(conversations):
        try:
            # Mem0 add() with messages format: internally extracts facts + stores
            resp = client.add(
                messages=[{"role": "user", "content": conv.content}],
                user_id=user_id,
                metadata={
                    "source": conv.source,
                    "chat_name": conv.chat_name,
                    "conversation_id": conv.id,
                },
            )

            # Count how many facts Mem0 extracted
            if isinstance(resp, dict):
                results_list = resp.get("results", [])
                n_facts = len(results_list) if isinstance(results_list, list) else 0
            elif isinstance(resp, list):
                n_facts = len(resp)
            else:
                n_facts = 1
            total_stored += n_facts

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                rate_limited += 1
                time.sleep(5.0)  # Back off on rate limit
                try:
                    client.add(
                        messages=[{"role": "user", "content": conv.content}],
                        user_id=user_id,
                        metadata={
                            "source": conv.source,
                            "conversation_id": conv.id,
                        },
                    )
                    total_stored += 1
                except Exception:
                    errors += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"    Store error at index {i}: {e}")

        if MEM0_RATE_LIMIT_SLEEP > 0:
            time.sleep(MEM0_RATE_LIMIT_SLEEP)

        # Progress
        if (i + 1) % 10 == 0 or i + 1 == len(conversations):
            elapsed = time.time() - extraction_start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(conversations) - i - 1) / rate if rate > 0 else 0
            print(f"    [{i+1}/{len(conversations)}] {rate:.1f} conv/s, "
                  f"stored={total_stored}, errors={errors}, rate_limited={rate_limited}, "
                  f"ETA={eta:.0f}s")

    extraction_time = time.time() - extraction_start
    result.extraction.total_facts = total_stored
    result.extraction.total_extraction_time_ms = extraction_time * 1000
    result.extraction.facts_per_conversation = (
        total_stored / len(conversations) if conversations else 0
    )
    result.extraction.extraction_errors = errors

    # Wait for Mem0 async processing -- poll until count stabilizes
    # Mem0 v2 processes memories asynchronously, so we need to wait for
    # the background queue to drain before querying.
    print("  Waiting for Mem0 async indexing (polling every 15s, max 5min)...")
    max_wait = 300  # 5 minutes
    poll_interval = 15
    prev_count = 0
    stable_rounds = 0
    wait_start = time.time()

    while (time.time() - wait_start) < max_wait:
        time.sleep(poll_interval)
        try:
            all_mems = client.get_all(
                filters={"user_id": user_id},
                page=1,
                page_size=10000,
            )
            if isinstance(all_mems, dict):
                cur_count = len(all_mems.get("results", []))
            else:
                cur_count = len(all_mems) if isinstance(all_mems, list) else 0
        except Exception:
            cur_count = prev_count

        elapsed_wait = time.time() - wait_start
        print(f"    ... {elapsed_wait:.0f}s: {cur_count} memories indexed")

        if cur_count == prev_count and cur_count > 0:
            stable_rounds += 1
            if stable_rounds >= 2:
                print(f"  Indexing stabilized at {cur_count} memories after {elapsed_wait:.0f}s")
                break
        else:
            stable_rounds = 0

        prev_count = cur_count
    else:
        print(f"  Timeout after {max_wait}s, proceeding with {prev_count} memories")

    # Get final memory count and metadata
    try:
        all_mems = client.get_all(
            filters={"user_id": user_id},
            page=1,
            page_size=10000,
        )
        if isinstance(all_mems, dict):
            actual_count = len(all_mems.get("results", []))
        else:
            actual_count = len(all_mems) if isinstance(all_mems, list) else 0
        print(f"  Mem0 reports {actual_count} memories stored")
        result.extraction.total_facts = actual_count

        # Calculate avg importance from stored memories
        importances = []
        if isinstance(all_mems, dict):
            for m in all_mems.get("results", []):
                meta = m.get("metadata", {}) or {}
                imp = meta.get("importance")
                if imp is not None:
                    importances.append(float(imp))
        if importances:
            result.extraction.avg_importance = statistics.mean(importances)
    except Exception as e:
        print(f"  Could not get memory count: {e}")

    # ---- Retrieval ----
    print(f"  Running {len(queries)} retrieval queries...")
    r8_list, r20_list, mrr_list, lat_list = [], [], [], []

    # Build a text index for matching Mem0 results back
    conv_text_index: Dict[str, str] = {}
    for conv in conversations:
        conv_text_index[conv.id] = conv.content

    for qi, q in enumerate(queries):
        query_text = q["query"]
        source_id = q["source_id"]

        start = time.perf_counter()
        try:
            search_result = client.search(
                query_text,
                filters={"user_id": user_id},
                limit=20,
            )
            if isinstance(search_result, dict):
                results_list = search_result.get("results", [])
            elif isinstance(search_result, list):
                results_list = search_result
            else:
                results_list = []
        except Exception as e:
            print(f"    Search error: {e}")
            results_list = []

        latency = (time.perf_counter() - start) * 1000
        lat_list.append(latency)

        # Match results to source conversations using fuzzy text overlap
        matched_conv_ids = _match_mem0_results_to_conv_ids(
            results_list, conversations
        )

        # Calculate recall: did we retrieve content from the same conversation?
        top_8_match = 1.0 if source_id in matched_conv_ids[:8] else 0.0
        top_20_match = 1.0 if source_id in matched_conv_ids[:20] else 0.0
        r8_list.append(top_8_match)
        r20_list.append(top_20_match)

        # MRR: rank of the correct conversation
        found_rank = 0.0
        for rank, cid in enumerate(matched_conv_ids[:20]):
            if cid == source_id:
                found_rank = 1.0 / (rank + 1)
                break
        mrr_list.append(found_rank)

        if MEM0_RATE_LIMIT_SLEEP > 0:
            time.sleep(MEM0_RATE_LIMIT_SLEEP)

        if (qi + 1) % 25 == 0 or qi + 1 == len(queries):
            avg_r8 = statistics.mean(r8_list) if r8_list else 0
            print(f"    Queried [{qi+1}/{len(queries)}], running recall@8={avg_r8:.3f}")

    # Populate retrieval metrics
    result.retrieval.recall_at_8 = statistics.mean(r8_list) if r8_list else 0
    result.retrieval.recall_at_20 = statistics.mean(r20_list) if r20_list else 0
    result.retrieval.mrr = statistics.mean(mrr_list) if mrr_list else 0
    result.retrieval.avg_latency_ms = statistics.mean(lat_list) if lat_list else 0
    result.retrieval.p95_latency_ms = (
        sorted(lat_list)[int(len(lat_list) * 0.95)] if lat_list else 0
    )
    result.retrieval.queries_run = len(queries)
    result.retrieval.raw_recalls_8 = r8_list
    result.retrieval.raw_recalls_20 = r20_list
    result.retrieval.raw_latencies = lat_list

    result.total_time_s = time.time() - extraction_start
    result.notes = (
        f"Mem0 SaaS, internal extraction (gpt-4.1-nano), "
        f"stored={result.extraction.total_facts}, errors={errors}, "
        f"rate_limited={rate_limited}"
    )

    # Cleanup
    print("  Cleaning up Mem0...")
    try:
        client.delete_all(user_id=user_id)
    except Exception as e:
        print(f"  Cleanup warning: {e}")

    return result


def _match_mem0_results_to_conv_ids(
    search_results: List[Dict],
    conversations: List[ConversationChunk],
) -> List[str]:
    """
    Match Mem0 search results back to source conversation IDs.

    Strategy:
    1. Check metadata for conversation_id
    2. Fall back to fuzzy token overlap matching against conversation content
    """
    matched_ids = []

    for sr in search_results:
        mem_text = sr.get("memory", "")
        metadata = sr.get("metadata", {}) or {}

        # Strategy 1: Check metadata for conversation_id
        conv_id = metadata.get("conversation_id")
        if conv_id:
            matched_ids.append(conv_id)
            continue

        # Strategy 2: Fuzzy match against all conversation content
        mem_tokens = set(mem_text.lower().split())
        if not mem_tokens:
            continue

        best_id = ""
        best_score = 0.0
        for conv in conversations:
            conv_tokens = set(conv.content.lower().split()[:100])
            if not conv_tokens:
                continue
            overlap = len(mem_tokens & conv_tokens)
            score = overlap / (len(mem_tokens | conv_tokens) + 1e-10)
            if score > best_score:
                best_score = score
                best_id = conv.id

        if best_id and best_score > 0.05:
            matched_ids.append(best_id)

    return matched_ids


# ============================================================================
# TotalReclaw E2E Pipeline
# ============================================================================

async def run_totalreclaw_e2e(
    conversations: List[ConversationChunk],
    queries: List[Dict[str, str]],
) -> E2EBenchmarkResult:
    """
    Run the TotalReclaw end-to-end pipeline.

    1. Use LLM wrapper (ombh.llm) to extract facts from raw conversations
    2. Store facts through TotalReclaw E2EE pipeline (encrypt + LSH + blind indices)
    3. Retrieve via blind index search + client-side reranking
    """
    result = E2EBenchmarkResult(
        system_name="TotalReclaw E2EE",
        privacy_score=100,
        total_conversations=len(conversations),
    )

    # Import E2EE backend and LLM extractor
    from ombh.backends.totalreclaw_e2ee import TotalReclawE2EEBackend
    from ombh.backends.base import Fact
    from ombh.llm.client import LLMClient
    from ombh.llm.extractor import FactExtractor

    # ---- Initialize components ----
    try:
        llm_client = LLMClient()
    except ValueError as e:
        print(f"  SKIP: Cannot initialize LLM client: {e}")
        result.notes = f"SKIPPED: {e}"
        return result

    extractor = FactExtractor(llm_client, min_importance=3)

    # Initialize E2EE backend (works without server for benchmarking)
    backend = TotalReclawE2EEBackend(
        base_url="http://localhost:8080",
        master_password="benchmark_e2e_password",
    )

    pipeline_start = time.time()

    # ---- Phase 1: Extraction ----
    print(f"  Extracting facts from {len(conversations)} conversations via LLM...")
    extraction_start = time.time()
    all_extracted_facts = []  # List of (conv_id, list_of_facts)
    all_importances = []
    all_confidences = []
    extraction_errors = 0

    # Process conversations with bounded concurrency
    semaphore = asyncio.Semaphore(OM_EXTRACTION_CONCURRENCY)

    async def _extract_one(conv: ConversationChunk) -> Tuple[str, List[Any]]:
        async with semaphore:
            try:
                result = await extractor.extract_from_conversation(conv.content)
                return conv.id, result.facts
            except Exception as e:
                print(f"    Extraction error for {conv.id}: {e}")
                return conv.id, []

    # Run extraction in parallel
    tasks = [_extract_one(conv) for conv in conversations]

    completed = 0
    for coro in asyncio.as_completed(tasks):
        conv_id, facts = await coro
        completed += 1
        all_extracted_facts.append((conv_id, facts))

        for f in facts:
            all_importances.append(f.importance)
            all_confidences.append(f.confidence)

        if not facts:
            extraction_errors += 1

        if completed % 10 == 0 or completed == len(conversations):
            total_facts = sum(len(fs) for _, fs in all_extracted_facts)
            elapsed = time.time() - extraction_start
            print(f"    Extracted [{completed}/{len(conversations)}], "
                  f"total_facts={total_facts}, "
                  f"elapsed={elapsed:.0f}s")

    extraction_time = time.time() - extraction_start
    total_facts = sum(len(fs) for _, fs in all_extracted_facts)

    result.extraction.total_facts = total_facts
    result.extraction.avg_importance = (
        statistics.mean(all_importances) if all_importances else 0
    )
    result.extraction.avg_confidence = (
        statistics.mean(all_confidences) if all_confidences else 0
    )
    result.extraction.total_extraction_time_ms = extraction_time * 1000
    result.extraction.facts_per_conversation = (
        total_facts / len(conversations) if conversations else 0
    )
    result.extraction.extraction_errors = extraction_errors

    print(f"  Extraction complete: {total_facts} facts from {len(conversations)} "
          f"conversations in {extraction_time:.1f}s")
    print(f"  Avg importance: {result.extraction.avg_importance:.1f}, "
          f"avg confidence: {result.extraction.avg_confidence:.2f}")

    # ---- Phase 2: Storage (E2EE) ----
    print(f"  Storing {total_facts} facts via E2EE pipeline...")
    storage_start = time.time()

    # Build a map: conv_id -> extracted fact texts (for retrieval matching)
    conv_id_to_facts: Dict[str, List[str]] = {}

    for conv_id, facts in all_extracted_facts:
        # Convert extracted facts to backend Fact format
        backend_facts = []
        fact_texts = []
        for ef in facts:
            backend_facts.append(Fact(
                fact_text=ef.fact_text,
                fact_type=ef.type,
                importance=ef.importance,
                entities=[e.name for e in ef.entities],
                metadata={
                    "confidence": ef.confidence,
                    "action": ef.action,
                    "conversation_id": conv_id,
                },
            ))
            fact_texts.append(ef.fact_text)

        conv_id_to_facts[conv_id] = fact_texts

        if backend_facts:
            await backend.store(
                facts=backend_facts,
                session_id=f"e2e_benchmark_{conv_id}",
                user_id="benchmark_user",
            )

    storage_time = time.time() - storage_start
    print(f"  Storage complete in {storage_time:.1f}s")

    # ---- Phase 3: Retrieval ----
    print(f"  Running {len(queries)} retrieval queries...")
    r8_list, r20_list, mrr_list, lat_list = [], [], [], []

    for qi, q in enumerate(queries):
        query_text = q["query"]
        source_id = q["source_id"]

        start = time.perf_counter()
        try:
            retrieved = await backend.retrieve(
                query=query_text,
                k=20,
                min_importance=1,
                user_id="benchmark_user",
            )
        except Exception as e:
            print(f"    Retrieve error: {e}")
            retrieved = []

        latency = (time.perf_counter() - start) * 1000
        lat_list.append(latency)

        # Match retrieved facts to source conversations
        matched_conv_ids = _match_om_results_to_conv_ids(
            retrieved, all_extracted_facts
        )

        # Recall: did we retrieve facts from the correct conversation?
        top_8_match = 1.0 if source_id in matched_conv_ids[:8] else 0.0
        top_20_match = 1.0 if source_id in matched_conv_ids[:20] else 0.0
        r8_list.append(top_8_match)
        r20_list.append(top_20_match)

        # MRR
        found_rank = 0.0
        for rank, cid in enumerate(matched_conv_ids[:20]):
            if cid == source_id:
                found_rank = 1.0 / (rank + 1)
                break
        mrr_list.append(found_rank)

        if (qi + 1) % 25 == 0 or qi + 1 == len(queries):
            avg_r8 = statistics.mean(r8_list) if r8_list else 0
            print(f"    Queried [{qi+1}/{len(queries)}], running recall@8={avg_r8:.3f}")

    # Populate retrieval metrics
    result.retrieval.recall_at_8 = statistics.mean(r8_list) if r8_list else 0
    result.retrieval.recall_at_20 = statistics.mean(r20_list) if r20_list else 0
    result.retrieval.mrr = statistics.mean(mrr_list) if mrr_list else 0
    result.retrieval.avg_latency_ms = statistics.mean(lat_list) if lat_list else 0
    result.retrieval.p95_latency_ms = (
        sorted(lat_list)[int(len(lat_list) * 0.95)] if lat_list else 0
    )
    result.retrieval.queries_run = len(queries)
    result.retrieval.raw_recalls_8 = r8_list
    result.retrieval.raw_recalls_20 = r20_list
    result.retrieval.raw_latencies = lat_list

    result.total_time_s = time.time() - pipeline_start

    # LLM usage stats
    llm_stats = llm_client.usage.to_dict()
    result.notes = (
        f"TotalReclaw E2EE pipeline, extraction via {llm_client._model}, "
        f"LLM tokens={llm_stats['total_tokens']}, "
        f"LLM calls={llm_stats['total_calls']}, "
        f"extraction_time={extraction_time:.1f}s"
    )

    # Close backend
    await backend.close()

    return result


def _match_om_results_to_conv_ids(
    retrieved: List[Any],  # List[RetrievedMemory]
    all_extracted_facts: List[Tuple[str, List[Any]]],
) -> List[str]:
    """
    Match TotalReclaw retrieval results to source conversation IDs.

    Uses fuzzy token overlap between retrieved fact text and the facts
    extracted from each conversation.
    """
    # Build index: fact_text_tokens -> conv_id
    conv_fact_tokens: Dict[str, set] = {}
    for conv_id, facts in all_extracted_facts:
        tokens = set()
        for f in facts:
            tokens.update(f.fact_text.lower().split())
        conv_fact_tokens[conv_id] = tokens

    matched_ids = []
    for mem in retrieved:
        try:
            retrieved_text = mem.fact.fact_text if hasattr(mem, "fact") else ""
        except Exception:
            retrieved_text = ""

        if not retrieved_text:
            continue

        ret_tokens = set(retrieved_text.lower().split())
        if not ret_tokens:
            continue

        # Check metadata for conversation_id
        try:
            meta = mem.fact.metadata if hasattr(mem.fact, "metadata") else {}
            conv_id = meta.get("conversation_id")
            if conv_id:
                matched_ids.append(conv_id)
                continue
        except Exception:
            pass

        # Fuzzy match
        best_id = ""
        best_score = 0.0
        for conv_id, tokens in conv_fact_tokens.items():
            if not tokens:
                continue
            overlap = len(ret_tokens & tokens)
            score = overlap / (len(ret_tokens | tokens) + 1e-10)
            if score > best_score:
                best_score = score
                best_id = conv_id

        if best_id and best_score > 0.05:
            matched_ids.append(best_id)

    return matched_ids


# ============================================================================
# Main Benchmark
# ============================================================================

async def run_e2e_benchmark():
    """Run the full end-to-end benchmark."""
    print("=" * 80)
    print("END-TO-END PIPELINE BENCHMARK: TotalReclaw E2EE vs Mem0 Platform")
    print("=" * 80)
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Config: max_conversations={MAX_CONVERSATIONS}, max_queries={MAX_QUERIES}")

    # ---- Load data ----
    print("\n[1/5] Loading raw conversation data...")
    conversations = load_raw_conversations(MAX_CONVERSATIONS)
    if not conversations:
        print("  ERROR: No conversations loaded. Check data paths.")
        return

    # ---- Generate queries ----
    print("\n[2/5] Generating retrieval queries...")
    queries = generate_retrieval_queries(conversations, MAX_QUERIES)

    results: Dict[str, E2EBenchmarkResult] = {}

    # ---- Benchmark: TotalReclaw E2EE ----
    print("\n[3/5] Running TotalReclaw E2EE pipeline...")
    om_result = await run_totalreclaw_e2e(conversations, queries)
    results["totalreclaw"] = om_result
    _print_system_summary("TotalReclaw E2EE", om_result)

    # ---- Benchmark: Mem0 Platform ----
    print("\n[4/5] Running Mem0 Platform pipeline...")
    mem0_result = await run_mem0_e2e(conversations, queries)
    results["mem0"] = mem0_result
    _print_system_summary("Mem0 Platform", mem0_result)

    # ---- Print final comparison ----
    print("\n[5/5] Final comparison...")
    _print_comparison(results)

    # ---- Save results ----
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "e2e_benchmark_results.json"
    output = {
        "benchmark_type": "e2e_pipeline",
        "description": (
            "Full pipeline benchmark: raw conversations -> extraction -> "
            "storage -> retrieval. Each system uses its own extraction."
        ),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "max_conversations": MAX_CONVERSATIONS,
            "max_queries": MAX_QUERIES,
            "seed": SEED,
            "om_extraction_concurrency": OM_EXTRACTION_CONCURRENCY,
        },
        "dataset": {
            "total_conversations": len(conversations),
            "total_queries": len(queries),
            "sources": list(set(c.source for c in conversations)),
        },
        "results": {name: r.to_dict() for name, r in results.items()},
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    return results


def _print_system_summary(name: str, result: E2EBenchmarkResult) -> None:
    """Print a summary for one system."""
    print(f"\n  --- {name} Summary ---")
    if "SKIPPED" in result.notes:
        print(f"  {result.notes}")
        return

    ext = result.extraction
    ret = result.retrieval
    print(f"  Extraction: {ext.total_facts} facts, "
          f"avg_importance={ext.avg_importance:.1f}, "
          f"avg_confidence={ext.avg_confidence:.2f}, "
          f"facts/conv={ext.facts_per_conversation:.1f}, "
          f"errors={ext.extraction_errors}")
    print(f"  Retrieval:  Recall@8={ret.recall_at_8:.3f}, "
          f"Recall@20={ret.recall_at_20:.3f}, "
          f"MRR={ret.mrr:.3f}, "
          f"Latency={ret.avg_latency_ms:.1f}ms")
    print(f"  Privacy:    {result.privacy_score}")
    print(f"  Total time: {result.total_time_s:.1f}s")


def _print_comparison(results: Dict[str, E2EBenchmarkResult]) -> None:
    """Print the head-to-head comparison table."""
    print("\n" + "=" * 80)
    print("FINAL RESULTS -- E2E Pipeline Comparison")
    print("=" * 80)

    # Header
    header = (
        f"{'System':<25} {'Facts':>7} {'Imp':>6} {'Conf':>6} "
        f"{'R@8':>8} {'R@20':>8} {'MRR':>8} {'Lat.':>10} {'Priv':>6}"
    )
    print(header)
    print("-" * 90)

    for name in ["totalreclaw", "mem0"]:
        if name not in results:
            continue
        r = results[name]
        if "SKIPPED" in r.notes:
            print(f"{r.system_name:<25} {'SKIPPED':>7}")
            continue

        ext = r.extraction
        ret = r.retrieval
        print(
            f"{r.system_name:<25} "
            f"{ext.total_facts:>7} "
            f"{ext.avg_importance:>6.1f} "
            f"{ext.avg_confidence:>6.2f} "
            f"{ret.recall_at_8:>8.3f} "
            f"{ret.recall_at_20:>8.3f} "
            f"{ret.mrr:>8.3f} "
            f"{ret.avg_latency_ms:>7.1f}ms "
            f"{r.privacy_score:>6}"
        )

    # Head-to-head
    if "totalreclaw" in results and "mem0" in results:
        om = results["totalreclaw"]
        m0 = results["mem0"]

        if "SKIPPED" in om.notes or "SKIPPED" in m0.notes:
            print("\n  (Cannot compare: one or both systems were skipped)")
            return

        print(f"\n{'=' * 60}")
        print("HEAD-TO-HEAD: TotalReclaw E2EE vs Mem0 Platform")
        print(f"{'=' * 60}")

        comparisons = [
            ("Facts extracted", om.extraction.total_facts, m0.extraction.total_facts, True),
            ("Avg importance", om.extraction.avg_importance, m0.extraction.avg_importance, True),
            ("Facts/conv", om.extraction.facts_per_conversation, m0.extraction.facts_per_conversation, True),
            ("Recall@8", om.retrieval.recall_at_8, m0.retrieval.recall_at_8, True),
            ("Recall@20", om.retrieval.recall_at_20, m0.retrieval.recall_at_20, True),
            ("MRR", om.retrieval.mrr, m0.retrieval.mrr, True),
            ("Privacy", om.privacy_score, m0.privacy_score, True),
            ("Avg latency", om.retrieval.avg_latency_ms, m0.retrieval.avg_latency_ms, False),
        ]

        for label, om_val, m0_val, higher_better in comparisons:
            delta = om_val - m0_val
            if isinstance(om_val, float):
                om_str = f"{om_val:.3f}"
                m0_str = f"{m0_val:.3f}"
                delta_str = f"{delta:+.3f}"
            else:
                om_str = str(om_val)
                m0_str = str(m0_val)
                delta_str = f"{delta:+}"

            if "latency" in label.lower():
                om_str += "ms"
                m0_str += "ms"
                delta_str += "ms"
                winner = "N/A*"
            elif higher_better:
                winner = "OM" if delta > 0 else ("Mem0" if delta < 0 else "TIE")
            else:
                winner = "OM" if delta < 0 else ("Mem0" if delta > 0 else "TIE")

            print(f"  {label:<20} OM={om_str:<14} Mem0={m0_str:<14} "
                  f"Delta={delta_str:<14} {winner}")

        print(f"\n  * Latency comparison is unfair: TotalReclaw runs locally, "
              f"Mem0 includes network RTT.")

        # Extraction insight
        print(f"\n{'=' * 60}")
        print("EXTRACTION COMPARISON")
        print(f"{'=' * 60}")
        print(f"  TotalReclaw extracted {om.extraction.total_facts} facts "
              f"({om.extraction.facts_per_conversation:.1f}/conv, "
              f"avg importance={om.extraction.avg_importance:.1f})")
        print(f"  Mem0 extracted {m0.extraction.total_facts} facts "
              f"({m0.extraction.facts_per_conversation:.1f}/conv)")
        print(f"\n  Note: Mem0 does its own internal extraction with gpt-4.1-nano.")
        print(f"  TotalReclaw uses custom extraction prompts (configurable model).")


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Synchronous entry point."""
    asyncio.run(run_e2e_benchmark())


if __name__ == "__main__":
    main()
