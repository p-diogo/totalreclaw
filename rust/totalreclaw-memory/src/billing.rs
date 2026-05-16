//! Billing cache with 2-hour TTL and feature flags parsing.
//!
//! Matches the TypeScript plugin's billing cache (`~/.totalreclaw/billing-cache.json`).
//!
//! Feature flags from the relay's `GET /v1/billing/status` response drive:
//! - Extraction interval (`extraction_interval`)
//! - Max facts per extraction (`max_facts_per_extraction`)
//! - Max candidate pool size (`max_candidate_pool`)
//! - LLM dedup kill-switch (`llm_dedup`)

use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::relay::RelayClient;
use crate::Result;

/// Billing cache TTL: 2 hours (7200 seconds), matching all other clients.
const BILLING_CACHE_TTL_SECS: u64 = 7200;

/// Quota warning threshold: 80%.
const QUOTA_WARNING_THRESHOLD: f64 = 0.80;

/// Default extraction interval (turns).
const DEFAULT_EXTRACTION_INTERVAL: u32 = 3;

/// Default max facts per extraction.
const DEFAULT_MAX_FACTS_PER_EXTRACTION: u32 = 15;

/// Default candidate pool size (free tier).
const DEFAULT_CANDIDATE_POOL_FREE: usize = 100;

/// Default candidate pool size (pro tier).
const DEFAULT_CANDIDATE_POOL_PRO: usize = 250;

// ---------------------------------------------------------------------------
// Feature flags (from relay billing response)
// ---------------------------------------------------------------------------

/// Feature flags parsed from the billing status response.
///
/// The relay returns these in the `features` JSON blob on the billing
/// status endpoint. Clients consult them at the call-site when resolving
/// tuning knobs; env-var fallbacks are retained for self-hosted deployments.
///
/// See `docs/guides/env-vars-reference.md` — as of the v1 env var cleanup,
/// managed-service clients read tuning knobs from this struct and never
/// from env vars.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FeatureFlags {
    pub llm_dedup: Option<bool>,
    pub extraction_interval: Option<u32>,
    pub max_facts_per_extraction: Option<u32>,
    pub max_candidate_pool: Option<usize>,
    pub custom_extract_interval: Option<bool>,
    pub min_extract_interval: Option<u32>,

    // Tuning knobs moved to server-side delivery in the v1 env cleanup.
    // Optional — when absent, clients fall back to their built-in defaults
    // (or their self-hosted env-var overrides).
    pub cosine_threshold: Option<f64>,
    pub relevance_threshold: Option<f64>,
    pub semantic_skip_threshold: Option<f64>,
    pub min_importance: Option<u32>,
    pub cache_ttl_ms: Option<u64>,
    pub trapdoor_batch_size: Option<usize>,
    pub subgraph_page_size: Option<usize>,
}

// ---------------------------------------------------------------------------
// Billing cache entry (persisted to disk)
// ---------------------------------------------------------------------------

/// Cached billing status, matching the TypeScript `BillingCache` interface.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BillingCache {
    pub tier: String,
    pub facts_used: u64,
    pub facts_limit: u64,
    #[serde(default)]
    pub features: FeatureFlags,
    /// Unix epoch millis when this cache was written.
    pub checked_at: u64,
    /// "monthly" or "lifetime". Defaults to "monthly" on the free tier so
    /// older relays that don't yet emit the field still give an
    /// unambiguous signal.
    #[serde(default)]
    pub period: Option<String>,
    /// ISO 8601 timestamp of the next monthly reset.
    #[serde(default)]
    pub resets_at: Option<String>,
    /// "production" or "staging". Surface staging-specific notes ONLY
    /// when this is "staging" — production users should see no mention
    /// of staging.
    #[serde(default)]
    pub environment: Option<String>,
}

/// Staging caveat text — kept as a constant so the prose is identical
/// across all clients and tests can assert on it.
pub const STAGING_NOTE: &str = "You are on the staging relay (api-staging.totalreclaw.xyz). The free-tier quota is NOT enforced here — writes will succeed past the listed limit. Production (api.totalreclaw.xyz) enforces the 250 writes/month cap.";

impl BillingCache {
    /// Whether this cache entry is still valid (within TTL).
    pub fn is_fresh(&self) -> bool {
        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        now_ms.saturating_sub(self.checked_at) < BILLING_CACHE_TTL_SECS * 1000
    }

