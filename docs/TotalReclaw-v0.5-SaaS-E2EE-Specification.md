# TotalReclaw v0.5 SaaS: Enhanced E2EE Specification

**Version:** 0.5.0
**Status:** Draft
**Last Updated:** February 18, 2026

**Purpose:** Technical specification for TotalReclaw SaaS with enhanced zero-knowledge E2EE, incorporating LLM-powered variant generation and reranking based on testbed findings.

---

## Part 1: Executive Summary

### 1.1 What Changed Since v0.2

TotalReclaw v0.5 incorporates three major enhancements based on competitive analysis and UX requirements:

| Enhancement | v0.2 | v0.5 | Rationale |
|-------------|------|------|-----------|
| **Search Passes** | 2-pass | 3-pass | Add LLM reranking for QMD-like accuracy |
| **Blind Indices** | Single-variant | Multi-variant | Improve fuzzy/partial query coverage |
| **Index Generation** | Regex-only | Regex + LLM | Smarter variant generation, better coverage |
| **Dataset Focus** | Technical docs | Email/Calendar heavy | Match real OpenClaw usage patterns |

### 1.2 Core Design Principles

1. **Zero-Knowledge Above All**
   - Server never sees plaintext
   - Encryption happens client-side before network transmission
   - Even with LLM features, E2EE is maintained

2. **Competitive Accuracy**
   - Match or exceed QMD's plaintext search accuracy
   - Within 5% of OpenClaw's default hybrid search

