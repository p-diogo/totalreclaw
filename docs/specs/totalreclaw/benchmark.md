<!--
Product: TotalReclaw
Formerly: tech specs/v0.3 (grok)/TS v0.3: TotalReclaw Benchmark Harness (OMBH).md
Version: 1.1
Last updated: 2026-02-24
-->

# Technical Specification: TotalReclaw Benchmark Harness (OMBH) v1.1 — 3-Skill Edition

**Version:** 1.1 (Complete & Self-Contained for Coding Agent)  
**Date:** February 20, 2026  
**Author:** Grok (on behalf of the TotalReclaw team)  
**Target Audience:** Any coding agent / developer with **zero prior context** on TotalReclaw, OpenClaw, or the project.  
**Goal:** Build a standalone, reproducible, agentic benchmark framework that runs **identical** multi-session conversations through exactly three memory systems and produces publication-grade apples-to-apples leaderboards on accuracy, latency, storage, cost, downstream quality, and privacy.

**Core Principle**  
**One source of truth** for data, triggers, extraction moments, and evaluation queries. Every memory system sees **exactly** the same input turns, same pre-compaction flushes, same ground-truth questions, and same downstream tasks. No manual copying or cherry-picking.

---

## 1. The Three Systems Being Benchmarked (Hard-Coded for v1.1)

1. **TotalReclaw E2EE (Crypto/LSH)** — Your new ClawHub skill + TotalReclaw server (using the LSH + encrypted-embeddings spec). This is the privacy champion we are proving.
2. **Native OpenClaw QMD** — Standard OpenClaw installation with its built-in QMD hybrid memory skill (default Markdown + vector hybrid, no extra plugins).
3. **OpenClaw + Official Mem0 Plugin** — Standard OpenClaw installation with the official `@mem0/openclaw-mem0` plugin enabled (the most popular and performant third-party alternative).

These three represent:
- The new private solution (TotalReclaw)
- The default everyone already uses (QMD)
- The best third-party alternative people actually switch to (Mem0)

---

## 2. Data Layer — Unified Corpus

All benchmarks run on the **same** datasets stored in `dataset/` (JSONL format).

### Tiers (loaded together or separately via CLI flags)
- **Anchor Tier**: Your original 1,162 WhatsApp conversation chunks + 50 LLM-generated ground-truth queries. NOTE: I also have a raw slack export now. The previous scripts can only process whatsapp data (already stored somewhere), but not yet slack. The slack data to be imported must first be anonimized.   
- **Gold-Standard Tier**: Official LoCoMo-10 dataset (10 full multi-session conversations from Snap Research, used by Mem0, Zep, LongMemEval, etc.).
- **Scale Tier**: 200 synthetic OpenClaw-style conversations (generated once and cached).

**Total target for full runs**: 210+ conversations, ~45k turns, ~4,500 ground-truth queries.

### Agentic Data Generator Workflow (Runs Once, Cached Forever)
The harness includes a fully automated generator so you can expand the corpus anytime.

## 1. **Persona & Event Graph Generator** (uses the non-thinking free model from openrouter temperature=0.7 optionally, JSON mode):
   ```prompt
   Create a realistic 30-session conversation history between a software engineer and their OpenClaw AI assistant.
   Include evolving user preferences, code decisions that later get revised, tool-use successes/failures, daily life events, and preference drift.
   Mark pre-compaction moments naturally (when context would exceed soft threshold).
   Output **strict JSON only**:
   {
     "conversation_id": "conv_001",
     "persona": { ... },
     "sessions": [
       {
         "session_id": "sess_001",
         "turns": [ {"role": "user"|"assistant", "content": "...", "timestamp": "ISO"} ],
         "pre_compaction_moment": true/false
       }
     ],
     "ground_truth_queries": [
       {
         "query": "What did I decide about databases last month?",
         "expected_facts": ["array of fact texts"],
         "ideal_answer": "detailed expected response"
       }
     ]
   }

Validation Agent (second LLM call):
Checks temporal consistency, factual deduplication, answerability, and realism.
If any check fails → regenerate that conversation.

Export & Pre-process:
Save as dataset/openclaw_synthetic_*.jsonl
Pre-compute embeddings for all turns/queries (cached).


Provided Scripts (coding agent must implement):
Bashpython -m ombh.dataset.download_locomo          # pulls official LoCoMo-10
python -m ombh.dataset.generate_synthetic \
  --num 200 \
  --style openclaw \
  --seed 42 \
  --model claude-3-5-sonnet-20241022

3. Spin-Up Instructions for the Two OpenClaw Instances
The harness uses Docker Compose to run real isolated OpenClaw instances so triggers (pre-compaction flush, context builder, etc.) behave exactly as in production. 
Note: make sure openclaw is launched in a secure way, not exposed to the internet, only accessible in localhost. 
docker-compose.testbed.yml (coding agent must create this file):
```
YAMLversion: '3.9'
services:
  openclaw-qmd:
    image: openclaw/openclaw:latest
    container_name: ombh-qmd
    environment:
      MEMORY_BACKEND: qmd_only
      OPENCLAW_CONFIG_PATH: /config/qmd.yaml
      LOG_LEVEL: INFO
    ports:
      - "8081:8080"
    volumes:
      - ./config/qmd.yaml:/config/qmd.yaml:ro
    restart: unless-stopped

  openclaw-mem0:
    image: openclaw/openclaw:latest
    container_name: ombh-mem0
    environment:
      MEMORY_BACKEND: mem0
      MEM0_API_KEY: ${MEM0_API_KEY}   # loaded from .env
      OPENCLAW_CONFIG_PATH: /config/mem0.yaml
      LOG_LEVEL: INFO
    ports:
      - "8082:8080"
    volumes:
      - ./config/mem0.yaml:/config/mem0.yaml:ro
    restart: unless-stopped
