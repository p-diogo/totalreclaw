# TotalReclaw

**Zero-knowledge encrypted memory vault for AI agents** -- the "password manager for AI memory."

## Current Status

**PoC v2 Complete** -- Full E2EE search pipeline with LSH, embeddings, and hybrid reranking. 343 tests passing.

| Component | Status | Tests |
|-----------|--------|-------|
| Server (FastAPI + PostgreSQL) | Complete | 221 |
| Client (TypeScript, E2EE) | Complete | -- |
| OpenClaw Plugin (PoC v2) | Complete | 38 + 32 + 52 |
| NanoClaw MCP Server | Complete | 32 (TAP) |
| Generic MCP Server | Complete | -- |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 20+
- Python 3.11+

### Run Server

```bash
cd server
docker-compose up -d
# Server at http://localhost:8080
```

### Run Client

```bash
cd client
npm install
npm run build
npm test
```

### Use in OpenClaw

```bash
cd skill
npm install
openclaw plugins enable totalreclaw
```

## Architecture

```
+-------------------------------------------------------------------------+
|                           CLIENT (OpenClaw Skill)                       |
+-------------------------------------------------------------------------+
|  +--------------+  +--------------+  +--------------+  +-------------+ |
|  | Fact Extract |->|   Encrypt    |->| Generate LSH |->| Blind Index | |
|  |    (LLM)     |  | (AES-256-GCM)|  |   Buckets    |  |  (SHA-256)  | |
|  +--------------+  +--------------+  +--------------+  +-------------+ |
+-------------------------------------------------------------------------+
                               | HTTP + JSON
                               v
+-------------------------------------------------------------------------+
|                        SERVER (FastAPI + PostgreSQL)                    |
+-------------------------------------------------------------------------+
|  - facts (encrypted_ciphertext, blind_indices[], encrypted_embedding)  |
|  - Search: blind_trapdoors -> GIN index -> encrypted candidates        |
+-------------------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------------------+
|                         CLIENT (Re-ranking)                             |
+-------------------------------------------------------------------------+
|  Decrypt 400-5000 candidates -> BM25 + Cosine + RRF fusion -> Top K   |
+-------------------------------------------------------------------------+
```

## Key Features

| Feature | Description |
|---------|-------------|
| **E2EE with AES-256-GCM** | Server never sees plaintext facts or embeddings |
| **LSH Blind Indices** | Search encrypted data using locality-sensitive hashing (32-bit x 20 tables) |
| **Local Embeddings** | bge-small-en-v1.5 ONNX model runs client-side (no API keys needed) |
| **Client-side Re-ranking** | BM25 + cosine similarity + RRF fusion with stemmed blind indices |
| **Dynamic Candidate Pool** | 400-5000 candidates based on fact count |
| **Export/Import** | One-click plaintext export. No vendor lock-in. |
| **MCP Server** | Works with Claude Desktop, OpenClaw, any MCP client |
| **BIP-39 Mnemonic** | Same 12-word phrase derives encryption keys and future Ethereum wallet |

## Repository Structure

```
totalreclaw/
├── server/          # FastAPI + PostgreSQL backend
├── client/          # TypeScript client library (E2EE, LSH, embeddings)
├── skill/           # OpenClaw plugin (PoC v2: embedding, LSH, reranker)
├── skill-nanoclaw/  # NanoClaw skill package + self-contained MCP server
├── mcp/             # Generic MCP server (for Claude Desktop, etc.)
├── contracts/       # Solidity contracts (EventfulDataEdge, Paymaster)
├── subgraph/        # Graph Node indexer (AssemblyScript mappings)
├── database/        # Database schema
├── tests/           # Integration tests
└── docs/            # Specs, guides, PRD, roadmap
```

## Benchmark Results

5-way benchmark comparison (TotalReclaw v2 vs Mem0 vs QMD vs LanceDB vs TotalReclaw v1):

| System | Overall Recall | Semantic Recall | Privacy |
|--------|---------------|-----------------|---------|
| TotalReclaw v2 (E2EE) | 24.3% | 24.3% | Zero-knowledge |
| LanceDB (plaintext) | 24.7% | 24.7% | None |
| TotalReclaw v1 (E2EE) | 16.4% | 16.4% | Zero-knowledge |

TotalReclaw v2 achieves within 0.4% of LanceDB's semantic recall while maintaining full zero-knowledge E2EE.

## Related Repositories

| Repo | Description |
|------|-------------|
| [totalreclaw](https://github.com/p-diogo/totalreclaw) | Product code (this repo) |
| [totalreclaw-internal](https://github.com/p-diogo/totalreclaw-internal) | Benchmarks, testbed, research, archive |
| [totalreclaw-website](https://github.com/p-diogo/totalreclaw-website) | Landing page |

## Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](./CLAUDE.md) | Project guide for AI agents |
| [TASKS.md](./TASKS.md) | Live task tracking |
| [CHANGELOG.md](./CHANGELOG.md) | Complete change history |
| [docs/specs/](./docs/specs/) | Technical specifications (by product) |
| [docs/prd.md](./docs/prd.md) | Product Requirements Document |
| [docs/ROADMAP.md](./docs/ROADMAP.md) | Phased roadmap |

### Technical Specs

- **[architecture.md](./docs/specs/totalreclaw/architecture.md)** -- E2EE with LSH + Blind Buckets (zero-knowledge search)
- **[server.md](./docs/specs/totalreclaw/server.md)** -- Server PoC v0.3.1b (Auth + Dedup)
- **[skill-openclaw.md](./docs/specs/totalreclaw/skill-openclaw.md)** -- OpenClaw plugin integration
- **[skill-nanoclaw.md](./docs/specs/totalreclaw/skill-nanoclaw.md)** -- NanoClaw MCP integration
- **[mcp-server.md](./docs/specs/totalreclaw/mcp-server.md)** -- Generic MCP Server
- **[mcp-auto-memory.md](./docs/specs/totalreclaw/mcp-auto-memory.md)** -- MCP Auto-Memory for generic hosts
- **[benchmark.md](./docs/specs/totalreclaw/benchmark.md)** -- Benchmark Harness (OMBH)
- **[conflict-resolution.md](./docs/specs/totalreclaw/conflict-resolution.md)** -- Multi-Agent Conflict Resolution v0.3.2

## Testing

```bash
# Server tests (221 tests)
cd server && pip install -r requirements.txt && python -m pytest tests/ -v

# Plugin E2E tests (38 tests)
cd skill/plugin && npm install && npm test

# LSH tests (32 tests)
cd skill/plugin && npx tsx lsh.test.ts

# Reranker tests (52 tests)
cd skill/plugin && npx tsx reranker.test.ts

# Client tests
cd client && npm install && npm test
```

## License

MIT
