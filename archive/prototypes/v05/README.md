# OpenMemory v0.5 - Enhanced E2EE Search

## Overview

OpenMemory v0.5 extends v0.2 with:

1. **Multi-Variant Blind Indices** - Generate multiple search variants per entity
   - Fast path: Regex-based variants (lowercase, separators, prefixes)
   - Smart path: LLM-based context-aware variants

2. **Three-Pass Search** - Enhanced search pipeline
   - Pass 1: Remote vector search + blind index boost (~100ms)
   - Pass 2: Local BM25 + RRF fusion (~500ms)
   - Pass 3: LLM reranking (~500ms)

3. **Zero-Knowledge Properties** - Server never sees plaintext
   - All encryption/decryption happens client-side
   - LLM operates locally on decrypted data
   - Uses same LLM the agent already has

## Installation

```bash
# Install dependencies
pip install cryptography numpy

# Optional: For production embedding model
pip install sentence-transformers
```

## Quick Start

```python
from openmemory_v05.client import OpenMemoryClientV05
from openmemory_v02.server import MockOpenMemoryServer

# Initialize
client = OpenMemoryClientV05(
    master_password="your-master-password",
    embedding_model=your_embedding_model,
    llm_client=your_llm_client  # Optional
)

server = MockOpenMemoryServer()
server.create_vault(vault_id=client.vault_id)

# Store a memory
memory_text = """
API Configuration:
- Base URL: https://api.example.com/v1
- Contact: sarah@example.com
- Rate limit: 100 req/min
"""

memory_id = client.store_memory(memory_text, server)

# Search
results = client.search("API config", server, top_k=5)

for result in results:
    print(f"Score: {result.score:.4f}")
    print(f"Content: {result.content[:200]}...")
    print()
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPENMEMORY v0.5 ARCHITECTURE                │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐    ┌──────────────────────┐
│   CLIENT-SIDE        │    │   SERVER-SIDE        │
│   (Local Node)        │    │   (OpenMemory SaaS)  │
│                      │    │                      │
│ ┌──────────────────┐  │    │ ┌──────────────────┐ │
│ │ LLM Integration │  │    │ │ PostgreSQL +     │ │
│ │ (Agent's LLM)    │  │    │ │ pgvector         │ │
│ └──────────────────┘  │    │ └──────────────────┘ │
│                      │    │                      │
│ ┌──────────────────┐  │    │                      │
│ │ Crypto Engine    │  │    │                      │
│ │ • AES-256-GCM    │  │    │                      │
│ │ • HKDF KDF       │  │    │                      │
│ │ • HMAC-SHA256    │  │    │                      │
│ └──────────────────┘  │    │                      │
│                      │    │                      │
│ ┌──────────────────┐  │    │                      │
│ │ Search Engine    │  │    │                      │
│ │ • 3-Pass Search  │  │    │                      │
│ │ • BM25 Reranker  │  │    │                      │
│ │ • RRF Fusion     │  │    │                      │
│ │ • LLM Reranking  │  │    │                      │
│ └──────────────────┘  │    │                      │
│                      │    │                      │
│ ┌──────────────────┐  │    │                      │
│ │ Blind Index Gen  │  │    │                      │
│ │ • Regex Variants │  │    │                      │
│ │ • LLM Variants   │  │    │                      │
│ └──────────────────┘  │    │                      │
│                      │    │                      │
└──────────────────────┘    │                      │
         │ mTLS                │
         └─────────────────────┘
```

## Multi-Variant Blind Indices

### Regex-Based Variants (Fast Path)

For entity `user@example.com`:
- `user@example.com` (full, lowercase)
- `user` (local part)
- `example.com` (domain)

For entity `ERR-503`:
- `err-503` (lowercase)
- `503` (numeric part)

### LLM-Based Variants (Smart Path)

For entity `Photo Backup Tool`:
- `photo backup`
- `backup tool`
- `photo sync`
- `backup automation`

For entity `ERR-503`:
- `rate limit`
- `service unavailable`
- `503 error`

## Three-Pass Search

### Pass 1: Remote Vector Search (~100ms)

```python
# Server-side (encrypted)
- HNSW KNN on query embedding
- Blind index exact-match check
- Returns top 250 candidates (ciphertext only)
```

### Pass 2: Local BM25 + RRF (~500ms)

```python
# Client-side (decrypted)
- Decrypt all 250 candidates
- BM25 keyword search on plaintext
- RRF fusion: score = 1/(60+vector) + 1/(60+bm25)
- Returns top 50 candidates
```

### Pass 3: LLM Reranking (~500ms)

```python
# Client-side (LLM-powered)
- Send query + top 50 to LLM
- LLM reranks by relevance and diversity
- Returns top 5 with explanations
```

## API Reference

### OpenMemoryClientV05

```python
class OpenMemoryClientV05:
    def __init__(
        self,
        master_password: str,
        api_url: str = None,
        embedding_model = None,
        vault_id: str = None,
        llm_client = None
    )

    def store_memory(
        self,
        plaintext: str,
        server,
        embedding: np.ndarray = None,
        use_llm_variants: bool = True
    ) -> str

    def search(
        self,
        query: str,
        server,
        top_k: int = 5,
        candidate_pool_size: int = 250,
        use_llm_rerank: bool = True,
        use_llm_query_expansion: bool = False
    ) -> List[SearchResult]
```

### MultiVariantBlindIndexGenerator

```python
class MultiVariantBlindIndexGenerator:
    def __init__(self, blind_key: bytes, llm_client=None)

    def generate_blind_indices(
        self,
        text: str,
        use_llm: bool = True
    ) -> Set[str]

    def generate_query_blind_indices(
        self,
        query: str,
        use_llm: bool = False
    ) -> Set[str]
```

### LLMReranker

```python
class LLMReranker:
    def __init__(self, llm_client, max_candidates: int = 50, top_k: int = 5)

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        use_llm: bool = True
    ) -> List[RerankedResult]
```

## LLM Integration

OpenMemory v0.5 is designed to work with the agent's existing LLM:

```python
# Example with Anthropic Claude
class AnthropicLLMClient:
    def complete(self, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key="your-key")
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

# Use with OpenMemory
client = OpenMemoryClientV05(
    master_password="password",
    embedding_model=embedding_model,
    llm_client=AnthropicLLMClient()
)
```

## Performance

Expected latency breakdown:

| Pass | Operation | Time |
|------|-----------|------|
| 1 | Remote vector search | ~100ms |
| 2 | Decrypt + BM25 + RRF | ~500ms |
| 3 | LLM reranking | ~500ms |
| **Total** | | **~1.1s** |

## Testing

```bash
# Run integration tests
cd src/openmemory_v05/tests
python test_integration.py

# Run benchmark
python ../benchmark.py
```

## Backward Compatibility

v0.5 is backward compatible with v0.2:
- Same encryption keys
- Same blind index format (extended with variants)
- Same API contract
- Opt-in LLM features

## License

MIT License - See LICENSE file for details.
