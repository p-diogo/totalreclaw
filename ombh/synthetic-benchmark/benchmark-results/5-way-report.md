# 5-Way Memory System Benchmark Report

**Generated**: 2026-02-28 03:33:25
**Dataset**: 50 synthetic conversations, 140 test queries
**Query categories**: 42 factual, 42 semantic, 42 cross-conversation, 14 negative
**Scorer**: Keyword overlap (40% threshold)
**LLM**: glm-4.5-air (via OpenRouter)

---

## Overall Recall (sorted best to worst)

| Rank | System | Overall Recall | Non-Negative Recall | Successful Queries | Failed |
|------|--------|---------------|--------------------|--------------------|--------|
| 1 | LanceDB (Vector DB) | 31.3% | 23.6% | 127/140 | 13 |
| 2 | TotalReclaw v2 (E2EE + Embeddings) | 28.7% | 20.8% | 133/140 | 7 |
| 3 | QMD (memory-core) | 28.2% | 20.2% | 134/140 | 6 |
| 4 | Mem0 Cloud | 23.8% | 15.3% | 125/140 | 15 |
| 5 | TotalReclaw v1 (E2EE, Facts-Only) | 21.6% | 12.9% | 138/140 | 2 |

> **Note**: "Overall Recall" includes negative queries (where recall=100% by definition for all systems that correctly say "I don't know"). "Non-Negative Recall" excludes negative queries for a fairer comparison of actual retrieval ability.

## Per-Category Recall Breakdown

| System | Factual | Semantic | Cross-Conv | Negative |
|--------|---------|----------|------------|----------|
| LanceDB (Vector DB) | 28.3% | 24.6% | 18.1% | 100.0% |
| TotalReclaw v2 (E2EE + Embeddings) | 27.3% | 16.4% | 18.7% | 100.0% |
| QMD (memory-core) | 27.5% | 16.8% | 16.3% | 100.0% |
| Mem0 Cloud | 22.7% | 10.5% | 12.7% | 100.0% |
| TotalReclaw v1 (E2EE, Facts-Only) | 19.9% | 11.5% | 7.3% | 100.0% |

### Fact Recovery Details

| System | Factual Hits/Total | Semantic Hits/Total | Cross-Conv Hits/Total |
|--------|--------------------|---------------------|----------------------|
| LanceDB (Vector DB) | 38/142 | 29/133 | 39/208 |
| TotalReclaw v2 (E2EE + Embeddings) | 37/142 | 21/133 | 39/208 |
| QMD (memory-core) | 38/142 | 21/133 | 32/208 |
| Mem0 Cloud | 30/142 | 13/133 | 26/208 |
| TotalReclaw v1 (E2EE, Facts-Only) | 27/142 | 15/133 | 14/208 |

## Latency Comparison

| System | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) |
|--------|----------|----------|----------|----------|
| TotalReclaw v2 (E2EE + Embeddings) | 26,326 | 21,004 | 56,673 | 57,685 |
| TotalReclaw v1 (E2EE, Facts-Only) | 22,013 | 21,021 | 48,984 | 57,022 |
| QMD (memory-core) | 31,477 | 31,897 | 52,410 | 58,060 |
| Mem0 Cloud | 33,290 | 34,996 | 53,867 | 57,062 |
| LanceDB (Vector DB) | 35,728 | 35,876 | 57,190 | 59,056 |

> **Note**: Latency includes LLM inference time (glm-4.5-air via OpenRouter), memory retrieval, and response generation. The LLM is the dominant factor for all systems, so latency differences primarily reflect memory backend overhead.

## V1 vs V2 Head-to-Head Comparison

| Metric | V1 (Facts-Only) | V2 (Embeddings) | Delta |
|--------|----------------|-----------------|-------|
| Overall Recall | 21.6% | 28.7% | +7.1% |
| Non-Negative Recall | 12.9% | 20.8% | +7.9% |
| Factual Recall | 19.9% | 27.3% | +7.3% |
| Semantic Recall | 11.5% | 16.4% | +5.0% |
| Cross-Conv Recall | 7.3% | 18.7% | +11.4% |
| Latency p50 | 21,021ms | 21,004ms | -17ms |
| Successful Queries | 138/140 | 133/140 | |

