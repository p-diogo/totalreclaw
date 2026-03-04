# Handoff: Beta Tester User Guide for TotalReclaw MVP

## 1. Purpose and Scope

Write a **Beta Tester User Guide** -- a step-by-step document aimed at internal testers who want to evaluate TotalReclaw end-to-end. The guide must walk a non-technical user through the entire lifecycle: installation, key setup, free tier usage, memory storage and retrieval (automatic and explicit), upgrade to Pro, and validation that everything works.

This guide is the primary onboarding artifact for MVP beta testers. It supersedes any earlier PoC user guide.

**What this guide IS:**
- A reproducible setup-and-test walkthrough for a real OpenClaw instance.
- A reference for every user-facing configuration option.
- A troubleshooting section for common failure modes.

**What this guide is NOT:**
- An architecture deep-dive (point readers to the specs instead).
- A developer guide (no subgraph mapping code, no contract deployment).
- A production operations runbook.

---

## 2. Target Audience

- Internal beta testers (non-technical, or lightly technical).
- They have an OpenClaw account and can install skills/plugins.
- They do NOT have Solidity, Docker, or backend experience.
- They may or may not have a crypto wallet -- the guide must cover both "fresh seed" and "import existing seed" paths.

---

## 3. Prerequisites the Guide Should State

The guide should tell testers they need:

1. **An OpenClaw account** with an active workspace.
2. **Node.js >= 18** installed (for the plugin).
3. **An LLM API key** -- either an OpenAI key or an Anthropic key (used by the plugin for fact extraction and embeddings). The plugin auto-detects which provider is available.
4. **Internet access** -- the plugin communicates with the TotalReclaw relay server and (in subgraph mode) the Graph Network.
5. **A safe place to write down 12 words** -- the BIP-39 recovery phrase is the only way to recover memories. Stress this heavily.

The guide should NOT assume testers have:
- Docker, Python, or PostgreSQL installed.
- Any crypto tokens or wallet software.
- Familiarity with environment variables (explain `.env` files step by step).

---

## 4. Detailed Section Outline

### Section 1: What Is TotalReclaw? (1 paragraph)

One-paragraph plain-English summary: "TotalReclaw is a private, encrypted memory layer for your AI agent. It remembers things you tell it across sessions, and only you can decrypt those memories -- not even the server can read them."

### Section 2: Installation

1. Navigate to OpenClaw skill marketplace (or manual install path).
2. Install the TotalReclaw plugin (`skill/plugin/`).
3. Verify the plugin appears in the skill list.

### Section 3: First-Time Setup -- Key Generation

1. **Generate your recovery phrase.** Two options:
   - **Option A (automatic):** The plugin generates a 12-word BIP-39 mnemonic on first run. The agent will display it.
   - **Option B (manual):** Run `npx tsx generate-mnemonic.ts` in the `skill/plugin/` directory. This prints a 12-word phrase.
2. **WRITE IT DOWN on paper.** The guide must include a prominent warning: "If you lose this phrase, your memories are permanently unrecoverable. There is no reset, no recovery email, no support ticket."
3. **Set the environment variable.** Walk through creating/editing an `.env` file with:
   ```
   TOTALRECLAW_MASTER_PASSWORD="word1 word2 word3 ... word12"
   TOTALRECLAW_SERVER_URL="https://api.totalreclaw.dev"
   ```
4. **Explain what happens behind the scenes** (one sentence): "This phrase derives your encryption key AND your on-chain wallet address. You never need to manage crypto."

### Section 4: Understanding the Wallet Address

1. Explain that the 12 words derive an Ethereum-compatible wallet address via BIP-39 (`m/44'/60'/0'/0/0`).
2. This wallet address is your identity on the Gnosis Chain for on-chain storage.
3. The user never needs to fund it, send transactions, or interact with it directly -- the paymaster covers gas.
4. Show how to view the derived address (if there is a command or log line that displays it).

### Section 5: Free Tier -- How It Works

1. Explain: "Your first N memories are free. Gas fees are covered by the TotalReclaw paymaster (Pimlico) on Gnosis Chain."
2. No credit card, no crypto, no signup beyond the seed phrase.
3. The relay server tracks usage per wallet address.
4. When nearing the limit, the agent will proactively warn: "You've used X/Y free memories."

### Section 6: Automatic Memory (No Action Required)

Explain the two automatic behaviors:

