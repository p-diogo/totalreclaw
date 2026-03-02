# TotalReclaw

**Zero-knowledge encrypted memory vault for AI agents** — the "password manager for AI memory."

## Current Status

**Phase 5 Complete** — PoC ready for benchmark validation. Core implementation finished with 526 tests passing.

| Component | Status | Tests |
|-----------|--------|-------|
| Server (FastAPI + PostgreSQL) | ✅ Complete | 133 |
| Client (TypeScript, E2EE) | ✅ Complete | 87 |
| OpenClaw Skill | ✅ Complete | 300 |
| Benchmark Harness (OMBH) | ✅ Ready | - |

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
openclaw skill install .
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT (OpenClaw Skill)                       │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Fact Extract │→ │   Encrypt    │→ │ Generate LSH │→ │ Blind Index │ │
│  │    (LLM)     │  │ (AES-256-GCM)│  │   Buckets    │  │  (SHA-256)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
                               │ HTTP + Protobuf
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        SERVER (FastAPI + PostgreSQL)                    │
├─────────────────────────────────────────────────────────────────────────┤
│  • facts (encrypted_ciphertext, blind_indices[], decay_score)          │
│  • Search: blind_trapdoors → GIN index → encrypted candidates          │
└─────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Re-ranking)                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Decrypt candidates → BM25 + Cosine + RRF fusion → Top K results       │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **E2EE with AES-256-GCM** | Server never sees plaintext facts or embeddings |
| **LSH Blind Indices** | Search encrypted data using locality-sensitive hashing |
| **Client-side Re-ranking** | BM25 + cosine similarity + RRF fusion |
| **Export/Import** | One-click plaintext export. No vendor lock-in. |
| **MCP Server** | Works with Claude Desktop, OpenClaw, any MCP client |
| **Argon2id KDF** | Memory-hard key derivation from master password |

## Repository Structure

```
totalreclaw/
├── client/          # TypeScript client library (E2EE, LSH, search)
├── server/          # Python/FastAPI server (PostgreSQL, protobuf API)
├── skill/           # OpenClaw skill integration (MemOS-style hooks)
├── mcp/             # Model Context Protocol server
├── ombh/            # TotalReclaw Benchmark Harness
├── docs/            # Documentation, PRD, and all specs
│   ├── specs/totalreclaw/  # Core E2EE product specs
│   ├── specs/subgraph/    # Decentralized storage specs
│   ├── specs/tee/         # TEE product specs
│   └── specs/archive/     # Superseded specs
├── archive/         # Old prototypes (v02, v05, v06)
├── testbed/         # Testing & validation data
├── plans/           # Implementation plans
└── research/        # Research notes
```

## Validation Results

LSH parameters validated on combined WhatsApp + Slack dataset (8,727 embeddings):

| Metric | Result | Target |
|--------|--------|--------|
| Recall | 93.6% (P5: 84.4%) | ≥93% |
| Query Latency | 9.71ms | <50ms |
| Storage Overhead | 0.06x | ≤2.2x |

**Validated Configuration**: `n_bits=64, n_tables=12, candidate_pool=3000`

## Performance Targets

| Metric | Target |
|--------|--------|
| Search latency (p95) | <140ms for 1M memories |
| Recall | ≥93% of true top-250 |
| Storage overhead | ≤2.2x vs plaintext |

## Repositories

| Repo | Description |
|------|-------------|
| [totalreclaw-poc](https://github.com/p-diogo/openmemory-poc) | Code (client, server, skill) |
| [totalreclaw-specs](https://github.com/p-diogo/openmemory-specs) | Technical specifications & methodology |

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

- **[architecture.md](./docs/specs/totalreclaw/architecture.md)** — E2EE with LSH + Blind Buckets (zero-knowledge search)
- **[server.md](./docs/specs/totalreclaw/server.md)** — Server PoC v0.3.1b (Auth + Dedup)
- **[skill-openclaw.md](./docs/specs/totalreclaw/skill-openclaw.md)** — MemOS-style lifecycle hooks
- **[benchmark.md](./docs/specs/totalreclaw/benchmark.md)** — Benchmark Harness (OMBH)
- **[conflict-resolution.md](./docs/specs/totalreclaw/conflict-resolution.md)** — Multi-Agent Conflict Resolution v0.3.2
- **[mcp-server.md](./docs/specs/totalreclaw/mcp-server.md)** — Generic MCP Server
- **[skill-nanoclaw.md](./docs/specs/totalreclaw/skill-nanoclaw.md)** — NanoClaw Skill

## Testing

```bash
# Client tests
cd client && npm test

# Server tests  
cd server && pytest tests/

# Skill tests
cd skill && npm test

# Integration tests (Docker)
cd testbed/functional-test && ./run-tests.sh
```

## License

MIT
