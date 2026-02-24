# OpenMemory - Project Guide for AI Agents

> **CRITICAL: All agents MUST read this file at the start of every session.**
> **CRITICAL: All agents MUST update TASKS.md and CHANGELOG.md as they work.**

---

## Project Overview

**OpenMemory** is a zero-knowledge encrypted memory vault for AI agents — the "password manager for AI memory."

### Core Value Proposition
1. **Encrypted** — Zero-knowledge E2EE. Server never sees plaintext.
2. **Portable** — One-click plain-text export. No vendor lock-in.
3. **Universal** — Works across OpenClaw, Claude Desktop, any MCP-compatible agent.

### Target Users
- Non-technical hosted OpenClaw users (memory locked to Railway/Vercel)
- Power users with multiple AI agents (fragmented memory across tools)

---

## Architecture (v0.3)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT (OpenClaw Skill)                       │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Fact Extract │→ │   Encrypt    │→ │ Generate LSH │→ │ Blind Index │ │
│  │    (LLM)     │  │  (AES-GCM)   │  │   Buckets    │  │  (SHA-256)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
│                              │                                          │
│                              ▼                                          │
│                    Protobuf over HTTP                                   │
└─────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        SERVER (OpenMemory PoC)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL Tables:                                                     │
│  • raw_events (immutable log, future DataEdge events)                  │
│  • facts (mutable view with blind_indices, decay_score)                │
│                                                                         │
│  Search Flow:                                                           │
│  blind_trapdoors → GIN index lookup → return encrypted candidates      │
└─────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Re-ranking)                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Decrypt 400-1200 candidates → BM25 + Cosine + RRF fusion → Top 8      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
/openmemory
├── CLAUDE.md              # THIS FILE - Read first!
├── TASKS.md               # Live task tracking (todo, in-progress, blocked)
├── CHANGELOG.md           # Complete change history
├── plans/                 # Implementation plans (rename to *-complete.md when done)
│
├── docs/                  # All documentation and specs
│   ├── prd.md             # Product Requirements Document
│   ├── ROADMAP.md         # Phased roadmap
│   ├── specs/
│   │   ├── openmemory/    # Core E2EE product specs
│   │   │   ├── architecture.md      # E2EE with LSH + Blind Buckets
│   │   │   ├── server.md            # Server PoC v0.3.1b (Auth + Dedup)
│   │   │   ├── skill-openclaw.md    # OpenClaw skill integration
│   │   │   ├── skill-nanoclaw.md    # NanoClaw skill integration
│   │   │   ├── mcp-server.md        # Generic MCP server
│   │   │   ├── benchmark.md         # Benchmark Harness (OMBH)
│   │   │   └── conflict-resolution.md # Multi-Agent Conflict Resolution v0.3.2
│   │   ├── subgraph/     # Decentralized storage specs
│   │   │   └── seed-to-subgraph.md  # Seed-to-Subgraph v1.0
│   │   ├── tee/           # Trusted Execution Environment specs
│   │   │   ├── architecture.md      # TEE vs E2EE comparison
│   │   │   ├── tdx-saas.md          # TDX SaaS v0.4
│   │   │   └── grok-tee-notes.md    # TEE edition notes
│   │   └── archive/       # Superseded specs
│   │       ├── server-no-auth-superseded.md
│   │       ├── v02-saas-e2ee.md
│   │       ├── v02-ts-e2ee-horizon.md
│   │       ├── v03-prd-tdx-horizon.md
│   │       ├── gtm-strategy.md
│   │       └── landing-page.md
│   └── *.md               # Other documentation files
│
├── server/                # Server PoC (FastAPI + PostgreSQL)
├── client/                # TypeScript client library
├── skill/                 # OpenClaw skill
├── mcp/                   # MCP server package
├── skill-nanoclaw/        # NanoClaw skill package
├── ombh/                  # Benchmark harness
│
├── archive/               # Archived prototypes
│   └── prototypes/
│       ├── v02/           # Old v0.2 prototype
│       ├── v05/           # Old v0.5 prototype
│       ├── v06/           # Old v0.6 prototype
│       └── infrastructure/ # Old DB infrastructure
│
├── testbed/               # Testing & benchmarking
│   ├── v2-realworld-data/ # WhatsApp data + processing scripts
│   ├── baseline/          # Baseline algorithms (BM25, vector)
│   └── src/               # Testbed source code
│
├── research/              # Research notes
└── pitch/                 # Pitch materials
```

---

## Agent Coordination Rules

### MANDATORY for ALL Agents

1. **READ FIRST** — At session start, read:
   - This file (CLAUDE.md)
   - TASKS.md (understand current state)
   - CHANGELOG.md (understand recent changes)

2. **UPDATE AS YOU WORK**:
   - Claim tasks in TASKS.md (set `owner` and `status: in_progress`)
   - Log all changes in CHANGELOG.md with timestamp
   - Release tasks when done (`status: completed`)

3. **PERSIST STATE IN FILES** — Never keep state only in memory. If an agent crashes, another must be able to resume from TASKS.md.

4. **PLANS IN /plans/** — All implementation plans go in `/plans/`. Rename to `XXXX-complete.md` when finished.

5. **COMMUNICATE VIA CHANGELOG** — If you need to leave a message for the next agent, put it in CHANGELOG.md.

6. **WHENEVER POSSIBLE, ALWAYS LAUNCH AGENTS FOR TASKS TO SAVE CONTEXT** — Use the Task tool to delegate implementation work to subagents. This preserves the main conversation's context window for coordination. Launch multiple agents in parallel when tasks are independent. The main agent should coordinate, not implement.

---

## Current Technical Specifications

Specs are organized by product area under `docs/specs/`:

### OpenMemory (E2EE) — `docs/specs/openmemory/`
| Spec | File | Status |
|------|------|--------|
| E2EE Architecture (LSH + Blind Buckets) | `architecture.md` | Implemented, validated |
| Server PoC v0.3.1b (Auth + Dedup) | `server.md` | Partially implemented |
| OpenClaw Skill | `skill-openclaw.md` | Implemented |
| NanoClaw Skill | `skill-nanoclaw.md` | Implemented |
| MCP Server | `mcp-server.md` | Implemented |
| Benchmark Harness (OMBH) | `benchmark.md` | Implemented |
| Conflict Resolution v0.3.2 | `conflict-resolution.md` | Draft spec |

### Subgraph (Decentralized) — `docs/specs/subgraph/`
| Spec | File | Status |
|------|------|--------|
| Seed-to-Subgraph v1.0 | `seed-to-subgraph.md` | Spec complete, not started |

### TEE (Trusted Execution) — `docs/specs/tee/`
| Spec | File | Status |
|------|------|--------|
| TEE vs E2EE Comparison | `architecture.md` | Analysis complete |
| TDX SaaS v0.4 | `tdx-saas.md` | Spec complete, not started |

---

## Known Technical Gaps

| Gap | Severity | Status |
|-----|----------|--------|
| LSH parameters | HIGH | Validated — 98.1% Recall@8 on real data |
| Authentication | HIGH | DONE — HKDF auth with SHA-256 key hashing |
| Conflict resolution (Layers 3-4) | MEDIUM | Spec'd in v0.3.2, not implemented |
| Mem0 competitive benchmark | MEDIUM | Retrieval-only done, E2E deferred |
| Load testing | MEDIUM | Not done — need to validate <140ms p95 |
| Graceful shutdown | LOW | Not yet configured in uvicorn |

---

## Key Constraints

- **Search latency**: <140ms p95 for 1M memories
- **Recall**: ≥93% of true top-250
- **Storage overhead**: ≤2.2× vs plaintext
- **Zero-knowledge**: Server NEVER sees plaintext

---

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Generate embeddings
python testbed/v2-realworld-data/scripts/generate_embeddings.py

# Parse WhatsApp data
python testbed/v2-realworld-data/scripts/parse_whatsapp.py
```

---

## Contact & Context

- **User**: @pdiogo
- **Project started**: February 2026
- **Current phase**: Phase 12 — MVP Polish & Ship (see TASKS.md)

---

## Recovery Instructions (If Session Crashes)

If you're a new agent picking up this project:

1. **READ FIRST**:
   - This file (CLAUDE.md)
   - TASKS.md - see current status
   - CHANGELOG.md - see what's been done
   - `/plans/2026-02-22-poc-implementation-plan.md` - the implementation blueprint

2. **Current Phase**: Check TASKS.md for current phase

3. **Key Files**:
   - Tech specs: `/docs/specs/openmemory/` (core), `/docs/specs/subgraph/`, `/docs/specs/tee/`
   - PRD: `/docs/prd.md`
   - Roadmap: `/docs/ROADMAP.md`
   - Data: `/testbed/v2-realworld-data/processed/`
   - Validation: `/testbed/validation/`
   - Plans: `/plans/`

4. **Before Starting Work**:
   - Claim tasks in TASKS.md (set owner and status: in_progress)
   - Check if dependencies are complete
   - Read the relevant plan in /plans/

5. **After Completing Work**:
   - Mark tasks complete in TASKS.md
   - Log changes in CHANGELOG.md
   - Update any affected documentation
