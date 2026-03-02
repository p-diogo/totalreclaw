# TotalReclaw v0.6 Technical Specification

**Version:** 0.6.0
**Date:** 2026-02-20
**Status:** Draft
**Author:** TotalReclaw Team

---

## Overview

TotalReclaw v0.6 introduces **Encrypted BM25 Index Storage** to achieve baseline-comparable search accuracy while maintaining zero-knowledge encryption and full data portability.

### Key Changes from v0.5

| Feature | v0.5 | v0.6 |
|---------|------|------|
| BM25 Scope | Top 250 candidates only | **Full corpus** |
| Index Storage | Not stored | **Encrypted on server** |
| Query Expansion | LLM reranking only | **Pre-search expansion** |
| Portability | ✅ Full | ✅ Full |
| Zero-Knowledge | ✅ Yes | ✅ Yes |

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SERVER (Zero-Knowledge)                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │ Encrypted       │  │ Encrypted       │  │ Encrypted BM25 Index        │ │
│  │ Documents       │  │ Embeddings      │  │ (NEW in v0.6)               │ │
│  │ (AES-GCM)       │  │ (AES-GCM)       │  │ (AES-GCM serialized)        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
│                                                                              │
│  Server sees ONLY ciphertext - cannot read documents, embeddings, or index   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ mTLS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT (Trusted)                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │ Master Password │  │ Decrypted       │  │ BM25 Index                  │ │
│  │ (derived keys)  │  │ Documents       │  │ (in-memory, from encrypted) │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ SEARCH FLOW (v0.6)                                                      ││
│  │                                                                         ││
│  │  1. Query Expansion (NEW)                                               ││
│  │     Query → Local LLM → [query, synonyms, related terms]                ││
│  │                                                                         ││
│  │  2. Parallel Search                                                     ││
│  │     ├─ BM25: Full corpus search on expanded queries                     ││
│  │     └─ Vector: KNN on encrypted embeddings (server-side)                ││
│  │                                                                         ││
│  │  3. RRF Fusion                                                          ││
│  │     Combine BM25 + Vector scores → Final ranking                        ││
│  │                                                                         ││
│  │  4. Decrypt & Return                                                    ││
│  │     Decrypt top-K documents → Return to user                            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Storage, Encryption & Portability

### Server-Side Storage (Zero-Knowledge)

The server stores ONLY encrypted data. The hosting provider cannot access plaintext content.

| Data | Format | Encrypted | Server Can Read? |
|------|--------|-----------|------------------|
| Documents | AES-256-GCM ciphertext | Yes | No |
| Embeddings | AES-256-GCM ciphertext | Yes | No |
| Blind Indices | SHA-256 hashes | N/A (already hashed) | No |
| **BM25 Index** | **AES-256-GCM ciphertext** | **Yes** | **No** |

**NEW in v0.6:** The BM25 index is encrypted and stored on the server, enabling full-corpus keyword search without server-side plaintext access.

### Client-Side Storage

| Data | Stored on Disk? | In Memory? | Notes |
|------|-----------------|------------|-------|
| Master password | No | No | User enters each session |
| Derived keys | No | Yes | Calculated from password |
| Decrypted documents | No | Yes (on-demand) | Decrypted for display |
| **BM25 index** | **No** | **Yes (decrypted at startup)** | **Downloaded encrypted, decrypted to memory** |

**CRITICAL:** No unencrypted data is EVER written to client disk. The BM25 index is downloaded encrypted, decrypted to memory, and never touches disk in plaintext.

### Portability

**Can I move to a different agent?** YES

1. New agent connects to server
2. Downloads ALL encrypted data:
   - Encrypted documents
   - Encrypted embeddings
   - Encrypted BM25 index (NEW in v0.6)
3. User enters master password
4. Agent decrypts everything into memory (including BM25 index)
5. Full memory access with full-corpus search restored

**All persistent data lives on the server (encrypted).** The client is stateless.

### Comparison: v0.2 vs v0.6 Storage

| Aspect | v0.2 | v0.6 |
|--------|------|------|
| Documents on server | Encrypted | Encrypted |
| BM25 index on server | Not stored | Encrypted |
| Client disk storage | None | None |
| Client memory (startup) | Low | Higher (BM25 index) |
| Search scope | Top 250 candidates | Full corpus |

---

