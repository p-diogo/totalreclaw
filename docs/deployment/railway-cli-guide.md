# Railway CLI & API Guide

> Practical reference for deploying, debugging, and managing TotalReclaw on Railway.

---

## Installation

Choose one method:

```bash
# Homebrew (macOS)
brew install railway

# npm (macOS, Linux, Windows) — requires Node.js 16+
npm i -g @railway/cli

# Shell script (macOS, Linux, Windows via WSL)
bash <(curl -fsSL cli.new)

# Scoop (Windows)
scoop install railway
```

Verify installation:

```bash
railway --version
```

---

## Authentication

### Interactive Login

```bash
railway login
```

Opens a browser for OAuth. For headless/SSH environments:

```bash
railway login --browserless
```

### CI/CD (Non-Interactive)

Set one of these environment variables instead of interactive login:

| Variable | Scope | Use Case |
|----------|-------|----------|
| `RAILWAY_TOKEN` | Single project + environment | CI/CD deployments |
| `RAILWAY_API_TOKEN` | Full account / workspace | Automation scripts |

```bash
# Deploy using a project token
RAILWAY_TOKEN=xxx railway up
```

---

## Project Setup

```bash
railway init          # Create a new project
railway link          # Link current directory to existing project
railway status        # Show linked project, service, environment
railway list          # View all projects
railway open          # Open project in browser
railway unlink        # Disconnect directory from project
```

### Link a Specific Service

```bash
railway service       # Interactive service selection
railway link -s <service-name>
```

---

## Deployment

### Deploy from Local Directory

```bash
railway up              # Deploy and stream build + runtime logs
railway up --detach     # Deploy and return immediately (no log streaming)
railway up --json       # Output logs in JSON format
```

### Other Deployment Commands

```bash
railway redeploy        # Redeploy the latest version
railway restart         # Restart the service (no rebuild)
railway down            # Remove the latest deployment
```

### Deploy a Database or Template

```bash
railway add --database postgres    # Add a PostgreSQL service
railway add --repo user/repo       # Add a GitHub repo as a service
```

---

## Environment Variables

### View Variables

```bash
railway variable list                    # List all variables
railway variable list -s <service>       # List for a specific service
```

### Set Variables

```bash
railway variable set KEY=value
railway variable set DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db"
railway variable set KEY1=val1 KEY2=val2  # Set multiple at once
```

### Delete Variables

```bash
railway variable delete KEY
```

---

## Viewing Logs

### CLI

```bash
railway logs              # Stream runtime logs (latest deployment)
railway logs --build      # View build logs
railway logs -n 100       # Show last 100 lines
railway logs -s <service> # Logs for a specific service
```

### Dashboard

1. **Deployment Logs** -- Click a deployment in the service panel. Use the "Build Logs" tab for build output and "Deploy Logs" tab for runtime output.
2. **Log Explorer** -- Click "Observability" in top navigation to view logs across all services in an environment.

### Log Explorer Query Syntax

Railway's Log Explorer supports powerful filtering:

```
# Substring match
error

# Phrase match
"connection refused"

# Attribute queries
@httpStatus:>=500
@responseTime:>500
@path:/v1/store

# Boolean operators
@httpStatus:>=500 AND @responseTime:>1000

# Negation
-healthcheck
```

### Structured Logging

Emit JSON logs from your application for better filtering:

```python
import logging
from pythonjsonlogger.json import JsonFormatter

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.getLogger().addHandler(handler)
```

Railway automatically normalizes logs: `stdout` becomes info-level, `stderr` becomes error-level.

### Log Limits

| Plan | Retention | Rate Limit |
|------|-----------|------------|
| Hobby | 7 days | 500 lines/sec/replica |
| Pro | 30 days | 500 lines/sec/replica |
| Enterprise | Up to 90 days | Custom |

---

## Debugging Deployment Crashes

### Step 1: Check Build Logs

```bash
railway logs --build
```

Common build failures:
- Missing dependencies in `requirements.txt`
- Incorrect Python/Node version
- Build command errors

### Step 2: Check Runtime Logs

```bash
railway logs -n 200
```

Common runtime failures:
- Missing environment variables (e.g., `DATABASE_URL` not set)
- Wrong database URL scheme (e.g., `postgres://` instead of `postgresql+asyncpg://`)
- Port binding issues (Railway sets `PORT` automatically)
- Database not ready yet at startup

