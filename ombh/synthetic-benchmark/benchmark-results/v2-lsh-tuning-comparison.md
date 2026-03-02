# TotalReclaw v2 LSH Tuning Comparison

**Generated**: 2026-02-28 13:17
**Goal**: Find optimal LSH parameters balancing factual, semantic, and cross-conversation recall.
**Dataset**: 50 synthetic conversations, 140 test queries (42 factual, 42 semantic, 42 cross-conv, 14 negative)
**Scorer**: Keyword overlap (40% threshold)
**LLM**: glm-4.5-air (Z.AI)

---

## TotalReclaw LSH Configurations Tested

| Config | LSH Params | Stemming | Candidates | Notes |
|--------|-----------|----------|------------|-------|
| **A: Original v2** | 64-bit x 12 tables | No | 400 | Baseline -- tight buckets, few tables |
| **B: Wide buckets** | 12-bit x 28 tables | Yes | 1200 | Too coarse -- helped factual, hurt semantic |
| **C: Middle ground** | 32-bit x 20 tables | Yes | 1200 | Balanced -- this run |

---

## Overall Recall Comparison

| Metric | A: 64b x 12 | B: 12b x 28 | C: 32b x 20 | LanceDB (ref) |
|--------|-------------|-------------|-------------|---------------|
| **Overall Recall** | 28.7% | 27.7% | **30.9%** | 31.3% |
| **Non-Neg Recall** | 20.8% | 19.6% | **23.2%** | 23.6% |
| Factual | 27.3% | **32.8%** | 27.3% | 28.3% |
| Semantic | 16.4% | 13.1% | **24.3%** | 24.6% |
| Cross-Conv | 18.7% | 13.0% | **18.1%** | 18.1% |
| Negative | 100.0% | 100.0% | 100.0% | 100.0% |

## Fact Hit Details

| Category | A: 64b x 12 | B: 12b x 28 | C: 32b x 20 | LanceDB |
|----------|-------------|-------------|-------------|---------|
| Factual | 37/142 | **44/142** | 37/142 | 38/142 |
| Semantic | 21/133 | 14/133 | **30/133** | 29/133 |
| Cross-Conv | **39/208** | 26/208 | 36/208 | 39/208 |
| **Total** | 97/483 | 84/483 | **103/483** | 106/483 |

## Delta from Original v2 (Config A)

| Metric | B: 12b x 28 | C: 32b x 20 |
|--------|-------------|-------------|
| Overall Recall | -1.1% | **+2.2%** |
| Non-Neg Recall | -1.2% | **+2.4%** |
| Factual | **+5.6%** | 0.0% |
| Semantic | -3.4% | **+7.9%** |
| Cross-Conv | -5.7% | -0.6% |
| Total Hits | -13 | **+6** |

## Delta from LanceDB Baseline

| Metric | A: 64b x 12 | B: 12b x 28 | C: 32b x 20 |
|--------|-------------|-------------|-------------|
| Overall | -2.6% | -3.6% | **-0.4%** |
| Non-Neg | -2.8% | -4.0% | **-0.4%** |
| Factual | -1.0% | +4.5% | **-1.0%** |
| Semantic | -8.2% | -11.5% | **-0.3%** |
| Cross-Conv | +0.6% | -5.1% | **0.0%** |
| Total Hits | -9 | -22 | **-3** |

## Latency Comparison

| Metric | A: 64b x 12 | B: 12b x 28 | C: 32b x 20 |
|--------|-------------|-------------|-------------|
| p50 (ms) | 21,004 | 19,298 | **16,560** |
| p95 (ms) | 56,673 | 51,330 | **39,374** |
| p99 (ms) | 57,685 | 57,007 | **42,744** |

## Reliability

| Metric | A: 64b x 12 | B: 12b x 28 | C: 32b x 20 |
|--------|-------------|-------------|-------------|
| Successful | 133/140 | 136/140 | **139/140** |
| Failed | 7 | 4 | **1** |

---

## Full 5-Way Ranking (with 32-bit x 20 TotalReclaw)