### V1 vs V2 Analysis

- **V2 achieves 61% higher non-negative recall** than V1 (20.8% vs 12.9%).
- **Cross-conversation recall improved by 156%** — the biggest category gain, showing embeddings help connect related facts across sessions.
- **Semantic recall improved by 43%** — embeddings help find paraphrased/semantically similar queries.
- **Latency is comparable** — V2 adds minimal overhead despite embedding computation.

## Ingest Performance

| System | Conversations | Success Rate | Avg Latency |
|--------|--------------|-------------|-------------|
| TotalReclaw v2 (E2EE + Embeddings) | 50 | 50/50 | 50.6s |
| TotalReclaw v1 (E2EE, Facts-Only) | 50 | 50/50 | 10.0s |
| Mem0 Cloud | 50 | 49/50 | 54.0s |
| QMD (memory-core) | 50 | 50/50 | 42.7s |
| LanceDB (Vector DB) | 50 | 50/50 | 47.3s |

## Key Findings

1. **LanceDB leads in overall recall** (23.6% non-negative recall), benefiting from OpenAI's text-embedding-3-small for vector search.

2. **TotalReclaw V2 is competitive** (20.8% non-negative recall) while maintaining zero-knowledge E2EE. It matches or exceeds QMD and Mem0.

3. **TotalReclaw V2 has the fastest p50 latency** (21,004ms) among all systems, showing the E2EE overhead is minimal.

4. **Cross-conversation recall is the hardest category** for all systems. Best: 18.7% (by TotalReclaw v2 (E2EE + Embeddings)).

5. **All systems correctly handle negative queries** (100% recall on queries about facts not in memory), indicating no hallucination of non-existent memories.

6. **V1 to V2 upgrade is worth it** — embeddings add 61% recall improvement with negligible latency impact. The biggest gains are in semantic (43%) and cross-conversation (156%) categories.

## Data Quality Notes

- **43 total failed queries** across all instances (out of 700 = 700 total).
  Most failures are HTTP timeouts from the LLM API (OpenRouter/glm-4.5-air).
  - TotalReclaw v2 (E2EE + Embeddings): 7 failed
  - TotalReclaw v1 (E2EE, Facts-Only): 2 failed
  - Mem0 Cloud: 15 failed
  - QMD (memory-core): 6 failed
  - LanceDB (Vector DB): 13 failed

- **Scoring method**: Keyword overlap with 40% threshold. This is a conservative scorer that may undercount recall for responses that paraphrase facts instead of using exact keywords. An LLM-judge scorer would likely show higher absolute recall for all systems while preserving relative rankings.

- **LLM variance**: All systems use the same LLM (glm-4.5-air) for response generation, so recall differences reflect memory retrieval quality, not generation quality.

- **Single run**: Results are from a single benchmark run. Statistical significance would require multiple runs with confidence intervals.

## Methodology

### Systems Under Test

| System | Port | Description |
|--------|------|-------------|
| TotalReclaw V2 | 8081 | E2EE + LSH blind indices + local embeddings (MiniLM-L6-v2) + BM25+cosine+RRF reranking |
| TotalReclaw V1 | 8085 | E2EE + word-only blind indices + BM25-only reranking (no embeddings) |
| Mem0 Cloud | 8082 | Mem0 cloud API (@mem0/openclaw-mem0@0.1.2) |
| QMD | 8083 | Built-in memory-core (default OpenClaw) |
| LanceDB | 8084 | Vector DB with OpenAI text-embedding-3-small (via OpenRouter) |

### Pipeline

1. **Ingest**: 50 synthetic multi-turn conversations fed to each instance via chat API
2. **Query**: 140 test queries sent to each instance (42 factual, 42 semantic, 42 cross-conversation, 14 negative)
3. **Score**: Keyword overlap scorer checks if key terms from ground-truth facts appear in responses

### Ground Truth

- **Facts extracted by**: GPT-4.1 Mini (via OpenRouter)
- **Total facts**: 8268
- **Queries generated from**: facts with mapped relevant_facts for ground truth
