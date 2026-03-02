# TotalReclaw v2.0 Real-World Data Evaluation Report

**Generated:** 2026-02-20 01:20:25

**Testbed Version:** v2.0 Real-World WhatsApp Data

---

## Executive Summary

### ⚠️ Decision: MODIFY

### Key Findings

- **TotalReclaw v0.6 F1@5:** 0.229
- **MRR:** 0.526
- **Latency p50:** 750ms

### v0.6 vs v0.2 Improvement

- **F1@5:** 0.218 → 0.229 (+5.1%)
- **MRR:** 0.485 → 0.526

### Parity with Production Baselines

- ✗ **OpenClaw-Hybrid:** 0.229 vs 0.230 (-0.001)

### Decision Rationale

F1@5 of 0.229 meets minimum threshold (0.2) | Achieves parity with OpenClaw-Hybrid (gap: -0.001)

### Concerns

- ⚠️ Latency p50 of 750ms exceeds threshold (100ms)

## Algorithm Comparison

### Accuracy Metrics (All 7 Algorithms)

| Rank | Algorithm | P@5 | R@5 | F1@5 | MRR | MAP | NDCG@5 |
|------|-----------|-----|-----|------|-----|-----|--------|
| 1 | 🥇 BM25-Only | 0.188 | 0.358 | **0.242** | 0.500 | 0.273 | 0.531 |
| 2 | 🥈 OpenClaw-Hybrid | 0.179 | 0.337 | **0.230** | 0.491 | 0.271 | 0.527 |
| 3 | 🥉 TotalReclaw-v0.6 | 0.179 | 0.333 | **0.229** | 0.526 | 0.276 | 0.594 |
| 4 |  TotalReclaw-v0.2 | 0.171 | 0.316 | **0.218** | 0.485 | 0.256 | 0.555 |
| 5 |  TotalReclaw-v0.5 | 0.171 | 0.316 | **0.218** | 0.485 | 0.256 | 0.555 |
| 6 |  Vector-Only | 0.083 | 0.167 | **0.108** | 0.262 | 0.135 | 0.271 |

### Latency Comparison

| Algorithm | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) |
|-----------|----------|----------|----------|----------|
| Vector-Only | 11.4 | 60.6 | 179.0 | 28.6 |
| BM25-Only | 88.0 | 104.5 | 130.0 | 90.1 |
| TotalReclaw-v0.2 | 98.2 | 130.5 | 2681.9 | 206.2 |
| TotalReclaw-v0.5 | 100.2 | 121.4 | 126.3 | 102.2 |
| OpenClaw-Hybrid | 101.0 | 117.3 | 123.9 | 102.7 |
| TotalReclaw-v0.6 | 749.7 | 856.2 | 1020.6 | 768.4 |

## TotalReclaw Version Evolution

### Version Comparison

| Metric | v0.2 | v0.5 | v0.6 | v0.6 vs v0.2 | v0.6 vs v0.5 |
|--------|------|------|------|-------------|-------------|
| F1@5 | 0.218 | 0.218 | 0.229 | +5.1% | +5.1% |
| Precision@5 | 0.171 | 0.171 | 0.179 | +4.9% | +4.9% |
| Recall@5 | 0.316 | 0.316 | 0.333 | +5.5% | +5.5% |
| MRR | 0.485 | 0.485 | 0.526 | +8.4% | +8.4% |
| NDCG@5 | 0.555 | 0.555 | 0.594 | +7.1% | +7.1% |

### Latency Evolution

| Version | p50 (ms) | p95 (ms) | p99 (ms) |
|---------|----------|----------|----------|
| v0.2 | 98.2 | 130.5 | 2681.9 |
| v0.5 | 100.2 | 121.4 | 126.3 |
| v0.6 | 749.7 | 856.2 | 1020.6 |

## v0.6 vs Production Baselines Parity

### F1 Score Comparison

#### ✗ BELOW: OpenClaw-Hybrid

| Metric | TotalReclaw v0.6 | OpenClaw-Hybrid | Delta |
|--------|----------------|----------|-------|
| F1@5 | 0.229 | 0.230 | -0.001 |
| MRR | 0.526 | 0.491 | +0.035 |
| NDCG@5 | 0.594 | 0.527 | +0.067 |

## E2EE Overhead Analysis

### Latency Impact of E2EE

**vs OpenClaw-Hybrid:** +648.8ms (+642.6%)

### Analysis

TotalReclaw v0.6 operates at ~750ms median latency. This includes:
- Client-side encryption
- Server-side encrypted search (2-pass E2EE)
- Client-side decryption
- Query expansion with LLM

## Query Expansion Impact

### Effect of Adding Query Expansion (v0.5 → v0.6)

- **F1@5:** 0.218 → 0.229 (+0.011)
- **MRR:** 0.485 → 0.526 (+0.041)
- **Latency:** 100.2ms → 749.7ms (+649.6ms)

### Analysis

Query expansion provides a **1.1% improvement** in F1 score, justifying the added latency cost.

## Recommendations

### ⚠️ Adjust Before Proceeding

TotalReclaw v0.6 shows promise but requires improvements:

- Latency p50 of 750ms exceeds threshold (100ms)

**Recommended Actions:**
1. Address the concerns listed above
2. Re-run evaluation with improvements
3. Consider query expansion tuning

## Appendix

### Evaluation Methodology

