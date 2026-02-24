# OpenMemory — Task Tracker

> **Source of truth for all agents.** Read this file first. Claim tasks before starting work. Update status as you go.

**Last updated:** 2026-02-24 (session 3)
**Roadmap:** See `docs/ROADMAP.md` for the full product roadmap.

---

## How to Use This File

1. Read this file at session start
2. Claim a task: set `owner: your-agent-id` and `status: in_progress`
3. When done: set `status: completed` and log in CHANGELOG.md
4. If blocked: note the blocker and move on

---

## Phase Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1-3 | Research + Data Processing + Validation | COMPLETED |
| Phase 4 | PoC Core (Server + Client + Skill) | COMPLETED |
| Phase 5 | Benchmark Harness (OMBH) | COMPLETED |
| Phase 6 | NanoClaw + MCP Integration | COMPLETED (except T054, T056, T058, T059) |
| Phase 7 | Mem0 Competitive Benchmark | PARTIALLY COMPLETE (retrieval done, E2E needs redo) |
| Phase 7B | PoC Completion (v0.3.1b) | COMPLETED — 76 tests |
| Phase 8 | Repo Split & Deployment | COMPLETED |
| Phase 9 | Claw Hub Publishing | PENDING (some prep done) |
| Phase 10 | Server Production Hardening (MVP) | COMPLETED — 142 tests, SlowAPI replaced with per-user limits |
| Phase 11 | Subgraph (Decentralized) | COMPLETED — 92 tests, code done, deployment blocked on credentials |
| Phase 12 | MVP Polish & Ship | IN PROGRESS — /v1/ prefix, /export pagination, DB backup, OpenAPI, rate limit observability |

---

## Completed Phases (Summary)

| Phase | Tasks | Key Result |
|-------|-------|------------|
| Phase 1-3 | T001-T029 | WhatsApp/Slack data processed, LSH validated, specs written |
| Phase 4 | T030-T035 | Server (FastAPI+Postgres), Client (TS, E2EE, LSH), OpenClaw skill — 526 tests |
| Phase 5 | T040-T048 | OMBH benchmark: OpenMemory 98.1% Recall@8 with full E2EE privacy |

---

## Phase 6: NanoClaw + MCP Integration (MOSTLY COMPLETE)

Remaining tasks only. T050-T053, T055, T057 are completed (MCP server, NanoClaw skill, integration tests, LLM client, credentials).

| ID | Task | Status | Owner | Blocker | Plan Reference |
|----|------|--------|-------|---------|----------------|
| T054 | Real server integration tests | blocked | — | Needs running OpenMemory server | — |
| T056 | CLAUDE.md sync testing (preCompact hook) | pending | — | — | — |
| T058 | Namespace migration tool | pending | — | — | — |
| T059 | Rollback by import_id | pending | — | — | — |

---

## Phase 7: Mem0 Competitive Benchmark (PARTIALLY COMPLETE)

**Plan:** `plans/2026-02-23-mem0-competitive-benchmark.md`

Retrieval-only benchmark complete (T060-T064). E2E benchmark ran but results not representative. See `docs/ROADMAP.md` section 2.2 for lessons learned.

| ID | Task | Status | Owner | Blocker | Plan Reference |
|----|------|--------|-------|---------|----------------|
| T066 | Final benchmark report | pending | — | Needs E2E re-run with host agent LLM | Deferred to pre-MVP |
| T067 | QMD adapter (real implementation) | pending | — | — | Deferred |
| T068 | Mem0 self-hosted comparison (Docker) | pending | — | — | Deferred |

**Retrieval-only results (validated):**

| Backend | Recall@8 | Latency | Privacy |
|---------|----------|---------|---------|
| OpenMemory E2EE | 98.1% | 4.1ms | 100 |
| Mem0 Platform | 0.0%* | 459ms | 0 |
| Vector-only (baseline) | 100.0% | 1.0ms | 0 |

*Mem0 0% context: Mem0 extracts atomic facts (242 from 8727), fundamentally different approach.

---

## Phase 7B: PoC Completion (v0.3.1b) — COMPLETED

