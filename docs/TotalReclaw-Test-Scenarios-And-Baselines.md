# TotalReclaw Test Scenarios & Baselines

**Version:** 1.0.0
**Status:** Draft
**Last Updated:** February 18, 2026

**Purpose:** Define the search algorithm variants to be tested in the accuracy validation testbed.

---

## Overview

We will test **6 search algorithms** against **4 query categories** to determine if TotalReclaw's zero-knowledge E2EE approach can achieve competitive accuracy while maintaining privacy.

---

## Part 1: Search Algorithm Variants

### Baseline 1: BM25-Only (Keyword Search)

**Description:** Pure keyword-based search using BM25 algorithm. No semantic understanding.

**Algorithm:**
```
1. Tokenize query and documents
2. Calculate BM25 scores
3. Return top-k results by score
```

**Strengths:**
- Excellent for exact matches (emails, IDs, error codes)
- Fast (<50ms)
- No embedding model required

**Weaknesses:**
- Fails on semantic queries ("container orchestration" won't find "Docker")
- Fails on paraphrases
- No understanding of context

**Expected Use Case:** Baseline for keyword-only performance

---

### Baseline 2: Vector-Only (Semantic Search)

**Description:** Pure semantic search using vector embeddings. No keyword matching.

**Algorithm:**
```
1. Encode query using all-MiniLM-L6-v2
2. Calculate cosine similarity with document embeddings
3. Return top-k results by similarity
```

**Strengths:**
- Excellent for semantic queries
- Finds paraphrases and concepts
- Good for natural language queries

**Weaknesses:**
- Poor for exact matches (IDs, error codes, specific strings)
- Misses high-value exact tokens
- Higher latency (~100-200ms)

**Expected Use Case:** Baseline for semantic-only performance

---

### Baseline 3: OpenClaw Hybrid (Current Default)

**Description:** Weighted merge of vector and BM25 scores. Replicates OpenClaw's default search from official docs.

**Algorithm (from OpenClaw documentation):**
```
1. Vector search: top (maxResults × candidateMultiplier) by cosine similarity
2. BM25 search: top (maxResults × candidateMultiplier) by FTS5 BM25 rank
3. Convert BM25 rank to score: textScore = 1 / (1 + max(0, bm25Rank))
4. Merge: finalScore = vectorWeight × vectorScore + textWeight × textScore
5. Optional: MMR re-ranking (diversity)
6. Optional: Temporal decay (recency boost)
7. Return top-k results by finalScore

Defaults (from OpenClaw docs):
- vectorWeight = 0.7
- textWeight = 0.3
- candidateMultiplier = 4
- Chunk size: ~400 tokens with 80-token overlap
- MMR: off by default (lambda = 0.7 when enabled)
- Temporal decay: off by default (halfLife = 30 days when enabled)

Storage: ~/.openclaw/memory/<agentId>.sqlite (per-agent SQLite)
```

**Post-Processing Pipeline (from OpenClaw docs):**
```
Vector + Keyword → Weighted Merge → Temporal Decay → Sort → MMR → Top-K Results
```

**Optional Features (from OpenClaw docs):**
- **MMR re-ranking**: Balances relevance with diversity to avoid redundant results
- **Temporal decay**: Recent memories rank higher (exponential decay, half-life 30 days)

**Strengths:**
- Balanced performance on semantic and keyword queries
- Proven in production (OpenClaw default since 2025)
- Optional MMR prevents redundant results from daily notes
- Optional temporal decay prioritizes recent context
- Hybrid search is why OpenClaw adopted this (better than vector-only)

**Weaknesses:**
- No query expansion (unlike QMD)
- No LLM reranking (unlike QMD)
- Works on plaintext (not encrypted)

**Expected Use Case:** Current state-of-the-art for plaintext search (OpenClaw default)

---

### Baseline 4: QMD-Style Hybrid (With LLM Reranking)

**Description:** BM25 + vector + query expansion + RRF fusion + LLM reranking. Replicates QMD's `query` mode.

**Algorithm (from QMD GitHub README):**
```
1. Query Expansion: LLM generates 1 variant query
2. Parallel Retrieval: Original (×2 weight) + variant search both FTS and vector
3. RRF Fusion: score = Σ(1/(k+rank+1)) where k=60
4. Top-Rank Bonus: #1 gets +0.05, #2-3 get +0.02
5. Top 30 candidates → LLM reranking (yes/no with logprobs)
6. Position-Aware Blending:
   - Rank 1-3:  75% RRF / 25% reranker
   - Rank 4-10: 60% RRF / 40% reranker
   - Rank 11+:  40% RRF / 60% reranker

Models (via node-llama-cpp, local GGUF):
- Embedding: embeddinggemma-300M-Q8_0 (~300MB)
- Reranker: qwen3-reranker-0.6b-q8_0 (~640MB)
- Query Expansion: qmd-query-expansion-1.7B-q4_k_m (~1.1GB)
```

**Why QMD is State-of-the-Art:**
- Query expansion catches semantic variants that might be missed
- RRF with top-rank bonus preserves exact matches
- Position-aware blending prevents reranker from destroying high-confidence retrieval results
- All models run locally via node-llama-cpp

**Strengths:**
- Best accuracy among plaintext approaches (per QMD author and community)
- Query expansion catches results that pure vector/BM25 miss
- Local-only (no API keys needed)
- Smart chunking: ~900 tokens with natural break point detection

**Weaknesses:**
- Highest latency (query expansion + reranking adds ~500-1000ms)
- Most complex architecture
- Requires ~2GB disk space for GGUF models
- Works on plaintext (not encrypted)

**Expected Use Case:** State-of-the-art for plaintext local search (QMD has 9.1k GitHub stars)

---

### System Under Test 1: TotalReclaw v0.2 E2EE (Original)

**Description:** Two-pass search with E2EE. Client-side decryption and BM25 reranking.

**Algorithm:**
```
PASS 1 (Remote, Server-Side, ~100ms):
  1. Client generates query embedding
  2. Client generates blind indices for query entities
  3. Send to server: {query_vector, blind_hashes, limit: 250}
  4. Server performs HNSW KNN search on encrypted embeddings
  5. Server returns top 250 matches (ciphertext only)

PASS 2 (Local, Client-Side, ~500ms):
  1. Client decrypts all 250 ciphertexts
  2. Client runs BM25 on decrypted plaintext
  3. Client applies RRF fusion:
     score = 1 / (60 + vector_rank) + 1 / (60 + bm25_rank)
  4. Client returns top 3-5 results
```

**Zero-Knowledge Properties:**
- Server stores only: ciphertext, embeddings, blind indices
- Server never sees plaintext
- Client does all decryption and BM25 locally

**Strengths:**
- Maintains zero-knowledge encryption
- Good semantic accuracy (remote vector search)
- Good keyword precision (local BM25)
- Blind indices enable exact-match queries

**Weaknesses:**
- Limited candidate pool (250) — potential recall loss
- Single-round BM25 (no refinement)
- No LLM reranking (less intelligent than QMD)
- No query expansion
- Blind indices only cover exact matches (no fuzzy/partial)

**Expected Use Case:** Original TotalReclaw E2EE design

---

### System Under Test 2: TotalReclaw v0.5 E2EE (Enhanced)

**Description:** Three-pass search with E2EE, LLM variant generation, and LLM reranking.

**Algorithm:**
```
INGESTION (When Saving Memory):
  1. Extract entities using regex + LLM
  2. Generate multi-variant blind indices:
     - Fast path: Regex-based (lowercase, separators, prefixes)
     - Smart path: LLM-based (context-aware variants)
  3. Store: ciphertext, embeddings, blind_indices

PASS 1 (Remote, Server-Side, ~100ms):
  1. Client generates query embedding
  2. Client generates multi-variant blind indices for query
  3. Send to server: {query_vector, blind_hashes, limit: 250}
  4. Server performs HNSW KNN search on encrypted embeddings
  5. Server checks blind indices for exact matches
  6. Server returns top 250 matches (ciphertext only)
     - Boosted if blind index match found

PASS 2 (Local, Client-Side, ~500ms):
  1. Client decrypts all 250 ciphertexts
  2. Client runs BM25 on decrypted plaintext
  3. Client applies RRF fusion (vector + BM25)

PASS 3 (Local, Client-Side, ~500ms):
  1. Client sends top 50 candidates to LLM
  2. LLM reranks based on:
     - Query intent understanding
     - Semantic relevance
     - Context and nuance
  3. LLM returns top 3-5 results with explanations
```

**Zero-Knowledge Properties:**
- Server stores only: ciphertext, embeddings, blind indices
- Server never sees plaintext
- Client does all decryption, BM25, and LLM calls locally
- LLM is the same one the agent uses (already available client-side)

**Enhancements over v0.2:**
- **Multi-variant blind indices:** Better coverage for fuzzy/partial queries
- **LLM reranking:** Intelligence similar to QMD, but maintains E2EE
- **Blind index boost in Pass 1:** Exact matches get priority

**Strengths:**
- Maintains zero-knowledge encryption
- Best-of-both-worlds: semantic + keyword + LLM intelligence
- Multi-variant blind indices improve recall
- LLM reranking improves precision
- Uses existing agent LLM (no extra infrastructure)

**Weaknesses:**
- Highest latency (~1.1s total: 100ms + 500ms + 500ms)
- Most complex client-side logic
- LLM token costs for reranking
- Still limited by 250 candidate pool

**Expected Use Case:** Enhanced TotalReclaw E2EE design

---

## Part 2: Query Categories

Based on real-world OpenClaw usage patterns from official documentation and QMD's architecture.

### Category A: Contextual/Fact Retrieval (30%)

**Definition:** Queries asking "what did X say about Y?" - referencing specific people and topics.

**Real-world examples from OpenClaw usage:**
- "What did Sarah say about the API key rotation?"
- "What did we decide about the deployment timeline?"
- "What's Rod's work schedule?"
- "What did Mike say about the database schema?"
- "What did security@example.com say about authentication?"

**Why this matters:** OpenClaw users frequently ask about what specific people said in emails or meetings. This tests:
- Entity extraction and blind indexing (names, emails)
- Cross-referencing capability
- Contextual understanding

**Distribution in Test Set:** 45 queries (30% of 150)

---

### Category B: Configuration & Setup Queries (20%)

**Definition:** Queries about system configuration, API setup, deployment details.

**Real-world examples from OpenClaw usage:**
- "What's my Gmail API configuration?"
- "How do I set up the deployment pipeline?"
- "What's the base URL for the production API?"
- "How did we configure rate limiting?"
- "What's the database connection string for staging?"

**Why this matters:** OpenClaw users frequently store configuration details in memory and need to retrieve them. This tests:
- Exact technical parameter matching
- Environment-specific queries (prod, staging, dev)
- Code snippet and configuration retrieval

**Distribution in Test Set:** 30 queries (20% of 150)

---

### Category C: Temporal/Recent Activity Queries (15%)

**Definition:** Queries referencing time - "yesterday", "last week", "recent", "today".

**Real-world examples from OpenClaw usage:**
- "What did we discuss about OAuth yesterday?"
- "What meetings did I have last week?"
- "What did I work on today?"
- "What errors did we encounter this week?"
- "What's changed since February 15th?"

**Why this matters:** OpenClaw's memory is organized by date (`memory/YYYY-MM-DD.md`). Users frequently query by recency. This tests:
- Temporal decay effectiveness
- Date-based retrieval
- Recent context prioritization

**Distribution in Test Set:** 22 queries (15% of 150)

---

### Category D: Error & Solution Lookup (15%)

**Definition:** Queries about problems encountered and how they were solved.

**Real-world examples from OpenClaw usage:**
- "How did we fix the 429 rate limit error?"
- "What was the solution for the authentication timeout?"
- "Why did the deployment fail last week?"
- "What's the fix for the CORS issue?"
- "How did we resolve the database deadlock?"

**Why this matters:** A key use case is recalling how past problems were solved. This tests:
- Error code matching (exact + semantic variants)
- Solution pairing (problem → fix)
- Technical troubleshooting context

**Distribution in Test Set:** 22 queries (15% of 150)

---

### Category E: Semantic/Concept Queries (12%)

**Definition:** Queries where wording differs from stored content (paraphrases, concepts).

**Examples:**
- "container orchestration setup" → expects Docker Compose, Kubernetes
- "CI/CD pipeline" → expects GitHub Actions, Jenkins
- "user authentication" → expects OAuth, JWT, login flow
- "database connection pool" → expects PostgreSQL, connection string
- "rate limiting strategy" → expects 429 errors, retry logic

**Why this matters:** Tests vector embedding quality and semantic understanding.

**Distribution in Test Set:** 18 queries (12% of 150)

---

### Category F: Exact/Keyword Queries (8%)

**Definition:** Queries requiring exact string matching (IDs, error codes, specific values).

**Examples:**
- "sk-proj-abc123xyz" → specific API key
- "0a1b2c3d-4e5f-6789" → specific UUID
- "memorySearch.query.hybrid" → exact code path
- "429 Too Many Requests" → exact error message
- "us-east-1" → specific region

**Why this matters:** Tests BM25 effectiveness and blind index coverage for exact tokens.

**Distribution in Test Set:** 13 queries (8% of 150)

---

## Part 3: Updated Test Query Distribution (Based on Real-World Usage)

### Total Test Set: 150 Queries

| Category | Count | Percentage | Real-World Justification |
|----------|-------|------------|---------------------------|
| **Contextual/Fact Retrieval** | 45 | 30% | "What did Sarah say about X?" - Most common OpenClaw pattern |
| **Configuration & Setup** | 30 | 20% | "What's my API config?" - Storing setup details is core use case |
| **Temporal/Recent Activity** | 22 | 15% | "What did we do yesterday?" - Daily note organization |
| **Error & Solution Lookup** | 22 | 15% | "How did we fix error X?" - Troubleshooting memory |
| **Semantic/Concept Queries** | 18 | 12% | "container orchestration" → Docker - Semantic understanding |
| **Exact/Keyword Queries** | 13 | 8% | "sk-proj-abc123" - Exact token matching |
| **Total** | **150** | **100%** | |

### Key Changes from Original Plan

1. **Added "Contextual/Fact Retrieval" (30%)** - This is the #1 real-world pattern based on OpenClaw docs. Users constantly ask "what did X say about Y?"

2. **Added "Configuration & Setup" (20%)** - OpenClaw users store a lot of technical configuration and need to retrieve it

3. **Added "Error & Solution Lookup" (15%)** - A critical pattern: remembering how problems were solved

4. **Reduced "Exact Keyword" from 25% → 8%** - These are less common in real usage than we initially thought

5. **Added "Temporal" category (15%)** - OpenClaw's date-based file organization (`memory/YYYY-MM-DD.md`) makes time-based queries very common

## Part 3: Test Query Distribution (Updated Based on Real-World Usage)

### Total Test Set: 150 Queries

| Category | Count | Percentage | Real-World Justification |
|----------|-------|------------|---------------------------|
| **Contextual/Fact Retrieval** | 45 | 30% | #1 pattern: "What did Sarah say about X?" |
| **Configuration & Setup** | 30 | 20% | Storing/retrieving setup details |
| **Temporal/Recent Activity** | 22 | 15% | Daily notes organization |
| **Error & Solution Lookup** | 22 | 15% | Troubleshooting memory |
| **Semantic/Concept Queries** | 18 | 12% | Semantic understanding |
| **Exact/Keyword Queries** | 13 | 8% | Exact token matching |
| **Total** | **150** | **100%** | |

### Difficulty Distribution

| Difficulty | Count | Percentage | Examples |
|------------|-------|------------|----------|
| **Easy** (exact match, direct) | 60 | 40% | "What's my API key?", "sk-proj-abc123" |
| **Medium** (some inference) | 60 | 40% | "What did Sarah say about OAuth?", "How did we fix the 429 error?" |
| **Hard** (requires context, multi-hop) | 30 | 20% | "What did we discuss yesterday that relates to today's deployment issue?" |

---

## Part 4: Evaluation Metrics by Category

### Expected Performance by Algorithm and Category (Updated)

| Algorithm | Contextual | Config | Temporal | Error | Semantic | Exact |
|-----------|-----------|--------|----------|-------|----------|-------|
| **BM25-Only** | Poor | Good | Poor | Fair | Poor | Excellent |
| **Vector-Only** | Good | Fair | Fair | Fair | Excellent | Poor |
| **OpenClaw Hybrid** | Good | Good | Good* | Good | Good | Good |
| **QMD Hybrid** | Excellent | Good | Good | Excellent | Excellent | Good |
| **TotalReclaw v0.2** | Fair | Good | Fair | Fair | Good | Fair** |
| **TotalReclaw v0.5** | Good | Good | Good | Good | Good | Good*** |

\* With temporal decay enabled
\*\* Limited by blind index coverage for exact queries
\*\*\* With multi-variant blind indices (regex + LLM)

### Key Hypotheses to Test (Updated)

**Hypothesis 1:** TotalReclaw v0.5 will match QMD's accuracy on contextual queries ("What did Sarah say about X?").

**Rationale:** Multi-variant blind indices + entity extraction should handle people references; LLM reranking handles contextual understanding.

**Hypothesis 2:** TotalReclaw v0.5 will match OpenClaw's accuracy on configuration queries.

**Rationale:** Both use vector + BM25 hybrid; blind indices cover exact technical parameters.

**Hypothesis 3:** TotalReclaw v0.2 will struggle with temporal queries due to lack of temporal decay.

**Rationale:** v0.2 has no time-based ranking; old and new memories are ranked equally.

**Hypothesis 4:** TotalReclaw v0.5's multi-variant blind indices will significantly improve exact-match query performance vs v0.2.

**Rationale:** Regex + LLM variant generation covers more query variations (separators, case, prefixes).

**Hypothesis 5:** The accuracy gap between v0.2 and v0.5 will be 5-15 percentage points.

**Rationale:** LLM reranking + multi-variant blind indices should provide measurable improvement.

---

## Part 5: Success Criteria

### Primary Decision Matrix

| Metric | TotalReclaw v0.2 | TotalReclaw v0.5 | Decision |
|--------|------------------|------------------|----------|
| **F1 vs OpenClaw** | Within 10% | Within 5% | v0.5 preferred |
| **F1 vs QMD** | Within 15% | Within 10% | v0.5 preferred |
| **MRR** | >0.70 | >0.75 | v0.5 preferred |
| **Latency p95** | <1.5s | <2s | Both acceptable |

### Go/No-Go Thresholds

**GO with v0.2 (Original Design):**
- F1 score >0.80 OR
- Within 10% of OpenClaw hybrid OR
- MRR >0.70

**GO with v0.5 (Enhanced Design):**
- F1 score >0.82 OR
- Within 5% of OpenClaw hybrid OR
- Within 10% of QMD hybrid OR
- MRR >0.75

**MODIFY (Adjust Architecture):**
- v0.2: F1 0.75-0.80 OR within 10-15% of OpenClaw
- v0.5: F1 0.78-0.82 OR within 5-10% of OpenClaw

**NO-GO (Reconsider Architecture):**
- v0.2: F1 <0.75 OR >15% gap from OpenClaw
- v0.5: F1 <0.78 OR >10% gap from OpenClaw

---

## Part 6: Expected Results & Interpretation

### Scenario 1: v0.5 Matches QMD Accuracy

**Interpretation:** The enhancements (LLM reranking + multi-variant blind indices) successfully overcome E2EE constraints.

**Action:** Proceed with v0.5 for MVP development.

### Scenario 2: v0.5 Exceeds v0.2 by <5%

**Interpretation:** Enhancements provide marginal benefit; may not justify added complexity.

**Action:** Consider trade-offs:
- If latency is acceptable: proceed with v0.5
- If latency is problematic: start with v0.2, add v0.5 features as opt-in

### Scenario 3: v0.5 Significantly Underperforms (<10% gap)

**Interpretation:** E2EE constraints are fundamental limitations; LLM reranking and multi-variant indices aren't enough.

**Action:** Reconsider architecture:
- Increase candidate pool (250 → 500 or 1000)
- Add server-side enrichment (relaxes E2EE)
- Accept lower accuracy for zero-knowledge guarantee

### Scenario 4: v0.2 and v0.5 Both Underperform

**Interpretation:** Two-pass hybrid search with limited candidate pool is fundamentally flawed.

**Action:** Pivot to alternative:
- Single-pass search (remote only, larger pool)
- Client-side full-text search (no remote vector)
- Accept local-first only (no sync)

---

## Part 7: Test Execution Order

### Phase 1: Baselines Only (Week 1)

1. Implement BM25-Only
2. Implement Vector-Only
3. Implement OpenClaw Hybrid
4. Run initial evaluations
5. Establish baseline accuracy

**Purpose:** Validate testbed and establish performance floor.

### Phase 2: QMD Baseline (Week 2)

1. Implement QMD-Style Hybrid
2. Evaluate against existing baselines
3. Identify QMD's advantages

**Purpose:** Establish state-of-the-art plaintext performance.

### Phase 3: TotalReclaw v0.2 (Week 2)

1. Implement TotalReclaw v0.2 E2EE
2. Evaluate against baselines
3. Identify accuracy gaps

**Purpose:** Validate original E2EE design.

### Phase 4: TotalReclaw v0.5 (Week 3)

1. Implement TotalReclaw v0.5 E2EE
2. Evaluate against all baselines
3. Compare v0.2 vs v0.5

**Purpose:** Validate enhanced E2EE design.

### Phase 5: Analysis & Decision (Week 3)

1. Comprehensive comparison
2. Go/no-go recommendation
3. Architecture decision

**Purpose:** Make build/pivot decision.

---

## Part 8: Summary

**What We're Testing:**

6 algorithms × 6 query categories × 200 queries = 72,000 individual search results

**Key Questions:**

1. Can v0.2 match OpenClaw's plaintext accuracy with E2EE?
2. Can v0.5 match QMD's plaintext accuracy with E2EE?
3. What are the accuracy/latency trade-offs?
4. Are the enhancements worth the complexity?

**Decision Criteria:**

- **Accuracy:** Within 5-10% of state-of-the-art plaintext
- **Latency:** <2s p95 acceptable for memory search
- **Complexity:** v0.5 is more complex; validate that benefit > cost

**Next Steps:**

After testbed execution, we'll have clear data to decide:
- Proceed with v0.2 (simpler, good enough)
- Proceed with v0.5 (more complex, better accuracy)
- Modify architecture (testbed revealed issues)
- Pivot entirely (E2EE constraints too limiting)

---

**Document Control:**

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2026-02-18 | Initial test scenarios and baselines | TotalReclaw Team |
