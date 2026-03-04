# Handoff: Gas Cost Extrapolation for Power Users vs Regular Users

## 1. Purpose & Scope

TotalReclaw stores encrypted facts on Gnosis Chain at ~$0.00076/fact. The skill plugin auto-extracts facts every 5 turns, but each extraction batch passes through an importance filter (drop facts below threshold 3) and a semantic dedup filter (drop near-duplicates at cosine >= 0.9) before any on-chain write occurs.

This analysis needs to answer: **How many facts actually land on-chain per hour/day/month for different user profiles, and what does that cost?** The goal is to validate whether the free tier (100 facts/month) and Pro pricing ($2-5/month) are viable, and whether the extraction frequency (every 5 turns) is correctly tuned.

## 2. Key Assumptions to Verify

Each of these is stated as a current assumption. The implementing agent should verify or refine each one by reading the source files and reasoning about realistic usage.

| # | Assumption | Source | Confidence |
|---|-----------|--------|------------|
| A1 | Extraction fires every 5 turns (`AUTO_EXTRACT_EVERY_TURNS=5`) | `skill/plugin/index.ts:117` | HIGH -- read the code |
| A2 | Each extraction batch produces 1-5 raw facts | LLM extraction prompt in `extractor.ts` | MEDIUM -- needs empirical reasoning |
| A3 | The importance filter (`MIN_IMPORTANCE_THRESHOLD=3`) drops ~10-30% of raw facts | `skill/plugin/index.ts:395-425` | LOW -- no empirical data exists; estimate from prompt analysis |
| A4 | The semantic dedup filter (cosine >= 0.9) drops ~5-15% of remaining facts per batch | `skill/plugin/semantic-dedup.ts` | LOW -- depends on conversation style |
| A5 | A "turn" = 1 user message + 1 agent response (2 messages) | OpenClaw hook semantics | HIGH |
| A6 | Gas cost per fact on Gnosis Chain is $0.00076 | `docs/specs/subgraph/billing-and-onboarding.md` (Section 3 table) | HIGH -- from prior chain cost analysis |
| A7 | `before_compaction` and `before_reset` hooks also extract facts (full context, not turn-only) | `skill/plugin/index.ts:1457-1500` | HIGH -- read the code |
| A8 | Compaction typically fires every ~50-100 turns (when context window fills) | OpenClaw behavior | MEDIUM -- verify with OpenClaw docs if possible |

## 3. User Profiles to Model

| Profile | Sessions/day | Turns/session | Hours/day | Description |
|---------|:---:|:---:|:---:|-------------|
| **Casual** | 1-2 | 10-15 | 0.5-1 | Quick Q&A, occasional usage |
| **Regular** | 2-4 | 15-25 | 1-2 | Daily AI assistant user |
| **Power** | 4-8 | 20-40 | 4-8 | Developer/researcher, heavy daily usage |
| **Extreme** | 8+ | 30-50 | 8+ | All-day coding assistant, multiple long sessions |

## 4. Methodology

Execute the following steps in order. Each step depends on the previous.

### Step 1: Verify the extraction pipeline

Read the following files and trace the full write path:

1. `skill/plugin/index.ts` -- the `agent_end` hook (line ~1426-1451). Note the turn counter, the call to `extractFacts()`, the call to `filterByImportance()`, and the call to `storeExtractedFacts()`.
2. `skill/plugin/extractor.ts` -- the LLM extraction prompt. Note the system prompt instructs the LLM to "only extract facts with importance >= 6" and score 1-10. Consider: how many facts does a typical 5-turn conversation segment yield?
3. `skill/plugin/index.ts` -- the `filterByImportance()` function (line ~392-425). Note `MIN_IMPORTANCE_THRESHOLD` defaults to 3. Since the extractor prompt already filters to importance >= 6, the threshold=3 filter is mostly a safety net. Estimate the realistic pass-through rate.
4. `skill/plugin/semantic-dedup.ts` -- the `deduplicateBatch()` function. This deduplicates within a single extraction batch only (not cross-batch). Estimate what fraction of facts within a 1-5 fact batch are near-duplicates.
5. `skill/plugin/index.ts` -- the `storeExtractedFacts()` function. Trace how many on-chain transactions result from a single batch.

