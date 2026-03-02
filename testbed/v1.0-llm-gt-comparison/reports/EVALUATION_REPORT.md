# TotalReclaw v1.0 Testbed Evaluation Report

**Generated:** 2026-02-19 22:05:13

**Testbed Version:** v1.0 LLM-Ground-Truth Comparison

---

## Executive Summary

### ⚠️ Decision: MODIFY

#### Key Metrics

| Metric | Baseline (BM25-Only) | TotalReclaw | Gap |
|--------|------------------------------|------------|-----|
| F1@5 | 0.238 | 0.056 | -18.2% |
| Precision@5 | 0.607 | 0.129 | -47.8% |
| Recall@5 | 0.159 | 0.039 | -12.0% |
| MRR | 0.656 | 0.158 | -49.7% |
| Latency p50 (ms) | 25 | 6945 | 27595% |

#### Decision Rationale

**Decision: MODIFY**

## Summary

- TotalReclaw F1: 0.056 (baseline: 0.238, gap: 18.2%)
- TotalReclaw MRR: 0.158, Recall: 0.039
- Latency p50: 6945ms
- OpenClaw compatibility: MET
- Ground truth quality: poor (consider re-labeling)

## Passed Criteria

- ✓ OpenClaw compatibility met (import F1: 0.920, round-trip F1: 0.960)

## Warnings

- ⚠ Latency p50 (6945ms) exceeds target

## Failed Criteria

- ✗ F1 score (0.056) below 0.75
- ✗ F1 gap to baseline (18.2%) exceeds 15%
- ✗ MRR (0.158) below 0.65

## Recommendation

TotalReclaw shows promise but requires targeted improvements before proceeding. Address the failed criteria and warnings above, then re-run the testbed evaluation.

## Algorithm Comparison

### Accuracy Metrics

| Scenario | Algorithm | P@5 | R@5 | F1@5 | MRR | MAP | NDCG@5 |
|----------|-----------|-----|-----|------|-----|-----|-------|
| S1 | BM25-Only | 0.607 | 0.159 | 0.238 | 0.656 | 0.141 | 0.702 |
| S2 | Vector-Only | 0.273 | 0.085 | 0.120 | 0.398 | 0.065 | 0.469 |
| S3 | OpenClaw-Hybrid | 0.476 | 0.146 | 0.209 | 0.721 | 0.123 | 0.750 |
| S4 | QMD-Hybrid | 0.436 | 0.125 | 0.180 | 0.569 | 0.087 | 0.673 |
| S5 | TotalReclaw v0.2 E2EE | 0.112 | 0.037 | 0.052 | 0.158 | 0.029 | 0.184 |
| S6 | TotalReclaw v0.5 E2EE (no LLM) | 0.112 | 0.037 | 0.052 | 0.158 | 0.029 | 0.184 |
| S7 | TotalReclaw v0.5 E2EE (with LLM) | 0.129 | 0.039 | 0.056 | 0.158 | 0.034 | 0.176 |

### Latency Comparison

| Scenario | Algorithm | p50 (ms) | p95 (ms) | p99 (ms) |
|----------|-----------|----------|----------|----------|
| S1 | BM25-Only | 25.1 | 27.0 | 32.4 |
| S2 | Vector-Only | 7.3 | 31.9 | 77.4 |
| S3 | OpenClaw-Hybrid | 33.4 | 40.8 | 57.5 |
| S4 | QMD-Hybrid | 71.2 | 108.2 | 116.8 |
| S5 | TotalReclaw v0.2 E2EE | 7.1 | 10.6 | 46.1 |
| S6 | TotalReclaw v0.5 E2EE (no LLM) | 7.2 | 10.8 | 26.9 |
| S7 | TotalReclaw v0.5 E2EE (with LLM) | 6944.8 | 10417.2 | 31751.5 |

### F1 Score Leaderboard

1. 🥇 **BM25-Only** (S1): F1=0.238
2. 🥈 **OpenClaw-Hybrid** (S3): F1=0.209
3. 🥉 **QMD-Hybrid** (S4): F1=0.180
4.  **Vector-Only** (S2): F1=0.120
5.  **TotalReclaw v0.5 E2EE (with LLM)** (S7): F1=0.056
6.  **TotalReclaw v0.2 E2EE** (S5): F1=0.052
7.  **TotalReclaw v0.5 E2EE (no LLM)** (S6): F1=0.052

## E2EE Timing Breakdown Analysis

### Per-Pass Timing Breakdown

| Version | Encryption (ms) | Network/Pass1 (ms) | Decryption (ms) | BM25 (ms) | RRF (ms) | LLM Rerank (ms) | Total (ms) |
|---------|-----------------|-------------------|-----------------|-----------|----------|-----------------|-----------|
| TotalReclaw v0.2 | 0.00 | 0.57 | 0.42 | 0.71 | 0.35 | 0.00 | 8.05 |
| TotalReclaw v0.5 (base) | 0.00 | 0.59 | 0.45 | 0.72 | 0.36 | 0.00 | 8.24 |
| TotalReclaw v0.5 (LLM) | 0.00 | 0.98 | 0.60 | 694.48 | 347.24 | 6937.08 | 6946.39 |

