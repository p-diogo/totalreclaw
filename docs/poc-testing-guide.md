# TotalReclaw Beta Testing Guide

> Encrypted memory for AI agents. This guide gets you from zero to a working local stack in ~15 minutes.

---

## What is TotalReclaw?

TotalReclaw is an **encrypted memory vault for AI agents** -- a password manager for AI memory.

**The problem:** AI agents forget everything between sessions. Tools that do persist memory store it as plaintext on remote servers, readable by the provider.

**TotalReclaw's approach:**
- Memories are **AES-256-GCM encrypted on your device** before they leave it
- The server stores ciphertext and blind indices (SHA-256 hashes) -- it never sees plaintext
- You can **export or delete all your data** at any time
- One 12-word mnemonic derives all keys (and a future Ethereum wallet); lose it and the data is unrecoverable (by design)

**Validated performance:** 98.1% Recall@8 on real WhatsApp + Slack data, with full end-to-end encryption.

---

## Architecture

The test stack runs three Docker containers on a single machine:

```
 You (browser)
   |
   v
 openclaw-test (:8081)    -- OpenClaw with the TotalReclaw plugin
   |                          Encrypts/decrypts client-side
   |                          LLM decides when to store memories
   v
 totalreclaw-server (:8080) -- FastAPI server (sees only ciphertext)
   |
   v
 postgres                  -- PostgreSQL 16 (encrypted blobs + blind indices)
```

