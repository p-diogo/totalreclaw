# TotalReclaw -- Private Memory for Your AI Agent

**What it is:** Encrypted memory that works across sessions. Your AI remembers your preferences, decisions, and context -- and only you can read it. Not even our server sees your data.

**Works with:** OpenClaw, Claude Desktop, Cursor, or any MCP-compatible agent.

---

## Quick Start

### OpenClaw (recommended -- fully automatic)

During private beta, install from the GitHub repo. Ask your agent:

> "Install the totalreclaw skill from https://github.com/p-diogo/totalreclaw"

Or install manually via terminal:

```bash
git clone https://github.com/p-diogo/totalreclaw.git ~/totalreclaw
cd ~/totalreclaw/skill/plugin && npm install
openclaw plugins install -l ./
```

The agent handles the rest: generates your encryption keys and registers you. You'll be asked to write down a 12-word recovery phrase -- that's the only thing you need to keep safe.

> **Note:** After beta, this will be available directly via `clawhub install totalreclaw`.

**After setup, memory is fully automatic:**
- Your agent remembers important things from conversations (preferences, decisions, facts)
- At the start of each conversation, relevant memories are loaded automatically
- You never need to tell your agent to "remember" anything -- it just does

You can always be explicit too -- "remember that I prefer dark mode" or "what do you remember about my project?" -- but it's not required.

### Claude Desktop / Cursor / Other MCP Agents

1. Run the setup wizard:
   ```bash
   npx @totalreclaw/mcp-server setup
   ```
   The wizard generates your recovery phrase, sets up encryption, registers you, and prints a config snippet to paste into your MCP client.

2. Paste the config snippet (the wizard tells you exactly where).

3. Start chatting. Your agent has memory tools it can use when appropriate.

**Note:** MCP agents don't have automatic memory like OpenClaw. The agent uses the tools when contextually appropriate, and you can also explicitly ask it to remember or recall things.

---

## How It Works

1. **You set up with a 12-word recovery phrase** (like a crypto wallet)
2. **All memories are encrypted on your device** before reaching our server
3. **The server only stores encrypted blobs** -- it can never read them
4. **Same phrase on any device = same keys = same memories**

---

## What Gets Remembered

Your agent extracts and stores atomic facts from conversations:

| Type | Example |
|------|---------|
| **Preference** | "User prefers TypeScript over JavaScript" |
| **Decision** | "User decided to use PostgreSQL for the main database" |
| **Fact** | "User works at Acme Corp" |
| **Goal** | "User wants to launch by Q2" |

Each fact is scored by importance. Low-importance facts decay over time; critical ones persist.

---

## Recovery & Multi-Device

Your 12-word recovery phrase is the only thing you need to access your memories from a new device or agent. Same phrase = same keys = same data.

**Write it down and store it safely.** If you lose it, your memories are unrecoverable -- that's the point of zero-knowledge encryption.

To recover: just run the setup again (OpenClaw: reinstall the skill; MCP: re-run the setup wizard) and enter your existing phrase when prompted.

---

## Free Tier & Upgrading

| Tier | Writes | Reads | Price |
|------|--------|-------|-------|
| **Free** | 100/month | Unlimited | $0 |
| **Pro** | 10,000/month | Unlimited | $2-5/month |

- Counter resets at the start of each calendar month
- Pay with card (Stripe) or crypto (Coinbase Commerce)
- When you hit the limit, your agent tells you and provides an upgrade link

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Setup not working | Re-run: OpenClaw reinstall or `npx @totalreclaw/mcp-server setup` |
| "Not authenticated" / 401 | Check your recovery phrase -- exact words, exact order |
| Memories not appearing | Try an explicit recall: "what do you remember about X?" |
| Quota exceeded (403) | Wait for monthly reset or upgrade to Pro |

For detailed technical troubleshooting, see [beta-tester-guide-detailed.md](./beta-tester-guide-detailed.md).

---

## Known Limitations (Beta)

- Free tier limit (100 writes/month) and Pro pricing ($2-5/month) are not finalized
- MCP agents rely on explicit tool use rather than automatic memory hooks
- Beta runs on testnet infrastructure -- expect occasional downtime

---

## Further Reading

- [Detailed technical guide](./beta-tester-guide-detailed.md) -- full reference with architecture, configuration, and environment variables
- [totalreclaw.xyz](https://totalreclaw.xyz) -- project homepage

---

*TotalReclaw beta v0.2.0 -- [totalreclaw.xyz](https://totalreclaw.xyz)*