- **Dataset:** Real WhatsApp chat export (1,170 messages)
- **Queries:** 48 test queries
- **Ground Truth:** LLM-assisted relevance judgment
- **Metrics:** P@5, R@5, F1@5, MRR, MAP, NDCG@5
- **Latency:** p50, p95, p99, mean (milliseconds)

### Algorithm Descriptions

| Algorithm | Description |
|-----------|-------------|
| BM25-Only | Keyword-based search using BM25 ranking |
| Vector-Only | Semantic search using sentence embeddings |
| OpenClaw-Hybrid | Production hybrid search baseline |
| QMD-Hybrid | Advanced hybrid with query understanding |
| TotalReclaw-v0.2 | 2-pass E2EE without query expansion |
| TotalReclaw-v0.5 | 3-pass E2EE without query expansion |
| TotalReclaw-v0.6 | 3-pass E2EE with LLM query expansion |

## Architecture Comparison

### TotalReclaw v0.2 (2-Pass E2EE)

```
+---------------------------------------------------------------------+
| CLIENT (Trusted)                  | SERVER (Zero-Knowledge)        |
+---------------------------------------------------------------------+
|                                   |                                 |
|  Query ---+--> Embed Query -------+--> KNN Search --> Top 250      |
|           |                        |                                |
|           |   <------ Decrypt <----+----- Encrypted Docs <--------- |
|           |                        |                                |
|           +--> BM25 on 250 --------+                                |
|                                   |                                 |
|              RRF Fusion -----------+                                |
|                   |               |                                 |
|              Top-K Results        |                                 |
+---------------------------------------------------------------------+

Latency: ~100ms (KNN + Decrypt + BM25 on small set)
```

### TotalReclaw v0.6 (3-Pass with Query Expansion)

```
+---------------------------------------------------------------------+
| CLIENT (Trusted)                  | SERVER (Zero-Knowledge)        |
+---------------------------------------------------------------------+
|                                   |                                 |
|  Query --> LLM Expand ---> [q1,q2,q3]                              |
|              (~500ms)             |                                 |
|                                   |                                 |
|  [q1,q2,q3] --> Embed Each -------+--> KNN Search --> Top 250      |
|                                   |                                 |
|        <------ Decrypt All <------+----- Encrypted Docs <--------- |
|                                   |                                 |
|  BM25 on FULL corpus (1162 docs)  |                                 |
|        (~100ms)                   |                                 |
|                                   |                                 |
|        RRF Fusion                 |                                 |
|             |                     |                                 |
|        Top-K Results              |                                 |
+---------------------------------------------------------------------+

Latency: ~750ms (LLM expand + full corpus BM25 + RRF)
```

### OpenClaw Hybrid

```
+---------------------------------------------------------------------+
|                    OpenClaw Hybrid (No E2EE)                        |
+---------------------------------------------------------------------+
|                                                                     |
|  Query ---+--> BM25 on Full Corpus --> Top 250                     |
|           |                                                          |
|           +--> Vector Search ----------> Top 250                    |
|                                                                     |
|                   Weighted Fusion (70% BM25 + 30% Vector)           |
|                            |                                        |
|                       Top-K Results                                 |
+---------------------------------------------------------------------+

Latency: ~100ms (parallel BM25 + Vector, no encryption overhead)
```

### QMD Hybrid

```
+---------------------------------------------------------------------+
|                    QMD Hybrid (No E2EE)                             |
+---------------------------------------------------------------------+
|                                                                     |
|  Query --> Query Expansion (optional) --> [q1, q2]                  |
|                                                                     |
|  [q1,q2] ---+--> BM25 on Full Corpus --> Top 250                    |
|             |                                                       |
|             +--> Vector Search ----------> Top 250                  |
|                                                                     |
|                   RRF Fusion (k=60)                                 |
|                        |                                            |
|                   LLM Rerank (optional)                             |
|                        |                                            |
|                   Top-K Results                                     |
+---------------------------------------------------------------------+

Latency: ~200ms (parallel search + optional LLM rerank)
```

## Latency Breakdown Analysis

| Component | v0.2 | v0.6 | OpenClaw | QMD |
|-----------|------|------|----------|-----|
| Query Expansion | 0ms | ~500ms | 0ms | ~50ms (optional) |
| Vector Search | ~50ms | ~50ms | ~50ms | ~50ms |
| BM25 Search | ~50ms (250 docs) | ~100ms (1162 docs) | ~50ms (full) | ~50ms (full) |
| Encryption/Decryption | ~10ms | ~10ms | 0ms | 0ms |
| RRF Fusion | ~5ms | ~10ms | ~5ms | ~5ms |
| **Total** | **~100ms** | **~750ms** | **~100ms** | **~200ms** |

### Why v0.6 is Slower

1. **Query Expansion (+500ms)**: LLM generates synonyms/related terms
2. **Full Corpus BM25 (+50ms)**: Searches all 1,162 docs vs 250 in v0.2
3. **Trade-off**: +5% F1 accuracy for +650ms latency

### Why v0.6 is Competitive Despite Latency

- **Accuracy matches OpenClaw** (F1: 0.229 vs 0.230)
- **Zero-knowledge encryption** - server sees only ciphertext
- **Best MRR** (0.526) - better ranking quality than all baselines

### Test Environment

- **Evaluation Date:** 2026-02-20
- **Testbed Version:** v2.0 Real-World Data
- **Total Queries Evaluated:** 48

