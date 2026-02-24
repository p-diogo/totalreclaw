# OpenMemory PoC - Agent Guide

OpenMemory is a zero-knowledge encrypted memory vault for AI agents. The server never sees plaintext -- all encryption, LSH hashing, and re-ranking happen client-side. The server stores encrypted blobs with blind indices and performs GIN index lookups on blind trapdoors. This is the CODE repo containing the deployable server, client library, skills, smart contracts, and subgraph.

## Architecture

```
Client (encrypt + LSH)  -->  Server (blind search)  -->  Client (decrypt + rerank)

  1. Extract facts (LLM)          4. Receive blind trapdoors     7. Decrypt candidates
  2. Encrypt (AES-GCM)            5. GIN index lookup             8. BM25 + Cosine score
  3. Generate LSH blind indices   6. Return encrypted candidates  9. RRF fusion -> Top 8
```

## Directory Structure

| Directory | Description | Stack |
|-----------|-------------|-------|
| `server/` | API server + PostgreSQL backend | Python 3.11+, FastAPI, Protobuf, Alembic |
| `client/` | E2EE client library (encrypt, LSH, blind index, rerank) | TypeScript, Node 20+ |
| `skill/` | OpenClaw skill integration | TypeScript |
| `skill-nanoclaw/` | NanoClaw skill integration | TypeScript |
| `mcp/` | MCP server for Claude Desktop and MCP-compatible agents | TypeScript |
| `contracts/` | On-chain anchor contracts | Solidity, Hardhat |
| `subgraph/` | The Graph Protocol indexer | TypeScript, AssemblyScript |
| `docs/` | API docs, testing guides | Markdown |
| `tests/` | Cross-package integration tests | Python |

## Commands

### Development

```bash
# Server (Python)
cd server
pip install -r requirements.txt
python -m src.main

# Client / Skill / MCP (TypeScript)
cd client && npm install && npm run build
cd skill && npm install && npm run build
cd skill-nanoclaw && npm install && npm run build
cd mcp && npm install && npm run build

# Contracts
cd contracts && npm install && npx hardhat compile

# Subgraph
cd subgraph && npm install && npm run codegen && npm run build
```

### Testing

```bash
# Server
cd server && pytest tests/

# TypeScript packages
cd client && npm test
cd skill && npm test
cd skill-nanoclaw && npm test
cd mcp && npm test

# Contracts
cd contracts && npx hardhat test

# Subgraph
cd subgraph && npm test

# Integration tests
pytest tests/
```

### Docker

```bash
cd server
cp .env.example .env
# Edit .env -- change POSTGRES_PASSWORD at minimum
docker-compose up -d
curl http://localhost:8080/health
```

Server binds to `127.0.0.1:8080`, PostgreSQL to `127.0.0.1:5432`.

## Key Constraints

- **Search latency**: <140ms p95 for 1M memories
- **Recall**: >=93% of true top-250
- **Storage overhead**: <=2.2x vs plaintext
- **Zero-knowledge**: Server NEVER sees plaintext. No exceptions.

## Current Phase

**MVP Polish (Phase 12)** -- Server, client, skills, MCP, contracts, and subgraph are implemented. Focus is on hardening, testing, and PoC deployment.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/register` | POST | Register vault (ECDH key exchange) |
| `/v1/store` | POST | Store encrypted facts with blind indices |
| `/v1/search` | POST | Search by blind trapdoors |
| `/v1/export` | GET | Export all encrypted facts |
| `/v1/sync` | GET | Incremental sync |
| `/v1/account` | DELETE | Delete vault and all data |

Protobuf over HTTP. Auth via `Authorization: Bearer <vault_token>`.

Full spec: `server/openapi.json`

## Agent Rules

- **WHENEVER POSSIBLE, ALWAYS LAUNCH AGENTS FOR TASKS TO SAVE CONTEXT.** Delegate sub-tasks to agent threads rather than doing everything in a single session.
- Do not modify files outside this repo without explicit permission.
- Run tests after making changes. Do not commit broken code.
- Keep commits small and focused. One logical change per commit.

## Specs and Roadmap

Full technical specifications, architecture docs, PRD, and roadmap live in the separate specs repo:
[openmemory-specs](https://github.com/p-diogo/openmemory-specs)

Key specs to reference:
- `architecture.md` -- E2EE with LSH + Blind Buckets
- `server.md` -- Server PoC v0.3.1b (Auth + Dedup)
- `skill-openclaw.md` -- OpenClaw skill integration
- `mcp-server.md` -- MCP server spec
- `benchmark.md` -- Benchmark Harness (OMBH)