### Step 3: Verify Environment Variables

```bash
railway variable list
```

Check that all required variables are set. For TotalReclaw, verify:
- `DATABASE_URL` starts with `postgresql+asyncpg://`
- `SECRET_KEY` is set
- `ENVIRONMENT` is set to `production`

### Step 4: Run Locally with Railway Env Vars

```bash
railway run python -c "import os; print(os.environ.get('DATABASE_URL', 'NOT SET'))"
railway run python -m uvicorn totalreclaw.src.main:app --host 0.0.0.0 --port 8080
```

This loads all Railway environment variables into your local process, so you can reproduce issues locally.

### Step 5: SSH into the Container

```bash
railway ssh
```

Opens a shell inside the running container for live debugging.

### Step 6: Connect to Database

```bash
railway connect postgres
```

Opens a `psql` shell connected to the Railway PostgreSQL instance.

### Common Crash Patterns

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Crashes immediately on startup | Missing env var | `railway variable list` to check |
| "Connection refused" to DB | DB not ready, or wrong URL | Check `DATABASE_URL` scheme and host |
| "Address already in use" | Hardcoded port conflict | Use `os.environ.get("PORT", "8080")` |
| Build succeeds, deploy fails | Runtime dependency missing | Check `requirements.txt` completeness |
| OOM killed | Memory limit exceeded | Check memory usage, optimize, or upgrade plan |

---

## Environments

```bash
railway environment                # Switch environment interactively
railway environment new staging    # Create a new environment
railway environment delete dev     # Delete an environment
```

Each environment has its own set of variables, deployments, and domains.

---

## Domains & Networking

```bash
railway domain                  # Generate a Railway subdomain (*.up.railway.app)
railway domain api.example.com  # Add a custom domain
```

For custom domains, add a CNAME record pointing to `<project>.up.railway.app` in your DNS provider.

---

## Railway Public API (GraphQL)

Railway exposes a GraphQL API for programmatic access. There is no official Python SDK, but the API can be used with any HTTP or GraphQL client.

### Endpoint

```
https://backboard.railway.com/graphql/v2
```

### Authentication Tokens

| Token Type | Header | Scope |
|------------|--------|-------|
| Account Token | `Authorization: Bearer <token>` | All account resources |
| Workspace Token | `Authorization: Bearer <token>` | Single workspace |
| Project Token | `Project-Access-Token: <token>` | Single project + environment |

Create tokens at: https://railway.com/account/tokens

### Example: Query Current User

```bash
curl -X POST https://backboard.railway.com/graphql/v2 \
  -H "Authorization: Bearer $RAILWAY_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"query { me { name email } }"}'
```

### Example: Query Project Details

```bash
curl -X POST https://backboard.railway.com/graphql/v2 \
  -H "Project-Access-Token: $RAILWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"query { projectToken { projectId environmentId } }"}'
```

### Example: Python Script

```python
import requests

RAILWAY_API_TOKEN = "your-token-here"
ENDPOINT = "https://backboard.railway.com/graphql/v2"

def railway_query(query: str, variables: dict = None):
    response = requests.post(
        ENDPOINT,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {RAILWAY_API_TOKEN}"}
    )
    response.raise_for_status()
    return response.json()

# List all projects
result = railway_query("""
    query {
        me {
            projects {
                edges {
                    node {
                        id
                        name
                        updatedAt
                    }
                }
            }
        }
    }
""")
print(result)
```

### Rate Limits

| Plan | Requests/Hour | Requests/Second |
|------|---------------|-----------------|
| Free | 100 | -- |
| Hobby | 1,000 | 10 |
| Pro | 10,000 | 50 |
| Enterprise | Custom | Custom |

Rate limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`.

### Schema Exploration

- GraphiQL playground: https://railway.com/graphiql
- Full introspection supported (use any GraphQL client)

---

## Quick Reference

| Task | Command |
|------|---------|
| Install CLI | `brew install railway` |
| Login | `railway login` |
| Link project | `railway link` |
| Deploy | `railway up` |
| View runtime logs | `railway logs` |
| View build logs | `railway logs --build` |
| List env vars | `railway variable list` |
| Set env var | `railway variable set KEY=value` |
| Run locally with env | `railway run <command>` |
| SSH into container | `railway ssh` |
| Connect to DB | `railway connect postgres` |
| Open dashboard | `railway open` |