3. **Client-Side Intelligence**
   - LLM calls happen locally (on the agent's machine)
   - Uses the same LLM the agent is already using
   - No additional infrastructure required

4. **Acceptable Latency**
   - Total search time <2s p95
   - Asynchronous where possible (don't block agent)

---

## Part 2: Architecture Overview

### 2.1 System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    TOTALRECLAW v0.5 ARCHITECTURE                │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐    ┌──────────────────────┐
│   CLIENT-SIDE        │    │   SERVER-SIDE        │
│   (Local Node)        │    │   (TotalReclaw SaaS)  │
│                      │    │                      │
│ ┌──────────────────┐  │    │ ┌──────────────────┐ │
│ │ LLM Integration │  │    │ │ PostgreSQL +     │ │
│ │ (Agent's LLM)    │  │    │ │ pgvector         │ │
│ └──────────────────┘  │    │ └──────────────────┘ │
│                      │    │                      │
│ ┌──────────────────┐  │    │                      │
│ │ Crypto Engine    │  │    │                      │
│ │ • Argon2id KDF   │  │    │                      │
│ │ • AES-GCM        │  │    │                      │
│ │ • HMAC-SHA256    │  │    │                      │
│ └──────────────────┘  │    │                      │
│                      │    │                      │
│ ┌──────────────────┐  │    │                      │
│ │ Search Engine    │  │    │                      │
│ │ • ONNX Embedder  │  │    │                      │
│ │ • BM25 Reranker  │  │    │                      │
│ │ • RRF Fusion     │  │    │                      │
│ └──────────────────┘  │    │                      │
│                      │    │                      │
│ ┌──────────────────┐  │    │                      │
│ │ Blind Index Gen  │  │    │                      │
│ │ • Regex Extractor │  │    │                      │
│ │ • LLM Variants   │  │    │                      │
│ └──────────────────┘  │    │                      │
│                      │    │                      │
└──────────────────────┘    │                      │
         │ mTLS                │
         └─────────────────────┘
```

### 2.2 Data Flow

**Memory Ingestion Flow:**

```
1. Agent creates memory → Plain text
       ↓
2. Entity Extraction (Regex + LLM)
   - Fast path: Regex for emails, UUIDs, codes
   - Smart path: LLM for context-aware entities
       ↓
3. Multi-Variant Blind Index Generation
   - For each entity, generate variants:
     * Lowercase
     * Case variations
     * Separator substitutions
     * Prefixes/suffixes
     * Substrings
       ↓
4. Local Vectorization
   - ONNX all-MiniLM-L6-v2 (INT8)
   - 384-dimensional embedding
       ↓
5. Local Encryption
   - AES-GCM with Data Key
   - Generate nonce for each memory
       ↓
6. Upload to Server
   - Ciphertext
   - Embedding
   - Blind indices
   - Metadata
```

**Memory Retrieval Flow:**

```
1. User submits query via agent
       ↓
2. Multi-Variant Blind Index Generation (Query)
   - Generate blind hashes for query entities
   - LLM expands query with related terms (optional)
       ↓
3. Local Vectorization (Query)
   - Generate query embedding
       ↓
4. PASS 1: Remote Search (Server)
   - HNSW KNN on query embedding
   - Blind index exact-match check
   - Return top 250 candidates (ciphertext + scores)
       ↓
5. PASS 2: Local Decryption + BM25
   - Decrypt all 250 candidates
   - Run BM25 on plaintext
   - RRF fusion: score = 1/(60+vector) + 1/(60+bm25)
   - Return top 50 candidates
       ↓
6. PASS 3: LLM Reranking
   - Send top 50 candidates + query to LLM
   - LLM reranks based on relevance and understanding
   - Return top 3-5 results with explanations
       ↓
7. Return results to agent
```

---

## Data Storage, Encryption & Portability

### Server-Side Storage (Zero-Knowledge)

The server stores ONLY encrypted data. The hosting provider cannot access plaintext content.

| Data | Format | Encrypted | Server Can Read? |
|------|--------|-----------|------------------|
| Documents | AES-256-GCM ciphertext | Yes | No |
| Embeddings | AES-256-GCM ciphertext | Yes | No |
| Blind Indices | SHA-256 hashes | N/A (already hashed) | No (one-way hash) |

**What the server NEVER sees:**
- Plaintext document content
- Raw embedding vectors (semantic meaning)
- Master password or derived keys

**What the server CAN see:**
- Encrypted blobs (ciphertext)
- Blind index hashes (for exact match lookups)
- Metadata (document count, timestamps, etc.)

### Client-Side Storage

| Data | Stored on Disk? | In Memory? | Notes |
|------|-----------------|------------|-------|
| Master password | No | No | User enters each session |
| Derived keys | No | Yes | Calculated from password |
| Decrypted documents | No | Yes (on-demand) | Decrypted for search, discarded |
| BM25 index | No | Yes (built on candidates) | Rebuilt for each query |

**CRITICAL:** No unencrypted data is EVER written to client disk. All decryption happens in memory.

### Portability

**Can I move to a different agent?** YES

1. New agent connects to server
2. Downloads ALL encrypted data (documents, embeddings)
3. User enters master password
4. Agent decrypts everything into memory
5. Full memory access restored

**All persistent data lives on the server (encrypted).** The client is stateless - you only need your master password.

### Security Guarantees

| Threat | Mitigation |
|--------|------------|
| Server reads plaintext | All data encrypted before upload |
| Server infers content from embeddings | Embeddings encrypted |
| Server infers content from blind indices | One-way hash, no key stored on server |
| Network interception | mTLS for all communication |
| Client disk compromise | No plaintext ever written to disk |
| Server compromise | Attacker gets only ciphertext |

---

## Part 3: Cryptographic Architecture

### 3.1 Key Derivation

```
Master Password (user-provided)
        ↓
    Argon2id KDF
        ↓
┌─────────────────────────────┐
│ Master Key (256-bit)         │
│ • Derived from Master PW      │
│ • Salted with machine ID      │
│ • Stored in OS Keychain       │
└─────────────────────────────┘
        ↓
    HKDF (HMAC-based Key Derivation)
        ↓
┌───────────────┬───────────────┐
│ Data Key      │ Blind Key     │
│ (256-bit)     │ (256-bit)     │
│ • AES-GCM      │ • HMAC-SHA256  │
│ • Encryption   │ • Blind Indices│
└───────────────┴───────────────┘
```

**Key Properties:**
- **Argon2id:** Memory-hard KDF, prevents brute force
- **HKDF:** Deterministic derivation of two keys from one master
- **OS Keychain:** Master key never stored in plaintext
- **Per-Device Salt:** Each device has unique salt (device-specific keys)

### 3.2 Encryption

**Algorithm:** AES-GCM (Galois/Counter Mode)

**Parameters:**
- Key size: 256 bits
- Nonce size: 96 bits (12 bytes)
- Tag size: 128 bits (16 bytes)

**Format:**
```
┌────────────────────────────────────────────────────┐
│ nonce (12 bytes) │ ciphertext (variable) │ tag (16 bytes) │
└────────────────────────────────────────────────────┘
```

**Storage:** Store `nonce || ciphertext || tag` as a single blob.

### 3.3 Blind Indices

**Purpose:** Enable exact-match queries on encrypted data (emails, UUIDs, IDs) without revealing the plaintext to the server.

**Algorithm:** HMAC-SHA256

```python
import hmac
import hashlib

def generate_blind_index(entity: str, blind_key: bytes) -> str:
    """
    Generate a blind HMAC hash for an entity.

    Args:
        entity: The plaintext entity (email, UUID, API key, etc.)
        blind_key: 256-bit key derived from master password

    Returns:
        Hex-encoded HMAC-SHA256 hash
    """
    return hmac.new(
        blind_key,
        entity.encode(),
        hashlib.sha256
    ).hexdigest()
```

**Properties:**
- One-way function (can't reverse hash to get entity)
- Keyed (server can't compute without blind key)
- Deterministic (same entity always produces same hash)

---

## Part 4: Multi-Variant Blind Index Generation

### 4.1 Overview

**v0.2 Limitation:** Single blind index per entity (exact match only)
- `aws-api-key` → `hash("aws-api-key")`
- Query: "aws api key" → NO MATCH (separator differs)

**v0.5 Solution:** Generate multiple blind indices per entity
- `aws-api-key` → `hash("aws-api-key")`, `hash("aws-api_key")`, `hash("AWS-API-KEY")`, etc.
- Query: "aws api key" → MATCHES `hash("aws_api_key")`

### 4.2 Fast Path: Regex-Based Variants

**Entities:** Well-defined patterns (emails, UUIDs, codes)

**Variants Generated:**

| Entity Type | Variants | Example |
|-------------|----------|---------|
| **Email** | Lowercase, local-part, domain | `user@example.com` → `user@example.com`, `user`, `example.com` |
| **UUID** | Full, prefix (8 chars), suffix (8 chars) | `0a1b2c3d-4e5f-6789-90ab-cdef12345` → `0a1b2c3d`, `cdef12345` |
| **API Key** | Full, prefix (8 chars), service name | `sk-proj-abc123` → `sk-proj-abc123`, `sk-proj`, `abc123` |
| **Code Path** | Full, components, separators | `memory.search.query` → `memory.search.query`, `memory/search/query` |

**Implementation:**

```python
import re
import hmac
import hashlib
from typing import List, Set

def generate_regex_variants(entity: str) -> Set[str]:
    """
    Generate multi-variant blind indices using regex patterns.

    Fast path: ~10-30ms per memory
    """
    blind_indices = set()

    # Email variants
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if re.match(email_pattern, entity):
        # Full email (lowercase)
        blind_indices.add(entity.lower())

        # Local part (before @)
        local_part = entity.split('@')[0]
        blind_indices.add(local_part.lower())

        # Domain (after @)
        domain = entity.split('@')[1]
        blind_indices.add(domain.lower())

        return blind_indices

    # UUID variants
    uuid_pattern = r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
    if re.match(uuid_pattern, entity):
        # Full UUID (lowercase)
        blind_indices.add(entity.lower())

        # Prefix (first 8 chars)
        blind_indices.add(entity[:8].lower())

        # Suffix (last 8 chars)
        blind_indices.add(entity[-8:].lower())

        return blind_indices

    # API Key / Code Path variants
    # Split by common separators: -, _, /, .
    parts = re.split(r'[-_./]', entity)

    # Full entity (lowercase)
    blind_indices.add(entity.lower())

    # Generate prefix variants
    for i in range(1, min(len(parts), 3)):
        blind_indices.add('-'.join(parts[:i]).lower())

    # Generate suffix variants
    for i in range(len(parts)-1, max(len(parts)-3, 1), -1):
        blind_indices.add('-'.join(parts[i:]).lower())

    return blind_indices
```

**Performance:**
- Time: ~10-30ms per memory (negligible for writes)
- Storage: ~20-30 blind indices per memory (2-3x v0.2)

### 4.3 Smart Path: LLM-Based Variants

**Purpose:** Handle context-aware, complex, or domain-specific entities that regex can't capture.

**When to Use:**
- Project names: "Photo Backup Tool" → "photo backup", "backup tool"
- Custom codes: "ERR-503" → "rate limit", "service unavailable"
- Domain-specific terms: "prod deployment" → "production", "prod-env"

**LLM Prompt:**

```
You are an entity extraction and variant generation specialist. Extract 5-10 high-value
entities from the following memory that should be searchable by exact match.

For each entity, generate 3-5 search variants that a user might reasonably query:

Examples:
- "Photo Backup Tool" → "photo backup", "backup tool", "photo sync", "backup automation"
- "ERR-503 Service Unavailable" → "err-503", "503 error", "service unavailable", "rate limit"

Output format:
{
  "entities": [
    {
      "original": "Photo Backup Tool",
      "type": "project_name",
      "variants": ["photo backup", "backup tool", "photo sync", "backup automation"]
    }
  ]
}
```

**Implementation:**

```python
import json

def generate_llm_variants(memory_text: str, llm_client) -> Set[str]:
    """
    Generate multi-variant blind indices using LLM.

    Smart path: ~250-550ms per memory (includes LLM call)

    Args:
        memory_text: The plaintext memory content
        llm_client: Client for the agent's LLM (already available)

    Returns:
        Set of blind index strings
    """
    # Call LLM (uses the same LLM the agent uses)
    response = llm_client.complete(
        prompt=LLM_VARIANT_PROMPT,
        context=memory_text
    )

    # Parse LLM response
    extracted = json.loads(response)

    # Generate blind indices for all variants
    blind_indices = set()

    for entity_data in extracted.get('entities', []):
        # Original entity
        blind_indices.add(entity_data['original'].lower())

        # Variants
        for variant in entity_data.get('variants', []):
            blind_indices.add(variant.lower())

    return blind_indices
```

**Performance:**
- Time: ~250-550ms per memory (acceptable for writes)
- Token cost: ~50-100 tokens per memory (negligible)
- Coverage: Significantly better than regex-only

### 4.4 Hybrid Generation (Recommended)

```python
def generate_multi_variant_blind_indices(memory_text: str, llm_client) -> Set[str]:
    """
    Generate multi-variant blind indices using both regex and LLM.

    This is the recommended approach for production.
    """
    blind_indices = set()

    # Fast path: Regex-based variants (~10-30ms)
    regex_entities = extract_entities_regex(memory_text)
    for entity in regex_entities:
        blind_indices.update(generate_regex_variants(entity))

    # Smart path: LLM-based variants (~250-550ms)
    llm_variants = generate_llm_variants(memory_text, llm_client)
    blind_indices.update(llm_variants)

    return blind_indices
```

**Coverage:**
- **Regex path:** Covers ~80% of cases (emails, UUIDs, standard codes)
- **LLM path:** Covers ~20% of cases (context-aware, domain-specific)
- **Combined:** Near-complete coverage for practical use cases

---

## Part 5: Three-Pass Search Algorithm

### 5.1 Pass 1: Remote Vector Search (Server-Side)

**Purpose:** Retrieve candidate memories using semantic similarity and blind index exact matches.

**Client Request:**
```json
{
  "query_vector": [0.012, -0.045, ..., 0.123],  // 384-dimensional
  "blind_hashes": [
    "a7b8c9d0e1f2...",
    "3f4e5d6c7b8a...",
    "..."
  ],
  "limit": 250
}
```

**Server Processing:**
```sql
-- Vector similarity search (HNSW)
SELECT id, embedding, ciphertext, blind_indices
FROM encrypted_vault
WHERE vault_id = $1
ORDER BY embedding <=> $2  -- pgvector HNSW operator
LIMIT 250;

-- Check for blind index matches
-- (Blind index match = automatic boost)
```

**Server Response:**
```json
{
  "results": [
    {
      "id": "uuid-1",
      "ciphertext": "0xabc123...",
      "vector_distance": 0.234,
      "blind_match": true
    },
    {
      "id": "uuid-2",
      "ciphertext": "0xdef456...",
      "vector_distance": 0.456,
      "blind_match": false
    }
  ]
}
```

**Performance:**
- Time: ~100ms
- Data transferred: ~250 × (256 bytes ciphertext + 4 bytes distance)
- Network: mTLS encrypted

**Zero-Knowledge Property:**
- Server only sees: ciphertext, embeddings, blind indices
- Server never sees: plaintext, query plaintext, master key

### 5.2 Pass 2: Local Decryption + BM25 Reranking

**Purpose:** Decrypt candidates and perform keyword-based ranking.

**Processing:**
```python
# Decrypt all 250 candidates
decrypted_memories = []
for result in server_response['results']:
    plaintext = decrypt_aes_gcm(
        ciphertext=result['ciphertext'],
        key=data_key,
        nonce=extract_nonce(result)
    )
    decrypted_memories.append({
        'id': result['id'],
        'plaintext': plaintext,
        'vector_score': result['vector_distance'],
        'blind_match': result['blind_match']
    })

# BM25 on decrypted plaintext
bm25_scorer = BM25Okapi([tokenize(m['plaintext']) for m in decrypted_memories])
query_tokens = tokenize(query)
bm25_scores = bm25_scorer.get_scores(query_tokens)

# RRF Fusion
K = 60  # RRF constant
rrf_results = []
for i, memory in enumerate(decrypted_memories):
    # Vector rank (1-indexed)
    vector_rank = i + 1

    # BM25 rank (1-indexed)
    bm25_rank = bm25_scores[i] + 1  # Convert score to rank

    # RRF score
    rrf_score = 1 / (K + vector_rank) + 1 / (K + bm25_rank)

    rrf_results.append({
        'id': memory['id'],
        'score': rrf_score,
        'plaintext': memory['plaintext']
    })

# Sort and return top 50
rrf_results.sort(key=lambda x: x['score'], reverse=True)
top_50 = rrf_results[:50]
```

**Performance:**
- Time: ~500ms (decryption + BM25 + RRF)
- Memory: All operations in RAM (no disk I/O)

**Zero-Knowledge Property:**
- Decryption happens locally using Data Key
- BM25 operates on plaintext (available only after decryption)
- Server sees none of this

### 5.3 Pass 3: LLM Reranking

**Purpose:** Re-rank top 50 candidates using LLM intelligence and query understanding.

**LLM Prompt:**

```
You are a search result reranker. Given a user query and search results,
reorder them by relevance and select the top 5 most relevant.

Query: {query}

Search Results:
{results_with_snippets}

Instructions:
1. Understand the user's intent
2. Consider semantic relevance, keyword matches, and context
3. Identify redundant or near-duplicate results
4. Return the top 5 most relevant, diverse results

Output format:
{
  "results": [
    {"id": "uuid-1", "reason": "Direct match with specific details"},
    {"id": "uuid-2", "reason": "Semantic match with context"}
  ]
}
```

**Implementation:**

```python
def llm_rerank(query: str, top_50_candidates, llm_client) -> List[dict]:
    """
    Rerank search results using LLM.

    Args:
        query: User's search query
        top_50_candidates: Top 50 results from Pass 2
        llm_client: Client for the agent's LLM

    Returns:
        Top 5 reranked results with explanations
    """
    # Prepare results for LLM
    results_text = format_results_for_llm(top_50_candidates)

    # Call LLM (uses the same LLM the agent uses)
    response = llm_client.complete(
        prompt=LLM_RERANK_PROMPT.format(
            query=query,
            results=results_text
        ),
        max_tokens=500
    )

    # Parse LLM response
    reranked = json.loads(response)

    return reranked.get('results', [])
```

**Performance:**
- Time: ~500ms (LLM call + processing)
- Token cost: ~100-200 tokens per search

**Zero-Knowledge Property:**
- LLM operates locally on decrypted candidates
- LLM is the same one the agent uses (already available)
- Server sees none of this

### 5.4 Complete Search Flow Summary

```
Total Search Time: ~1.1 seconds (100ms + 500ms + 500ms)

┌─────────────────────────────────────────────────────────────┐
│ PASS 1: Remote Semantic Search (100ms)                        │
│ • Vector search: HNSW KNN on embeddings                      │
│ • Blind index check: Exact matches                           │
│ • Returns: Top 250 candidates (ciphertext only)               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ PASS 2: Local Decryption + BM25 (500ms)                      │
│ • Decrypt 250 candidates locally                               │
│ • BM25 keyword search on plaintext                            │
│ • RRF fusion: vector + BM25 scores                            │
│ • Returns: Top 50 candidates (plaintext)                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ PASS 3: LLM Reranking (500ms)                                │
│ • Send query + top 50 candidates to LLM                        │
│ • LLM reranks based on understanding and relevance            │
│ • Returns: Top 5 results with explanations                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Part 6: Database Schema

### 6.1 Encrypted Vault Table

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE encrypted_vault (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Routing
    vault_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,

    -- Encrypted Data (Zero-Knowledge)
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL,  -- 12 bytes
    tag BYTEA NOT NULL,     -- 16 bytes (AES-GCM auth tag)

    -- Search Indexes (Zero-Knowledge)
    embedding vector(384) NOT NULL,  -- all-MiniLM-L6-v2
    blind_indices TEXT[] NOT NULL,  -- Array of HMAC-SHA256 hashes

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT vault_agent_check CHECK (vault_id ~ '^[a-zA-Z0-9_-]+$')
);

-- Vector Index (HNSW)
CREATE INDEX idx_vault_embedding ON encrypted_vault
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- GIN Index for Blind Indices
CREATE INDEX idx_vault_blind_indices ON encrypted_vault
USING gin (blind_indices gin__int_ops);

-- Routing Indexes
CREATE INDEX idx_vault_vault ON encrypted_vault(vault_id);
CREATE INDEX idx_vault_agent ON encrypted_vault(agent_id);
CREATE INDEX idx_vault_created ON encrypted_vault(created_at DESC);
```

### 6.2 Index Estimation

**For 10,000 memories (per user):**

| Component | Size per Memory | Total Size |
|-----------|------------------|------------|
| **Ciphertext** | ~500 bytes | 5 MB |
| **Embedding** | 1.5 KB (384×4 bytes) | 15 MB |
| **Blind Indices** | ~100 bytes (20 indices × 5 bytes) | 1 MB |
| **Metadata** | ~100 bytes | 1 MB |
| **Total** | ~2.2 KB | 22 MB per user |

**Scalability:**
- Single server: 100K users @ 10K memories = 2.2 TB
- With sharding: Multi-tenant, distribute across servers

---

## Part 7: API Specification

### 7.1 Save Memory (Ingestion)

**Endpoint:** `POST /v1/vault/memory`

**Request:**
```json
{
  "vault_id": "derived-from-api-key",
  "agent_id": "openclaw-main",
  "plaintext": "## 2026-02-18\n\n### Email: API Key Rotation...",
  "metadata": {
    "source": "openclaw",
    "timestamp": "2026-02-18T10:23:45Z",
    "memory_type": "email"
  }
}
```

**Client Processing (Before API Call):**
1. Extract entities (regex + LLM)
2. Generate multi-variant blind indices
3. Generate embedding (ONNX all-MiniLM-L6-v2)
4. Encrypt plaintext (AES-GCM)
5. Upload ciphertext + embedding + blind indices

**Server Processing:**
1. Validate vault_id and agent_id
2. Store in database (ciphertext, embedding, blind_indices)
3. Return memory ID

**Response:**
```json
{
  "id": "uuid-123",
  "created_at": "2026-02-18T10:23:45Z",
  "status": "saved"
}
```

### 7.2 Search Memory (Retrieval)

**Endpoint:** `POST /v1/vault/search`

**Request:**
```json
{
  "vault_id": "derived-from-api-key",
  "query": "What did Sarah say about the API key?",
  "query_vector": [0.012, -0.045, ...],
  "blind_hashes": ["hash1", "hash2", ...],
  "limit": 250
}
```

**Server Processing (Pass 1):**
1. HNSW KNN search on query_vector
2. Check blind_hashes for exact matches
3. Return top 250 candidates

**Response:**
```json
{
  "results": [
    {
      "id": "uuid-1",
      "ciphertext": "0xabc123...",
      "score": 0.234,
      "blind_match": false
    }
  ]
}
```

**Client Processing (Pass 2 + 3):**
1. Decrypt all 250 results
2. BM25 + RRF fusion → top 50
3. LLM rerank → top 5

### 7.3 Export Memory (Data Portability)

**Endpoint:** `POST /v1/vault/export`

**Request:**
```json
{
  "vault_id": "derived-from-api-key",
  "format": "markdown"
}
```

**Client Processing:**
1. Request all memories (paginated)
2. Decrypt locally
3. Format as Markdown

**Response:**
```json
{
  "memories": [
    {
      "id": "uuid-1",
      "plaintext": "## 2026-02-18\n\n...",
      "created_at": "2026-02-18T10:23:45Z"
    }
  ]
}
```

**Anti-Vendor-Lock-In:** Users can export all memories in plaintext at any time.

---

## Part 8: Client SDK Design

### 8.1 OpenClaw Skill (npm Package)

**Package:** `@totalreclaw/openclaw-skill`

**Installation:**
```bash
npm install -g @totalreclaw/openclaw-skill
openclaw-skill configure --api-token YOUR_TOKEN
```

**Usage:**
```python
# In OpenClaw skill configuration
tools:
  - name: memory_save
    description: Save a memory to TotalReclaw vault
  - name: memory_search
    description: Search memories in TotalReclaw vault

# Both tools override default OpenClaw memory commands
```

### 8.2 MCP Server (Universal Compatibility)

**Package:** `@totalreclaw/mcp-server`

**Installation:**
```bash
npm install -g @totalreclaw/mcp-server
totalreclaw-mcp configure --api-token YOUR_TOKEN
```

**Configuration (Claude Desktop):**
```json
{
  "mcpServers": {
    "totalreclaw": {
      "command": "totalreclaw-mcp",
      "args": ["--api-token", "YOUR_TOKEN"]
    }
  }
}
```

**Usage:**
- Works with Claude Desktop, ChatGPT Desktop, any MCP-compatible agent
- Exposes same tools as OpenClaw skill
- Universal memory across all agents

### 8.3 REST API (Custom Integrations)

**Base URL:** `https://api.totalreclaw.ai/v1`

**Authentication:** Bearer token (derived from API key)

**Endpoints:**
- `POST /vault/memory` — Save memory
- `POST /vault/search` — Search memories
- `GET /vault/export` — Export memories
- `DELETE /vault/{id}` — Delete memory

---

## Part 9: Performance Considerations

### 9.1 Latency Breakdown

| Component | Time | Notes |
|-----------|------|-------|
| **Pass 1: Remote Search** | ~100ms | HNSW KNN + blind index check |
| **Pass 2: Decrypt + BM25** | ~500ms | 250 decrypts + BM25 + RRF |
| **Pass 3: LLM Rerank** | ~500ms | LLM call + processing |
| **Total** | **~1.1s** | Acceptable for memory search |

### 9.2 Optimization Strategies

**Client-Side:**
- **Parallel Processing:** Decrypt multiple memories concurrently
- **Caching:** Cache query embeddings and LLM reranker results
- **Adaptive Pass 2:** Reduce candidate pool if query is simple

**Server-Side:**
- **Connection Pooling:** Reuse database connections
- **Materialized Views:** Pre-filter by vault_id, agent_id
- **HNSW Tuning:** Optimize `m` and `ef_construction` parameters

### 9.3 Scalability

**Single-Instance Capacity:**
- 100K users × 10K memories = 1B memories
- 2.2 TB storage (excluding indexes)
- Vector index: ~150 GB (HNSW with m=16)

**Horizontal Scaling:**
- **Sharding:** Distribute by vault_id across multiple servers
- **Read Replicas:** Vector search on read replicas
- **Connection Router:** Route queries to appropriate shard

---

## Part 10: Security Considerations

### 10.1 Zero-Knowledge Properties

**Server Never Sees:**
- Plaintext memories
- Master password or derived keys
- Query plaintext (only query embeddings and blind hashes)

**Server Stores:**
- Ciphertext (encrypted memories)
- Embeddings (vectors of plaintext, but not reversible)
- Blind indices (hashes of entities, not reversible without key)

**Compromise Scenario:**
- If server is breached:
  - Attacker gets ciphertext (useless without key)
  - Attacker gets embeddings (reverses to approximate plaintext, but low quality)
  - Attacker gets blind indices (useless without blind key)
- **User data remains safe** without master password

### 10.2 Key Management Best Practices

**Master Password:**
- Minimum 12 characters, recommended 20+
- Must be entered by user (never stored)
- Used to derive Data Key and Blind Key
- Stored in OS Keychain for convenience

**Device Trust:**
- Each device has unique salt (device-specific keys)
- Compromised device = compromised vault access
- Mitigation: Revoke device, regenerate keys

**Recovery Phrase:**
- 24-word BIP-39 phrase (separate from master password)
- Can recover Data Key if master password is lost
- Must be stored securely (written down, never stored digitally)

### 10.3 mTLS Configuration

**Client Certificates:**
- Each client device has unique certificate
- Certificate pinning prevents MITM attacks
- Certificates stored in OS Keychain

**Server Certificate:**
- Wildcard certificate for *.api.totalreclaw.ai
- Automatic rotation via Let's Encrypt

---

## Part 11: Migration Path from v0.2

### 11.1 What Changed

| Component | v0.2 | v0.5 |
|-----------|------|------|
| **Search Passes** | 2 | 3 |
| **Blind Indices** | Single-variant | Multi-variant |
| **Variant Gen** | Regex-only | Regex + LLM |
| **LLM Integration** | None | Reranking + variant gen |
| **Latency Target** | <1s p95 | <2s p95 |

### 11.2 Breaking Changes

**None.** v0.5 is backward compatible with v0.2:
- Existing API contracts unchanged
- Existing encrypted data unchanged
- New features are additive

**Migration Path:**
1. Deploy v0.5 server (supports both v0.2 and v0.5 clients)
2. Update client SDKs to v0.5
3. Users opt-in to LLM features (default: disabled for compatibility)
4. Gradual rollout of enhanced features

### 11.3 Feature Flags

```yaml
features:
  multi_variant_blind_indices:
    enabled: true
    mode: "hybrid"  # regex, llm, or hybrid

  llm_reranking:
    enabled: true
    require_opt_in: false  # default on for new users

  llm_variant_generation:
    enabled: true
    require_opt_in: false  # default on for new users
```

---

## Part 12: Open Questions

1. **LLM Selection for Reranking:**
   - Use the same model the agent uses (variable)
   - Or require a specific model for consistency?
   - Trade-off: Flexibility vs. predictability

2. **Blind Index Storage Optimization:**
   - 2-3x storage increase is acceptable?
   - Deduplicate blind indices across memories?
   - Compress blind index storage?

3. **Candidate Pool Size:**
   - Fixed at 250 or adaptive based on query complexity?
   - Larger pool = better recall but slower Pass 2

4. **LLM Reranking Caching:**
   - Cache reranked results for common queries?
   - Cache invalidation strategy?

5. **Query Expansion with LLM:**
   - Use LLM to expand query with related terms before search?
   - Example: "deployment" → "deployment, docker, container, production"

---

## Part 13: Success Metrics

### 13.1 Testbed Success Criteria

| Metric | v0.2 Target | v0.5 Target |
|--------|-----------|-----------|
| **F1 Score (vs OpenClaw)** | Within 10% | Within 5% |
| **F1 Score (vs QMD)** | Within 15% | Within 10% |
| **MRR** | >0.70 | >0.75 |
| **Latency p95** | <1.5s | <2s |

### 13.2 Production Success Criteria

| Metric | 6-Month Target | 12-Month Target |
|--------|---------------|----------------|
| **Weekly Active Users** | 1,000 | 10,000 |
| **Search Latency p50** | <800ms | <600ms |
| **Search Latency p95** | <1.5s | <1s |
| **Search Success Rate** | >90% | >95% |
| **Export Rate** | <5% monthly | <3% monthly |

---

## Part 14: OpenClaw Compatibility

### 14.1 File Structure Compatibility

**Requirement:** TotalReclaw must be fully compatible with OpenClaw's memory file structure for seamless import/export.

**OpenClaw's Memory Structure:**
```
~/.openclaw/workspace/
├── MEMORY.md              # Curated long-term memory
└── memory/
    ├── 2026-02-18.md      # Daily log (append-only)
    ├── 2026-02-17.md
    └── 2026-02-16.md
```

### 14.2 Import/Export API

#### Export Endpoint

**Endpoint:** `POST /v1/vault/export`

**Request:**
```json
{
  "vault_id": "derived-from-api-key",
  "format": "openclaw"
}
```

**Response:**
```json
{
  "format": "openclaw",
  "files": {
    "MEMORY.md": "## Team\n\nBackend lead: Sarah...",
    "memory/2026-02-18.md": "## 10:23 AM - Project Discussion\n...",
    "memory/2026-02-17.md": "## 9:15 AM - Standup\n..."
  }
}
```

**Client Processing (After Decryption):**
1. Receive encrypted memories from server
2. Decrypt locally
3. Reconstruct file structure (MEMORY.md, memory/*.md)
4. Write to local workspace

#### Import Endpoint

**Endpoint:** `POST /v1/vault/import/openclaw`

**Request:**
```json
{
  "format": "openclaw",
  "files": {
    "MEMORY.md": "content...",
    "memory/2026-02-18.md": "content..."
  }
}
```

**Client Processing (Before Upload):**
1. Read OpenClaw memory files from workspace
2. Parse Markdown structure
3. Extract entities for blind indexing
4. Generate embeddings locally
5. Encrypt each memory
6. Upload to server

### 14.3 Format Specification

**MEMORY.md Format:**
```markdown
# MEMORY.md

## Team
- Backend lead: Sarah (sarahr@example.com)
- Frontend lead: Mike (miket@example.com)

## API Configuration
- Base URL: https://api.example.com/v1
- Authentication: Bearer token
- Rate limit: 100 req/min

## Projects
- Photo Backup Tool
- Deployment Automation
```

**memory/YYYY-MM-DD.md Format:**
```markdown
# 2026-02-18

## 10:23 AM - Project Structure Discussion
User: We should use /src/components for React components.
Assistant: Agreed. I'll update the project structure.

## 2:45 PM - API Integration
User: The API is returning 429 errors.
Assistant: Let's implement exponential backoff.
```

### 14.4 Compatibility Validation

**Test Cases:**
1. **Import OpenClaw → TotalReclaw**
   - Parse existing OpenClaw files
   - Validate search accuracy F1 ≥ 0.90

2. **Export TotalReclaw → OpenClaw**
   - Generate valid OpenClaw format
   - Validate OpenClaw can index exported files

3. **Round-Trip Test**
   - Import → Export → Import
   - Validate content fidelity F1 ≥ 0.95

**Success Criteria:**
- 100% of exported files are valid Markdown
- OpenClaw can index 100% of exported files
- Search accuracy maintained after round-trip

---

## Part 15: References

### Design Influences

1. **QMD (Tobi Lütke)**
   - Local-first hybrid + reranking
   - Multi-modal search approach
   - https://github.com/tobi/qmd

2. **OpenClaw Memory Documentation**
   - Hybrid search with weighted merge
   - MMR re-ranking
   - Temporal decay
   - https://docs.openclaw.ai/concepts/memory

3. **Reciprocal Rank Fusion**
   - Cormack et al. (2009)
   - Combines multiple ranking systems
   - Formula: `1 / (k + rank1) + 1 / (k + rank2)`

4. **Password Manager Architecture**
   - 1Password, LastPass
   - E2EE with sync
   - Recovery phrase model

### Technical Specifications

- **all-MiniLM-L6-v2:** Sentence transformer model
- **Argon2id:** Password-based key derivation
- **AES-GCM:** Authenticated encryption
- **HMAC-SHA256:** Blind index generation
- **RRF:** Reciprocal Rank Fusion

---

**Document Control:**

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.5.0 | 2026-02-18 | Enhanced E2EE with LLM reranking and multi-variant blind indices | TotalReclaw Team |