All ports are bound to `127.0.0.1` only. Nothing is exposed to the network.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| **Docker + Docker Compose** | v2 (the `docker compose` command, not `docker-compose`) |
| **Git** | To clone the repo |
| **OpenClaw source code** | The `openclaw-test` container builds from source. Place the OpenClaw repo at `testbed/functional-test/openclaw/` (see Step 1) |
| **LLM API key** | Z.AI key by default. Any OpenClaw-supported provider works (see [LLM Providers](#using-a-different-llm-provider)) |

---

## Setup

### Step 1: Clone and prepare

```bash
git clone https://github.com/p-diogo/totalreclaw.git
cd totalreclaw
```

The OpenClaw container builds from source. You need the OpenClaw source tree at `testbed/functional-test/openclaw/`. If it is not already there, clone or symlink it:

```bash
# Option A: Clone into place
git clone https://github.com/openclaw/openclaw.git testbed/functional-test/openclaw

# Option B: Symlink an existing checkout
ln -s /path/to/your/openclaw testbed/functional-test/openclaw
```

### Step 2: Configure environment

```bash
cd testbed/functional-test
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `ZAI_API_KEY` | Yes | Your Z.AI API key (or another provider's key -- see below) |
| `TOTALRECLAW_MASTER_PASSWORD` | Yes | A **12-word BIP-39 mnemonic** for encryption key derivation. Generate one with `npx tsx skill/plugin/generate-mnemonic.ts` from the repo root. **Unrecoverable if lost.** This mnemonic can later derive an Ethereum wallet for on-chain features. |
| `POSTGRES_PASSWORD` | No | Defaults to `test`. Change for any shared environment. |

**Generating a mnemonic:**

```bash
cd /path/to/totalreclaw-poc
npx tsx skill/plugin/generate-mnemonic.ts
```

This prints 12 random English words. Copy them into your `.env`:

```
TOTALRECLAW_MASTER_PASSWORD=word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12
```

> **Why a mnemonic?** The same 12-word secret will later derive an Ethereum wallet for on-chain memory anchoring (MVP roadmap). Using it now means your encrypted memories will be forward-compatible — no migration needed.

### Step 3: Start the stack

```bash
docker compose -f docker-compose.functional-test.yml --profile functional-test up -d --build
```

The first build takes 3-5 minutes (OpenClaw compiles from source). Subsequent starts are fast.

### Step 4: Verify

Wait ~30 seconds for health checks to pass, then:

```bash
# Server healthy?
curl http://localhost:8080/health

# All containers running?
docker compose -f docker-compose.functional-test.yml --profile functional-test ps

# Plugin loaded?
docker logs openclaw-test 2>&1 | grep -i totalreclaw
# Look for: "TotalReclaw plugin loaded"
# Note: "Registered new user: <uuid>" appears after your first message, not at startup.
```

### Step 5: Connect to OpenClaw

Open **http://localhost:8081** in your browser. On first connect, you need to pair the device:

```bash
# From your host machine:
docker exec openclaw-test npx openclaw devices approve --latest \
  --token e6a13aa43a07820b3a80755748a6c856fdb2cd9a8a6be0b6
```

You are now connected. The TotalReclaw plugin is active and the agent has four memory tools available.

---

## How It Works

The TotalReclaw plugin gives the agent four tools and one automatic hook:

| Tool | What it does |
|---|---|
| `totalreclaw_remember` | Encrypt and store a fact, preference, decision, or goal |
| `totalreclaw_recall` | Search the vault using blind indices, decrypt and re-rank client-side |
| `totalreclaw_forget` | Soft-delete a memory by ID |
| `totalreclaw_export` | Export all memories as JSON or Markdown (decrypted client-side) |

**Automatic recall (`before_agent_start` hook):** Before every response, the plugin tokenizes your message, searches for relevant memories via blind indices, decrypts matches client-side, and injects the top 8 into the agent's context. The server never sees the query or the results in plaintext.

**Fact extraction (two paths):**
1. **Explicit** — The agent calls `totalreclaw_remember` when it detects important information (guided by SKILL.md instructions).
2. **Automatic** — After each agent turn, the `agent_end` hook runs a lightweight LLM call to extract facts the agent may have missed. This uses a cheap/fast model derived from your provider (e.g., `glm-4.5-flash` for Z.AI, `gpt-4.1-mini` for OpenAI, `claude-haiku-4-5` for Anthropic).

Both paths encrypt and store facts identically. Content fingerprint deduplication prevents exact duplicates, though slight LLM text variations may occasionally produce near-duplicates.

---

## Test Scenarios

### 1. Basic Memory Storage (~5 min)

Tell the agent some personal facts in natural conversation:

- "I'm working on a project called Lighthouse using React and TypeScript"
- "My team meets every Tuesday at 2pm"
- "I prefer dark mode in all my editors"

Start a **new conversation** (or reload the page) and ask:

- "What project am I working on?"
- "When does my team meet?"

**Expected:** The agent recalls your facts from the previous conversation. Check the logs to confirm the `before_agent_start` hook fired:

```bash
docker logs openclaw-test 2>&1 | tail -20
```

> **Tip:** After sending a message, wait 3-5 seconds for the `agent_end` hook to run automatic fact extraction. Check the logs for "Auto-extracted and stored N memories".

### 2. Explicit Memory Commands (~3 min)

Test direct memory operations:

- "Remember that my favorite programming language is Rust"
- "What do you remember about my preferences?" (triggers `totalreclaw_recall`)
- "Export all my memories" (triggers `totalreclaw_export`)
- "Forget memory `<paste-an-id-from-export>`" (triggers `totalreclaw_forget`)

### 3. Encryption Verification (~2 min)

Confirm the server only stores ciphertext:

```bash
docker exec $(docker ps -qf name=postgres) \
  psql -U totalreclaw -d totalreclaw \
  -c "SELECT id, substring(encrypted_blob, 1, 80) AS blob_preview, blind_indices FROM facts LIMIT 5;"
```

**Expected:** `encrypted_blob` is hex-encoded gibberish. `blind_indices` are SHA-256 hashes, not your search terms.

### 4. Memory Across Conversations (~10 min)

Build up context over 3-4 conversations on different topics (tech stack, work habits, a problem you are solving). In the final conversation, ask: "Summarize everything you know about me."

**Expected:** A coherent picture assembled from memories across all sessions.

### 5. Indirect Recall (~5 min)

After storing 10+ facts, ask questions that require inference rather than keyword matching:

- Instead of "What's my tech stack?" try "What tools should I use for my next project?"
- Instead of "When do I meet?" try "Am I free on Tuesday afternoon?"

**Expected:** Relevant memories surface even when the question uses different words.

### 6. Data Portability (~2 min)

Ask: "Export all my memories as markdown"

**Expected:** A complete, readable export of everything stored. This is your data; you can take it anywhere.

---

## Using a Different LLM Provider

The default configuration uses Z.AI with `glm-5`. To use a different provider, update **three files**:

### 1. `.env` — Set your API key

| Provider | Variable |
|---|---|
| Z.AI | `ZAI_API_KEY=your-key` |
| OpenAI | `OPENAI_API_KEY=your-key` |
| Anthropic | `ANTHROPIC_API_KEY=your-key` |
| Google/Gemini | `GEMINI_API_KEY=your-key` |
| Mistral | `MISTRAL_API_KEY=your-key` |
| Groq | `GROQ_API_KEY=your-key` |
| DeepSeek | `DEEPSEEK_API_KEY=your-key` |
| xAI | `XAI_API_KEY=your-key` |

### 2. `docker-compose.functional-test.yml` — Pass the key to the container

Find the `openclaw-test` service and update:

```yaml
environment:
  - OPENCLAW_LLM_PROVIDER=anthropic          # your provider
  - OPENCLAW_LLM_MODEL=claude-sonnet-4-5     # your model
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}    # match the .env variable
```

### 3. `openclaw-config/config.json5` — Set the agent's model

```json5
"agents": {
  "defaults": {
    "model": {
      "primary": "anthropic/claude-sonnet-4-5"  // format: provider/model
    }
  }
}
```

The memory plugin auto-detects your provider and uses a cheap/fast model for fact extraction (e.g., `claude-haiku-4-5` for Anthropic, `gpt-4.1-mini` for OpenAI). No additional LLM configuration is needed.

---

## Security

### What is hardened in this setup

| Feature | Detail |
|---|---|
| **Client-side encryption** | AES-256-GCM. Keys derived via HKDF from your passphrase. Server never sees plaintext. |
| **Blind search indices** | SHA-256 hashes of n-gram tokens. Server matches hashes without knowing the words. |
| **Localhost-only ports** | All ports bound to `127.0.0.1`. Nothing exposed to the network. |
| **Privilege restriction** | `no-new-privileges:true` on server and database containers. |
| **Read-only filesystem** | Server container filesystem is read-only (`tmpfs` for `/tmp`). |
| **Non-root processes** | Server runs as `totalreclaw` user, OpenClaw build runs as `node` user. |

### What testers should verify

- [ ] Database contains no readable plaintext (Test Scenario 3 above)
- [ ] `docker port` shows only `127.0.0.1` bindings, not `0.0.0.0`
- [ ] No plaintext facts appear in container logs (`docker logs totalreclaw-server`)

### PoC limitations (not production-ready)

- Gateway auth token is static in `config.json5` (would be generated per-session in production)
- No TLS between containers (all traffic stays on a Docker bridge network)
- No rate limiting on the API
- `TOTALRECLAW_MASTER_PASSWORD` falls back to a test passphrase if `.env` is not configured (uses Argon2id path, not BIP-39)

---

## Troubleshooting

### Server won't start

```bash
docker compose -f docker-compose.functional-test.yml --profile functional-test logs totalreclaw-server
docker compose -f docker-compose.functional-test.yml --profile functional-test logs postgres
```

Common cause: port 8080 already in use. Check with `lsof -i :8080`.

### Plugin not loading

```bash
docker logs openclaw-test 2>&1 | grep -i "error\|totalreclaw\|plugin"
```

- **"TOTALRECLAW_MASTER_PASSWORD not set"** -- Your `.env` is missing or not being read. Confirm the file exists in `testbed/functional-test/.env`.
- **No "TotalReclaw plugin loaded" log** -- Check that `skill/plugin/node_modules/` exists. Run `cd skill/plugin && ./setup.sh` on the host, or rebuild: `docker compose ... up -d --build openclaw-test`.
- **"openclaw: command not found"** — Use `npx openclaw` instead of bare `openclaw` inside the container. All CLI commands require the `npx` prefix.

### "Register failed: 409"

The server already has an account for a different password/salt combination. Reset credentials:

```bash
docker volume rm functional-test_totalreclaw-credentials
docker compose -f docker-compose.functional-test.yml --profile functional-test restart openclaw-test
```

### OpenClaw build fails

The OpenClaw container builds from source and requires the full repo at `testbed/functional-test/openclaw/`. Verify:
- The directory is not empty
- It contains `package.json`, `pnpm-lock.yaml`, and the full source tree
- Your Docker has enough memory allocated (4 GB minimum recommended)

### Want to start fresh

```bash
docker compose -f docker-compose.functional-test.yml --profile functional-test down -v
docker compose -f docker-compose.functional-test.yml --profile functional-test up -d --build
```

The `-v` flag removes all volumes (database data, credentials, OpenClaw state).

### Forgot your passphrase

There is no recovery. This is the zero-knowledge tradeoff. Start fresh (see above).

---

## Persistence

| Data | Location | Survives restart? |
|---|---|---|
| Encrypted memories | PostgreSQL volume (`test-db-data`) | Yes |
| Plugin credentials (user ID + salt) | Docker volume (`totalreclaw-credentials`) | Yes |
| OpenClaw state | Docker volume (`openclaw-state`) | Yes |
| Encryption keys | Derived from 12-word mnemonic at startup | Never stored |

---

## Feedback

After testing, we would like to hear about:

1. **Setup** -- Where did you get stuck? How long did it take?
2. **Memory quality** -- Are extracted facts accurate? Does it remember the right things?
3. **Recall quality** -- Does it find relevant context? Any "wow" moments?
4. **Privacy feel** -- Does encryption change how you interact with the agent?
5. **Performance** -- Any noticeable lag when storing or recalling?
6. **Overall** -- Would you use this? What would you change?

---

## Technical Reference

| Component | Detail |
|---|---|
| Encryption | AES-256-GCM, keys via HKDF (SHA-256) from BIP-39 mnemonic seed |
| Search | LSH blind indices, GIN index lookup on PostgreSQL |
| Re-ranking | Client-side text-overlap scoring (BM25 + cosine planned) |
| Benchmark | 98.1% Recall@8, full E2EE, real-world data |
| Architecture spec | `docs/specs/totalreclaw/architecture.md` |
| Server spec | `docs/specs/totalreclaw/server.md` |
