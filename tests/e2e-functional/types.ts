/**
 * Type definitions for the TotalReclaw E2E functional test suite.
 *
 * Defines all metric, scenario, configuration, and report types used across
 * the test infrastructure: conversation driver, interceptors, assertions,
 * and report generation.
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (sections 4.1, 4.2, 6.3)
 */

// ---------------------------------------------------------------------------
// Metric types (section 4.1)
// ---------------------------------------------------------------------------

export interface TestMetrics {
  instanceId: string;
  scenarioId: string;
  hookInvocations: HookInvocation[];
  cacheEvents: CacheEvent[];
  extractionEvents: ExtractionEvent[];
  injectionEvents: InjectionEvent[];
  graphqlQueries: CapturedGraphQLQuery[];
  turnMetrics: TurnMetric[];
}

export interface HookInvocation {
  hookName: string;
  timestamp: number;
  durationMs: number;
  returnedContext: boolean;
  contextLength: number;
}

export interface CacheEvent {
  timestamp: number;
  type: 'hit' | 'miss' | 'refresh' | 'semantic_skip';
  querySimilarity?: number;
  cacheAge?: number;
}

export interface ExtractionEvent {
  turnIndex: number;
  timestamp: number;
  extracted: boolean;
  factCount: number;
}

export interface InjectionEvent {
  turnIndex: number;
  injected: boolean;
  contextSnippet: string | null;
  timestamp: number;
}

export interface TurnMetric {
  turnIndex: number;
  durationMs: number;
  hookLatencyMs: number;
  memoryInjected: boolean;
  toolsUsed: string[];
  /** Timestamp when this turn started (epoch ms). Used for GraphQL query correlation. */
  timestamp?: number;
}

export interface CapturedGraphQLQuery {
  timestamp: number;
  endpoint: string;
  query: string;
  variables: Record<string, unknown>;
  durationMs: number;
  resultCount: number;
  wasBatched: boolean;
}

// ---------------------------------------------------------------------------
// Scenario and turn types (section 4.1)
// ---------------------------------------------------------------------------

export interface ConversationScenario {
  id: string;
  name: string;
  description: string;
  pluginPath: string;
  turns: Turn[];
  triggerCompaction?: boolean;
}

export interface Turn {
  index: number;
  userMessage: string;
  assistantResponse?: string;
  toolCalls?: Array<{ name: string; params: Record<string, unknown> }>;
}

export interface TurnResult {
  injectedContext: string | null;
  toolResults: unknown[];
  messageHistory: unknown[];
}

// ---------------------------------------------------------------------------
// Instance configuration (section 2.2)
// ---------------------------------------------------------------------------

export interface InstanceConfig {
  /** Unique identifier for this instance (e.g. 'server-improved'). */
  id: string;
  /** Backend mode: 'server' uses HTTP + PG, 'subgraph' uses GraphQL + Graph Node. */
  mode: 'server' | 'subgraph';
  /** Whether retrieval improvements (B1-B3, C1-C3, A1-A5) are enabled. */
  improvements: boolean;
  /** Environment variables to set before loading the plugin. */
  env: Record<string, string>;
  /** Path to the plugin module to import. */
  pluginPath: string;
}

// ---------------------------------------------------------------------------
// GraphQL analysis (section 6.3)
// ---------------------------------------------------------------------------

export interface GraphQLAnalysis {
  totalQueries: number;
  /** Number of SearchByBlindIndex queries. */
  searchQueries: number;
  /** Number of PaginateBlindIndex queries (cursor-based pagination). */
  paginationQueries: number;
  /** Number of FactCount / globalStates queries. */
  factCountQueries: number;
  /** Average trapdoor count per search query. */
  avgBatchSize: number;
  /** Maximum number of queries observed within a 100ms window (parallelism). */
  maxParallelBatch: number;
  /** Average GraphQL response time in ms. */
  avgQueryLatency: number;
  /** 95th percentile GraphQL response time in ms. */
  p95QueryLatency: number;
  /** Total entities returned across all queries. */
  totalResultsReturned: number;
  /** Number of batches returning exactly PAGE_SIZE (1000) results. */
  saturatedBatches: number;
}

// ---------------------------------------------------------------------------
// Structured log (section 6.2)
// ---------------------------------------------------------------------------

export interface StructuredLog {
  timestamp: number;
  level: 'info' | 'warn' | 'error';
  category: 'init' | 'search' | 'cache' | 'extraction' | 'store' | 'hook' | 'other';
  message: string;
  metadata?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Report types (section 4.2)
// ---------------------------------------------------------------------------

export interface AssertionResult {
  passed: boolean;
  message: string;
}

export interface ScenarioReport {
  metrics: TestMetrics;
  assertions: { [name: string]: AssertionResult };
}

export interface InstanceReport {
  scenarios: { [scenarioId: string]: ScenarioReport };
}

export interface ComparisonEntry {
  metric: string;
  improved: number | string;
  baseline: number | string;
  delta: string;
  target: string;
  passed: boolean;
}

export interface ComparisonMatrix {
  serverImprovedVsBaseline: ComparisonEntry[];
  subgraphImprovedVsBaseline: ComparisonEntry[];
  subgraphVsServer: ComparisonEntry[];
}

export interface TestReport {
  timestamp: string;
  duration_seconds: number;
  instances: { [instanceId: string]: InstanceReport };
  comparison: ComparisonMatrix;
  summary: {
    total_assertions: number;
    passed: number;
    failed: number;
    scenarios_run: number;
    instances_used: number;
  };
}

// ---------------------------------------------------------------------------
// Scenario applicability matrix (section 7.4)
// ---------------------------------------------------------------------------

/**
 * Maps scenario IDs to the set of instance IDs they should run against.
 *
 * | Scenario | server-improved | server-baseline | subgraph-improved | subgraph-baseline | server-recency |
 * |----------|:-:|:-:|:-:|:-:|:-:|
 * | A        | X | X | X | X | X |
 * | B        | X | X | X |   |   |
 * | C        | X | X |   |   |   |
 * | D        | X | X | X |   |   |
 * | E        | X | X |   |   |   |
 * | F        |   |   | X | X |   |
 * | G        |   |   | X | X |   |
 * | H        | X |   | X |   |   |
 */
export const SCENARIO_APPLICABILITY: Record<string, string[]> = {
  A: ['server-improved', 'server-baseline', 'subgraph-improved', 'subgraph-baseline', 'server-recency'],
  B: ['server-improved', 'server-baseline', 'subgraph-improved'],
  C: ['server-improved', 'server-baseline'],
  D: ['server-improved', 'server-baseline', 'subgraph-improved'],
  E: ['server-improved', 'server-baseline'],
  F: ['subgraph-improved', 'subgraph-baseline'],
  G: ['subgraph-improved', 'subgraph-baseline'],
  H: ['server-improved', 'subgraph-improved'],
};

// ---------------------------------------------------------------------------
// Assertion function signatures
// ---------------------------------------------------------------------------

/** A single-instance assertion function. */
export type AssertionFn = (metrics: TestMetrics) => void;

/** A cross-instance comparison assertion function. */
export type ComparisonAssertionFn = (
  improvedMetrics: TestMetrics,
  baselineMetrics: TestMetrics,
) => void;
