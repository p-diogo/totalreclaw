/**
 * ConversationDriver -- Core engine for the E2E functional test suite.
 *
 * Simulates the OpenClaw plugin lifecycle by:
 *   1. Loading the TotalReclaw plugin via dynamic import
 *   2. Providing a mock OpenClawPluginApi that captures all hook/tool registrations
 *   3. Driving conversation turns: before_agent_start -> tool calls -> agent_end
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 2.4)
 */

import type {
  ConversationScenario,
  Turn,
  TurnResult,
  TestMetrics,
  InstanceConfig,
} from './types.js';

// ---------------------------------------------------------------------------
// Mock plugin API types
// ---------------------------------------------------------------------------

interface MockPluginApi {
  logger: {
    info: (...args: unknown[]) => void;
    warn: (...args: unknown[]) => void;
    error: (...args: unknown[]) => void;
  };
  config: Record<string, unknown>;
  pluginConfig: Record<string, unknown>;
  registerTool: (tool: unknown, opts?: { name?: string; names?: string[] }) => void;
  registerService: (service: { id: string; start(): void; stop?(): void }) => void;
  on: (hookName: string, handler: (...args: unknown[]) => unknown, opts?: { priority?: number }) => void;
}

/**
 * Registered hook handlers (populated during plugin.register()).
 * Keys: 'before_agent_start', 'agent_end', 'before_compaction', 'before_reset'
 */
interface HookRegistry {
  [hookName: string]: Array<{
    handler: (...args: unknown[]) => unknown;
    priority: number;
  }>;
}

/**
 * Registered tool handlers (populated during plugin.register()).
 * Keys: 'totalreclaw_remember', 'totalreclaw_recall', etc.
 */
interface ToolRegistry {
  [toolName: string]: {
    execute: (toolCallId: string, params: Record<string, unknown>) => Promise<unknown>;
  };
}

// ---------------------------------------------------------------------------
// Captured log entry
// ---------------------------------------------------------------------------

export interface LogEntry {
  level: string;
  timestamp: number;
  args: unknown[];
}

// ---------------------------------------------------------------------------
// ConversationDriver
// ---------------------------------------------------------------------------

export class ConversationDriver {
  private hooks: HookRegistry = {};
  private tools: ToolRegistry = {};
  private metrics: TestMetrics;
  private logCapture: LogEntry[] = [];
  private runId: string;

  constructor(
    private instanceConfig: InstanceConfig,
    private scenario: ConversationScenario,
  ) {
    this.runId = `${instanceConfig.id}-${scenario.id}-${Date.now()}`;
    this.metrics = {
      instanceId: instanceConfig.id,
      scenarioId: scenario.id,
      hookInvocations: [],
      cacheEvents: [],
      extractionEvents: [],
      injectionEvents: [],
      graphqlQueries: [],
      turnMetrics: [],
    };
  }

  // -------------------------------------------------------------------------
  // Mock API construction
  // -------------------------------------------------------------------------

  /**
   * Build a mock OpenClaw plugin API that captures all registrations.
   */
  private buildMockApi(): MockPluginApi {
    return {
      logger: {
        info: (...args: unknown[]) =>
          this.logCapture.push({ level: 'info', timestamp: Date.now(), args }),
        warn: (...args: unknown[]) =>
          this.logCapture.push({ level: 'warn', timestamp: Date.now(), args }),
        error: (...args: unknown[]) =>
          this.logCapture.push({ level: 'error', timestamp: Date.now(), args }),
      },
      config: {
        agents: { defaults: { model: { primary: 'claude-3-5-haiku-20241022' } } },
      },
      pluginConfig: {},
      registerTool: (tool: any, opts?: { name?: string; names?: string[] }) => {
        const name = opts?.name ?? tool.name;
        if (name) {
          this.tools[name] = { execute: tool.execute.bind(tool) };
        }
        // Some tools register multiple names (e.g. aliases)
        if (opts?.names) {
          for (const n of opts.names) {
            this.tools[n] = { execute: tool.execute.bind(tool) };
          }
        }
      },
      registerService: (_service: { id: string; start(): void; stop?(): void }) => {
        // Services are not exercised in the test driver; capture silently.
      },
      on: (
        hookName: string,
        handler: (...args: unknown[]) => unknown,
        opts?: { priority?: number },
      ) => {
        if (!this.hooks[hookName]) this.hooks[hookName] = [];
        this.hooks[hookName].push({ handler, priority: opts?.priority ?? 50 });
        // Sort by priority (lower = earlier)
        this.hooks[hookName].sort((a, b) => a.priority - b.priority);
      },
    };
  }

