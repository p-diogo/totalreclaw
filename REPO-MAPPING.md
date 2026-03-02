# Repository File Mapping

**Updated**: 2026-02-24 (paths updated after repo reorganization)

This document maps the current monolithic repository structure to the two new repositories.

---

## Repo 1: totalreclaw-poc (Code)
**URL**: https://github.com/p-diogo/openmemory-poc

### Root Files (totalreclaw-poc/)

| File | Action | Notes |
|------|--------|-------|
| `README-poc.md` | -> `README.md` | POC readme |
| `.gitignore-poc` | -> `.gitignore` | POC gitignore |
| `requirements.txt` | Include | Python dependencies |
| `.env.example` | Include | Environment template |
| `demo_v02.py` | Include | Demo script |
| `README_INFRASTRUCTURE.md` | Include | Infrastructure docs |
| `README.md` | **SKIP** | Superseded by README-poc.md |
| `.env` | **DO NOT COMMIT** | Credentials |
| `.DS_Store` | **DO NOT COMMIT** | macOS metadata |

### Directories (totalreclaw-poc/)

| Directory | Action | Notes |
|-----------|--------|-------|
| `server/` | Include | Python/FastAPI server |
| `client/` | Include | TypeScript client library |
| `skill/` | Include | OpenClaw skill |
| `skill-nanoclaw/` | Include | NanoClaw skill |
| `mcp/` | Include | Generic MCP server |
| `tests/` | Include | Integration tests |
| `testbed/functional-test/` | Include as `tests/functional/` | Functional tests (rename) |
| `database/` | Include | Database infrastructure |

### Docs Subset (totalreclaw-poc/docs/)

Only code-related docs go to poc:

| Source | Target | Notes |
|--------|--------|-------|
| `docs/nanoclaw-memory-system.md` | `docs/nanoclaw-memory-system.md` | NanoClaw design |
| `docs/IMPLEMENTATION_SUMMARY.md` | `docs/IMPLEMENTATION_SUMMARY.md` | Implementation notes |
| `docs/nanoclaw-production-readiness.md` | `docs/nanoclaw-production-readiness.md` | Production readiness |
| `docs/poc-validation-guide.md` | `docs/poc-validation-guide.md` | Validation guide |

### DO NOT Include in poc

- `archive/` -- Archived prototypes (goes to specs repo)
- `docs/specs/` -- All specs (goes to specs repo)
- `docs/prd.md` -- PRD (goes to specs repo)
- `docs/ROADMAP.md` -- Roadmap (goes to specs repo)
- `docs/SECOND_OPINION_PROMPT.md` -- Review docs (goes to specs repo)
- `docs/TotalReclaw-*.md` -- Phase/improvement docs (goes to specs repo)
- `ombh/` -- Benchmark harness (goes to specs repo)
- `testbed/` (except functional-test) -- Testbed (goes to specs repo)
- `plans/` -- Plans (goes to specs repo)
- `research/` -- Research (goes to specs repo)
- `pitch/` -- Pitch materials (goes to specs repo)
- `.venv/` -- Virtual environment
- `.pytest_cache/` -- Test cache
- `node_modules/` -- Node dependencies
- `*.pyc` -- Python bytecode
- `__pycache__/` -- Python cache
- `.env` -- Credentials

---

## Repo 2: totalreclaw-specs (Private - Methodology)
**URL**: https://github.com/p-diogo/openmemory-specs

### Root Files (totalreclaw-specs/)

| File | Action | Notes |
|------|--------|-------|
| `README-specs.md` | -> `README.md` | Specs readme |
| `.gitignore-specs` | -> `.gitignore` | Specs gitignore |
| `CLAUDE.md` | Include | Project instructions (spec-focused) |
| `TASKS.md` | Include | Live task tracking |
| `CHANGELOG.md` | Include | Change history |

### Directories (totalreclaw-specs/)

