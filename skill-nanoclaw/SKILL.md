# TotalReclaw Skill for NanoClaw

This skill adds zero-knowledge encrypted memory to NanoClaw using the generic TotalReclaw MCP Server.

## Installation

1. Install the TotalReclaw MCP server:
   ```bash
   npm install @totalreclaw/mcp-server
   ```

2. Configure environment variables:
   ```bash
   TOTALRECLAW_SERVER_URL=http://localhost:8080
   TOTALRECLAW_MASTER_PASSWORD=your-secure-password
   TOTALRECLAW_NAMESPACE=${groupFolder}
   ```

3. Add MCP server to NanoClaw config

## Hooks

### before-agent-start
Retrieves relevant memories before processing user message.

### agent-end
Extracts and stores facts periodically after agent turns.

### pre-compact
Full extraction before context truncation.

## Namespace Mapping

The skill maps NanoClaw's `groupFolder` to TotalReclaw's `namespace`:
- `main` → `main` namespace
- `work` → `work` namespace
- `family` → `family` namespace

This provides memory isolation between different contexts.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TOTALRECLAW_SERVER_URL` | TotalReclaw server URL | `http://127.0.0.1:8080` |
| `TOTALRECLAW_MASTER_PASSWORD` | Master password for encryption | Required |
| `TOTALRECLAW_NAMESPACE` | Default namespace | `default` |
| `TOTALRECLAW_AUTO_EXTRACT` | Enable automatic extraction | `true` |
| `TOTALRECLAW_EXTRACT_INTERVAL` | Turns between extractions | `5` |

## Usage

The agent automatically has access to these MCP tools:
- `totalreclaw_remember` - Store a fact
- `totalreclaw_recall` - Search memories
- `totalreclaw_forget` - Delete a memory
- `totalreclaw_export` - Export vault
- `totalreclaw_import` - Import from backup
