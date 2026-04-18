# Changelog

All notable changes to `@totalreclaw/totalreclaw` (the OpenClaw plugin) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] — 2026-04-17

Major release adopting **Memory Taxonomy v1** and **Retrieval v2 Tier 1** source-weighted reranking.

### Breaking changes

- **`@totalreclaw/core` bumped to 2.0.0.** The core WASM package now ships v1 schema validators (`validateMemoryClaimV1`, `parseMemoryTypeV1`, `parseMemorySource`), the Retrieval v2 Tier 1 source-weighted reranker (`rerankWithConfig`, `sourceWeight`, `legacyClaimFallbackWeight`), and strips v0-only types. Existing v0 canonical claims still decode via `parseClaimOrLegacy`.
- **`ExtractedFact.type` is now a union of v0 and v1 type tokens.** Consumers that relied on the 8-type closed enum (`fact | preference | decision | episodic | goal | context | summary | rule`) must also accept the v1 tokens (`claim | preference | directive | commitment | episode | summary`). The new `isValidMemoryTypeV1` runtime guard covers the v1 side; `normalizeToV1Type` maps v0 tokens to their v1 equivalents for the adapter layer.

### Added

- **Memory Taxonomy v1 types.** New exports from `extractor.ts`: `MemoryTypeV1`, `MemorySource`, `MemoryScope`, `MemoryVolatility`, `VALID_MEMORY_TYPES_V1`, `VALID_MEMORY_SOURCES`, `VALID_MEMORY_SCOPES`, `VALID_MEMORY_VOLATILITIES`, `isValidMemoryTypeV1`, `V0_TO_V1_TYPE`.
- **`extractFactsV1` pipeline (G pipeline).** Opt-in via `TOTALRECLAW_TAXONOMY_VERSION=v1`. Single merged-topic LLM call that returns `{topics, facts}` for better topic anchoring, followed by `applyProvenanceFilterLax` (tag-don't-drop, caps assistant-source at 7 rather than dropping), `comparativeRescoreV1` (forces re-rank when ≥5 facts to spread importance across 1-10), and `defaultVolatility` heuristic fallback.
- **`buildCanonicalClaimV1` canonical claim builder.** Produces a MemoryClaimV1 JSON payload matching `docs/specs/totalreclaw/memory-taxonomy-v1.md`. Validates through core's strict `validateMemoryClaimV1` then re-attaches plugin-only extras (`schema_version`, `volatility`) that core's v2.0.0 validator strips. Throws on missing/invalid `source`.
- **`buildCanonicalClaimRouted` router.** Picks v0 or v1 builder based on `TOTALRECLAW_TAXONOMY_VERSION`. Falls back to v0 when v1 is selected but `fact.source` is unset, so a misconfigured rollout doesn't drop data.
- **`isV1Blob` + `readV1Blob` decoders.** Detect and parse v1 payloads for the decrypt path. `readClaimFromBlob` now prefers v1 payloads when present, so mixed-version vaults round-trip cleanly.
- **Source-weighted reranker (Retrieval v2 Tier 1).** `rerank()` gains an `applySourceWeights: boolean` parameter (default `false`). When `true`, final RRF score is multiplied by the source weight (`user=1.0`, `user-inferred=0.9`, `derived/external=0.7`, `assistant=0.55`, legacy/missing=`0.85`). `getSourceWeight` is exported for direct access. Candidates now carry an optional `source` field.
- **New test file: `v1-taxonomy.test.ts`.** 100 TAP-style tests covering v1 type guards, v0↔v1 mapping, canonical claim build+round-trip, encryption-simulated round-trip, `readV1Blob`, `parseMergedResponseV1` (valid/malformed/empty/code-fenced/think-tag-stripped/summary-user-rejected), `applyProvenanceFilterLax`, `defaultVolatility` heuristic, `getSourceWeight` table, and reranker source-weight ordering.

### Changed

- **`TYPE_TO_CATEGORY` mapping extended.** `mapTypeToCategory` now accepts both v0 and v1 type tokens. v1 `directive` maps to the v0 category key `rule`; v1 `commitment` maps to the v0 category key `goal`, so on-chain consumers that index by category key keep working across a mixed-taxonomy vault.
- **`readClaimFromBlob` handles v1 payloads first.** When a decrypted blob carries `schema_version` starting with `1.`, the reader pulls fields from the v1 shape (`text`, `type`, `importance`, `source`, `scope`, `volatility`, `reasoning`) and surfaces them in the `metadata` object. v0 canonical (`{t,c,i,...}`) and legacy (`{text, metadata}`) paths are unchanged.

### Migration notes

- **Backward compatibility.** Plugin v3.0.0 reads v0 vaults transparently — `parseClaimOrLegacy` (in core) + `readClaimFromBlob` fall back through v1 → v0 → legacy `{text, metadata}` → raw text.
- **Opt-in v1 extraction.** The default extraction pipeline is still v0. Flip `TOTALRECLAW_TAXONOMY_VERSION=v1` to enable `extractFactsV1` + `buildCanonicalClaimRouted` → v1 path. This lets operators roll out v1 per-session before the global flip.
- **Protobuf outer wrapper.** This release still writes `version = 3` in the outer protobuf wrapper; the inner blob is v1 JSON when `TOTALRECLAW_TAXONOMY_VERSION=v1`. A follow-up release will bump the outer `version` to 4 once the subgraph indexer confirms it surfaces the change without schema breakage. (The subgraph is agnostic to inner-blob format — see `totalreclaw-internal/docs/plans/2026-04-18-protobuf-v4-design.md`.)
- **Tool-level pin/retype/set_scope.** The OpenClaw plugin does not register MCP-style tools directly (the MCP server does). These are handled by the MCP server agent; the plugin's `totalreclaw_pin` / `totalreclaw_unpin` tools remain unchanged for now. The retype + set-scope tools will ship when auto-resolution integrates v1 fields.
- **Contradiction-sync + digest compaction.** These components continue to read v0 short-key claims via `readClaimFromBlob`. They are forward-compatible with v1 (the reader surfaces the same `{text, importance, category}` shape regardless of source format), but their WRITE paths still emit v0 canonical claims. Updating the write paths to v1 is tracked as a follow-up.

### Known gaps (deferred to follow-up)

- Auto-resolution write path still emits v0 canonical claims. Mixed-taxonomy vaults work for read but will regenerate v0 claims on supersede — not harmful, just not fully v1.
- `totalreclaw_remember` tool handler does not yet accept v1 `source`/`scope`/`volatility` parameters. Currently it passes `type` through to the v0 extractor path.
- Outer protobuf version field stays at 3 pending a follow-up release once v4 is indexer-verified.
