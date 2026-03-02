# Baseline Search Algorithms - Implementation Report

**Date:** 2026-02-18
**Version:** 1.0.0
**Status:** Complete

---

## Executive Summary

This report documents the implementation of 4 plaintext baseline search algorithms for the TotalReclaw testbed. These algorithms will be used to compare TotalReclaw's E2EE search performance against state-of-the-art plaintext search systems.

### Algorithms Implemented

1. **BM25-Only** - Pure keyword search using BM25 ranking
2. **Vector-Only** - Pure semantic search using cosine similarity
3. **OpenClaw Hybrid** - Replicates OpenClaw's official hybrid search
4. **QMD-Style Hybrid** - Replicates QMD's sophisticated approach with RRF fusion

---

## Algorithm Specifications

### 1. BM25-Only Search

**File:** `/Users/pdiogo/Documents/code/totalreclaw/testbed/baseline/bm25_only.py`

**Algorithm:**
```
1. Tokenize query and documents
2. Calculate BM25 scores using rank-bm25
3. Return top-k results by score descending
```

**Key Features:**
- Portable BM25 implementation included (no external dependency issues)
- Custom tokenization handles emails, UUIDs, and code identifiers
- Configurable parameters: k1=1.5, b=0.75, epsilon=0.25

**Expected Performance:**
- Excellent for exact matches (emails, IDs, error codes)
- Poor for semantic queries
- Fast: <50ms typical

**Function Signature:**
```python
def bm25_only_search(
    query: str,
    documents: List[str],
    top_k: int = 5,
    k1: float = 1.5,
    b: float = 0.75,
    epsilon: float = 0.25
) -> List[Tuple[int, float]]
```

---

### 2. Vector-Only Search

**File:** `/Users/pdiogo/Documents/code/totalreclaw/testbed/baseline/vector_only.py`

**Algorithm:**
```
1. Encode query using all-MiniLM-L6-v2
2. Calculate cosine similarity with document embeddings
3. Return top-k results by similarity descending
```

**Key Features:**
- Uses sentence-transformers all-MiniLM-L6-v2 model
- 384-dimensional embeddings
- Model caching for performance
- Cosine similarity via sklearn

**Expected Performance:**
- Excellent for semantic queries and paraphrases
- Poor for exact matches (IDs, error codes)
- Moderate latency: 100-200ms

**Function Signature:**
```python
def vector_only_search(
    query: str,
    embeddings: np.ndarray,
    top_k: int = 5,
    model_name: str = 'all-MiniLM-L6-v2'
) -> List[Tuple[int, float]]
```

---

### 3. OpenClaw Hybrid Search

**File:** `/Users/pdiogo/Documents/code/totalreclaw/testbed/baseline/openclaw_hybrid.py`

**Algorithm (from OpenClaw docs):**
```
1. Vector search: top (maxResults × candidateMultiplier) by cosine similarity
2. BM25 search: top (maxResults × candidateMultiplier) by FTS5 BM25 rank
3. Convert BM25 rank to score: textScore = 1 / (1 + max(0, bm25Rank))
4. Merge: finalScore = vectorWeight × vectorScore + textWeight × textScore
5. Return top-k results by finalScore descending
```

**Key Features:**
- Exact replica of OpenClaw's default search algorithm
- Default weights: vectorWeight=0.7, textWeight=0.3
- Default candidateMultiplier=4
- Optional temporal decay feature

**Expected Performance:**
- Good balance of semantic and keyword search
- Matches OpenClaw's production behavior
- The current standard for OpenClaw users

**Function Signature:**
```python
def openclaw_hybrid_search(
    query: str,
    documents: List[str],
    embeddings: np.ndarray,
    top_k: int = 5,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
    candidate_multiplier: int = 4,
    model=None
) -> List[Tuple[int, float]]
```

---

### 4. QMD-Style Hybrid Search

**File:** `/Users/pdiogo/Documents/code/totalreclaw/testbed/baseline/qmd_hybrid.py`

**Algorithm (from QMD GitHub):**
```
1. Query Expansion: LLM generates 1 variant query
2. Parallel Retrieval: Original (×2 weight) + variant search both FTS and vector
3. RRF Fusion: score = Σ(1/(k+rank+1)) where k=60
4. Top-Rank Bonus: #1 gets +0.05, #2-3 get +0.02
5. Top 30 candidates → LLM reranking
6. Position-Aware Blending:
   - Rank 1-3:  75% RRF / 25% reranker
   - Rank 4-10: 60% RRF / 40% reranker
   - Rank 11+:  40% RRF / 60% reranker
```

**Key Features:**
- Sophisticated fusion with Reciprocal Rank Fusion
- Query expansion via rule-based synonyms
- Top-rank bonus for precision
- Position-aware blending
- Simulated LLM reranking (testbed version)

**Expected Performance:**
- Best accuracy among plaintext baselines
- Higher latency due to complexity
- State-of-the-art for local search