## Component Specifications

### 1. Encrypted BM25 Index

#### 1.1 Index Structure

The BM25 index is serialized and encrypted for server storage:

```python
@dataclass
class BM25Index:
    """Serializable BM25 index structure."""

    # Document frequencies
    doc_freqs: Dict[str, int]  # term -> document frequency

    # Inverse document frequencies
    idf: Dict[str, float]  # term -> IDF score

    # Term frequencies per document
    doc_term_freqs: List[Dict[str, int]]  # doc_id -> {term: freq}

    # Document lengths
    doc_lengths: List[int]

    # Average document length
    avgdl: float

    # Metadata
    version: str = "0.6.0"
    created_at: str = ""
    doc_count: int = 0

    # BM25 parameters
    k1: float = 1.5
    b: float = 0.75
```

#### 1.2 Encryption

The serialized index is encrypted using AES-256-GCM:

```python
class EncryptedBM25Index:
    """Encrypted BM25 index for server storage."""

    ciphertext: bytes  # Encrypted index data
    nonce: bytes       # 12-byte nonce for AES-GCM
    tag: bytes         # 16-byte authentication tag
    version: str       # Index format version
    doc_count: int     # Number of documents in index
    created_at: str    # ISO timestamp
```

#### 1.3 Storage Location

```
Server Storage Structure:
/users/{user_id}/
├── memories/
│   ├── {memory_id_1}.enc
│   ├── {memory_id_2}.enc
│   └── ...
├── embeddings/
│   └── embeddings.enc  # Encrypted numpy array
└── index/
    └── bm25_index.enc  # Encrypted BM25 index (NEW)
```

---

### 2. Query Expansion

#### 2.1 Expansion Strategy

Query expansion generates semantically related terms to improve recall:

```python
@dataclass
class ExpandedQuery:
    """Result of query expansion."""

    original: str              # Original user query
    expanded_terms: List[str]  # Synonyms and related terms
    expanded_queries: List[str] # Full query variations
    confidence: float          # LLM confidence score
```

#### 2.2 Expansion Prompt

```
You are a query expansion assistant for a memory search system.

Given a user's search query, generate 2-4 semantically related search terms
that might help find relevant memories. Focus on:
- Synonyms
- Related concepts
- Alternative phrasings
- Technical terms if applicable

Query: "{user_query}"

Return ONLY a JSON array of terms, nothing else.
Example: ["term1", "term2", "term3"]
```

#### 2.3 Local LLM Configuration

```yaml
query_expansion:
  model: "llama3.2:3b"  # Or similar local model
  max_tokens: 50
  temperature: 0.3
  timeout_ms: 500

  fallback:
    enabled: true
    strategy: "none"  # Skip expansion if LLM unavailable
```

#### 2.4 Expansion Examples

| Original Query | Expanded Terms |
|----------------|----------------|
| "database slow" | ["db performance", "query optimization", "latency", "SQL tuning"] |
| "API error 429" | ["rate limit", "throttling", "too many requests", "HTTP 429"] |
| "deploy to production" | ["release", "deployment", "prod", "ship to prod"] |
| "meeting with John" | ["appointment", "discussion", "John", "sync"] |

---

### 3. Search Flow

#### 3.1 Search Request

```python
@dataclass
class SearchRequest:
    """v0.6 search request."""

    query: str
    top_k: int = 5

    # Expansion options
    expand_query: bool = True
    max_expansions: int = 3

    # Search weights
    bm25_weight: float = 0.5
    vector_weight: float = 0.5

    # RRF parameter
    rrf_k: int = 60
```

#### 3.2 Search Response

```python
@dataclass
class SearchResponse:
    """v0.6 search response."""

    results: List[SearchResult]

    # Timing breakdown
    timing: SearchTiming

    # Query expansion info
    expanded_query: Optional[ExpandedQuery]

class SearchTiming:
    expansion_ms: float = 0.0
    bm25_ms: float = 0.0
    vector_ms: float = 0.0
    decrypt_ms: float = 0.0
    fusion_ms: float = 0.0
    total_ms: float = 0.0
```

#### 3.3 Search Algorithm

