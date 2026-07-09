/* @ts-self-types="./totalreclaw_core.d.ts" */

/**
 * Contradiction candidate cap constant.
 * @returns {number}
 */
export function CONTRADICTION_CANDIDATE_CAP() {
    const ret = wasm.CONTRADICTION_CANDIDATE_CAP();
    return ret >>> 0;
}

/**
 * Decision log max lines constant.
 * @returns {number}
 */
export function DECISION_LOG_MAX_LINES() {
    const ret = wasm.DECISION_LOG_MAX_LINES();
    return ret >>> 0;
}

/**
 * Tie-zone score tolerance constant.
 * @returns {number}
 */
export function TIE_ZONE_SCORE_TOLERANCE() {
    const ret = wasm.TIE_ZONE_SCORE_TOLERANCE();
    return ret;
}

/**
 * Random Hyperplane LSH hasher (WASM wrapper).
 *
 * Construct with `new WasmLshHasher(seedHex, dims)`.
 * Call `hash(embeddingFloat64Array)` to get bucket IDs.
 */
export class WasmLshHasher {
    static __wrap(ptr) {
        ptr = ptr >>> 0;
        const obj = Object.create(WasmLshHasher.prototype);
        obj.__wbg_ptr = ptr;
        WasmLshHasherFinalization.register(obj, obj.__wbg_ptr, obj);
        return obj;
    }
    __destroy_into_raw() {
        const ptr = this.__wbg_ptr;
        this.__wbg_ptr = 0;
        WasmLshHasherFinalization.unregister(this);
        return ptr;
    }
    free() {
        const ptr = this.__destroy_into_raw();
        wasm.__wbg_wasmlshhasher_free(ptr, 0);
    }
    /**
     * Bits per table.
     * @returns {number}
     */
    get bits() {
        const ret = wasm.wasmlshhasher_bits(this.__wbg_ptr);
        return ret >>> 0;
    }
    /**
     * Embedding dimensionality.
     * @returns {number}
     */
    get dimensions() {
        const ret = wasm.wasmlshhasher_dimensions(this.__wbg_ptr);
        return ret >>> 0;
    }
    /**
     * Hash an embedding vector to blind-hashed bucket IDs.
     *
     * `embedding`: Float64Array of length `dims`.
     * Returns a JSON array of hex strings (one per table).
     * @param {Float64Array} embedding
     * @returns {any}
     */
    hash(embedding) {
        const ptr0 = passArrayF64ToWasm0(embedding, wasm.__wbindgen_malloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.wasmlshhasher_hash(this.__wbg_ptr, ptr0, len0);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        return takeFromExternrefTable0(ret[0]);
    }
    /**
     * Create a new LSH hasher with default parameters (20 tables, 32 bits).
     *
     * `seed_hex`: hex-encoded seed (>= 32 chars = 16 bytes).
     * `dims`: embedding dimensionality (e.g. 640).
     * @param {string} seed_hex
     * @param {number} dims
     */
    constructor(seed_hex, dims) {
        const ptr0 = passStringToWasm0(seed_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.wasmlshhasher_new(ptr0, len0, dims);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        this.__wbg_ptr = ret[0] >>> 0;
        WasmLshHasherFinalization.register(this, this.__wbg_ptr, this);
        return this;
    }
    /**
     * Number of hash tables.
     * @returns {number}
     */
    get tables() {
        const ret = wasm.wasmlshhasher_tables(this.__wbg_ptr);
        return ret >>> 0;
    }
    /**
     * Create a new LSH hasher with custom parameters.
     *
     * `seed_hex`: hex-encoded seed.
     * `dims`: embedding dimensionality.
     * `n_tables`: number of hash tables.
     * `n_bits`: bits per table.
     * @param {string} seed_hex
     * @param {number} dims
     * @param {number} n_tables
     * @param {number} n_bits
     * @returns {WasmLshHasher}
     */
    static withParams(seed_hex, dims, n_tables, n_bits) {
        const ptr0 = passStringToWasm0(seed_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.wasmlshhasher_withParams(ptr0, len0, dims, n_tables, n_bits);
        if (ret[2]) {
            throw takeFromExternrefTable0(ret[1]);
        }
        return WasmLshHasher.__wrap(ret[0]);
    }
}
if (Symbol.dispose) WasmLshHasher.prototype[Symbol.dispose] = WasmLshHasher.prototype.free;

/**
 * Append one decision entry to existing JSONL content. Non-fallible.
 * @param {string} existing_content
 * @param {string} entry_json
 * @returns {string}
 */
export function appendDecisionEntry(existing_content, entry_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(existing_content, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(entry_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.appendDecisionEntry(ptr0, len0, ptr1, len1);
        deferred3_0 = ret[0];
        deferred3_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Append one feedback entry to existing JSONL content.
 * @param {string} existing
 * @param {string} entry_json
 * @returns {string}
 */
export function appendFeedbackToJsonl(existing, entry_json) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(existing, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(entry_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.appendFeedbackToJsonl(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Apply a single counterexample to the weights; returns updated ResolutionWeights JSON.
 * @param {string} weights_json
 * @param {string} counterexample_json
 * @returns {string}
 */
export function applyFeedback(weights_json, counterexample_json) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(weights_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(counterexample_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.applyFeedback(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Assemble a full Digest from a parsed LLM response and source claims.
 * @param {string} parsed_json
 * @param {string} claims_json
 * @param {bigint} now_unix_seconds
 * @returns {string}
 */
export function assembleDigestFromLlm(parsed_json, claims_json, now_unix_seconds) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(parsed_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(claims_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.assembleDigestFromLlm(ptr0, len0, ptr1, len1, now_unix_seconds);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Build ABI-encoded calldata for a batch of prepared facts.
 *
 * `prepared_array_json`: JSON array of `PreparedFact` objects.
 * Returns ABI-encoded calldata (Uint8Array).
 * @param {string} prepared_array_json
 * @returns {Uint8Array}
 */
export function buildBatchCalldataFromPrepared(prepared_array_json) {
    const ptr0 = passStringToWasm0(prepared_array_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.buildBatchCalldataFromPrepared(ptr0, len0);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    var v2 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v2;
}

/**
 * Build the debrief prompt with already-stored facts filled in.
 *
 * `stored_facts_json`: JSON array of strings (fact texts already stored).
 * @param {string} stored_facts_json
 * @returns {string}
 */
export function buildDebriefPrompt(stored_facts_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(stored_facts_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.buildDebriefPrompt(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Build decision log entries from resolution actions.
 *
 * Returns a JSON array of `DecisionLogEntry`.
 * @param {string} actions_json
 * @param {string} new_claim_json
 * @param {string} existing_claims_json
 * @param {string} mode
 * @param {bigint} now_unix
 * @returns {string}
 */
export function buildDecisionLogEntries(actions_json, new_claim_json, existing_claims_json, mode, now_unix) {
    let deferred6_0;
    let deferred6_1;
    try {
        const ptr0 = passStringToWasm0(actions_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(new_claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(existing_claims_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        const ptr3 = passStringToWasm0(mode, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len3 = WASM_VECTOR_LEN;
        const ret = wasm.buildDecisionLogEntries(ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, now_unix);
        var ptr5 = ret[0];
        var len5 = ret[1];
        if (ret[3]) {
            ptr5 = 0; len5 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred6_0 = ptr5;
        deferred6_1 = len5;
        return getStringFromWasm0(ptr5, len5);
    } finally {
        wasm.__wbindgen_free(deferred6_0, deferred6_1, 1);
    }
}

/**
 * Build the LLM prompt for digest compilation.
 * `claims_json`: JSON array of Claim (must be non-empty).
 * @param {string} claims_json
 * @returns {string}
 */
export function buildDigestPrompt(claims_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(claims_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.buildDigestPrompt(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Build a FeedbackEntry JSON from a decision-log entry JSON + pin action.
 * Returns the JSON string, or the literal string "null" on failure.
 * @param {string} decision_json
 * @param {string} action
 * @param {bigint} now_unix
 * @returns {string}
 */
export function buildFeedbackFromDecision(decision_json, action, now_unix) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(decision_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(action, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.buildFeedbackFromDecision(ptr0, len0, ptr1, len1, now_unix);
        deferred3_0 = ret[0];
        deferred3_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Build the profiling prompt for a batch of conversation summaries.
 *
 * `summaries_json`: JSON array of ChunkSummary objects.
 * Returns the prompt string.
 * @param {string} summaries_json
 * @returns {string}
 */
export function buildProfileBatchPrompt(summaries_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(summaries_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.buildProfileBatchPrompt(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Build the merge prompt that combines partial profiles.
 *
 * `partials_json`: JSON array of PartialProfile objects.
 * Returns the prompt string.
 * @param {string} partials_json
 * @returns {string}
 */
export function buildProfileMergePrompt(partials_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(partials_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.buildProfileMergePrompt(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Build ABI-encoded calldata for a single prepared fact.
 *
 * `prepared_json`: JSON string of a `PreparedFact`.
 * Returns ABI-encoded calldata (Uint8Array).
 * @param {string} prepared_json
 * @returns {Uint8Array}
 */
export function buildSingleCalldataFromPrepared(prepared_json) {
    const ptr0 = passStringToWasm0(prepared_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.buildSingleCalldataFromPrepared(ptr0, len0);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    var v2 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v2;
}

/**
 * Build a template digest from an array of active claims.
 * `claims_json`: JSON array of Claim. Returns JSON-serialized Digest.
 * @param {string} claims_json
 * @param {bigint} now_unix_seconds
 * @returns {string}
 */
export function buildTemplateDigest(claims_json, now_unix_seconds) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(claims_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.buildTemplateDigest(ptr0, len0, now_unix_seconds);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Build the triage prompt for classifying chunks.
 *
 * `profile_json`: JSON string of a UserProfile.
 * `summaries_json`: JSON array of ChunkSummary objects.
 * Returns the prompt string.
 * @param {string} profile_json
 * @param {string} summaries_json
 * @returns {string}
 */
export function buildTriagePrompt(profile_json, summaries_json) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(profile_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(summaries_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.buildTriagePrompt(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Canonicalize a Claim JSON: strict-parse as Claim, re-serialize to canonical bytes.
 * Rejects legacy or malformed input. Use before encryption so TS/Python/Rust all
 * produce byte-identical blobs for the same logical claim.
 * @param {string} claim_json
 * @returns {string}
 */
export function canonicalizeClaim(claim_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.canonicalizeClaim(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Convert conversation chunks to summaries.
 *
 * `chunks_json`: JSON array of ConversationChunk objects.
 * Returns a JsValue (JSON array of ChunkSummary objects).
 * @param {string} chunks_json
 * @returns {any}
 */
export function chunksToSummaries(chunks_json) {
    const ptr0 = passStringToWasm0(chunks_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.chunksToSummaries(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Classify natural-language pin/unpin intent from a user utterance.
 *
 * Returns JSON of [`PinIntent`] when a trigger phrase matches, or `null` when
 * the utterance contains no recognised pin gesture. Lowercase normalization
 * is applied internally — callers pass the raw user text.
 * @param {string} text
 * @returns {string}
 */
export function classifyPinIntent(text) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(text, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.classifyPinIntent(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * WASM binding for `cluster_facts`.
 *
 * `candidates_json`: JSON array of `ConsolidationCandidate` objects.
 * `threshold`: Cosine similarity threshold for clustering.
 *
 * Returns JSON array of `{ representative: string, duplicates: string[] }`.
 * @param {string} candidates_json
 * @param {number} threshold
 * @returns {any}
 */
export function clusterFacts(candidates_json, threshold) {
    const ptr0 = passStringToWasm0(candidates_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.clusterFacts(ptr0, len0, threshold);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Compute SHA-256(authKey) as a hex string.
 *
 * `auth_key_hex`: 64-char hex string (32 bytes).
 * @param {string} auth_key_hex
 * @returns {string}
 */
export function computeAuthKeyHash(auth_key_hex) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(auth_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.computeAuthKeyHash(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Compute the content fingerprint for dedup checks.
 *
 * `dedup_key_hex`: 64-char hex string (32 bytes).
 * Returns 64-char hex fingerprint.
 * @param {string} text
 * @param {string} dedup_key_hex
 * @returns {string}
 */
export function computeContentFingerprint(text, dedup_key_hex) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(text, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(dedup_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.computeContentFingerprint(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Compute a claim's score components for contradiction resolution.
 * @param {string} claim_json
 * @param {bigint} now_unix_seconds
 * @param {string} weights_json
 * @returns {string}
 */
export function computeScoreComponents(claim_json, now_unix_seconds, weights_json) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(weights_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.computeScoreComponents(ptr0, len0, now_unix_seconds, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Cosine similarity between two f32 vectors.
 * @param {Float32Array} a
 * @param {Float32Array} b
 * @returns {number}
 */
export function cosineSimilarity(a, b) {
    const ptr0 = passArrayF32ToWasm0(a, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passArrayF32ToWasm0(b, wasm.__wbindgen_malloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.cosineSimilarity(ptr0, len0, ptr1, len1);
    return ret;
}

/**
 * Decrypt a base64-encoded XChaCha20-Poly1305 blob.
 *
 * `encryption_key_hex`: 64-char hex string (32 bytes).
 * Returns the plaintext UTF-8 string.
 * @param {string} encrypted_base64
 * @param {string} encryption_key_hex
 * @returns {string}
 */
export function decrypt(encrypted_base64, encryption_key_hex) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(encrypted_base64, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(encryption_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.decrypt(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

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
 * @param {string} facts_json
 * @param {string} query
 * @param {Float32Array} query_embedding
 * @param {string} encryption_key_hex
 * @param {number} top_k
 * @returns {any}
 */
export function decryptAndRerank(facts_json, query, query_embedding, encryption_key_hex, top_k) {
    const ptr0 = passStringToWasm0(facts_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(query, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ptr2 = passArrayF32ToWasm0(query_embedding, wasm.__wbindgen_malloc);
    const len2 = WASM_VECTOR_LEN;
    const ptr3 = passStringToWasm0(encryption_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len3 = WASM_VECTOR_LEN;
    const ret = wasm.decryptAndRerank(ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, top_k);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Return the locked-default [`PinConfig`] as JSON. Clients that don't want
 * to retune can pass this verbatim to [`wasm_pin_boost`].
 * @returns {string}
 */
export function defaultPinConfig() {
    let deferred2_0;
    let deferred2_1;
    try {
        const ret = wasm.defaultPinConfig();
        var ptr1 = ret[0];
        var len1 = ret[1];
        if (ret[3]) {
            ptr1 = 0; len1 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred2_0 = ptr1;
        deferred2_1 = len1;
        return getStringFromWasm0(ptr1, len1);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Default P2-3 resolution weights as JSON.
 * @returns {string}
 */
export function defaultResolutionWeights() {
    let deferred2_0;
    let deferred2_1;
    try {
        const ret = wasm.defaultResolutionWeights();
        var ptr1 = ret[0];
        var len1 = ret[1];
        if (ret[3]) {
            ptr1 = 0; len1 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred2_0 = ptr1;
        deferred2_1 = len1;
        return getStringFromWasm0(ptr1, len1);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Build a fresh default WeightsFile JSON with the given timestamp.
 * @param {bigint} now_unix_seconds
 * @returns {string}
 */
export function defaultWeightsFile(now_unix_seconds) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ret = wasm.defaultWeightsFile(now_unix_seconds);
        var ptr1 = ret[0];
        var len1 = ret[1];
        if (ret[3]) {
            ptr1 = 0; len1 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred2_0 = ptr1;
        deferred2_1 = len1;
        return getStringFromWasm0(ptr1, len1);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Derive an Ethereum EOA wallet from a BIP-39 mnemonic via BIP-44.
 *
 * Path: m/44'/60'/0'/0/0 (standard Ethereum derivation path).
 * Returns a JS object: `{ private_key: "hex...", address: "0x..." }`.
 * @param {string} mnemonic
 * @returns {any}
 */
export function deriveEoa(mnemonic) {
    const ptr0 = passStringToWasm0(mnemonic, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.deriveEoa(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Derive just the Ethereum EOA address from a BIP-39 mnemonic.
 *
 * Returns: `"0x..."` (lowercase hex).
 * @param {string} mnemonic
 * @returns {string}
 */
export function deriveEoaAddress(mnemonic) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(mnemonic, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.deriveEoaAddress(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Derive encryption keys from a BIP-39 mnemonic (strict checksum validation).
 *
 * Returns a JSON object with hex-encoded keys:
 * `{ auth_key, encryption_key, dedup_key, salt }`
 * @param {string} mnemonic
 * @returns {any}
 */
export function deriveKeysFromMnemonic(mnemonic) {
    const ptr0 = passStringToWasm0(mnemonic, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.deriveKeysFromMnemonic(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Derive encryption keys from a BIP-39 mnemonic (lenient -- skips checksum).
 *
 * Same return format as `deriveKeysFromMnemonic`.
 * @param {string} mnemonic
 * @returns {any}
 */
export function deriveKeysFromMnemonicLenient(mnemonic) {
    const ptr0 = passStringToWasm0(mnemonic, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.deriveKeysFromMnemonicLenient(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Derive the 32-byte LSH seed from a BIP-39 mnemonic and salt.
 *
 * `salt_hex`: 64-char hex string (32 bytes).
 * Returns hex-encoded 32-byte seed.
 * @param {string} mnemonic
 * @param {string} salt_hex
 * @returns {string}
 */
export function deriveLshSeed(mnemonic, salt_hex) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(mnemonic, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(salt_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.deriveLshSeed(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Detect contradictions between a new claim and existing claims (JSON array of {claim, id, embedding}).
 * @param {string} new_claim_json
 * @param {string} new_claim_id
 * @param {string} new_embedding_json
 * @param {string} existing_json
 * @param {number} lower_threshold
 * @param {number} upper_threshold
 * @returns {string}
 */
export function detectContradictions(new_claim_json, new_claim_id, new_embedding_json, existing_json, lower_threshold, upper_threshold) {
    let deferred6_0;
    let deferred6_1;
    try {
        const ptr0 = passStringToWasm0(new_claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(new_claim_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(new_embedding_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        const ptr3 = passStringToWasm0(existing_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len3 = WASM_VECTOR_LEN;
        const ret = wasm.detectContradictions(ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, lower_threshold, upper_threshold);
        var ptr5 = ret[0];
        var len5 = ret[1];
        if (ret[3]) {
            ptr5 = 0; len5 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred6_0 = ptr5;
        deferred6_1 = len5;
        return getStringFromWasm0(ptr5, len5);
    } finally {
        wasm.__wbindgen_free(deferred6_0, deferred6_1, 1);
    }
}

/**
 * Deterministic entity ID from a name (first 8 bytes of SHA256 as hex).
 * @param {string} name
 * @returns {string}
 */
export function deterministicEntityId(name) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.deterministicEntityId(ptr0, len0);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Encode multiple fact submissions as SimpleAccount.executeBatch() calldata.
 *
 * `payloads_json`: JSON array of hex-encoded payload strings (e.g. `["deadbeef", "cafebabe"]`).
 * Returns ABI-encoded calldata (Uint8Array).
 * @param {string} payloads_json
 * @returns {Uint8Array}
 */
export function encodeBatchCall(payloads_json) {
    const ptr0 = passStringToWasm0(payloads_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.encodeBatchCall(ptr0, len0);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    var v2 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v2;
}

/**
 * Like `encodeBatchCall` but targets an explicit DataEdge address (#366).
 * @param {string} payloads_json
 * @param {string} data_edge_address
 * @returns {Uint8Array}
 */
export function encodeBatchCallTo(payloads_json, data_edge_address) {
    const ptr0 = passStringToWasm0(payloads_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(data_edge_address, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.encodeBatchCallTo(ptr0, len0, ptr1, len1);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    var v3 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v3;
}

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
 * @param {string} json
 * @returns {Uint8Array}
 */
export function encodeFactProtobuf(json) {
    const ptr0 = passStringToWasm0(json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.encodeFactProtobuf(ptr0, len0);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    var v2 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v2;
}

/**
 * Encode a single fact submission as SimpleAccount.execute() calldata.
 *
 * `protobuf_payload`: raw protobuf bytes (Uint8Array).
 * Returns ABI-encoded calldata (Uint8Array).
 * @param {Uint8Array} protobuf_payload
 * @returns {Uint8Array}
 */
export function encodeSingleCall(protobuf_payload) {
    const ptr0 = passArray8ToWasm0(protobuf_payload, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.encodeSingleCall(ptr0, len0);
    var v2 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v2;
}

/**
 * Like `encodeSingleCall` but targets an explicit DataEdge address.
 *
 * Chain/environment-aware clients pass the authoritative address from the
 * relay's `/v1/billing/status` `data_edge_address` (#366) — the isolated
 * staging Gnosis DataEdge differs from prod's. Throws on a bad address.
 * @param {Uint8Array} protobuf_payload
 * @param {string} data_edge_address
 * @returns {Uint8Array}
 */
export function encodeSingleCallTo(protobuf_payload, data_edge_address) {
    const ptr0 = passArray8ToWasm0(protobuf_payload, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(data_edge_address, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.encodeSingleCallTo(ptr0, len0, ptr1, len1);
    if (ret[3]) {
        throw takeFromExternrefTable0(ret[2]);
    }
    var v3 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v3;
}

/**
 * Encode a tombstone protobuf for soft-deleting a fact.
 *
 * `version` is optional; missing/0 defaults to `DEFAULT_PROTOBUF_VERSION` (3).
 * Pass `4` to emit a v1-taxonomy tombstone (outer protobuf version = 4).
 *
 * Returns the protobuf bytes as a Uint8Array.
 * @param {string} fact_id
 * @param {string} owner
 * @param {number | null} [version]
 * @returns {Uint8Array}
 */
export function encodeTombstoneProtobuf(fact_id, owner, version) {
    const ptr0 = passStringToWasm0(fact_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(owner, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.encodeTombstoneProtobuf(ptr0, len0, ptr1, len1, isLikeNone(version) ? 0x100000001 : (version) >>> 0);
    var v3 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v3;
}

/**
 * Encrypt a UTF-8 plaintext with XChaCha20-Poly1305.
 *
 * `encryption_key_hex`: 64-char hex string (32 bytes).
 * Returns base64-encoded ciphertext (wire format: nonce || tag || ciphertext).
 * @param {string} plaintext
 * @param {string} encryption_key_hex
 * @returns {string}
 */
export function encrypt(plaintext, encryption_key_hex) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(plaintext, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(encryption_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.encrypt(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Enrich an extraction prompt with user profile context.
 *
 * `profile_json`: JSON string of a UserProfile.
 * `base_prompt`: The base extraction prompt to enrich.
 * Returns the enriched prompt string.
 * @param {string} profile_json
 * @param {string} base_prompt
 * @returns {string}
 */
export function enrichExtractionPrompt(profile_json, base_prompt) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(profile_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(base_prompt, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.enrichExtractionPrompt(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Convert a feedback entry into a counterexample for weight tuning. Returns
 * JSON Counterexample or the literal string "null" if the entry has no signal.
 * @param {string} entry_json
 * @returns {string}
 */
export function feedbackToCounterexample(entry_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(entry_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.feedbackToCounterexample(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Filter resolution actions by mode ("active" passes through, "shadow"/"off" returns empty).
 *
 * Returns a JSON array of `ResolutionAction`.
 * @param {string} actions_json
 * @param {string} mode
 * @returns {string}
 */
export function filterShadowMode(actions_json, mode) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(actions_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(mode, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.filterShadowMode(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * WASM binding for `find_best_near_duplicate`.
 *
 * `new_embedding_json`: JSON array of floats (embedding vector).
 * `existing_json`: JSON array of `{ id: string, embedding: number[] }` objects.
 * `threshold`: Cosine similarity threshold.
 *
 * Returns JSON `{ fact_id: string, similarity: number }` or null.
 * @param {string} new_embedding_json
 * @param {string} existing_json
 * @param {number} threshold
 * @returns {any}
 */
export function findBestNearDuplicate(new_embedding_json, existing_json, threshold) {
    const ptr0 = passStringToWasm0(new_embedding_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(existing_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.findBestNearDuplicate(ptr0, len0, ptr1, len1, threshold);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Find a decision-log entry matching a fact as winner or loser.
 * Returns the JSON-serialized DecisionLogEntry, or the literal string "null".
 * @param {string} fact_id
 * @param {string} role
 * @param {string} log_content
 * @returns {string}
 */
export function findDecisionForPin(fact_id, role, log_content) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(fact_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(role, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(log_content, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        const ret = wasm.findDecisionForPin(ptr0, len0, ptr1, len1, ptr2, len2);
        deferred4_0 = ret[0];
        deferred4_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Find the loser claim JSON from the decision log for a given fact ID.
 * Returns the loser_claim_json string, or the literal string "null" if not found.
 * @param {string} fact_id
 * @param {string} log_content
 * @returns {string}
 */
export function findLoserClaimInDecisionLog(fact_id, log_content) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(fact_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(log_content, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.findLoserClaimInDecisionLog(ptr0, len0, ptr1, len1);
        deferred3_0 = ret[0];
        deferred3_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

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
 * @param {Float32Array} new_embedding
 * @param {string} existing_json
 * @param {number} threshold
 * @returns {any}
 */
export function findNearDuplicate(new_embedding, existing_json, threshold) {
    const ptr0 = passArrayF32ToWasm0(new_embedding, wasm.__wbindgen_malloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(existing_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.findNearDuplicate(ptr0, len0, ptr1, len1, threshold);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Unix seconds → `"YYYY-MM-DD"` (UTC). Returns `""` for `0` or negative.
 *
 * Maps directly to [`crate::recall_context::format_memory_date`].
 * @param {bigint} created_at_unix
 * @returns {string}
 */
export function formatMemoryDate(created_at_unix) {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.formatMemoryDate(created_at_unix);
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

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
 * @param {string} items_json
 * @param {bigint} now_unix
 * @returns {string}
 */
export function formatRecallContext(items_json, now_unix) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(items_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.formatRecallContext(ptr0, len0, now_unix);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Generate blind indices (SHA-256 token hashes) for a text string.
 *
 * Returns a JSON array of hex strings.
 * @param {string} text
 * @returns {any}
 */
export function generateBlindIndices(text) {
    const ptr0 = passStringToWasm0(text, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.generateBlindIndices(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Compute HMAC-SHA256 content fingerprint.
 *
 * `dedup_key_hex`: 64-char hex string (32 bytes).
 * Returns 64-char hex fingerprint.
 * @param {string} plaintext
 * @param {string} dedup_key_hex
 * @returns {string}
 */
export function generateContentFingerprint(plaintext, dedup_key_hex) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(plaintext, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(dedup_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.generateContentFingerprint(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Generate trapdoors for multiple query reformulations (expansion pipeline).
 *
 * `queries_json`: JSON array of query strings (original + reformulations).
 * `embeddings_json`: JSON array of Float32Array-compatible arrays (one per query).
 * `lsh_hasher`: A `WasmLshHasher` instance.
 *
 * Returns a JsValue (JSON array of trapdoor-string arrays, one per query).
 * @param {string} queries_json
 * @param {string} embeddings_json
 * @param {WasmLshHasher} lsh_hasher
 * @returns {any}
 */
export function generateExpansionTrapdoors(queries_json, embeddings_json, lsh_hasher) {
    const ptr0 = passStringToWasm0(queries_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(embeddings_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    _assertClass(lsh_hasher, WasmLshHasher);
    const ret = wasm.generateExpansionTrapdoors(ptr0, len0, ptr1, len1, lsh_hasher.__wbg_ptr);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Generate all search trapdoors for a query (word hashes + LSH bucket hashes).
 *
 * `query`: The search query text.
 * `query_embedding`: Float32Array of the query embedding.
 * `lsh_hasher`: A `WasmLshHasher` instance.
 *
 * Returns a JsValue (JSON array of hex-encoded trapdoor strings).
 * @param {string} query
 * @param {Float32Array} query_embedding
 * @param {WasmLshHasher} lsh_hasher
 * @returns {any}
 */
export function generateSearchTrapdoors(query, query_embedding, lsh_hasher) {
    const ptr0 = passStringToWasm0(query, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passArrayF32ToWasm0(query_embedding, wasm.__wbindgen_malloc);
    const len1 = WASM_VECTOR_LEN;
    _assertClass(lsh_hasher, WasmLshHasher);
    const ret = wasm.generateSearchTrapdoors(ptr0, len0, ptr1, len1, lsh_hasher.__wbg_ptr);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Get the GraphQL query string for broadened (fallback) search.
 * @returns {string}
 */
export function getBroadenedSearchQuery() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getBroadenedSearchQuery();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the canonical v1 compaction system prompt.
 *
 * Used on end-of-context surfaces where the importance floor is 5 rather
 * than the default 6.
 * @returns {string}
 */
export function getCompactionSystemPrompt() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getCompactionSystemPrompt();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * WASM binding: get the consolidation cosine threshold constant.
 * @returns {number}
 */
export function getConsolidationCosineThreshold() {
    const ret = wasm.getConsolidationCosineThreshold();
    return ret;
}

/**
 * Get the GraphQL query string for fact count.
 * @returns {string}
 */
export function getCountQuery() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getCountQuery();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the DataEdge contract address constant.
 * @returns {string}
 */
export function getDataEdgeAddress() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getDataEdgeAddress();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Source tag for debrief items.
 * @returns {string}
 */
export function getDebriefSource() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getDebriefSource();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the canonical debrief system prompt template.
 *
 * Contains `{already_stored_facts}` placeholder.
 * @returns {string}
 */
export function getDebriefSystemPrompt() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getDebriefSystemPrompt();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the EntryPoint v0.7 address constant.
 * @returns {string}
 */
export function getEntryPointAddress() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getEntryPointAddress();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the GraphQL query string for paginated export.
 * @returns {string}
 */
export function getExportQuery() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getExportQuery();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the canonical v1 merged-topic extraction system prompt.
 *
 * Single source of truth across all TotalReclaw clients — TS/WASM
 * callers get the same bytes the Python `totalreclaw_core` module
 * returns from `get_extraction_system_prompt()`. Includes the Rule 6
 * meta-request filter (see the docstring on `prompts.rs`).
 * @returns {string}
 */
export function getExtractionSystemPrompt() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getExtractionSystemPrompt();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the maximum batch size constant.
 * @returns {number}
 */
export function getMaxBatchSize() {
    const ret = wasm.getMaxBatchSize();
    return ret >>> 0;
}

/**
 * Maximum debrief items (5).
 * @returns {number}
 */
export function getMaxDebriefItems() {
    const ret = wasm.getMaxDebriefItems();
    return ret >>> 0;
}

/**
 * Minimum messages for debrief (8 = 4 turns).
 * @returns {number}
 */
export function getMinDebriefMessages() {
    const ret = wasm.getMinDebriefMessages();
    return ret >>> 0;
}

/**
 * Get the page size constant.
 * @returns {number}
 */
export function getPageSize() {
    const ret = wasm.getPageSize();
    return ret >>> 0;
}

/**
 * Get the GraphQL query string for blind index search.
 * @returns {string}
 */
export function getSearchQuery() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getSearchQuery();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Get the SimpleAccountFactory address constant.
 * @returns {string}
 */
export function getSimpleAccountFactory() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.getSimpleAccountFactory();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * WASM binding: get the store-time dedup cosine threshold constant.
 * @returns {number}
 */
export function getStoreDedupCosineThreshold() {
    const ret = wasm.getStoreDedupCosineThreshold();
    return ret;
}

/**
 * WASM binding: get the store-time dedup max candidates constant.
 * @returns {number}
 */
export function getStoreDedupMaxCandidates() {
    const ret = wasm.getStoreDedupMaxCandidates();
    return ret >>> 0;
}

/**
 * Get the trapdoor batch size constant.
 * @returns {number}
 */
export function getTrapdoorBatchSize() {
    const ret = wasm.getTrapdoorBatchSize();
    return ret >>> 0;
}

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
 * @returns {any}
 */
export function getTypeToCategory() {
    const ret = wasm.getTypeToCategory();
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Get the canonical list of v1 memory types.
 *
 * Returns a JS array of six strings: `["claim", "preference",
 * "directive", "commitment", "episode", "summary"]`.
 * @returns {any}
 */
export function getValidMemoryTypes() {
    const ret = wasm.getValidMemoryTypes();
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Compute the ERC-4337 v0.7 UserOp hash for signing.
 *
 * `userop_json`: JSON string of a UserOperationV7 struct.
 * `entrypoint`: EntryPoint address (0x-prefixed).
 * `chain_id`: Chain ID (e.g. 84532 for Base Sepolia).
 * Returns 32-byte hash as hex string.
 * @param {string} userop_json
 * @param {string} entrypoint
 * @param {bigint} chain_id
 * @returns {string}
 */
export function hashUserOp(userop_json, entrypoint, chain_id) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(userop_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(entrypoint, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.hashUserOp(ptr0, len0, ptr1, len1, chain_id);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Convert a subgraph hex blob to base64 for decryption.
 *
 * `hex_blob`: Hex string (optionally `0x`-prefixed) from the subgraph.
 * Returns base64-encoded bytes, or null if the hex is invalid.
 * @param {string} hex_blob
 * @returns {string | undefined}
 */
export function hexBlobToBase64(hex_blob) {
    const ptr0 = passStringToWasm0(hex_blob, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.hexBlobToBase64(ptr0, len0);
    let v2;
    if (ret[0] !== 0) {
        v2 = getStringFromWasm0(ret[0], ret[1]).slice();
        wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    }
    return v2;
}

/**
 * Check whether a JSON-serialized claim has pinned status.
 * @param {string} claim_json
 * @returns {boolean}
 */
export function isPinnedClaim(claim_json) {
    const ptr0 = passStringToWasm0(claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.isPinnedClaim(ptr0, len0);
    return ret !== 0;
}

/**
 * Check whether a JSON-encoded claim is pinned, recognizing both the v0
 * short-key sentinel (`st == "p"`) and the v1.1 field (`pin_status ==
 * "pinned"`). Returns `false` on any parse failure.
 *
 * Wrapper around [`crate::claims::is_pinned_json`] for TS clients.
 * @param {string} claim_json
 * @returns {boolean}
 */
export function isPinnedClaimJson(claim_json) {
    const ptr0 = passStringToWasm0(claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.isPinnedClaimJson(ptr0, len0);
    return ret !== 0;
}

/**
 * Runtime guard: is `value` a valid v1 memory type?
 * @param {string} value
 * @returns {boolean}
 */
export function isValidMemoryType(value) {
    const ptr0 = passStringToWasm0(value, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.isValidMemoryType(ptr0, len0);
    return ret !== 0;
}

/**
 * Return the v1 legacy-claim fallback weight (applied to candidates that
 * have no `source` field).
 * @returns {number}
 */
export function legacyClaimFallbackWeight() {
    const ret = wasm.legacyClaimFallbackWeight();
    return ret;
}

/**
 * Map a v1 type to its short-form category key.
 *
 * Returns `null` if `value` is not one of the six v1 types.
 * @param {string} value
 * @returns {any}
 */
export function mapTypeToCategory(value) {
    const ptr0 = passStringToWasm0(value, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.mapTypeToCategory(ptr0, len0);
    return ret;
}

/**
 * Merge multiple SubgraphFact sets from parallel query reformulations via RRF.
 *
 * `fact_sets_json`: JSON array of SubgraphFact arrays (one array per reformulation).
 * `rrf_k`: RRF k-parameter (use 60.0 for default behaviour).
 *
 * Returns a JsValue (merged, deduplicated SubgraphFact array sorted by RRF score).
 * @param {string} fact_sets_json
 * @param {number} rrf_k
 * @returns {any}
 */
export function mergeExpansionResults(fact_sets_json, rrf_k) {
    const ptr0 = passStringToWasm0(fact_sets_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.mergeExpansionResults(ptr0, len0, rrf_k);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Normalize an entity name (NFC, lowercase, trim, collapse whitespace).
 * @param {string} name
 * @returns {string}
 */
export function normalizeEntityName(name) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(name, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.normalizeEntityName(ptr0, len0);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Normalize text (NFC, lowercase, collapse whitespace, trim).
 * @param {string} text
 * @returns {string}
 */
export function normalizeText(text) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(text, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.normalizeText(ptr0, len0);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Parse a broadened search GraphQL response into SubgraphFact list.
 *
 * `response_json`: Raw JSON string from the GraphQL response.
 * Returns a JsValue (JSON array of SubgraphFact objects).
 * @param {string} response_json
 * @returns {any}
 */
export function parseBroadenedResponse(response_json) {
    const ptr0 = passStringToWasm0(response_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.parseBroadenedResponse(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Parse a decrypted blob as a Claim, falling back to legacy formats.
 * Returns JSON-serialized Claim.
 * @param {string} decrypted
 * @returns {string}
 */
export function parseClaimOrLegacy(decrypted) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(decrypted, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.parseClaimOrLegacy(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Parse a debrief LLM response into validated items.
 *
 * Returns a JSON array of `{ text, type, importance }` objects.
 * @param {string} response
 * @returns {any}
 */
export function parseDebriefResponse(response) {
    const ptr0 = passStringToWasm0(response, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.parseDebriefResponse(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Parse an LLM digest response.
 * Returns JSON-serialized ParsedDigestResponse.
 * @param {string} raw
 * @returns {string}
 */
export function parseDigestResponse(raw) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(raw, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.parseDigestResponse(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Parse a Gemini export (JSON or saved-info text) into a `ParseResult`.
 * @param {string} input
 * @returns {any}
 */
export function parseGemini(input) {
    const ptr0 = passStringToWasm0(input, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.parseGemini(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Case-insensitive parse of a memory source string. Unknown input returns "user-inferred".
 * @param {string} s
 * @returns {string}
 */
export function parseMemorySource(s) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(s, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.parseMemorySource(ptr0, len0);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Case-insensitive parse of a memory type string. Unknown input returns "claim".
 * @param {string} s
 * @returns {string}
 */
export function parseMemoryTypeV1(s) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(s, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.parseMemoryTypeV1(ptr0, len0);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Case-insensitive parse of a v1.1 pin_status string. Unknown input returns "unpinned".
 * @param {string} s
 * @returns {string}
 */
export function parsePinStatus(s) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(s, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.parsePinStatus(ptr0, len0);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

/**
 * Parse a batch profiling LLM response into a PartialProfile.
 *
 * `llm_output`: Raw LLM response string.
 * Returns a JsValue (PartialProfile object).
 * @param {string} llm_output
 * @returns {any}
 */
export function parseProfileBatchResponse(llm_output) {
    const ptr0 = passStringToWasm0(llm_output, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.parseProfileBatchResponse(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Parse the merge LLM response into a UserProfile.
 *
 * `llm_output`: Raw LLM response string.
 * Returns a JsValue (UserProfile object).
 * @param {string} llm_output
 * @returns {any}
 */
export function parseProfileResponse(llm_output) {
    const ptr0 = passStringToWasm0(llm_output, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.parseProfileResponse(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Parse a blind index search GraphQL response into SubgraphFact list.
 *
 * `response_json`: Raw JSON string from the GraphQL response.
 * Returns a JsValue (JSON array of SubgraphFact objects).
 * @param {string} response_json
 * @returns {any}
 */
export function parseSearchResponse(response_json) {
    const ptr0 = passStringToWasm0(response_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.parseSearchResponse(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Parse the triage LLM response into chunk decisions.
 *
 * `llm_output`: Raw LLM response string.
 * Returns a JsValue (JSON array of ChunkDecision objects).
 * @param {string} llm_output
 * @returns {any}
 */
export function parseTriageResponse(llm_output) {
    const ptr0 = passStringToWasm0(llm_output, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.parseTriageResponse(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Parse a WeightsFile from JSON; rejects unknown versions and malformed input.
 * @param {string} content
 * @returns {string}
 */
export function parseWeightsFile(content) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(content, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.parseWeightsFile(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Compute the [`PinTier`]'s multiplicative boost at a given timestamp.
 *
 * `tier_json`: internally-tagged JSON, e.g. `{"tier":"soft","pinned_at":1716000000}`,
 * `{"tier":"hard"}`, `{"tier":"none"}`.
 * `now_unix`: seconds since epoch.
 * `config_json`: JSON of [`PinConfig`], e.g. `{"soft_half_life_days":90,"soft_max_boost":1.5,"hard_boost":1.5}`.
 *
 * Returns the multiplicative boost factor (1.0 for `none`).
 * @param {string} tier_json
 * @param {bigint} now_unix
 * @param {string} config_json
 * @returns {number}
 */
export function pinBoost(tier_json, now_unix, config_json) {
    const ptr0 = passStringToWasm0(tier_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(config_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.pinBoost(ptr0, len0, now_unix, ptr1, len1);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return ret[0];
}

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
 * @param {string} text
 * @param {string} encryption_key_hex
 * @param {string} dedup_key_hex
 * @param {WasmLshHasher} lsh_hasher
 * @param {Float32Array} embedding
 * @param {number} importance
 * @param {string} source
 * @param {string} owner
 * @param {string} agent_id
 * @returns {any}
 */
export function prepareFact(text, encryption_key_hex, dedup_key_hex, lsh_hasher, embedding, importance, source, owner, agent_id) {
    const ptr0 = passStringToWasm0(text, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(encryption_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ptr2 = passStringToWasm0(dedup_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len2 = WASM_VECTOR_LEN;
    _assertClass(lsh_hasher, WasmLshHasher);
    const ptr3 = passArrayF32ToWasm0(embedding, wasm.__wbindgen_malloc);
    const len3 = WASM_VECTOR_LEN;
    const ptr4 = passStringToWasm0(source, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len4 = WASM_VECTOR_LEN;
    const ptr5 = passStringToWasm0(owner, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len5 = WASM_VECTOR_LEN;
    const ptr6 = passStringToWasm0(agent_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len6 = WASM_VECTOR_LEN;
    const ret = wasm.prepareFact(ptr0, len0, ptr1, len1, ptr2, len2, lsh_hasher.__wbg_ptr, ptr3, len3, importance, ptr4, len4, ptr5, len5, ptr6, len6);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Prepare a fact with a pre-normalized decay score (already 0.0-1.0).
 *
 * Same as `prepareFact()` but takes a raw decay score.
 * @param {string} text
 * @param {string} encryption_key_hex
 * @param {string} dedup_key_hex
 * @param {WasmLshHasher} lsh_hasher
 * @param {Float32Array} embedding
 * @param {number} decay_score
 * @param {string} source
 * @param {string} owner
 * @param {string} agent_id
 * @returns {any}
 */
export function prepareFactWithDecayScore(text, encryption_key_hex, dedup_key_hex, lsh_hasher, embedding, decay_score, source, owner, agent_id) {
    const ptr0 = passStringToWasm0(text, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(encryption_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ptr2 = passStringToWasm0(dedup_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len2 = WASM_VECTOR_LEN;
    _assertClass(lsh_hasher, WasmLshHasher);
    const ptr3 = passArrayF32ToWasm0(embedding, wasm.__wbindgen_malloc);
    const len3 = WASM_VECTOR_LEN;
    const ptr4 = passStringToWasm0(source, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len4 = WASM_VECTOR_LEN;
    const ptr5 = passStringToWasm0(owner, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len5 = WASM_VECTOR_LEN;
    const ptr6 = passStringToWasm0(agent_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len6 = WASM_VECTOR_LEN;
    const ret = wasm.prepareFactWithDecayScore(ptr0, len0, ptr1, len1, ptr2, len2, lsh_hasher.__wbg_ptr, ptr3, len3, decay_score, ptr4, len4, ptr5, len5, ptr6, len6);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Prepare a tombstone (soft-delete) protobuf.
 *
 * Returns the protobuf bytes as a Uint8Array.
 * @param {string} fact_id
 * @param {string} owner
 * @returns {Uint8Array}
 */
export function prepareTombstone(fact_id, owner) {
    const ptr0 = passStringToWasm0(fact_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(owner, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.prepareTombstone(ptr0, len0, ptr1, len1);
    var v3 = getArrayU8FromWasm0(ret[0], ret[1]).slice();
    wasm.__wbindgen_free(ret[0], ret[1] * 1, 1);
    return v3;
}

/**
 * Parse JSONL content. Returns JSON: `{"entries": [...], "warnings": [...]}`.
 * @param {string} content
 * @returns {string}
 */
export function readFeedbackJsonl(content) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(content, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.readFeedbackJsonl(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Build the recall-context header string (current-date + temporal-reasoning nudge).
 *
 * `now_unix`: current time as Unix seconds.
 * Returns the header with a trailing newline, e.g.:
 * `"## Relevant memories from TotalReclaw\nThe current date is 2024-01-15. ..."`
 * @param {bigint} now_unix
 * @returns {string}
 */
export function recallContextHeader(now_unix) {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.recallContextHeader(now_unix);
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

/**
 * Rerank candidates using BM25 + Cosine + RRF fusion.
 *
 * `candidates_json`: JSON array of `{ id, text, embedding, timestamp, source? }` objects.
 * Returns a JsValue (array of `RankedResult` objects).
 * @param {string} query
 * @param {Float32Array} query_embedding
 * @param {string} candidates_json
 * @param {number} top_k
 * @returns {any}
 */
export function rerank(query, query_embedding, candidates_json, top_k) {
    const ptr0 = passStringToWasm0(query, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passArrayF32ToWasm0(query_embedding, wasm.__wbindgen_malloc);
    const len1 = WASM_VECTOR_LEN;
    const ptr2 = passStringToWasm0(candidates_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len2 = WASM_VECTOR_LEN;
    const ret = wasm.rerank(ptr0, len0, ptr1, len1, ptr2, len2, top_k);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Rerank candidates with a config flag (Retrieval v2 Tier 1).
 *
 * When `apply_source_weights` is `true`, each candidate's final score is
 * multiplied by the provenance weight from its `source` field (legacy
 * candidates without `source` use the v0 fallback weight).
 *
 * `candidates_json`: JSON array of `{ id, text, embedding, timestamp, source? }` objects.
 * Returns a JsValue (array of `RankedResult` objects including `source_weight`).
 * @param {string} query
 * @param {Float32Array} query_embedding
 * @param {string} candidates_json
 * @param {number} top_k
 * @param {boolean} apply_source_weights
 * @returns {any}
 */
export function rerankWithConfig(query, query_embedding, candidates_json, top_k, apply_source_weights) {
    const ptr0 = passStringToWasm0(query, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passArrayF32ToWasm0(query_embedding, wasm.__wbindgen_malloc);
    const len1 = WASM_VECTOR_LEN;
    const ptr2 = passStringToWasm0(candidates_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len2 = WASM_VECTOR_LEN;
    const ret = wasm.rerankWithConfig(ptr0, len0, ptr1, len1, ptr2, len2, top_k, apply_source_weights);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Run the resolution formula on two contradicting claims; returns ResolutionOutcome JSON.
 * @param {string} claim_a_json
 * @param {string} claim_a_id
 * @param {string} claim_b_json
 * @param {string} claim_b_id
 * @param {bigint} now_unix_seconds
 * @param {string} weights_json
 * @returns {string}
 */
export function resolvePair(claim_a_json, claim_a_id, claim_b_json, claim_b_id, now_unix_seconds, weights_json) {
    let deferred7_0;
    let deferred7_1;
    try {
        const ptr0 = passStringToWasm0(claim_a_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(claim_a_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(claim_b_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        const ptr3 = passStringToWasm0(claim_b_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len3 = WASM_VECTOR_LEN;
        const ptr4 = passStringToWasm0(weights_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len4 = WASM_VECTOR_LEN;
        const ret = wasm.resolvePair(ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, now_unix_seconds, ptr4, len4);
        var ptr6 = ret[0];
        var len6 = ret[1];
        if (ret[3]) {
            ptr6 = 0; len6 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred7_0 = ptr6;
        deferred7_1 = len6;
        return getStringFromWasm0(ptr6, len6);
    } finally {
        wasm.__wbindgen_free(deferred7_0, deferred7_1, 1);
    }
}

/**
 * Orchestrate contradiction detection + resolution for a new claim against candidates.
 *
 * Returns a JSON array of `ResolutionAction`.
 * @param {string} new_claim_json
 * @param {string} new_claim_id
 * @param {string} new_embedding_json
 * @param {string} candidates_json
 * @param {string} weights_json
 * @param {number} threshold_lower
 * @param {number} threshold_upper
 * @param {bigint} now_unix
 * @param {number} tie_tolerance
 * @returns {string}
 */
export function resolveWithCandidates(new_claim_json, new_claim_id, new_embedding_json, candidates_json, weights_json, threshold_lower, threshold_upper, now_unix, tie_tolerance) {
    let deferred7_0;
    let deferred7_1;
    try {
        const ptr0 = passStringToWasm0(new_claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(new_claim_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(new_embedding_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        const ptr3 = passStringToWasm0(candidates_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len3 = WASM_VECTOR_LEN;
        const ptr4 = passStringToWasm0(weights_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len4 = WASM_VECTOR_LEN;
        const ret = wasm.resolveWithCandidates(ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, ptr4, len4, threshold_lower, threshold_upper, now_unix, tie_tolerance);
        var ptr6 = ret[0];
        var len6 = ret[1];
        if (ret[3]) {
            ptr6 = 0; len6 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred7_0 = ptr6;
        deferred7_1 = len6;
        return getStringFromWasm0(ptr6, len6);
    } finally {
        wasm.__wbindgen_free(deferred7_0, deferred7_1, 1);
    }
}

/**
 * Apply pin-status and tie-zone checks to a resolution outcome.
 * Returns a JSON-serialized `ResolutionAction`.
 * @param {string} existing_claim_json
 * @param {string} new_claim_id
 * @param {string} existing_claim_id
 * @param {string} resolution_winner
 * @param {number} score_gap
 * @param {number} similarity
 * @param {number} tie_tolerance
 * @returns {string}
 */
export function respectPinInResolution(existing_claim_json, new_claim_id, existing_claim_id, resolution_winner, score_gap, similarity, tie_tolerance) {
    let deferred6_0;
    let deferred6_1;
    try {
        const ptr0 = passStringToWasm0(existing_claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(new_claim_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ptr2 = passStringToWasm0(existing_claim_id, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len2 = WASM_VECTOR_LEN;
        const ptr3 = passStringToWasm0(resolution_winner, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len3 = WASM_VECTOR_LEN;
        const ret = wasm.respectPinInResolution(ptr0, len0, ptr1, len1, ptr2, len2, ptr3, len3, score_gap, similarity, tie_tolerance);
        var ptr5 = ret[0];
        var len5 = ret[1];
        if (ret[3]) {
            ptr5 = 0; len5 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred6_0 = ptr5;
        deferred6_1 = len5;
        return getStringFromWasm0(ptr5, len5);
    } finally {
        wasm.__wbindgen_free(deferred6_0, deferred6_1, 1);
    }
}

/**
 * Keep only the most recent `max_lines` non-empty feedback log lines. Non-falliable.
 * @param {string} content
 * @param {bigint} max_lines
 * @returns {string}
 */
export function rotateFeedbackLog(content, max_lines) {
    let deferred2_0;
    let deferred2_1;
    try {
        const ptr0 = passStringToWasm0(content, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.rotateFeedbackLog(ptr0, len0, max_lines);
        deferred2_0 = ret[0];
        deferred2_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred2_0, deferred2_1, 1);
    }
}

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
 * @param {string} timestamps_json
 * @param {string} embeddings_json
 * @param {number} gap_seconds
 * @param {number} sim_threshold
 * @returns {any}
 */
export function segmentSessions(timestamps_json, embeddings_json, gap_seconds, sim_threshold) {
    const ptr0 = passStringToWasm0(timestamps_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ptr1 = passStringToWasm0(embeddings_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len1 = WASM_VECTOR_LEN;
    const ret = wasm.segmentSessions(ptr0, len0, ptr1, len1, gap_seconds, sim_threshold);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return takeFromExternrefTable0(ret[0]);
}

/**
 * Serialize a WeightsFile JSON to pretty-printed JSON (2-space indent).
 * @param {string} file_json
 * @returns {string}
 */
export function serializeWeightsFile(file_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(file_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.serializeWeightsFile(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * WASM binding: determine if a new fact should supersede an existing one.
 * @param {number} new_importance
 * @param {number} existing_importance
 * @returns {boolean}
 */
export function shouldSupersede(new_importance, existing_importance) {
    const ret = wasm.shouldSupersede(new_importance, existing_importance);
    return ret !== 0;
}

/**
 * Sign a UserOp hash with an ECDSA private key (EIP-191 prefixed).
 *
 * `hash_hex`: 64-char hex string (32-byte UserOp hash).
 * `private_key_hex`: 64-char hex string (32-byte private key).
 * Returns 65-byte signature as hex string (r + s + v).
 * @param {string} hash_hex
 * @param {string} private_key_hex
 * @returns {string}
 */
export function signUserOp(hash_hex, private_key_hex) {
    let deferred4_0;
    let deferred4_1;
    try {
        const ptr0 = passStringToWasm0(hash_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ptr1 = passStringToWasm0(private_key_hex, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len1 = WASM_VECTOR_LEN;
        const ret = wasm.signUserOp(ptr0, len0, ptr1, len1);
        var ptr3 = ret[0];
        var len3 = ret[1];
        if (ret[3]) {
            ptr3 = 0; len3 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred4_0 = ptr3;
        deferred4_1 = len3;
        return getStringFromWasm0(ptr3, len3);
    } finally {
        wasm.__wbindgen_free(deferred4_0, deferred4_1, 1);
    }
}

/**
 * Return the source weight multiplier for a given source string.
 *
 * Accepted values: "user" | "user-inferred" | "assistant" | "external" | "derived".
 *
 * Unknown input is routed through `MemorySource::from_str_lossy` which
 * falls back to `user-inferred` (v2-lenient weight 0.95). Callers who need
 * the "no source field at all" fallback (weight 0.85) should call
 * `legacyClaimFallbackWeight()` instead.
 * @param {string} source
 * @returns {number}
 */
export function sourceWeight(source) {
    const ptr0 = passStringToWasm0(source, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.sourceWeight(ptr0, len0);
    return ret;
}

/**
 * Validate a Memory Taxonomy v1 claim (JSON in, JSON out — canonicalised).
 *
 * Returns the canonical JSON encoding on success. Throws on any schema
 * violation (wrong type token, missing required field, wrong schema_version).
 *
 * See `docs/specs/totalreclaw/memory-taxonomy-v1.md`.
 * @param {string} claim_json
 * @returns {string}
 */
export function validateMemoryClaimV1(claim_json) {
    let deferred3_0;
    let deferred3_1;
    try {
        const ptr0 = passStringToWasm0(claim_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
        const len0 = WASM_VECTOR_LEN;
        const ret = wasm.validateMemoryClaimV1(ptr0, len0);
        var ptr2 = ret[0];
        var len2 = ret[1];
        if (ret[3]) {
            ptr2 = 0; len2 = 0;
            throw takeFromExternrefTable0(ret[2]);
        }
        deferred3_0 = ptr2;
        deferred3_1 = len2;
        return getStringFromWasm0(ptr2, len2);
    } finally {
        wasm.__wbindgen_free(deferred3_0, deferred3_1, 1);
    }
}

/**
 * Default polling interval (ms) — exposed so host adapters share the same
 * default without re-declaring the constant.
 * @returns {number}
 */
export function wasmConfirmIndexedDefaultPollMs() {
    const ret = wasm.wasmConfirmIndexedDefaultPollMs();
    return ret >>> 0;
}

/**
 * Default total timeout (ms) — exposed so host adapters share the same default.
 * @returns {number}
 */
export function wasmConfirmIndexedDefaultTimeoutMs() {
    const ret = wasm.wasmConfirmIndexedDefaultTimeoutMs();
    return ret >>> 0;
}

/**
 * Parse a subgraph response JSON and return whether the fact is indexed +
 * active. Returns `true` when the read-after-write loop can stop.
 * @param {string} response_json
 * @returns {boolean}
 */
export function wasmConfirmIndexedParse(response_json) {
    const ptr0 = passStringToWasm0(response_json, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
    const len0 = WASM_VECTOR_LEN;
    const ret = wasm.wasmConfirmIndexedParse(ptr0, len0);
    if (ret[2]) {
        throw takeFromExternrefTable0(ret[1]);
    }
    return ret[0] !== 0;
}

/**
 * GraphQL query string used to confirm a fact id has been indexed.
 * Pair with `wasmConfirmIndexedParse` in a host-side polling loop.
 * @returns {string}
 */
export function wasmConfirmIndexedQuery() {
    let deferred1_0;
    let deferred1_1;
    try {
        const ret = wasm.wasmConfirmIndexedQuery();
        deferred1_0 = ret[0];
        deferred1_1 = ret[1];
        return getStringFromWasm0(ret[0], ret[1]);
    } finally {
        wasm.__wbindgen_free(deferred1_0, deferred1_1, 1);
    }
}

function __wbg_get_imports() {
    const import0 = {
        __proto__: null,
        __wbg_Error_2e59b1b37a9a34c3: function(arg0, arg1) {
            const ret = Error(getStringFromWasm0(arg0, arg1));
            return ret;
        },
        __wbg_String_8564e559799eccda: function(arg0, arg1) {
            const ret = String(arg1);
            const ptr1 = passStringToWasm0(ret, wasm.__wbindgen_malloc, wasm.__wbindgen_realloc);
            const len1 = WASM_VECTOR_LEN;
            getDataViewMemory0().setInt32(arg0 + 4 * 1, len1, true);
            getDataViewMemory0().setInt32(arg0 + 4 * 0, ptr1, true);
        },
        __wbg___wbindgen_is_function_49868bde5eb1e745: function(arg0) {
            const ret = typeof(arg0) === 'function';
            return ret;
        },
        __wbg___wbindgen_is_object_40c5a80572e8f9d3: function(arg0) {
            const val = arg0;
            const ret = typeof(val) === 'object' && val !== null;
            return ret;
        },
        __wbg___wbindgen_is_string_b29b5c5a8065ba1a: function(arg0) {
            const ret = typeof(arg0) === 'string';
            return ret;
        },
        __wbg___wbindgen_is_undefined_c0cca72b82b86f4d: function(arg0) {
            const ret = arg0 === undefined;
            return ret;
        },
        __wbg___wbindgen_throw_81fc77679af83bc6: function(arg0, arg1) {
            throw new Error(getStringFromWasm0(arg0, arg1));
        },
        __wbg_call_d578befcc3145dee: function() { return handleError(function (arg0, arg1, arg2) {
            const ret = arg0.call(arg1, arg2);
            return ret;
        }, arguments); },
        __wbg_crypto_38df2bab126b63dc: function(arg0) {
            const ret = arg0.crypto;
            return ret;
        },
        __wbg_getRandomValues_c44a50d8cfdaebeb: function() { return handleError(function (arg0, arg1) {
            arg0.getRandomValues(arg1);
        }, arguments); },
        __wbg_getRandomValues_d49329ff89a07af1: function() { return handleError(function (arg0, arg1) {
            globalThis.crypto.getRandomValues(getArrayU8FromWasm0(arg0, arg1));
        }, arguments); },
        __wbg_getTime_f6ac312467f7cf09: function(arg0) {
            const ret = arg0.getTime();
            return ret;
        },
        __wbg_length_0c32cb8543c8e4c8: function(arg0) {
            const ret = arg0.length;
            return ret;
        },
        __wbg_msCrypto_bd5a034af96bcba6: function(arg0) {
            const ret = arg0.msCrypto;
            return ret;
        },
        __wbg_new_0_bfa2ef4bc447daa2: function() {
            const ret = new Date();
            return ret;
        },
        __wbg_new_4f9fafbb3909af72: function() {
            const ret = new Object();
            return ret;
        },
        __wbg_new_f3c9df4f38f3f798: function() {
            const ret = new Array();
            return ret;
        },
        __wbg_new_with_length_9cedd08484b73942: function(arg0) {
            const ret = new Uint8Array(arg0 >>> 0);
            return ret;
        },
        __wbg_node_84ea875411254db1: function(arg0) {
            const ret = arg0.node;
            return ret;
        },
        __wbg_now_6798946be0e6fe2b: function() { return handleError(function () {
            const ret = Date.now();
            return ret;
        }, arguments); },
        __wbg_process_44c7a14e11e9f69e: function(arg0) {
            const ret = arg0.process;
            return ret;
        },
        __wbg_prototypesetcall_3e05eb9545565046: function(arg0, arg1, arg2) {
            Uint8Array.prototype.set.call(getArrayU8FromWasm0(arg0, arg1), arg2);
        },
        __wbg_randomFillSync_6c25eac9869eb53c: function() { return handleError(function (arg0, arg1) {
            arg0.randomFillSync(arg1);
        }, arguments); },
        __wbg_require_b4edbdcf3e2a1ef0: function() { return handleError(function () {
            const ret = module.require;
            return ret;
        }, arguments); },
        __wbg_set_6be42768c690e380: function(arg0, arg1, arg2) {
            arg0[arg1] = arg2;
        },
        __wbg_set_6c60b2e8ad0e9383: function(arg0, arg1, arg2) {
            arg0[arg1 >>> 0] = arg2;
        },
        __wbg_set_8ee2d34facb8466e: function() { return handleError(function (arg0, arg1, arg2) {
            const ret = Reflect.set(arg0, arg1, arg2);
            return ret;
        }, arguments); },
        __wbg_static_accessor_GLOBAL_THIS_a1248013d790bf5f: function() {
            const ret = typeof globalThis === 'undefined' ? null : globalThis;
            return isLikeNone(ret) ? 0 : addToExternrefTable0(ret);
        },
        __wbg_static_accessor_GLOBAL_f2e0f995a21329ff: function() {
            const ret = typeof global === 'undefined' ? null : global;
            return isLikeNone(ret) ? 0 : addToExternrefTable0(ret);
        },
        __wbg_static_accessor_SELF_24f78b6d23f286ea: function() {
            const ret = typeof self === 'undefined' ? null : self;
            return isLikeNone(ret) ? 0 : addToExternrefTable0(ret);
        },
        __wbg_static_accessor_WINDOW_59fd959c540fe405: function() {
            const ret = typeof window === 'undefined' ? null : window;
            return isLikeNone(ret) ? 0 : addToExternrefTable0(ret);
        },
        __wbg_subarray_0f98d3fb634508ad: function(arg0, arg1, arg2) {
            const ret = arg0.subarray(arg1 >>> 0, arg2 >>> 0);
            return ret;
        },
        __wbg_versions_276b2795b1c6a219: function(arg0) {
            const ret = arg0.versions;
            return ret;
        },
        __wbindgen_cast_0000000000000001: function(arg0) {
            // Cast intrinsic for `F64 -> Externref`.
            const ret = arg0;
            return ret;
        },
        __wbindgen_cast_0000000000000002: function(arg0) {
            // Cast intrinsic for `I64 -> Externref`.
            const ret = arg0;
            return ret;
        },
        __wbindgen_cast_0000000000000003: function(arg0, arg1) {
            // Cast intrinsic for `Ref(Slice(U8)) -> NamedExternref("Uint8Array")`.
            const ret = getArrayU8FromWasm0(arg0, arg1);
            return ret;
        },
        __wbindgen_cast_0000000000000004: function(arg0, arg1) {
            // Cast intrinsic for `Ref(String) -> Externref`.
            const ret = getStringFromWasm0(arg0, arg1);
            return ret;
        },
        __wbindgen_cast_0000000000000005: function(arg0) {
            // Cast intrinsic for `U64 -> Externref`.
            const ret = BigInt.asUintN(64, arg0);
            return ret;
        },
        __wbindgen_init_externref_table: function() {
            const table = wasm.__wbindgen_externrefs;
            const offset = table.grow(4);
            table.set(0, undefined);
            table.set(offset + 0, undefined);
            table.set(offset + 1, null);
            table.set(offset + 2, true);
            table.set(offset + 3, false);
        },
    };
    return {
        __proto__: null,
        "./totalreclaw_core_bg.js": import0,
    };
}

const WasmLshHasherFinalization = (typeof FinalizationRegistry === 'undefined')
    ? { register: () => {}, unregister: () => {} }
    : new FinalizationRegistry(ptr => wasm.__wbg_wasmlshhasher_free(ptr >>> 0, 1));

function addToExternrefTable0(obj) {
    const idx = wasm.__externref_table_alloc();
    wasm.__wbindgen_externrefs.set(idx, obj);
    return idx;
}

function _assertClass(instance, klass) {
    if (!(instance instanceof klass)) {
        throw new Error(`expected instance of ${klass.name}`);
    }
}

function getArrayU8FromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return getUint8ArrayMemory0().subarray(ptr / 1, ptr / 1 + len);
}

let cachedDataViewMemory0 = null;
function getDataViewMemory0() {
    if (cachedDataViewMemory0 === null || cachedDataViewMemory0.buffer.detached === true || (cachedDataViewMemory0.buffer.detached === undefined && cachedDataViewMemory0.buffer !== wasm.memory.buffer)) {
        cachedDataViewMemory0 = new DataView(wasm.memory.buffer);
    }
    return cachedDataViewMemory0;
}

let cachedFloat32ArrayMemory0 = null;
function getFloat32ArrayMemory0() {
    if (cachedFloat32ArrayMemory0 === null || cachedFloat32ArrayMemory0.byteLength === 0) {
        cachedFloat32ArrayMemory0 = new Float32Array(wasm.memory.buffer);
    }
    return cachedFloat32ArrayMemory0;
}

let cachedFloat64ArrayMemory0 = null;
function getFloat64ArrayMemory0() {
    if (cachedFloat64ArrayMemory0 === null || cachedFloat64ArrayMemory0.byteLength === 0) {
        cachedFloat64ArrayMemory0 = new Float64Array(wasm.memory.buffer);
    }
    return cachedFloat64ArrayMemory0;
}

function getStringFromWasm0(ptr, len) {
    ptr = ptr >>> 0;
    return decodeText(ptr, len);
}

let cachedUint8ArrayMemory0 = null;
function getUint8ArrayMemory0() {
    if (cachedUint8ArrayMemory0 === null || cachedUint8ArrayMemory0.byteLength === 0) {
        cachedUint8ArrayMemory0 = new Uint8Array(wasm.memory.buffer);
    }
    return cachedUint8ArrayMemory0;
}

function handleError(f, args) {
    try {
        return f.apply(this, args);
    } catch (e) {
        const idx = addToExternrefTable0(e);
        wasm.__wbindgen_exn_store(idx);
    }
}

function isLikeNone(x) {
    return x === undefined || x === null;
}

function passArray8ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 1, 1) >>> 0;
    getUint8ArrayMemory0().set(arg, ptr / 1);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passArrayF32ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 4, 4) >>> 0;
    getFloat32ArrayMemory0().set(arg, ptr / 4);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passArrayF64ToWasm0(arg, malloc) {
    const ptr = malloc(arg.length * 8, 8) >>> 0;
    getFloat64ArrayMemory0().set(arg, ptr / 8);
    WASM_VECTOR_LEN = arg.length;
    return ptr;
}

function passStringToWasm0(arg, malloc, realloc) {
    if (realloc === undefined) {
        const buf = cachedTextEncoder.encode(arg);
        const ptr = malloc(buf.length, 1) >>> 0;
        getUint8ArrayMemory0().subarray(ptr, ptr + buf.length).set(buf);
        WASM_VECTOR_LEN = buf.length;
        return ptr;
    }

    let len = arg.length;
    let ptr = malloc(len, 1) >>> 0;

    const mem = getUint8ArrayMemory0();

    let offset = 0;

    for (; offset < len; offset++) {
        const code = arg.charCodeAt(offset);
        if (code > 0x7F) break;
        mem[ptr + offset] = code;
    }
    if (offset !== len) {
        if (offset !== 0) {
            arg = arg.slice(offset);
        }
        ptr = realloc(ptr, len, len = offset + arg.length * 3, 1) >>> 0;
        const view = getUint8ArrayMemory0().subarray(ptr + offset, ptr + len);
        const ret = cachedTextEncoder.encodeInto(arg, view);

        offset += ret.written;
        ptr = realloc(ptr, len, offset, 1) >>> 0;
    }

    WASM_VECTOR_LEN = offset;
    return ptr;
}

function takeFromExternrefTable0(idx) {
    const value = wasm.__wbindgen_externrefs.get(idx);
    wasm.__externref_table_dealloc(idx);
    return value;
}

let cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
cachedTextDecoder.decode();
const MAX_SAFARI_DECODE_BYTES = 2146435072;
let numBytesDecoded = 0;
function decodeText(ptr, len) {
    numBytesDecoded += len;
    if (numBytesDecoded >= MAX_SAFARI_DECODE_BYTES) {
        cachedTextDecoder = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
        cachedTextDecoder.decode();
        numBytesDecoded = len;
    }
    return cachedTextDecoder.decode(getUint8ArrayMemory0().subarray(ptr, ptr + len));
}

const cachedTextEncoder = new TextEncoder();

if (!('encodeInto' in cachedTextEncoder)) {
    cachedTextEncoder.encodeInto = function (arg, view) {
        const buf = cachedTextEncoder.encode(arg);
        view.set(buf);
        return {
            read: arg.length,
            written: buf.length
        };
    };
}

let WASM_VECTOR_LEN = 0;

let wasmModule, wasm;
function __wbg_finalize_init(instance, module) {
    wasm = instance.exports;
    wasmModule = module;
    cachedDataViewMemory0 = null;
    cachedFloat32ArrayMemory0 = null;
    cachedFloat64ArrayMemory0 = null;
    cachedUint8ArrayMemory0 = null;
    wasm.__wbindgen_start();
    return wasm;
}

async function __wbg_load(module, imports) {
    if (typeof Response === 'function' && module instanceof Response) {
        if (typeof WebAssembly.instantiateStreaming === 'function') {
            try {
                return await WebAssembly.instantiateStreaming(module, imports);
            } catch (e) {
                const validResponse = module.ok && expectedResponseType(module.type);

                if (validResponse && module.headers.get('Content-Type') !== 'application/wasm') {
                    console.warn("`WebAssembly.instantiateStreaming` failed because your server does not serve Wasm with `application/wasm` MIME type. Falling back to `WebAssembly.instantiate` which is slower. Original error:\n", e);

                } else { throw e; }
            }
        }

        const bytes = await module.arrayBuffer();
        return await WebAssembly.instantiate(bytes, imports);
    } else {
        const instance = await WebAssembly.instantiate(module, imports);

        if (instance instanceof WebAssembly.Instance) {
            return { instance, module };
        } else {
            return instance;
        }
    }

    function expectedResponseType(type) {
        switch (type) {
            case 'basic': case 'cors': case 'default': return true;
        }
        return false;
    }
}

function initSync(module) {
    if (wasm !== undefined) return wasm;


    if (module !== undefined) {
        if (Object.getPrototypeOf(module) === Object.prototype) {
            ({module} = module)
        } else {
            console.warn('using deprecated parameters for `initSync()`; pass a single object instead')
        }
    }

    const imports = __wbg_get_imports();
    if (!(module instanceof WebAssembly.Module)) {
        module = new WebAssembly.Module(module);
    }
    const instance = new WebAssembly.Instance(module, imports);
    return __wbg_finalize_init(instance, module);
}

async function __wbg_init(module_or_path) {
    if (wasm !== undefined) return wasm;


    if (module_or_path !== undefined) {
        if (Object.getPrototypeOf(module_or_path) === Object.prototype) {
            ({module_or_path} = module_or_path)
        } else {
            console.warn('using deprecated parameters for the initialization function; pass a single object instead')
        }
    }

    if (module_or_path === undefined) {
        module_or_path = new URL('totalreclaw_core_bg.wasm', import.meta.url);
    }
    const imports = __wbg_get_imports();

    if (typeof module_or_path === 'string' || (typeof Request === 'function' && module_or_path instanceof Request) || (typeof URL === 'function' && module_or_path instanceof URL)) {
        module_or_path = fetch(module_or_path);
    }

    const { instance, module } = await __wbg_load(await module_or_path, imports);

    return __wbg_finalize_init(instance, module);
}

export { initSync, __wbg_init as default };