Also account for the non-periodic hooks:
- `before_compaction` (line ~1457-1482): extracts from the FULL conversation context, not just the last 5 turns. This is a burst of facts when context fills up.
- `before_reset` (line ~1488+): similar full-context extraction on session reset.

### Step 2: Estimate raw facts per extraction

Based on the extraction prompt analysis:
- The prompt instructs: extract atomic facts, importance >= 6, skip small talk and generic knowledge.
- For a 5-turn conversation segment (10 messages), a reasonable range is 0-5 raw facts depending on content density.
- Coding sessions: lower fact yield (mostly code, less personal info).
- Planning/preference sessions: higher fact yield (decisions, preferences, goals).
- Estimate a distribution: mean and range for each user profile.

### Step 3: Apply the importance filter

- The extractor prompt already targets importance >= 6.
- The runtime filter drops facts below importance 3.
- Since the LLM prompt targets >= 6, most facts that make it through the LLM already pass the threshold=3 filter.
- Estimate: ~95-100% pass-through for this filter (it catches only LLM failures/hallucinations that score below 3).

### Step 4: Apply the semantic dedup filter

- The dedup operates within a single batch (not cross-batch, not cross-session).
- With batch sizes of 1-5 facts, the probability of within-batch near-duplicates is low but nonzero.
- Estimate: ~5-10% dedup rate for batches with 3+ facts; ~0% for batches with 1-2 facts.

### Step 5: Account for compaction/reset bursts

- When context fills up (every ~50-100 turns), `before_compaction` fires and extracts from the FULL conversation.
- This can yield 5-20+ facts in a single burst (many of which may be duplicates of previously stored facts, but the dedup is within-batch only).
- Important: there is NO cross-batch dedup currently. Facts from compaction that duplicate facts from periodic extraction WILL be stored again. The only defense is the content fingerprint dedup at the server/subgraph level.
- Estimate compaction frequency per profile and burst size.

### Step 6: Calculate facts/hour, facts/day, facts/month

For each user profile, compute:

```
periodic_extractions_per_hour = turns_per_hour / AUTO_EXTRACT_EVERY_TURNS
raw_facts_per_extraction = estimated mean from Step 2
post_importance_facts = raw_facts * importance_pass_rate (Step 3)
post_dedup_facts = post_importance_facts * (1 - dedup_rate) (Step 4)

periodic_facts_per_hour = periodic_extractions_per_hour * post_dedup_facts

compaction_facts_per_session = estimated burst size (Step 5)
compaction_sessions_per_day = sessions_per_day (if context fills per session)

total_facts_per_day = (periodic_facts_per_hour * hours_per_day) + (compaction_facts_per_session * compaction_sessions_per_day)
total_facts_per_month = total_facts_per_day * 30
```

### Step 7: Calculate gas costs

```
gas_cost_per_month = total_facts_per_month * $0.00076
```

Compare against:
- Free tier: 100 facts/month
- Pro tier cost: $2-5/month

### Step 8: Sensitivity analysis

Vary the key parameters and show how costs change:
- AUTO_EXTRACT_EVERY_TURNS: 3 vs 5 vs 10 vs 15
- Average facts per extraction: 1 vs 2 vs 3
- Compaction burst size: 5 vs 10 vs 20

### Step 9: Recommendations

Based on the analysis, answer:
1. Is 100 facts/month a reasonable free tier for casual users? Will regular users hit it?
2. Does $2-5/month cover gas costs for power users?
3. Should AUTO_EXTRACT_EVERY_TURNS be increased to reduce gas costs?
4. Is the lack of cross-batch dedup a significant cost driver?
5. What is the break-even subscription price at different usage levels?

## 5. Data Sources (Files to Read)

