# Functional E2E Test Plan: Retrieval Improvements v3

**Created:** 2026-03-03 (Session 19)
**Branch:** `feature/subgraph`
**Scope:** All Category A-C improvements from `retrieval-improvements-v3.md`
**Depends on:** Implemented improvements in `skill/plugin/index.ts`, `skill/plugin/subgraph-search.ts`, `skill/plugin/reranker.ts`, `skill/plugin/hot-cache-wrapper.ts`

---

## 1. Objectives

This test plan validates the retrieval improvements in a **real OpenClaw conversation setup** -- not synthetic data or direct API calls. An LLM-driven conversation driver talks TO OpenClaw instances with TotalReclaw installed, creating realistic multi-turn conversations, while an instrumentation layer captures hook invocations, search queries, cache behavior, extraction events, and memory injection content.

### What This Tests (and What It Does Not)

**In scope:**
- A1-A5: Subgraph search fixes (parallel batches, ordering, pagination, fact count)
- B1: 4-signal weighted RRF ranking (BM25 + cosine + importance + recency)
- B2: Relevance threshold gate (cosine < 0.3 = no injection)
- B3: MMR diversity in results
- C1: Two-tier search (hook = lightweight/cached, tool = full search)
- C2: Hot cache TTL + semantic similarity skip
- C3: Extraction throttle (every 5 turns, not every turn)

**Out of scope:**
- D1-D3: Write-path optimizations (not yet implemented)
- E1-E3: Architecture differentiators (not yet implemented)
- B4: Cross-encoder reranker (not yet implemented)

---

## 2. Test Architecture

### 2.1 System Topology

```
+------------------------------------------------------------------+
|  TEST DRIVER (Node.js / tsx)                                      |
|                                                                    |
|  +-----------------------+  +---------------------------+          |
|  | Conversation Driver   |  | Metrics Collector         |          |
|  | (Claude API / script) |  | (hook logs, GraphQL logs, |          |
|  +-----------+-----------+  |  cache stats, timing)     |          |
|              |               +---------------------------+          |
|              v                                                     |
|  +---------------------------+                                     |
|  | OpenClaw Instance Manager |-- spins up 2-5 instances           |
|  +---------------------------+                                     |
+------------------------------------------------------------------+
              |              |              |
              v              v              v
  +-----------+--+  +-------+------+  +----+----------+
  | Instance A   |  | Instance B   |  | Instance C    |
  | Server mode  |  | Server mode  |  | Subgraph mode |
  | + improve-   |  | (baseline,   |  | + improve-    |
  |   ments ON   |  |  no changes) |  |   ments ON    |
  +-----------+--+  +-------+------+  +----+----------+
              |              |              |
              v              v              v
  +-----------+--+  +-------+------+  +----+----------+
  | TotalReclaw  |  | TotalReclaw  |  | Graph Node    |
  | Server (PG)  |  | Server (PG)  |  | + Hardhat     |
  +--------------+  +--------------+  +---------------+
```

### 2.2 Instance Configurations

| Instance | ID | Mode | Improvements | Purpose |
|----------|-----|------|-------------|---------|
| A | `server-improved` | Server (HTTP + PG) | All B1-B3, C1-C3 ON | Main test target |
| B | `server-baseline` | Server (HTTP + PG) | All OFF (pre-improvement code) | Baseline comparison |
| C | `subgraph-improved` | Subgraph (GraphQL + Graph Node) | All A1-A5, B1-B3, C1-C3 ON | Subgraph test target |
| D | `subgraph-baseline` | Subgraph (GraphQL + Graph Node) | All OFF | Subgraph baseline |
| E | `server-improved-recency` | Server (HTTP + PG) | B1 with recency-heavy weights (0.2, 0.2, 0.2, 0.4) | Weight sensitivity |

**Environment variables that control improvement toggles:**

```bash
# Instance A / C / E (improvements ON):
TOTALRECLAW_RELEVANCE_THRESHOLD=0.3       # B2: relevance gate
TOTALRECLAW_EXTRACT_EVERY_TURNS=5         # C3: extraction throttle
TOTALRECLAW_RANKING_WEIGHTS="0.25,0.25,0.25,0.25"  # B1: equal weights
# C1/C2 are code-level changes, active when the improved plugin is loaded

# Instance B / D (baseline):
TOTALRECLAW_RELEVANCE_THRESHOLD=0.0       # B2: disabled (inject everything)
TOTALRECLAW_EXTRACT_EVERY_TURNS=1         # C3: disabled (extract every turn)
# C1/C2 disabled via feature flag or loading the pre-improvement plugin code
```

### 2.3 Infrastructure Requirements

| Component | Instance A/B/E | Instance C/D |
|-----------|---------------|--------------|
| TotalReclaw server | 1 per instance (Docker) | Not needed |
| PostgreSQL | 1 shared (separate schemas) | 1 for Graph Node |
| Hardhat | Not needed | 1 shared |
| Graph Node | Not needed | 1 shared (separate subgraphs) |
| IPFS | Not needed | 1 shared |
| LLM API key | Required (for extraction + embeddings are local) | Same |

**Docker Compose file:** `tests/e2e-functional/docker-compose.yml`

```yaml
services:
  # --- Server mode infrastructure ---
  postgres-totalreclaw:
    image: postgres:16
    environment:
      POSTGRES_USER: totalreclaw
      POSTGRES_PASSWORD: testpass
      POSTGRES_DB: totalreclaw
    ports:
      - "25432:5432"

  totalreclaw-server:
    build: ../../server
    environment:
      DATABASE_URL: postgresql://totalreclaw:testpass@postgres-totalreclaw:5432/totalreclaw
    ports:
      - "28080:8080"
    depends_on:
      - postgres-totalreclaw

  # --- Subgraph mode infrastructure ---
  postgres-graphnode:
    image: postgres:16
    environment:
      POSTGRES_USER: graph-node
      POSTGRES_PASSWORD: let-me-in
      POSTGRES_DB: graph-node
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
    ports:
      - "25433:5432"

  ipfs:
    image: ipfs/kubo:latest
    ports:
      - "25001:5001"

  graph-node:
    image: graphprotocol/graph-node:latest
    ports:
      - "28000:8000"
      - "28020:8020"
    depends_on:
      - postgres-graphnode
      - ipfs
    environment:
      postgres_host: postgres-graphnode
      postgres_port: 5432
      postgres_user: graph-node
      postgres_pass: let-me-in
      postgres_db: graph-node
      ipfs: "ipfs:5001"
      ethereum: "hardhat:http://host.docker.internal:8545"
      GRAPH_LOG: info
      GRAPH_GRAPHQL_MAX_FIRST: "5000"
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### 2.4 Conversation Driver Architecture

The conversation driver is a Node.js script that programmatically sends messages to OpenClaw instances. It does NOT use the OpenClaw CLI directly; instead, it simulates the OpenClaw plugin lifecycle by:

1. **Loading the TotalReclaw plugin** directly (importing `skill/plugin/index.ts`)
2. **Providing a mock `OpenClawPluginApi`** that captures all hook invocations, tool registrations, and logger calls
3. **Driving the conversation loop** by calling hooks in sequence (simulating what OpenClaw does)

This approach avoids needing to install and run full OpenClaw instances. It tests the plugin code in isolation while faithfully reproducing the hook lifecycle.

```typescript
// tests/e2e-functional/conversation-driver.ts

import type { ConversationScenario, Turn, TestMetrics } from './types.js';

interface MockPluginApi {
  logger: {
    info: (...args: unknown[]) => void;
    warn: (...args: unknown[]) => void;
    error: (...args: unknown[]) => void;
  };
  config: Record<string, unknown>;
  pluginConfig: Record<string, unknown>;
  registerTool: (tool: unknown, opts?: { name?: string }) => void;
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

export class ConversationDriver {
  private hooks: HookRegistry = {};
  private tools: ToolRegistry = {};
  private metrics: TestMetrics;
  private logCapture: Array<{ level: string; timestamp: number; args: unknown[] }> = [];

