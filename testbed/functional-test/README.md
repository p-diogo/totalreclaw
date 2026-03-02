# Functional Testing with Real OpenClaw Instance

This directory contains Docker setup for running functional tests against a real OpenClaw instance integrated with TotalReclaw.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   OpenClaw      │────▶│  TotalReclaw     │────▶│   PostgreSQL    │
│   (Port 8081)   │     │   Server        │     │                 │
└─────────────────┘     │   (Port 8080)   │     │                 │
                        └─────────────────┘     └─────────────────┘
```

## Prerequisites

1. **Clone OpenClaw Repository**

   The OpenClaw repository must be cloned into this directory:

   ```bash
   cd /Users/pdiogo/Documents/code/totalreclaw/testbed/functional-test
   git clone https://github.com/openclaw/openclaw.git openclaw
   ```

   > **Note**: If the OpenClaw repository is private or located elsewhere, adjust the URL accordingly.

2. **Set Environment Variables**

   Create a `.env` file or export the required API key:

   ```bash
   export ZAI_API_KEY=your_api_key_here
   ```

3. **Verify TotalReclaw Server Dockerfile**

   Ensure the TotalReclaw server has a Dockerfile at:
   ```
   /Users/pdiogo/Documents/code/totalreclaw/server/Dockerfile
   ```

## Quick Start

```bash
# From this directory
cd /Users/pdiogo/Documents/code/totalreclaw/testbed/functional-test

# Run the full test suite
./run-tests.sh

# Or run manually with docker-compose
docker-compose -f docker-compose.functional-test.yml --profile functional-test up
```

## Running Tests

### Option 1: Using run-tests.sh (Recommended)

```bash
./run-tests.sh
```

This script will:
1. Check prerequisites
2. Start all services
3. Wait for health checks
4. Run test conversations
5. Collect results
6. Cleanup

### Option 2: Manual Docker Compose

```bash
# Start services
docker-compose -f docker-compose.functional-test.yml --profile functional-test up -d

# Check service health
docker-compose -f docker-compose.functional-test.yml ps

# View logs
docker-compose -f docker-compose.functional-test.yml logs -f openclaw-test

# Stop services
docker-compose -f docker-compose.functional-test.yml --profile functional-test down
```

## Test Scenarios

### Scenario 1: Basic Memory Storage

1. Send a message with personal information
2. Verify the fact is extracted and stored
3. Query TotalReclaw directly to confirm storage

### Scenario 2: Memory Retrieval

1. Store multiple facts across several turns
2. Ask a question that requires retrieving stored memories
3. Verify the agent references the correct information

### Scenario 3: Memory Decay (Future)

1. Store facts with different importance scores
2. Wait for decay interval
3. Verify low-importance memories are deprioritized

### Scenario 4: Cross-Session Memory

1. Complete a conversation storing facts
2. Restart the OpenClaw instance
3. Verify memories persist and are retrievable

## Configuration

### TotalReclaw Settings (agents.yaml)

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | `true` | Enable TotalReclaw integration |
| `serverUrl` | `http://totalreclaw-server:8080` | TotalReclaw server URL |
| `autoExtractEveryTurns` | `5` | Extract facts every N turns |
| `minImportanceForAutoStore` | `6` | Minimum importance (1-10) to store |
| `maxMemoriesInContext` | `8` | Max memories in context window |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ZAI_API_KEY` | Yes | API key for ZAI LLM provider |
| `OPENCLAW_LLM_PROVIDER` | No | LLM provider (default: zai) |
| `OPENCLAW_LLM_MODEL` | No | LLM model (default: glm-5) |

## Security Notes

1. **Network Isolation**: Services run on an internal Docker network. Only OpenClaw's port 8081 is exposed to the host.

2. **Read-Only Filesystems**: Containers use read-only root filesystems with tmpfs for /tmp.

3. **No New Privileges**: Security option `no-new-privileges:true` prevents privilege escalation.

4. **Internal Network**: The `totalreclaw-internal` network is internal, preventing external access to PostgreSQL and TotalReclaw server.

5. **Test-Only Credentials**: Database credentials and encryption keys are for testing only. Never use in production.

## Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose -f docker-compose.functional-test.yml logs

# Verify network
docker network ls | grep totalreclaw
```

### Health check failures

```bash
# Check individual service health
docker inspect --format='{{.State.Health.Status}}' totalreclaw-server-1
docker inspect --format='{{.State.Health.Status}}' openclaw-test-1
```

### Connection refused

1. Verify services are on the same network
2. Check that health checks pass
3. Verify service names match configuration

## Directory Structure

```
functional-test/
├── docker-compose.functional-test.yml  # Main compose file
├── openclaw-config/
│   └── agents.yaml                     # OpenClaw configuration
├── openclaw/                           # Cloned OpenClaw repo (git clone)
├── test-results/                       # Test output (created by run-tests.sh)
├── run-tests.sh                        # Test runner script
└── README.md                           # This file
```

## Cleanup

```bash
# Stop and remove containers
docker-compose -f docker-compose.functional-test.yml --profile functional-test down

# Remove volumes (clears database)
docker-compose -f docker-compose.functional-test.yml --profile functional-test down -v

# Remove everything including network
docker-compose -f docker-compose.functional-test.yml --profile functional-test down -v --rmi local
```