### E2EE Overhead Analysis

**Average baseline latency:** 34.2ms

- **TotalReclaw v0.2:** -27.2ms (-79.4% vs baseline)
- **TotalReclaw v0.5 (base):** -27.0ms (-79.0% vs baseline)
- **TotalReclaw v0.5 (LLM):** +6910.6ms (+20188.0% vs baseline)

## LLM Rerank Bottleneck Analysis

### Latency by Candidate Count

| Candidates | Queries | Avg (ms) | p50 (ms) | p95 (ms) | p99 (ms) | Input Tokens | Output Tokens |
|------------|---------|----------|----------|----------|----------|--------------|---------------|
| 10 | 19 | 5489 | 3124 | 27226 | 27226 | 450 | 40 |
| 20 | 20 | 7367 | 4211 | 38556 | 38556 | 768 | 113 |
| 30 | 20 | 6043 | 6337 | 11192 | 11192 | 1118 | 144 |
| 50 | 20 | 7995 | 7631 | 19616 | 19616 | 1829 | 236 |

### Scaling Analysis

**⚠️ BOTTLENECK IDENTIFIED**

#### Scaling Factors

| From | To | Count Ratio | Latency Ratio | Type |
|------|-----|-------------|---------------|------|
| 10 | 20 | 2.0x | 1.3x | non-linear |
| 10 | 30 | 3.0x | 1.1x | non-linear |
| 10 | 50 | 5.0x | 1.5x | non-linear |

### Recommendation

LLM reranking is a significant bottleneck at high candidate counts. Consider: (1) Limiting reranking to top-20 candidates, (2) Using a faster model, or (3) Implementing cache for frequent queries.

## Recommendations

### ⚠️ Adjust Architecture Before Proceeding

TotalReclaw shows promise but requires targeted improvements before proceeding to MVP development.

**Required Actions:**
- Address: Latency p50 (6945ms) exceeds target
- Fix: F1 score (0.056) below 0.75
- Fix: F1 gap to baseline (18.2%) exceeds 15%
- Fix: MRR (0.158) below 0.65

**Recommended Next Steps:**
1. Address the failed criteria listed above
2. Re-run the testbed evaluation
3. Consider architecture adjustments if accuracy gap persists

### Performance Recommendations

**High Latency Warning:**

- TotalReclaw v0.5 E2EE (with LLM): 6945ms average latency

Consider optimizing or caching for production use.

**LLM Reranking Bottleneck:**

The LLM reranking step introduces significant latency at higher candidate counts. Consider:
1. Limiting reranking to top-20 candidates
2. Using a faster model or local embedding-based reranking
3. Implementing result caching for frequent queries

## Appendix

### Methodology

#### Evaluation Metrics

- **Precision@5:** |Relevant Retrieved| / |All Retrieved| (top 5)
- **Recall@5:** |Relevant Retrieved| / |All Relevant| (top 5)
- **F1@5:** Harmonic mean of Precision@5 and Recall@5
- **MRR:** Mean Reciprocal Rank (1/rank of first relevant result)
- **MAP:** Mean Average Precision across all queries
- **NDCG@5:** Normalized Discounted Cumulative Gain at rank 5

#### Go/No-Go Criteria

**GO (Proceed to Development):**
- F1 >= 0.80 OR F1 Gap <= 5% OR (MRR >= 0.70 AND Recall >= 0.75)

**MODIFY (Adjust Architecture):**
- 0.75 <= F1 < 0.80 OR F1 Gap <= 10% OR 0.65 <= MRR < 0.70

**NO-GO (Reconsider Architecture):**
- F1 < 0.75 OR F1 Gap > 15% OR MRR < 0.65

### Test Scenarios

| ID | Algorithm | Description |
|----|-----------|-------------|
| S1 | BM25-Only | Keyword baseline |
| S2 | Vector-Only | Semantic baseline |
| S3 | OpenClaw Hybrid | Production hybrid baseline |
| S4 | QMD Hybrid | Advanced hybrid baseline |
| S5 | TotalReclaw v0.2 E2EE | Zero-knowledge 2-pass |
| S6 | TotalReclaw v0.5 E2EE (no LLM) | 3-pass without LLM |
| S7 | TotalReclaw v0.5 E2EE (with LLM) | Full 3-pass with LLM |
| S8 | LLM Rerank Isolation | Compute bottleneck test |

### Ground Truth

- **Source:** LLM-based relevance judgment using OpenRouter
- **Model:** arcee-ai/trinity-large-preview:free
- **Queries:** 150 test queries across multiple categories
- **Dataset:** 1,500 memory chunks

