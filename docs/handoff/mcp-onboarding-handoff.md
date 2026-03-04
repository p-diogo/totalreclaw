# Handoff: MCP Onboarding Implementation

## 1. Summary

TotalReclaw is a zero-knowledge encrypted memory vault for AI agents. The MCP server (`mcp/`) lets Claude Desktop, Cursor, and other MCP-compatible hosts use TotalReclaw via tool calls. **MCP onboarding** adds a setup CLI (`npx @totalreclaw/mcp-server setup`), billing tools (`totalreclaw_status`, `totalreclaw_upgrade`), and structured error handling so users can go from zero to working memory in under 2 minutes -- and seamlessly upgrade when they hit the free tier limit.

## 2. Current State

The MCP server is already functional with:

- **5 tools**: `totalreclaw_remember` (batch + single), `totalreclaw_recall`, `totalreclaw_forget`, `totalreclaw_export`, `totalreclaw_import`
- **Full E2EE crypto**: AES-256-GCM encryption, HKDF key derivation, blind indices, LSH bucketing, local MiniLM-L6-v2 embeddings, BM25 + cosine + RRF reranking
- **Server instructions** (Layer 1): `instructions` field in `initialize` response guides LLM auto-recall/store behavior
- **Resources** (Layer 4): `memory://context/summary` resource with 5-min cache, subscription notifications
- **Prompts** (Layer 5): `totalreclaw_start` and `totalreclaw_save` slash commands as fallbacks
- **Tool annotations**: `readOnlyHint`, `destructiveHint`, `idempotentHint` on all tools
- **Auto-registration**: If `TOTALRECLAW_MASTER_PASSWORD` is set but no `credentials.json` exists, the server auto-registers on first run

**Not yet built**: setup CLI, billing integration, `totalreclaw_status` tool, `totalreclaw_upgrade` tool, structured billing-aware error responses.

## 3. What Needs to Be Built

### Phase 1 -- Core (Start Here)

| Task | Description |
|------|-------------|
| **Setup CLI** | `npx @totalreclaw/mcp-server setup` -- interactive CLI that generates a BIP-39 mnemonic (or accepts an existing one), derives keys, saves `credentials.json` to `~/.totalreclaw/`, registers with relay, and prints the MCP client config snippet. Detect via `process.argv[2] === 'setup'` in `index.ts`. |
| **`instructions` billing addendum** | Append billing guidance to `SERVER_INSTRUCTIONS` in `prompts.ts`: "If a remember call fails with quota error, offer to call totalreclaw_upgrade." |
| **Structured error responses** | Implement `not_configured`, `free_tier_quota_exceeded`, `subscription_expired`, `server_unreachable` error codes. All errors include human-readable `message` + actionable `upgrade_url` or `docs_url`. |
| **Quota warning pass-through** | When relay returns `quota_warning` in a successful write response, include it in the tool result. |

### Phase 2 -- Billing Tools

| Task | Description |
|------|-------------|
| **`totalreclaw_status` tool** | Read-only, idempotent. Calls `GET /v1/subscription/status` on the relay. Returns tier, usage stats, upgrade URL. |
| **`totalreclaw_upgrade` tool** | Creates a checkout session via `POST /v1/subscription/checkout`. Accepts `method: "card" | "crypto"`. Returns Stripe or Coinbase Commerce checkout URL. |
| **`getClient()` hardening** | Return structured `not_configured` error instead of crashing when no seed/credentials exist. |

### Phase 3 -- Auto-Memory Enhancements (Lower Priority)

| Task | Description |
|------|-------------|
| **Resources capability** | Already wired, but the `memory://context/summary` resource could be improved with relevance-based query. |
| **Sampling support** | Use `sampling/createMessage` for server-side fact extraction where clients support it (VS Code). |

## 4. Key Specs to Read

| File | What It Covers |
|------|---------------|
| `docs/specs/totalreclaw/mcp-onboarding.md` | **Primary spec.** Full design for setup CLI, billing tools, error handling, user flows. Read this end-to-end. |
| `docs/specs/totalreclaw/mcp-auto-memory.md` | Hybrid 6-layer auto-memory architecture. Layers 1-5 are already implemented. |
| `docs/specs/totalreclaw/mcp-server.md` | Original MCP server spec (tools, prompts, transport). |
| `docs/specs/subgraph/billing-and-onboarding.md` | Billing architecture: Stripe + Coinbase Commerce, relay endpoints, free tier, subscription model. |
| `CLAUDE.md` | Project conventions, repo structure, agent coordination rules. |

