//! Canonical LLM system prompts used by the extraction pipeline.
//!
//! This module hoists two prompts that were historically duplicated (and
//! drifted) across every client package:
//!
//! - `EXTRACTION_SYSTEM_PROMPT` — post-turn extraction prompt (importance
//!   floor 6).
//! - `COMPACTION_SYSTEM_PROMPT` — compaction extraction prompt (importance
//!   floor 5; "last-chance" wording).
//!
//! # Canonical text sources
//!
//! The prompt bodies live in readable Markdown files alongside this module:
//!
//! - [`prompts/extraction.md`](./prompts/extraction.md)
//! - [`prompts/compaction.md`](./prompts/compaction.md)
//!
//! They are pulled into the compiled artifact with `include_str!` so there
//! is no runtime file dependency — the WASM / PyO3 / native binaries all
//! ship the text inline. Recompiling is required to iterate on the prompt,
//! which is desirable here: every client must update in lockstep and the
//! core version bump is the forcing function for that.
//!
//! # Rationale — why was this hoisted?
//!
//! Before this module, each client kept its own copy:
//!
//! - `skill/plugin/extractor.ts::EXTRACTION_SYSTEM_PROMPT`
//! - `skill/plugin/extractor.ts::COMPACTION_SYSTEM_PROMPT`
//! - `python/src/totalreclaw/agent/extraction.py::EXTRACTION_SYSTEM_PROMPT`
//! - `python/src/totalreclaw/agent/extraction.py::COMPACTION_SYSTEM_PROMPT`
//! - `skill-nanoclaw/src/extraction/prompts.ts::BASE_SYSTEM_PROMPT`
//!
//! The three TypeScript copies and one Python copy drifted in real ways
//! between 2026-04-17 and 2026-04-19 — for example, the Python copy
//! acquired a "Rule 6: do not extract product-meta requests" after PR #34
//! (`ed289aa`) that never landed in TypeScript. That asymmetry shipped in
//! OpenClaw / NanoClaw and surfaced during v1.0 QA as spurious "setup
//! TotalReclaw" memories. The hoist in this module bakes Rule 6 into the
//! canonical text so every downstream client picks it up on the next
//! package bump.
//!
//! # Canonical shape
//!
//! - Plugin/Python topic-then-facts phased shape (PHASE 1 / PHASE 2).
//! - Rule 6 meta-request filter included (bug fix from PR #34).
//! - `ADD`-only output schema. Legacy `UPDATE` / `DELETE` / `NOOP` actions
//!   are intentionally dropped — the in-process contradiction resolver
//!   (see `consolidation` + `contradiction` modules) handles lifecycle
//!   transitions after extraction, so the LLM is no longer asked to emit
//!   them. NanoClaw historically emitted `UPDATE`/`DELETE`/`NOOP` but the
//!   dominant extraction path (`agent-end.ts:108`) silently dropped them
//!   anyway; aligning to `ADD`-only here removes the dead surface.
//! - Compaction prompt keeps its distinct preamble, lower importance floor,
//!   and "FORMAT-AGNOSTIC PARSING" section for non-turn inputs.
//!
//! # Exports
//!
//! - [`get_extraction_system_prompt`] — `&'static str` to the turn prompt.
//! - [`get_compaction_system_prompt`] — `&'static str` to the compaction
//!   prompt.
//! - WASM: `getExtractionSystemPrompt()` / `getCompactionSystemPrompt()`
//! - PyO3: `get_extraction_system_prompt()` / `get_compaction_system_prompt()`

// ---------------------------------------------------------------------------
// Core constants
// ---------------------------------------------------------------------------

/// Canonical post-turn extraction system prompt.
///
/// Importance floor 6. Use with the plugin's post-turn extractor path and
/// Python's `agent.extraction` pipeline. Compaction uses a distinct prompt
/// — see [`COMPACTION_SYSTEM_PROMPT`].
pub const EXTRACTION_SYSTEM_PROMPT: &str = include_str!("prompts/extraction.md");

