# TotalReclaw - Project Guide for AI Agents

> **CRITICAL: All agents MUST read this file at the start of every session.**
> **CRITICAL: All agents MUST update TASKS.md and CHANGELOG.md as they work.**

---

## Project Overview

**TotalReclaw** is a zero-knowledge encrypted memory vault for AI agents -- the "password manager for AI memory."

### Core Value Proposition
1. **Encrypted** -- Zero-knowledge E2EE. Server never sees plaintext.
2. **Portable** -- One-click plain-text export. No vendor lock-in.
3. **Universal** -- Works across OpenClaw, Claude Desktop, any MCP-compatible agent.

### Target Users
- Non-technical hosted OpenClaw users (memory locked to Railway/Vercel)
- Power users with multiple AI agents (fragmented memory across tools)

---

## Architecture (v0.3)

```
+-------------------------------------------------------------------------+
|                           CLIENT (OpenClaw Skill)                       |
+-------------------------------------------------------------------------+
|  +--------------+  +--------------+  +--------------+  +-------------+ |
|  | Fact Extract |->|   Encrypt    |->| Generate LSH |->| Blind Index | |
|  |    (LLM)     |  |  (AES-GCM)  |  |   Buckets    |  |  (SHA-256)  | |
|  +--------------+  +--------------+  +--------------+  +-------------+ |
|                              |                                          |
|                              v                                          |
|                    JSON over HTTP                                       |
+-------------------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------------------+
|                        SERVER (TotalReclaw)                             |
+-------------------------------------------------------------------------+
|  PostgreSQL Tables:                                                     |
|  - raw_events (immutable log, future DataEdge events)                  |
|  - facts (mutable view with blind_indices, decay_score)                |
|                                                                         |
|  Search Flow:                                                           |
|  blind_trapdoors -> GIN index lookup -> return encrypted candidates    |
+-------------------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------------------+
|                         CLIENT (Re-ranking)                             |
+-------------------------------------------------------------------------+
|  Decrypt 400-5000 candidates -> BM25 + Cosine + RRF fusion -> Top 8   |
+-------------------------------------------------------------------------+
```

---

## Repository Structure