**Plan:** `docs/plans/2026-02-24-poc-completion.md`
**Goal:** Content fingerprint dedup, /sync endpoint, host-agent LLM test. Completes PoC for local testing with friends.
**Dependency chain:** T090 → T094 → T091 → T092 → T093 → T095 → T088

| ID | Task | Status | Owner | Blocker | Plan Reference |
|----|------|--------|-------|---------|----------------|
| T090 | Schema migration (content_fp, sequence_id, agent_id) | completed | claude-opus | — | poc-completion Task 1 |
| T094 | Protobuf schema update | completed | claude-opus | T090 | poc-completion Task 2 |
| T091 | Client content fingerprint derivation (HKDF + HMAC) | completed | claude-opus | T094 | poc-completion Task 3 |
| T092 | Server /store fingerprint dedup check | completed | claude-opus | T090 | poc-completion Task 4 |
| T093 | Server /sync endpoint (delta sync via sequence_id) | completed | claude-opus | T090 | poc-completion Task 5 |
| T095 | Client reconnection protocol | completed | claude-opus | T091, T093 | poc-completion Task 6 |
| T088 | Test host agent LLM extraction | completed | claude-opus | T095 | poc-completion Task 7 |

---

## Phase 8: Repo Split & Deployment — COMPLETED

**Repos pushed (private):** [openmemory-poc](https://github.com/p-diogo/openmemory-poc) (4.6MB, 196 files), [openmemory-specs](https://github.com/p-diogo/openmemory-specs) (11MB, 247 files)

| ID | Task | Status | Owner | Blocker | Plan Reference |
|----|------|--------|-------|---------|----------------|
| T073 | Prepare poc README | completed | claude-opus | — | plans/repo-split-plan.md |
| T074 | Prepare specs README | completed | claude-opus | — | plans/repo-split-plan.md |
| T075 | Create CLAUDE.md for each repo | completed | claude-opus | — | plans/repo-split-plan.md |
| T076 | Migration script (scripts/migrate-repos.sh) | completed | claude-opus | — | plans/repo-split-plan.md |
| T077 | Push to GitHub | completed | claude-opus | — | plans/repo-split-plan.md |

---

## Phase 9: Claw Hub Publishing (PENDING)

T080-T083 completed (YAML frontmatter, README, skill.json, CLAWHUB.md checklist).

| ID | Task | Status | Owner | Blocker | Plan Reference |
|----|------|--------|-------|---------|----------------|
| T084 | Create screenshots (3-5, 1920x1080 PNG) | pending | — | Manual work | — |
| T085 | Create demo video (30-90s) | pending | — | Manual work, optional | — |
| T086 | Make openmemory-poc repo public | blocked | @pdiogo | User action required | — |
| T087 | Submit to Claw Hub for review | blocked | — | T086 (repo must be public) | — |
| T088 | Test skill uses host agent's LLM | pending | — | — | Also in Phase 7B |

---

## Phase 10: Server Production Hardening (MVP) — COMPLETED

**Plan:** `docs/plans/2026-02-24-server-production-hardening.md`
**Goal:** Make the server production-ready for Free MVP launch. Security, reliability, operations.
**Stack:** FastAPI + custom per-user rate limiter + Alembic + prometheus-client, Caddy reverse proxy, Cloudflare CDN/WAF

| ID | Task | Status | Owner | Blocker | Plan Reference |
|----|------|--------|-------|---------|----------------|
| T100 | Rate limiting (per-user, auth_hash keyed — replaced SlowAPI) | completed | claude-opus | — | hardening Task 1 |
| T101 | Request size limits (blob, indices, batch) | completed | claude-opus | — | hardening Task 2 |
| T102 | SQL injection fix in GIN query (trapdoor validation) | completed | claude-opus | — | hardening Task 3 |
| T103 | Fix audit logging (raw_events commit + call sites) | completed | claude-opus | — | hardening Task 4 |
| T104 | Account deletion endpoint (GDPR — DAY ONE REQUIREMENT) | completed | claude-opus | — | hardening Task 5 |
| T105 | Secrets management (docker-compose, .env) | completed | claude-opus | — | hardening Task 6 |
| T106 | Caddy reverse proxy setup | completed | claude-opus | — | hardening Task 7 |
| T107 | Cloudflare configuration guide | completed | claude-opus | — | hardening Task 8 |
| T108 | Structured JSON logging | completed | claude-opus | — | hardening Task 9 |
| T109 | Prometheus metrics | completed | claude-opus | — | hardening Task 10 |
| T110 | Database migrations (Alembic) | completed | claude-opus | — | hardening Task 11 |
| T111 | Connection pool tuning | completed | claude-opus | — | hardening Task 12 |
| T112 | Environment-specific configuration (dev/staging/prod) | completed | claude-opus | — | hardening Task 13 |

---

## Phase 11: Subgraph Kickoff (Decentralized) — COMPLETED

**Plan:** `docs/plans/2026-02-24-subgraph-kickoff.md`
**Goal:** Scaffold decentralized infrastructure — smart contracts on Base L2, subgraph indexer, client seed management.
**Stack:** Solidity (Hardhat), TypeScript, AssemblyScript, GraphQL, viem, bip39
**Prerequisites:** Pimlico API key, Base Sepolia ETH, Graph Node or The Graph Studio

| ID | Task | Status | Owner | Blocker | Plan Reference |
|----|------|--------|-------|---------|----------------|
| T120 | Project scaffolding (contracts/ + subgraph/) | completed | claude-opus | — | subgraph Task 1 |
| T121 | EventfulDataEdge.sol smart contract | completed | claude-opus | T120 | subgraph Task 2 |
| T122 | Custom Paymaster contract | completed | claude-opus | T120 | subgraph Task 3 |
| T123 | Contract deployment scripts (Base Sepolia testnet) | completed | claude-opus | T121, T122 | subgraph Task 4 |
| T124 | Subgraph schema + AssemblyScript mapping | completed | claude-opus | T121 | subgraph Task 5 |
| T125 | Client BIP-39 seed generation + key derivation | completed | claude-opus | — | subgraph Task 6 |
| T126 | Client UserOperation builder | completed | claude-opus | T121, T125 | subgraph Task 7 |
| T127 | Server /relay endpoint | completed | claude-opus | T121 | subgraph Task 8 |

---

## Phase 12: MVP Polish & Ship — IN PROGRESS

**Goal:** Final polish before repo split and public launch. API versioning, pagination, observability, documentation.

| ID | Task | Status | Owner | Blocker | Notes |
|----|------|--------|-------|---------|-------|
| T130 | Add /v1/ prefix to all API routes | completed | claude-opus | — | Server + client + tests updated. 175 pass |
| T131 | Add cursor-based pagination to /export endpoint | completed | claude-opus | — | Cursor-based, limit 1000/5000. 11 tests |
| T132 | Add rate limit observability (logging + Prometheus counter) | completed | claude-opus | — | rate_limit_hits_total metric + WARNING logs. 7 tests |
| T133 | Database backup/restore scripts + documentation | completed | claude-opus | — | backup.sh + restore.sh + cron + docs. Verified |
| T134 | Export and commit OpenAPI spec (openapi.json) | completed | claude-opus | — | 12 endpoints, 57KB |
| T135 | Rebuild Docker image with all new endpoints | completed | claude-opus | — | All Phase 7B, 10, 12 changes |
| T136 | Alembic migration for v0.3.1b schema (content_fp, sequence_id, agent_id) | completed | claude-opus | — | Applied to running DB |
| T137 | Configure production CORS origins | pending | @pdiogo | Needs domain decision | — |
| T138 | GitHub Actions CI workflow | pending | — | T073-T077 (repo split) | Basic: pytest + npm test on push |
| T139 | Client/skill/mcp API paths to /v1/ | completed | claude-opus | — | Done as part of T130 (client.ts + sync.ts updated) |
| T140 | PoC testing guide for friends | completed | claude-opus | — | docs/poc-testing-guide.md |

---

## Session 3 — Security Audit & Fixes

**Audit:** 4 parallel agents scanned the full codebase. Found 3 critical, 5 high, 9 medium issues.

| ID | Task | Status | Notes |
|----|------|--------|-------|
| T150 | Security audit (4 parallel agents) | completed | 3 critical, 5 high, 9 medium findings |
| T151 | Fix deleted users auth bypass (is_deleted check) | completed | database.py — 3 queries fixed |
| T152 | Fix timing side-channel (hmac.compare_digest) | completed | auth.py |
| T153 | Extract shared get_current_user dependency | completed | New src/dependencies.py |
| T154 | Remove hardcoded API keys from source | completed | testbed files cleaned |
| T155 | Comprehensive .gitignore overhaul | completed | Root + server/.dockerignore + testbed/.gitignore |
| T156 | Parameterize GIN SQL query | completed | database.py — :trapdoors::text[] |
| T157 | Fix X-Forwarded-For spoofing | completed | trusted_proxies config + middleware |
| T158 | Sanitize error messages (5 locations) | completed | relay, health, register, bundler, Content-Length |
| T159 | Fix .env.example rate limit vars | completed | Matches config.py now |
| T160 | Remove docker-compose version deprecation | completed | |
| T161 | Fix PoC testing guide auth format | completed | Bearer prefix |
| T162 | Move contracts/subgraph to feature branch | completed | feature/subgraph branch |
| T163 | Fix sequence_id NULL insertion | in_progress | SQLAlchemy server_default fix |
| T164 | Fix README (Protobuf→JSON, remove subgraph refs) | in_progress | |
| T165 | E2E test with OpenClaw | pending | NEXT: full end-to-end with skill |

---

## Notes for Next Agent

- **Plans are in `docs/plans/`** — Each phase has a detailed implementation plan with exact code, file paths, test commands, and commit messages. Read the plan before starting work.
- **ROADMAP is in `docs/ROADMAP.md`** — For the big picture (PoC -> MVP -> Subgraph -> TEE). Updated 2026-02-24 with current status of all gaps.
- **Specs are in `docs/specs/`** — Organized by product: `openmemory/`, `subgraph/`, `tee/`, `archive/`.
- **Rate limiting:** SlowAPI was removed and replaced with per-user rate limiting in `server/src/middleware/rate_limit.py`. Keyed on auth_hash, not IP. Cloudflare handles IP-level DDoS protection at the edge.
- **Cloudflare free tier:** IP-based rate limiting only (1 rule, 10s window). Per-user/header-based rate limiting requires Enterprise. That's why we do per-user limiting at the app level.
- **Subgraph (Phase 11):** Code moved to `feature/subgraph` branch. Not in PoC main. Testnet deployment blocked on Pimlico API key + Base Sepolia ETH.
- **Mem0 benchmark (T066):** Deferred to pre-MVP. Current E2E results are not representative (29/500 facts indexed, 502 errors). See lessons learned in ROADMAP.md section 2.2.
- **Docker image needs rebuild** after sequence_id fix (T163).
- **E2E testing with OpenClaw is the next priority** — Must verify the full flow: OpenClaw skill -> fact extraction -> encrypt -> store -> new conversation -> search -> decrypt -> recall. This is the critical path before sharing with testers.
- **sequence_id fix** — SQLAlchemy was inserting None, bypassing PostgreSQL nextval(). Fix: server_default=text("nextval('facts_sequence_id_seq')").
- **README was pushed to GitHub** with corrections (JSON not Protobuf, subgraph on branch).
- **All security audit fixes are in the monorepo** but NOT yet pushed to GitHub POC repo. Next session should rebuild Docker, verify, then push updated server code.
- **Next session priorities (in order):**
  1. T163: Fix sequence_id NULL insertion + rebuild Docker
  2. Push security fixes to GitHub POC repo
  3. T165: E2E test with OpenClaw (critical path before sharing with testers)
  4. Create automated E2E test scripts
  5. T138: GitHub Actions CI workflow
- **Completed session 3:** T135, T134, T136, T073-T077, T140 (deployment), T150-T162 (security audit + fixes). 21 tasks completed.
- **Completed session 2:** T090-T095, T088 (Phase 7B), T100-T112 (Phase 10), T120-T127 (Phase 11), T130-T133, T139 (Phase 12). 33 tasks completed.
- **Test count:** 836+ tests across all packages. 0 failures. 23 errors are pre-existing integration tests needing PostgreSQL (run inside Docker).
