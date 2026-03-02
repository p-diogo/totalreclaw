# TotalReclaw Functional Testing Guide

## Overview

Functional tests validate the complete end-to-end flow between OpenClaw (AI agent) and TotalReclaw (memory backend).

**Difference from Integration Tests:**
- Integration tests use **mock** OpenClaw context
- Functional tests use **real** OpenClaw instance in Docker

## Prerequisites

1. **Docker** installed and running
2. **OpenClaw repository** cloned (see below)
3. **Z.AI API key** (GLM-5 Coding Plan subscription)

## One-Time Setup

```bash
# 1. Navigate to functional test directory
cd /Users/pdiogo/Documents/code/totalreclaw/testbed/functional-test

# 2. Clone OpenClaw (required - it's a separate project)
git clone https://github.com/openclaw/openclaw.git openclaw

# 3. Set your API key
export ZAI_API_KEY=your_key_here
```

## Running Tests

```bash
# Run all functional tests
./run-tests.sh

# Run with verbose output
./run-tests.sh --verbose

# Run without cleanup (for debugging)
./run-tests.sh --skip-cleanup
```

## Test Scenarios

### Scenario 1: Health Check
**What it tests:** Both services start and respond
- TotalReclaw server: `GET /health`
- OpenClaw: Agent responds to ping

### Scenario 2: Basic Conversation
**What it tests:** OpenClaw processes messages without memory
- User sends message
- Agent responds
- No memory storage expected (below threshold)

### Scenario 3: Memory Storage
**What it tests:** Automatic fact extraction and storage
- User states preference (Turn 5+)
- Extraction triggered
- Memory encrypted and stored on server
- Server logs show only ciphertext

### Scenario 4: Memory Retrieval
**What it tests:** before_agent_start hook retrieves memory
- New session starts
- User asks about stored preference
- Memory injected into context
- Agent answers using memory

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Docker Network: totalreclaw-internal (no internet access)   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  OpenClaw       │    │  TotalReclaw     │                │
│  │  (port 8081)    │───▶│  Server         │                │
│  │                 │    │  (port 8080)    │                │
│  │  + Skill        │    │                 │                │
│  └─────────────────┘    └────────┬────────┘                │
│                                  │                          │
│                         ┌────────▼────────┐                │
│                         │  PostgreSQL 16  │                │
│                         │  (encrypted     │                │
│                         │   storage)      │                │
│                         └─────────────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │                              │
    localhost:8081               localhost:8080
    (your machine)               (your machine)
```

## Security Notes

- **No internet access**: All services on internal Docker network
- **Localhost only**: Ports bound to 127.0.0.1, not 0.0.0.0
- **Read-only filesystems**: OpenClaw cannot modify host files
- **No privileges**: `no-new-privileges` security option

## Extending Tests

### Rule: Extend on Every New Feature

**When to add new test scenarios:**
- New tool added to skill (e.g., `totalreclaw_search_by_date`)
- New lifecycle hook (e.g., `on_user_login`)
- New server endpoint (e.g., `POST /batch-store`)
- New encryption feature (e.g., key rotation)
- New retrieval feature (e.g., temporal filters)

**How to add a new scenario:**

1. Add scenario to `run-tests.sh`:
```bash
run_scenario_5_key_rotation() {
    log_info "Testing key rotation..."
    # Test implementation
}
```

2. Add expected behavior to `/skill/tests/fixtures/conversations.ts`

3. Update this document with scenario description

### Test Scenario Template

```markdown
### Scenario N: [Feature Name]
**What it tests:** [One-line description]
**Prerequisites:** [Any special setup]
**Steps:**
1. [User action]
2. [Expected system behavior]
3. [Verification]
**Success criteria:** [How to know it passed]
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "OpenClaw repo not found" | Run `git clone https://github.com/openclaw/openclaw.git openclaw` |
| "ZAI_API_KEY not set" | Export your key: `export ZAI_API_KEY=...` |
| "Port 8080 already in use" | Stop other services: `docker-compose down` |
| "Health check timeout" | Check logs: `docker-compose logs totalreclaw-server` |

## Files Reference

| File | Purpose |
|------|---------|
| `docker-compose.functional-test.yml` | Docker services config |
| `openclaw-config/agents.yaml` | OpenClaw agent settings |
| `run-tests.sh` | Test runner script |
| `TESTING-GUIDE.md` | This file |
