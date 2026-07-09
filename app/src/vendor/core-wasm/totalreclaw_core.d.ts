/* tslint:disable */
/* eslint-disable */

/**
 * Contradiction candidate cap constant.
 */
export function CONTRADICTION_CANDIDATE_CAP(): number;

/**
 * Decision log max lines constant.
 */
export function DECISION_LOG_MAX_LINES(): number;

/**
 * Tie-zone score tolerance constant.
 */
export function TIE_ZONE_SCORE_TOLERANCE(): number;

/**
 * Random Hyperplane LSH hasher (WASM wrapper).
 *
 * Construct with `new WasmLshHasher(seedHex, dims)`.
 * Call `hash(embeddingFloat64Array)` to get bucket IDs.
 */
export class WasmLshHasher {
    free(): void;
    [Symbol.dispose](): void;
    /**
     * Hash an embedding vector to blind-hashed bucket IDs.
     *
     * `embedding`: Float64Array of length `dims`.
     * Returns a JSON array of hex strings (one per table).
     */
    hash(embedding: Float64Array): any;
    /**
     * Create a new LSH hasher with default parameters (20 tables, 32 bits).
     *
     * `seed_hex`: hex-encoded seed (>= 32 chars = 16 bytes).
     * `dims`: embedding dimensionality (e.g. 640).
     */
    constructor(seed_hex: string, dims: number);
    /**
     * Create a new LSH hasher with custom parameters.
     *
     * `seed_hex`: hex-encoded seed.
     * `dims`: embedding dimensionality.
     * `n_tables`: number of hash tables.
     * `n_bits`: bits per table.
     */
    static withParams(seed_hex: string, dims: number, n_tables: number, n_bits: number): WasmLshHasher;
    /**
     * Bits per table.
     */
    readonly bits: number;
    /**
     * Embedding dimensionality.
     */
    readonly dimensions: number;
    /**
     * Number of hash tables.
     */
    readonly tables: number;
}

/**
 * Append one decision entry to existing JSONL content. Non-fallible.
 */
export function appendDecisionEntry(existing_content: string, entry_json: string): string;

/**
 * Append one feedback entry to existing JSONL content.
 */
export function appendFeedbackToJsonl(existing: string, entry_json: string): string;

/**
 * Apply a single counterexample to the weights; returns updated ResolutionWeights JSON.
 */
export function applyFeedback(weights_json: string, counterexample_json: string): string;

/**
 * Assemble a full Digest from a parsed LLM response and source claims.
 */
export function assembleDigestFromLlm(parsed_json: string, claims_json: string, now_unix_seconds: bigint): string;

/**
 * Build ABI-encoded calldata for a batch of prepared facts.
 *
 * `prepared_array_json`: JSON array of `PreparedFact` objects.
 * Returns ABI-encoded calldata (Uint8Array).
 */
export function buildBatchCalldataFromPrepared(prepared_array_json: string): Uint8Array;

/**
 * Build the debrief prompt with already-stored facts filled in.
 *
 * `stored_facts_json`: JSON array of strings (fact texts already stored).
 */
export function buildDebriefPrompt(stored_facts_json: string): string;

/**
 * Build decision log entries from resolution actions.
 *
 * Returns a JSON array of `DecisionLogEntry`.
 */
export function buildDecisionLogEntries(actions_json: string, new_claim_json: string, existing_claims_json: string, mode: string, now_unix: bigint): string;

/**
 * Build the LLM prompt for digest compilation.
 * `claims_json`: JSON array of Claim (must be non-empty).
 */
export function buildDigestPrompt(claims_json: string): string;

/**
 * Build a FeedbackEntry JSON from a decision-log entry JSON + pin action.
 * Returns the JSON string, or the literal string "null" on failure.
 */
export function buildFeedbackFromDecision(decision_json: string, action: string, now_unix: bigint): string;

/**
 * Build the profiling prompt for a batch of conversation summaries.
 *
 * `summaries_json`: JSON array of ChunkSummary objects.
 * Returns the prompt string.
 */
export function buildProfileBatchPrompt(summaries_json: string): string;

/**
 * Build the merge prompt that combines partial profiles.
 *
 * `partials_json`: JSON array of PartialProfile objects.
 * Returns the prompt string.
 */
export function buildProfileMergePrompt(partials_json: string): string;

/**
 * Build ABI-encoded calldata for a single prepared fact.
 *
 * `prepared_json`: JSON string of a `PreparedFact`.
 * Returns ABI-encoded calldata (Uint8Array).
 */
export function buildSingleCalldataFromPrepared(prepared_json: string): Uint8Array;

/**
 * Build a template digest from an array of active claims.
 * `claims_json`: JSON array of Claim. Returns JSON-serialized Digest.
 */
export function buildTemplateDigest(claims_json: string, now_unix_seconds: bigint): string;

/**
 * Build the triage prompt for classifying chunks.
 *
 * `profile_json`: JSON string of a UserProfile.
 * `summaries_json`: JSON array of ChunkSummary objects.
 * Returns the prompt string.
 */
export function buildTriagePrompt(profile_json: string, summaries_json: string): string;

/**
 * Canonicalize a Claim JSON: strict-parse as Claim, re-serialize to canonical bytes.
 * Rejects legacy or malformed input. Use before encryption so TS/Python/Rust all
 * produce byte-identical blobs for the same logical claim.
 */
export function canonicalizeClaim(claim_json: string): string;

/**
 * Convert conversation chunks to summaries.
 *
 * `chunks_json`: JSON array of ConversationChunk objects.
 * Returns a JsValue (JSON array of ChunkSummary objects).
 */
