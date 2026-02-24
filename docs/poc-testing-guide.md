# OpenMemory PoC Testing Guide

> For friends testing OpenMemory with self-hosted OpenClaw. No prior knowledge of OpenMemory required.

---

## What is OpenMemory?

OpenMemory is an **encrypted memory vault for AI agents**. Think of it as a password manager, but for your AI's memories.

**The problem:** When you chat with AI agents (like OpenClaw), they forget everything between sessions. Some tools store your memories on their servers in plaintext — meaning the company can read all your personal data.

**OpenMemory's solution:** Your AI remembers things across conversations, but all memories are **encrypted on your device before they ever leave it**. The server stores ciphertext it cannot read. You own your data, and you can export or delete it at any time.

---

## Setup (15 minutes)

### Prerequisites

- A machine running **OpenClaw** (self-hosted)
- **Docker** and **Docker Compose** installed
- **Git** installed

### Step 1: Clone and start the OpenMemory server

```bash
git clone https://github.com/p-diogo/openmemory-poc.git
cd openmemory-poc/server

# Create your environment file
cp .env.example .env

# Edit .env — change the password!
# POSTGRES_PASSWORD=pick_a_strong_password_here
# DATABASE_URL=postgresql+asyncpg://openmemory:pick_a_strong_password_here@postgres:5432/openmemory

# Start the server
docker-compose up -d
```

Wait ~30 seconds, then verify:
```bash
curl http://localhost:8080/health
# Should return: {"status": "healthy", ...}
```

> **Tip:** Set `DEBUG=true` in your `.env` file to enable the Swagger UI at `http://localhost:8080/docs` for interactive API exploration.

### Step 2: Install the OpenMemory skill in OpenClaw

In your OpenClaw chat, type:
```
/install openmemory
```

Or manually copy the `skill/` directory into your OpenClaw skills folder.

### Step 3: Configure the skill

The skill needs to know where your server is. Set these environment variables in your OpenClaw configuration:

```bash
OPENMEMORY_SERVER_URL=http://localhost:8080
```

### Step 4: Set your passphrase

The first time you use OpenMemory, it will ask you to set a **passphrase**. This passphrase derives your encryption keys — the server never sees it.

**Important:** If you forget your passphrase, your memories are gone. There is no recovery. This is by design (zero-knowledge).

---

## What to Test

### Test 1: Basic Memory Storage (5 min)

**Goal:** Verify that OpenMemory extracts and stores facts from your conversations.

1. Have a normal conversation with OpenClaw. Mention some personal details:
   - "I'm working on a project called Lighthouse using React and TypeScript"
   - "My team meets every Tuesday at 2pm"
   - "I prefer dark mode in all my editors"

2. End the conversation or wait for a natural pause.

3. Start a **new conversation** and ask:
   - "What project am I working on?"
   - "When does my team meet?"
   - "What are my editor preferences?"

**Expected:** OpenClaw should recall the facts you mentioned, even in a brand new conversation.

**What to note:** Did it remember? How accurate was the recall? Did it miss anything? Did it hallucinate anything you didn't say?

### Test 2: Memory Accumulation (10 min)

**Goal:** Verify that memories build up over multiple conversations.

1. Across 3-4 separate conversations, mention different things:
   - Conversation 1: Your tech stack preferences
   - Conversation 2: Your work schedule and habits
   - Conversation 3: A problem you're trying to solve
   - Conversation 4: Ask it to summarize everything it knows about you

**Expected:** By conversation 4, it should have a rich picture of your context.

**What to note:** Does the memory feel natural? Does it bring up relevant context without being asked? Is it annoying or helpful?

### Test 3: Memory Export (2 min)

**Goal:** Verify you can see and export your data.

1. Ask OpenClaw: "Export my memories" or "Show me what you remember about me"
2. Or hit the API directly:
   ```bash
   # You'll need your auth token from the skill
   curl http://localhost:8080/v1/export -H "Authorization: Bearer <your-auth-key>"
   ```

**Expected:** You should see a JSON list of all extracted facts, each with an importance score and confidence level.

**What to note:** Are the extracted facts accurate? Are they useful? Are there any that seem wrong or irrelevant?

### Test 4: Encryption Verification (2 min)

**Goal:** Verify the server truly cannot read your data.

