# TotalReclaw Benchmark Harness (OMBH)

A standalone, reproducible benchmark framework for comparing AI memory systems.

## Overview

OMBH runs **identical** multi-session conversations through multiple memory systems and produces publication-grade apples-to-apples leaderboards on:

- **Accuracy** - Factual correctness, preference adherence
- **Latency** - Store and retrieve timing (target: <140ms p95)
- **Storage** - Memory footprint
- **Cost** - Token usage and API costs
- **Privacy** - Zero-knowledge vs plaintext (100% for TotalReclaw)

## The Four Systems (4-Way Benchmark)

| # | System | Port | Memory Backend | Privacy |
|---|--------|------|---------------|---------|
| 1 | **TotalReclaw** | 8081 | TotalReclaw E2EE (blind indices + LSH + BM25/cosine/RRF) | 100% |
| 2 | **Mem0** | 8082 | Mem0 cloud API (LLM-based extraction) | 0% |
| 3 | **QMD** | 8083 | Built-in memory-core (Markdown + vector hybrid) | 0% |
| 4 | **LanceDB** | 8084 | LanceDB vector DB (OpenAI embeddings) | 0% |

All instances use the same LLM provider (Z.AI glm-5) so extraction quality is not a variable.

## Quick Start — 4-Way Benchmark

### 1. Set up environment

```bash
cd ombh
cp .env.example .env
# Edit .env — fill in ALL required keys:
#   ZAI_API_KEY, TOTALRECLAW_MASTER_PASSWORD, OPENAI_API_KEY, MEM0_API_KEY
```

### 2. Build and start all 4 instances

```bash
docker compose -f docker-compose.benchmark.yml build
docker compose -f docker-compose.benchmark.yml up -d
```

This starts all 4 instances:
- **TotalReclaw** on `http://localhost:8081` (+ totalreclaw-server + postgres)
- **Mem0** on `http://localhost:8082` (uses Mem0 cloud API)
- **QMD** on `http://localhost:8083`
- **LanceDB** on `http://localhost:8084`

The Mem0 instance uses a custom Dockerfile (`Dockerfile.openclaw-mem0`) that installs the
`@mem0/openclaw-mem0` plugin during the Docker build. No manual plugin installation needed.

### 3. Verify all instances are healthy

```bash
docker compose -f docker-compose.benchmark.yml ps
# All 6 services should show "healthy"

# Test each instance:
curl -s http://localhost:8081/  # TotalReclaw gateway
curl -s http://localhost:8082/  # Mem0 gateway
curl -s http://localhost:8083/  # QMD gateway
curl -s http://localhost:8084/  # LanceDB gateway
```

### 4. Send a test message via OpenAI-compat API

```bash
curl -s http://localhost:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer benchmark-token-2026" \
  -d '{
    "model": "zai/glm-5",
    "messages": [{"role": "user", "content": "Remember that my name is Alex and I work at Nexus Labs."}]
  }'
```

### 5. Clean up

```bash
docker compose -f docker-compose.benchmark.yml down -v
```

## Mem0 Plugin Setup

The Mem0 plugin (`@mem0/openclaw-mem0`) is **NOT bundled** with the OpenClaw Docker image as of v2026.2.22.
To include it in the benchmark, we use a custom Dockerfile (`Dockerfile.openclaw-mem0`) that:

1. Builds OpenClaw from source (same base as other instances)
2. Installs `@mem0/openclaw-mem0` from npm into the `extensions/openclaw-mem0/` directory
3. The plugin's dependencies (`mem0ai`, `@sinclair/typebox`) are installed alongside it

All 4 instances start together by default -- no profile flag needed.

| Plugin | ID | Bundled | Docker Setup | Notes |
|--------|-----|---------|-------------|-------|
| memory-core (QMD) | `memory-core` | Yes | Base image | Default, no extra deps |
| LanceDB | `memory-lancedb` | Yes | Base image | Needs OPENAI_API_KEY for embeddings |
| TotalReclaw | `totalreclaw` | External | Volume mount | Mounted from `skill/plugin/` |
| Mem0 | `openclaw-mem0` | No | Custom Dockerfile | Installed during build via npm |

### Getting a Mem0 API Key