| File | What to extract |
|------|----------------|
| `skill/plugin/index.ts` | `AUTO_EXTRACT_EVERY_TURNS` (line 117), `MIN_IMPORTANCE_THRESHOLD` (line 395), `agent_end` hook (line 1426), `before_compaction` hook (line 1457), `before_reset` hook (line 1488), `storeExtractedFacts()` function |
| `skill/plugin/extractor.ts` | LLM extraction prompt (line 36-56), `extractFacts()` function signature and logic |
| `skill/plugin/semantic-dedup.ts` | `deduplicateBatch()` logic, default threshold 0.9, within-batch-only scope |
| `docs/specs/subgraph/billing-and-onboarding.md` | Section 3: Gnosis Chain cost ($0.00076/fact), Section 5: tier structure (free/pro), Section 2: pricing ($2-5/mo) |
| `subgraph/tests/gas-report.md` | Per-fact gas measurements (medium fact: 379,650 gas, 8,967 bytes calldata). Note: these are Base L2 figures -- Gnosis costs differ |
| `subgraph/tests/scaling-report.md` | Scenario definitions (A/B/C), write cost projections. Note: uses Base L2 pricing, not Gnosis |
| `docs/specs/totalreclaw/retrieval-improvements-v3.md` | C3 spec (autoExtractEveryTurns throttle), D3 spec (semantic dedup). Current vs proposed state table at the top |
| `docs/specs/totalreclaw/skill-openclaw.md` | Skill behavior spec -- hook definitions, when they fire |

## 6. Expected Output Format

The implementing agent should produce a document with:

### Summary Table (Primary Output)

| Profile | Turns/day | Extractions/day | Raw facts/day | Post-filter facts/day | Facts/month | Gas cost/month | Free tier lasts | Pro tier margin |
|---------|:---------:|:---------------:|:-------------:|:--------------------:|:-----------:|:--------------:|:---------------:|:---------------:|
| Casual | ... | ... | ... | ... | ... | ... | ... | ... |
| Regular | ... | ... | ... | ... | ... | ... | ... | ... |
| Power | ... | ... | ... | ... | ... | ... | ... | ... |
| Extreme | ... | ... | ... | ... | ... | ... | ... | ... |

### Sensitivity Table

| AUTO_EXTRACT_EVERY_TURNS | Power user facts/month | Gas cost/month | Notes |
|:------------------------:|:---------------------:|:--------------:|-------|
| 3 | ... | ... | ... |
| 5 (current) | ... | ... | ... |
| 10 | ... | ... | ... |
| 15 | ... | ... | ... |

### Recommendations Section

Bullet-point answers to the questions in Step 9.

## 7. Open Questions

1. **What is the actual compaction frequency in OpenClaw?** The context window size and compaction trigger are not fully documented. If compaction fires rarely, the burst-fact contribution is negligible. If it fires every session, it could double the fact count.

2. **Is the $0.00076/fact figure for Gnosis still accurate?** The gas report (`subgraph/tests/gas-report.md`) measures gas units on Hardhat and extrapolates to Base L2 pricing. The Gnosis figure comes from the billing spec. The agent should verify the Gnosis calculation: `gas_used * gnosis_gas_price_gwei * 1e-9 * xDAI_price`. Gnosis gas price is typically ~1-2 gwei, xDAI = $1.00.

3. **Does content fingerprint dedup at the server/subgraph level catch cross-batch duplicates?** If so, the compaction burst problem is partially mitigated. Check how `generateContentFingerprint()` works in `skill/plugin/crypto.ts` and whether the server/subgraph rejects duplicate fingerprints.

4. **What is the LLM cost per extraction call?** Each extraction requires an LLM call (GPT-4o-mini or similar). At ~$0.15/1M input tokens and ~500 tokens per 5-turn extraction, this may dominate gas costs. The agent should note this but does not need to calculate it in detail -- the focus is gas costs.

5. **Are there plans to batch multiple facts per on-chain transaction?** The gas report notes that batching would amortize the 21,000 base gas. If batching is planned, per-fact gas cost would decrease. Check the scaling report recommendations section.

## 8. Non-Goals

- Do not implement any code changes.
- Do not modify the extraction frequency or any thresholds.
- Do not calculate LLM inference costs (note them as a separate concern).
- Do not calculate infrastructure costs (Graph Node hosting, PostgreSQL, etc.) -- those are covered in the scaling report.
- Do not calculate query (read) costs -- focus solely on write (store) costs.
