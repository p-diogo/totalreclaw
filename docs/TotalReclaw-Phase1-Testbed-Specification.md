# TotalReclaw Phase 1: Technical Testbed Specification

**Version:** 1.0.0
**Status:** Draft
**Last Updated:** February 18, 2026

**Purpose:** Validate the hybrid search accuracy of TotalReclaw's zero-knowledge E2EE approach against state-of-the-art plaintext baselines before full implementation.

---

## Executive Summary

This document specifies a minimal testbed to benchmark TotalReclaw's two-pass hybrid search (remote semantic → local BM25 rerank → RRF fusion) against current state-of-the-art plaintext search systems used by OpenClaw users.

**The Core Question:** Can we achieve competitive search accuracy while maintaining zero-knowledge encryption?

**Success Criteria:**
- **Accuracy:** Within 5% of QMD's plaintext hybrid search
- **Latency:** <1 second p50, <1.5 seconds p95
- **Go/No-Go Decision:** If accuracy gap >15%, reconsider the E2EE architecture

---

## Part 1: State of the Art Analysis

### Current OpenClaw Memory Landscape

Based on research conducted February 18, 2026:

#### 1. OpenClaw Built-in Memory (Default Baseline)

**Source:** https://docs.openclaw.ai/concepts/memory

**Architecture:**
- **Storage:** Markdown files in workspace (`MEMORY.md`, `memory/YYYY-MM-DD.md`)
- **Index:** SQLite with sqlite-vec for vector acceleration
- **Embedding:** Requires external API (OpenAI, Gemini, Voyage) or local via node-llama-cpp
- **Search:** Hybrid (BM25 + vector) with configurable weights

**Search Algorithm:**
```
1. Retrieve candidates from both sides:
   - Vector: top (maxResults × candidateMultiplier) by cosine similarity
   - BM25: top (maxResults × candidateMultiplier) by FTS5 BM25 rank

2. Convert BM25 rank to score:
   textScore = 1 / (1 + max(0, bm25Rank))

3. Merge results:
   finalScore = vectorWeight × vectorScore + textWeight × textScore

4. Optional post-processing:
   - MMR re-ranking (diversity)
   - Temporal decay (recency boost)
```

**Default Configuration:**
- `vectorWeight`: 0.7
- `textWeight`: 0.3
- `candidateMultiplier`: 4
- Chunk size: ~400 tokens with 80-token overlap

**Strengths:**
- Familiar UX for OpenClaw users
- Optional local embeddings (no API keys)
- Mature, well-documented

**Weaknesses:**
- Requires API key for remote embeddings (cost, privacy)
- No encryption by default
- Data siloed to single machine

---

#### 2. QMD (Local-First Hybrid + Reranking)

**Source:** https://github.com/tobi/qmd, https://travis.media/blog/openclaw-memory-qmd-guide/

**Architecture:**
- **Storage:** SQLite with custom indexing
- **Embedding:** Fully local via node-llama-cpp (GGUF models from HuggingFace)
- **Search:** Three modes

**Search Modes:**
1. **`search`** (BM25 only): Fast, lightweight
2. **`vsearch`** (semantic only): Vector embeddings
3. **`query`** (hybrid + reranking): BM25 + vector + local LLM reranking

**Hybrid + Reranking Algorithm:**
```
1. BM25 full-text search (exact keyword matches)
2. Vector semantic search (conceptual matches)
3. Local LLM reranking with query expansion
4. Merge and return top results
```

**Hardware Requirements:**
- 4GB RAM: BM25 only
- 8GB+ RAM: Full semantic + reranking

**Embedding Model:**
- Auto-downloaded GGUF model (~1.28GB for reranker)
- Runs via Bun + node-llama-cpp

**Strengths:**
- Fully local (no API keys, no cloud calls)
- State-of-the-art reranking
- Comparable to paid options (Mem0)
- Free and open-source

**Weaknesses:**
- Higher memory requirements for full features
- First query after boot can be slow (10-30s model loading)
- Experimental software