/// Canonical compaction system prompt.
///
/// Importance floor 5 (one below turn-extraction). Sent when a conversation
/// is about to be compacted and the remaining context would be lost. Adds
/// a "FORMAT-AGNOSTIC PARSING" section to handle summary / bullet / code
/// inputs that differ from raw turn transcripts.
pub const COMPACTION_SYSTEM_PROMPT: &str = include_str!("prompts/compaction.md");

// ---------------------------------------------------------------------------
// Native Rust accessors
// ---------------------------------------------------------------------------

/// Return the canonical extraction system prompt as a static string.
///
/// Equivalent to reading [`EXTRACTION_SYSTEM_PROMPT`] directly. Provided as
/// a function so the WASM and PyO3 bindings have a symmetric surface
/// (`getExtractionSystemPrompt()` in JS, `get_extraction_system_prompt()`
/// in Python, `get_extraction_system_prompt()` in Rust).
pub fn get_extraction_system_prompt() -> &'static str {
    EXTRACTION_SYSTEM_PROMPT
}

/// Return the canonical compaction system prompt as a static string.
///
/// See [`COMPACTION_SYSTEM_PROMPT`].
pub fn get_compaction_system_prompt() -> &'static str {
    COMPACTION_SYSTEM_PROMPT
}

// ---------------------------------------------------------------------------
// WASM bindings (feature-gated)
// ---------------------------------------------------------------------------

#[cfg(feature = "wasm")]
mod wasm_bindings {
    use super::{COMPACTION_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT};
    use wasm_bindgen::prelude::*;

    /// Canonical post-turn extraction system prompt.
    ///
    /// TypeScript / JavaScript callers should prefer this over any
    /// in-package constant. The string is baked into the WASM binary at
    /// compile time so there is no runtime I/O.
    #[wasm_bindgen(js_name = "getExtractionSystemPrompt")]
    pub fn wasm_get_extraction_system_prompt() -> String {
        EXTRACTION_SYSTEM_PROMPT.to_string()
    }

    /// Canonical compaction system prompt.
    ///
    /// Same rationale as `getExtractionSystemPrompt`. The prompt body
    /// differs materially (lower importance floor, "last-chance" wording,
    /// format-agnostic parsing section) so callers must not substitute one
    /// for the other.
    #[wasm_bindgen(js_name = "getCompactionSystemPrompt")]
    pub fn wasm_get_compaction_system_prompt() -> String {
        COMPACTION_SYSTEM_PROMPT.to_string()
    }
}

// ---------------------------------------------------------------------------
// Python (PyO3) bindings (feature-gated)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod python_bindings {
    use super::{COMPACTION_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT};
    use pyo3::prelude::*;

    /// Canonical post-turn extraction system prompt.
    ///
    /// Python callers should prefer this over any in-package constant.
    #[pyfunction]
    fn get_extraction_system_prompt() -> &'static str {
        EXTRACTION_SYSTEM_PROMPT
    }

    /// Canonical compaction system prompt.
    #[pyfunction]
    fn get_compaction_system_prompt() -> &'static str {
        COMPACTION_SYSTEM_PROMPT
    }

    pub fn register_python_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(get_extraction_system_prompt, m)?)?;
        m.add_function(wrap_pyfunction!(get_compaction_system_prompt, m)?)?;
        Ok(())
    }
}

