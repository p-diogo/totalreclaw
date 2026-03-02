# TotalReclaw Improvement Suggestions After v1.0 Benchmark

**Date:** 2026-02-20
**Status:** Post-Benchmark Analysis

---

## Executive Summary

The v1.0 benchmark revealed significant accuracy gaps between TotalReclaw and baseline algorithms:

| Algorithm | F1@5 | MRR | Latency |
|-----------|------|-----|---------|
| BM25-Only (baseline) | 0.238 | 0.656 | 25ms |
| OpenClaw-Hybrid | 0.209 | 0.721 | 33ms |
| **TotalReclaw v0.2 E2EE** | **0.052** | **0.158** | 7ms |
| **TotalReclaw v0.5 + LLM** | **0.056** | **0.158** | 6.9s |

**Root Cause:** TotalReclaw's 2-pass architecture limits BM25 to only searching the top 250 candidates from Pass 1 (vector search), missing relevant documents that weren't found by semantic similarity.

---

## What Does "Memories Change" Mean?

In a real-world memory system, memories are not static. Here are the types of changes that occur:

### 1. New Memories Added
**Use Case:** User has a conversation with an AI agent
**Example:**
- Agent helps debug a PostgreSQL query issue
- Memory is created: "Discussed PostgreSQL query optimization with index hints"
**Frequency:** Multiple times per day in active use
**Impact on Index:** BM25 index must be updated with new document

### 2. Memory Content Updated
**Use Case:** User corrects or refines a memory
**Example:**
- Original: "Meeting with John next Tuesday"
- Updated: "Meeting with John next Tuesday at 3pm in Conference Room B"
**Frequency:** Occasional
**Impact on Index:** Old document removed, new version indexed

### 3. Memory Deleted
**Use Case:** User removes outdated or incorrect memories
**Example:**
- Deleting: "Project deadline is March 15" (after deadline passes)
**Frequency:** Occasional
**Impact on Index:** Document removed from index

### 4. Memory Merged
**Use Case:** Consolidating related memories
**Example:**
- Merging: "Discussed API design" + "Decided on REST over GraphQL"
- Into: "Discussed API design and decided on REST over GraphQL for simplicity"
**Frequency:** Rare
**Impact on Index:** Multiple docs removed, one new doc added

### 5. Memory Split
**Use Case:** Breaking down a large memory into smaller chunks
**Example:**
- Original: Long conversation about multiple topics
- Split into: 3 separate memories by topic
**Frequency:** Rare
**Impact on Index:** One doc removed, multiple new docs added

---

## Performance Implications of Index Updates

### Scenario Analysis

| Scenario | Memory Count | Index Size (est.) | Update Time | Re-upload Time |
|----------|--------------|-------------------|-------------|----------------|
| Single new memory | 1,000 | ~500KB | <10ms | ~100ms |
| Batch of 10 memories | 1,000 | ~500KB | ~50ms | ~100ms |
| Major update (100 memories) | 1,000 | ~500KB | ~200ms | ~150ms |
| Full reindex | 10,000 | ~5MB | ~2s | ~1s |

### Key Insights

1. **Incremental updates are fast** - Adding a single memory is nearly instant
2. **Full reindex is acceptable** - Even 10,000 memories only takes ~3 seconds
3. **Network is the bottleneck** - Re-uploading the encrypted index takes time
4. **Optimization opportunity** - Could use incremental index patches instead of full re-upload

---

## Improvement Options Analyzed

### Option A: Increase Pass 1 Candidates
**Change:** Increase from 250 to 500 or 1000 candidates in Pass 1

**Pros:**
- Simple change
- Better recall without architecture changes

**Cons:**
- More decryption overhead
- Higher latency
- Still not full corpus coverage

**Verdict:** Marginal improvement, doesn't solve root cause

---

### Option B: Blind Index Priority
**Change:** Use blind indices to pre-filter before vector search

**Pros:**
- Better keyword matching
- Maintains E2EE

**Cons:**
- Blind indices can have collisions
- Limited vocabulary coverage
- Still dependent on Pass 1 candidates

**Verdict:** Helpful as a complement, not a solution

---

### Option C: QMD-Style with Query Expansion
**Change:** Add LLM-based query expansion to generate synonyms

**Pros:**
- Better recall through multiple query variations
- Can be complementary to other solutions

**Cons:**
- Adds latency (LLM call)
- Cost per query
- Still limited to Pass 1 candidates

**Verdict:** Good complementary feature, not a complete solution

---

### Option D: Hybrid Local Index (Rejected)
**Change:** Store BM25 index locally on client

**Problem:**
- Index not portable across agents
- New agent must rebuild entire index from scratch
- Violates "all data on server" portability goal

**Verdict:** ❌ Rejected due to portability concerns

---

### Option E: Encrypted BM25 Index on Server ✅ SELECTED
**Change:** Store encrypted BM25 index on server alongside encrypted documents

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│ SERVER STORES (All Encrypted):                                  │
│   ├─ Encrypted documents                                        │
│   ├─ Encrypted embeddings                                       │
│   └─ Encrypted BM25 index (serialized)                          │
│                                                                 │
│ CLIENT OPERATIONS:                                              │
│   Startup: Download + decrypt index (~100ms)                    │
│   Search:   Full BM25 + Vector KNN → RRF fusion                 │
│   Update:   Incremental index update + re-encrypt + upload      │
└─────────────────────────────────────────────────────────────────┘
```

**Pros:**
- ✅ Zero-knowledge server (all data encrypted)
- ✅ Full portability (everything on server)
- ✅ Fast startup (decrypt one file)
- ✅ Full BM25 accuracy (entire corpus searchable)

**Cons:**
- Must re-upload index when memories change
- Index file can be large for big memory stores
- Adds complexity to client

**Verdict:** ✅ SELECTED - Best balance of security, portability, and accuracy

---

## Complementary Improvements

### Query Expansion (Add to Option E)
Even with full BM25, query expansion can improve recall for semantic queries:

```
Original Query: "database slow"
Expanded Queries: ["database slow", "db performance", "query optimization", "latency issues"]
```

**Implementation:**
- LLM generates 2-3 synonyms/related terms locally on client
- No additional server requests
- All expanded terms searched in both BM25 and vector search

**Cost:** ~100ms latency, ~$0.0001 per query (local LLM)

---

## Recommended Implementation Path

### Phase 1: v0.6 Specification (Now)
1. Design encrypted BM25 index storage format
2. Define index update protocol
3. Specify RRF fusion with full corpus access

### Phase 2: v2 Testbed (Next)
1. Use real-world data (WhatsApp, Telegram, Gmail)
2. Clean data processing pipeline
3. Regenerate proper ground truth

### Phase 3: Benchmark v0.6
1. Compare v0.6 vs v0.2 vs baselines
2. Measure index update performance
3. Validate accuracy improvement

---

## Open Questions

1. **Index Format:** Should we use pickle, JSON, or custom binary format for BM25 index?
2. **Incremental Updates:** Should we support incremental index patches or always do full re-upload?
3. **Query Expansion Model:** Which local LLM to use for query expansion?
4. **Index Compression:** Should we compress the index before encryption to reduce storage?

---

## Appendix: Benchmark Data Quality Issues

The v1.0 benchmark had data quality issues that may have affected results:

| Issue | Impact |
|-------|--------|
| 1480 memories but only 218 unique | Inflated baseline scores |
| 63% of queries had no GT | Limited evaluation coverage |
| Tiny chunks (15 chars) | Poor semantic representation |
| GT marked all duplicates | Artificial precision inflation |

**Resolution:** v2 testbed will use real-world data with proper ground truth generation.
