# TotalReclaw v2 Improvement Benchmark Comparison

**Generated**: 2026-02-28 12:11
**Changes Tested**: LSH 12-bit x 28 tables (was 64-bit x 12), stemmed blind indices, 1200 candidate pool (was 400)
**Dataset**: 50 synthetic conversations, 140 test queries (42 factual, 42 semantic, 42 cross-conversation, 14 negative)
**Scorer**: Keyword overlap (40% threshold)
**LLM**: glm-4.5-air (Z.AI)

---

## Overall Comparison

| Metric | Old v2 | Improved v2 | Delta | Direction |
|--------|--------|-------------|-------|-----------|
| Overall Recall | 28.7% | 27.7% | -1.1% | Regression |
| Non-Negative Recall | 20.8% | 19.6% | -1.2% | Regression |
| Factual Recall | 27.3% | 32.8% | **+5.6%** | **Improved** |
| Semantic Recall | 16.4% | 13.1% | -3.4% | Regression |
| Cross-Conv Recall | 18.7% | 13.0% | -5.7% | Regression |
| Negative Recall | 100.0% | 100.0% | 0.0% | Same |

## Fact Recovery Details

| Category | Old Hits/Total | New Hits/Total | Delta |
|----------|---------------|----------------|-------|
| Factual | 37/142 | 44/142 | **+7 hits** |
| Semantic | 21/133 | 14/133 | -7 hits |
| Cross-Conv | 39/208 | 26/208 | -13 hits |
| **Total** | **97/483** | **84/483** | **-13 hits** |

## Latency Comparison

| Metric | Old v2 | Improved v2 | Delta |
|--------|--------|-------------|-------|
| p50 (ms) | 21,004 | 19,298 | **-1,705 (8.1% faster)** |
| p95 (ms) | 56,673 | 51,330 | **-5,344 (9.4% faster)** |
| p99 (ms) | 57,685 | 57,007 | -678 (1.2% faster) |

## Reliability

| Metric | Old v2 | Improved v2 | Delta |
|--------|--------|-------------|-------|
| Successful Queries | 133/140 | 136/140 | **+3** |
| Failed Queries | 7 | 4 | **-3** |
| Ingest Success | 50/50 | 50/50 | Same |
| Avg Ingest Latency | 50.6s | 11.2s | **-39.4s (78% faster)** |

## Ranking vs 5-Way Benchmark (with improved v2 replacing old v2)

| Rank | System | Overall Recall |
|------|--------|---------------|
| 1 | LanceDB (Vector DB) | 31.3% |
| 2 | QMD (memory-core) | 28.2% |
| 3 | **Improved TotalReclaw v2** | **27.7%** |
| 4 | Mem0 Cloud | 23.8% |
| 5 | TotalReclaw v1 (Facts-Only) | 21.6% |

> Note: Old TotalReclaw v2 was ranked #2 at 28.7%. The improved version drops to #3, behind QMD.

---

## Analysis

### What Improved

1. **Factual recall gained 5.6 percentage points** (27.3% -> 32.8%), recovering 7 additional facts. Stemmed blind indices likely help match exact fact lookups where word forms vary (e.g., "running" -> "run").

2. **Latency improved across the board** -- p50 dropped 8.1%, p95 dropped 9.4%. The 12-bit LSH with 28 tables produces more targeted bucket matches, reducing the candidate set the server needs to scan despite the larger 1200 pool.

3. **Ingest was dramatically faster** (11.2s vs 50.6s avg per conversation, 78% reduction). This is likely due to the faster LSH hashing with shorter 12-bit signatures.

4. **Reliability improved** -- 3 fewer query failures (4 vs 7).

### What Regressed

1. **Semantic recall dropped 3.4 percentage points** (16.4% -> 13.1%), losing 7 fact hits. Shorter 12-bit LSH signatures may be too coarse for semantic similarity matching -- they capture broader buckets but lose the fine-grained discrimination that 64-bit signatures provided.

2. **Cross-conversation recall dropped 5.7 percentage points** (18.7% -> 13.0%), losing 13 fact hits. This is the largest regression and suggests the combination of stemming + shorter LSH signatures is hurting the ability to connect related facts across different conversations.

3. **Overall non-negative recall dropped 1.2 percentage points** (20.8% -> 19.6%). Despite factual gains, the semantic and cross-conv losses more than offset them.

### Root Cause Hypothesis

The 12-bit x 28 tables LSH configuration generates **broader but less discriminating buckets** compared to 64-bit x 12 tables. For factual queries (which tend to match on exact or near-exact terms), stemming helps. But for semantic and cross-conversation queries (which rely on embedding similarity to find paraphrased or related content), the shorter hash signatures lose too much information.

The 1200 candidate pool (up from 400) may not help if the broader buckets are returning less relevant candidates -- more candidates does not help if they are lower quality.

### Recommendations

1. **Keep stemmed blind indices** -- they clearly help factual recall (+5.6%).

2. **Revert LSH to 64-bit x 12 tables** (or try a middle ground like 32-bit x 20 tables) -- the shorter signatures hurt semantic/cross-conv retrieval.

3. **Keep the 1200 candidate pool** -- this provides headroom for the reranker once LSH quality is restored.

4. **Consider a hybrid approach**: use stemmed word indices for factual matching AND the original 64-bit LSH for embedding-based matching.

5. **Test incrementally** -- change one variable at a time to isolate which change caused the semantic/cross-conv regression.

---

## Raw Data References

- Old baseline metrics: `benchmark-metrics-5way.json`
- New improved metrics: `benchmark-metrics.json`
- Old query results: `query-results-4way.json`
- New query results: `query-results.json`
- Ingest results: `ingest-results.json`