  constructor(
    private instanceId: string,
    private scenario: ConversationScenario,
  ) {
    this.metrics = {
      instanceId,
      scenarioId: scenario.id,
      hookInvocations: [],
      cacheEvents: [],
      extractionEvents: [],
      injectionEvents: [],
      graphqlQueries: [],
      turnMetrics: [],
    };
  }

  /**
   * Build a mock OpenClaw plugin API that captures all registrations.
   */
  private buildMockApi(): MockPluginApi {
    return {
      logger: {
        info: (...args) => this.logCapture.push({ level: 'info', timestamp: Date.now(), args }),
        warn: (...args) => this.logCapture.push({ level: 'warn', timestamp: Date.now(), args }),
        error: (...args) => this.logCapture.push({ level: 'error', timestamp: Date.now(), args }),
      },
      config: {
        agents: { defaults: { model: { primary: 'claude-3-5-haiku-20241022' } } },
      },
      pluginConfig: {},
      registerTool: (tool: any, opts?: { name?: string }) => {
        const name = opts?.name ?? tool.name;
        this.tools[name] = { execute: tool.execute.bind(tool) };
      },
      registerService: () => {},
      on: (hookName: string, handler: (...args: unknown[]) => unknown, opts?: { priority?: number }) => {
        if (!this.hooks[hookName]) this.hooks[hookName] = [];
        this.hooks[hookName].push({ handler, priority: opts?.priority ?? 50 });
        // Sort by priority (lower = earlier)
        this.hooks[hookName].sort((a, b) => a.priority - b.priority);
      },
    };
  }

  /**
   * Initialize the plugin by calling register() with our mock API.
   */
  async initialize(): Promise<void> {
    // Dynamic import to pick up either improved or baseline plugin
    const pluginModule = await import(this.scenario.pluginPath);
    const plugin = pluginModule.default;
    plugin.register(this.buildMockApi());
  }

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
      contextLength: typeof result === 'object' && result !== null
        ? JSON.stringify(result).length
        : 0,
    });

    return result;
  }

  /**
   * Run a single conversation turn through the plugin lifecycle:
   *   1. before_agent_start (with user message)
   *   2. [optional] tool calls (if turn specifies explicit tool use)
   *   3. agent_end (with full message history)
   */
  async runTurn(turn: Turn, messageHistory: unknown[]): Promise<TurnResult> {
    const turnStart = performance.now();

    // 1. before_agent_start hook
    const hookResult = await this.fireHook('before_agent_start', {
      prompt: turn.userMessage,
    });

    const injectedContext = hookResult as { prependContext?: string } | undefined;
    this.metrics.injectionEvents.push({
      turnIndex: turn.index,
      injected: !!injectedContext?.prependContext,
      contextSnippet: injectedContext?.prependContext?.slice(0, 200) ?? null,
      timestamp: Date.now(),
    });

    // 2. Optional explicit tool calls
    let toolResults: unknown[] = [];
    if (turn.toolCalls) {
      for (const tc of turn.toolCalls) {
        const tool = this.tools[tc.name];
        if (tool) {
          const result = await tool.execute(`tc-${Date.now()}`, tc.params);
          toolResults.push({ name: tc.name, result });
        }
      }
    }

    // Simulate assistant response (the LLM response content itself)
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

    const turnDurationMs = performance.now() - turnStart;
    this.metrics.turnMetrics.push({
      turnIndex: turn.index,
      durationMs: turnDurationMs,
      hookLatencyMs: this.metrics.hookInvocations
        .filter(h => h.timestamp > turnStart)
        .reduce((sum, h) => sum + h.durationMs, 0),
      memoryInjected: !!injectedContext?.prependContext,
      toolsUsed: turn.toolCalls?.map(tc => tc.name) ?? [],
    });

    return {
      injectedContext: injectedContext?.prependContext ?? null,
      toolResults,
      messageHistory: updatedHistory,
    };
  }

  /**
   * Run the complete scenario.
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

  getMetrics(): TestMetrics { return this.metrics; }
  getLogs(): typeof this.logCapture { return this.logCapture; }
}
```

### 2.5 Instrumentation Layer

To capture GraphQL queries, cache behavior, and internal state, we intercept at three points:

**2.5.1 GraphQL Query Interceptor**

Monkey-patch `global.fetch` before loading the plugin to capture all outbound GraphQL requests:

```typescript
// tests/e2e-functional/interceptors/graphql-interceptor.ts

export interface CapturedGraphQLQuery {
  timestamp: number;
  endpoint: string;
  query: string;
  variables: Record<string, unknown>;
  durationMs: number;
  resultCount: number;
  wasBatched: boolean;
}

const captured: CapturedGraphQLQuery[] = [];
const originalFetch = globalThis.fetch;

export function installGraphQLInterceptor(): void {
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const isGraphQL = url.includes('/subgraphs/') || url.includes('graphql');

    if (!isGraphQL || !init?.body) {
      return originalFetch(input, init);
    }

    const body = JSON.parse(init.body as string);
    const startMs = performance.now();
    const response = await originalFetch(input, init);
    const durationMs = performance.now() - startMs;

    // Clone response to read body without consuming it
    const cloned = response.clone();
    const responseBody = await cloned.json();
    const resultCount = responseBody?.data?.blindIndexes?.length ?? 0;

    captured.push({
      timestamp: Date.now(),
      endpoint: url,
      query: body.query?.trim().slice(0, 200),
      variables: body.variables,
      durationMs,
      resultCount,
      wasBatched: (body.variables?.trapdoors?.length ?? 0) <= 5,
    });

    return response;
  };
}

export function getGraphQLCaptures(): CapturedGraphQLQuery[] {
  return [...captured];
}

export function resetCaptures(): void {
  captured.length = 0;
}
```

**2.5.2 Cache Behavior Monitor**

Analyze plugin logs for cache-related events:

```typescript
// tests/e2e-functional/interceptors/cache-monitor.ts

export interface CacheEvent {
  timestamp: number;
  type: 'hit' | 'miss' | 'refresh' | 'semantic_skip';
  querySimilarity?: number;
  cacheAge?: number;
}

/**
 * Parse plugin logs to infer cache behavior.
 *
 * Log patterns from index.ts:
 *   - Cache hit: hook returns with "(cached)" suffix in context lines
 *   - Semantic skip: C2 path triggered (querySimilarity > 0.85)
 *   - Cache miss: hook runs full subgraph/server query
 */
export function analyzeCacheEvents(
  logs: Array<{ level: string; timestamp: number; args: unknown[] }>,
  injections: Array<{ turnIndex: number; injected: boolean; contextSnippet: string | null }>
): CacheEvent[] {
  const events: CacheEvent[] = [];

  for (const injection of injections) {
    if (injection.contextSnippet?.includes('cached')) {
      events.push({ timestamp: Date.now(), type: 'hit' });
    } else if (injection.injected) {
      events.push({ timestamp: Date.now(), type: 'miss' });
    }
  }

  return events;
}
```

**2.5.3 Extraction Frequency Tracker**

Count how often the `agent_end` hook actually calls `extractFacts`:

```typescript
// tests/e2e-functional/interceptors/extraction-tracker.ts

export interface ExtractionEvent {
  turnIndex: number;
  timestamp: number;
  extracted: boolean;
  factCount: number;
}

/**
 * Infer extraction events from plugin logs.
 *
 * Log pattern from index.ts:
 *   "Auto-extracted and stored N memories" => extraction happened
 *   No such log entry => extraction was throttled (C3)
 */