    /// Quota usage as a fraction (0.0 to 1.0).
    pub fn quota_fraction(&self) -> f64 {
        if self.facts_limit == 0 {
            return 0.0;
        }
        self.facts_used as f64 / self.facts_limit as f64
    }

    /// Whether the user is above the 80% quota warning threshold.
    ///
    /// Returns `false` on staging — the cap isn't enforced there, so
    /// surfacing an "approaching limit" warning would be a lie that
    /// nudges QA toward a fake upgrade.
    pub fn is_quota_warning(&self) -> bool {
        if self.is_staging() {
            return false;
        }
        self.quota_fraction() > QUOTA_WARNING_THRESHOLD
    }

    /// Human-readable quota warning message (or None if under threshold
    /// or on staging).
    pub fn quota_warning_message(&self) -> Option<String> {
        if !self.is_quota_warning() {
            return None;
        }
        let pct = (self.quota_fraction() * 100.0).round() as u32;
        Some(format!(
            "Memory usage at {}% ({}/{} memories). Upgrade to Pro for unlimited storage.",
            pct, self.facts_used, self.facts_limit
        ))
    }

    /// Is this a Pro tier user?
    pub fn is_pro(&self) -> bool {
        self.tier == "pro"
    }

    /// Is this cache from the staging relay?
    pub fn is_staging(&self) -> bool {
        matches!(self.environment.as_deref(), Some("staging"))
    }

    /// Staging caveat text — `Some` only when on staging. Production
    /// callers must never surface a staging mention.
    pub fn staging_note(&self) -> Option<&'static str> {
        if self.is_staging() { Some(STAGING_NOTE) } else { None }
    }
}

// ---------------------------------------------------------------------------
// Disk persistence
// ---------------------------------------------------------------------------

/// Get the billing cache file path (`~/.totalreclaw/billing-cache.json`).
fn cache_path() -> PathBuf {
    crate::setup::config_dir().join("billing-cache.json")
}

/// Read the billing cache from disk. Returns `None` if missing, expired, or corrupt.
pub fn read_cache() -> Option<BillingCache> {
    let path = cache_path();
    let data = std::fs::read_to_string(&path).ok()?;
    let cache: BillingCache = serde_json::from_str(&data).ok()?;
    if cache.is_fresh() {
        Some(cache)
    } else {
        None
    }
}

/// Write the billing cache to disk. Best-effort (does not error on failure).
pub fn write_cache(cache: &BillingCache) {
    let dir = crate::setup::config_dir();
    let _ = std::fs::create_dir_all(&dir);
    let path = cache_path();
    if let Ok(data) = serde_json::to_string(cache) {
        let _ = std::fs::write(&path, data);
    }
}

/// Invalidate (delete) the billing cache. Used on 403 responses.
pub fn invalidate_cache() {
    let _ = std::fs::remove_file(cache_path());
}

// ---------------------------------------------------------------------------
// Fetch + cache from relay
// ---------------------------------------------------------------------------

/// Fetch billing status from the relay server, update the local cache, and return it.
///
/// If the cache is fresh, returns the cached value without a network call.
pub async fn fetch_billing_status(relay: &RelayClient) -> Result<BillingCache> {
    // Return cached if fresh
    if let Some(cached) = read_cache() {
        return Ok(cached);
    }

    // Fetch from relay
    let status = relay.billing_status().await?;

    // Parse feature flags from the `features` JSON blob
    let features: FeatureFlags = status
        .features
        .and_then(|v| serde_json::from_value(v).ok())
        .unwrap_or_default();

    let now_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;

    let tier = status.tier.unwrap_or_else(|| "free".into());
    // Default the free-tier period to "monthly" so older relays that
    // don't yet emit the field still give the agent an unambiguous answer.
    let period = status.period.or_else(|| {
        if tier == "free" { Some("monthly".to_string()) } else { None }
    });
    let cache = BillingCache {
        tier,
        facts_used: status.facts_used.unwrap_or(0),
        // Production free-tier cap is 250/month. The relay should always
        // populate ``facts_limit``; 250 is the fallback if it doesn't.
        facts_limit: status.facts_limit.unwrap_or(250),
        features,
        checked_at: now_ms,
        period,
        resets_at: status.resets_at,
        environment: status.environment,
    };

    write_cache(&cache);
    Ok(cache)
}