**Function Signature:**
```python
def qmd_hybrid_search(
    query: str,
    documents: List[str],
    embeddings: np.ndarray,
    top_k: int = 5,
    candidate_multiplier: int = 4,
    rrf_k: int = 60,
    use_query_expansion: bool = True,
    use_reranking: bool = True,
    model=None
) -> List[Tuple[int, float]]
```

---

## Common Interface

All algorithms follow a consistent interface:

```python
def search(
    query: str,              # Search query string
    documents: List[str],    # Documents to search (BM25/hybrid)
    embeddings: np.ndarray,  # Document embeddings (vector/hybrid)
    top_k: int = 5          # Number of results to return
) -> List[Tuple[int, float]]  # (doc_index, score) sorted by score
```

---

## Testing

### Unit Tests

**File:** `/Users/pdiogo/Documents/code/totalreclaw/testbed/tests/test_baselines.py`

**Test Coverage:**
- Exact keyword matching (BM25)
- Semantic search (Vector)
- Hybrid fusion (OpenClaw, QMD)
- Edge cases (empty queries, no matches)
- Algorithm comparisons

**Run Tests:**
```bash
cd /Users/pdiogo/Documents/code/totalreclaw
pytest testbed/tests/test_baselines.py -v
```

---

## Performance Benchmarking

### Benchmark Script

**File:** `/Users/pdiogo/Documents/code/totalreclaw/testbed/benchmark_baselines.py`

**Metrics Collected:**
- p50, p95, p99 latency
- Average, min, max latency
- Queries per second
- Average result count

**Run Benchmark:**
```bash
cd /Users/pdiogo/Documents/code/totalreclaw
python testbed/benchmark_baselines.py
```

---

## Expected Performance by Query Type

| Algorithm | Exact/Keyword | Semantic | Mixed | Contextual |
|-----------|---------------|----------|-------|------------|
| **BM25-Only** | Excellent | Poor | Fair | Poor |
| **Vector-Only** | Poor | Excellent | Fair | Good |
| **OpenClaw Hybrid** | Good | Good | Good | Good |
| **QMD Hybrid** | Good | Excellent | Excellent | Excellent |

---

## Dependencies

### Required
- `numpy` - Numerical operations
- `scikit-learn` - Cosine similarity
- `sentence-transformers` - Embeddings (auto-downloaded)

### Optional
- `pytest` - Unit testing
- `rank-bm25` - Not required (portable implementation included)

---

## File Structure

```
testbed/
├── baseline/
│   ├── __init__.py
│   ├── bm25_only.py              # BM25-Only implementation
│   ├── vector_only.py            # Vector-Only implementation
│   ├── openclaw_hybrid.py        # OpenClaw Hybrid implementation
│   ├── qmd_hybrid.py             # QMD-Style Hybrid implementation
│   └── rank_bm25_portable.py     # Portable BM25 (no deps)
├── tests/
│   ├── __init__.py
│   └── test_baselines.py         # Unit tests
├── data/
│   └── benchmark_results.md      # Generated by benchmark script
└── benchmark_baselines.py        # Performance benchmarking script
```

---

## Usage Example

```python
from testbed.baseline import (
    bm25_only_search,
    vector_only_search,
    openclaw_hybrid_search,
    qmd_hybrid_search,
    compute_embeddings
)

# Sample documents
documents = [
    "API key: sk-proj-abc123 for authentication",
    "Database connection pool configuration",
    "Deployment to us-east-1 using Docker"
]

# Compute embeddings (for vector-based algorithms)
embeddings = compute_embeddings(documents)

# Run searches
query = "API configuration"

bm25_results = bm25_only_search(query, documents, top_k=3)
vector_results = vector_only_search(query, embeddings, top_k=3)
openclaw_results = openclaw_hybrid_search(query, documents, embeddings, top_k=3)
qmd_results = qmd_hybrid_search(query, documents, embeddings, top_k=3)

# Results are list of (doc_index, score) tuples
for idx, score in openclaw_results:
    print(f"Doc {idx}: {score:.3f} - {documents[idx]}")
```

---

## Deliverables Checklist

- [x] BM25-Only algorithm implementation
- [x] Vector-Only algorithm implementation
- [x] OpenClaw Hybrid algorithm implementation
- [x] QMD-Style Hybrid algorithm implementation
- [x] Common interface for all algorithms
- [x] Unit tests for each algorithm
- [x] Performance benchmarking script
- [x] Algorithm comparison report (this document)

---

## Next Steps

1. **Wait for real dataset** from data-generator agent
2. **Run full evaluation** with ground truth labels
3. **Generate accuracy report** comparing all algorithms
4. **Compare against TotalReclaw E2EE** when implemented

---

**Implementation Status:** COMPLETE

All 4 baseline algorithms are implemented and ready for use in the TotalReclaw testbed. The data-generator agent will provide the real dataset for comprehensive evaluation.
