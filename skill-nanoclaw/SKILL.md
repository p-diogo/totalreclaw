# OpenMemory Skill for NanoClaw

This skill adds zero-knowledge encrypted memory to NanoClaw using the generic OpenMemory MCP Server.

## Installation

1. Install the OpenMemory MCP server:
   ```bash
   npm install @openmemory/mcp-server
   ```

2. Configure environment variables:
   ```bash
   OPENMEMORY_SERVER_URL=http://localhost:8080
   OPENMEMORY_MASTER_PASSWORD=your-secure-password
   OPENMEMORY_NAMESPACE=${groupFolder}
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

The skill maps NanoClaw's `groupFolder` to OpenMemory's `namespace`:
- `main` → `main` namespace
- `work` → `work` namespace
- `family` → `family` namespace

This provides memory isolation between different contexts.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENMEMORY_SERVER_URL` | OpenMemory server URL | `http://127.0.0.1:8080` |
| `OPENMEMORY_MASTER_PASSWORD` | Master password for encryption | Required |
| `OPENMEMORY_NAMESPACE` | Default namespace | `default` |
| `OPENMEMORY_AUTO_EXTRACT` | Enable automatic extraction | `true` |
| `OPENMEMORY_EXTRACT_INTERVAL` | Turns between extractions | `5` |

## Usage

The agent automatically has access to these MCP tools:
- `openmemory_remember` - Store a fact
- `openmemory_recall` - Search memories
- `openmemory_forget` - Delete a memory
- `openmemory_export` - Export vault
- `openmemory_import` - Import from backup