1. **Auto-search (every message):** Before every agent turn (messages >= 5 characters), the plugin searches for relevant past memories and silently injects them into context. The user does not need to do anything.
2. **Auto-store (every 5 turns):** Every 5 conversation turns, the plugin extracts facts from recent messages, scores their importance, encrypts them, and stores them. Configurable via `TOTALRECLAW_EXTRACT_EVERY_TURNS`.
3. Pre-compaction flush: When OpenClaw triggers compaction, a full memory flush runs automatically.

### Section 7: Explicit Memory Tools

Walk through each of the 4 tools with example prompts:

1. **`totalreclaw_remember`** -- "Remember that I prefer dark mode in all my apps."
   - What happens: fact extraction, encryption, blind index generation, storage.
   - Expected agent response: confirmation of what was stored.

2. **`totalreclaw_recall`** -- "What do you remember about my coding preferences?"
   - What happens: query encryption, blind trapdoor search, candidate retrieval, client-side decryption, BM25+cosine reranking.
   - Expected agent response: top relevant memories with source info.

3. **`totalreclaw_forget`** -- "Forget that I said I like Java."
   - What happens: soft-delete (tombstone), importance set to 0.
   - Expected agent response: confirmation of deletion.

4. **`totalreclaw_export`** -- "Export all my memories as JSON."
   - What happens: all memories decrypted client-side, returned as JSON or Markdown.
   - Expected agent response: a file or text block with all memories.

### Section 8: Testing Your Setup (Manual Validation)

A checklist the tester can follow:

1. Start a new conversation. Say something memorable: "I always use PostgreSQL for databases and prefer TypeScript over JavaScript."
2. Continue chatting for 5+ turns about unrelated topics.
3. Start a NEW conversation (to confirm cross-session memory).
4. Ask: "What databases do I prefer?" -- expect the agent to recall PostgreSQL.
5. Explicitly: "Remember that my favorite color is blue."
6. In another turn: "What's my favorite color?" -- expect "blue."
7. "Forget that my favorite color is blue."
8. "What's my favorite color?" -- expect it to be gone or uncertain.
9. "Export all my memories as JSON." -- expect a JSON blob with your facts.

### Section 9: Upgrading to Pro Tier

1. When the free tier limit is reached, the agent will prompt: "You've used X/Y free memories. Upgrade for $Z/month."
2. Two payment options:
   - **Credit card:** Agent generates a Stripe Checkout URL. Click it, complete payment.
   - **Crypto:** Agent generates a Coinbase Commerce URL. Pay with USDC/USDT/ETH from any supported chain (Base, Ethereum, Solana, Polygon, Arbitrum).
3. After payment, the webhook fires and the relay activates the subscription.
4. The agent confirms: "You're all set on the Pro tier."
5. Continue using TotalReclaw with higher/unlimited write limits.

### Section 10: Recovery on a New Device

1. Install the plugin on the new device/agent.
2. Set `TOTALRECLAW_MASTER_PASSWORD` to your 12-word phrase.
3. The plugin derives the same wallet address and encryption key.
4. All memories are automatically retrieved from the subgraph and decrypted.
5. Existing subscription is recognized (same wallet address).

### Section 11: Running E2E Validation (Optional, for Technical Testers)

For testers who want to run the automated test suite:

1. Clone the repo, install dependencies.
2. `cd tests/e2e-functional`
3. `npx tsx run-all.ts --scenarios=A,B,C,D,E,F,G,H --instances=server-improved`
4. Explain what the scenarios test (A=preferences, B=technical facts, C=noise filtering, D=topic switching, E=long conversations, F=subgraph, G=pagination, H=freeform).
5. Expected result: all scenarios PASS.

### Section 12: Configuration Reference

A table of all user-facing environment variables with defaults:

