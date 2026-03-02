# TotalReclaw Beta Testing Guide (NanoClaw)

## What You Are Testing

TotalReclaw is an encrypted memory vault for AI agents. Memories are AES-256-GCM encrypted on your device before they leave it -- the server only ever sees ciphertext. When a NanoClaw container starts a new conversation, it recalls relevant memories from the encrypted vault, giving the agent continuity across ephemeral sessions. You are testing whether this actually works end-to-end with a real Claude agent.

**You are the first people running the full agent integration.** The encryption pipeline (32/32 tests passing) and server infrastructure are validated. What has NOT been validated yet is the complete experience: NanoClaw building from source on your machine, Claude using MCP tools during conversation, SKILL.md driving auto-recall/remember, and cross-session memory feeling natural. Your feedback on the real experience is exactly what we need.

---

## What You Need

| Requirement | Notes |
|---|---|
| Docker + Docker Compose v2 | The `docker compose` command (not `docker-compose`) |
| Git | To clone two repos |
| Node.js 18+ | For the pipeline test (runs on the host) |
| Claude auth | **One** of: Claude subscription OAuth token, or Anthropic API key |

**Which auth method?**
- Claude subscription (Pro/Team/Enterprise): run `claude setup-token` in your terminal to get an OAuth token.
- Anthropic API key: get one from console.anthropic.com.

Auth is only needed for the full agent test (Step 5). The pipeline test in Step 4 runs without it.

---

## Quick Start

### 1. Clone both repos

```bash
git clone https://github.com/p-diogo/totalreclaw.git
cd totalreclaw/testbed/functional-test-nanoclaw
git clone https://github.com/qwibitai/nanoclaw.git nanoclaw
```

### 2. Generate your BIP-39 mnemonic and configure

First, install dependencies and generate your 12-word BIP-39 mnemonic:

```bash
npm install --no-save @scure/bip39
node generate-seed.mjs
```

This prints a 12-word BIP-39 mnemonic. This mnemonic is the **only way to access your encrypted memories**. The server never sees your data in readable form — it cannot recover it for you. If you lose this mnemonic, your memories are gone forever. If you move to a new device or agent, this mnemonic is how you restore everything. Store it somewhere safe.

Now create your `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | One of these two | OAuth token — run `claude setup-token` to get it |
| `ANTHROPIC_API_KEY` | One of these two | Anthropic API key from console.anthropic.com |
| `TOTALRECLAW_MASTER_PASSWORD` | Yes | Your 12-word BIP-39 mnemonic from `generate-seed.mjs` |
| `POSTGRES_PASSWORD` | No | Defaults to `test` |

### 3. Build the NanoClaw base image

```bash
cd nanoclaw/container && ./build.sh && cd ../..
```

### 4. Build the extended image (adds TotalReclaw crypto)

```bash
docker build -f Dockerfile.nanoclaw-totalreclaw -t nanoclaw-totalreclaw:latest .
```

### 5. Start the infrastructure

```bash
docker compose -f docker-compose.nanoclaw-test.yml up -d
```

Wait about 15 seconds, then verify:

```bash
curl http://localhost:8090/health
docker compose -f docker-compose.nanoclaw-test.yml ps
```

Both `postgres` and `totalreclaw-server` should show healthy.

---

## Verify Your Setup

Run the pipeline test. This validates the full crypto pipeline -- encrypt, store, search, decrypt, export, dedup -- directly against the server. It does NOT need an API key or OAuth token.

```bash
./run-pipeline-test.sh
```

Expected output: `All pipeline tests PASSED` (32/32).

**If this fails, stop here.** Check the troubleshooting section before proceeding. The pipeline test confirms the server and crypto layer are working; everything after this builds on top of it.

---

## Talk to Your Agent

### Automated test

The full agent test launches ephemeral NanoClaw containers, sends prompts via stdin, and verifies that memories are stored and recalled across sessions.

```bash
./run-tests.sh
```

This requires your Claude auth to be set in `.env`. The script will:

1. Build both container images (if not already built)
2. Start the infrastructure
3. Run a conversation where the agent stores facts ("My name is Alice, I work at Acme Corp")
4. Spin up a **new** container and ask the agent what it remembers
5. Verify the database contains only encrypted blobs
6. Report pass/fail results

Use `./run-tests.sh --no-cleanup` to keep the infrastructure running after tests finish.

### Manual interactive testing

To have a freeform conversation with the agent, adapt the `docker run` command from the test runner. Save the following as a JSON file (e.g., `my-prompt.json`):

```json
{
  "prompt": "Hi! Let's have a conversation.",
  "groupFolder": "test-main",
  "chatJid": "manual@test.us",
  "isMain": true,
  "assistantName": "TestBot",
  "secrets": {
    "TOTALRECLAW_MASTER_PASSWORD": "your-passphrase-here",
    "CLAUDE_CODE_OAUTH_TOKEN": "your-token-here"
  }
}
```

Then run:

```bash
cat my-prompt.json | docker run --rm -i \
  --network nanoclaw-totalreclaw-test_nanoclaw-test \
  -e TOTALRECLAW_SERVER_URL=http://totalreclaw-server:8080 \
  -v "$(pwd)/nanoclaw-totalreclaw-overlay/agent-runner-src/index.ts:/app/src/index.ts:ro" \
  -v "$(pwd)/nanoclaw-totalreclaw-overlay/agent-runner-src/totalreclaw-mcp.ts:/app/src/totalreclaw-mcp.ts:ro" \
  -v "$(pwd)/nanoclaw-totalreclaw-overlay/skills/totalreclaw:/app/skills/totalreclaw:ro" \
  -v nanoclaw-totalreclaw-credentials:/workspace/.totalreclaw \
  nanoclaw-totalreclaw:latest