1. Go to [https://app.mem0.ai](https://app.mem0.ai) and create an account (free tier available)
2. Navigate to Settings > API Keys and create a new key
3. Copy the key to your `.env` file as `MEM0_API_KEY=m0-...`

### How the Mem0 Dockerfile Works

The `Dockerfile.openclaw-mem0` uses Docker's `additional_contexts` feature to reference the
OpenClaw source tree. It builds OpenClaw normally, then installs the Mem0 plugin:

```dockerfile
# Install the Mem0 plugin into the extensions directory
WORKDIR /app/extensions/openclaw-mem0
RUN npm install @mem0/openclaw-mem0@latest
# Copy plugin files from node_modules to the extension root
RUN cp -r node_modules/@mem0/openclaw-mem0/* .
```

This approach keeps the Mem0 instance identical to the others except for the added plugin.

## Directory Structure

```
ombh/
├── docker-compose.benchmark.yml  # 4-way benchmark compose file
├── Dockerfile.openclaw-mem0      # Custom Dockerfile: OpenClaw + Mem0 plugin
├── docker-compose.testbed.yml    # Old 2-way testbed (Phase 5)
├── configs/
│   ├── openclaw-totalreclaw/
│   │   └── config.json5          # TotalReclaw: totalreclaw plugin, memory-core disabled
│   ├── openclaw-mem0/
│   │   └── config.json5          # Mem0: openclaw-mem0 plugin (cloud API)
│   ├── openclaw-qmd/
│   │   └── config.json5          # QMD: memory-core (default, no extra plugins)
│   └── openclaw-lancedb/
│       └── config.json5          # LanceDB: memory-lancedb plugin
├── .env.example                  # Required API keys
├── scripts/
│   └── generate_synthetic_benchmark.py  # Synthetic conversation generator
├── ombh/                         # Python benchmark harness package
└── README.md                     # This file
```

## Configuration Details

Each instance gets its own `config.json5` in `configs/openclaw-<name>/`. All configs share:

- Same LLM model: `zai/glm-5`
- Same gateway token: `benchmark-token-2026`
- Same gateway port: 18789 (internal), mapped to unique external ports
- Chat completions API enabled at `/v1/chat/completions`

Per-instance differences:
- **TotalReclaw**: `plugins.slots.memory = "totalreclaw"`, needs TOTALRECLAW_SERVER_URL + TOTALRECLAW_MASTER_PASSWORD
- **Mem0**: `plugins.slots.memory = "openclaw-mem0"`, needs MEM0_API_KEY (custom Dockerfile installs plugin)
- **QMD**: `plugins.slots.memory = "memory-core"` (default, no extra env vars)
- **LanceDB**: `plugins.slots.memory = "memory-lancedb"`, needs OPENAI_API_KEY for embeddings

## Required API Keys

| Key | Required by | How to get |
|-----|------------|------------|
| `ZAI_API_KEY` | All instances | https://zai.ai |
| `TOTALRECLAW_MASTER_PASSWORD` | TotalReclaw | `cd skill/plugin && npx tsx generate-mnemonic.ts` |
| `OPENAI_API_KEY` | LanceDB | https://platform.openai.com/api-keys |
| `MEM0_API_KEY` | Mem0 | https://app.mem0.ai |
| `POSTGRES_PASSWORD` | TotalReclaw server | Any random string |

## Network Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │            benchmark-internal network        │
                    │                                             │
  :8081 ──────────► │  openclaw-totalreclaw ──► totalreclaw-server │
                    │                              │              │
                    │                              ▼              │
                    │                           postgres ◄── :5434│
                    │                                             │
  :8082 ──────────► │  openclaw-mem0 ──► mem0 cloud API           │
                    │                                             │
  :8083 ──────────► │  openclaw-qmd (self-contained)              │
                    │                                             │
  :8084 ──────────► │  openclaw-lancedb ──► OpenAI API            │
                    └─────────────────────────────────────────────┘
```

All ports bind to 127.0.0.1 only. Never expose to the internet.

## Extending

### Adding a New Backend

```python
from ombh.backends.base import MemoryBackend, BackendType
from ombh.backends.registry import register_backend

@register_backend(BackendType.CUSTOM)
class CustomBackend(MemoryBackend):
    @property
    def backend_type(self) -> BackendType:
        return BackendType.CUSTOM

    @property
    def privacy_score(self) -> int:
        return 50  # Partial privacy

    async def store(self, facts, session_id, user_id):
        # Implement storage
        pass

    async def retrieve(self, query, k, min_importance, session_id, user_id):
        # Implement retrieval
        pass

    # ... other methods
```

## License

MIT