| Variable | Description | Default |
|----------|-------------|---------|
| `TOTALRECLAW_MASTER_PASSWORD` | 12-word BIP-39 mnemonic (required) | -- |
| `TOTALRECLAW_SERVER_URL` | Relay server URL (required) | `http://totalreclaw-server:8080` |
| `TOTALRECLAW_CREDENTIALS_PATH` | Path to credentials.json | `/home/node/.totalreclaw/credentials.json` |
| `TOTALRECLAW_COSINE_THRESHOLD` | Minimum cosine similarity for recall results | `0.15` |
| `TOTALRECLAW_MIN_IMPORTANCE` | Minimum importance score to auto-store (1-10) | `3` |
| `TOTALRECLAW_EXTRACT_EVERY_TURNS` | Turns between automatic extractions | `5` |
| `TOTALRECLAW_RELEVANCE_THRESHOLD` | Minimum relevance score for injected context | `0.3` |
| `TOTALRECLAW_SEMANTIC_SKIP_THRESHOLD` | Dedup similarity threshold | `0.85` |
| `TOTALRECLAW_CACHE_TTL_MS` | Hot cache TTL in milliseconds | `300000` (5 min) |
| `TOTALRECLAW_TWO_TIER_SEARCH` | Enable two-tier (LSH-only + word) search | `true` |
| `TOTALRECLAW_SUBGRAPH_MODE` | Use on-chain subgraph instead of HTTP server | `false` |
| `TOTALRECLAW_RELAY_URL` | Relay endpoint for subgraph writes | `http://localhost:8545` |
| `TOTALRECLAW_SUBGRAPH_ENDPOINT` | GraphQL endpoint for subgraph reads | `http://localhost:8000/subgraphs/name/totalreclaw` |
| `TOTALRECLAW_SUBGRAPH_PAGE_SIZE` | Max results per subgraph query page | `5000` |
| `TOTALRECLAW_LLM_MODEL` | Override LLM model for extraction | Auto-detected |

### Section 13: Troubleshooting

Cover these common issues:

1. **"TOTALRECLAW_MASTER_PASSWORD not set"** -- The env var is missing or empty.
2. **Memories not appearing in new conversations** -- Check that `TOTALRECLAW_SERVER_URL` points to the correct server. Verify with an explicit `recall` call.
3. **"Free tier quota exceeded"** -- Upgrade to Pro or wait for monthly reset.
4. **Slow retrieval** -- Check network connectivity to the relay server. The hot cache (5 min TTL) should speed up repeated queries.
5. **Wrong memories returned / low relevance** -- Try adjusting `TOTALRECLAW_COSINE_THRESHOLD` (lower = more permissive) or `TOTALRECLAW_RELEVANCE_THRESHOLD`.
6. **Recovery phrase doesn't restore memories** -- Double-check every word and its order. BIP-39 is case-sensitive (lowercase). Even one wrong word derives a completely different key.

### Section 14: Known Limitations (Beta)

Be honest about what is not yet polished:

- Free tier threshold is not yet finalized (TBD).
- Subscription price ($2-5/mo) is not yet finalized.
- Billing tools (`totalreclaw_status`, `totalreclaw_upgrade`) may not be fully wired.
- The `autoExtractEveryTurns` config key exists in the spec but extraction is currently every-turn on `agent_end` hook.
- Batch writes for gas optimization are not yet implemented.
- Decay/eviction engine runs but tuning is ongoing.

---

## 5. Key Files the Implementing Agent Should Read

Read these files in order before writing the guide:

| Priority | File | Why |
|----------|------|-----|
| **1** | `CLAUDE.md` | Project conventions, repo structure, agent rules. |
| **2** | `docs/specs/totalreclaw/skill-openclaw.md` | Full plugin spec: triggers, tools, config, data models. |
| **3** | `docs/specs/subgraph/billing-and-onboarding.md` | Billing tiers, paymaster flow, onboarding UX, Gnosis Chain rationale. |
| **4** | `skill/plugin/index.ts` | Actual plugin code: env vars, hooks, tools, initialization flow. |
| **5** | `skill/plugin/generate-mnemonic.ts` | BIP-39 mnemonic generation script (the user-facing key setup tool). |
| **6** | `skill/plugin/setup.sh` | Existing setup script for reference (minimal). |
| **7** | `skill/plugin/subgraph-store.ts` | Subgraph mode env vars (`TOTALRECLAW_SUBGRAPH_MODE`, `TOTALRECLAW_RELAY_URL`, etc.). |
| **8** | `skill/plugin/subgraph-search.ts` | Subgraph search config (`PAGE_SIZE`, `TRAPDOOR_BATCH_SIZE`). |
| **9** | `skill/plugin/reranker.ts` | Reranking pipeline (BM25 + cosine + RRF) for understanding retrieval quality. |
| **10** | `docs/specs/subgraph/seed-to-subgraph.md` | Seed-to-subgraph architecture (BIP-39 derivation, recovery flow). |
| **11** | `tests/e2e-functional/run-all.ts` | E2E test runner (for Section 11 of the guide). |
| **12** | `tests/e2e-functional/scenarios/` | Individual scenario files (A through H) for describing what each tests. |
| **13** | `skill/plugin/hot-cache-wrapper.ts` | Hot cache behavior (for troubleshooting section). |
| **14** | `skill/plugin/llm-client.ts` | LLM client auto-detection logic (for explaining provider requirements). |