// ---------------------------------------------------------------------------
// Feature flag accessors (with env overrides + defaults)
// ---------------------------------------------------------------------------

/// Get the effective extraction interval.
///
/// Priority: server-side config (from billing cache) > env var > default (3).
pub fn get_extraction_interval(cache: Option<&BillingCache>) -> u32 {
    if let Some(c) = cache {
        if let Some(interval) = c.features.extraction_interval {
            return interval;
        }
    }
    std::env::var("TOTALRECLAW_EXTRACT_INTERVAL")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_EXTRACTION_INTERVAL)
}

/// Get the max facts per extraction.
///
/// Priority: server-side config > default (15).
pub fn get_max_facts_per_extraction(cache: Option<&BillingCache>) -> u32 {
    if let Some(c) = cache {
        if let Some(max) = c.features.max_facts_per_extraction {
            return max;
        }
    }
    DEFAULT_MAX_FACTS_PER_EXTRACTION
}

/// Get the max candidate pool size for search.
///
/// Priority: server-side config > env var > tier default.
pub fn get_max_candidate_pool(cache: Option<&BillingCache>) -> usize {
    // Server-side value first
    if let Some(c) = cache {
        if let Some(pool) = c.features.max_candidate_pool {
            return pool;
        }
    }

    // Env overrides
    let is_pro = cache.map_or(false, |c| c.is_pro());
    if is_pro {
        std::env::var("CANDIDATE_POOL_MAX_PRO")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_CANDIDATE_POOL_PRO)
    } else {
        std::env::var("CANDIDATE_POOL_MAX_FREE")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_CANDIDATE_POOL_FREE)
    }
}