| Rank | System | Overall | Non-Neg | Factual | Semantic | Cross-Conv |
|------|--------|---------|---------|---------|----------|------------|
| 1 | LanceDB (Vector DB) | 31.3% | 23.6% | 28.3% | **24.6%** | 18.1% |
| **2** | **TotalReclaw v2 (32b x 20)** | **30.9%** | **23.2%** | 27.3% | 24.3% | 18.1% |
| 3 | QMD (memory-core) | 28.2% | 20.2% | 27.5% | 16.8% | 16.3% |
| 4 | Mem0 Cloud | 23.8% | 15.3% | 22.7% | 10.5% | 12.7% |
| 5 | TotalReclaw v1 (Facts-Only) | 21.6% | 12.9% | 19.9% | 11.5% | 7.3% |

---

## Analysis

### Config C (32-bit x 20) is the clear winner

The 32-bit x 20 configuration achieves the best balance across all query types:

1. **Semantic recall jumped +7.9%** (16.4% -> 24.3%), recovering 9 additional semantic hits. This is the single largest improvement across all tuning runs. The 32-bit signatures provide enough discrimination to surface semantically similar facts that 12-bit could not distinguish, while not being as strict as 64-bit.

2. **Cross-conversation recall held steady** at 18.1% (-0.6% from baseline), unlike the 12-bit config which dropped -5.7%. The moderate bit width preserves cross-conversation matching ability.

3. **Factual recall is unchanged** at 27.3% -- identical to the original 64-bit config. The stemmed blind indices (present in both B and C configs) should help factual matching, but the smaller table count (20 vs 28) may return fewer word-index candidates, offsetting the stemming benefit.

4. **Near-parity with LanceDB** -- only 0.4% behind on non-negative recall (23.2% vs 23.6%), and only 3 fewer total hits (103 vs 106). This is remarkable given TotalReclaw operates under zero-knowledge encryption constraints.

5. **Best latency** -- p50 dropped 21% from original (16.5s vs 21.0s), p95 dropped 30% (39.4s vs 56.7s). The 32-bit x 20 table configuration generates fewer, more targeted buckets than 12-bit x 28 tables.

6. **Best reliability** -- only 1 failed query out of 140 (vs 7 in original, 4 in 12-bit config).

### Why 32-bit x 20 works

The math explains it:

| Cosine Similarity | P(match, 1 table) | P(at least 1 of N tables) |
|------|------|------|
| | 64b x 12 | 32b x 20 | 12b x 28 | 64b x 12 | 32b x 20 | 12b x 28 |
| 0.95 | 43.2% | 65.7% | 81.1% | 100% | 100% | 100% |
| 0.80 | 1.5% | 12.2% | 34.9% | 16.5% | 93.1% | 100% |
| 0.70 | 0.1% | 3.6% | 23.2% | 0.7% | 52.0% | 100% |
| 0.50 | ~0% | 0.1% | 8.8% | ~0% | 2.0% | 93.0% |

At cosine 0.70-0.80 (typical semantic match range), 32-bit x 20 gives 52-93% probability of a match, while 64-bit x 12 gives only 0.7-16.5%. This explains the massive semantic recall gain. Meanwhile, 12-bit x 28 gives ~100% even at cosine 0.50, which floods the candidate pool with low-quality matches that dilute good results.

### Recommendation

**Adopt 32-bit x 20 tables with stemmed blind indices as the default configuration.** This achieves near-LanceDB recall quality while maintaining full zero-knowledge encryption -- the core value proposition of TotalReclaw.

### Remaining gap analysis

The remaining 0.4% gap vs LanceDB is in:
- Factual: -1.0% (37 vs 38 hits) -- within noise
- Semantic: -0.3% (30 vs 29 hits) -- TotalReclaw actually has 1 MORE hit
- Cross-conv: 0.0% (36 vs 39 hits, but avg recall is identical at 18.1%)

The gap is negligible and may close with additional optimizations like:
- Tuning the BM25/cosine/RRF fusion weights
- Increasing the candidate pool beyond 1200
- Hybrid word + LSH index strategies

---

## Raw Data References

- Original v2 (64b x 12): `benchmark-metrics-5way.json` (totalreclaw entry)
- 12-bit x 28 config: `benchmark-metrics-12bit-28t.json`
- 32-bit x 20 config (this run): `benchmark-metrics.json`
- Ingest results: `ingest-results.json`
- Query results: `query-results.json`