---

## 6. Acceptance Criteria

The guide is "done" when:

1. **Completeness:** All 14 sections from the outline above are written with enough detail that a non-technical tester can follow them without asking questions.
2. **Reproducibility:** A tester with only the guide and an OpenClaw account can go from zero to a working TotalReclaw setup, store memories, retrieve them across sessions, and export them.
3. **Accuracy:** Every environment variable name, default value, tool name, and command matches the actual codebase. No placeholders like "TBD" for things that are already decided.
4. **Tone:** Friendly, direct, no jargon without explanation. When crypto/blockchain concepts must be mentioned, explain them in one plain-English sentence.
5. **Warnings:** The recovery phrase warning is prominent and impossible to miss (bold, repeated, separate callout box).
6. **Testable:** The Section 8 checklist can be executed step-by-step with pass/fail outcomes.
7. **Self-contained:** The guide does not require reading any spec files. All necessary information is in the guide itself (with optional links to specs for the curious).
8. **Format:** Markdown, well-structured with headers, numbered steps, tables, and code blocks. No emojis.
9. **Location:** Written to `docs/guides/beta-tester-guide.md`.

---

## 7. Open Questions and Decisions for the Implementing Agent

| # | Question | Context | Suggested Default |
|---|----------|---------|-------------------|
| 1 | What is the production `TOTALRECLAW_SERVER_URL`? | The default in code is `http://totalreclaw-server:8080` (Docker internal). Beta testers need the public URL. | Use `https://api.totalreclaw.dev` as the documented URL. If not yet deployed, note it as "will be provided by the TotalReclaw team." |
| 2 | Is the OpenClaw skill marketplace live, or is install manual? | The guide needs to describe the actual install path. | Check if there is a marketplace entry. If not, document the manual install path (clone repo, `npm install`, configure in OpenClaw settings). |
| 3 | What is the free tier limit? | The billing spec says "TBD -- to be tuned after observing real usage patterns." | Write "100 memories/month (subject to change during beta)" as a working default, and note it may be adjusted. The code has `FREE_TIER_LIMIT` default of 100. |
| 4 | What is the Pro tier price? | Billing spec says "$2-5/month (TBD)." | Write "$5/month (beta pricing, subject to change)" and note it is not finalized. |
| 5 | Should the guide cover subgraph mode vs server mode? | The plugin supports both `TOTALRECLAW_SUBGRAPH_MODE=true` (on-chain) and the default HTTP server mode. | Default the guide to server mode (simpler). Mention subgraph mode in an "Advanced" subsection or appendix. Subgraph mode is the long-term target but server mode is simpler for beta. |
| 6 | Should the guide include screenshots? | Screenshots would help non-technical users but require a running instance. | Write the guide text-only first. Add placeholder notes like "[Screenshot: OpenClaw skill installation screen]" where screenshots would help. Screenshots can be added in a follow-up pass. |
| 7 | Is `credentials.json` auto-created on first run, or must the user create it? | The plugin auto-registers and creates credentials on first run if `TOTALRECLAW_MASTER_PASSWORD` is set. | Document the auto-creation flow. The user only needs to set the env var; the plugin handles the rest. |
| 8 | Does the agent actually display the mnemonic on first run? | Need to verify in `index.ts` whether the plugin logs or displays the generated mnemonic to the user. | Check the `initClient()` function in `index.ts`. If it does not display the mnemonic, the guide should instruct users to generate it manually first with `generate-mnemonic.ts`. |

---

## 8. Style and Formatting Notes

- Use second person ("you") throughout.
- Use numbered steps for procedures, bullet points for lists.
- Use fenced code blocks for commands and env var examples.
- Use tables for reference data (env vars, tools).
- Use blockquotes (`>`) for warnings and important notes.
- Keep paragraphs short (3-4 sentences max).
- The guide should be readable in ~15 minutes and executable in ~30 minutes.