export function analyzeExtractionEvents(
  logs: Array<{ level: string; timestamp: number; args: unknown[] }>,
  totalTurns: number,
): ExtractionEvent[] {
  const events: ExtractionEvent[] = [];
  let turnIndex = 0;

  for (const log of logs) {
    const msg = String(log.args[0] ?? '');
    if (msg.includes('Auto-extracted and stored')) {
      const match = msg.match(/stored (\d+) memories/);
      events.push({
        turnIndex,
        timestamp: log.timestamp,
        extracted: true,
        factCount: match ? parseInt(match[1], 10) : 0,
      });
    }
    // Increment turn counter on agent_end invocations (heuristic)
    if (msg.includes('agent_end') || msg.includes('extraction')) {
      turnIndex++;
    }
  }

  return events;
}
```

---

## 3. Conversation Scenarios

Each scenario is a structured sequence of turns with expected behaviors. Turns include the user message, an optional simulated assistant response, and optional explicit tool calls.

### 3.1 Scenario A: Personal Preferences (25 turns)

**Goal:** Test basic memory storage and retrieval across a realistic personal conversation. Validates B1 (importance ranking), C3 (extraction throttle), and recall quality.

| Turn | User Message | Expected Behavior |
|------|-------------|-------------------|
| 1 | "Hi there! I just moved to Portland, Oregon last month." | No injection (no prior memories). Extraction: NO (turn 1 of 5). |
| 2 | "Yeah, I'm loving it here. The food scene is incredible -- I've become obsessed with Thai food, especially pad see ew." | No injection. Extraction: NO (turn 2 of 5). |
| 3 | "For work, I'm a senior backend engineer at Stripe. I mainly work with Go and PostgreSQL." | No injection. Extraction: NO (turn 3 of 5). |
| 4 | "My work schedule is pretty flexible -- I usually start at 10am and wrap up around 6pm Pacific." | No injection. Extraction: NO (turn 4 of 5). |
| 5 | "On weekends I like hiking in the Columbia River Gorge. Eagle Creek Trail is my favorite." | No injection. Extraction: YES (turn 5 -- C3 triggers). Should extract: Portland move, Thai food preference, Stripe job, Go/PG stack, work schedule, hiking hobby. |
| 6 | "I also play guitar -- mostly fingerstyle acoustic." | No injection yet (facts still being indexed). |
| 7 | "Do you remember where I work?" | **CRITICAL**: Should inject memories mentioning Stripe, Go, PostgreSQL. B1: Stripe/job facts should rank high (importance 8+). |
| 8 | "What kind of food do I like?" | Should inject Thai food preference. B1: preference-type facts rank appropriately. |
| 9 | "ok thanks" | **B2 test**: "ok thanks" should NOT trigger memory injection (cosine < 0.3 against all stored facts). |
| 10 | "great" | **B2 test**: "great" should NOT trigger memory injection. |
| 11-15 | Mix of follow-up questions about Portland, hiking trails, work tools | Tests C2: consecutive queries about the same topic should hit the semantic cache (similarity > 0.85). |
| 16 | "Actually, I want to switch topics. What programming languages should I learn next?" | **C2 invalidation test**: Topic shift should cause cache miss (similarity to last query drops below 0.85). |
| 17 | "Remember that I'm allergic to shellfish -- this is really important for restaurant recommendations." | Explicit `totalreclaw_remember` tool call with importance 9. |
| 18-20 | "What are my dietary restrictions?", "Where do I like to eat?", "What's my work schedule?" | **Recall quality tests**: Each should return the correct stored facts. Shellfish allergy should rank high (importance 9). |
| 21-25 | Gradual wind-down conversation | C3: Extraction fires at turn 25 (turn 10 of 5). Compaction hook at end. |

**Assertions:**

```typescript
const scenarioA_assertions = {
  // C3: Extraction throttle
  'extraction_fires_at_correct_intervals': (metrics: TestMetrics) => {
    const extractions = metrics.extractionEvents.filter(e => e.extracted);
    // With 25 turns and EXTRACT_EVERY_TURNS=5, expect ~5 extractions
    assert(extractions.length >= 4 && extractions.length <= 6,
      `Expected 4-6 extractions, got ${extractions.length}`);
  },

  // B2: Relevance threshold
  'no_injection_on_greeting_turns': (metrics: TestMetrics) => {
    const turn9 = metrics.injectionEvents.find(e => e.turnIndex === 8); // 0-indexed
    const turn10 = metrics.injectionEvents.find(e => e.turnIndex === 9);
    assert(!turn9?.injected, 'Turn 9 ("ok thanks") should not have injection');
    assert(!turn10?.injected, 'Turn 10 ("great") should not have injection');
  },

  // B1: Ranking quality
  'job_facts_rank_high_on_work_query': (metrics: TestMetrics) => {
    const turn7 = metrics.injectionEvents.find(e => e.turnIndex === 6);
    assert(turn7?.injected === true, 'Turn 7 should have memory injection');
    assert(
      turn7?.contextSnippet?.toLowerCase().includes('stripe') ?? false,
      'Injected context should mention Stripe'
    );
  },

  // C2: Semantic cache
  'cache_hit_rate_on_same_topic': (metrics: TestMetrics) => {
    // Turns 11-15 are same-topic; at least 2 should be cache hits
    const sameTopic = metrics.injectionEvents.slice(10, 15);
    const cacheHits = sameTopic.filter(e =>
      e.contextSnippet?.includes('cached') ?? false
    );
    assert(cacheHits.length >= 2, `Expected >=2 cache hits on same-topic turns, got ${cacheHits.length}`);
  },
};
```

### 3.2 Scenario B: Technical Learning (20 turns)

**Goal:** Test cross-referencing of technical concepts, embedding-based semantic search, and MMR diversity (B3).

| Turn | User Message | Expected Behavior |
|------|-------------|-------------------|
| 1-5 | User describes learning Rust: ownership system, borrow checker, lifetimes, traits, async/await | Facts extracted at turn 5. |
| 6-10 | User discusses a Rust project: building a CLI tool, using Tokio for async, serde for serialization | Facts extracted at turn 10. |
| 11 | "How does Rust handle memory safety?" | Should retrieve facts about ownership, borrow checker, lifetimes. **B3**: Should NOT return 3 near-duplicate facts about ownership; MMR should diversify across ownership + borrow checker + lifetimes. |
| 12 | "What libraries am I using in my project?" | Should retrieve Tokio and serde facts. |
| 13-15 | User asks paraphrased questions that don't share exact words with stored facts | **Semantic search test**: LSH-based search should find matches despite different wording. E.g., "What did I learn about memory management in that systems language?" should retrieve Rust ownership facts. |
| 16 | Use `totalreclaw_recall` explicitly: "Rust async patterns" | **C1 test**: Tool call uses FULL search path (all trapdoor batches), not lightweight hook path. |
| 17-20 | Follow-up technical questions | Validates consistency of recall. |

**Assertions:**

```typescript
const scenarioB_assertions = {
  // B3: MMR diversity
  'diverse_results_on_memory_safety_query': (metrics: TestMetrics) => {
    const turn11 = metrics.injectionEvents.find(e => e.turnIndex === 10);
    assert(turn11?.injected === true, 'Turn 11 should have injection');
    const ctx = turn11?.contextSnippet ?? '';
    // Should mention at least 2 distinct concepts (not just "ownership" repeated)
    const concepts = ['ownership', 'borrow', 'lifetime', 'trait'];
    const mentionedConcepts = concepts.filter(c => ctx.toLowerCase().includes(c));
    assert(mentionedConcepts.length >= 2,
      `Expected >=2 distinct concepts, got: ${mentionedConcepts.join(', ')}`);
  },

  // C1: Two-tier search (tool uses full path)
  'tool_call_uses_full_search': (metrics: TestMetrics) => {
    // Turn 16 uses explicit tool -- should generate more GraphQL queries than hook
    const hookQueries = metrics.graphqlQueries.filter(q =>
      q.timestamp < metrics.turnMetrics[15]?.timestamp
    );
    const toolQueries = metrics.graphqlQueries.filter(q =>
      q.timestamp >= metrics.turnMetrics[15]?.timestamp &&
      q.timestamp <= (metrics.turnMetrics[16]?.timestamp ?? Infinity)
    );
    // Tool path should fire multiple parallel batches
    // (hook path fires 1 batch with LSH-only trapdoors)
    assert(toolQueries.length > hookQueries.length / metrics.turnMetrics.length,
      'Tool call should generate more queries than average hook call');
  },

  // Semantic recall
  'paraphrased_query_finds_facts': (metrics: TestMetrics) => {
    const turn13 = metrics.injectionEvents.find(e => e.turnIndex === 12);
    assert(turn13?.injected === true, 'Paraphrased query should still find relevant memories');
  },
};
```

### 3.3 Scenario C: Greeting/Noise Resilience (15 turns)

**Goal:** Validate that B2 (relevance threshold) prevents noise injection on conversational filler. First, seed memories; then fire a series of low-content messages.

| Turn | User Message | Expected Behavior |
|------|-------------|-------------------|
| 1 | Use `totalreclaw_remember`: "I prefer dark mode in all applications" | Explicit store. |
| 2 | Use `totalreclaw_remember`: "My favorite programming language is Python" | Explicit store. |
| 3 | Use `totalreclaw_remember`: "I have a cat named Luna" | Explicit store. |
| 4 | "thanks" | **B2**: No injection. Cosine("thanks", any stored fact) < 0.3. |
| 5 | "ok" | **B2**: No injection. |
| 6 | "got it" | **B2**: No injection. |
| 7 | "sure thing" | **B2**: No injection. |
| 8 | "lol" | **B2**: No injection. Also below 5-char threshold (length < 5). |
| 9 | "yeah that makes sense" | **B2**: No injection. Generic agreement. |
| 10 | "cool cool cool" | **B2**: No injection. |
| 11 | "Tell me about my cat" | **Should inject** Luna fact. Validates that B2 doesn't over-filter. |
| 12 | "What programming language do I use?" | **Should inject** Python fact. |
| 13 | "Do I prefer light mode or dark mode?" | **Should inject** dark mode fact. |
| 14 | "haha nice" | **B2**: No injection. |
| 15 | "bye!" | **B2**: No injection. |

**Assertions:**

```typescript
const scenarioC_assertions = {
  // B2: No injection on noise turns
  'no_injection_on_noise': (metrics: TestMetrics) => {
    const noiseTurns = [3, 4, 5, 6, 7, 8, 9, 13, 14]; // 0-indexed
    for (const idx of noiseTurns) {
      const event = metrics.injectionEvents.find(e => e.turnIndex === idx);
      assert(!event?.injected, `Turn ${idx + 1} should NOT have injection`);
    }
  },

  // B2: Relevant queries still get injection
  'injection_on_relevant_queries': (metrics: TestMetrics) => {
    const relevantTurns = [10, 11, 12]; // 0-indexed: "cat", "programming", "dark mode"
    for (const idx of relevantTurns) {
      const event = metrics.injectionEvents.find(e => e.turnIndex === idx);
      assert(event?.injected === true, `Turn ${idx + 1} should have injection`);
    }
  },

  // Token savings: noise turns should have 0 injected tokens
  'token_savings_on_noise': (metrics: TestMetrics) => {
    const noiseTurns = metrics.injectionEvents.filter(
      (e, i) => [3, 4, 5, 6, 7, 8, 9, 13, 14].includes(e.turnIndex)
    );
    const totalInjectedChars = noiseTurns.reduce(
      (sum, e) => sum + (e.contextSnippet?.length ?? 0), 0
    );
    assert(totalInjectedChars === 0, `Expected 0 injected chars on noise turns, got ${totalInjectedChars}`);
  },
};
```

### 3.4 Scenario D: Topic Shifts (30 turns)

**Goal:** Test cache invalidation on topic change (C1/C2) and diversity in results (B3) when memories span multiple topics.

| Phase | Turns | Topic | Key Tests |
|-------|-------|-------|-----------|
| Phase 1 | 1-8 | Cooking recipes (Italian food, pasta techniques, knife skills) | Seed cooking memories. C2: turns 6-8 should cache-hit. |
| Phase 2 | 9-16 | Travel planning (Japan trip, booking flights, Kyoto temples) | **Topic shift at turn 9**: cache miss expected. Seed travel memories. |
| Phase 3 | 17-22 | Fitness goals (marathon training, running schedule, nutrition) | **Topic shift at turn 17**: cache miss expected. Seed fitness memories. |
| Phase 4 | 23-30 | Cross-topic recall questions | Turn 23: "What are all my hobbies?" (should pull from cooking + travel + fitness). **B3 MMR**: Results should be diverse across topics, not all from one topic. |

**Assertions:**

```typescript
const scenarioD_assertions = {
  // C2: Cache invalidation on topic shift
  'cache_miss_on_topic_shift': (metrics: TestMetrics) => {
    // Turn 9 (topic shift to travel) should NOT be a cache hit
    const turn9 = metrics.injectionEvents.find(e => e.turnIndex === 8);
    assert(
      !(turn9?.contextSnippet?.includes('cached') ?? false),
      'Turn 9 (topic shift) should not be a cache hit'
    );
    // Turn 17 (topic shift to fitness) should NOT be a cache hit
    const turn17 = metrics.injectionEvents.find(e => e.turnIndex === 16);
    assert(
      !(turn17?.contextSnippet?.includes('cached') ?? false),
      'Turn 17 (topic shift) should not be a cache hit'
    );
  },

  // C2: Cache hits within a topic
  'cache_hits_within_topic': (metrics: TestMetrics) => {
    // Turns 6-8 (same cooking topic) should have at least 1 cache hit
    const cookingTurns = metrics.injectionEvents.slice(5, 8);
    const hits = cookingTurns.filter(e => e.contextSnippet?.includes('cached'));
    assert(hits.length >= 1, `Expected >=1 cache hit in cooking phase, got ${hits.length}`);
  },

  // B3: Cross-topic diversity
  'cross_topic_diversity': (metrics: TestMetrics) => {
    // Turn 23: "What are all my hobbies?" should mention multiple topics
    const turn23 = metrics.injectionEvents.find(e => e.turnIndex === 22);
    const ctx = (turn23?.contextSnippet ?? '').toLowerCase();
    const topics = {
      cooking: ['cook', 'pasta', 'italian', 'recipe', 'knife'],
      travel: ['japan', 'kyoto', 'flight', 'temple', 'travel'],
      fitness: ['marathon', 'running', 'training', 'nutrition', 'fitness'],
    };
    let topicsCovered = 0;
    for (const [, keywords] of Object.entries(topics)) {
      if (keywords.some(k => ctx.includes(k))) topicsCovered++;
    }
    assert(topicsCovered >= 2,
      `Expected memories from >=2 topics, got ${topicsCovered}`);
  },
};
```

### 3.5 Scenario E: Long Conversation / Extraction Throttle (55 turns)

**Goal:** Validate C3 (extraction fires every 5 turns, not every turn) over a long conversation, and test compaction hook behavior.

| Phase | Turns | Content |
|-------|-------|---------|
| 1 | 1-25 | User discusses their daily routine, meal plans, exercise, and work projects. Rich factual content every turn. |
| 2 | 26-50 | User discusses a vacation they took, books they read, movies they watched. Continued rich content. |
| 3 | 51-55 | Wind-down, then trigger `before_compaction` hook. |

**Assertions:**

```typescript
const scenarioE_assertions = {
  // C3: Extraction frequency
  'extraction_every_5_turns': (metrics: TestMetrics) => {
    const extractions = metrics.extractionEvents.filter(e => e.extracted);
    // 55 turns / 5 = 11 expected extractions
    assert(extractions.length >= 9 && extractions.length <= 13,
      `Expected 9-13 extractions for 55 turns, got ${extractions.length}`);
  },

  // C3: No extraction on non-5th turns
  'no_extraction_on_intermediate_turns': (metrics: TestMetrics) => {
    // Check that turns 1-4, 6-9, etc. did NOT trigger extraction
    const nonExtractionTurns = metrics.extractionEvents.filter(e => !e.extracted);
    // Should be ~44 non-extraction turns (55 - 11)
    assert(nonExtractionTurns.length >= 40,
      `Expected ~44 non-extraction turns, got ${nonExtractionTurns.length}`);
  },

  // Compaction: before_compaction extracts ALL remaining facts
  'compaction_extracts_all': (metrics: TestMetrics) => {
    const compactionLog = metrics.hookInvocations.find(
      h => h.hookName === 'before_compaction'
    );
    assert(compactionLog != null, 'before_compaction hook should fire');
    assert(compactionLog!.durationMs > 0, 'Compaction should do actual work');
  },

  // Baseline comparison: extraction count should be ~80% lower than baseline
  'extraction_reduction_vs_baseline': (
    improvedMetrics: TestMetrics,
    baselineMetrics: TestMetrics
  ) => {
    const improvedCount = improvedMetrics.extractionEvents.filter(e => e.extracted).length;
    const baselineCount = baselineMetrics.extractionEvents.filter(e => e.extracted).length;
    const reduction = 1 - (improvedCount / baselineCount);
    assert(reduction >= 0.7,
      `Expected >=70% extraction reduction, got ${(reduction * 100).toFixed(1)}%`);
  },
};
```

### 3.6 Scenario F: Subgraph-Specific Improvements (20 turns)

**Goal:** Validate A2 (parallel batches), A3 (ordering), A4 (pagination) in the subgraph search path. Only runs against instances C and D.

| Turn | User Message | Expected Behavior |
|------|-------------|-------------------|
| 1-10 | Seed 50+ facts using `totalreclaw_remember` (varied topics: work, hobbies, preferences, travel, food, pets, health, goals, decisions, events) | Build up a realistic fact corpus. Each turn stores 5 facts. |
| 11 | "What do I like to eat for dinner?" | **A2**: GraphQL captures should show multiple parallel batches (TRAPDOOR_BATCH_SIZE=5). Check that batch count = ceil(trapdoors / 5). |
| 12 | "Tell me everything about my work" | **A2+A3**: Should retrieve work-related facts. With ordering (A3: `orderBy: id, orderDirection: desc`), newest work facts should appear first. |
| 13 | Use `totalreclaw_recall` with broad query: "everything I've told you" | **A4 pagination test**: If any batch returns exactly 1000 results, pagination should kick in. (May not trigger with only 50 facts -- see note.) |
| 14-20 | Recall queries targeting specific stored facts | **Recall@8 measurement**: Track how many of the 50 stored facts can be correctly recalled. |

**Note on A4:** Cursor-based pagination only activates when a batch returns exactly 1000 results (PAGE_SIZE). With 50 facts, this is unlikely. To properly test A4, we need a separate stress scenario that ingests 500+ facts first. See Scenario G.

**Assertions:**

```typescript
const scenarioF_assertions = {
  // A2: Parallel batches observed
  'parallel_batches_in_graphql': (metrics: TestMetrics) => {
    // For a single search, multiple GraphQL queries should fire ~simultaneously
    // (within 50ms of each other = parallel, not sequential)
    const searchQueries = metrics.graphqlQueries.filter(q =>
      q.query.includes('SearchByBlindIndex')
    );
    if (searchQueries.length >= 2) {
      const timestamps = searchQueries.map(q => q.timestamp).sort();
      const maxGap = Math.max(...timestamps.slice(1).map((t, i) => t - timestamps[i]));
      assert(maxGap < 200, `Expected parallel queries (max gap < 200ms), got ${maxGap}ms`);
    }
  },

  // A2: Batch size of 5
  'batch_size_is_5': (metrics: TestMetrics) => {
    const batchedQueries = metrics.graphqlQueries.filter(q => q.wasBatched);
    for (const q of batchedQueries) {
      const trapdoorCount = (q.variables as any)?.trapdoors?.length ?? 0;
      assert(trapdoorCount <= 5,
        `Expected batch size <=5, got ${trapdoorCount}`);
    }
  },

  // A3: Results ordered by ID descending
  'results_ordered_by_recency': (metrics: TestMetrics) => {
    // Check that GraphQL queries include orderBy and orderDirection
    const searchQueries = metrics.graphqlQueries.filter(q =>
      q.query.includes('SearchByBlindIndex')
    );
    for (const q of searchQueries) {
      assert(q.query.includes('orderBy: id') || q.query.includes('orderBy:id'),
        'Query should include orderBy: id');
      assert(q.query.includes('orderDirection: desc') || q.query.includes('orderDirection:desc'),
        'Query should include orderDirection: desc');
    }
  },
};
```

### 3.7 Scenario G: Subgraph Pagination Stress Test (10 turns + 500 pre-seeded facts)

**Goal:** Force A4 (cursor-based pagination) to activate by pre-loading enough facts to saturate a batch.

**Setup:** Before running turns, directly ingest 500 facts using the E2E benchmark's ingestion pipeline (reusing code from `subgraph/tests/e2e-ombh-validation.ts`). This creates enough blind index entries that queries will hit the PAGE_SIZE (1000) limit.

| Turn | User Message | Expected Behavior |
|------|-------------|-------------------|
| 1 | "What did I learn about cooking?" | With 500 facts, blind index matches may saturate. A4: Check for `PaginateBlindIndex` queries in GraphQL captures. |
| 2-5 | Varied recall queries targeting common terms | Monitor for pagination queries. |
| 6-10 | Recall queries targeting rare terms (should NOT paginate) | Confirm pagination only fires when batch is saturated. |

**Assertions:**

```typescript
const scenarioG_assertions = {
  // A4: Pagination observed on saturated batches
  'pagination_queries_fired': (metrics: TestMetrics) => {
    const paginationQueries = metrics.graphqlQueries.filter(q =>
      q.query.includes('PaginateBlindIndex')
    );
    assert(paginationQueries.length > 0,
      'Expected at least 1 pagination query on saturated batch');
  },

  // A4: Pagination only on saturated batches
  'pagination_only_when_saturated': (metrics: TestMetrics) => {
    // Rare-term queries (turns 6-10) should NOT trigger pagination
    const rareTurnStart = metrics.turnMetrics[5]?.timestamp ?? Infinity;
    const paginationAfterRare = metrics.graphqlQueries.filter(q =>
      q.query.includes('PaginateBlindIndex') && q.timestamp > rareTurnStart
    );
    assert(paginationAfterRare.length === 0,
      'Rare-term queries should not trigger pagination');
  },
};
```

### 3.8 Scenario H: LLM-Driven Freeform Conversation (30 turns)

**Goal:** Use an actual LLM (Claude API) to generate both sides of the conversation, creating a fully realistic interaction pattern that no human-scripted scenario can replicate.

**Architecture:**

```
+-----------------+     user msg      +------------------+
| Conversation    | ----------------> | OpenClaw + Plugin |
| Orchestrator    |     context +     |  (mock lifecycle) |
| (Claude API)    | <---------------- |                   |
|                 |     injection     +------------------+
+-----------------+
        |
        v (sends next user message based on persona + conversation history)
