# OpenMemory

Zero-knowledge encrypted memory vault for AI agents. OpenMemory provides end-to-end encrypted storage and retrieval so AI agents can remember facts across sessions without the server ever seeing plaintext. Think "password manager for AI memory" -- client-side encryption with blind index search.

## Architecture

```
Client (encrypt + LSH)  -->  Server (blind search)  -->  Client (decrypt + rerank)

  1. Extract facts (LLM)          4. Receive blind trapdoors     7. Decrypt candidates
  2. Encrypt (AES-GCM)            5. GIN index lookup             8. BM25 + Cosine score
  3. Generate LSH blind indices   6. Return encrypted candidates  9. RRF fusion -> Top 8
```

## Project Structure

| Directory | Description | Stack |
|-----------|-------------|-------|
| `server/` | API server + PostgreSQL backend | Python, FastAPI, Protobuf |
| `client/` | E2EE client library (encrypt, LSH, blind index, rerank) | TypeScript |
| `skill/` | OpenClaw skill integration | TypeScript |
| `skill-nanoclaw/` | NanoClaw skill integration | TypeScript |
| `mcp/` | MCP server (Claude Desktop, etc.) | TypeScript |
| `contracts/` | On-chain anchor contracts | Solidity, Hardhat |
| `subgraph/` | The Graph Protocol indexer | TypeScript, AssemblyScript |

## Quick Start

```bash
cd server
cp .env.example .env
# Edit .env -- at minimum change POSTGRES_PASSWORD
docker-compose up -d
curl http://localhost:8080/health
```

The server binds to `127.0.0.1:8080` (localhost only). PostgreSQL runs on `127.0.0.1:5432`.

## Testing

```bash
# Server (Python)
cd server && pytest tests/

# Client library
cd client && npm test

# OpenClaw skill
cd skill && npm test

# NanoClaw skill
cd skill-nanoclaw && npm test

# MCP server
cd mcp && npm test

# Smart contracts
cd contracts && npx hardhat test

# Subgraph
cd subgraph && npm test
```

## API

Full OpenAPI spec: [`server/openapi.json`](server/openapi.json)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/register` | POST | Register a new vault (ECDH key exchange) |
| `/v1/store` | POST | Store encrypted facts with blind indices |
| `/v1/search` | POST | Search by blind trapdoors, returns encrypted candidates |
| `/v1/export` | GET | Export all encrypted facts (for backup/migration) |
| `/v1/sync` | GET | Incremental sync (delta since last sync token) |
| `/v1/account` | DELETE | Delete vault and all associated data |
| `/health` | GET | Health check |

All payloads use Protobuf over HTTP. Auth via `Authorization: Bearer <vault_token>`.

## PoC Testing Guide

See [`docs/poc-testing-guide.md`](docs/poc-testing-guide.md) for step-by-step instructions on testing the full E2EE flow end-to-end.

## Performance Targets

| Metric | Target |
|--------|--------|
| Search latency (p95) | <140ms for 1M memories |
| Recall | >=93% of true top-250 |
| Storage overhead | <=2.2x vs plaintext |

## See Also

- [openmemory-specs](https://github.com/p-diogo/openmemory-specs) -- Technical specifications, architecture docs, roadmap, and research