  // -------------------------------------------------------------------------
  // Plugin initialization
  // -------------------------------------------------------------------------

  /**
   * Initialize the plugin by dynamically importing it and calling register()
   * with our mock API.
   *
   * Uses a cache-busting query string to ensure ESM module isolation between
   * scenarios (each scenario gets fresh module-level state).
   */
  async initialize(): Promise<void> {
    // Set instance-specific environment variables before loading the plugin
    for (const [key, value] of Object.entries(this.instanceConfig.env)) {
      process.env[key] = value;
    }

    // Dynamic import with cache-busting for ESM module isolation
    const pluginModule = await import(
      `${this.instanceConfig.pluginPath}?run=${this.runId}`
    );
    const plugin = pluginModule.default;

    if (typeof plugin?.register !== 'function') {
      throw new Error(
        `Plugin at ${this.instanceConfig.pluginPath} does not export a default ` +
        `object with a register() method`,
      );
    }

    plugin.register(this.buildMockApi());
  }

  // -------------------------------------------------------------------------
  // Hook firing
  // -------------------------------------------------------------------------

  /**
   * Fire a hook and capture timing + return value.
   */
  private async fireHook(hookName: string, event: unknown): Promise<unknown> {
    const handlers = this.hooks[hookName] ?? [];
    const startMs = performance.now();
    let result: unknown;

    for (const { handler } of handlers) {
      result = await handler(event);
    }

    const durationMs = performance.now() - startMs;
    this.metrics.hookInvocations.push({
      hookName,
      timestamp: Date.now(),
      durationMs,
      returnedContext: result != null,
      contextLength:
        typeof result === 'object' && result !== null
          ? JSON.stringify(result).length
          : 0,
    });

    return result;
  }

  // -------------------------------------------------------------------------
  // Turn execution
  // -------------------------------------------------------------------------

  /**
   * Run a single conversation turn through the plugin lifecycle:
   *   1. before_agent_start (with user message)
   *   2. [optional] tool calls (if turn specifies explicit tool use)
   *   3. agent_end (with full message history)
   */
  async runTurn(turn: Turn, messageHistory: unknown[]): Promise<TurnResult> {
    const turnStart = performance.now();
    const turnStartTimestamp = Date.now();

    // 1. before_agent_start hook
    const hookResult = await this.fireHook('before_agent_start', {
      prompt: turn.userMessage,
    });

    const injectedContext = hookResult as { prependContext?: string } | undefined;
    this.metrics.injectionEvents.push({
      turnIndex: turn.index,
      injected: !!injectedContext?.prependContext,
      contextSnippet: injectedContext?.prependContext?.slice(0, 2000) ?? null,
      timestamp: Date.now(),
    });

    // 2. Optional explicit tool calls
    const toolResults: unknown[] = [];
    if (turn.toolCalls) {
      for (const tc of turn.toolCalls) {
        const tool = this.tools[tc.name];
        if (tool) {
          const result = await tool.execute(`tc-${Date.now()}`, tc.params);
          toolResults.push({ name: tc.name, result });
        } else {
          toolResults.push({
            name: tc.name,
            error: `Tool '${tc.name}' not registered`,
          });
        }
      }
    }

    // Simulate assistant response
    const assistantMessage = turn.assistantResponse ?? '[simulated response]';

    // Build message history for agent_end
    const updatedHistory = [
      ...messageHistory,
      { role: 'user', content: [{ type: 'text', text: turn.userMessage }] },
      { role: 'assistant', content: [{ type: 'text', text: assistantMessage }] },
    ];

    // 3. agent_end hook
    await this.fireHook('agent_end', {
      messages: updatedHistory,
      success: true,
    });
    // Inject turn boundary marker AFTER agent_end for the extraction tracker.
    // This ensures extraction logs from the hook are assigned to the correct turn.
    this.logCapture.push({
      level: 'info',
      timestamp: Date.now(),
      args: [`agent_end: turn ${turn.index} complete`],
    });

    const turnDurationMs = performance.now() - turnStart;

    // Collect hook latency for hooks that fired during this turn
    const hookLatencyMs = this.metrics.hookInvocations
      .filter((h) => h.timestamp >= turnStartTimestamp)
      .reduce((sum, h) => sum + h.durationMs, 0);

    this.metrics.turnMetrics.push({
      turnIndex: turn.index,
      durationMs: turnDurationMs,
      hookLatencyMs,
      memoryInjected: !!injectedContext?.prependContext,
      toolsUsed: turn.toolCalls?.map((tc) => tc.name) ?? [],
      timestamp: turnStartTimestamp,
    });

    return {
      injectedContext: injectedContext?.prependContext ?? null,
      toolResults,
      messageHistory: updatedHistory,
    };
  }

