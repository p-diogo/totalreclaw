/**
 * GraphQL Query Interceptor
 *
 * Monkey-patches `globalThis.fetch` to capture all outbound GraphQL requests
 * for analysis. Captures timing, query text, variables, result counts, and
 * batching information without breaking actual fetch behavior.
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 2.5.1, 6.3)
 */

import type { CapturedGraphQLQuery, GraphQLAnalysis } from '../types.js';

const captured: CapturedGraphQLQuery[] = [];
let originalFetch: typeof globalThis.fetch | null = null;

/**
 * Install the GraphQL interceptor by monkey-patching `globalThis.fetch`.
 *
 * Must be called BEFORE loading the plugin so all outbound GraphQL requests
 * are captured. Safe to call multiple times -- subsequent calls are no-ops
 * if the interceptor is already installed.
 */
export function installGraphQLInterceptor(): void {
  if (originalFetch !== null) {
    // Already installed
    return;
  }

  originalFetch = globalThis.fetch;

  globalThis.fetch = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    const isGraphQL =
      url.includes('/subgraphs/') || url.includes('graphql');

    if (!isGraphQL || !init?.body) {
      return originalFetch!(input, init);
    }

    let body: Record<string, unknown>;
    try {
      body = JSON.parse(init.body as string);
    } catch {
      // Not valid JSON -- pass through unmodified
      return originalFetch!(input, init);
    }

    const startMs = performance.now();
    const response = await originalFetch!(input, init);
    const durationMs = performance.now() - startMs;

    // Clone response to read body without consuming the original stream
    const cloned = response.clone();
    let resultCount = 0;
    try {
      const responseBody = await cloned.json();
      // Try common response shapes for result count
      resultCount =
        responseBody?.data?.blindIndexes?.length ??
        responseBody?.data?.facts?.length ??
        responseBody?.data?.globalStates?.length ??
        0;
    } catch {
      // Response wasn't JSON or couldn't be parsed -- leave resultCount as 0
    }

    // Determine trapdoor count from variables for batching analysis
    const trapdoors = (body.variables as Record<string, unknown> | undefined)
      ?.trapdoors;
    const trapdoorCount = Array.isArray(trapdoors) ? trapdoors.length : 0;

    captured.push({
      timestamp: Date.now(),
      endpoint: url,
      query: (body.query as string)?.trim().slice(0, 200) ?? '',
      variables: (body.variables as Record<string, unknown>) ?? {},
      durationMs,
      resultCount,
      wasBatched: trapdoorCount > 0 && trapdoorCount <= 5,
    });

    return response;
  };
}

/**
 * Return a copy of all captured GraphQL queries since the last reset.
 */
export function getGraphQLCaptures(): CapturedGraphQLQuery[] {
  return [...captured];
}

/**
 * Clear all captured queries. Call between scenarios to isolate metrics.
 */
export function resetCaptures(): void {
  captured.length = 0;
}

/**
 * Uninstall the interceptor and restore the original `globalThis.fetch`.
 */
export function uninstallGraphQLInterceptor(): void {
  if (originalFetch !== null) {
    globalThis.fetch = originalFetch;
    originalFetch = null;
  }
}

/**
 * Compute aggregate analysis over captured GraphQL queries.
 *
 * Categorizes queries by operation name pattern, detects parallel batching
 * by measuring timestamp gaps, and computes latency percentiles.
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 6.3)
 */
export function analyzeGraphQL(
  queries: CapturedGraphQLQuery[],
): GraphQLAnalysis {
  const search = queries.filter((q) =>
    q.query.includes('SearchByBlindIndex'),
  );
  const paginate = queries.filter((q) =>
    q.query.includes('PaginateBlindIndex'),
  );
  const factCount = queries.filter(
    (q) =>
      q.query.includes('FactCount') || q.query.includes('globalStates'),
  );

  // Detect parallel batches: count queries within 100ms sliding windows
  const sorted = [...search].sort((a, b) => a.timestamp - b.timestamp);
  let maxParallel = 0;
  for (let i = 0; i < sorted.length; i++) {
    let count = 1;
    for (
      let j = i + 1;
      j < sorted.length && sorted[j].timestamp - sorted[i].timestamp < 100;
      j++
    ) {
      count++;
    }
    maxParallel = Math.max(maxParallel, count);
  }

  // Latency statistics across all queries
  const latencies = queries.map((q) => q.durationMs).sort((a, b) => a - b);
  const avgLatency =
    latencies.length > 0
      ? latencies.reduce((a, b) => a + b, 0) / latencies.length
      : 0;
  const p95Index = Math.floor(latencies.length * 0.95);
  const p95Latency = latencies[p95Index] ?? 0;

  // Average batch size (trapdoor count) across search queries
  const totalTrapdoors = search.reduce((sum, q) => {
    const trapdoors = (q.variables as Record<string, unknown>)?.trapdoors;
    return sum + (Array.isArray(trapdoors) ? trapdoors.length : 0);
  }, 0);
  const avgBatchSize =
    search.length > 0 ? totalTrapdoors / search.length : 0;

  return {
    totalQueries: queries.length,
    searchQueries: search.length,
    paginationQueries: paginate.length,
    factCountQueries: factCount.length,
    avgBatchSize,
    maxParallelBatch: maxParallel,
    avgQueryLatency: avgLatency,
    p95QueryLatency: p95Latency,
    totalResultsReturned: queries.reduce(
      (sum, q) => sum + q.resultCount,
      0,
    ),
    saturatedBatches: search.filter((q) => q.resultCount >= 1000).length,
  };
}