export function chunksToSummaries(chunks_json: string): any;

/**
 * Classify natural-language pin/unpin intent from a user utterance.
 *
 * Returns JSON of [`PinIntent`] when a trigger phrase matches, or `null` when
 * the utterance contains no recognised pin gesture. Lowercase normalization
 * is applied internally — callers pass the raw user text.
 */
export function classifyPinIntent(text: string): string;

/**
 * WASM binding for `cluster_facts`.
 *
 * `candidates_json`: JSON array of `ConsolidationCandidate` objects.
 * `threshold`: Cosine similarity threshold for clustering.
 *
 * Returns JSON array of `{ representative: string, duplicates: string[] }`.
 */
export function clusterFacts(candidates_json: string, threshold: number): any;

/**
 * Compute SHA-256(authKey) as a hex string.
 *
 * `auth_key_hex`: 64-char hex string (32 bytes).
 */
export function computeAuthKeyHash(auth_key_hex: string): string;

/**
 * Compute the content fingerprint for dedup checks.
 *
 * `dedup_key_hex`: 64-char hex string (32 bytes).
 * Returns 64-char hex fingerprint.
 */
export function computeContentFingerprint(text: string, dedup_key_hex: string): string;

/**
 * Compute a claim's score components for contradiction resolution.
 */
export function computeScoreComponents(claim_json: string, now_unix_seconds: bigint, weights_json: string): string;

/**
 * Cosine similarity between two f32 vectors.
 */
export function cosineSimilarity(a: Float32Array, b: Float32Array): number;

/**
 * Decrypt a base64-encoded XChaCha20-Poly1305 blob.
 *
 * `encryption_key_hex`: 64-char hex string (32 bytes).
 * Returns the plaintext UTF-8 string.
 */
export function decrypt(encrypted_base64: string, encryption_key_hex: string): string;

/**
 * Decrypt and rerank search candidates.
 *
 * Takes raw SubgraphFacts (as JSON), decrypts their content + embeddings,
 * and returns top-K ranked results using BM25 + Cosine + RRF fusion.
 *
 * `facts_json`: JSON array of SubgraphFact objects.
 * `query`: The search query text.
 * `query_embedding`: Float32Array of the query embedding.
 * `encryption_key_hex`: 64-char hex string (32 bytes).
 * `top_k`: Number of top results to return.
 *
 * Returns a JsValue (JSON array of RankedResult objects).
 */
export function decryptAndRerank(facts_json: string, query: string, query_embedding: Float32Array, encryption_key_hex: string, top_k: number): any;

/**
 * Return the locked-default [`PinConfig`] as JSON. Clients that don't want
 * to retune can pass this verbatim to [`wasm_pin_boost`].
 */
export function defaultPinConfig(): string;

/**
 * Default P2-3 resolution weights as JSON.
 */
export function defaultResolutionWeights(): string;

/**
 * Build a fresh default WeightsFile JSON with the given timestamp.
 */
export function defaultWeightsFile(now_unix_seconds: bigint): string;

/**
 * Derive an Ethereum EOA wallet from a BIP-39 mnemonic via BIP-44.
 *
 * Path: m/44'/60'/0'/0/0 (standard Ethereum derivation path).
 * Returns a JS object: `{ private_key: "hex...", address: "0x..." }`.
 */
export function deriveEoa(mnemonic: string): any;

/**
 * Derive just the Ethereum EOA address from a BIP-39 mnemonic.
 *
 * Returns: `"0x..."` (lowercase hex).
 */
export function deriveEoaAddress(mnemonic: string): string;

/**
 * Derive encryption keys from a BIP-39 mnemonic (strict checksum validation).
 *
 * Returns a JSON object with hex-encoded keys:
 * `{ auth_key, encryption_key, dedup_key, salt }`
 */
export function deriveKeysFromMnemonic(mnemonic: string): any;

/**
 * Derive encryption keys from a BIP-39 mnemonic (lenient -- skips checksum).
 *
 * Same return format as `deriveKeysFromMnemonic`.
 */
export function deriveKeysFromMnemonicLenient(mnemonic: string): any;

/**
 * Derive the 32-byte LSH seed from a BIP-39 mnemonic and salt.
 *
 * `salt_hex`: 64-char hex string (32 bytes).
 * Returns hex-encoded 32-byte seed.
 */
export function deriveLshSeed(mnemonic: string, salt_hex: string): string;

/**
 * Detect contradictions between a new claim and existing claims (JSON array of {claim, id, embedding}).
 */
export function detectContradictions(new_claim_json: string, new_claim_id: string, new_embedding_json: string, existing_json: string, lower_threshold: number, upper_threshold: number): string;

/**
 * Deterministic entity ID from a name (first 8 bytes of SHA256 as hex).
 */
export function deterministicEntityId(name: string): string;

/**
 * Encode multiple fact submissions as SimpleAccount.executeBatch() calldata.
 *
 * `payloads_json`: JSON array of hex-encoded payload strings (e.g. `["deadbeef", "cafebabe"]`).
 * Returns ABI-encoded calldata (Uint8Array).
 */
export function encodeBatchCall(payloads_json: string): Uint8Array;

/**
 * Like `encodeBatchCall` but targets an explicit DataEdge address (#366).
 */
export function encodeBatchCallTo(payloads_json: string, data_edge_address: string): Uint8Array;

