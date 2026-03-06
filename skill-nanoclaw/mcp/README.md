# NanoClaw TotalReclaw MCP Server

Self-contained stdio MCP server that provides zero-knowledge encrypted memory
tools for NanoClaw agents.

## Architecture

This is a single-file MCP server (`totalreclaw-mcp.ts`) with all crypto logic
inlined (no dependency on `@totalreclaw/client`). This design was chosen because
NanoClaw's agent-runner spawns MCP servers as child processes via stdio, and
keeping the server self-contained minimizes deployment complexity.

## Files

| File | Purpose |
|------|---------|
| `totalreclaw-mcp.ts` | Self-contained MCP server (crypto + API + 4 tools) |
| `nanoclaw-agent-runner.ts` | Modified NanoClaw agent-runner that registers this MCP server |
| `SKILL.md` | Agent instructions (auto-recall, when to remember) |

## Dependencies

- `@modelcontextprotocol/sdk` (already in NanoClaw agent-runner)
- `@noble/hashes` (must be added to NanoClaw Docker image)
- `@scure/bip39` (for BIP-39 mnemonic support)

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `TOTALRECLAW_MASTER_PASSWORD` | Yes | — |
| `TOTALRECLAW_SERVER_URL` | No | `http://totalreclaw-server:8080` |
| `TOTALRECLAW_NAMESPACE` | No | `default` |

## Testing

The full Docker test harness lives in the `totalreclaw-internal` repo (private, maintainers only) at
`testbed/functional-test-nanoclaw/`. See `run-pipeline-test.sh` for the
32-test TAP pipeline validation.