**Claimed Accuracy:** According to Supermemory comparison (https://x.com/julianweisser/status/2023635504638685344), QMD achieves significantly better accuracy than other OpenClaw memory options.

---

#### 3. Mem0 (Cloud-Hosted Baseline)

**Source:** https://mem0.ai, https://mem0.ai/blog/mem0-memory-for-openclaw

**Architecture:**
- **Storage:** Cloud-hosted (vendor-controlled)
- **Search:** Proprietary (likely vector + custom ranking)
- **Privacy:** Mem0 can read user memories

**Benchmark Results (Mem0 vs Others):**
According to Mem0's AI Memory Benchmark blog:
- Mem0 leads with 66.9% accuracy
- Compared against: OpenAI Memory, LangMem, MemGPT

**Strengths:**
- Easy setup (managed service)
- Good accuracy
- Active development

**Weaknesses:**
- Not zero-knowledge (vendor can read memories)
- Paid subscription
- Data lock-in (no portable export)

---

#### 4. Supermemory (Emerging Competitor)

**Source:** https://x.com/julianweisser/status/2023635504638685344

**Claim:** "Supermemory is about 30 points higher accuracy than the other memory options tested for OpenClaw"

**Note:** This is a significant claim (30 percentage points improvement) that needs validation in our testbed.

---

## Part 2: TotalReclaw Proposed Architecture

### Two-Pass Hybrid Search with E2EE

**Source:** TotalReclaw v0.2 E2EE & Horizon specification

**Architecture:**
- **Client-Side:** Local Node (npm package / MCP server)
  - Argon2id KDF → Data Key + Blind Key
  - ONNX all-MiniLM-L6-v2 (INT8) for local vectorization
  - AES-GCM encryption
  - HMAC-SHA256 blind indices
  - Local BM25 reranking

- **Server-Side:** Encrypted only (zero-knowledge)
  - PostgreSQL + pgvector
  - Stores: ciphertext, embeddings, blind indices
  - Server never sees plaintext

**Search Algorithm:**
```
PASS 1 (Remote, ~100ms):
  1. Client generates query vector using ONNX all-MiniLM-L6-v2
  2. Client generates blind indices for query entities
  3. Send to server: {query_vector, blind_hashes, limit: 250}
  4. Server performs HNSW KNN search on encrypted embeddings
  5. Server returns top 250 matches (ciphertext only)

PASS 2 (Local, ~500ms):
  1. Client receives up to 250 ciphertexts
  2. Client decrypts all using Data Key
  3. Client runs BM25 keyword search on plaintext
  4. Client applies RRF fusion:
     score = 1 / (60 + vector_rank) + 1 / (60 + bm25_rank)
  5. Client returns top 3-5 results to agent
```

**Key Differences from Competitors:**
- All encryption/decryption happens on client
- Server only performs vector similarity search (blind to content)
- Local BM25 adds precision for exact matches
- Blind indices enable exact-match queries on sensitive data

**Theoretical Accuracy:**
- Should match or exceed plaintext hybrid search for:
  - Semantic queries (remote vector search is identical)
  - Exact keyword queries (local BM25 on plaintext after decryption)
- Potential accuracy loss:
  - Limited candidate pool (250 vs unlimited in plaintext)
  - No blind indices for all possible query variations
  - Single-round BM25 vs multi-stage refinement

---

## Part 3: Testbed Design

### Minimal Viable Testbed Architecture

The testbed strips away all agent complexity and focuses purely on the search algorithm:

```
┌─────────────────────────────────────────────────────────────────┐
│                    TESTBED ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Data Generator  │ -> │  Search Systems  │ -> │  Evaluator      │
│                  │    │                  │    │                  │
│  • Synthetic     │    │  • BM25-only     │    │  • Metrics       │
│    chat logs     │    │  • Vector-only   │    │  • Reports       │
│  • Technical docs│    │  • OpenClaw      │    │  • Go/No-Go      │
│  • Personal notes│    │    hybrid        │    │                  │
│                  │    │  • QMD hybrid    │    │                  │
│  • LLM interface │    │  • TotalReclaw    │    │                  │
│    for creating  │    │    E2EE          │    │                  │
│    memories      │    │                  │    │                  │
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

### Technology Stack

**Core Components:**
- **Language:** Python 3.12+
- **Database:** PostgreSQL 16 with pgvector extension
- **Embedding Model:** all-MiniLM-L6-v2 (quantized INT8 via ONNX)
- **BM25:** Rank-BM25 Python library
- **Cryptography:** cryptography.hazmat.primitives (AES-GCM, HKDF, Argon2id)
- **Framework:** FastAPI for server components

**Why Python:**
- Excellent ML/AI ecosystem (rank-bm25, transformers, sentence-transformers)
- PostgreSQL/pgvector support
- FastAPI for quick API development
- Easy to prototype and iterate

---

## Part 4: Data Generation Strategy

### Synthetic Memory Dataset

We need realistic memory data that mimics actual OpenClaw usage patterns. Three categories:

#### 1. Chat Interaction Memories (40%)
Simulated conversations between user and AI assistant, capturing:
- Project decisions and agreements
- Technical debugging sessions
- Configuration discussions
- Workflow agreements
- Error message debugging

**Example:**
```markdown
## 2026-02-18.md

### 10:23 AM - Project Structure Discussion
User: We should use /src/components for React components and /src/lib for utilities.
Assistant: Agreed. I'll update the project structure. We'll use TypeScript strict mode.
User: Also, let's name files using kebab-case: UserProfileCard.tsx
Assistant: Noted. I'll create the component with proper TypeScript types.

### 2:45 PM - API Integration
User: The API is returning 429 errors. Rate limit is 100 requests per minute.
Assistant: We need to implement exponential backoff with jitter. I'll add the rate-limiting middleware.
User: The endpoint is https://api.example.com/v1/graphql
Assistant: Got it. I'll configure Apollo Client with the rate limit plugin.
```

#### 2. Technical Documentation (30%)
Reference information that would go in MEMORY.md:
- API endpoints and authentication
- Server configurations
- Network setups
- Code conventions
- Deployment procedures

**Example:**
```markdown
## MEMORY.md

### API Configuration
- Base URL: https://api.example.com/v1
- Authentication: Bearer token (retrieved from AWS Secrets Manager)
- Rate limit: 100 req/min (429 response with Retry-After header)
- Timeout: 30 seconds

### Database Schema
- Users table: id (UUID), email (VARCHAR), created_at (TIMESTAMP)
- Posts table: id (UUID), user_id (FK), title (VARCHAR), body (TEXT)

### Deployment
- Production: us-east-1
- Staging: us-west-2
- CI/CD: GitHub Actions
- Container registry: ECR
```

#### 3. Personal Notes & Context (30%)
Facts about the user's preferences, environment, and context:
- Hardware setup
- Work schedule
- Team member information
- Personal preferences
- Recurring tasks

**Example:**
```markdown
## 2026-02-15.md

### Work Context
- Standup at 10:00 AM EST with the frontend team
- 1:1 with manager on Thursdays at 3:00 PM
- Focus hours: 9 AM - 12 PM (no meetings)

### Environment
- Local dev server: http://localhost:3000
- Database: PostgreSQL 15 on port 5432
- Redis cache on port 6379

### Team
- Backend lead: Sarah (sarahr@example.com)
- Frontend lead: Mike (miket@example.com)
- Product manager: Jen (jenl@example.com)
```

### Dataset Size

**Initial Test:** 500 memory chunks
- Chat interactions: 200 chunks
- Technical docs: 150 chunks
- Personal notes: 150 chunks

**Expanded Test:** 5,000 memory chunks (if initial results are promising)
- Scales all categories proportionally

### LLM-Based Data Generation

Instead of manually writing memories, use an LLM to generate realistic synthetic data:

**Prompt Template:**
```
You are simulating an OpenClaw user's memory files. Generate 50 realistic memory
entries from chat conversations about software development. Include:

1. Technical discussions (APIs, databases, debugging)
2. Project decisions and agreements
3. Code snippets and configuration examples
4. Error messages and solutions

Format as Markdown with timestamps. Include specific IDs, error codes, and technical
terms that would require exact matching.

Output only the Markdown content, no explanations.
```

**Generation Pipeline:**
1. Use Claude/ChatGPT API to generate bulk memories
2. Parse and clean the output
3. Split into chunks (~400 tokens each)
4. Store in test database

---

## Part 5: Search System Implementations

### Baseline 1: BM25-Only (Plaintext)

**Purpose:** Establish keyword search baseline (what OpenClaw had before embeddings)

**Implementation:**
```python
from rank_bm25 import BM25Okapi
from tokenize import word_tokenize

def bm25_only_search(query: str, documents: List[str], top_k: int = 5):
    """
    Pure BM25 keyword search on plaintext documents.
    """
    tokenized_corpus = [word_tokenize(doc.lower()) for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)

    tokenized_query = word_tokenize(query.lower())
    scores = bm25.get_scores(tokenized_query)

    # Get top-k indices
    top_indices = np.argsort(scores)[::-1][:top_k]

    return [(idx, scores[idx]) for idx in top_indices]
```

**Expected Performance:**
- Excellent for exact keyword matches (IDs, error codes, function names)
- Poor for semantic queries (different wording, concepts)
- Fast (<50ms typically)

---

### Baseline 2: Vector-Only (Plaintext)

**Purpose:** Establish semantic search baseline

**Implementation:**
```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

def vector_only_search(query: str, documents: List[str], embeddings: np.ndarray, top_k: int = 5):
    """
    Pure vector semantic search on plaintext documents.
    """
    model = SentenceTransformer('all-MiniLM-L6-v2')
    query_embedding = model.encode([query])[0]

    # Cosine similarity
    similarities = cosine_similarity([query_embedding], embeddings)[0]

    # Get top-k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]

    return [(idx, similarities[idx]) for idx in top_indices]
```

**Expected Performance:**
- Excellent for semantic queries (concepts, paraphrases)
- Poor for exact matches (IDs, error codes)
- Moderate latency (~100-200ms)

---

### Baseline 3: OpenClaw Hybrid (Plaintext)

**Purpose:** Replicate OpenClaw's current default search algorithm

**Implementation:**
```python
def openclaw_hybrid_search(query: str, documents: List[str],
                            embeddings: np.ndarray, top_k: int = 5,
                            vector_weight: float = 0.7,
                            text_weight: float = 0.3,
                            candidate_multiplier: int = 4):
    """
    OpenClaw-style hybrid search: weighted merge of vector and BM25 scores.
    """
    # Pass 1: Vector search
    model = SentenceTransformer('all-MiniLM-L6-v2')
    query_embedding = model.encode([query])[0]
    vector_similarities = cosine_similarity([query_embedding], embeddings)[0]

    # Pass 2: BM25 search
    tokenized_corpus = [word_tokenize(doc.lower()) for doc in documents]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = word_tokenize(query.lower())
    bm25_scores = bm25.get_scores(tokenized_query)

    # Convert BM25 rank to score (OpenClaw's formula)
    bm25_normalized = 1 / (1 + np.maximum(0, bm25_scores))

    # Merge results
    candidate_count = top_k * candidate_multiplier
    vector_candidates = set(np.argsort(vector_similarities)[::-1][:candidate_count])
    bm25_candidates = set(np.argsort(bm25_scores)[::-1][:candidate_count])

    # Union and weighted score
    all_candidates = vector_candidates | bm25_candidates
    results = []

    for idx in all_candidates:
        vector_score = vector_similarities[idx]
        text_score = bm25_normalized[idx]
        final_score = vector_weight * vector_score + text_weight * text_score
        results.append((idx, final_score))

    # Sort by final score and return top-k
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]
```

**Expected Performance:**
- Good for both semantic and keyword queries
- Balanced performance
- The current standard for OpenClaw users

---

### Baseline 4: QMD-Style Hybrid (Plaintext)

**Purpose:** Replicate QMD's full pipeline with LLM reranking

**Implementation:**
```python
def qmd_hybrid_search(query: str, documents: List[str],
                      embeddings: np.ndarray, top_k: int = 5):
    """
    QMD-style hybrid: BM25 + vector + LLM reranking.
    """
    # Pass 1: BM25 + Vector (similar to OpenClaw)
    candidates = openclaw_hybrid_search(
        query, documents, embeddings,
        top_k=top_k * 4,  # Larger candidate pool
        vector_weight=0.5, text_weight=0.5
    )

    # Pass 2: LLM reranking (simplified for testbed)
    # In production, QMD uses local GGUF model
    # For testbed, we can use OpenAI API or skip this step

    # Simplified: boost results that contain query terms
    reranked = []
    query_lower = query.lower()
    query_terms = set(word_tokenize(query_lower))

    for idx, score in candidates:
        doc_lower = documents[idx].lower()
        # Boost if document contains query terms
        term_match = any(term in doc_lower for term in query_terms)
        reranked_score = score * 1.5 if term_match else score
        reranked.append((idx, reranked_score))

    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked[:top_k]
