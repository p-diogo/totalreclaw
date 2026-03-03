/**
 * Cache Behavior Monitor
 *
 * Analyzes plugin logs and injection events to infer cache behavior.
 * The plugin does not expose cache state directly, so we infer it from
 * observable patterns in log output and injection context.
 *
 * Detection heuristics:
 * - Cache hit: injection context contains "(cached)" suffix
 * - Cache miss: injection happened without "(cached)" marker
 * - Semantic skip: log contains semantic similarity / query similarity
 *   indicators showing the cache skipped a search (C2 path, similarity > 0.85)
 * - Refresh: log indicates cache was explicitly refreshed/invalidated
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 2.5.2)
 */

import type { CacheEvent, InjectionEvent } from '../types.js';

/** Raw log entry as captured by the ConversationDriver's mock logger. */
export interface LogEntry {
  level: string;
  timestamp: number;
  args: unknown[];
}

/**
 * Parse plugin logs and injection events to infer cache behavior.
 *
 * @param logs - Raw log entries captured from the plugin's logger
 * @param injections - Injection events captured from before_agent_start returns
 * @returns Array of CacheEvent entries, one per turn that had a search
 */
export function analyzeCacheEvents(
  logs: LogEntry[],
  injections: InjectionEvent[],
): CacheEvent[] {
  const events: CacheEvent[] = [];

  // First pass: check injection events for cache hit indicators
  for (const injection of injections) {
    if (!injection.injected) {
      // No injection means either no search or relevance-gated -- not a cache event
      continue;
    }

    if (injection.contextSnippet?.includes('cached')) {
      events.push({
        timestamp: injection.timestamp,
        type: 'hit',
      });
    } else {
      events.push({
        timestamp: injection.timestamp,
        type: 'miss',
      });
    }
  }

  // Second pass: scan logs for semantic skip events (C2 path)
  // Pattern: "semantic similarity X.XX > threshold" or "query too similar, skipping search"
  for (const log of logs) {
    const msg = stringifyLogArgs(log.args);

    // Detect semantic similarity skip (C2: querySimilarity > 0.85)
    const similarityMatch = msg.match(
      /(?:semantic\s+)?similarity[:\s]+(\d+\.?\d*)/i,
    );
    if (similarityMatch && msg.toLowerCase().includes('skip')) {
      const similarity = parseFloat(similarityMatch[1]);
      events.push({
        timestamp: log.timestamp,
        type: 'semantic_skip',
        querySimilarity: similarity,
      });
    }

    // Detect explicit cache refresh/invalidation
    if (
      msg.toLowerCase().includes('cache') &&
      (msg.toLowerCase().includes('refresh') ||
        msg.toLowerCase().includes('invalidat') ||
        msg.toLowerCase().includes('expired'))
    ) {
      const ageMatch = msg.match(/age[:\s]+(\d+)/i);
      events.push({
        timestamp: log.timestamp,
        type: 'refresh',
        cacheAge: ageMatch ? parseInt(ageMatch[1], 10) : undefined,
      });
    }
  }

  // Sort by timestamp for chronological ordering
  events.sort((a, b) => a.timestamp - b.timestamp);

  return events;
}

/**
 * Compute summary statistics from cache events.
 */
export function computeCacheStats(events: CacheEvent[]): {
  hits: number;
  misses: number;
  semanticSkips: number;
  refreshes: number;
  hitRate: number;
} {
  const hits = events.filter((e) => e.type === 'hit').length;
  const misses = events.filter((e) => e.type === 'miss').length;
  const semanticSkips = events.filter((e) => e.type === 'semantic_skip').length;
  const refreshes = events.filter((e) => e.type === 'refresh').length;
  const total = hits + misses;

  return {
    hits,
    misses,
    semanticSkips,
    refreshes,
    hitRate: total > 0 ? hits / total : 0,
  };
}

/**
 * Convert log args array to a single string for pattern matching.
 */
function stringifyLogArgs(args: unknown[]): string {
  return args
    .map((arg) => {
      if (typeof arg === 'string') return arg;
      if (typeof arg === 'number' || typeof arg === 'boolean') return String(arg);
      try {
        return JSON.stringify(arg);
      } catch {
        return String(arg);
      }
    })
    .join(' ');
}
