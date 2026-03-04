# TotalReclaw Beta Tester Guide

**Version:** 1.0
**Date:** March 2026
**Audience:** Internal beta testers with OpenClaw access
**Time to read:** ~15 minutes
**Time to complete setup:** ~30 minutes

---

## Table of Contents

1. [What Is TotalReclaw?](#1-what-is-totalreclaw)
2. [Installation](#2-installation)
3. [First-Time Setup -- Key Generation](#3-first-time-setup----key-generation)
4. [Understanding the Wallet Address](#4-understanding-the-wallet-address)
5. [Free Tier -- How It Works](#5-free-tier----how-it-works)
6. [Automatic Memory (No Action Required)](#6-automatic-memory-no-action-required)
7. [Explicit Memory Tools](#7-explicit-memory-tools)
8. [Testing Your Setup (Manual Validation)](#8-testing-your-setup-manual-validation)
9. [Upgrading to Pro Tier](#9-upgrading-to-pro-tier)
10. [Recovery on a New Device](#10-recovery-on-a-new-device)
11. [Running E2E Validation (Optional, for Technical Testers)](#11-running-e2e-validation-optional-for-technical-testers)
12. [Configuration Reference](#12-configuration-reference)
13. [Troubleshooting](#13-troubleshooting)
14. [Known Limitations (Beta)](#14-known-limitations-beta)

---

## 1. What Is TotalReclaw?

TotalReclaw is a private, encrypted memory layer for your AI agent. It remembers things you tell it across sessions -- your preferences, decisions, facts about your projects -- and only you can decrypt those memories. Not even the TotalReclaw server can read them. Think of it as a password manager, but for your AI's memory: fully encrypted, fully portable, and under your control.

---

## 2. Installation

### Prerequisites

Before you begin, make sure you have:

1. **An OpenClaw account** with an active workspace.
2. **Node.js 18 or later** installed on your machine. You can check by running:
   ```
   node --version
   ```
   If you see `v18.x.x` or higher, you are all set. If not, download Node.js from [nodejs.org](https://nodejs.org).
3. **An LLM provider configured in OpenClaw.** TotalReclaw auto-detects your agent's LLM provider and API key — no extra LLM configuration is needed. Embeddings are generated locally (no API key required). Fact extraction uses a cheap model from your existing provider (e.g., Anthropic → `claude-haiku-4-5`, OpenAI → `gpt-4.1-mini`).
4. **Internet access** -- the plugin communicates with the TotalReclaw relay server.
5. **A safe place to write down 12 words** -- you will generate a recovery phrase during setup. This is your only way to recover your memories if you switch devices. More on this in the next section.

### Install the Plugin

1. Open your OpenClaw workspace.
2. Navigate to **Settings > Plugins** (or **Skill Marketplace** if available).
3. Search for **TotalReclaw** and click **Install**.

If TotalReclaw is not yet listed in the marketplace, install it manually:

1. Open a terminal and navigate to your OpenClaw plugins directory:
   ```
   cd /path/to/your/openclaw/plugins
   ```
2. Clone the TotalReclaw repository:
   ```
   git clone https://github.com/p-diogo/totalreclaw.git
   ```
3. Install the plugin dependencies:
   ```
   cd totalreclaw/skill/plugin
   npm install --production
   ```
4. In your OpenClaw configuration, add TotalReclaw to the plugin list. The plugin registers itself with the ID `totalreclaw`.

5. Verify the plugin appears in your OpenClaw skill/plugin list. You should see **TotalReclaw** described as "Zero-knowledge encrypted memory vault for AI agents."

---

## 3. First-Time Setup -- Key Generation

TotalReclaw uses a 12-word recovery phrase (called a BIP-39 mnemonic) as your master key. This phrase is used to derive your encryption key and your identity. You must generate it before using TotalReclaw for the first time.

> **WARNING: Your recovery phrase is the ONLY way to access your memories.**
> If you lose it, your memories are permanently unrecoverable.
> There is no reset, no recovery email, no support ticket.
> Write it down on paper and store it somewhere safe.

### Step 1: Generate your recovery phrase

Open a terminal, navigate to the plugin directory, and run:

```
cd /path/to/totalreclaw/skill/plugin
npx tsx generate-mnemonic.ts
```

You will see output like this:

```
  Your TotalReclaw master mnemonic (12 words):

  apple banana cherry dolphin eagle falcon grape honey iris jungle kite lemon

  WRITE THIS DOWN. If you lose it, your memories are unrecoverable.
  Set it as TOTALRECLAW_MASTER_PASSWORD in your .env file.
```

The 12 words shown above are an example. Your actual phrase will be different and unique to you.

### Step 2: Write it down

Write all 12 words on paper, in the exact order shown. Double-check every word. Store the paper somewhere safe -- a locked drawer, a safe, or wherever you keep important documents.

> **Do not store your recovery phrase in a text file on your computer, in a screenshot,
> or in a cloud notes app.** If someone gains access to these 12 words, they can
> decrypt all your memories.

### Step 3: Set your environment variables

Create or edit a `.env` file in the plugin directory (`skill/plugin/.env`) with the following contents:

```
TOTALRECLAW_MASTER_PASSWORD="word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"
TOTALRECLAW_SERVER_URL="https://api.totalreclaw.dev"
```

Replace `word1 word2 ...` with your actual 12-word phrase. Keep the quotes around it.

If the production server URL has not been provided to you yet, the TotalReclaw team will share it before your beta test begins.

Your agent's LLM API key (e.g., `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`) should already be configured in your OpenClaw environment. TotalReclaw auto-detects it — no extra LLM setup is needed.

### Step 4: Understand what happens behind the scenes

Your 12-word phrase derives both your encryption key (for encrypting and decrypting memories) and your on-chain wallet address (your identity on the network). You never need to manage crypto or interact with any blockchain directly -- it all happens automatically.

---

## 4. Understanding the Wallet Address

Your 12-word recovery phrase derives an Ethereum-compatible wallet address using a standard derivation path (`m/44'/60'/0'/0/0`). This is the same method used by popular wallets like MetaMask.

Here is what you need to know:

- **This wallet address is your identity** on Gnosis Chain, the blockchain where TotalReclaw stores encrypted data.
- **You never need to fund it.** The TotalReclaw paymaster covers all transaction fees (gas) on your behalf.
- **You never need to send transactions or interact with the blockchain.** The plugin handles everything automatically.
- **The same phrase always produces the same wallet address.** This is how recovery works -- enter your phrase on any device, and you get the same identity and encryption key.

If you want to view your derived wallet address, check the plugin logs after the first run. The plugin logs a message like `Registered new user: <user-id>` during initialization. Your wallet address is also stored in the credentials file (see [Configuration Reference](#12-configuration-reference) for its location).

---

## 5. Free Tier -- How It Works

TotalReclaw includes a free tier so you can start using it immediately:

- **Your first 100 memories per month are free** (beta; this limit may be adjusted).
- All transaction fees (gas) are covered by the TotalReclaw paymaster on Gnosis Chain. You pay nothing.
- No credit card, no crypto, and no signup beyond your recovery phrase are required.
- The relay server tracks your usage by wallet address.

When you approach the free tier limit, the agent will proactively tell you. For example:

> "You've used 90/100 free memories this month. Consider upgrading to Pro for unlimited storage."

If you reach the limit, you can either wait for the monthly reset or upgrade to Pro (see [Upgrading to Pro Tier](#9-upgrading-to-pro-tier)).

---

## 6. Automatic Memory (No Action Required)

Once TotalReclaw is installed and configured, it works in the background without any action from you. Two automatic behaviors are always running:

### Auto-Search (every message)

Before every agent turn, if your message is at least 5 characters long, the plugin automatically searches your stored memories for anything relevant. If it finds matching memories, it silently injects them into the agent's context so the agent can reference them naturally.

You do not need to ask the agent to recall anything -- it happens automatically. The agent will simply "know" relevant things from past conversations.

### Auto-Store (every 5 turns)

Every 5 conversation turns, the plugin automatically extracts important facts from your recent messages. It scores each fact by importance (1-10 scale), and facts that meet the minimum importance threshold (default: 3) are encrypted and stored.

This means you do not need to explicitly tell the agent to remember things. Preferences, decisions, and notable facts are captured automatically as you chat.

The number of turns between automatic extractions is configurable via the `TOTALRECLAW_EXTRACT_EVERY_TURNS` environment variable (default: `5`).

### Pre-Compaction Flush

When OpenClaw triggers a context compaction (because your conversation is getting long), TotalReclaw performs a full memory flush beforehand. This ensures no important information is lost when older messages are compressed or removed from context. This happens automatically with no action from you.

### Pre-Reset Flush

Similarly, if a session is reset or cleared, the plugin extracts and stores any important facts from the conversation before the reset occurs.

---

## 7. Explicit Memory Tools

In addition to automatic behaviors, TotalReclaw provides four tools you can use by asking the agent directly.

### 7.1 Remember -- `totalreclaw_remember`

Use this when you want to explicitly store something.

**Example prompts:**
- "Remember that I prefer dark mode in all my apps."
- "Store this: my database password rotation schedule is every 90 days."
- "Remember that the project deadline is March 15th."

**What happens behind the scenes:**
1. The plugin extracts the fact from your message.
2. It encrypts the fact with your key (AES-256-GCM).
3. It generates blind search indices (hashed keywords) so the server can find it later without seeing the plaintext.
4. It generates a content fingerprint to prevent duplicates.
5. It stores the encrypted blob on the server.

**Expected agent response:**
> "Memory stored (ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890)"

### 7.2 Recall -- `totalreclaw_recall`

Use this when you want to search your stored memories.

**Example prompts:**
- "What do you remember about my coding preferences?"
- "Recall anything related to the TotalReclaw project."
- "What databases have I mentioned preferring?"

**What happens behind the scenes:**
1. The plugin encrypts your query into blind search trapdoors.
2. The server returns matching encrypted candidates (up to several thousand).
3. The plugin decrypts all candidates on your device.
4. It re-ranks them using BM25 (text matching) + cosine similarity (semantic matching) + RRF fusion (combining scores).
5. The top results (default: 8) are returned.

**Expected agent response:**
> 1. User prefers PostgreSQL for databases (importance: 8/10) -- 2h ago [ID: ...]
> 2. User prefers TypeScript over JavaScript (importance: 7/10) -- 1d ago [ID: ...]

### 7.3 Forget -- `totalreclaw_forget`

Use this when you want to delete a specific memory.

**Example prompts:**
- "Forget that I said I like Java."
- "Delete the memory about my old email address."

**What happens behind the scenes:**
The agent first searches for matching memories using `totalreclaw_recall`, identifies the relevant one by ID, and then calls `totalreclaw_forget` with that ID. The memory is soft-deleted (marked as a tombstone with importance set to 0).

**Expected agent response:**
> "Memory a1b2c3d4-e5f6-7890-abcd-ef1234567890 deleted"

### 7.4 Export -- `totalreclaw_export`

Use this to get a copy of all your stored memories.

**Example prompts:**
- "Export all my memories as JSON."
- "Export my memories in markdown format."

**What happens behind the scenes:**
1. The plugin downloads all your encrypted memory blobs from the server.
2. It decrypts every memory on your device.
3. It formats them as JSON or Markdown (your choice).

**Expected agent response (JSON format):**
```json
[
  {
    "id": "a1b2c3d4-...",
    "text": "User prefers PostgreSQL for databases",
    "metadata": {
      "type": "preference",
      "importance": 0.8,
      "source": "explicit",
      "created_at": "2026-03-04T10:30:00.000Z"
    },
    "created_at": "2026-03-04T10:30:00.000Z"
  }
]
```

**Expected agent response (Markdown format):**
```
# Exported Memories (3)

1. **[preference]** User prefers PostgreSQL for databases (importance: 8/10)
   _ID: a1b2c3d4-... | Created: 2026-03-04T10:30:00.000Z_
2. **[fact]** User prefers TypeScript over JavaScript (importance: 7/10)
   _ID: b2c3d4e5-... | Created: 2026-03-04T10:25:00.000Z_
```

---

## 8. Testing Your Setup (Manual Validation)

Follow this checklist step by step to verify that TotalReclaw is working correctly. Each step has a clear expected outcome. If any step fails, see [Troubleshooting](#13-troubleshooting).

### Checklist

**Step 1: Store a fact via auto-extraction.**

1. Start a new conversation with your agent.
2. Say: "I always use PostgreSQL for databases and prefer TypeScript over JavaScript."
3. Continue chatting for at least 5 more turns about unrelated topics (this triggers auto-extraction).
4. **Expected:** The plugin silently extracts and stores your database and language preferences. You will not see a confirmation, but the facts are stored in the background.

**Step 2: Verify cross-session memory.**

5. Start a **new conversation** (to confirm memories persist across sessions).
6. Ask: "What databases do I prefer?"
7. **Expected:** The agent mentions PostgreSQL. It may phrase this naturally (e.g., "Based on what I know about you, you prefer PostgreSQL for databases.") or reference the memory explicitly.

**Step 3: Explicitly store a memory.**

8. Say: "Remember that my favorite color is blue."
9. **Expected:** The agent responds with a confirmation, such as: "Memory stored (ID: ...)"

**Step 4: Explicitly recall a memory.**

10. In another message, ask: "What is my favorite color?"
11. **Expected:** The agent responds with "blue."

**Step 5: Forget a memory.**

12. Say: "Forget that my favorite color is blue."
13. **Expected:** The agent searches for the memory, finds it, and confirms deletion: "Memory ... deleted."

**Step 6: Verify the memory is gone.**

14. Ask: "What is my favorite color?"
15. **Expected:** The agent does not mention blue, or says it does not know.

**Step 7: Export your memories.**

16. Say: "Export all my memories as JSON."
17. **Expected:** The agent returns a JSON array containing your stored facts (your database preference and any other facts extracted during the conversation). The favorite-color memory should not appear (it was deleted in Step 5).

### Validation Summary

| Step | Action | Expected Result | Pass? |
|------|--------|----------------|-------|
| 1-4 | Auto-store + auto-recall | Agent remembers PostgreSQL preference in new session | |
| 8-9 | Explicit remember | Confirmation with memory ID | |
| 10-11 | Explicit recall | Agent knows favorite color is blue | |
| 12-13 | Explicit forget | Confirmation of deletion | |
| 14-15 | Verify forget | Agent no longer knows favorite color | |
| 16-17 | Export | JSON with stored facts, no deleted memory | |

---

## 9. Upgrading to Pro Tier

When your free tier limit (100 memories/month, beta pricing) is reached, the agent will prompt you to upgrade.

**What you will see:**
> "You've used 100/100 free memories this month. Upgrade to Pro for $5/month for unlimited storage."

> **Note:** The Pro tier price ($5/month) is beta pricing and subject to change.

### Two payment options:

**Option A: Credit card**

1. Tell the agent: "I'd like to upgrade with a credit card."
2. The agent generates a Stripe Checkout URL and shares it with you.
3. Click the URL. It opens in your browser.
4. Complete the payment (card, Apple Pay, or Google Pay are all accepted).
5. After payment, Stripe sends a webhook to the relay server, which activates your subscription.
6. The agent confirms: "You're all set on the Pro tier."

**Option B: Cryptocurrency**

1. Tell the agent: "I'd like to upgrade with crypto."
2. The agent generates a Coinbase Commerce payment URL and shares it.
3. Click the URL. It opens in your browser.
4. Pay with USDC, USDT, or ETH from any supported network: Base, Ethereum, Solana, Polygon, or Arbitrum. No bridging is required.
5. After the payment is confirmed, Coinbase sends a webhook to the relay server, which activates your subscription.
6. The agent confirms: "You're all set on the Pro tier."

After upgrading, you can continue using TotalReclaw with higher write limits. Your subscription is tied to your wallet address, so it follows you across devices (as long as you use the same recovery phrase).

---

## 10. Recovery on a New Device

If you switch to a new computer or install TotalReclaw on a second agent, you can restore all your memories using your 12-word recovery phrase.

### Steps

1. Install the TotalReclaw plugin on the new device (follow [Section 2](#2-installation)).
2. Create a `.env` file and set `TOTALRECLAW_MASTER_PASSWORD` to your 12-word phrase:
   ```
   TOTALRECLAW_MASTER_PASSWORD="word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"
   TOTALRECLAW_SERVER_URL="https://api.totalreclaw.dev"
   ```
3. Start a conversation with your agent.
4. The plugin derives the same wallet address and encryption key from your phrase.
5. All your memories are automatically retrieved from the server and decrypted on your device.
6. If you have an active Pro subscription, it is recognized automatically (same wallet address).

> **If recovery does not work,** double-check every word in your recovery phrase and its
> exact order. BIP-39 phrases are case-sensitive (all lowercase). Even one wrong word
> derives a completely different encryption key and wallet address.

---

## 11. Running E2E Validation (Optional, for Technical Testers)

If you want to run the automated end-to-end test suite to verify the plugin against a mock server, follow these steps. This section requires familiarity with the command line and Node.js.

### Steps

1. Clone the repository and install dependencies:
   ```
   git clone https://github.com/p-diogo/totalreclaw.git
   cd totalreclaw/tests/e2e-functional
   npm install
   ```

2. Run the full test suite:
   ```
   npx tsx run-all.ts --scenarios=A,B,C,D,E,F,G,H --instances=server-improved
   ```

3. To run a subset of scenarios:
   ```
   npx tsx run-all.ts --scenarios=A,B --instances=server-improved
   ```

### What each scenario tests

| Scenario | Name | What it validates |
|----------|------|-------------------|
| A | Preferences | Storing and recalling user preferences (e.g., "I prefer dark mode") |
| B | Technical Facts | Technical knowledge recall (e.g., "I use PostgreSQL") |
| C | Noise Filtering | Low-importance facts are filtered out and not stored |
| D | Topic Switching | Correct recall after switching between multiple conversation topics |
| E | Long Conversations | Memory extraction and recall in extended conversations (many turns) |
| F | Subgraph Mode | End-to-end flow using the on-chain subgraph path (mock) |
| G | Pagination | Correct behavior when the memory vault has many entries (pagination) |
| H | Freeform | Open-ended conversational memory with diverse fact types |

### Expected result

All scenarios should show **PASS**. The test runner outputs a summary table and writes a detailed JSON report to `tests/e2e-functional/e2e-results/`.

### Available test instances

You can test against multiple configurations by specifying different instances:

| Instance | Description |
|----------|-------------|
| `server-improved` | Server mode with all retrieval improvements enabled |
| `server-baseline` | Server mode with baseline configuration |
| `server-recency` | Server mode with recency-weighted ranking |
| `subgraph-improved` | Subgraph mode with all improvements enabled |
| `subgraph-baseline` | Subgraph mode with baseline configuration |

Example running all instances:
```
npx tsx run-all.ts --scenarios=A,B,C,D,E,F,G,H --instances=server-improved,server-baseline,server-recency,subgraph-improved,subgraph-baseline
```

---

## 12. Configuration Reference

All configuration is done through environment variables, typically set in a `.env` file in the plugin directory (`skill/plugin/.env`).

### Required Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TOTALRECLAW_MASTER_PASSWORD` | Your 12-word BIP-39 recovery phrase. **Required.** | -- (none) |
| `TOTALRECLAW_SERVER_URL` | URL of the TotalReclaw relay server. **Required.** | `http://totalreclaw-server:8080` |

### LLM Provider Keys (auto-detected from your agent)

TotalReclaw auto-detects your agent's LLM provider and API key. No extra configuration is needed — the key your agent already uses for its own LLM calls is reused for fact extraction. The table below shows which providers are supported.

| Variable | Provider |
|----------|----------|
| `OPENAI_API_KEY` | OpenAI (GPT-4.1-mini for extraction) |
| `ANTHROPIC_API_KEY` | Anthropic (Claude Haiku for extraction) |
| `ZAI_API_KEY` | Z.AI (GLM-4.5-flash for extraction) |
| `GEMINI_API_KEY` | Google Gemini (Gemini 2.0 Flash for extraction) |
| `MISTRAL_API_KEY` | Mistral (Mistral Small for extraction) |
| `GROQ_API_KEY` | Groq (LLaMA 3.3 70B for extraction) |
| `DEEPSEEK_API_KEY` | DeepSeek (DeepSeek Chat for extraction) |
| `OPENROUTER_API_KEY` | OpenRouter (routes to Claude Haiku for extraction) |
| `XAI_API_KEY` | xAI (Grok-2 for extraction) |
| `TOGETHER_API_KEY` | Together AI |
| `CEREBRAS_API_KEY` | Cerebras |

### Optional Variables (Tuning)

| Variable | Description | Default |
|----------|-------------|---------|
| `TOTALRECLAW_CREDENTIALS_PATH` | Path to the credentials file (stores user ID and salt) | `/home/node/.totalreclaw/credentials.json` |
| `TOTALRECLAW_COSINE_THRESHOLD` | Minimum cosine similarity of the top result required to return memories. Lower = more permissive. | `0.15` |
| `TOTALRECLAW_MIN_IMPORTANCE` | Minimum importance score (1-10) for auto-extracted facts. Facts below this are silently dropped. | `3` |
| `TOTALRECLAW_EXTRACT_EVERY_TURNS` | Number of conversation turns between automatic extractions. | `5` |
| `TOTALRECLAW_RELEVANCE_THRESHOLD` | Minimum cosine relevance score for auto-injecting memories into context. | `0.3` |
| `TOTALRECLAW_SEMANTIC_SKIP_THRESHOLD` | Cosine similarity threshold for deduplication. Facts too similar to existing ones are skipped. | `0.85` |
| `TOTALRECLAW_CACHE_TTL_MS` | Hot cache time-to-live in milliseconds. Cached results within this window are reused for similar queries. | `300000` (5 minutes) |
| `TOTALRECLAW_TWO_TIER_SEARCH` | Enable two-tier search (LSH-only for auto-search, full word+LSH for explicit recall). | `true` |
| `TOTALRECLAW_LLM_MODEL` | **Advanced.** Override the auto-detected extraction model. TotalReclaw automatically derives a cheap model from your agent's provider (e.g., Anthropic → `claude-haiku-4-5`, OpenAI → `gpt-4.1-mini`). Only set this if the auto-derived model doesn't work for you. | Auto-detected |

### Subgraph Mode Variables (Advanced)

These variables are only relevant if you enable on-chain storage via the subgraph. Most beta testers should leave these at their defaults (server mode).

| Variable | Description | Default |
|----------|-------------|---------|
| `TOTALRECLAW_SUBGRAPH_MODE` | Set to `true` to use on-chain subgraph storage instead of the HTTP server. | `false` |
| `TOTALRECLAW_RELAY_URL` | Relay endpoint for on-chain writes (subgraph mode only). | `http://localhost:8545` |
| `TOTALRECLAW_SUBGRAPH_ENDPOINT` | GraphQL endpoint for subgraph reads (subgraph mode only). | `http://localhost:8000/subgraphs/name/totalreclaw` |
| `TOTALRECLAW_SUBGRAPH_PAGE_SIZE` | Maximum results per subgraph query page. | `5000` |
| `TOTALRECLAW_TRAPDOOR_BATCH_SIZE` | Number of trapdoors per batch in subgraph queries. | `5` |

---

## 13. Troubleshooting

### "TOTALRECLAW_MASTER_PASSWORD not set"

**Cause:** The `TOTALRECLAW_MASTER_PASSWORD` environment variable is missing or empty.

**Fix:** Make sure your `.env` file in the plugin directory contains:
```
TOTALRECLAW_MASTER_PASSWORD="your twelve words here"
```
Restart the plugin after saving the file.

### Memories not appearing in new conversations

**Cause:** The plugin may not be connecting to the correct server, or the auto-search hook may not be triggering.

**Fix:**
1. Verify that `TOTALRECLAW_SERVER_URL` in your `.env` file points to the correct server URL.
2. Try an explicit recall: "What do you remember about me?" If this returns results, auto-search is working but may have filtered your query as irrelevant (messages shorter than 5 characters are skipped).
3. Check the plugin logs for error messages (look for lines starting with `TotalReclaw:`).

### "Free tier quota exceeded"

**Cause:** You have used all 100 free memories for the month.

**Fix:** Either upgrade to Pro (see [Section 9](#9-upgrading-to-pro-tier)) or wait for the monthly reset.

### Slow retrieval

**Cause:** Network latency to the relay server, or a large number of stored memories.

**Fix:**
1. Check your internet connection.
2. The hot cache (5-minute TTL) speeds up repeated queries. If you query the same topic twice within 5 minutes, the second query is near-instant.
3. If you have thousands of memories, retrieval may take a few seconds for the initial query each session. This is normal -- the plugin downloads and decrypts candidates client-side.

### Wrong memories returned or low relevance

**Cause:** The search and reranking thresholds may not match your use case.

**Fix:** Try adjusting these environment variables:
- `TOTALRECLAW_COSINE_THRESHOLD` -- lower the value (e.g., `0.10`) to be more permissive, or raise it (e.g., `0.25`) to be stricter.
- `TOTALRECLAW_RELEVANCE_THRESHOLD` -- lower the value (e.g., `0.15`) to inject memories more often, or raise it to reduce noise.
- `TOTALRECLAW_MIN_IMPORTANCE` -- raise the value (e.g., `5`) to only store more important facts.

### No LLM available for extraction

**Cause:** The plugin could not find an API key for any supported LLM provider.

**Fix:** Add at least one LLM provider API key to your `.env` file. The simplest option:
```
OPENAI_API_KEY="sk-your-key-here"
```

### Recovery phrase does not restore memories

**Cause:** One or more words in the recovery phrase are wrong or in the wrong order.

**Fix:**
1. Double-check every word against what you wrote down.
2. BIP-39 phrases are **all lowercase**. Make sure you did not capitalize any words.
3. Verify the word order is exactly right. Even one wrong word derives a completely different key and wallet address, meaning the server will treat you as a new user.
4. Make sure there is exactly one space between each word, no leading or trailing spaces.

### Plugin logs show "LLM call failed" errors

**Cause:** Your LLM API key may be invalid, expired, or rate-limited.

**Fix:**
1. Test your API key independently (e.g., make a simple curl request to the provider's API).
2. Check that your API key has not expired or run out of credits.
3. If rate-limited, the plugin will retry on the next extraction cycle (every 5 turns by default).

---

## 14. Known Limitations (Beta)

This is a beta release. The following items are known limitations that will be addressed in future updates:

- **Free tier threshold:** The limit of 100 memories/month is provisional and may be adjusted based on usage data.
- **Subscription pricing:** The Pro tier price of $5/month is beta pricing and not yet finalized.
- **Billing tools:** The upgrade flow (`totalreclaw_status`, `totalreclaw_upgrade`) may not be fully wired in all environments. If the agent cannot generate a checkout URL, contact the TotalReclaw team directly.
- **Auto-extraction timing:** The `TOTALRECLAW_EXTRACT_EVERY_TURNS` config controls extraction frequency. The plugin currently fires extraction on the `agent_end` hook every N turns. The spec mentions an `autoExtractEveryTurns` config key, but the plugin uses the environment variable approach.
- **Batch writes:** On-chain writes are currently sent one fact at a time. Batch writes for gas optimization are not yet implemented.
- **Decay and eviction engine:** The importance decay formula runs, but tuning is ongoing. Low-importance facts decay over time and may be evicted.
- **Subgraph mode:** On-chain storage via Gnosis Chain subgraph is functional but still in testing. Beta testers should use the default server mode unless specifically asked to test subgraph mode.

---

## Further Reading

For those who want to understand the technical architecture:

- **E2EE Architecture:** `docs/specs/totalreclaw/architecture.md` -- how encryption, LSH blind indices, and zero-knowledge search work.
- **Skill Specification:** `docs/specs/totalreclaw/skill-openclaw.md` -- full plugin spec with data models, triggers, and processing pipelines.
- **Billing and Onboarding:** `docs/specs/subgraph/billing-and-onboarding.md` -- tier structure, payment infrastructure, and Gnosis Chain rationale.
- **Seed-to-Subgraph:** `docs/specs/subgraph/seed-to-subgraph.md` -- how BIP-39 derivation connects to on-chain identity.
- **Product Requirements:** `docs/prd.md` -- the full product requirements document.

---

*This guide was written for TotalReclaw beta v0.2.0. If you encounter issues not covered here, contact the TotalReclaw team.*