```

**Expected Performance:**
- Best accuracy among plaintext baselines
- Higher latency due to reranking
- Current state-of-the-art for local search

---

### System Under Test: TotalReclaw E2EE

**Purpose:** Implement the proposed two-pass E2EE search

**Implementation:**
```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from argon2 import PasswordHasher

class TotalReclawE2EE:
    def __init__(self, master_password: str):
        # Derive keys from master password
        self.kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=64,  # 32 bytes for data key + 32 bytes for blind key
            salt=b'totalreclaw-salt',  # In production: use random salt
            info=b'totalreclaw-key-derivation',
        )
        derived = self.kdf.derive(master_password.encode())

        self.data_key = derived[:32]
        self.blind_key = derived[32:]

        # AES-GCM for encryption
        self.cipher = AESGCM(self.data_key)

    def encrypt_memory(self, plaintext: str, embedding: np.ndarray) -> dict:
        """
        Encrypt a memory for storage on server.
        Returns: {ciphertext, nonce, embedding, blind_indices}
        """
        # Encrypt plaintext
        nonce = os.urandom(12)
        ciphertext = self.cipher.encrypt(nonce, plaintext.encode(), b'')

        # Generate blind indices for exact-match entities
        blind_indices = self._generate_blind_indices(plaintext)

        return {
            'ciphertext': ciphertext,
            'nonce': nonce,
            'embedding': embedding,
            'blind_indices': blind_indices
        }

    def decrypt_memory(self, ciphertext: bytes, nonce: bytes) -> str:
        """
        Decrypt a memory from server.
        """
        plaintext = self.cipher.decrypt(nonce, ciphertext, b'')
        return plaintext.decode()

    def _generate_blind_indices(self, plaintext: str) -> List[str]:
        """
        Generate HMAC-SHA256 blind indices for exact-match entities.
        """
        import hmac
        import hashlib
        import re

        blind_indices = []

        # Extract high-value exact-match targets
        # Emails
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', plaintext)
        # UUIDs
        uuids = re.findall(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', plaintext)
        # API keys (pattern)
        api_keys = re.findall(r'\b[A-Za-z0-9]{32,}\b', plaintext)

        # Generate blind HMAC for each entity
        for entity in set(emails + uuids + api_keys):
            blind_hash = hmac.new(
                self.blind_key,
                entity.encode(),
                hashlib.sha256
            ).hexdigest()
            blind_indices.append(blind_hash)

        return list(set(blind_indices))

    def search(self, query: str, encrypted_memories: List[dict], top_k: int = 3):
        """
        Two-pass search: remote semantic → local BM25 rerank → RRF fusion.
        """
        # Generate query embedding
        model = SentenceTransformer('all-MiniLM-L6-v2')
        query_embedding = model.encode([query])[0]

        # Generate blind indices for query
        query_blind_indices = set(self._generate_blind_indices(query))

        # PASS 1: Remote vector search (server-side simulation)
        candidate_pool = 250  # Fixed candidate pool size

        # Calculate vector similarities
        embeddings = np.array([m['embedding'] for m in encrypted_memories])
        vector_similarities = cosine_similarity([query_embedding], embeddings)[0]

        # Check for blind index matches
        blind_matches = []
        for i, memory in enumerate(encrypted_memories):
            if any(idx in query_blind_indices for idx in memory['blind_indices']):
                blind_matches.append((i, 1.0))  # Perfect match score

        # Get top candidates by vector similarity
        top_vector_indices = np.argsort(vector_similarities)[::-1][:candidate_pool]

        # Combine blind matches with vector candidates
        candidate_indices = set(top_vector_indices) | set([m[0] for m in blind_matches])
        candidate_indices = list(candidate_indices)[:candidate_pool]

        # PASS 2: Local BM25 reranking
        # Decrypt candidates and run BM25
        decrypted_candidates = [self.decrypt_memory(
            encrypted_memories[i]['ciphertext'],
            encrypted_memories[i]['nonce']
        ) for i in candidate_indices]

        # BM25 on decrypted plaintext
        tokenized_corpus = [word_tokenize(doc.lower()) for doc in decrypted_candidates]
        bm25 = BM25Okapi(tokenized_corpus)
        tokenized_query = word_tokenize(query.lower())
        bm25_scores = bm25.get_scores(tokenized_query)

        # RRF Fusion
        rrf_results = []
        k = 60  # RRF constant

        for rank, idx in enumerate(candidate_indices):
            vector_rank = np.where(top_vector_indices == idx)[0]
            if len(vector_rank) > 0:
                vector_rank = vector_rank[0] + 1  # 1-indexed
            else:
                vector_rank = len(candidate_indices)  # Penalize unseen

            bm25_rank = rank + 1  # 1-indexed

            rrf_score = 1 / (k + vector_rank) + 1 / (k + bm25_rank)
            rrf_results.append((idx, rrf_score))

        # Sort by RRF score and return top-k
        rrf_results.sort(key=lambda x: x[1], reverse=True)
        return rrf_results[:top_k]
```

**Expected Performance:**
- Semantic accuracy comparable to vector search (Pass 1 uses same embeddings)
- Keyword precision from local BM25 (Pass 2 operates on decrypted plaintext)
- Potential accuracy loss from limited candidate pool (250)
- Higher latency than plaintext baselines (two-pass approach)

---

## Part 6: Evaluation Metrics

### Primary Metrics

#### 1. Recall (Sensitivity)
**Definition:** Percentage of relevant documents retrieved

```
Recall = |Relevant Retrieved| / |All Relevant|
```

**Target:** >0.85 (85% of relevant documents found)

#### 2. Precision
**Definition:** Percentage of retrieved documents that are relevant

```
Precision = |Relevant Retrieved| / |All Retrieved|
```

**Target:** >0.80 (80% of retrieved documents are relevant)

#### 3. F1 Score
**Definition:** Harmonic mean of precision and recall

```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
```

**Target:** >0.82 (balanced performance)

#### 4. Mean Reciprocal Rank (MRR)
**Definition:** Average of reciprocal ranks of first relevant result

```
MRR = 1 / |Q| Σ (1 / rank_i)
```

Where `rank_i` is the rank of the first relevant document for query i.

**Target:** >0.75 (first relevant result appears in top 3 on average)

### Secondary Metrics

#### 5. Latency
- **p50:** Median search time
- **p95:** 95th percentile search time
- **p99:** 99th percentile search time

**Targets:**
- p50 < 800ms
- p95 < 1.5s
- p99 < 2s

#### 6. Throughput
- Queries per second
- Concurrent query capacity

### Tertiary Metrics (Observational)

#### 7. Query Type Performance
Break down performance by query type:
- **Semantic:** "deployment setup", "API authentication"
- **Keyword:** "a828e60", "memorySearch.query.hybrid"
- **Mixed:** "home network router config"

#### 8. Memory Size Performance
Test across different corpus sizes:
- 500 memories (initial test)
- 1,000 memories
- 5,000 memories

---

## Part 6.5: OpenClaw Compatibility Requirements

### 6.5.1 File Structure Compatibility

**Critical Requirement:** TotalReclaw must be fully compatible with OpenClaw's file structure for seamless import/export.

**OpenClaw's File Structure:**
```
~/.openclaw/workspace/
├── MEMORY.md              # Curated long-term memory
└── memory/
    ├── 2026-02-18.md      # Daily log (append-only)
    ├── 2026-02-17.md
    └── 2026-02-16.md
```

**Export Format Specification:**
When users export from TotalReclaw, they must receive valid OpenClaw-compatible Markdown:

```markdown
# MEMORY.md
## Team
- Backend lead: Sarah (sarahr@example.com)
- Frontend lead: Mike (miket@example.com)

## API Configuration
- Base URL: https://api.example.com/v1
- Rate limit: 100 req/min
```

```markdown
# memory/2026-02-18.md
## 10:23 AM - Project Structure Discussion
User: We should use /src/components...
Assistant: Agreed. I'll update...

## 2:45 PM - API Integration
User: The API is returning 429 errors...
```

**Database Schema for Export Tracking:**
```sql
-- Track original OpenClaw file structure
ALTER TABLE encrypted_vault ADD COLUMN source_file TEXT;
ALTER TABLE encrypted_vault ADD COLUMN source_type TEXT
    CHECK (source_type IN ('MEMORY.md', 'memory-daily', 'imported'));

-- Track chunk boundaries for memory_get compatibility
ALTER TABLE encrypted_vault ADD COLUMN line_start INTEGER;
ALTER TABLE encrypted_vault ADD COLUMN line_end INTEGER;
ALTER TABLE encrypted_vault ADD COLUMN chunk_index INTEGER;
```

### 6.5.2 Memory Search Tool Compatibility

**OpenClaw's Tool Interface:**
- **`memory_search(query, maxResults)`**: Returns snippets, file path, line range, score
- **`memory_get(path, lineStart, maxLines)`**: Reads full file content

**Testbed Must Implement:**
```python
@dataclass
class SearchResult:
    """OpenClaw-compatible search result format"""
    path: str              # "memory/2026-02-18.md" or "MEMORY.md"
    line_start: int        # Line number where snippet starts
    line_end: int          # Line number where snippet ends
    snippet: str           # ~700 chars, terms highlighted
    score: float           # 0.0 to 1.0
    docid: str             # Short hash identifier (6 chars)

@dataclass
class MemoryGetResult:
    """OpenClaw-compatible memory_get format"""
    path: str              # File path
    content: str           # Full file content or line range
    line_start: int        # Starting line (if requested)
    line_end: int          # Ending line (if requested)
```

### 6.5.3 Import/Export Validation Tests

**Test 1: OpenClaw → TotalReclaw Import**
```
Input: OpenClaw memory files (MEMORY.md, memory/*.md)
Process:
1. Parse Markdown files
2. Extract entities for blind indexing
3. Generate embeddings
4. Encrypt and store in TotalReclaw
Validate: Search accuracy F1 ≥ 0.90 vs original OpenClaw search
```

**Test 2: TotalReclaw → OpenClaw Export**
```
Input: Encrypted TotalReclaw vault
Process:
1. Decrypt all memories locally
2. Reconstruct file structure
3. Write Markdown files (MEMORY.md, memory/*.md)
Validate: OpenClaw can index and search exported files
```

**Test 3: Round-Trip Fidelity**
```
Start: OpenClaw files
  → Import to TotalReclaw
  → Export from TotalReclaw
  → Compare with original
Validate: Content F1 ≥ 0.95, search F1 ≥ 0.90
```

### 6.5.4 MCP/Skill Integration Requirements

**Future Implementation: TotalReclaw MCP Server**

```yaml
name: totalreclaw
description: Zero-knowledge E2EE memory system compatible with OpenClaw

tools:
  - name: memory_search
    description: Search encrypted memories (E2EE, zero-knowledge)
    input:
      query: string
      max_results: integer (default: 5)
      min_score: number (default: 0.0)
    output:
      results: SearchResult[]

  - name: memory_get
    description: Retrieve full memory content
    input:
      path: string
      line_start: integer (optional)
      max_lines: integer (default: 100)
    output:
      content: string
      line_start: integer
      line_end: integer

  - name: memory_save
    description: Save a memory to encrypted vault
    input:
      content: string
      source_type: string (MEMORY.md or memory-daily)
      metadata: object (optional)
    output:
      path: string
      saved: boolean
```

**Claude Desktop Configuration:**
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

---

## Part 7: Test Query Design

### Query Categories

#### Category A: Semantic Queries (30%)
Queries where the wording differs from the stored content.

**Examples:**
- "container orchestration setup" → expects Docker Compose results
- "CI/CD pipeline configuration" → expects GitHub Actions results
- "database connection issues" → expects PostgreSQL connection errors
- "authentication flow" → expects OAuth/JWT results
- "rate limiting errors" → expects 429 error solutions

#### Category B: Exact Keyword Queries (30%)
Queries requiring exact string matching.

**Examples:**
- "a828e60" → expects specific UUID/ID
- "memorySearch.query.hybrid" → expects exact code path
- "429 Too Many Requests" → expects exact error message
- "us-east-1" → expects specific region
- "sarahr@example.com" → expects exact email

#### Category C: Mixed Queries (20%)
Queries combining semantic and keyword elements.

**Examples:**
- "API rate limit configuration for example.com" → semantic + specific domain
- "PostgreSQL connection string in production" → specific DB + environment
- "Deploy React app to S3 with CloudFront" → semantic + specific services

#### Category D: Temporal Queries (10%)
Queries about recent or specific time periods.

**Examples:**
- "standup time from yesterday" → expects recent meeting
- "database schema changes from last week" → expects recent changes
- "deployment from February 15" → expects specific date

#### Category E: Fuzzy/Partial Queries (10%)
Queries with incomplete or approximate information.

**Examples:**
- "github token" → expects "ghp_xxxxx" or similar
- "sarah's email" → expects "sarahr@example.com"
- "the API error we fixed" → expects specific error from context

### Test Query Set Size

**Initial Test:** 50 queries
- Semantic: 15
- Keyword: 15
- Mixed: 10
- Temporal: 5
- Fuzzy: 5

**Expanded Test:** 200 queries (if initial results are promising)

---

## Part 8: Ground Truth Annotation

### Human Evaluation Process

For accurate metrics, we need ground truth labels (which documents are relevant to each query).

**Process:**
1. Generate test queries
2. For each query, have 2-3 human evaluators label relevant documents
3. Use majority voting to resolve disagreements
4. Calculate inter-annotator agreement (Fleiss' kappa)

**Tools:**
- Use a simple labeling interface (Google Sheets, Airtable)
- Or build a minimal web interface for faster labeling

### Estimated Effort

- **Dataset creation:** 4-8 hours (using LLM generation)
- **Query creation:** 2-4 hours
- **Ground truth labeling:** 8-12 hours (50 queries × 2-3 evaluators)
- **Total:** 14-24 hours for initial test

---

## Part 9: Implementation Plan

### Phase 1: Setup (Week 1)

**Tasks:**
1. Set up PostgreSQL 16 with pgvector
2. Install Python dependencies (rank-bm25, sentence-transformers, cryptography)
3. Create synthetic memory dataset (500 chunks)
4. Generate test query set (50 queries)
5. Implement baseline search algorithms (BM25-only, Vector-only, OpenClaw hybrid)

**Deliverables:**
- Working database with test data
- All baseline search implementations
- Test query set

### Phase 2: TotalReclaw Implementation (Week 2)

**Tasks:**
1. Implement TotalReclaw E2EE class
2. Encrypt test dataset and store in PostgreSQL
3. Implement two-pass search algorithm
4. Add blind index generation and matching

**Deliverables:**
- Working TotalReclaw E2EE implementation
- Encrypted test dataset

### Phase 3: Ground Truth Labeling (Week 2-3)

**Tasks:**
1. Create labeling interface
2. Recruit 2-3 evaluators
3. Label ground truth for all queries
4. Calculate inter-annotator agreement

**Deliverables:**
- Labeled ground truth dataset
- Inter-annotator agreement scores

### Phase 4: Evaluation & Analysis (Week 3)

**Tasks:**
1. Run all search algorithms on test queries
2. Calculate metrics (recall, precision, F1, MRR, latency)
3. Generate comparison report
4. Create go/no-go recommendation

**Deliverables:**
- Comprehensive evaluation report
- Go/no-go recommendation with supporting data

---

## Part 10: Go/No-Go Criteria

### Accuracy Thresholds

| Metric | Minimum Acceptable | Target | Outstanding |
|--------|-------------------|--------|-------------|
| **Recall** | >0.75 | >0.85 | >0.90 |
| **Precision** | >0.70 | >0.80 | >0.85 |
| **F1 Score** | >0.73 | >0.82 | >0.87 |
| **MRR** | >0.65 | >0.75 | >0.80 |

### Decision Matrix

**GO (Proceed to Development):**
- F1 score >0.80 OR
- Within 5% of QMD's F1 score OR
- MRR >0.70 with recall >0.75
- **AND OpenClaw compatibility met** (see below)

**MODIFY (Adjust Architecture):**
- F1 score 0.75-0.80 OR
- Within 10% of QMD but with clear gap identified
- MRR 0.65-0.70
- **OR OpenClaw compatibility needs work** (fixable)

**NO-Go (Reconsider Architecture):**
- F1 score <0.75 OR
- >15% gap from QMD's F1 score OR
- MRR <0.65
- **OR OpenClaw compatibility fundamentally broken** (unfixable)

### OpenClaw Compatibility Criteria

**Critical Requirements (Must Pass):**
1. **Export Format**: Exported files must be valid Markdown that OpenClaw can index
2. **Import Accuracy**: Searching imported OpenClaw data achieves F1 ≥ 0.90
3. **Round-Trip Fidelity**: Import → Export preserves content with F1 ≥ 0.95
4. **Tool Interface**: Search results match OpenClaw's `memory_search` format 100%

**Important Requirements (Should Pass):**
1. **File Structure**: Export matches OpenClaw's directory structure (MEMORY.md, memory/*.md)
2. **Line Number Accuracy**: `line_start` and `line_end` in results accurate within ±5 lines
3. **Metadata Preservation**: Dates, people, entities preserved during round-trip
4. **Snippet Quality**: Exported snippets are well-formed Markdown (~700 chars)

**Nice-to-Have:**
1. **Context Preservation**: Section headings, list items preserved during chunking
2. **Code Block Handling**: Code blocks kept intact across chunk boundaries
3. **Timestamp Preservation**: Original timestamps from daily notes preserved

### Modification Options (If Modify)

If results fall in "MODIFY" range, consider:
1. Increase candidate pool size (250 → 500)
2. Add multi-variant blind indexing
3. Improve query expansion
4. Add temporal decay weighting
5. Implement MMR re-ranking

---

## Part 11: Success Metrics by Query Type

### Expected Performance by Category

| Query Type | BM25-Only | Vector-Only | OpenClaw | QMD | TotalReclaw (Target) |
|------------|-----------|-------------|-----------|-----|---------------------|
| **Semantic** | Poor | Good | Good | Excellent | Good |
| **Keyword** | Excellent | Poor | Good | Good | Good |
| **Mixed** | Fair | Fair | Good | Excellent | Good |
| **Temporal** | N/A | N/A | Good (with decay) | Good | Good |
| **Fuzzy** | Poor | Fair | Good | Good | Fair (needs variants) |

### Key Risks by Query Type

| Query Type | Risk | Mitigation |
|------------|------|------------|
| **Semantic** | Limited candidate pool | Increase pool, improve vector quality |
| **Keyword** | Blind index coverage gaps | Multi-variant indexing |
| **Fuzzy** | No exact match | Generate query variations, fuzzy blind indices |

---

## Part 12: Timeline and Resources

### Estimated Timeline

**Week 1:** Setup + Baseline Implementation
- Days 1-3: Environment setup, data generation
- Days 4-5: Baseline search implementations

**Week 2:** TotalReclaw Implementation + Labeling
- Days 1-3: TotalReclaw E2EE implementation
- Days 4-5: Ground truth labeling

**Week 3:** Evaluation + Decision
- Days 1-2: Run evaluations
- Day 3: Analysis and reporting
- Day 4: Go/no-go decision

### Resources Required

**Personnel:**
- 1 Full-time engineer (Python, ML/AI background)
- 2-3 Part-time evaluators (for ground truth labeling)
- 1 Product/Strategy stakeholder (for go/no-go decision)

**Infrastructure:**
- PostgreSQL 16 with pgvector (can run locally or on cloud)
- Development machine with 8GB+ RAM
- Python 3.12+ environment

**Budget:**
- Infrastructure: $50-100/month (or $0 if local)
- OpenAI API (for LLM-generated data): ~$20-50
- Evaluator time: ~$200-400 (20-40 hours at $10-20/hour)

**Total Estimated Budget:** $270-550 for initial test

---

## Part 13: Reporting Format

### Evaluation Report Template

```markdown
# TotalReclaw Testbed Evaluation Report

**Date:** [Date]
**Dataset:** [Memory count, query count]
**Evaluators:** [Names, inter-annotator agreement]

## Executive Summary

[One-paragraph summary of findings and go/no-go recommendation]

## Overall Results

| System | Recall | Precision | F1 | MRR | Latency p50 |
|--------|--------|-----------|-----|-----|-------------|
| BM25-Only | 0.XX | 0.XX | 0.XX | 0.XX | XXms |
| Vector-Only | 0.XX | 0.XX | 0.XX | 0.XX | XXms |
| OpenClaw Hybrid | 0.XX | 0.XX | 0.XX | 0.XX | XXms |
| QMD Hybrid | 0.XX | 0.XX | 0.XX | 0.XX | XXms |
| TotalReclaw E2EE | 0.XX | 0.XX | 0.XX | 0.XX | XXms |

## Performance by Query Type

[Breakdown tables for each query category]

## Analysis

[Key findings, strengths, weaknesses, gaps identified]

## Go/No-Go Recommendation

[Clear recommendation with supporting data and next steps]

## Appendix: Detailed Results

[Per-query results, confusion matrices, latency distributions]
```

---

## Part 14: References

### Technical References

1. **OpenClaw Memory Documentation**
   - URL: https://docs.openclaw.ai/concepts/memory
   - Key insights: Hybrid search algorithm, configuration options

2. **QMD Repository and Documentation**
   - URL: https://github.com/tobi/qmd
   - Key insights: Local-first hybrid + reranking architecture

3. **QMD Guide for OpenClaw**
   - URL: https://travis.media/blog/openclaw-memory-qmd-guide/
   - Key insights: Practical implementation details, hardware requirements

4. **Supermemory Accuracy Claim**
   - URL: https://x.com/julianweisser/status/2023635504638685344
   - Key insights: "30 points higher accuracy than other memory options"

5. **Mem0 AI Memory Benchmark**
   - URL: https://mem0.ai/blog/benchmarked-openai-memory-vs-langmem-vs-memgpt-vs-mem0-for-long-term-memory-here-s-how-they-stacked-up
   - Key insights: Mem0 achieves 66.9% accuracy against competitors

### Algorithm References

6. **BM25 Algorithm**
   - Robertson & Zaragoza (2009): "The Probabilistic Relevance Framework: BM25 and Beyond"
   - Implementation: Python rank-bm25 library

7. **Reciprocal Rank Fusion (RRF)**
   - Cormack et al. (2009): "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"
   - Formula: score = 1 / (k + rank1) + 1 / (k + rank2)

8. **MMR (Maximal Marginal Relevance)**
   - Carbonell & Goldstein (1998): "The Use of MMR, Diversity-Based Reranking for Reordering Documents"

### Implementation References

9. **all-MiniLM-L6-v2**
   - Sentence transformers model
   - 384-dimensional embeddings
   - Good balance of speed and accuracy

10. **Argon2id KDF**
    - RFC 9106: "Argon2id Memory-Hard Hashing for Passwords"
    - Recommended for password-based key derivation

11. **AES-GCM Encryption**
    - NIST Special Publication 800-38D
    - Authenticated encryption with additional data

---

## Part 15: Next Steps After Testbed

### If GO Decision

1. **Proceed to MVP Development**
   - Implement OpenClaw skill (npm package)
   - Implement MCP server
   - Build REST API
   - Focus on addressing identified gaps

2. **Optimization Priorities**
   - Address largest accuracy gaps first
   - Optimize latency bottlenecks
   - Add missing features (multi-variant blind indices)

3. **Production Readiness**
   - Security audit
   - Performance testing at scale
   - User testing for UX flows

### If NO-Go Decision

1. **Architecture Alternatives**
   - Consider larger candidate pool
   - Consider server-side enrichment (TDX)
   - Consider hybrid E2EE (optional server-side features)

2. **Pivot Options**
   - Focus on local-first only (QMD-style, no sync)
   - Partner with existing memory provider
   - Defer E2EE to Phase 2

### If MODIFY Decision

1. **Targeted Improvements**
   - Implement specific mitigations for identified gaps
   - Re-run testbed with modifications
   - Iterate until GO or NO-Go

2. **Alternative Test Designs**
   - Larger dataset (5,000 memories)
   - More diverse query types
   - Real-world user study

---

**Document Control:**

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2026-02-18 | Initial testbed specification | TotalReclaw Team |