```

The orchestrator uses a Claude API call with a persona prompt to generate user messages. The persona is designed to naturally introduce personal facts, ask follow-up questions, change topics, and produce noise turns.

```typescript
// tests/e2e-functional/llm-orchestrator.ts

const PERSONA_PROMPT = `You are a user having a conversation with an AI assistant.
Your persona:
- Name: Alex Chen
- Age: 32
- Job: Product designer at a fintech startup
- Location: Austin, TX (recently moved from Chicago)
- Hobbies: rock climbing, photography, making sourdough bread
- Dietary: vegetarian, lactose intolerant
- Pet: a golden retriever named Max
- Goal: learning Spanish, training for a half-marathon
- Recent: just got engaged, planning a wedding for fall 2026

Instructions:
- Have a natural, flowing conversation
- Mention personal details gradually over multiple turns
- Sometimes ask the assistant to remember specific things
- Sometimes ask "do you remember..." questions
- Include some short replies like "thanks", "ok", "got it" (about 20% of turns)
- Change topics naturally every 5-8 turns
- After turn 20, start asking recall questions about things mentioned earlier
- Be specific with details (dates, names, numbers) -- these are testable

Output ONLY the next user message, nothing else.`;

async function generateNextUserMessage(
  conversationHistory: Array<{ role: string; content: string }>,
  turnIndex: number,
): Promise<string> {
  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': process.env.ANTHROPIC_API_KEY!,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-3-5-haiku-20241022',
      max_tokens: 300,
      system: PERSONA_PROMPT,
      messages: [
        ...conversationHistory.map(m => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
        })),
        {
          role: 'user',
          content: `[Turn ${turnIndex + 1}/30. Generate the next message from Alex.]`,
        },
      ],
    }),
  });

  const data = await response.json();
  return data.content[0].text;
}
```

**Assertions:** This scenario uses statistical assertions rather than per-turn checks:

```typescript
const scenarioH_assertions = {
  // Overall injection rate should be 40-80% (not every turn)
  'reasonable_injection_rate': (metrics: TestMetrics) => {
    const injected = metrics.injectionEvents.filter(e => e.injected).length;
    const rate = injected / metrics.injectionEvents.length;
    assert(rate >= 0.3 && rate <= 0.85,
      `Expected 30-85% injection rate, got ${(rate * 100).toFixed(1)}%`);
  },

  // B2: At least some turns should have no injection (noise filtering)
  'noise_filtering_active': (metrics: TestMetrics) => {
    const noInjection = metrics.injectionEvents.filter(e => !e.injected).length;
    assert(noInjection >= 3,
      `Expected >=3 turns with no injection (noise), got ${noInjection}`);
  },

  // Latency: Hook p95 should be under 500ms
  'hook_latency_p95': (metrics: TestMetrics) => {
    const latencies = metrics.hookInvocations
      .filter(h => h.hookName === 'before_agent_start')
      .map(h => h.durationMs)
      .sort((a, b) => a - b);
    const p95Index = Math.floor(latencies.length * 0.95);
    const p95 = latencies[p95Index] ?? 0;
    assert(p95 < 500, `Expected hook p95 < 500ms, got ${p95.toFixed(0)}ms`);
  },
};
```

---

## 4. Metrics and Assertions Summary

### 4.1 Type Definitions

```typescript
// tests/e2e-functional/types.ts

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