## 5. Key Files to Modify

| File | Changes |
|------|---------|
| `mcp/src/index.ts` | Add `process.argv` check for `setup` subcommand. Register `totalreclaw_status` and `totalreclaw_upgrade` tools. Harden `getClient()` error handling. |
| `mcp/src/prompts.ts` | Append billing section to `SERVER_INSTRUCTIONS`. Add descriptions for new tools. |
| `mcp/src/tools/remember.ts` | Pass through `quota_warning` from relay response in tool result. |
| `mcp/package.json` | Add `bin` entry for setup CLI. Add `readline` or `inquirer` dependency if needed for interactive prompts. |

**New files to create:**

| File | Purpose |
|------|---------|
| `mcp/src/cli/setup.ts` | Interactive setup CLI: mnemonic generation/import, credential storage, relay registration, config output. |
| `mcp/src/tools/status.ts` | `handleStatus()` -- calls `GET /v1/subscription/status` on relay, returns tier + usage. |
| `mcp/src/tools/upgrade.ts` | `handleUpgrade()` -- calls `POST /v1/subscription/checkout`, returns checkout URL. |

## 6. Architecture Decisions Already Made

- **BIP-39 mnemonic** for key derivation (same as OpenClaw skill). The mnemonic is the user's recovery phrase.
- **`credentials.json`** stores only `userId` + `salt` (NOT the mnemonic). Mnemonic provided at runtime via `TOTALRECLAW_MASTER_PASSWORD` env var.
- **Pimlico** paymaster for gas-sponsored relay transactions (decided Session 21, 60x cheaper than ZeroDev).
- **Stripe** for card payments, **Coinbase Commerce** for crypto payments.
- **Relay server** is authoritative for subscription status. No client-side caching of subscription state.
- **Read operations (`recall`) are never metered** -- only writes are gated by quota.
- **Single binary with argv detection** -- `setup` is a subcommand, not a separate package.
- **Hybrid 6-layer approach** for auto-memory (instructions, tool descriptions, batch tools, resources, prompts, sampling). Layers 1-5 are implemented.

## 7. Testing Approach

1. **Build check**: `cd mcp && npm run build` -- must compile without errors.
2. **Existing tests**: `cd mcp && npm test` -- existing tests must still pass.
3. **New unit tests**: Add tests for setup CLI (mock fs/readline), status/upgrade handlers (mock relay responses), error formatting.
4. **Manual test with Claude Desktop**: Configure `claude_desktop_config.json` with the MCP server. Verify:
   - Server starts and returns `instructions` in initialize response
   - `totalreclaw_status` returns subscription info
   - `totalreclaw_remember` with quota exhausted returns structured error with upgrade URL
   - `totalreclaw_upgrade` returns checkout URL
5. **Setup CLI test**: Run `npx @totalreclaw/mcp-server setup` and verify it generates a mnemonic, saves credentials, prints config snippet.

## 8. Environment Setup

```bash
# Install dependencies
cd mcp && npm install

# Build
npm run build

# Run tests
npm test

# Start the MCP server (for manual testing)
TOTALRECLAW_MASTER_PASSWORD="test mnemonic words here" \
TOTALRECLAW_SERVER_URL="http://127.0.0.1:8080" \
node dist/index.js

# Test the setup CLI
node dist/index.js setup
```

The MCP server depends on `@totalreclaw/client` (linked from `../client`). If you get import errors, run `cd ../client && npm install && npm run build` first.

**Note**: The relay server (`server/`) must be running for integration tests. For unit tests, mock the HTTP calls. The server can be started with `cd server && python -m uvicorn main:app --port 8080`.

### Key env vars

| Variable | Purpose | Default |
|----------|---------|---------|
| `TOTALRECLAW_MASTER_PASSWORD` | BIP-39 mnemonic for key derivation | Required (or credentials.json) |
| `TOTALRECLAW_SERVER_URL` | Relay server URL | `http://127.0.0.1:8080` |
| `TOTALRECLAW_CREDENTIALS_PATH` | Path to credentials.json | `/workspace/.totalreclaw/credentials.json` |
| `TOTALRECLAW_NAMESPACE` | Default namespace | `default` |
