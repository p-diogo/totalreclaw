# Claw Hub Publishing Checklist

Internal notes for preparing the OpenMemory skill for listing on [clawhub.ai](https://clawhub.ai).

---

## Readiness Status

### Ready

- [x] `skill.json` -- Metadata, hooks, tools, config, and Claw Hub fields populated
- [x] `SKILL.md` -- YAML frontmatter with full metadata; tools, hooks, prompts, and LLM instructions documented
- [x] `README.md` -- Public-facing documentation with quick start, benchmarks, configuration, and architecture
- [x] Hooks defined: `before_agent_start`, `agent_end`, `pre_compaction`
- [x] Tools defined: `openmemory_remember`, `openmemory_recall`, `openmemory_forget`, `openmemory_export`
- [x] Environment variables documented (`OPENMEMORY_SERVER_URL`, `OPENMEMORY_MASTER_PASSWORD`)
- [x] Benchmark comparison table (98.1% recall@8 with 100% privacy)
- [x] License declared (MIT)
- [x] Keywords and OS compatibility specified

### Not Yet Ready

- [ ] **Screenshots** (3-5 required, 1920x1080 PNG) -- must be created manually
  - Suggested screenshots:
    1. Agent remembering a user preference (tool call + response)
    2. Agent recalling memories at conversation start (context injection)
    3. Memory export in JSON format
    4. Encryption in action (showing encrypted vs plaintext data)
    5. Configuration / environment variable setup
- [ ] **Demo video** (optional but recommended, 30-90 seconds)
  - Show a full cycle: store a memory, start a new conversation, recall it automatically
  - Highlight that the server never sees plaintext
  - Keep it under 90 seconds
- [ ] **Icon/logo** (256x256 PNG, transparent background)
- [ ] **Server deployment guide** -- users need a running OpenMemory server; link to deployment docs
- [ ] **End-to-end integration tests** -- verify the full clawhub install flow works
- [ ] **npm package published** -- `@openmemory/skill` must be on npm before listing

---

## Claw Hub Publishing Process

### Step 1: Prepare Assets

1. Create 3-5 screenshots at 1920x1080 resolution, saved as PNG
2. (Optional) Record a 30-90 second demo video
3. Create a 256x256 skill icon with transparent background
4. Verify all files are up to date:
   - `skill.json`
   - `SKILL.md` (with YAML frontmatter)
   - `README.md`

### Step 2: Validate Locally

```bash
# Validate skill manifest
clawhub validate ./skill

# Test the install flow locally
clawhub install --local ./skill

# Run the skill in a test agent
clawhub test openmemory
```

### Step 3: Submit for Review

```bash
# Authenticate with Claw Hub
clawhub auth login

# Publish the skill (submits for review)
clawhub publish ./skill
```

### Step 4: Security Review

Claw Hub runs an automated security review that takes **2-5 business days**. The review includes:

- **Automated scanning** for undeclared environment variables (any env var access not listed in `skill.json` `requires.env` will be flagged)
- **Dependency audit** for known vulnerabilities
- **Permission scope check** -- verify the skill only requests necessary permissions
- **Code review** for data exfiltration patterns (network calls to undeclared endpoints)
- **Encryption verification** -- skills claiming E2EE will have their crypto implementation reviewed

If issues are found, you will receive a report with required fixes. Address them and resubmit.

### Step 5: Go Live

Once approved:
- The skill appears on [clawhub.ai/skills/openmemory](https://clawhub.ai/skills/openmemory)
- Users can install with `clawhub install openmemory`
- Monitor install metrics and reviews on the Claw Hub dashboard

---

## Post-Publishing Maintenance

- **Version updates**: Bump version in `skill.json` and `SKILL.md` frontmatter, then `clawhub publish` again
- **Responding to reviews**: Monitor the Claw Hub dashboard for user feedback
- **Security patches**: Critical security fixes can be fast-tracked (24-48 hours review)
- **Deprecation**: Use `clawhub deprecate openmemory@0.1.0` if a version needs to be pulled

---

## Notes

- The `OPENMEMORY_MASTER_PASSWORD` env var will likely trigger extra scrutiny during security review. Prepare documentation explaining the zero-knowledge architecture and that the password never leaves the client.
- Claw Hub listings with benchmark data (like our recall comparison table) tend to rank higher in search results.
- Consider adding a "Verified E2EE" badge request once the crypto review passes.