This is the **product code** repository. Internal tooling (benchmarks, testbed, archive)
lives in [totalreclaw-internal](https://github.com/p-diogo/totalreclaw-internal).

```
/totalreclaw
├── CLAUDE.md              # THIS FILE - Read first!
├── TASKS.md               # Live task tracking (todo, in-progress, blocked)
├── CHANGELOG.md           # Change history
│
├── server/                # FastAPI + PostgreSQL backend
├── client/                # TypeScript client library (E2EE, LSH, embeddings)
├── skill/                 # OpenClaw plugin (PoC v2: embedding, LSH, reranker)
├── skill-nanoclaw/        # NanoClaw skill package + MCP server
│   ├── src/               # Hooks, extraction logic
│   └── mcp/               # Self-contained MCP server (totalreclaw-mcp.ts)
├── mcp/                   # Generic MCP server (for Claude Desktop, etc.)
├── contracts/             # Solidity smart contracts (EventfulDataEdge, Paymaster)
├── subgraph/              # Graph Node indexer (AssemblyScript mappings)
├── database/              # Database schema (schema.sql)
├── tests/                 # Integration tests
│   ├── e2e-functional/    # E2E functional test suite (66/66 + 130/130 assertions)
│   └── parity/            # Parity tests (plugin vs NanoClaw)
│
└── docs/                  # Specs and guides
    ├── specs/
    │   ├── totalreclaw/   # Core product specs (architecture, server, skills, MCP)
    │   ├── subgraph/      # Subgraph specs (seed-to-subgraph, billing)
    │   └── tee/           # TEE specs (architecture, TDX SaaS)
    ├── deployment/        # Deployment guides (backup, Cloudflare)
    ├── guides/            # User-facing guides (beta tester guide)
    ├── analysis/          # Cost analysis and projections
    ├── prd.md             # Product Requirements Document
    └── ROADMAP.md         # Phased roadmap
```

## Related Repositories

| Repo | Purpose | URL |
|------|---------|-----|
| `totalreclaw-internal` | Benchmarks, testbed, research, archive, plans | [github.com/p-diogo/totalreclaw-internal](https://github.com/p-diogo/totalreclaw-internal) |
| `totalreclaw-website` | Landing page | [github.com/p-diogo/totalreclaw-website](https://github.com/p-diogo/totalreclaw-website) |

---

## Agent Coordination Rules

### MANDATORY for ALL Agents

1. **READ FIRST** -- At session start, read:
   - This file (CLAUDE.md)
   - TASKS.md (understand current state)
   - CHANGELOG.md (understand recent changes)

2. **UPDATE AS YOU WORK** (real-time, not at the end):
   - Claim tasks in TASKS.md (set `owner` and `status: in_progress`) BEFORE starting work
   - Log all changes in CHANGELOG.md with timestamp
   - Release tasks when done (`status: completed`)
   - **This enables parallel agents** -- if another agent is running concurrently, it checks TASKS.md to avoid conflicts

3. **PERSIST STATE IN FILES** -- Never keep state only in memory. If an agent crashes, another must be able to resume from TASKS.md.

4. **COMMUNICATE VIA CHANGELOG** -- If you need to leave a message for the next agent, put it in CHANGELOG.md.

5. **ALWAYS DELEGATE TO SUBAGENTS -- NEVER DO IMPLEMENTATION IN THE MAIN SESSION** -- Use the Task tool to delegate ALL implementation work, research, and testing to subagents. The main session is ONLY for coordination, decision-making, and user communication. This is a hard rule, not a suggestion. Launch multiple agents in parallel when tasks are independent.

6. **COMPACTION PROTOCOL** -- Whenever the user says "prepare for compaction" (or similar), you MUST:
   - Update TASKS.md with current status of all in-progress work
   - Update CHANGELOG.md with everything done in the current session
   - This is mandatory because multiple agents work on this project in parallel -- the files are the shared state.

---

## Current Technical Specifications

Specs are organized by product area under `docs/specs/`:

### TotalReclaw (E2EE) -- `docs/specs/totalreclaw/`
| Spec | File | Status |
|------|------|--------|
| E2EE Architecture (LSH + Blind Buckets) | `architecture.md` | Implemented, validated |
| Server PoC v0.3.1b (Auth + Dedup) | `server.md` | Partially implemented |
| OpenClaw Skill | `skill-openclaw.md` | Implemented |
| NanoClaw Skill | `skill-nanoclaw.md` | Implemented |
| MCP Server | `mcp-server.md` | Implemented |
| MCP Auto-Memory (Generic Hosts) | `mcp-auto-memory.md` | Spec complete |
| Benchmark Harness (OMBH) | `benchmark.md` | Implemented |
| Benchmark v2 Improvements | `benchmark-v2-improvements.md` | Spec complete |
| LSH Tuning (Multi-Tenant SaaS) | `lsh-tuning.md` | Complete |
| Conflict Resolution v0.3.2 | `conflict-resolution.md` | Design complete, not implemented |
| Retrieval Improvements v3 | `retrieval-improvements-v3.md` | Implemented (13/13 tasks) |
| MCP Onboarding | `mcp-onboarding.md` | Spec complete, not started |
| E2E Test Plan v2 (Billing) | `e2e-test-plan-v2.md` | Implemented (130/130 assertions) |

### Subgraph (Decentralized) -- `docs/specs/subgraph/`
| Spec | File | Status |
|------|------|--------|
| Seed-to-Subgraph v1.0 | `seed-to-subgraph.md` | Implemented, deployed to Chiado testnet |
| Billing & Onboarding | `billing-and-onboarding.md` | Implemented (Stripe + Coinbase) |
| Paymaster Comparison | `paymaster-comparison.md` | Complete (Pimlico chosen) |

### TEE (Trusted Execution) -- `docs/specs/tee/`
| Spec | File | Status |
|------|------|--------|
| TEE vs E2EE Comparison | `architecture.md` | Analysis complete |
| TDX SaaS v0.4 | `tdx-saas.md` | Spec complete, not started |

---

## Known Technical Gaps

| Gap | Severity | Status |
|-----|----------|--------|
| LSH parameters | RESOLVED | 32-bit x 20 tables, 98.1% Recall@8 on real data |
| Authentication | RESOLVED | HKDF auth with SHA-256 key hashing |
| Conflict resolution (Layers 3-4) | MEDIUM | Spec'd in v0.3.2, not implemented |
| Mem0 competitive benchmark | MEDIUM | Retrieval-only done, E2E deferred |
| Load testing | MEDIUM | Not done -- need to validate <140ms p95 |
| Graceful shutdown | LOW | Not yet configured in uvicorn |

---

## Key Constraints

- **Search latency**: <140ms p95 for 1M memories
- **Recall**: >=93% of true top-250
- **Storage overhead**: <=2.2x vs plaintext
- **Zero-knowledge**: Server NEVER sees plaintext

---

## Commands

```bash
# Server
pip install -r requirements.txt -r server/requirements.txt
cd server && python -m pytest tests/ -v

# Client library
cd client && npm install && npm test

# OpenClaw plugin
cd skill/plugin && npm install && npm test

# MCP server
cd mcp && npm install && npm run build

# NanoClaw skill
cd skill-nanoclaw && npm install
```

---

## Contact & Context

- **User**: @pdiogo
- **Project started**: February 2026
- **Current phase**: Post Session 24 -- All phases complete, ship prep + MCP onboarding next (see TASKS.md)
- **Current version**: v0.2.0 (PoC v2)

---

## Recovery Instructions (If Session Crashes)

If you're a new agent picking up this project:

1. **READ FIRST**:
   - This file (CLAUDE.md)
   - TASKS.md -- see current status
   - CHANGELOG.md -- see what's been done

2. **Current Phase**: Check TASKS.md for current phase

3. **Key Files**:
   - Tech specs: `docs/specs/totalreclaw/` (core), `docs/specs/subgraph/`, `docs/specs/tee/`
   - PRD: `docs/prd.md`
   - Roadmap: `docs/ROADMAP.md`
   - Plans: In [totalreclaw-internal](https://github.com/p-diogo/totalreclaw-internal) repo under `plans/`
   - Benchmarks/testbed: In [totalreclaw-internal](https://github.com/p-diogo/totalreclaw-internal) repo

4. **Before Starting Work**:
   - Claim tasks in TASKS.md (set owner and status: in_progress)
   - Check if dependencies are complete

5. **After Completing Work**:
   - Mark tasks complete in TASKS.md
   - Log changes in CHANGELOG.md
   - Update any affected documentation
