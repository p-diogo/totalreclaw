# @totalreclaw/mcp-server

MCP (Model Context Protocol) server for TotalReclaw - zero-knowledge encrypted memory.

## Installation

```bash
npm install @totalreclaw/mcp-server
```

## Usage

### With Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "totalreclaw": {
      "command": "npx",
      "args": ["-y", "@totalreclaw/mcp-server"],
      "env": {
        "TOTALRECLAW_SERVER_URL": "http://localhost:8080",
        "TOTALRECLAW_MASTER_PASSWORD": "your-secure-password"
      }
    }
  }
}
```

### With NanoClaw

See the `@totalreclaw/skill-nanoclaw` package for NanoClaw integration.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TOTALRECLAW_SERVER_URL` | TotalReclaw server URL | `http://127.0.0.1:8080` |
| `TOTALRECLAW_MASTER_PASSWORD` | Master password for encryption | Required |
| `TOTALRECLAW_NAMESPACE` | Default namespace | `default` |
| `TOTALRECLAW_CREDENTIALS_PATH` | Path to store credentials | `/workspace/.totalreclaw/credentials.json` |

## Available Tools

### totalreclaw_remember

Store a fact in encrypted memory.

```json
{
  "fact": "User prefers dark mode",
  "importance": 7,
  "namespace": "work"
}
```

### totalreclaw_recall

Search memories semantically.

```json
{
  "query": "user preferences",
  "k": 8,
  "min_importance": 5
}
```

### totalreclaw_forget

Delete a memory.

```json
{
  "fact_id": "uuid-of-fact"
}
```

### totalreclaw_export

Export all memories for portability.

```json
{
  "format": "markdown"
}
```

### totalreclaw_import

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