/**
 * Encode a fact payload as minimal protobuf wire format.
 *
 * `json`: JSON string with shape:
 * ```json
 * {
 *   "id": "...", "timestamp": "...", "owner": "...",
 *   "encrypted_blob_hex": "...", "blind_indices": ["..."],
 *   "decay_score": 0.8, "source": "...", "content_fp": "...",
 *   "agent_id": "...", "encrypted_embedding": "..." (optional)
 * }
 * ```
 *
 * Returns the protobuf bytes as a Uint8Array.
 */
export function encodeFactProtobuf(json: string): Uint8Array;

/**
 * Encode a single fact submission as SimpleAccount.execute() calldata.
 *
 * `protobuf_payload`: raw protobuf bytes (Uint8Array).
 * Returns ABI-encoded calldata (Uint8Array).
 */
export function encodeSingleCall(protobuf_payload: Uint8Array): Uint8Array;

/**
 * Like `encodeSingleCall` but targets an explicit DataEdge address.
 *
 * Chain/environment-aware clients pass the authoritative address from the
 * relay's `/v1/billing/status` `data_edge_address` (#366) — the isolated
 * staging Gnosis DataEdge differs from prod's. Throws on a bad address.
 */
export function encodeSingleCallTo(protobuf_payload: Uint8Array, data_edge_address: string): Uint8Array;

/**
 * Encode a tombstone protobuf for soft-deleting a fact.
 *
 * `version` is optional; missing/0 defaults to `DEFAULT_PROTOBUF_VERSION` (3).
 * Pass `4` to emit a v1-taxonomy tombstone (outer protobuf version = 4).
 *
 * Returns the protobuf bytes as a Uint8Array.
 */
export function encodeTombstoneProtobuf(fact_id: string, owner: string, version?: number | null): Uint8Array;

/**
 * Encrypt a UTF-8 plaintext with XChaCha20-Poly1305.
 *
 * `encryption_key_hex`: 64-char hex string (32 bytes).
 * Returns base64-encoded ciphertext (wire format: nonce || tag || ciphertext).
 */
export function encrypt(plaintext: string, encryption_key_hex: string): string;

/**
 * Enrich an extraction prompt with user profile context.
 *
 * `profile_json`: JSON string of a UserProfile.
 * `base_prompt`: The base extraction prompt to enrich.
 * Returns the enriched prompt string.
 */
export function enrichExtractionPrompt(profile_json: string, base_prompt: string): string;

/**
 * Convert a feedback entry into a counterexample for weight tuning. Returns
 * JSON Counterexample or the literal string "null" if the entry has no signal.
 */
export function feedbackToCounterexample(entry_json: string): string;

/**
 * Filter resolution actions by mode ("active" passes through, "shadow"/"off" returns empty).
 *
 * Returns a JSON array of `ResolutionAction`.
 */
export function filterShadowMode(actions_json: string, mode: string): string;

/**
 * WASM binding for `find_best_near_duplicate`.
 *
 * `new_embedding_json`: JSON array of floats (embedding vector).
 * `existing_json`: JSON array of `{ id: string, embedding: number[] }` objects.
 * `threshold`: Cosine similarity threshold.
 *
 * Returns JSON `{ fact_id: string, similarity: number }` or null.
 */
export function findBestNearDuplicate(new_embedding_json: string, existing_json: string, threshold: number): any;

/**
 * Find a decision-log entry matching a fact as winner or loser.
 * Returns the JSON-serialized DecisionLogEntry, or the literal string "null".
 */
export function findDecisionForPin(fact_id: string, role: string, log_content: string): string;

/**
 * Find the loser claim JSON from the decision log for a given fact ID.
 * Returns the loser_claim_json string, or the literal string "null" if not found.
 */
export function findLoserClaimInDecisionLog(fact_id: string, log_content: string): string;

/**
 * WASM binding for `find_near_duplicate` (deprecated — use `findBestNearDuplicate`).
 *
 * **Deprecated since core 1.5.0; scheduled for removal in core 3.0.** Returns
 * the *first* match above `threshold`, not the highest-similarity one. Migrate
 * npm consumers to `findBestNearDuplicate`.
 *
 * `new_embedding`: Float32Array of the new fact's embedding.
 * `existing_json`: JSON array of `{ id: string, embedding: number[] }` objects.
 * `threshold`: Cosine similarity threshold.
 *
 * Returns `null` if no duplicate found, or a string (the duplicate fact ID).
 */
export function findNearDuplicate(new_embedding: Float32Array, existing_json: string, threshold: number): any;

/**
 * Unix seconds → `"YYYY-MM-DD"` (UTC). Returns `""` for `0` or negative.
 *
 * Maps directly to [`crate::recall_context::format_memory_date`].
 */
export function formatMemoryDate(created_at_unix: bigint): string;

/**
 * Build the full recall-context block: header + one line per memory item.
 *
 * `items_json`: JSON array of `{ category, text, created_at }`. Any field
 * may be absent (defaults to empty string / 0). Bad or empty JSON → header
 * only (no panic).
 *
 * Output line format:
 * - With date:    `"- [category] (YYYY-MM-DD) text"`
 * - Without date: `"- [category] text"`
 *
 * `now_unix`: current time as Unix seconds (used in the header date).
 */
export function formatRecallContext(items_json: string, now_unix: bigint): string;

/**
 * Generate blind indices (SHA-256 token hashes) for a text string.
 *
 * Returns a JSON array of hex strings.
 */
export function generateBlindIndices(text: string): any;

/**
 * Compute HMAC-SHA256 content fingerprint.
 *
 * `dedup_key_hex`: 64-char hex string (32 bytes).
 * Returns 64-char hex fingerprint.
 */
