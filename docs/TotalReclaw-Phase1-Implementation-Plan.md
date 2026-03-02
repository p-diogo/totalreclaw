# TotalReclaw Phase 1: Implementation Plan

**Version:** 1.0.0
**Status:** Draft
**Last Updated:** February 18, 2026

**Purpose:** Detailed implementation plan for building the TotalReclaw testbed to validate zero-knowledge E2EE search accuracy before full product development.

---

## Executive Summary

This plan covers the build-out of a technical testbed to validate TotalReclaw's zero-knowledge E2EE architecture against state-of-the-art plaintext search baselines.

**Testbed Scale (3x from Original Proposal):**
- **1,500 memory chunks** (vs. 500)
- **150 test queries** (vs. 50)
- **6 search algorithms** (4 baselines + 2 E2EE variants)
- **3 evaluators** for ground truth labeling
- **3-week timeline**

**Critical Requirement: OpenClaw Compatibility**
- Testbed must validate seamless import/export between TotalReclaw (encrypted remote) and OpenClaw (local plaintext)
- Data format must match OpenClaw's file structure exactly
- Search behavior must be indistinguishable from OpenClaw's native memory tools

**Go/No-Go Decision:** Based on testbed results, determine whether to proceed with full MVP development.

---

## Part 1: Team & Resources

### 1.1 Team Composition

**Core Team (Full-Time):**
- **1 Lead Engineer** (Python, ML/AI, cryptography)
  - Responsibilities: Architecture, core implementations, technical decisions
  - Skills: Python, PostgreSQL, pgvector, ML, cryptography, FastAPI

**Part-Time/Contractors:**
- **1 Ground Truth Evaluator A** (20-30 hours over 3 weeks)
- **1 Ground Truth Evaluator B** (20-30 hours over 3 weeks)
- **1 Ground Truth Evaluator C** (20-30 hours over 3 weeks)
- **1 Product/Strategy Stakeholder** (5-10 hours for go/no-go decision)

**Total Effort:**
- Lead Engineer: 120 hours (3 weeks @ 40h/week)
- Evaluators: 60-90 hours total
- Stakeholder: 5-10 hours

### 1.2 Infrastructure Requirements

**Development Machine:**
- OS: macOS 14+ or Ubuntu 22.04+
- RAM: 16GB minimum (32GB preferred for local LLM)
- Storage: 50GB free space
- CPU: 4+ cores (8+ preferred for parallel processing)

**Cloud Resources (Optional):**
- PostgreSQL 16 instance (8GB RAM, 2 vCPUs)
- Or run locally with Docker Compose

**Software Stack:**
- Python 3.12+
- PostgreSQL 16 with pgvector extension
- FastAPI (for quick API endpoints)
- Jupyter Notebook (for data analysis and visualization)

**Budget:** $270-550 (mostly for LLM API calls during data generation)

---

## Part 1.5: OpenClaw Compatibility Requirements

### 1.5.1 File Structure Compatibility

**Requirement:** TotalReclaw must be able to export data in OpenClaw's native format, and OpenClaw must be able to import TotalReclaw data seamlessly.

**OpenClaw's File Structure (from official docs):**
```
~/.openclaw/workspace/
├── MEMORY.md              # Curated long-term memory (main session only)
└── memory/
    ├── 2026-02-18.md      # Daily log (append-only)
    ├── 2026-02-17.md
    └── 2026-02-16.md
```

**Testbed Validation Requirements:**
1. **Export Format**: When users export from TotalReclaw, they must get valid Markdown files that OpenClaw can read
2. **Import Capability**: TotalReclaw should be able to ingest existing OpenClaw memory files and encrypt them
3. **Round-Trip Preservation**: Export → Import → Export should preserve content and structure

**Database Schema Compatibility:**
```sql
-- Add OpenClaw file source tracking
ALTER TABLE encrypted_vault ADD COLUMN source_file TEXT;
ALTER TABLE encrypted_vault ADD COLUMN source_type TEXT
    CHECK (source_type IN ('MEMORY.md', 'memory-daily', 'imported'));

-- Track original file structure for export
ALTER TABLE encrypted_vault ADD COLUMN chunk_index INTEGER;
ALTER TABLE encrypted_vault ADD COLUMN total_chunks INTEGER;
```

### 1.5.2 Memory Search Tool Compatibility

**Requirement:** TotalReclaw's search results must be compatible with OpenClaw's `memory_search` and `memory_get` tool interfaces.

**OpenClaw's Tool Interface (from official docs):**
- **`memory_search`**: Returns snippets (~700 chars), file path, line range, score
- **`memory_get`**: Reads full file by path, supports line ranges

**Testbed Validation:**
```python
class OpenClawCompatibleSearch:
    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        Must return results in OpenClaw's format:
        {
            "path": "memory/2026-02-18.md",
            "line_start": 42,
            "line_end": 65,
            "snippet": "This section covers the **craftsmanship**...",
            "score": 0.93,
            "docid": "a1b2c3"
        }
        """

    def get(self, path: str, line_start: int = None, max_lines: int = None) -> str:
        """
        Must retrieve full content in OpenClaw's format.
        Used when agent needs full context after search.
        """
```

### 1.5.3 Skill/MCP Integration Simulation

**Requirement:** Testbed must simulate how OpenClaw skills will interact with TotalReclaw.

**OpenClaw Skill Integration Pattern:**
```
User (via agent)
    ↓
Agent calls memory_search tool
    ↓
TotalReclaw MCP Server or Skill
    ↓
Returns results in OpenClaw-compatible format
    ↓
Agent receives results as if from local memory
```