export interface ConversationScenario {
  id: string;
  name: string;
  description: string;
  pluginPath: string;  // Path to plugin module (improved or baseline)
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
```

### 4.2 Metrics Collection

All metrics are aggregated into a JSON report at the end of each test run:

```typescript
// tests/e2e-functional/report.ts

interface TestReport {
  timestamp: string;
  duration_seconds: number;
  instances: {
    [instanceId: string]: {
      scenarios: {
        [scenarioId: string]: {
          metrics: TestMetrics;
          assertions: {
            [name: string]: { passed: boolean; message: string };
          };
        };
      };
    };
  };
  comparison: ComparisonMatrix;
  summary: {
    total_assertions: number;
    passed: number;
    failed: number;
    scenarios_run: number;
    instances_used: number;
  };
}
```

### 4.3 Full Assertion Matrix

| ID | Assertion | Improvement | Scenarios | Pass Criteria |
|----|-----------|-------------|-----------|---------------|
| C3-1 | Extraction fires every 5 turns | C3 | A, E | Extraction count = floor(turns / 5) +/- 1 |
| C3-2 | No extraction on intermediate turns | C3 | E | >= 80% of turns have no extraction |
| C3-3 | 70%+ reduction vs baseline | C3 | E (comparison) | Improved extractions / baseline extractions <= 0.3 |
| B2-1 | No injection on greeting turns | B2 | A, C | Specific greeting turns have injected = false |
| B2-2 | Injection on relevant queries | B2 | C | Specific recall turns have injected = true |
| B2-3 | 0 chars injected on noise turns | B2 | C | Sum of context length on noise turns = 0 |
| B1-1 | Important facts rank high | B1 | A | Job/allergy facts appear in top 3 of injection |
| B1-2 | Recency-weighted results differ | B1 | E comparison | Instance E (recency-heavy) returns different ordering than A |
| B3-1 | Diverse results across concepts | B3 | B | >= 2 distinct concepts in a single injection |
| B3-2 | Cross-topic diversity | B3 | D | >= 2 topic clusters in cross-topic query results |
| C1-1 | Hook uses lightweight search | C1 | B, F | Hook path generates fewer GraphQL queries than tool path |
| C1-2 | Tool uses full search | C1 | B | Explicit recall tool fires all trapdoor batches |
| C2-1 | Cache hit on same-topic turns | C2 | A, D | >= 1 cache hit per same-topic sequence (3+ turns) |
| C2-2 | Cache miss on topic shift | C2 | D | First turn after topic shift is not a cache hit |
| A2-1 | Parallel batches observed | A2 | F | Multiple GraphQL queries within 200ms of each other |
| A2-2 | Batch size <= 5 | A2 | F | All batched queries have <= 5 trapdoors |
| A3-1 | orderBy and orderDirection in query | A3 | F | GraphQL query text includes sort parameters |
| A4-1 | Pagination queries fire on saturation | A4 | G | PaginateBlindIndex query observed |
| A4-2 | No pagination on unsaturated batches | A4 | G | No pagination queries for rare-term searches |
| LAT-1 | Hook p95 latency < 500ms | All | H | 95th percentile of before_agent_start latency |
| INJ-1 | Injection rate 30-85% | All | H | Not too aggressive, not too conservative |
| CMP-1 | Compaction extracts remaining facts | C3 | E | before_compaction hook fires and extracts |

---

## 5. Comparison Matrix

### 5.1 Server: Improved vs Baseline

| Metric | Improved (A) | Baseline (B) | Delta | Target |
|--------|-------------|-------------|-------|--------|
| Extraction calls per 50 turns | ~10 | ~50 | -80% | >= -70% |
| Noise injection rate (% of greeting turns with injection) | 0% | 100% | -100% | 0% injections on greetings |
| Average injected context length (chars) | Lower | Higher | Negative | Meaningful reduction |
| Hook latency p50 (ms) | ~X | ~Y | -% | Improved or equal |
| Hook latency p95 (ms) | ~X | ~Y | -% | < 500ms |
| Recall accuracy (% of explicit recall queries with correct answer in top 3) | >= 80% | >= 75% | Improved | >= 80% |
| Cache hit rate (same-topic sequences) | > 30% | 0% | +30%+ | > 20% |

### 5.2 Subgraph: Improved vs Baseline

| Metric | Improved (C) | Baseline (D) | Delta | Target |
|--------|-------------|-------------|-------|--------|
| GraphQL queries per search (hook) | 1 (LSH-only) | 1 (all trapdoors) | Similar | <= baseline |
| GraphQL queries per search (tool) | 4-8 parallel | 1 sequential | More queries but parallel | Wall-clock <= baseline |
| Recall accuracy (% correct in top 3) | >= 70% | <= 50% | +20%+ | >= 70% |
| Pagination observed | Yes (on saturation) | No | New feature | Activated when needed |
| Batch size per query | <= 5 | 500 (all trapdoors) | -99% | <= 5 |

### 5.3 Subgraph Improved vs Server Improved

| Metric | Subgraph (C) | Server (A) | Delta | Acceptable |
|--------|-------------|-----------|-------|------------|
| Recall accuracy | >= 70% | >= 80% | <= -10% | Yes (known gap) |
| Hook latency p95 | ~200ms | ~150ms | +33% | Yes (network overhead) |
| Cache behavior | Identical | Identical | 0 | Must match |
| B2 threshold behavior | Identical | Identical | 0 | Must match |
| C3 throttle behavior | Identical | Identical | 0 | Must match |

---

## 6. Monitoring and Instrumentation

### 6.1 What to Capture

| Data Point | Source | How Captured |
|------------|--------|-------------|
| Hook invocations (name, timing, return value) | Mock plugin API | `api.on()` wrapper in ConversationDriver |
| GraphQL queries (count, batching, variables, timing) | `global.fetch` interceptor | `graphql-interceptor.ts` |
| Cache hit/miss/skip | Plugin logs + injection content analysis | Log pattern matching for "(cached)" |
| Extraction frequency | Plugin logs | Log pattern matching for "Auto-extracted" |
| Memory injection content per turn | `before_agent_start` return value | Captured in `fireHook()` |
| Token usage per turn (approximate) | Injection context length | Character count / 4 |
| Tool calls (name, params, timing) | Mock tool execute wrapper | `registerTool()` capture |
| Total scenario duration | Test runner | `performance.now()` delta |

### 6.2 Log Levels and Filtering

The instrumentation layer captures ALL plugin log output (info, warn, error) and categorizes it:

```typescript
interface StructuredLog {
  timestamp: number;
  level: 'info' | 'warn' | 'error';
  category: 'init' | 'search' | 'cache' | 'extraction' | 'store' | 'hook' | 'other';
  message: string;
  metadata?: Record<string, unknown>;
}

function categorizeLog(args: unknown[]): StructuredLog['category'] {
  const msg = String(args[0] ?? '');
  if (msg.includes('initialized') || msg.includes('Registered') || msg.includes('loaded')) return 'init';
  if (msg.includes('search') || msg.includes('Fact count') || msg.includes('candidate')) return 'search';
  if (msg.includes('cache') || msg.includes('cached')) return 'cache';
  if (msg.includes('extract') || msg.includes('Auto-extracted')) return 'extraction';
  if (msg.includes('store') || msg.includes('Memory stored')) return 'store';
  if (msg.includes('hook') || msg.includes('before_agent_start') || msg.includes('agent_end')) return 'hook';
  return 'other';
}
```

### 6.3 GraphQL Query Analysis

For subgraph instances, the interceptor provides:

```typescript
interface GraphQLAnalysis {
  totalQueries: number;
  searchQueries: number;      // SearchByBlindIndex
  paginationQueries: number;  // PaginateBlindIndex
  factCountQueries: number;   // FactCount (globalStates)
  avgBatchSize: number;       // Average trapdoor count per query
  maxParallelBatch: number;   // Max queries within 100ms window
  avgQueryLatency: number;    // Average GraphQL response time
  p95QueryLatency: number;
  totalResultsReturned: number;
  saturatedBatches: number;   // Batches returning exactly PAGE_SIZE results
}

function analyzeGraphQL(queries: CapturedGraphQLQuery[]): GraphQLAnalysis {
  const search = queries.filter(q => q.query.includes('SearchByBlindIndex'));
  const paginate = queries.filter(q => q.query.includes('PaginateBlindIndex'));
  const factCount = queries.filter(q => q.query.includes('FactCount') || q.query.includes('globalStates'));

  // Detect parallel batches: count queries within 100ms windows
  const sorted = [...search].sort((a, b) => a.timestamp - b.timestamp);
  let maxParallel = 0;
  for (let i = 0; i < sorted.length; i++) {
    let count = 1;
    for (let j = i + 1; j < sorted.length && sorted[j].timestamp - sorted[i].timestamp < 100; j++) {
      count++;
    }
    maxParallel = Math.max(maxParallel, count);
  }

  const latencies = queries.map(q => q.durationMs).sort((a, b) => a - b);

  return {
    totalQueries: queries.length,
    searchQueries: search.length,
    paginationQueries: paginate.length,
    factCountQueries: factCount.length,
    avgBatchSize: search.reduce((sum, q) => sum + ((q.variables as any)?.trapdoors?.length ?? 0), 0) / Math.max(search.length, 1),
    maxParallelBatch: maxParallel,
    avgQueryLatency: latencies.reduce((a, b) => a + b, 0) / Math.max(latencies.length, 1),
    p95QueryLatency: latencies[Math.floor(latencies.length * 0.95)] ?? 0,
    totalResultsReturned: queries.reduce((sum, q) => sum + q.resultCount, 0),
    saturatedBatches: search.filter(q => q.resultCount >= 1000).length,
  };
}
```

---

## 7. Implementation Approach

### 7.1 Directory Structure

```
tests/e2e-functional/
  README.md                         # Setup instructions
  docker-compose.yml                # Infrastructure for all instances
  package.json                      # Dependencies (tsx, @anthropic-ai/sdk)
  tsconfig.json
  run-all.ts                        # Main entry point: runs all scenarios x all instances
  run-scenario.ts                   # Run a single scenario on a single instance
  conversation-driver.ts            # Core: mock plugin API + turn executor
  llm-orchestrator.ts               # Claude API for Scenario H
  types.ts                          # All shared type definitions
  report.ts                         # JSON report generation + comparison matrix
  scenarios/
    scenario-a-preferences.ts       # Personal preferences (25 turns)
    scenario-b-technical.ts         # Technical learning (20 turns)
    scenario-c-noise.ts             # Greeting/noise resilience (15 turns)
    scenario-d-topics.ts            # Topic shifts (30 turns)
    scenario-e-long.ts              # Long conversation / throttle (55 turns)
    scenario-f-subgraph.ts          # Subgraph-specific (20 turns)
    scenario-g-pagination.ts        # Pagination stress test (10 turns + 500 pre-seeded)
    scenario-h-freeform.ts          # LLM-driven freeform (30 turns)
  interceptors/
    graphql-interceptor.ts          # Monkey-patches fetch for GraphQL capture
    cache-monitor.ts                # Analyzes logs for cache events
    extraction-tracker.ts           # Analyzes logs for extraction frequency
  assertions/
    scenario-assertions.ts          # All per-scenario assertion functions
    comparison-assertions.ts        # Cross-instance comparison assertions
  results/                          # Output directory for JSON reports
```

### 7.2 Dependencies

```json
{
  "name": "totalreclaw-e2e-functional",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "test": "tsx run-all.ts",
    "test:scenario": "tsx run-scenario.ts",
    "test:server": "tsx run-all.ts --instances=server-improved,server-baseline",
    "test:subgraph": "tsx run-all.ts --instances=subgraph-improved,subgraph-baseline",
    "test:quick": "tsx run-all.ts --scenarios=C,H --instances=server-improved",
    "report": "tsx report.ts"
  },
  "dependencies": {
    "tsx": "^4.0.0",
    "typescript": "^5.0.0",
    "@anthropic-ai/sdk": "^0.25.0"
  }
}
```

### 7.3 Execution Flow

```
run-all.ts
  |
  +-- For each instance (A, B, C, D, E):
  |     |
  |     +-- Set environment variables for the instance
  |     +-- Install GraphQL interceptor (if subgraph mode)
  |     +-- For each applicable scenario:
  |     |     |
  |     |     +-- Create ConversationDriver(instanceId, scenario)
  |     |     +-- driver.initialize() -- loads plugin with mock API
  |     |     +-- driver.runScenario() -- executes all turns
  |     |     +-- Collect TestMetrics
  |     |     +-- Run assertions
  |     |     +-- Reset module state (re-import with fresh counters)
  |     |
  |     +-- Collect per-instance results
  |
  +-- Run comparison assertions (improved vs baseline)
  +-- Generate JSON report
  +-- Print summary to stdout