export function generateContentFingerprint(plaintext: string, dedup_key_hex: string): string;

/**
 * Generate trapdoors for multiple query reformulations (expansion pipeline).
 *
 * `queries_json`: JSON array of query strings (original + reformulations).
 * `embeddings_json`: JSON array of Float32Array-compatible arrays (one per query).
 * `lsh_hasher`: A `WasmLshHasher` instance.
 *
 * Returns a JsValue (JSON array of trapdoor-string arrays, one per query).
 */
export function generateExpansionTrapdoors(queries_json: string, embeddings_json: string, lsh_hasher: WasmLshHasher): any;

/**
 * Generate all search trapdoors for a query (word hashes + LSH bucket hashes).
 *
 * `query`: The search query text.
 * `query_embedding`: Float32Array of the query embedding.
 * `lsh_hasher`: A `WasmLshHasher` instance.
 *
 * Returns a JsValue (JSON array of hex-encoded trapdoor strings).
 */
export function generateSearchTrapdoors(query: string, query_embedding: Float32Array, lsh_hasher: WasmLshHasher): any;

/**
 * Get the GraphQL query string for broadened (fallback) search.
 */
export function getBroadenedSearchQuery(): string;

/**
 * Get the canonical v1 compaction system prompt.
 *
 * Used on end-of-context surfaces where the importance floor is 5 rather
 * than the default 6.
 */
export function getCompactionSystemPrompt(): string;

/**
 * WASM binding: get the consolidation cosine threshold constant.
 */
export function getConsolidationCosineThreshold(): number;

/**
 * Get the GraphQL query string for fact count.
 */
export function getCountQuery(): string;

/**
 * Get the DataEdge contract address constant.
 */
export function getDataEdgeAddress(): string;

/**
 * Source tag for debrief items.
 */
export function getDebriefSource(): string;

/**
 * Get the canonical debrief system prompt template.
 *
 * Contains `{already_stored_facts}` placeholder.
 */
export function getDebriefSystemPrompt(): string;

/**
 * Get the EntryPoint v0.7 address constant.
 */
export function getEntryPointAddress(): string;

/**
 * Get the GraphQL query string for paginated export.
 */
export function getExportQuery(): string;

/**
 * Get the canonical v1 merged-topic extraction system prompt.
 *
 * Single source of truth across all TotalReclaw clients — TS/WASM
 * callers get the same bytes the Python `totalreclaw_core` module
 * returns from `get_extraction_system_prompt()`. Includes the Rule 6
 * meta-request filter (see the docstring on `prompts.rs`).
 */
export function getExtractionSystemPrompt(): string;

/**
 * Get the maximum batch size constant.
 */
export function getMaxBatchSize(): number;

/**
 * Maximum debrief items (5).
 */
export function getMaxDebriefItems(): number;

/**
 * Minimum messages for debrief (8 = 4 turns).
 */
export function getMinDebriefMessages(): number;

/**
 * Get the page size constant.
 */
export function getPageSize(): number;

/**
 * Get the GraphQL query string for blind index search.
 */
export function getSearchQuery(): string;

/**
 * Get the SimpleAccountFactory address constant.
 */
export function getSimpleAccountFactory(): string;

/**
 * WASM binding: get the store-time dedup cosine threshold constant.
 */
export function getStoreDedupCosineThreshold(): number;

/**
 * WASM binding: get the store-time dedup max candidates constant.
 */
export function getStoreDedupMaxCandidates(): number;

/**
 * Get the trapdoor batch size constant.
 */
export function getTrapdoorBatchSize(): number;

/**
 * Get the v1 type → short-form category mapping.
 *
 * Returns a plain JS object `{ claim: "claim", preference: "pref",
 * directive: "rule", commitment: "goal", episode: "epi",
 * summary: "sum" }`.
 *
 * Uses `js_sys::Object.set` directly so the result is a plain JS
 * object (not a `Map`) regardless of serde-wasm-bindgen defaults,
 * matching how TypeScript clients consume the mapping via bracket
 * access (`map[type]`).
 */
export function getTypeToCategory(): any;

/**
 * Get the canonical list of v1 memory types.
 *
 * Returns a JS array of six strings: `["claim", "preference",
 * "directive", "commitment", "episode", "summary"]`.
 */
export function getValidMemoryTypes(): any;

/**
 * Compute the ERC-4337 v0.7 UserOp hash for signing.
 *
 * `userop_json`: JSON string of a UserOperationV7 struct.
 * `entrypoint`: EntryPoint address (0x-prefixed).
 * `chain_id`: Chain ID (e.g. 84532 for Base Sepolia).
 * Returns 32-byte hash as hex string.
 */
export function hashUserOp(userop_json: string, entrypoint: string, chain_id: bigint): string;

/**
 * Convert a subgraph hex blob to base64 for decryption.
 *
 * `hex_blob`: Hex string (optionally `0x`-prefixed) from the subgraph.
 * Returns base64-encoded bytes, or null if the hex is invalid.
 */
export function hexBlobToBase64(hex_blob: string): string | undefined;

/**
 * Check whether a JSON-serialized claim has pinned status.
 */
export function isPinnedClaim(claim_json: string): boolean;

/**
 * Check whether a JSON-encoded claim is pinned, recognizing both the v0
 * short-key sentinel (`st == "p"`) and the v1.1 field (`pin_status ==
 * "pinned"`). Returns `false` on any parse failure.
 *
 * Wrapper around [`crate::claims::is_pinned_json`] for TS clients.
 */
export function isPinnedClaimJson(claim_json: string): boolean;