1. Connect to the database directly:
   ```bash
   docker exec -it openmemory-db psql -U openmemory -d openmemory
   ```

2. Look at what's stored:
   ```sql
   SELECT id, encrypted_blob, blind_indices FROM facts LIMIT 5;
   ```

**Expected:** The `encrypted_blob` column should contain hex-encoded gibberish — NOT readable text. The `blind_indices` should be SHA-256 hashes, not your actual search terms.

**What to note:** Can you read any plaintext in the database? (You shouldn't be able to.)

### Test 5: Account Deletion / GDPR (2 min)

**Goal:** Verify you can delete all your data.

1. Delete your account:
   ```bash
   curl -X DELETE http://localhost:8080/v1/account -H "Authorization: Bearer <your-auth-key>"
   ```

2. Check the database:
   ```sql
   SELECT COUNT(*) FROM facts WHERE is_active = true;
   ```

**Expected:** All your facts should be deactivated (soft delete). After 30 days they'd be permanently purged.

### Test 6: Search Quality (5 min)

**Goal:** Test how well OpenMemory finds relevant memories.

1. Store 10-20 facts across several conversations
2. Then ask indirect questions that require the AI to find relevant context:
   - Instead of "What's my tech stack?" try "What tools should I use for my next project?"
   - Instead of "When do I meet?" try "Am I free on Tuesday afternoon?"

**Expected:** OpenMemory should surface relevant memories even when the question doesn't use the exact same words.

**What to note:** How often does it find the right context? Does it ever miss something obvious? Does it surface irrelevant things?

### Test 7: Natural Conversation Flow (10 min)

**Goal:** Use it like you normally would — no special test cases.

Just have 2-3 normal conversations over a day. See if the memory feels helpful, annoying, or invisible. The best outcome is that it "just works" and you don't think about it.

---

## Feedback Questions

After testing, please share your thoughts on:

1. **Setup experience:** Was the installation smooth? Where did you get stuck?

2. **Memory quality:**
   - Are the extracted facts accurate?
   - Does it remember the right things?
   - Does it miss important things?
   - Does it remember things you'd rather it forget?

3. **Recall quality:**
   - When you ask about something from a previous conversation, does it find it?
   - Does it surface relevant context without being asked?
   - Any "wow" moments where it remembered something useful?

4. **Privacy feel:**
   - Does knowing your data is encrypted change how you interact with the AI?
   - Would you trust this with sensitive information (medical, financial, personal)?

5. **Performance:**
   - Any noticeable lag when storing or recalling memories?
   - Does it slow down your normal conversation flow?

6. **Overall:**
   - On a scale of 1-10, how useful is this?
   - Would you use this daily?
   - What's the one thing you'd change?
   - Any bugs or unexpected behavior?

---

## Troubleshooting

**Server won't start:**
```bash
docker-compose logs openmemory-server
docker-compose logs postgres
```

**Port 80/443 conflict (Caddy):**
Caddy starts by default on ports 80 and 443. If those ports are already in use by another service, either stop the conflicting service or start only the server and database:
```bash
docker-compose up -d openmemory-server postgres
```

**Health check fails:**
- Make sure port 8080 is not in use
- Check that PostgreSQL is healthy: `docker-compose ps`

**Skill can't connect:**
- Verify `OPENMEMORY_SERVER_URL` is set correctly
- If running OpenClaw in Docker too, use `host.docker.internal` instead of `localhost`

**Forgot passphrase:**
- There is no recovery. Delete your account and start fresh. This is the zero-knowledge tradeoff.

**Want to start fresh:**
```bash
docker-compose down -v  # Removes all data
docker-compose up -d    # Fresh start
```

---

## Technical Details (for the curious)

- **Encryption:** AES-256-GCM, keys derived via Argon2id + HKDF from your passphrase
- **Search:** LSH (Locality-Sensitive Hashing) blind indices — the server searches encrypted data without decrypting
- **Reranking:** Client-side BM25 + cosine similarity + Reciprocal Rank Fusion
- **Fact extraction:** LLM-powered, runs on your host agent (no separate API key needed)
- **Benchmark:** 98.1% Recall@8 on real WhatsApp+Slack data, with full E2EE privacy

For the full architecture, see `docs/specs/openmemory/architecture.md`.