**Testbed Validation:**
1. Simulate agent-style queries (conversational, contextual)
2. Validate response format matches OpenClaw's expectations
3. Test latency tolerance (agents need <2s for responsiveness)
4. Validate snippet quality (700 char limit, highlighted terms)

**MCP Tool Specification (for future implementation):**
```yaml
tools:
  - name: memory_search
    description: Search memories in TotalReclaw vault (E2EE)
    input_schema:
      type: object
      properties:
        query:
          type: string
          description: Search query
        max_results:
          type: integer
          default: 5
          description: Maximum results to return
        min_score:
          type: number
          default: 0.0
          description: Minimum relevance score

  - name: memory_get
    description: Retrieve full memory content by path
    input_schema:
      type: object
      properties:
        path:
          type: string
          description: Memory file path (e.g., memory/2026-02-18.md)
        line_start:
          type: integer
          description: Start reading from line number
        max_lines:
          type: integer
          default: 100
          description: Maximum lines to return
```

### 1.5.4 Data Migration Validation

**Testbed Must Validate:**

1. **Import Path** (OpenClaw → TotalReclaw):
   - Parse existing `MEMORY.md` and `memory/*.md` files
   - Extract entities for blind indexing
   - Generate embeddings for all content
   - Encrypt and store in TotalReclaw format
   - Validate that search results match or exceed OpenClaw's accuracy