| Directory | Action | Notes |
|-----------|--------|-------|
| `docs/` | Include (entire directory) | All documentation |
| `docs/specs/totalreclaw/` | Include | Core specs (architecture, server, skills, benchmark, MCP, conflict-resolution) |
| `docs/specs/subgraph/` | Include | Subgraph / decentralized specs |
| `docs/specs/tee/` | Include | TEE specs |
| `docs/specs/archive/` | Include | Superseded specs |
| `docs/prd.md` | Include | Product Requirements Document |
| `docs/ROADMAP.md` | Include | Project roadmap |
| `ombh/` | Include | Benchmark harness |
| `testbed/` | Include (minus functional-test) | Testbed and validation |
| `plans/` | Include | Implementation plans |
| `research/` | Include | Research notes |
| `pitch/` | Include | Pitch materials |
| `archive/prototypes/v02/` | Include | Prototype v0.2 |
| `archive/prototypes/v05/` | Include | Prototype v0.5 |
| `archive/prototypes/v06/` | Include | Prototype v0.6 |
| `archive/prototypes/infrastructure/` | Include | DB infrastructure prototype |
| `archive/prototypes/db_init.py` | Include | DB init script |

### DO NOT COMMIT (within testbed/ and ombh/)

- `testbed/functional-test/` -- Goes to poc repo instead
- `testbed/output/` -- Generated outputs
- `testbed/reports/` -- Generated reports
- `ombh/output/` -- Benchmark outputs
- `ombh/reports/` -- Benchmark reports
- `testbed/data/*.parquet` -- Large data files
- `testbed/data/*.csv` -- Large data files
- `testbed/data/*.jsonl` -- Large data files

---

## Files NOT Going to Either Repo

| File/Path | Reason |
|-----------|--------|
| `.claude/` | Claude-specific, local configuration |
| `.DS_Store` | macOS metadata |
| `.ruff_cache/` | Linter cache |
| `.pytest_cache/` | Test cache |

---

## Directories That No Longer Exist

These paths appeared in the original mapping but have been reorganized:

| Old Path | New Path | Notes |
|----------|----------|-------|
| `src/totalreclaw_v02/` | `archive/prototypes/v02/` | Archived prototype |
| `src/totalreclaw_v05/` | `archive/prototypes/v05/` | Archived prototype |
| `src/totalreclaw_infrastructure/` | `archive/prototypes/infrastructure/` | Archived prototype |
| `tech specs/` | `docs/specs/` | Reorganized under docs |
| `tech specs/v0.3 (grok)/` | `docs/specs/totalreclaw/` | Split into individual files |
| `tech specs/archive/` | `docs/specs/archive/` | Moved under docs/specs |

---

## Migration Checklist

### Pre-migration
1. [ ] Create both repos on GitHub
2. [ ] Create .gitignore files
3. [ ] Create README templates

### Migration (totalreclaw-poc)
- [ ] `git init` in poc directory
- [ ] Copy files according to mapping
- [ ] Verify `skill-nanoclaw/` and `mcp/` are included
- [ ] Verify `testbed/functional-test/` copied to `tests/functional/`
- [ ] Verify no `node_modules/`, `dist/`, `__pycache__/` copied
- [ ] `git remote add origin git@github.com:p-diogo/totalreclaw-poc.git`
- [ ] `git add .`
- [ ] `git commit -m "Initial commit"`
- [ ] `git push -u origin main`

### Migration (totalreclaw-specs)
- [ ] `git init` in specs directory
- [ ] Copy files according to mapping
- [ ] Verify `docs/specs/` structure is intact (totalreclaw, subgraph, tee, archive)
- [ ] Verify `archive/prototypes/` is included (NOT `src/`)
- [ ] Verify `testbed/functional-test/` is excluded
- [ ] `git remote add origin git@github.com:p-diogo/totalreclaw-specs.git`
- [ ] `git add .`
- [ ] `git commit -m "Initial commit"`
- [ ] `git push -u origin main`

### Post-migration
- [ ] Verify repos are private
- [ ] Test cloning both repos
- [ ] Update any hardcoded paths
- [ ] Verify no credentials in either repo

---

## Notes

### Large Files
The following large/generated file types should be excluded via .gitignore:
- Parquet files (`*.parquet`)
- CSV files in data directories (`*.csv`)
- JSONL files (`*.jsonl`)
- Test outputs and reports

### Credentials
Ensure the following are never committed:
- `.env` files
- `.pem` and `.key` files
- `credentials.json`
- `auth.json`

### Cross-repo References
The totalreclaw-poc README should reference totalreclaw-specs for detailed methodology:
```markdown
## See Also
- [totalreclaw-specs](https://github.com/p-diogo/openmemory-specs) — Technical specifications and methodology
```

The totalreclaw-specs README should reference totalreclaw-poc for working code:
```markdown
## See Also
- [totalreclaw-poc](https://github.com/p-diogo/openmemory-poc) — Working implementation
```