/**
 * Runtime guard: is `value` a valid v1 memory type?
 */
export function isValidMemoryType(value: string): boolean;

/**
 * Return the v1 legacy-claim fallback weight (applied to candidates that
 * have no `source` field).
 */
export function legacyClaimFallbackWeight(): number;

/**
 * Map a v1 type to its short-form category key.
 *
 * Returns `null` if `value` is not one of the six v1 types.
 */
export function mapTypeToCategory(value: string): any;

/**
 * Merge multiple SubgraphFact sets from parallel query reformulations via RRF.
 *
 * `fact_sets_json`: JSON array of SubgraphFact arrays (one array per reformulation).
 * `rrf_k`: RRF k-parameter (use 60.0 for default behaviour).
 *
 * Returns a JsValue (merged, deduplicated SubgraphFact array sorted by RRF score).
 */
export function mergeExpansionResults(fact_sets_json: string, rrf_k: number): any;

/**
 * Normalize an entity name (NFC, lowercase, trim, collapse whitespace).
 */
export function normalizeEntityName(name: string): string;

/**
 * Normalize text (NFC, lowercase, collapse whitespace, trim).
 */
export function normalizeText(text: string): string;

/**
 * Parse a broadened search GraphQL response into SubgraphFact list.
 *
 * `response_json`: Raw JSON string from the GraphQL response.
 * Returns a JsValue (JSON array of SubgraphFact objects).
 */
export function parseBroadenedResponse(response_json: string): any;

/**
 * Parse a decrypted blob as a Claim, falling back to legacy formats.
 * Returns JSON-serialized Claim.
 */
export function parseClaimOrLegacy(decrypted: string): string;

/**
 * Parse a debrief LLM response into validated items.
 *
 * Returns a JSON array of `{ text, type, importance }` objects.
 */
export function parseDebriefResponse(response: string): any;

/**
 * Parse an LLM digest response.
 * Returns JSON-serialized ParsedDigestResponse.
 */
export function parseDigestResponse(raw: string): string;

/**
 * Parse a Gemini export (JSON or saved-info text) into a `ParseResult`.
 */
export function parseGemini(input: string): any;

/**
 * Case-insensitive parse of a memory source string. Unknown input returns "user-inferred".
 */
export function parseMemorySource(s: string): string;

/**
 * Case-insensitive parse of a memory type string. Unknown input returns "claim".
 */
export function parseMemoryTypeV1(s: string): string;

/**
 * Case-insensitive parse of a v1.1 pin_status string. Unknown input returns "unpinned".
 */
export function parsePinStatus(s: string): string;

/**
 * Parse a batch profiling LLM response into a PartialProfile.
 *
 * `llm_output`: Raw LLM response string.
 * Returns a JsValue (PartialProfile object).
 */
export function parseProfileBatchResponse(llm_output: string): any;

/**
 * Parse the merge LLM response into a UserProfile.
 *
 * `llm_output`: Raw LLM response string.
 * Returns a JsValue (UserProfile object).
 */
export function parseProfileResponse(llm_output: string): any;

/**
 * Parse a blind index search GraphQL response into SubgraphFact list.
 *
 * `response_json`: Raw JSON string from the GraphQL response.
 * Returns a JsValue (JSON array of SubgraphFact objects).
 */
export function parseSearchResponse(response_json: string): any;

/**
 * Parse the triage LLM response into chunk decisions.
 *
 * `llm_output`: Raw LLM response string.
 * Returns a JsValue (JSON array of ChunkDecision objects).
 */
export function parseTriageResponse(llm_output: string): any;

/**
 * Parse a WeightsFile from JSON; rejects unknown versions and malformed input.
 */
export function parseWeightsFile(content: string): string;

/**
 * Compute the [`PinTier`]'s multiplicative boost at a given timestamp.
 *
 * `tier_json`: internally-tagged JSON, e.g. `{"tier":"soft","pinned_at":1716000000}`,
 * `{"tier":"hard"}`, `{"tier":"none"}`.
 * `now_unix`: seconds since epoch.
 * `config_json`: JSON of [`PinConfig`], e.g. `{"soft_half_life_days":90,"soft_max_boost":1.5,"hard_boost":1.5}`.
 *
 * Returns the multiplicative boost factor (1.0 for `none`).
 */
export function pinBoost(tier_json: string, now_unix: bigint, config_json: string): number;

/**
 * Prepare a fact for on-chain storage.
 *
 * Pure computation: encrypt, generate indices, encode protobuf.
 * Does NOT submit -- the host handles I/O.
 *
 * `encryption_key_hex`: 64-char hex string (32 bytes).
 * `dedup_key_hex`: 64-char hex string (32 bytes).
 * `lsh_hasher`: A `WasmLshHasher` instance.
 * `embedding`: Float32Array of the pre-computed embedding vector.
 * `importance`: Importance score on 1-10 scale (normalized to 0.0-1.0).
 *
 * Returns a JSON string with `PreparedFact` fields.
 */
export function prepareFact(text: string, encryption_key_hex: string, dedup_key_hex: string, lsh_hasher: WasmLshHasher, embedding: Float32Array, importance: number, source: string, owner: string, agent_id: string): any;

/**
 * Prepare a fact with a pre-normalized decay score (already 0.0-1.0).
 *
 * Same as `prepareFact()` but takes a raw decay score.
 */
export function prepareFactWithDecayScore(text: string, encryption_key_hex: string, dedup_key_hex: string, lsh_hasher: WasmLshHasher, embedding: Float32Array, decay_score: number, source: string, owner: string, agent_id: string): any;