  // -------------------------------------------------------------------------
  // Full scenario execution
  // -------------------------------------------------------------------------

  /**
   * Run the complete scenario: initialize plugin, execute all turns, optionally
   * trigger compaction, and return collected metrics.
   */
  async runScenario(): Promise<TestMetrics> {
    await this.initialize();

    let messageHistory: unknown[] = [];
    for (const turn of this.scenario.turns) {
      const result = await this.runTurn(turn, messageHistory);
      messageHistory = result.messageHistory;
    }

    // Optionally trigger compaction hook at the end
    if (this.scenario.triggerCompaction) {
      await this.fireHook('before_compaction', {
        messages: messageHistory,
        messageCount: messageHistory.length,
      });
    }

    return this.metrics;
  }

  // -------------------------------------------------------------------------
  // Accessors
  // -------------------------------------------------------------------------

  getMetrics(): TestMetrics {
    return this.metrics;
  }

  getLogs(): LogEntry[] {
    return this.logCapture;
  }

  getHooks(): HookRegistry {
    return this.hooks;
  }

  getTools(): ToolRegistry {
    return this.tools;
  }
}

// ---------------------------------------------------------------------------
// Utility: categorize plugin logs (section 6.2)
// ---------------------------------------------------------------------------

export function categorizeLog(args: unknown[]): string {
  const msg = String(args[0] ?? '');
  if (msg.includes('initialized') || msg.includes('Registered') || msg.includes('loaded'))
    return 'init';
  if (msg.includes('search') || msg.includes('Fact count') || msg.includes('candidate'))
    return 'search';
  if (msg.includes('cache') || msg.includes('cached')) return 'cache';
  if (msg.includes('extract') || msg.includes('Auto-extracted')) return 'extraction';
  if (msg.includes('store') || msg.includes('Memory stored')) return 'store';
  if (
    msg.includes('hook') ||
    msg.includes('before_agent_start') ||
    msg.includes('agent_end')
  )
    return 'hook';
  return 'other';
}

// ---------------------------------------------------------------------------
// Utility: analyze GraphQL captures (section 6.3)
// ---------------------------------------------------------------------------

import type { CapturedGraphQLQuery, GraphQLAnalysis } from './types.js';

export function analyzeGraphQL(queries: CapturedGraphQLQuery[]): GraphQLAnalysis {
  const search = queries.filter((q) => q.query.includes('SearchByBlindIndex'));
  const paginate = queries.filter((q) => q.query.includes('PaginateBlindIndex'));
  const factCount = queries.filter(
    (q) => q.query.includes('FactCount') || q.query.includes('globalStates'),
  );

  // Detect parallel batches: count queries within 100ms windows
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

  const latencies = queries.map((q) => q.durationMs).sort((a, b) => a - b);

  return {
    totalQueries: queries.length,
    searchQueries: search.length,
    paginationQueries: paginate.length,
    factCountQueries: factCount.length,
    avgBatchSize:
      search.reduce(
        (sum, q) => sum + ((q.variables as any)?.trapdoors?.length ?? 0),
        0,
      ) / Math.max(search.length, 1),
    maxParallelBatch: maxParallel,
    avgQueryLatency:
      latencies.reduce((a, b) => a + b, 0) / Math.max(latencies.length, 1),
    p95QueryLatency: latencies[Math.floor(latencies.length * 0.95)] ?? 0,
    totalResultsReturned: queries.reduce((sum, q) => sum + q.resultCount, 0),
    saturatedBatches: search.filter((q) => q.resultCount >= 1000).length,
  };
}