2. **Export Path** (TotalReclaw → OpenClaw):
   - Decrypt all memories locally
   - Reconstruct file structure (MEMORY.md, memory/*.md)
   - Preserve chunk boundaries and line ranges for `memory_get` compatibility
   - Validate that exported files are valid Markdown
   - Validate that OpenClaw can index and search exported files

3. **Round-Trip Test**:
   - Start with OpenClaw memory files
   - Import to TotalReclaw
   - Export from TotalReclaw
   - Compare with original
   - Success criteria: Content preserved, search accuracy maintained

### 1.5.5 Success Criteria for OpenClaw Compatibility

| Criterion | Test | Success Threshold |
|-----------|------|-------------------|
| **Import Accuracy** | Search imported data vs original | F1 ≥ 0.90 |
| **Export Validity** | OpenClaw can index exported files | 100% success rate |
| **Format Compatibility** | Export files match OpenClaw structure | 100% compliant |
| **Tool Compatibility** | Results match memory_search format | 100% compatible |
| **Round-Trip Fidelity** | Content preserved after import+export | F1 ≥ 0.95 |

---

## Part 2: Timeline Overview

### Week 1: Setup & Baselines

**Days 1-2: Environment Setup**
- Install PostgreSQL 16 with pgvector
- Set up Python environment
- Create synthetic data generation pipeline
- Initialize test database schema

**Days 3-4: Baseline Implementations**
- BM25-only search
- Vector-only search
- OpenClaw hybrid search
- QMD-style hybrid search

**Days 5: Initial Testing & Debugging**
- Test all baselines with sample data
- Debug implementation issues
- Validate performance metrics

**Week 1 Deliverables:**
- Working development environment
- All 4 baseline search implementations
- Initial synthetic dataset (500 chunks for testing)

---

### Week 2: TotalReclaw Implementation & Data Generation

**Days 1-3: Data Generation**
- Generate 1,500 memory chunks using LLM
- Distribute across categories (chat, email, calendar, personal, technical)
- Store in PostgreSQL with embeddings and metadata

**Days 4-5: TotalReclaw v0.2 Implementation**
- Implement E2EE encryption/decryption
- Implement two-pass search (remote + local BM25)
- Generate blind indices (regex-only)
- Integrate with test database

**Days 6-7: Ground Truth Labeling (Parallel)**
- Generate 150 test queries
- Set up labeling interface
- Begin ground truth labeling (3 evaluators)
- Calculate inter-annotator agreement

**Week 2 Deliverables:**
- Complete 1,500 memory dataset
- TotalReclaw v0.2 implementation
- 150 test queries
- Partial ground truth labels

---

### Week 3: TotalReclaw v0.5, Evaluation & Decision

**Days 1-3: TotalReclaw v0.5 Implementation**
- Implement multi-variant blind indices (regex + LLM)
- Implement three-pass search (add LLM reranking)
- Integration testing

**Days 4-5: Comprehensive Evaluation**
- Run all 6 algorithms on all 150 queries
- Calculate metrics (F1, precision, recall, MRR, latency)
- Generate comparison report

**Day 6: Analysis & Go/No-Go Decision**
- Review results with stakeholders
- Document findings and recommendations
- Make build/pivot decision

**Week 3 Deliverables:**
- TotalReclaw v0.5 implementation
- Comprehensive evaluation report
- Go/no-go recommendation with supporting data
- v0.5 specification (if GO decision)

---

## Part 3: Detailed Task Breakdown

### 3.1 Week 1 Tasks

#### Task 1.1: Environment Setup (Days 1-2)

**Subtasks:**
1. Install PostgreSQL 16 with pgvector extension
2. Create database schema and indexes
3. Set up Python virtual environment
4. Install dependencies:
   - `rank-bm25` (BM25 search)
   - `sentence-transformers` (vector embeddings)
   - `cryptography` (AES-GCM, HKDF, Argon2id)
   - `fastapi` (API server, if needed)
   - `numpy`, `pandas`, `scikit-learn` (metrics, analysis)
5. Create test database and connect
6. Verify pgvector extension is loaded

**Acceptance Criteria:**
- PostgreSQL running with pgvector enabled
- `SELECT vector('[1,2,3]')::vector` works
- All Python packages installed
- Can create test table and insert test data

**Estimated Effort:** 8 hours

---

#### Task 1.2: Data Generation Pipeline (Day 3)

**Subtasks:**

1. **Design LLM prompt templates for each memory category** (based on real OpenClaw usage):
   - Daily conversation logs (chat/AI interactions, project discussions)
   - Email threads (project decisions, technical discussions)
   - Meeting notes (calendar entries, standups, 1:1s)
   - Personal preferences (work schedule, meeting times, environment setup)
   - Technical documentation (API configs, deployment procedures, error solutions)
   - Configuration details (API keys, endpoints, database strings)

2. **Implement realistic memory file structure** (mimicking OpenClaw's actual format):
   ```markdown
   ## memory/2026-02-18.md

   ### 10:23 AM - Project Structure Discussion
   User: We should use /src/components for React components...
   Assistant: Agreed. I'll update the project structure...

   ### 2:45 PM - API Integration
   User: The API is returning 429 errors...
   ```

   ```markdown
   ## MEMORY.md

   ### Team
   - Backend lead: Sarah (sarahr@example.com)
   - Frontend lead: Mike (miket@example.com)

   ### API Configuration
   - Base URL: https://api.example.com/v1
   - Rate limit: 100 req/min
   ```

3. **Implement data generation script**:
   ```python
   def generate_memories(category: str, count: int, llm_client):
       prompt = CATEGORY_PROMPTS[category]
       response = llm_client.complete(prompt=prompt)
       return parse_and_validate(response)
   ```

4. **Implement memory chunking** (matching OpenClaw's approach):
   - Target: ~400 tokens per chunk (OpenClaw default)
   - Overlap: 80 tokens between chunks (OpenClaw default)
   - Preserve context within chunks
   - **Smart chunking**: Respect markdown boundaries (headings, code blocks)

5. **Implement metadata extraction**:
   - Extract entities for blind indexing validation (emails, UUIDs, error codes, names)
   - Store creation timestamps (for temporal decay testing)
   - Store file source (MEMORY.md vs memory/YYYY-MM-DD.md)
   - Categorize memories

6. **Generate 1,500 memories** (updated distribution based on real usage):
   - Daily conversation logs: 450 chunks (30%) - project decisions, debugging
   - Email threads: 375 chunks (25%) - project discussions, technical decisions
   - Meeting notes: 225 chunks (15%) - standups, 1:1s, planning
   - Personal preferences: 225 chunks (15%) - work schedule, environment setup
   - Technical documentation: 150 chunks (10%) - API configs, deployment procedures
   - Configuration details: 75 chunks (5%) - API keys, endpoints, connection strings

**Acceptance Criteria:**
- 1,500 unique memory chunks generated
- All chunks properly categorized
- File source metadata included (MEMORY.md vs daily notes)
- Metadata extracted (people mentioned, dates, error codes, API references)
- Data quality validated (no duplicates, proper formatting)

**Estimated Effort:** 12 hours (increased from 10 for realistic formatting)

---

#### Task 1.3: Baseline Implementation: BM25-Only (Day 4)

**Subtasks:**
1. Implement BM25 tokenization:
   ```python
   def tokenize(text: str) -> List[str]:
       return word_tokenize(text.lower())
   ```

2. Implement BM25 index creation:
   ```python
   from rank_bm25 import BM25Okapi
   tokenized_corpus = [tokenize(doc) for doc in documents]
   bm25 = BM25Okapi(tokenized_corpus)
   ```

3. Implement BM25 search:
   ```python
   def bm25_search(query: str, bm25_index, top_k: int = 5):
       scores = bm25_index.get_scores(tokenize(query))
       top_indices = np.argsort(scores)[::-1][:top_k]
       return [(idx, scores[idx]) for idx in top_indices]
   ```

4. Add metadata to results (score, document snippet)

**Acceptance Criteria:**
- BM25 search returns top-5 results for any query
- Scores are properly calculated
- Results include document snippets for validation

**Estimated Effort:** 4 hours

---

#### Task 1.4: Baseline Implementation: Vector-Only (Day 4)

**Subtasks:**
1. Implement sentence transformer model:
   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer('all-MiniLM-L6-v2')
   ```

2. Generate embeddings for all memories:
   ```python
   embeddings = model.encode(documents)
   # Store in PostgreSQL pgvector
   ```

3. Implement vector search:
   ```python
   def vector_search(query: str, embeddings: np.ndarray, top_k: int = 5):
       query_embedding = model.encode([query])[0]
       similarities = cosine_similarity([query_embedding], embeddings)[0]
       top_indices = np.argsort(similarities)[::-1][:top_k]
       return [(idx, similarities[idx]) for idx in top_indices]
   ```

**Acceptance Criteria:**
- All 1,500 memories embedded (384-dimensional vectors)
- Vector search returns top-5 results
- Cosine similarity scores calculated correctly

**Estimated Effort:** 5 hours

---

#### Task 1.5: Baseline Implementation: OpenClaw Hybrid (Day 5)

**Subtasks:**
1. Implement weighted merge algorithm:
   ```python
   def openclaw_hybrid_search(query, documents, embeddings, top_k=5):
       # Vector search
       vector_results = vector_search(query, embeddings, top_k * 4)

       # BM25 search
       bm25_results = bm25_search(query, documents, top_k * 4)

       # Normalize BM25 ranks to scores
       bm25_normalized = {idx: 1 / (1 + rank) for idx, rank in bm25_results}

       # Union candidates
       all_candidates = set([r[0] for r in vector_results]) | set([r[0] for r in bm25_results])

       # Weighted merge
       final_scores = {}
       for idx in all_candidates:
           vector_score = vector_results[idx] if idx in [r[0] for r in vector_results] else 0
           bm25_score = bm25_normalized.get(idx, 0)
           final_scores[idx] = 0.7 * vector_score + 0.3 * bm25_score

       # Sort and return top-k
       sorted_results = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
       return [(idx, score) for idx, score in sorted_results[:top_k]]
   ```

2. Optimize with candidate pool size (candidateMultiplier = 4)

**Acceptance Criteria:**
- Hybrid search returns top-5 results
- Weighted merge algorithm matches OpenClaw spec
- Configurable vector_weight and text_weight

**Estimated Effort:** 6 hours

---

#### Task 1.6: Baseline Implementation: QMD-Style Hybrid (Day 5)

**Subtasks:**
1. Implement BM25 + vector retrieval
2. Implement simplified LLM reranker:
   ```python
   def llm_reranker_simple(query, candidates):
       # Boost candidates with query term matches
       query_lower = query.lower()
       query_terms = set(word_tokenize(query_lower))

       reranked = []
       for idx, score in candidates:
           doc_lower = documents[idx].lower()
           term_match = any(term in doc_lower for term in query_terms)
           reranked_score = score * 1.5 if term_match else score
           reranked.append((idx, reranked_score))

       reranked.sort(key=lambda x: x[1], reverse=True)
       return reranked[:top_k]
   ```

3. Note: Full LLM reranker requires actual LLM integration (deferred to Week 2 or use local LLM)

**Acceptance Criteria:**
- QMD-style hybrid returns top-5 results
- Simplified reranker works without LLM
- Ready for LLM integration when ready

**Estimated Effort:** 4 hours

---

#### Task 1.7: Testing & Validation (Day 5)

**Subtasks:**
1. Create test query set (50 queries for Week 1 testing)
2. Run each baseline on test queries
3. Validate metrics are calculated correctly:
   - Precision, Recall, F1
   - MRR
   - Latency (p50, p95, p99)
4. Debug and fix issues
5. Document baseline performance

**Acceptance Criteria:**
- All baselines functional
- Metrics calculated correctly
- Baseline performance documented
- Test queries validated

**Estimated Effort:** 8 hours

**Week 1 Total:** ~40 hours (1 week)

---

### 3.2 Week 2 Tasks

#### Task 2.1: Complete Data Generation (Days 1-3)

**Subtasks:**
1. Scale up data generation to 1,500 memories
2. Generate all embeddings and store in PostgreSQL
3. Validate data quality and diversity
4. Create memory statistics report:
   - Category distribution
   - Average chunk size
   - Entity density (for blind indexing)

**Acceptance Criteria:**
- 1,500 memories stored in database
- All embeddings generated and stored
- Data quality report complete

**Estimated Effort:** 16 hours

---

#### Task 2.2: TotalReclaw v0.2 Implementation (Days 4-5)

**Subtasks:**
1. **Cryptographic Core:**
   ```python
   class TotalReclawClient:
       def __init__(self, master_password: str):
           self.kdf = HKDF(
               algorithm=hashes.SHA256(),
               length=64,
               salt=b'totalreclaw-salt',
               info=b'totalreclaw-key-derivation'
           )
           derived = self.kdf.derive(master_password.encode())
           self.data_key = derived[:32]
           self.blind_key = derived[32:]
           self.cipher = AESGCM(self.data_key)
   ```

2. **Memory Encryption:**
   ```python
   def encrypt_memory(self, plaintext: str, embedding: np.ndarray):
       nonce = os.urandom(12)
       ciphertext = self.cipher.encrypt(nonce, plaintext.encode(), b'')

       # Generate blind indices (regex-only for v0.2)
       blind_indices = self.generate_regex_blind_indices(plaintext)

       return {
           'ciphertext': ciphertext,
           'nonce': nonce,
           'embedding': embedding.tolist(),
           'blind_indices': blind_indices
       }
   ```

3. **Memory Decryption:**
   ```python
   def decrypt_memory(self, ciphertext: bytes, nonce: bytes) -> str:
       plaintext = self.cipher.decrypt(nonce, ciphertext, b'')
       return plaintext.decode()
   ```

4. **Blind Index Generation (v0.2):**
   ```python
   def generate_regex_blind_indices(self, plaintext: str) -> List[str]:
       blind_indices = []

       # Extract emails
       emails = re.findall(r'[\w.%+-]+@[\w.-]+\.[a-zA-Z]{2,}', plaintext)
       for email in emails:
           blind_indices.append(self.hmac_sha256(email.lower()))

       # Extract UUIDs
       uuids = re.findall(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', plaintext)
       for uuid in uuids:
           blind_indices.append(self.hmac_sha256(uuid.lower()))

       return list(set(blind_indices))
   ```

5. **Pass 1: Remote Search Client:**
   ```python
   def pass1_remote_search(self, query_vector, blind_hashes, limit=250):
       # Send to server (simulated)
       response = requests.post(
           f"{self.api_url}/v1/vault/search",
           json={
               "vault_id": self.vault_id,
               "query_vector": query_vector.tolist(),
               "blind_hashes": blind_hashes,
               "limit": limit
           }
       )
       return response.json()['results']
   ```

6. **Pass 2: Local Decryption + BM25:**
   ```python
   def pass2_local_bm25(self, query, server_results, top_k=50):
       # Decrypt all candidates
       decrypted = []
       for result in server_results:
           plaintext = self.decrypt_memory(result['ciphertext'], result['nonce'])
           decrypted.append({'id': result['id'], 'plaintext': plaintext})

       # BM25 on decrypted
       bm25 = BM25Okapi([tokenize(d['plaintext']) for d in decrypted])
       scores = bm25.get_scores(tokenize(query))

       # RRF fusion
       K = 60
       rrf_results = []
       for i, doc in enumerate(decrypted):
           vector_rank = i  # Simplified for now
           bm25_rank = scores[i] + 1
           rrf_score = 1/(K + vector_rank) + 1/(K + bm25_rank)
           rrf_results.append((doc['id'], rrf_score))

       rrf_results.sort(key=lambda x: x[1], reverse=True)
       return rrf_results[:top_k]
   ```

**Acceptance Criteria:**
- TotalReclaw v0.2 client fully functional
- E2EE properties maintained (server never sees plaintext)
- Two-pass search implemented
- 250 candidate pool size

**Estimated Effort:** 12 hours

---

#### Task 2.3: Test Query Generation & Ground Truth Labeling (Days 6-7)

**Subtasks:**

**Query Generation** (based on real OpenClaw usage patterns):
1. Design query templates for each category:
   - **Contextual/Fact Retrieval** (45 queries, 30%): "What did Sarah say about X?"
   - **Configuration & Setup** (30 queries, 20%): "What's my API config?"
   - **Temporal/Recent Activity** (22 queries, 15%): "What did we do yesterday?"
   - **Error & Solution Lookup** (22 queries, 15%): "How did we fix error X?"
   - **Semantic/Concept Queries** (18 queries, 12%): "container orchestration" → Docker
   - **Exact/Keyword Queries** (13 queries, 8%): "sk-proj-abc123", error codes

2. **Real-world query patterns to include:**
   - People-referenced queries (Sarah, Mike, Rod - from actual OpenClaw examples)
   - Email queries (security@example.com, sarahr@example.com)
   - Time-referenced queries (yesterday, last week, today, this week)
   - Error-specific queries (429, timeout, CORS, deadlock)
   - Configuration queries (base URL, rate limit, connection string, deployment)

3. Implement query generation script:
   ```python
   def generate_queries(category: str, count: int, memories_context):
       """
       Generate realistic queries based on actual memory content.

       This ensures queries are answerable (ground truth exists) while
       testing real-world usage patterns.
       """
       # Use LLM to generate queries that would actually be asked
       # based on the memory content we generated
       prompt = CATEGORY_QUERY_PROMPTS[category].format(
           memories_sample=memories_context[:100]
       )
       response = llm_client.complete(prompt=prompt)
       return parse_and_validate_queries(response)
   ```

4. Validate queries:
   - No duplicates
   - Clear intent
   - Each query has at least 1 relevant document in our dataset
   - Query reflects real OpenClaw usage patterns

**Ground Truth Labeling:**
1. Create labeling interface:
   - Simple web interface or Google Sheet
   - Each evaluator labels independently
   - Shows: query, memory snippet, relevance checkbox
   - Allows multiple relevant documents per query
   - Shows file source (MEMORY.md vs daily note) for context

2. Implement labeling workflow:
   ```
   For each query:
     1. Show query text
     2. Show 20 memory snippets (10 random + 10 likely relevant)
     3. Evaluator marks: relevant / not relevant / not sure
     4. Collect responses from 3 evaluators
     5. Use majority voting to resolve disagreements
   ```

3. Calculate inter-annotator agreement (Fleiss' kappa)

4. Validate ground truth quality:
   - Minimum 70% agreement between evaluators
   - If agreement <70%, add more examples or clarify guidelines

**Acceptance Criteria:**
- 150 test queries generated
- All queries labeled by 3 evaluators
- Inter-annotator agreement >0.70
- Ground truth dataset ready

**Estimated Effort:**
- Query generation: 4 hours
- Labeling interface: 4 hours
- Labeling work: 20-30 hours (across 3 evaluators)
- Validation: 2 hours

---

### 3.3 Week 3 Tasks

#### Task 3.1: TotalReclaw v0.5 Implementation (Days 1-3)

**Subtasks:**

**Enhancement 1: Multi-Variant Blind Indices:**
```python
def generate_multi_variant_blind_indices(self, plaintext: str, llm_client) -> Set[str]:
    blind_indices = set()

    # Fast path: Regex variants
    regex_entities = extract_entities_regex(plaintext)
    for entity in regex_entities:
        blind_indices.update(generate_regex_variants(entity))

    # Smart path: LLM variants
    llm_variants = generate_llm_variants(plaintext, llm_client)
    blind_indices.update(llm_variants)

    return blind_indices
```

**Enhancement 2: LLM Reranking (Pass 3):**
```python
def pass3_llm_rerank(self, query: str, top_50_candidates, llm_client):
    # Format candidates for LLM
    results_text = format_for_llm(query, top_50_candidates)

    # LLM prompt
    prompt = f"""
    Query: {query}

Search Results:
{results_text}

Reorder these by relevance and return the top 5 most relevant, diverse results.
    """

    # Call LLM
    response = llm_client.complete(prompt, max_tokens=500)

    # Parse response
    reranked = json.loads(response)
    return reranked['results'][:5]
```

**Integration:**
```python
class TotalReclawClientV05(TotalReclawClientV02):
    def search(self, query: str, top_k: int = 5):
        # Generate multi-variant blind indices for query
        query_blind_indices = self.generate_multi_variant_blind_indices(query)

        # Pass 1: Remote search
        query_vector = self.generate_embedding(query)
        server_results = self.pass1_remote_search(
            query_vector.tolist(),
            list(query_blind_indices),
            limit=250
        )

        # Pass 2: Local BM25 + RRF
        top_50 = self.pass2_local_bm25(query, server_results, top_k=50)

        # Pass 3: LLM reranking
        top_5 = self.pass3_llm_rerank(query, top_50, self.llm_client)

        return top_5
```

**Acceptance Criteria:**
- Multi-variant blind indices implemented (regex + LLM)
- Three-pass search implemented
- LLM reranking functional
- Ready for comprehensive testing

**Estimated Effort:** 16 hours

---

#### Task 3.2: Comprehensive Evaluation (Days 4-5)

**Subtasks:**

**1. Run All Algorithms:**
   ```python
   algorithms = {
       'bm25_only': bm25_only_search,
       'vector_only': vector_only_search,
       'openclaw_hybrid': openclaw_hybrid_search,
       'qmd_hybrid': qmd_hybrid_search,
       'totalreclaw_v02': totalreclaw_v02_search,
       'totalreclaw_v05': totalreclaw_v05_search
   }

   results = {}
   for name, algorithm in algorithms.items():
       results[name] = []
       for query in test_queries:
           result = algorithm(query, documents, embeddings)
           results[name].append(result)
   ```

**2. Calculate Metrics:**
   For each algorithm and query:
   - Precision, Recall, F1
   - MRR (Mean Reciprocal Rank)
   - Latency (p50, p95, p99)

**3. Statistical Analysis:**
   - Mean performance across all queries
   - Performance by query category
   - Confidence intervals (95%)
   - Statistical significance tests

**4. Generate Comparison Report:**
   - Executive summary
   - Detailed metrics tables
   - Visualizations (charts, graphs)
   - Key findings and insights
   - Recommendations

**Acceptance Criteria:**
- All 6 algorithms evaluated on all 150 queries
- All metrics calculated correctly
- Comprehensive report generated
- Clear go/no-go recommendation

**Estimated Effort:** 12 hours

---

#### Task 3.3: Decision & Documentation (Day 6)

**Subtasks:**

**1. Review Session:**
   - Present findings to stakeholders
   - Review accuracy, latency, trade-offs
   - Discuss implications for MVP development

**2. Go/No-Go Decision:**
   - Based on criteria from testbed spec
   - Document rationale with supporting data
   - Identify next steps

**3. Create Architecture Decision Record:**
   - Selected architecture (v0.2 or v0.5)
   - Rationale for decision
   - Alternative architectures considered
   - Risks and mitigations

**4. Update v0.5 Specification (if GO):**
   - Incorporate learnings from testbed
   - Refine implementation details
   - Add missing sections if needed

**Acceptance Criteria:**
- Go/no-go decision made
- Architecture decision record created
- Stakeholders aligned
- Next steps documented

**Estimated Effort:** 8 hours

**Week 3 Total:** ~52 hours (1.3 weeks)

---

## Part 4: Database Schema

### 4.1 Complete Schema

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main vault table
CREATE TABLE encrypted_vault (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Routing
    vault_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,

    -- Encrypted Data (Zero-Knowledge)
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    tag BYTEA NOT NULL,

    -- Search Indexes (Zero-Knowledge)
    embedding vector(384) NOT NULL,
    blind_indices TEXT[] NOT NULL,

    -- Metadata (plaintext)
    category TEXT NOT NULL,  -- 'chat', 'email', 'calendar', 'personal', 'technical'
    source_file TEXT NOT NULL,  -- original filename
    chunk_index INTEGER NOT NULL,  -- which chunk this is
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT vault_id_check CHECK (vault_id ~ '^[a-zA-Z0-9_-]+$'),
    CONSTRAINT category_check CHECK (category IN ('chat', 'email', 'calendar', 'personal', 'technical'))
);

-- Vector index (HNSW)
CREATE INDEX idx_vault_embedding ON encrypted_vault
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- GIN index for blind indices
CREATE INDEX idx_vault_blind_indices ON encrypted_vault
USING gin (blind_indices gin__int_ops);

-- Routing indexes
CREATE INDEX idx_vault_vault ON encrypted_vault(vault_id);
CREATE INDEX idx_vault_agent ON encrypted_vault(agent_id);
CREATE INDEX idx_vault_category ON encrypted_vault(category);
CREATE INDEX idx_vault_created ON encrypted_vault(created_at DESC);
```

### 4.2 Index Estimation

**For 1,500 memories:**

| Component | Size | Notes |
|-----------|------|-------|
| **Ciphertext** | ~750 KB | 500 bytes × 1,500 |
| **Embeddings** | ~2.3 MB | 1.5 KB × 1,500 |
| **Blind Indices** | ~150 KB | ~100 bytes × 1,500 |
| **Metadata** | ~150 KB | ~100 bytes × 1,500 |
| **Total** | ~3.35 MB | Per user (1,500 memories) |

**With 100 users:** ~335 MB (trivial)
**With 10K users:** ~33.5 GB (manageable with sharding)

---

## Part 5: File Structure

### 5.1 Project Layout

```
totalreclaw-testbed/
├── data/
│   ├── raw/                  # Raw LLM-generated memories
│   ├── processed/             # Chunked and categorized
│   └── test_queries/          # Generated test queries
├── src/
│   ├── algorithms/            # Search algorithm implementations
│   │   ├── bm25_only.py
│   │   ├── vector_only.py
│   │   ├── openclaw_hybrid.py
│   │   ├── qmd_hybrid.py
│   │   ├── totalreclaw_v02.py
│   │   └── totalreclaw_v05.py
│   ├── crypto/                # Cryptographic utilities
│   │   ├── encryption.py
│   │   ├── key_derivation.py
│   │   └── blind_indices.py
│   ├── search/                 # Search utilities
│   │   ├── bm25.py
│   │   ├── vector.py
│   │   └── reranking.py
│   ├── data_generation/       # Synthetic data generation
│   │   ├── memory_generator.py
│   │   └── query_generator.py
│   ├── evaluation/              # Metrics and analysis
│   │   ├── metrics.py
│   │   ├── evaluation.py
│   │   └── reporting.py
│   └── api/                    # REST API (for server simulation)
│       ├── main.py
│       └── routes.py
├── tests/
│   ├── test_algorithms.py
│   ├── test_crypto.py
│   └── test_search.py
├── notebooks/
│   ├── data_analysis.ipynb
│   ├── baseline_comparison.ipynb
│   └── results_visualization.ipynb
├── config/
│   ├── categories.yaml
│   ├── prompts.yaml
│   └── thresholds.yaml
└── docs/
    ├── setup.md
    ├── algorithm_comparison.md
    └── final_report.md
```

---

## Part 6: Deliverables

### 6.1 Week 1 Deliverables

1. **Working Development Environment**
   - PostgreSQL 16 with pgvector
   - Python environment with all dependencies
   - Connection strings and configuration files

2. **4 Baseline Search Implementations**
   - BM25-only
   - Vector-only
   - OpenClaw hybrid
   - QMD-style hybrid

3. **Initial Dataset**
   - 500 test memories (for Week 1 testing)
   - 50 test queries
   - Sample embeddings and indexes

4. **Test Infrastructure**
   - Unit tests for all algorithms
   - Integration tests
   - Performance benchmarking scripts

### 6.2 Week 2 Deliverables

1. **Complete Dataset (1,500 Memories)**
   - All categories represented
   - Embeddings computed and stored
   - Metadata extracted
   - Quality validated

2. **TotalReclaw v0.2 Implementation**
   - Full cryptographic stack
   - Two-pass search
   - Single-variant blind indices
   - Server simulation

3. **Test Query Set (150 Queries)**
   - All categories covered
   - Ground truth labeled
   - Inter-annotator agreement calculated

4. **Partial Evaluation Results**
   - Baseline performance documented
   - TotalReclaw v0.2 performance measured
   - Initial comparison report

### 6.3 Week 3 Deliverables

1. **TotalReclaw v0.5 Implementation**
   - Multi-variant blind indices
   - Three-pass search
   - LLM reranking integration

2. **Comprehensive Evaluation Report**
   - All 6 algorithms compared
   - Metrics by category and overall
   - Statistical analysis
   - Visualizations and charts

3. **Go/No-Go Recommendation**
   - Clear decision with supporting data
   - Architecture decision record
   - Risk assessment

4. **Updated v0.5 Specification**
   - Incorporates testbed learnings
   - Production-ready spec
   - Implementation guide

---

## Part 7: Risk Register

### 7.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|-------|------------|
| **LLM API costs exceed budget** | Medium | Medium | Use local LLM (Ollama, llama.cpp) for most tasks; reserve API calls for critical data generation only |
| **Inter-annotator agreement too low** | Low | High | Clear guidelines, pilot labeling phase, remove ambiguous queries, add more examples |
| **v0.5 latency too high** | Medium | High | Optimize candidate pool size, parallelize decryption, cache LLM responses |
| **Candidate pool (250) too small** | Low | High | Make adaptive based on query complexity; or test with 500 as comparison |
| **PostgreSQL/pgvector setup issues** | Low | Low | Use Docker Compose for reproducible setup; document installation process |
| **Data generation quality issues** | Medium | Medium | Validate with pilot first; manual review of generated samples; iterate on prompts |

### 7.2 Schedule Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|-------|------------|
| **Week 2 overruns (labeling)** | Medium | Medium | Labeling is parallelizable; increase evaluator count; use crowd-sourcing platform if needed |
| **Week 3 overruns (evaluation)** | Low | Medium | Evaluation is automated once ground truth is ready; buffer time for analysis |
| **LLM API rate limiting** | Medium | Medium | Use local LLM for data generation; batch API calls; implement retry logic |

### 7.3 Decision Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|-------|------------|
| **Results are inconclusive** | Low | Critical | Ensure testbed is designed to give clear answers; define success criteria upfront; collect sufficient data |
| **v0.5 significantly underperforms** | Medium | Critical | Have v0.2 as fallback; understand which features are causing issues; iterate and re-test |
| **All variants underperform QMD** | Low | Critical | This would fundamentally challenge the E2EE approach; pivot consideration required |

---

## Part 8: Budget Summary

### 8.1 Personnel Costs

| Role | Hours | Rate | Cost |
|------|-------|------|------|
| **Lead Engineer** | 120 | $100-150/h | $12,000-$18,000 |
| **Evaluator A** | 25 | $15-25/h | $375-$625 |
| **Evaluator B** | 25 | $15-25/h | $375-$625 |
| **Evaluator C** | 25 | $15-25/h | $375-$625 |
| **Stakeholder** | 10 | $150-250/h | $1,500-$2,500 |
| **Total** | **205** | - | **$17,625-$22,875** |

### 8.2 Infrastructure Costs

| Item | Monthly Cost | Total (3 months) |
|------|-------------|-----------------|
| **PostgreSQL hosting** (or compute) | $50 | $150 |
| **LLM API calls** (data generation) | $20 | $60 |
| **Development tools** | $20 | $60 |
| **Domain/SSL** | $10 | $30 |
| **Contingency** | $50 | $150 |
| **Total** | **$150** | **$450** |

### 8.3 Total Budget

**Three-Week Total: $17,775 - $23,325**

**Contingency:** Add 15% buffer to total: $20,450 - $26,850

---

## Part 9: Success Criteria

### 9.1 Week 1 Success Criteria

- [ ] All 4 baseline algorithms implemented and tested
- [ ] 1,500 memories generated and stored with embeddings
- [ ] Test query generation pipeline functional
- [ ] Baseline performance documented

### 9.2 Week 2 Success Criteria

- [ ] TotalReclaw v0.2 fully implemented
- [ ] 150 test queries generated
- [ ] All queries labeled by 3 evaluators
- [ ] Inter-annotator agreement >0.70
- [ ] Partial evaluation report completed

### 9.3 Week 3 Success Criteria

- [ ] TotalReclaw v0.5 fully implemented
- [ ] All 6 algorithms evaluated on all 150 queries
- [ ] Comprehensive report generated
- [ ] Go/no-go decision made
- [ ] Stakeholder alignment achieved

---

## Part 10: Next Steps After Decision

### 10.1 If GO Decision

**Phase 1: MVP Development (Weeks 4-8)
- Implement TotalReclaw v0.5 in production
- Build OpenClaw skill
- Build MCP server
- Create REST API
- Launch beta test

**Phase 2: Launch Preparation (Weeks 9-12)
- Security audit
- Bug bounty program
- Documentation
- Marketing materials
- Launch

**Phase 3: Growth (Months 4-6)
- Scale to 1,000 weekly active users
- Add enterprise features
- Expand to Graph Network

### 10.2 If NO-GO Decision

**Option A: Modify Architecture**
- Increase candidate pool size (250 → 500 or 1000)
- Add server-side enrichment (TDX)
- Accept lower accuracy for E2EE

**Option B: Pivot to Local-First**
- Remove sync feature
- Focus on local-only encryption
- Position as "QMD competitor" but with better UX

**Option C: Defer E2EE**
- Launch plaintext sync first (like QMD)
- Add E2EE as premium feature later
- Build trust with transparency

### 10.3 If MODIFY Decision

**Iteration Cycle:**
1. Identify specific gaps (e.g., fuzzy queries)
2. Implement targeted improvements
3. Re-run testbed with modified architecture
4. Re-evaluate go/no-go criteria

---

## Part 11: Contingency Plans

### 11.1 Week 1 Contingencies

**Risk:** LLM data generation takes longer than expected

**Contingency:**
- Use template-based generation instead of full LLM
- Generate 1,000 memories instead of 1,500
- Extend Week 1 by 2 days

### 11.2 Week 2 Contingencies

**Risk:** Ground truth labeling takes longer than expected

**Contingency:**
- Reduce query set to 100 queries
- Increase evaluator count to 5 (parallelize)
- Use crowd-sourcing platform (Amazon Mechanical Turk, Labelbox)

### 11.3 Week 3 Contingencies

**Risk:** TotalReclaw v0.5 implementation takes longer than expected

**Contingency:**
- Focus on v0.2 evaluation first
- Defer v0.5 to Week 4
- Make decision based on v0.2 results only

---

## Part 12: Post-Testbed Activities

### 12.1 If GO Decision

**Immediate Actions:**
1. Create GitHub repository for TotalReclaw SaaS
2. Set up CI/CD pipeline
3. Create product roadmap
4. Begin MVP development (8-week timeline)

### 12.2 If NO-GO Decision

**Immediate Actions:**
1. Document lessons learned
2. Document alternative architectures
3. Decide on pivot direction
4. Communicate with stakeholders

### 12.3 If MODIFY Decision

**Immediate Actions:**
1. Document specific gaps identified
2. Propose architectural modifications
3. Estimate effort for modifications
4. Plan testbed iteration

---

## Appendix: Task Checklist

### Week 1 Checklist

- [ ] PostgreSQL 16 with pgvector installed
- [ ] Python environment created with dependencies
- [ ] Database schema created
- [ ] Data generation script implemented
- [ ] 1,500 memories generated
- [ ] Embeddings computed and stored
- [ ] BM25-only baseline implemented
- [ ] Vector-only baseline implemented
- [ ] OpenClaw hybrid baseline implemented
- [ ] QMD-style hybrid baseline implemented
- [ ] Test infrastructure created
- [ ] Unit tests written
- [ ] Sample data tested (50 queries)

### Week 2 Checklist

- [ ] Data generation scaled to 1,500 memories
- [ ] Data quality validated
- [ ] Test query set generated (150 queries)
- [ ] Labeling interface created
- [ ] Evaluators recruited
- [ ] Ground truth labeling completed
- [ ] Inter-annotator agreement calculated
- [ ] TotalReclaw v0.2 implemented
- [ ] Cryptographic core tested
- [ ] Two-pass search implemented
- [ ] Integration testing completed
- [ ] Partial evaluation report

### Week 3 Checklist

- [ ] TotalReclaw v0.5 implemented
- [ ] Multi-variant blind indices implemented
- [ ] LLM reranking integrated
- [ ] Three-pass search tested
- [ ] All 6 algorithms evaluated
- [ ] Metrics calculated for all queries
- [ ] Statistical analysis completed
- [ ] Comparison report generated
- [ ] Go/no-go decision made
- [ ] Stakeholder review completed
- [ ] Architecture decision record created
- [ ] Next steps documented

---

**Document Control:**

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2026-02-18 | Initial implementation plan with 3x scaled testbed | TotalReclaw Team |