```
FUNCTION search(query, top_k):
    # Step 1: Query Expansion
    IF expand_query:
        expanded = expand_query_with_llm(query)
        queries = [query] + expanded.expanded_queries
    ELSE:
        queries = [query]

    # Step 2: BM25 Search (Full Corpus)
    bm25_results = {}
    FOR q IN queries:
        FOR doc_id, score IN bm25.search(q, corpus=all_documents):
            bm25_results[doc_id] = max(bm25_results.get(doc_id, 0), score)

    # Step 3: Vector Search (Server-side KNN)
    query_embedding = embed(query)
    vector_results = server.knn_search(query_embedding, top_k=250)

    # Step 4: Decrypt Candidates
    candidates = set(bm25_results.keys()) | set(vector_results.keys())
    decrypted = {}
    FOR doc_id IN candidates:
        decrypted[doc_id] = client.decrypt(server.get_encrypted(doc_id))

    # Step 5: RRF Fusion
    final_scores = rrf_fusion(bm25_results, vector_results, k=rrf_k)

    # Step 6: Return Top-K
    RETURN top_k(final_scores, decrypted)
```

---

### 4. Index Update Protocol

#### 4.1 When Index Updates Occur

| Event | Action | Frequency |
|-------|--------|-----------|
| New memory added | Incremental update | Multiple/day |
| Memory updated | Incremental update | Occasional |
| Memory deleted | Incremental update | Occasional |
| Batch import | Full reindex | Rare |
| Client startup | Download & decrypt | Per session |

#### 4.2 Incremental Update Flow

```
FUNCTION add_memory(memory):
    # 1. Add to local index
    bm25_index.add_document(memory.id, memory.content)

    # 2. Encrypt and upload document
    encrypted = encrypt(memory.content, key)
    server.upload_document(memory.id, encrypted)

    # 3. Generate and upload embedding
    embedding = embed(memory.content)
    encrypted_embedding = encrypt(embedding, key)
    server.upload_embedding(memory.id, encrypted_embedding)

    # 4. Re-encrypt and upload index
    encrypted_index = encrypt(bm25_index.serialize(), key)
    server.upload_index(encrypted_index)

FUNCTION remove_memory(memory_id):
    # 1. Remove from local index
    bm25_index.remove_document(memory_id)

    # 2. Delete from server
    server.delete_document(memory_id)
    server.delete_embedding(memory_id)

    # 3. Re-encrypt and upload index
    encrypted_index = encrypt(bm25_index.serialize(), key)
    server.upload_index(encrypted_index)
```

#### 4.3 Batch Update Optimization

For multiple changes, batch updates are more efficient:

```python
@dataclass
class BatchUpdate:
    """Batch memory update for efficiency."""

    additions: List[Memory] = []
    updates: List[Memory] = []
    deletions: List[str] = []  # memory IDs

    def apply(self, bm25_index: BM25Index) -> BM25Index:
        # Apply all changes in one pass
        for memory in self.deletions:
            bm25_index.remove_document(memory)
        for memory in self.updates:
            bm25_index.update_document(memory.id, memory.content)
        for memory in self.additions:
            bm25_index.add_document(memory.id, memory.content)
        return bm25_index
```

---

## Performance Specifications

### Latency Targets

| Operation | Target | Acceptable |
|-----------|--------|------------|
| Client startup (index decrypt) | <100ms | <500ms |
| Single search (no expansion) | <50ms | <100ms |
| Single search (with expansion) | <200ms | <500ms |
| Add single memory | <200ms | <1s |
| Batch update (10 memories) | <500ms | <2s |
| Full reindex (1000 memories) | <3s | <10s |

### Storage Estimates

| Component | Per Memory | 1000 Memories | 10000 Memories |
|-----------|------------|---------------|----------------|
| Encrypted document | ~2KB | ~2MB | ~20MB |
| Encrypted embedding | ~1.5KB | ~1.5MB | ~15MB |
| Encrypted BM25 index | N/A | ~500KB | ~5MB |
| **Total** | ~3.5KB | ~4MB | ~40MB |

---

## Test Specifications

### Unit Tests