```

Each run is a fresh container. Change the `prompt` field to say different things. The agent should auto-recall relevant memories at the start and store new facts as the conversation progresses.

---

## What to Look For

- [ ] **Auto-store**: The agent stores facts without being explicitly asked. Tell it your name, job, and preferences in natural conversation and check if it calls `totalreclaw_remember` on its own.

- [ ] **Cross-session recall**: Start a new container and ask "What do you know about me?" The agent should recall facts from the previous session without any prompting.

- [ ] **No plaintext on the server**: Run this to inspect the database directly:
  ```bash
  docker exec -it $(docker ps -qf name=postgres) \
    psql -U totalreclaw -d totalreclaw \
    -c "SELECT id, substring(encrypted_blob, 1, 80) AS blob_preview, blind_indices FROM facts LIMIT 5;"
  ```
  You should see hex-encoded ciphertext in `encrypted_blob` and SHA-256 hashes in `blind_indices` -- no readable text.

- [ ] **Export works**: Ask the agent to "export all my memories." The decryption happens client-side inside the container. You should get back readable plaintext.

- [ ] **No plaintext in logs**: Check server logs for leaked memory content:
  ```bash
  docker logs $(docker ps -qf name=totalreclaw-server) 2>&1 | head -50
  ```

- [ ] **Indirect recall**: After storing several facts, ask questions using different words than you used to store them (e.g., store "I prefer Python" then ask "What should I use for my next backend project?").

---

## Troubleshooting

**Server won't start**

```bash
docker compose -f docker-compose.nanoclaw-test.yml logs totalreclaw-server
docker compose -f docker-compose.nanoclaw-test.yml logs postgres
```

Most common cause: port 8090 or 5433 already in use. Check with `lsof -i :8090`.

**NanoClaw build fails**

Verify the `nanoclaw/container/` directory exists and contains `build.sh`. Docker needs at least 4 GB of memory. Check network connectivity for npm installs.

**Agent container exits immediately**

```bash
docker logs $(docker ps -alqf ancestor=nanoclaw-totalreclaw)
```

Usually means auth is missing or invalid. Verify your `.env` has a valid `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`, and that the server is healthy (`curl http://localhost:8090/health`).

**No memories recalled in new session**

The passphrase must match between sessions. A different `TOTALRECLAW_MASTER_PASSWORD` derives different keys, making old memories unreadable. Check that your `.env` hasn't changed.

**"Register failed: 409"**

The server already has credentials from a different passphrase. Reset:

```bash
docker compose -f docker-compose.nanoclaw-test.yml down
docker volume rm nanoclaw-totalreclaw-credentials 2>/dev/null
docker compose -f docker-compose.nanoclaw-test.yml up -d
```

**Lost your BIP-39 mnemonic**

There is no recovery. The server never sees your data in readable form, so it cannot help you. This is the zero-knowledge tradeoff. Start fresh:

```bash
docker compose -f docker-compose.nanoclaw-test.yml down -v
docker compose -f docker-compose.nanoclaw-test.yml up -d
```

The `-v` flag removes all volumes (database and credentials). Clean slate.

---

## Tell Us What You Found

We want to hear about:

1. **Setup friction** -- Where did you get stuck? How long did it take end-to-end?
2. **Memory quality** -- Does the agent store the right things? Are extracted facts accurate and concise?
3. **Recall quality** -- Does it find relevant context? Any "it just knew" moments? Any misses?
4. **Cross-session feel** -- Does a new container picking up old memories feel seamless or jarring?
5. **Performance** -- Any noticeable lag when storing or recalling?
6. **Overall** -- Would you use this? What would make it better?

---

## Technical Reference

| Component | Detail |
|---|---|
| Encryption | AES-256-GCM, keys via HKDF (SHA-256) from passphrase |
| Search | Blind indices (SHA-256 of n-gram tokens), GIN index on PostgreSQL |
| Re-ranking | Client-side text-overlap scoring after decryption |
| MCP transport | stdio (inside container) |
| Agent SDK | Claude Agent SDK (Anthropic) |
| Ports | 8090 (server), 5433 (postgres) -- localhost only |
| Benchmark | 98.1% Recall@8 on real-world data with full E2EE |