/// Whether LLM-guided dedup is enabled.
///
/// Always true unless the server explicitly sets `llm_dedup: false` (kill-switch).
pub fn is_llm_dedup_enabled(cache: Option<&BillingCache>) -> bool {
    if let Some(c) = cache {
        if c.features.llm_dedup == Some(false) {
            return false;
        }
    }
    true
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_billing_cache_fresh() {
        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;

        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 100,
            facts_limit: 500,
            features: FeatureFlags::default(),
            checked_at: now_ms,
            ..Default::default()
        };
        assert!(cache.is_fresh());

        // Expired cache (3 hours ago)
        let expired = BillingCache {
            checked_at: now_ms - 3 * 60 * 60 * 1000,
            ..cache.clone()
        };
        assert!(!expired.is_fresh());
    }

    #[test]
    fn test_quota_fraction() {
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 420,
            facts_limit: 500,
            features: FeatureFlags::default(),
            checked_at: 0,
            ..Default::default()
        };
        assert!((cache.quota_fraction() - 0.84).abs() < 0.01);
        assert!(cache.is_quota_warning());

        let low_usage = BillingCache {
            facts_used: 100,
            ..cache
        };
        assert!(!low_usage.is_quota_warning());
    }

    #[test]
    fn test_quota_warning_message() {
        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 450,
            facts_limit: 500,
            features: FeatureFlags::default(),
            checked_at: now_ms,
            ..Default::default()
        };
        let msg = cache.quota_warning_message();
        assert!(msg.is_some());
        assert!(msg.unwrap().contains("90%"));
    }

    #[test]
    fn test_feature_flags_extraction_interval() {
        let cache = BillingCache {
            tier: "pro".into(),
            facts_used: 0,
            facts_limit: 0,
            features: FeatureFlags {
                extraction_interval: Some(5),
                ..Default::default()
            },
            checked_at: 0,
            ..Default::default()
        };
        assert_eq!(get_extraction_interval(Some(&cache)), 5);

        // Without cache, returns default
        assert_eq!(get_extraction_interval(None), DEFAULT_EXTRACTION_INTERVAL);
    }

    #[test]
    fn test_feature_flags_max_candidate_pool() {
        let cache = BillingCache {
            tier: "pro".into(),
            facts_used: 0,
            facts_limit: 0,
            features: FeatureFlags {
                max_candidate_pool: Some(300),
                ..Default::default()
            },
            checked_at: 0,
            ..Default::default()
        };
        assert_eq!(get_max_candidate_pool(Some(&cache)), 300);

        // Free tier default
        let free_cache = BillingCache {
            tier: "free".into(),
            features: FeatureFlags::default(),
            ..cache.clone()
        };
        assert_eq!(get_max_candidate_pool(Some(&free_cache)), DEFAULT_CANDIDATE_POOL_FREE);

        // Pro tier default (no server override)
        let pro_no_override = BillingCache {
            tier: "pro".into(),
            features: FeatureFlags::default(),
            ..cache
        };
        assert_eq!(get_max_candidate_pool(Some(&pro_no_override)), DEFAULT_CANDIDATE_POOL_PRO);
    }

    #[test]
    fn test_feature_flags_deserialization() {
        let json = r#"{
            "llm_dedup": true,
            "extraction_interval": 3,
            "max_facts_per_extraction": 15,
            "max_candidate_pool": 200
        }"#;
        let flags: FeatureFlags = serde_json::from_str(json).unwrap();
        assert_eq!(flags.llm_dedup, Some(true));
        assert_eq!(flags.extraction_interval, Some(3));
        assert_eq!(flags.max_facts_per_extraction, Some(15));
        assert_eq!(flags.max_candidate_pool, Some(200));
    }

    #[test]
    fn test_llm_dedup_kill_switch() {
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 0,
            facts_limit: 500,
            features: FeatureFlags {
                llm_dedup: Some(false),
                ..Default::default()
            },
            checked_at: 0,
            ..Default::default()
        };
        assert!(!is_llm_dedup_enabled(Some(&cache)));
        assert!(is_llm_dedup_enabled(None)); // Default: enabled
    }

    // ------------------------------------------------------------------
    // Environment (prod vs staging) — production users must never see
    // staging mentioned; staging callers MUST see the quota carve-out.
    // ------------------------------------------------------------------

    #[test]
    fn test_production_cache_emits_no_staging_note() {
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 30,
            facts_limit: 250,
            environment: Some("production".into()),
            ..Default::default()
        };
        assert!(!cache.is_staging());
        assert!(cache.staging_note().is_none());
    }

    #[test]
    fn test_staging_cache_emits_staging_note() {
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 500, // Past the production cap — only possible on staging.
            facts_limit: 250,
            environment: Some("staging".into()),
            ..Default::default()
        };
        assert!(cache.is_staging());
        let note = cache.staging_note().expect("staging emits a note");
        // The note must explain BOTH the staging behavior AND the
        // production cap so the agent can give an honest comparison.
        assert!(note.contains("staging"));
        assert!(note.contains("NOT enforced") || note.to_lowercase().contains("not enforced"));
        assert!(note.contains("250"));
        assert!(note.contains("api-staging.totalreclaw.xyz"));
        assert!(note.contains("api.totalreclaw.xyz"));
    }

    #[test]
    fn test_quota_warning_suppressed_on_staging() {
        // 90% usage on staging — would normally warn, but staging
        // doesn't enforce the cap, so a warning would be a lie.
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 450,
            facts_limit: 500,
            environment: Some("staging".into()),
            ..Default::default()
        };
        assert!(!cache.is_quota_warning());
        assert!(cache.quota_warning_message().is_none());
    }

    #[test]
    fn test_quota_warning_fires_on_production() {
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 450,
            facts_limit: 500,
            environment: Some("production".into()),
            ..Default::default()
        };
        assert!(cache.is_quota_warning());
        assert!(cache.quota_warning_message().is_some());
    }

    #[test]
    fn test_environment_none_treated_as_production_for_warning() {
        // Defensive: if environment is missing (older cache file), we
        // must NOT suppress the warning — production users at 90%
        // need the nudge.
        let cache = BillingCache {
            tier: "free".into(),
            facts_used: 450,
            facts_limit: 500,
            environment: None,
            ..Default::default()
        };
        assert!(!cache.is_staging());
        assert!(cache.is_quota_warning());
    }

    #[test]
    fn test_infer_environment_from_url() {
        use crate::relay::infer_environment_from_url;
        assert_eq!(infer_environment_from_url("https://api.totalreclaw.xyz"), "production");
        assert_eq!(infer_environment_from_url("https://api-staging.totalreclaw.xyz"), "staging");
        assert_eq!(infer_environment_from_url("HTTPS://API-STAGING.totalreclaw.xyz"), "staging");
        // Self-hosted: treat as production (operator runs their own relay,
        // not our staging instance).
        assert_eq!(infer_environment_from_url("https://relay.example.com"), "production");
        assert_eq!(infer_environment_from_url("http://localhost:8000"), "production");
    }
}