/**
 * Prepare a tombstone (soft-delete) protobuf.
 *
 * Returns the protobuf bytes as a Uint8Array.
 */
export function prepareTombstone(fact_id: string, owner: string): Uint8Array;

/**
 * Parse JSONL content. Returns JSON: `{"entries": [...], "warnings": [...]}`.
 */
export function readFeedbackJsonl(content: string): string;

/**
 * Build the recall-context header string (current-date + temporal-reasoning nudge).
 *
 * `now_unix`: current time as Unix seconds.
 * Returns the header with a trailing newline, e.g.:
 * `"## Relevant memories from TotalReclaw\nThe current date is 2024-01-15. ..."`
 */
export function recallContextHeader(now_unix: bigint): string;

/**
 * Rerank candidates using BM25 + Cosine + RRF fusion.
 *
 * `candidates_json`: JSON array of `{ id, text, embedding, timestamp, source? }` objects.
 * Returns a JsValue (array of `RankedResult` objects).
 */
export function rerank(query: string, query_embedding: Float32Array, candidates_json: string, top_k: number): any;

/**
 * Rerank candidates with a config flag (Retrieval v2 Tier 1).
 *
 * When `apply_source_weights` is `true`, each candidate's final score is
 * multiplied by the provenance weight from its `source` field (legacy
 * candidates without `source` use the v0 fallback weight).
 *
 * `candidates_json`: JSON array of `{ id, text, embedding, timestamp, source? }` objects.
 * Returns a JsValue (array of `RankedResult` objects including `source_weight`).
 */
export function rerankWithConfig(query: string, query_embedding: Float32Array, candidates_json: string, top_k: number, apply_source_weights: boolean): any;

/**
 * Run the resolution formula on two contradicting claims; returns ResolutionOutcome JSON.
 */
export function resolvePair(claim_a_json: string, claim_a_id: string, claim_b_json: string, claim_b_id: string, now_unix_seconds: bigint, weights_json: string): string;

/**
 * Orchestrate contradiction detection + resolution for a new claim against candidates.
 *
 * Returns a JSON array of `ResolutionAction`.
 */
export function resolveWithCandidates(new_claim_json: string, new_claim_id: string, new_embedding_json: string, candidates_json: string, weights_json: string, threshold_lower: number, threshold_upper: number, now_unix: bigint, tie_tolerance: number): string;

/**
 * Apply pin-status and tie-zone checks to a resolution outcome.
 * Returns a JSON-serialized `ResolutionAction`.
 */
export function respectPinInResolution(existing_claim_json: string, new_claim_id: string, existing_claim_id: string, resolution_winner: string, score_gap: number, similarity: number, tie_tolerance: number): string;

/**
 * Keep only the most recent `max_lines` non-empty feedback log lines. Non-falliable.
 */
export function rotateFeedbackLog(content: string, max_lines: bigint): string;

/**
 * Centroid-walk session segmentation over time-ordered turns.
 *
 * Mirrors `session_segmentation.py:segment_sessions` byte-for-byte.
 *
 * # Inputs (JSON strings, per this module's convention)
 * - `timestamps_json`: JSON array of Unix seconds or `null`, e.g.
 *   `"[0.0, null, 5000.0]"`. `null` = 0-gap to the previous turn.
 * - `embeddings_json`: JSON array of L2-normalised vectors, e.g.
 *   `"[[1.0,0.0],[0.9,0.1]]"`.
 * - `gap_seconds`: min time gap (strict `>`) forcing a new session (e.g. 1800).
 * - `sim_threshold`: cosine threshold (strict `<` splits; e.g. 0.55).
 *
 * # Returns
 * A `JsValue` — array of sessions, each an array of turn indices
 * (`number[][]`), contiguous and ascending. Bad JSON → `JsError`.
 */
export function segmentSessions(timestamps_json: string, embeddings_json: string, gap_seconds: number, sim_threshold: number): any;

/**
 * Serialize a WeightsFile JSON to pretty-printed JSON (2-space indent).
 */
export function serializeWeightsFile(file_json: string): string;

/**
 * WASM binding: determine if a new fact should supersede an existing one.
 */
export function shouldSupersede(new_importance: number, existing_importance: number): boolean;

/**
 * Sign a UserOp hash with an ECDSA private key (EIP-191 prefixed).
 *
 * `hash_hex`: 64-char hex string (32-byte UserOp hash).
 * `private_key_hex`: 64-char hex string (32-byte private key).
 * Returns 65-byte signature as hex string (r + s + v).
 */
export function signUserOp(hash_hex: string, private_key_hex: string): string;

/**
 * Return the source weight multiplier for a given source string.
 *
 * Accepted values: "user" | "user-inferred" | "assistant" | "external" | "derived".
 *
 * Unknown input is routed through `MemorySource::from_str_lossy` which
 * falls back to `user-inferred` (v2-lenient weight 0.95). Callers who need
 * the "no source field at all" fallback (weight 0.85) should call
 * `legacyClaimFallbackWeight()` instead.
 */
export function sourceWeight(source: string): number;

/**
 * Validate a Memory Taxonomy v1 claim (JSON in, JSON out — canonicalised).
 *
 * Returns the canonical JSON encoding on success. Throws on any schema
 * violation (wrong type token, missing required field, wrong schema_version).
 *
 * See `docs/specs/totalreclaw/memory-taxonomy-v1.md`.
 */
export function validateMemoryClaimV1(claim_json: string): string;

/**
 * Default polling interval (ms) — exposed so host adapters share the same
 * default without re-declaring the constant.
 */