#[cfg(feature = "python")]
pub use python_bindings::register_python_functions;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extraction_prompt_non_empty() {
        let p = get_extraction_system_prompt();
        assert!(!p.is_empty(), "extraction prompt must not be empty");
        assert!(
            p.len() > 1_000,
            "extraction prompt looks suspiciously short: {} chars",
            p.len()
        );
    }

    #[test]
    fn compaction_prompt_non_empty() {
        let p = get_compaction_system_prompt();
        assert!(!p.is_empty(), "compaction prompt must not be empty");
        assert!(
            p.len() > 1_000,
            "compaction prompt looks suspiciously short: {} chars",
            p.len()
        );
    }

    #[test]
    fn prompts_are_distinct() {
        // The two prompts MUST differ — compaction has a lower importance
        // floor + last-chance preamble + FORMAT-AGNOSTIC PARSING section.
        // Confusing the two would silently cripple one of the pipelines.
        assert_ne!(
            get_extraction_system_prompt(),
            get_compaction_system_prompt()
        );
    }

    #[test]
    fn prompts_are_stable_across_invocations() {
        // Hoisted prompts should be pointer-identical (static) across
        // calls. Callers that cache the string must not observe drift.
        let a1 = get_extraction_system_prompt();
        let a2 = get_extraction_system_prompt();
        assert_eq!(a1.as_ptr(), a2.as_ptr(), "extraction prompt ptr drifted");

        let c1 = get_compaction_system_prompt();
        let c2 = get_compaction_system_prompt();
        assert_eq!(c1.as_ptr(), c2.as_ptr(), "compaction prompt ptr drifted");
    }

    #[test]
    fn extraction_prompt_contains_v1_taxonomy_markers() {
        // Canary tests for the core structural elements of the v1 prompt.
        // If one of these markers disappears the prompt has silently
        // regressed and extraction will skew.
        let p = get_extraction_system_prompt();
        assert!(p.contains("Memory Taxonomy v1"), "missing v1 header");
        assert!(
            p.contains("PHASE 1 — Topic identification"),
            "missing PHASE 1 header"
        );
        assert!(
            p.contains("PHASE 2 — Fact extraction"),
            "missing PHASE 2 header"
        );
    }

    #[test]
    fn extraction_prompt_contains_rule_6_meta_filter() {
        // Rule 6 is the PR #34 meta-request filter — the bug fix that was
        // in Python but missing from TypeScript pre-hoist. Lock the
        // canonical text so a future edit can't silently drop it.
        let p = get_extraction_system_prompt();
        assert!(
            p.contains("DO NOT extract setup / configuration / installation"),
            "rule 6 meta-request filter missing from extraction prompt"
        );
        assert!(
            p.contains("set up TotalReclaw"),
            "rule 6 example utterance missing"
        );
    }

    #[test]
    fn compaction_prompt_contains_rule_6_meta_filter() {
        let p = get_compaction_system_prompt();
        assert!(
            p.contains("DO NOT extract setup / configuration / installation"),
            "rule 6 meta-request filter missing from compaction prompt"
        );
    }

    #[test]
    fn extraction_prompt_is_add_only() {
        // The canonical shape is ADD-only; the legacy UPDATE/DELETE/NOOP
        // actions are intentionally absent. Guard against their
        // accidental reintroduction — those tokens must NOT appear in the
        // emitted JSON schema examples (inline code inside an action
        // enumeration).
        let p = get_extraction_system_prompt();
        assert!(
            !p.contains("ADD|UPDATE|DELETE|NOOP"),
            "legacy UPDATE|DELETE|NOOP union leaked back into extraction prompt"
        );
        assert!(
            p.contains("\"action\": \"ADD\""),
            "extraction prompt missing ADD-only action example"
        );
    }

    #[test]
    fn compaction_prompt_is_add_only() {
        let p = get_compaction_system_prompt();
        assert!(
            !p.contains("ADD|UPDATE|DELETE|NOOP"),
            "legacy UPDATE|DELETE|NOOP union leaked back into compaction prompt"
        );
        assert!(
            p.contains("\"action\": \"ADD\""),
            "compaction prompt missing ADD-only action example"
        );
    }

    #[test]
    fn compaction_prompt_has_format_agnostic_section() {
        // The compaction-specific "FORMAT-AGNOSTIC PARSING" section is
        // what tells the LLM to treat bullets / prose / code equally.
        // Distinguishes compaction from turn-extraction.
        let p = get_compaction_system_prompt();
        assert!(
            p.contains("FORMAT-AGNOSTIC PARSING"),
            "compaction prompt missing FORMAT-AGNOSTIC PARSING section"
        );
    }

    #[test]
    fn compaction_prompt_has_lower_importance_floor_language() {
        // Compaction accepts importance >= 5 (one below turn-extraction).
        // The prompt must say so explicitly.
        let p = get_compaction_system_prompt();
        assert!(
            p.contains("5+ = worth storing during compaction"),
            "compaction prompt missing floor-5 wording"
        );
    }
}