```python
class TestBM25Index:
    def test_serialize_deserialize(self):
        """Index serialization should be lossless."""

    def test_encryption_decryption(self):
        """Encrypted index should decrypt correctly."""

    def test_incremental_update(self):
        """Adding/removing docs should update index correctly."""

class TestQueryExpansion:
    def test_expansion_generates_terms(self):
        """Expansion should return related terms."""

    def test_expansion_timeout_fallback(self):
        """Should gracefully handle LLM timeout."""

    def test_expansion_empty_query(self):
        """Should handle empty or invalid queries."""

class TestSearchFlow:
    def test_full_corpus_bm25(self):
        """BM25 should search entire corpus."""

    def test_rrf_fusion(self):
        """RRF should correctly combine scores."""

    def test_expansion_improves_recall(self):
        """Query expansion should improve recall metrics."""
```

### Integration Tests

```python
class TestEndToEndSearch:
    def test_search_returns_relevant_results(self):
        """Search should return documents matching query intent."""

    def test_keyword_query_accuracy(self):
        """Keyword queries should match BM25 baseline accuracy."""

    def test_semantic_query_accuracy(self):
        """Semantic queries should leverage vector search."""

class TestIndexUpdates:
    def test_add_memory_updates_index(self):
        """Adding memory should update searchable index."""

    def test_delete_memory_removes_from_index(self):
        """Deleted memories should not appear in search."""

    def test_update_memory_reindexes(self):
        """Updated memories should reflect new content."""
```

### Benchmark Tests

```python
class TestPerformance:
    def test_search_latency_p95(self):
        """95% of searches should complete under 100ms."""

    def test_startup_latency(self):
        """Client startup should complete under 500ms."""

    def test_index_update_latency(self):
        """Single memory update should complete under 1s."""

    def test_large_corpus_performance(self):
        """Search should scale linearly with corpus size."""
```

---

## Migration from v0.5

### Migration Steps

1. **Download existing data:**
   - Encrypted documents
   - Encrypted embeddings

2. **Decrypt with master password**

3. **Build BM25 index:**
   ```python
   bm25_index = BM25Index()
   for doc_id, content in decrypted_docs.items():
       bm25_index.add_document(doc_id, content)
   ```

4. **Encrypt and upload index:**
   ```python
   encrypted_index = encrypt(bm25_index.serialize(), key)
   server.upload_index(encrypted_index)
   ```

### Migration Time Estimates

| Memory Count | Migration Time |
|--------------|----------------|
| 100 | <5 seconds |
| 1,000 | <30 seconds |
| 10,000 | <5 minutes |

---

## Security Considerations

### Threat Model

| Threat | Mitigation |
|--------|------------|
| Server reads plaintext | All data encrypted with client-held key |
| Server infers content from index | Index encrypted, terms not readable |
| Network interception | mTLS for all communication |
| Client compromise | Master password required for decryption |

### Cryptographic Specifications

| Component | Algorithm | Key Size |
|-----------|-----------|----------|
| Document encryption | AES-256-GCM | 256 bits |
| Embedding encryption | AES-256-GCM | 256 bits |
| Index encryption | AES-256-GCM | 256 bits |
| Key derivation | Argon2id | Output: 256 bits |

---

## Appendix A: API Reference

### Client API

```python
class TotalReclawClient:
    """v0.6 client API."""

    def __init__(self, master_password: str, server_url: str):
        """Initialize client with credentials."""

    def search(self, query: str, top_k: int = 5,
               expand_query: bool = True) -> SearchResponse:
        """Search memories with optional query expansion."""

    def add_memory(self, content: str, metadata: dict = None) -> str:
        """Add a new memory. Returns memory ID."""

    def update_memory(self, memory_id: str, content: str) -> None:
        """Update an existing memory."""

    def delete_memory(self, memory_id: str) -> None:
        """Delete a memory."""

    def batch_update(self, additions: List, updates: List,
                    deletions: List) -> None:
        """Batch update multiple memories efficiently."""
```

---

## Appendix B: Configuration

```yaml
# totalreclaw_config.yaml

version: "0.6.0"

server:
  url: "https://api.totalreclaw.dev"
  timeout_ms: 10000

encryption:
  algorithm: "AES-256-GCM"
  key_derivation: "Argon2id"

search:
  top_k: 5
  bm25_weight: 0.5
  vector_weight: 0.5
  rrf_k: 60

query_expansion:
  enabled: true
  model: "llama3.2:3b"
  max_expansions: 3
  timeout_ms: 500

index:
  storage: "server"  # "server" or "local"
  update_mode: "incremental"  # "incremental" or "batch"
  batch_size: 10
```

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 0.6.0 | 2026-02-20 | Initial v0.6 specification |