```

Startup command (run once at beginning of benchmark):
```Bash
docker compose -f docker-compose.testbed.yml up -d
sleep 15  # wait for both instances to be healthy
```
TotalReclaw E2EE does not need a full OpenClaw instance — it uses the pure client library (in-process).

## 4. Unified MemoryBackend Abstract Interface
Every system implements this exact Python abstract base class (in ombh/backends/base.py):
Pythonfrom abc import ABC, abstractmethod
from typing import List, Dict, Any

```class MemoryBackend(ABC):
    @abstractmethod
    def store(self, facts: List[Dict[str, Any]], session_id: str, user_id: str = "test_user") -> None:
        """facts = [{"fact_text": "...", "type": "...", "importance": 8, "entities": [...], ...}]"""
        pass

    @abstractmethod
    def retrieve(self, query: str, k: int = 8, min_importance: int = 5) -> List[Dict[str, Any]]:
        """Returns list of retrieved memories with scores, facts, and graph snippets"""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Returns latency histograms, storage_mb, tokens_used, cost_estimate, etc."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Clear all memory for a clean run"""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify the backend is responsive"""
        pass
```

## 5. Three Concrete Adapters (Must Be Implemented)

- `ombh/backends/totalreclaw_e2ee.py` — Uses your new TotalReclaw Python client library (LSH version).
- `ombh/backends/openclaw_qmd.py` — HTTP client talking to port 8081.
- `ombh/backends/openclaw_mem0.py` — HTTP client talking to port 8082.

Each adapter must respect the exact same extraction triggers and config values as defined in the TotalReclaw Skill spec.

## 6. Agentic Simulation Workflow (LangGraph Orchestrator)
The core is a LangGraph pipeline that replays conversations:
Nodes (executed for every conversation):

LoadConversation — load from dataset.
TurnSimulator (loop over turns):
Feed turn to all three backends simultaneously.
If pre_compaction_moment or every 5 turns → call .store() on all three.
Every 10 turns → sample 2–3 ground-truth queries → call .retrieve() on all three.

### DownstreamJudge:
Feed retrieved memories + current turn to a strong LLM (Claude-3.5 or Grok-4).
Score factual correctness, preference adherence, temporal accuracy (0–100).

MetricsCollector — record latency, storage, etc.

Parallel execution: All three backends run in separate processes for fairness.

## 7. One-Command Benchmark Runner
```python -m ombh.run \
  --systems totalreclaw_e2ee,openclaw_qmd,openclaw_mem0 \
  --dataset locomo+openclaw_synthetic \
  --num_conversations 150 \
  --output reports/2026-02-20_3way.html \
  --judge_model claude-3-5-sonnet-20241022
  ```
Output:

Beautiful HTML dashboard with side-by-side tables + Plotly charts (accuracy vs latency scatter, forgetting curves, cost curves).
Markdown leaderboard.
Raw JSON + CSV for further analysis.
Privacy column: 100 % for TotalReclaw, 0 % for the others.


## 8. Verification Suite (Run Before Any A/B)
Automated checks (run via python -m ombh.verify):

Correctness: Force “remember I hate pineapple” → ask 20 sessions later → must retrieve with high score in TotalReclaw.
Forgetting: Simulate 90 days decay → verify low-importance facts evicted in TotalReclaw.
Portability: Export/import TotalReclaw with password → re-test queries (100 % match).
Consistency: Run same conversation 3× → variance <2 %.
Privacy leak test: Attempt simple inversion on TotalReclaw blind indices/embeddings → must score 0 usable info.


## 9. Implementation Order (Recommended for Coding Agent)
**Days 1–2**
Dataset loader + synthetic generator + Docker Compose.

**Days 3–4**
Unified interface + three adapters + health checks.

**Days 5–6**
LangGraph simulator + metrics collector + LLM judge.

**Day 7**
Reporting dashboard + verification suite + one-command runner + full test on 10 conversations.


## 10. Deliverables Expected

ombh/ installable Python package (pip install -e .)
docker-compose.testbed.yml
Complete HTML/PDF report templates
notebooks/analysis.ipynb for interactive exploration
Full README.md with screenshots of expected leaderboard, installation, and example commands
CI-ready GitHub Actions workflow (optional but nice)

Configuration file (ombh/config.yaml) for all tunables (number of conversations, judge model, etc.).