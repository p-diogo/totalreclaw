/**
 * Cross-Instance Comparison Assertions
 *
 * Validates that the improved instance outperforms (or at least matches) the
 * baseline instance on key metrics. These assertions compare TestMetrics from
 * two different instances that ran the same scenario.
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 5)
 */

import type { TestMetrics } from '../types.js';

// ---------------------------------------------------------------------------
// Assertion helper
// ---------------------------------------------------------------------------

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

// ---------------------------------------------------------------------------
// Comparison assertions
// ---------------------------------------------------------------------------

/**
 * C3-3: Extraction reduction vs baseline.
 * The improved instance (EXTRACT_EVERY_TURNS=5) should achieve at least
 * 70% fewer extraction calls compared to the baseline (EXTRACT_EVERY_TURNS=1).
 *
 * Spec target: improved extractions / baseline extractions <= 0.3 (70%+ reduction)
 */
export function extraction_reduction_vs_baseline(
  improvedMetrics: TestMetrics,
  baselineMetrics: TestMetrics,
): void {
  const improvedCount = improvedMetrics.extractionEvents.filter(
    (e) => e.extracted,
  ).length;
  const baselineCount = baselineMetrics.extractionEvents.filter(
    (e) => e.extracted,
  ).length;

  // Guard against division by zero (baseline should always extract)
  assert(
    baselineCount > 0,
    `Baseline should have at least 1 extraction, got ${baselineCount}`,
  );

  const reduction = 1 - improvedCount / baselineCount;
  assert(
    reduction >= 0.7,
    `Expected >=70% extraction reduction vs baseline, got ${(reduction * 100).toFixed(1)}% ` +
      `(improved: ${improvedCount}, baseline: ${baselineCount})`,
  );
}

/**
 * Noise injection eliminated.
 * On noise/greeting turns, the improved instance (B2 relevance threshold = 0.3)
 * should have 0% injection rate, while the baseline (threshold = 0.0) has
 * 100% injection rate.
 *
 * Spec target: 0% noise injection on improved vs 100% on baseline
 */
export function noise_injection_eliminated(
  improvedMetrics: TestMetrics,
  baselineMetrics: TestMetrics,
): void {
  // Use scenario C's noise turn indices (0-indexed)
  const noiseTurnIndices = [3, 4, 5, 6, 7, 8, 9, 13, 14];

  const improvedNoiseInjections = improvedMetrics.injectionEvents.filter(
    (e) => noiseTurnIndices.includes(e.turnIndex) && e.injected,
  );
  const baselineNoiseInjections = baselineMetrics.injectionEvents.filter(
    (e) => noiseTurnIndices.includes(e.turnIndex) && e.injected,
  );

  assert(
    improvedNoiseInjections.length === 0,
    `Expected 0 noise injections on improved instance, got ${improvedNoiseInjections.length}`,
  );

  // Baseline should inject on all or most noise turns (no threshold gate)
  const baselineRate =
    noiseTurnIndices.length > 0
      ? baselineNoiseInjections.length / noiseTurnIndices.length
      : 0;
  assert(
    baselineRate >= 0.5,
    `Expected baseline to inject on most noise turns (>=50%), got ${(baselineRate * 100).toFixed(1)}% ` +
      `(${baselineNoiseInjections.length}/${noiseTurnIndices.length})`,
  );
}

/**
 * Cache hit improvement.
 * The improved instance (C2 hot cache enabled) should have a higher cache
 * hit rate than the baseline (cache disabled, TTL=0).
 *
 * Spec target: improved cache hits > 0%, baseline cache hits = 0%
 */
export function cache_hit_improvement(
  improvedMetrics: TestMetrics,
  baselineMetrics: TestMetrics,
): void {
  const improvedHits = improvedMetrics.cacheEvents.filter(
    (e) => e.type === 'hit',
  ).length;
  const baselineHits = baselineMetrics.cacheEvents.filter(
    (e) => e.type === 'hit',
  ).length;

  assert(
    improvedHits > 0,
    `Expected improved instance to have >0 cache hits, got ${improvedHits}`,
  );
  assert(
    improvedHits > baselineHits,
    `Expected improved cache hits (${improvedHits}) > baseline cache hits (${baselineHits})`,
  );
}

/**
 * Recall no regression.
 * The improved instance should recall at least as well as the baseline.
 * We measure recall by counting turns where memory injection matched the
 * expected context (injected = true on relevant turns).
 *
 * A 5% margin is allowed to account for non-determinism in embeddings
 * and LLM extraction.
 *
 * Spec target: improved recall >= baseline recall (within 5% margin)
 */
export function recall_no_regression(
  improvedMetrics: TestMetrics,
  baselineMetrics: TestMetrics,
): void {
  const improvedInjections = improvedMetrics.injectionEvents.filter(
    (e) => e.injected,
  ).length;
  const baselineInjections = baselineMetrics.injectionEvents.filter(
    (e) => e.injected,
  ).length;

  const improvedTotal = improvedMetrics.injectionEvents.length;
  const baselineTotal = baselineMetrics.injectionEvents.length;

  const improvedRate =
    improvedTotal > 0 ? improvedInjections / improvedTotal : 0;
  const baselineRate =
    baselineTotal > 0 ? baselineInjections / baselineTotal : 0;

  // Allow 5% margin for non-determinism
  const margin = 0.05;
  assert(
    improvedRate >= baselineRate - margin,
    `Recall regression detected: improved ${(improvedRate * 100).toFixed(1)}% vs ` +
      `baseline ${(baselineRate * 100).toFixed(1)}% (margin: ${(margin * 100).toFixed(0)}%)`,
  );
}

/**
 * Latency no regression.
 * The improved instance's p95 hook latency should not exceed 1.5x the
 * baseline's p95. The improvements (cache, throttle, threshold) should
 * either maintain or improve latency, not degrade it.
 *
 * Spec target: improved p95 <= baseline p95 * 1.5
 */
export function latency_no_regression(
  improvedMetrics: TestMetrics,
  baselineMetrics: TestMetrics,
): void {
  const getP95 = (metrics: TestMetrics): number => {
    const latencies = metrics.hookInvocations
      .filter((h) => h.hookName === 'before_agent_start')
      .map((h) => h.durationMs)
      .sort((a, b) => a - b);

    if (latencies.length === 0) return 0;
    const p95Index = Math.floor(latencies.length * 0.95);
    return latencies[p95Index] ?? 0;
  };

  const improvedP95 = getP95(improvedMetrics);
  const baselineP95 = getP95(baselineMetrics);

  // Guard: if baseline has no hook data, skip
  if (baselineP95 === 0) {
    return;
  }

  assert(
    improvedP95 <= baselineP95 * 1.5,
    `Latency regression: improved p95 (${improvedP95.toFixed(0)}ms) exceeds ` +
      `1.5x baseline p95 (${baselineP95.toFixed(0)}ms, threshold: ${(baselineP95 * 1.5).toFixed(0)}ms)`,
  );
}

// ---------------------------------------------------------------------------
// Export map for programmatic access
// ---------------------------------------------------------------------------

/**
 * Registry of all comparison assertions for programmatic invocation.
 */
export const comparisonAssertions: Record<
  string,
  (improved: TestMetrics, baseline: TestMetrics) => void
> = {
  extraction_reduction_vs_baseline,
  noise_injection_eliminated,
  cache_hit_improvement,
  recall_no_regression,
  latency_no_regression,
};
