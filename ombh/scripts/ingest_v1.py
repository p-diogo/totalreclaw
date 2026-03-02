#!/usr/bin/env python3
"""Standalone script to ingest conversations into TotalReclaw v1 (port 8085).

Loads the same 50 conversations that were ingested into the other 4 benchmark
instances and feeds them to the v1 instance via the chat completions API.

Usage:
    python scripts/ingest_v1.py
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INSTANCE = "totalreclaw-v1"
PORT = 8085
AUTH_TOKEN = "benchmark-token-2026"
MODEL = "glm-4.5-air"
BASE_URL = f"http://127.0.0.1:{PORT}/v1/chat/completions"

DATA_DIR = Path(__file__).parent.parent / "synthetic-benchmark"
CONV_DIR = DATA_DIR / "conversations"
RESULTS_DIR = DATA_DIR / "benchmark-results"
INGEST_RESULTS_PATH = RESULTS_DIR / "ingest-results.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest-v1")


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class IngestResult:
    instance: str
    conv_id: str
    success: bool
    turns_sent: int
    latency_ms: float
    error: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_target_conv_ids() -> List[str]:
    """Get the list of conversation IDs that were ingested into totalreclaw."""
    with open(INGEST_RESULTS_PATH) as f:
        data = json.load(f)
    conv_ids = sorted(set(
        r["conv_id"] for r in data
        if r["instance"] == "totalreclaw" and r["success"]
    ))
    return conv_ids


def load_conversation(conv_id: str) -> List[Dict[str, str]]:
    """Load a single conversation from its JSONL file."""
    path = CONV_DIR / f"{conv_id}.jsonl"
    messages = []
    for line in path.read_text().strip().split("\n"):
        if line.strip():
            messages.append(json.loads(line))
    return messages


async def ingest_conversation(
    client: httpx.AsyncClient,
    conv_id: str,
    messages: List[Dict[str, str]],
) -> IngestResult:
    """Feed a conversation to the TotalReclaw v1 instance."""
    try:
        # Ensure last message is from user to trigger agent_end hook
        chat_messages = list(messages)
        if chat_messages and chat_messages[-1]["role"] == "assistant":
            chat_messages.append({
                "role": "user",
                "content": "Please summarize the key facts you learned about me from our conversation.",
            })

        payload = {
            "model": MODEL,
            "messages": chat_messages,
            "temperature": 0.3,
            "max_tokens": 512,
        }
        headers = {
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        resp = await client.post(BASE_URL, json=payload, headers=headers, timeout=180.0)
        latency = (time.monotonic() - start) * 1000.0
        resp.raise_for_status()

        # Parse to verify we got a valid response
        data = resp.json()
        _ = data["choices"][0]["message"]["content"]

        return IngestResult(
            instance=INSTANCE,
            conv_id=conv_id,
            success=True,
            turns_sent=len(chat_messages),
            latency_ms=latency,
        )
    except Exception as e:
        return IngestResult(
            instance=INSTANCE,
            conv_id=conv_id,
            success=False,
            turns_sent=len(messages),
            latency_ms=0.0,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    logger.info("=== TotalReclaw v1 Ingest (port %d) ===", PORT)

    # Get target conversation IDs
    conv_ids = get_target_conv_ids()
    logger.info("Target conversations: %d", len(conv_ids))

    # Check instance health
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"http://127.0.0.1:{PORT}/", timeout=5.0)
            if resp.status_code >= 500:
                logger.error("Instance unhealthy: HTTP %d", resp.status_code)
                return
            logger.info("Instance healthy (HTTP %d)", resp.status_code)
        except Exception as e:
            logger.error("Instance unreachable: %s", e)
            return

    # Ingest conversations sequentially (concurrency=1)
    results: List[IngestResult] = []
    started_at = datetime.now().isoformat()

    async with httpx.AsyncClient() as client:
        for i, conv_id in enumerate(conv_ids):
            messages = load_conversation(conv_id)
            logger.info(
                "[%d/%d] Ingesting %s (%d turns)...",
                i + 1, len(conv_ids), conv_id, len(messages),
            )

            result = await ingest_conversation(client, conv_id, messages)
            results.append(result)

            if result.success:
                logger.info(
                    "[%d/%d] %s — OK (%.1fs, %d turns)",
                    i + 1, len(conv_ids), conv_id,
                    result.latency_ms / 1000.0, result.turns_sent,
                )
            else:
                logger.error(
                    "[%d/%d] %s — FAILED: %s",
                    i + 1, len(conv_ids), conv_id, result.error,
                )

            # Small delay between conversations
            await asyncio.sleep(0.5)

    # Summary
    successes = sum(1 for r in results if r.success)
    failures = sum(1 for r in results if not r.success)
    avg_latency = (
        sum(r.latency_ms for r in results if r.success) / max(1, successes)
    )
    total_time = sum(r.latency_ms for r in results if r.success) / 1000.0

    logger.info("")
    logger.info("=" * 60)
    logger.info("  INGEST COMPLETE — TotalReclaw v1")
    logger.info("=" * 60)
    logger.info("  Successful: %d / %d", successes, len(results))
    logger.info("  Failed:     %d", failures)
    logger.info("  Avg latency: %.1fs per conversation", avg_latency / 1000.0)
    logger.info("  Total time:  %.1fs (%.1f min)", total_time, total_time / 60.0)
    logger.info("=" * 60)

    # Save results
    output_path = RESULTS_DIR / "ingest-results-v1.json"
    with open(output_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    logger.info("Results saved to %s", output_path)

    # Also append to the main ingest-results.json
    with open(INGEST_RESULTS_PATH) as f:
        all_results = json.load(f)

    # Remove any existing v1 results to avoid duplicates
    all_results = [r for r in all_results if r.get("instance") != INSTANCE]
    all_results.extend([asdict(r) for r in results])

    with open(INGEST_RESULTS_PATH, "w") as f:
        json.dump(all_results, f, indent=2)
    logger.info("Appended v1 results to %s", INGEST_RESULTS_PATH)

    if failures > 0:
        logger.warning("Failed conversations:")
        for r in results:
            if not r.success:
                logger.warning("  %s: %s", r.conv_id, r.error)


if __name__ == "__main__":
    asyncio.run(main())