export function wasmConfirmIndexedDefaultPollMs(): number;

/**
 * Default total timeout (ms) — exposed so host adapters share the same default.
 */
export function wasmConfirmIndexedDefaultTimeoutMs(): number;

/**
 * Parse a subgraph response JSON and return whether the fact is indexed +
 * active. Returns `true` when the read-after-write loop can stop.
 */
export function wasmConfirmIndexedParse(response_json: string): boolean;

/**
 * GraphQL query string used to confirm a fact id has been indexed.
 * Pair with `wasmConfirmIndexedParse` in a host-side polling loop.
 */
export function wasmConfirmIndexedQuery(): string;

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
    readonly memory: WebAssembly.Memory;
    readonly getValidMemoryTypes: () => [number, number, number];
    readonly getTypeToCategory: () => [number, number, number];
    readonly mapTypeToCategory: (a: number, b: number) => any;
    readonly isValidMemoryType: (a: number, b: number) => number;
    readonly findNearDuplicate: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly findBestNearDuplicate: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly clusterFacts: (a: number, b: number, c: number) => [number, number, number];
    readonly getStoreDedupCosineThreshold: () => number;
    readonly getStoreDedupMaxCandidates: () => number;
    readonly getConsolidationCosineThreshold: () => number;
    readonly shouldSupersede: (a: number, b: number) => number;
    readonly deriveKeysFromMnemonic: (a: number, b: number) => [number, number, number];
    readonly deriveKeysFromMnemonicLenient: (a: number, b: number) => [number, number, number];
    readonly deriveLshSeed: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly computeAuthKeyHash: (a: number, b: number) => [number, number, number, number];
    readonly encrypt: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly decrypt: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly generateBlindIndices: (a: number, b: number) => [number, number, number];
    readonly generateContentFingerprint: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly normalizeText: (a: number, b: number) => [number, number];
    readonly __wbg_wasmlshhasher_free: (a: number, b: number) => void;
    readonly wasmlshhasher_new: (a: number, b: number, c: number) => [number, number, number];
    readonly wasmlshhasher_withParams: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly wasmlshhasher_hash: (a: number, b: number, c: number) => [number, number, number];
    readonly wasmlshhasher_tables: (a: number) => number;
    readonly wasmlshhasher_bits: (a: number) => number;
    readonly wasmlshhasher_dimensions: (a: number) => number;
    readonly encodeFactProtobuf: (a: number, b: number) => [number, number, number, number];
    readonly encodeTombstoneProtobuf: (a: number, b: number, c: number, d: number, e: number) => [number, number];
    readonly parseDebriefResponse: (a: number, b: number) => [number, number, number];
    readonly getDebriefSystemPrompt: () => [number, number];
    readonly getExtractionSystemPrompt: () => [number, number];
    readonly getCompactionSystemPrompt: () => [number, number];
    readonly buildDebriefPrompt: (a: number, b: number) => [number, number, number, number];
    readonly getMinDebriefMessages: () => number;
    readonly getMaxDebriefItems: () => number;
    readonly getDebriefSource: () => [number, number];
    readonly encodeSingleCall: (a: number, b: number) => [number, number];
    readonly encodeSingleCallTo: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly encodeBatchCall: (a: number, b: number) => [number, number, number, number];
    readonly encodeBatchCallTo: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly hashUserOp: (a: number, b: number, c: number, d: number, e: bigint) => [number, number, number, number];
    readonly signUserOp: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly getDataEdgeAddress: () => [number, number];
    readonly getEntryPointAddress: () => [number, number];
    readonly getSimpleAccountFactory: () => [number, number];
    readonly getMaxBatchSize: () => number;
    readonly deriveEoa: (a: number, b: number) => [number, number, number];
    readonly deriveEoaAddress: (a: number, b: number) => [number, number, number, number];
    readonly generateSearchTrapdoors: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly parseSearchResponse: (a: number, b: number) => [number, number, number];
    readonly parseBroadenedResponse: (a: number, b: number) => [number, number, number];
    readonly decryptAndRerank: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number) => [number, number, number];
    readonly getSearchQuery: () => [number, number];
    readonly getBroadenedSearchQuery: () => [number, number];
    readonly getExportQuery: () => [number, number];
    readonly getCountQuery: () => [number, number];
    readonly hexBlobToBase64: (a: number, b: number) => [number, number];
    readonly getTrapdoorBatchSize: () => number;
    readonly getPageSize: () => number;
    readonly generateExpansionTrapdoors: (a: number, b: number, c: number, d: number, e: number) => [number, number, number];
    readonly mergeExpansionResults: (a: number, b: number, c: number) => [number, number, number];
    readonly wasmConfirmIndexedQuery: () => [number, number];
    readonly wasmConfirmIndexedParse: (a: number, b: number) => [number, number, number];
    readonly wasmConfirmIndexedDefaultTimeoutMs: () => number;
    readonly formatMemoryDate: (a: bigint) => [number, number];
    readonly recallContextHeader: (a: bigint) => [number, number];
    readonly formatRecallContext: (a: number, b: number, c: bigint) => [number, number];
    readonly segmentSessions: (a: number, b: number, c: number, d: number, e: number, f: number) => [number, number, number];
    readonly wasmConfirmIndexedDefaultPollMs: () => number;
    readonly chunksToSummaries: (a: number, b: number) => [number, number, number];
    readonly buildProfileBatchPrompt: (a: number, b: number) => [number, number, number, number];
    readonly parseProfileBatchResponse: (a: number, b: number) => [number, number, number];
    readonly buildProfileMergePrompt: (a: number, b: number) => [number, number, number, number];
    readonly parseProfileResponse: (a: number, b: number) => [number, number, number];
    readonly buildTriagePrompt: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly parseTriageResponse: (a: number, b: number) => [number, number, number];
    readonly enrichExtractionPrompt: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly prepareFact: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number, k: number, l: number, m: number, n: number, o: number, p: number) => [number, number, number];
    readonly prepareFactWithDecayScore: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number, k: number, l: number, m: number, n: number, o: number, p: number) => [number, number, number];
    readonly buildSingleCalldataFromPrepared: (a: number, b: number) => [number, number, number, number];
    readonly buildBatchCalldataFromPrepared: (a: number, b: number) => [number, number, number, number];
    readonly prepareTombstone: (a: number, b: number, c: number, d: number) => [number, number];
    readonly computeContentFingerprint: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly normalizeEntityName: (a: number, b: number) => [number, number];
    readonly deterministicEntityId: (a: number, b: number) => [number, number];
    readonly parseClaimOrLegacy: (a: number, b: number) => [number, number, number, number];
    readonly canonicalizeClaim: (a: number, b: number) => [number, number, number, number];
    readonly buildTemplateDigest: (a: number, b: number, c: bigint) => [number, number, number, number];
    readonly buildDigestPrompt: (a: number, b: number) => [number, number, number, number];
    readonly parseDigestResponse: (a: number, b: number) => [number, number, number, number];
    readonly assembleDigestFromLlm: (a: number, b: number, c: number, d: number, e: bigint) => [number, number, number, number];
    readonly defaultResolutionWeights: () => [number, number, number, number];
    readonly computeScoreComponents: (a: number, b: number, c: bigint, d: number, e: number) => [number, number, number, number];
    readonly resolvePair: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: bigint, j: number, k: number) => [number, number, number, number];
    readonly detectContradictions: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number) => [number, number, number, number];
    readonly applyFeedback: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly defaultWeightsFile: (a: bigint) => [number, number, number, number];
    readonly serializeWeightsFile: (a: number, b: number) => [number, number, number, number];
    readonly parseWeightsFile: (a: number, b: number) => [number, number, number, number];
    readonly appendFeedbackToJsonl: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly readFeedbackJsonl: (a: number, b: number) => [number, number, number, number];
    readonly rotateFeedbackLog: (a: number, b: number, c: bigint) => [number, number];
    readonly feedbackToCounterexample: (a: number, b: number) => [number, number, number, number];
    readonly isPinnedClaim: (a: number, b: number) => number;
    readonly respectPinInResolution: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number, k: number) => [number, number, number, number];
    readonly findLoserClaimInDecisionLog: (a: number, b: number, c: number, d: number) => [number, number];
    readonly findDecisionForPin: (a: number, b: number, c: number, d: number, e: number, f: number) => [number, number];
    readonly buildFeedbackFromDecision: (a: number, b: number, c: number, d: number, e: bigint) => [number, number];
    readonly appendDecisionEntry: (a: number, b: number, c: number, d: number) => [number, number];
    readonly DECISION_LOG_MAX_LINES: () => number;
    readonly CONTRADICTION_CANDIDATE_CAP: () => number;
    readonly TIE_ZONE_SCORE_TOLERANCE: () => number;
    readonly resolveWithCandidates: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number, k: number, l: number, m: bigint, n: number) => [number, number, number, number];
    readonly buildDecisionLogEntries: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: bigint) => [number, number, number, number];
    readonly filterShadowMode: (a: number, b: number, c: number, d: number) => [number, number, number, number];
    readonly parseGemini: (a: number, b: number) => [number, number, number];
    readonly rerank: (a: number, b: number, c: number, d: number, e: number, f: number, g: number) => [number, number, number];
    readonly rerankWithConfig: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number) => [number, number, number];
    readonly sourceWeight: (a: number, b: number) => number;
    readonly legacyClaimFallbackWeight: () => number;
    readonly validateMemoryClaimV1: (a: number, b: number) => [number, number, number, number];
    readonly parseMemoryTypeV1: (a: number, b: number) => [number, number];
    readonly parseMemorySource: (a: number, b: number) => [number, number];
    readonly parsePinStatus: (a: number, b: number) => [number, number];
    readonly isPinnedClaimJson: (a: number, b: number) => number;
    readonly cosineSimilarity: (a: number, b: number, c: number, d: number) => number;
    readonly pinBoost: (a: number, b: number, c: bigint, d: number, e: number) => [number, number, number];
    readonly defaultPinConfig: () => [number, number, number, number];
    readonly classifyPinIntent: (a: number, b: number) => [number, number, number, number];
    readonly __wbindgen_malloc: (a: number, b: number) => number;
    readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
    readonly __wbindgen_exn_store: (a: number) => void;
    readonly __externref_table_alloc: () => number;
    readonly __wbindgen_externrefs: WebAssembly.Table;
    readonly __wbindgen_free: (a: number, b: number, c: number) => void;
    readonly __externref_table_dealloc: (a: number) => void;
    readonly __wbindgen_start: () => void;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;

/**
 * Instantiates the given `module`, which can either be bytes or
 * a precompiled `WebAssembly.Module`.
 *
 * @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
 *
 * @returns {InitOutput}
 */
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
 * If `module_or_path` is {RequestInfo} or {URL}, makes a request and
 * for everything else, calls `WebAssembly.instantiate` directly.
 *
 * @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
 *
 * @returns {Promise<InitOutput>}
 */
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
