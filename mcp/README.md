# @openmemory/mcp-server

MCP (Model Context Protocol) server for OpenMemory - zero-knowledge encrypted memory.

## Installation

```bash
npm install @openmemory/mcp-server
```

## Usage

### With Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openmemory": {
      "command": "npx",
      "args": ["-y", "@openmemory/mcp-server"],
      "env": {
        "OPENMEMORY_SERVER_URL": "http://localhost:8080",
        "OPENMEMORY_MASTER_PASSWORD": "your-secure-password"
      }
    }
  }
}
```

### With NanoClaw

See the `@openmemory/skill-nanoclaw` package for NanoClaw integration.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENMEMORY_SERVER_URL` | OpenMemory server URL | `http://127.0.0.1:8080` |
| `OPENMEMORY_MASTER_PASSWORD` | Master password for encryption | Required |
| `OPENMEMORY_NAMESPACE` | Default namespace | `default` |
| `OPENMEMORY_CREDENTIALS_PATH` | Path to store credentials | `/workspace/.openmemory/credentials.json` |

## Available Tools

### openmemory_remember

Store a fact in encrypted memory.

```json
{
  "fact": "User prefers dark mode",
  "importance": 7,
  "namespace": "work"
}
```

### openmemory_recall

Search memories semantically.

```json
{
  "query": "user preferences",
  "k": 8,
  "min_importance": 5
}
```

### openmemory_forget

Delete a memory.

```json
{
  "fact_id": "uuid-of-fact"
}
```

### openmemory_export

Export all memories for portability.

```json
{
  "format": "markdown"
}
```

### openmemory_import

Import memories from backup.

```json
{
  "content": "...",
  "format": "json",
  "merge_strategy": "skip_existing"
}
```

## Development

```bash
npm run build    # Build the package
npm test         # Run tests
npm run lint     # Lint code
```

## License

MIT