```

**Scenario applicability:**

| Scenario | A (server-imp) | B (server-base) | C (subgraph-imp) | D (subgraph-base) | E (server-recency) |
|----------|:-:|:-:|:-:|:-:|:-:|
| A: Preferences | X | X | X | X | X |
| B: Technical | X | X | X | | |
| C: Noise | X | X | | | |
| D: Topics | X | X | X | | |
| E: Long | X | X | | | |
| F: Subgraph | | | X | X | |
| G: Pagination | | | X | X | |
| H: Freeform | X | | X | | |

### 7.4 Module Isolation

Each scenario needs fresh plugin state (counters, cache, etc.). To achieve this without process restarts, we use Node.js module cache invalidation:

```typescript
function resetPluginState(): void {
  // Clear Node.js module cache for the plugin
  const pluginPath = require.resolve('../../skill/plugin/index.js');
  delete require.cache[pluginPath];

  // Also reset any modules that hold state
  const modules = [
    '../../skill/plugin/hot-cache-wrapper.js',
    '../../skill/plugin/subgraph-search.js',
    '../../skill/plugin/reranker.js',
  ];
  for (const mod of modules) {
    try {
      const resolved = require.resolve(mod);
      delete require.cache[resolved];
    } catch {}
  }
}
```

For ESM (which this project uses), we use dynamic `import()` with query-string cache busting:

```typescript
async function loadFreshPlugin(pluginPath: string, runId: string): Promise<any> {
  // Append unique query string to bust ESM cache
  return import(`${pluginPath}?run=${runId}`);
}
```

### 7.5 Handling Baseline vs Improved Code

Two approaches, in order of preference:

**Option 1: Feature Flags (recommended)**

The improvements are controlled by environment variables and code-level feature flags. The "baseline" configuration uses:

```bash
TOTALRECLAW_RELEVANCE_THRESHOLD=0.0   # B2 disabled
TOTALRECLAW_EXTRACT_EVERY_TURNS=1     # C3 disabled
TOTALRECLAW_CACHE_TTL_MS=0            # C2 disabled
TOTALRECLAW_TWO_TIER_SEARCH=false     # C1 disabled
```

This requires adding a few feature flags to `index.ts` (see Section 8, Implementation Tasks).

**Option 2: Git Checkout (alternative)**

For A1-A5 improvements that are structural code changes (not toggle-able), the baseline instances check out the pre-improvement commit:

```bash
# Pre-improvement commit hash (before Category A changes)
BASELINE_COMMIT="e4e098e"  # Last commit before improvements
```

This is more complex to manage. Option 1 is preferred.

---

## 8. Implementation Tasks

### 8.1 Prerequisites (must be done before tests can run)

| Task | Effort | Description |
|------|--------|-------------|
| P1 | 30 min | Add feature flags to `skill/plugin/index.ts` for C1 (`TOTALRECLAW_TWO_TIER_SEARCH`), C2 (`TOTALRECLAW_CACHE_TTL_MS`), and A2 (`TOTALRECLAW_TRAPDOOR_BATCH_SIZE`) |
| P2 | 15 min | Ensure all module-level state in `index.ts` can be reset for test isolation (export a `__resetForTesting()` function) |
| P3 | 15 min | Make `TOTALRECLAW_SUBGRAPH_MODE` actually switchable via env var in `subgraph-store.ts` |

### 8.2 Test Infrastructure

| Task | Effort | Description |
|------|--------|-------------|
| T1 | 2 hrs | Create `tests/e2e-functional/` directory structure, `package.json`, `tsconfig.json` |
| T2 | 3 hrs | Implement `conversation-driver.ts` (mock plugin API, hook firing, turn execution) |
| T3 | 1 hr | Implement `interceptors/graphql-interceptor.ts` (fetch monkey-patch) |
| T4 | 1 hr | Implement `interceptors/cache-monitor.ts` and `extraction-tracker.ts` |
| T5 | 1 hr | Implement `types.ts` with all metric/scenario interfaces |
| T6 | 2 hrs | Implement `report.ts` (JSON report generation, comparison matrix, stdout summary) |
| T7 | 1 hr | Create `docker-compose.yml` for test infrastructure |

### 8.3 Scenario Implementation

| Task | Effort | Description |
|------|--------|-------------|
| S1 | 2 hrs | Implement Scenario A (preferences, 25 turns with assertions) |
| S2 | 2 hrs | Implement Scenario B (technical learning, 20 turns) |
| S3 | 1 hr | Implement Scenario C (noise resilience, 15 turns) |
| S4 | 2 hrs | Implement Scenario D (topic shifts, 30 turns) |
| S5 | 1 hr | Implement Scenario E (long conversation, 55 turns) |
| S6 | 2 hrs | Implement Scenario F (subgraph-specific, 20 turns) |
| S7 | 3 hrs | Implement Scenario G (pagination stress, seeding pipeline + 10 turns) |
| S8 | 2 hrs | Implement Scenario H (LLM-driven freeform, Claude API integration) |

### 8.4 Assertion and Comparison

| Task | Effort | Description |
|------|--------|-------------|
| A1 | 2 hrs | Implement all per-scenario assertions from Section 4.3 |
| A2 | 1 hr | Implement cross-instance comparison assertions |
| A3 | 1 hr | Implement `run-all.ts` orchestrator |

### 8.5 Total Estimated Effort

| Category | Effort |
|----------|--------|
| Prerequisites | 1 hour |
| Test infrastructure (T1-T7) | 11 hours |
| Scenarios (S1-S8) | 15 hours |
| Assertions (A1-A3) | 4 hours |
| **Total** | **~31 hours** (~4 working days) |

### 8.6 Recommended Implementation Order

1. **Day 1:** P1-P3 (prerequisites) + T1, T2, T5 (core driver + types)
2. **Day 2:** T3, T4 (interceptors) + S3 (noise -- simplest scenario, validates B2)
3. **Day 3:** S1 (preferences) + S5 (long conversation) + A1 (assertions)
4. **Day 4:** S2, S4 (technical + topics) + T6 (report) + A2, A3 (comparison + orchestrator)
5. **Day 5:** T7 (docker) + S6, S7 (subgraph scenarios) + S8 (LLM freeform)
6. **Day 6:** Integration testing, debugging, final report validation

---

## 9. Acceptance Criteria

The test suite is considered passing when:

1. **All 21 assertions from Section 4.3 pass** on the improved instances (A, C, E)
2. **Comparison assertions show improvement:**
   - C3: >= 70% extraction reduction (improved vs baseline)
   - B2: 0% noise injection rate on improved (vs 100% on baseline)
   - C2: > 0% cache hit rate on improved (vs 0% on baseline)
3. **No regressions:**
   - Recall accuracy on improved >= baseline (or within 5% margin)
   - Hook latency p95 on improved <= baseline * 1.5
4. **Subgraph-specific:**
   - A2: Parallel batches observed (max gap < 200ms between batch queries)
   - A3: orderBy/orderDirection present in all search queries
   - A4: Pagination fires when batches saturate (500+ facts)
5. **LLM freeform (Scenario H):**
   - Injection rate between 30-85%
   - At least 3 noise-filtered turns
   - Hook p95 < 500ms

---

## 10. Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Plugin module isolation fails (state leaks between scenarios) | HIGH | Export `__resetForTesting()` from index.ts; use subprocess per scenario as fallback |
| LLM API calls in extraction make tests slow and expensive | MEDIUM | Mock extraction LLM in Scenarios A-G (only Scenario H uses real LLM). Use deterministic extracted facts. |
| Graph Node takes too long to index during subgraph tests | MEDIUM | Pre-seed facts before test starts; add polling loop for indexing completion |
| Scenario H (LLM-driven) produces non-deterministic results | LOW | Use statistical assertions (ranges) not exact matches. Run 3x and require 2/3 pass. |
| Baseline plugin code diverges as new improvements are added | LOW | Feature flags (Section 7.5, Option 1) avoid needing to maintain separate code branches |
| Hardhat localhost is too slow for 500-fact seeding in Scenario G | MEDIUM | Use Hardhat's `evm_mine` batch mining; accept ~30s seeding time |

---

## 11. Future Extensions

After initial implementation, the test suite can be extended to cover:

1. **D1-D3 (Write-path optimization):** Add gas measurement to subgraph scenarios; compare batch vs single-tx writes.
2. **E1 (Stable prefix / Observational Memory):** Add Scenario I testing stable prefix cache behavior over 50+ turns.
3. **E2 (Tiered memory categories):** Modify Scenario A to validate that preferences decay slower than episodic facts.
4. **Multi-user isolation:** Run two conversation drivers simultaneously against the same server, verifying zero cross-user leakage.
5. **5-instance comparison benchmark (from totalreclaw-internal, private, maintainers only):** Once the test infra is stable, port the existing 5-way comparison harness to use this framework for apples-to-apples comparisons.
6. **Regression CI:** Run Scenarios C and H in CI on every PR to catch regressions in B2 (noise filtering) and overall behavior.
