#!/usr/bin/env tsx
/**
 * run-all.ts -- Main orchestrator for the E2E functional test suite.
 *
 * Execution flow (section 7.3):
 *   1. Parse CLI arguments (--instances, --scenarios)
 *   2. For each instance:
 *      a. Set environment variables
 *      b. Install GraphQL interceptor (if subgraph mode)
 *      c. For each applicable scenario:
 *         - Create ConversationDriver
 *         - driver.initialize() -> driver.runScenario()
 *         - Collect TestMetrics, run assertions
 *         - Reset module state for next scenario
 *   3. Run cross-instance comparison assertions
 *   4. Generate JSON report + stdout summary
 *
 * Usage:
 *   tsx run-all.ts
 *   tsx run-all.ts --instances=server-improved,server-baseline
 *   tsx run-all.ts --scenarios=C --instances=server-improved
 *   tsx run-all.ts --scenarios=A,B,C --instances=server-improved,server-baseline
 */

import { ConversationDriver } from './conversation-driver.js';
import { generateReport, printSummary, writeReportToFile } from './report.js';
import {
  installGraphQLInterceptor,
  getGraphQLCaptures,
  resetCaptures,
} from './interceptors/graphql-interceptor.js';
import { analyzeCacheEvents } from './interceptors/cache-monitor.js';
import { analyzeExtractionEvents } from './interceptors/extraction-tracker.js';
import * as scenarioAssertions from './assertions/scenario-assertions.js';
import type {
  InstanceConfig,
  ConversationScenario,
  TestMetrics,
  AssertionResult,
  InstanceReport,
} from './types.js';
import { SCENARIO_APPLICABILITY } from './types.js';

// ---------------------------------------------------------------------------
// Instance definitions (section 2.2)
// ---------------------------------------------------------------------------

const PLUGIN_PATH = '../../skill/plugin/index.ts';

const ALL_INSTANCES: InstanceConfig[] = [
  {
    id: 'server-improved',
    mode: 'server',
    improvements: true,
    env: {
      TOTALRECLAW_RELEVANCE_THRESHOLD: '0.3',
      TOTALRECLAW_EXTRACT_EVERY_TURNS: '5',
      TOTALRECLAW_RANKING_WEIGHTS: '0.25,0.25,0.25,0.25',
      TOTALRECLAW_TWO_TIER_SEARCH: 'true',
      TOTALRECLAW_CACHE_TTL_MS: '300000',
    },
    pluginPath: PLUGIN_PATH,
  },
  {
    id: 'server-baseline',
    mode: 'server',
    improvements: false,
    env: {
      TOTALRECLAW_RELEVANCE_THRESHOLD: '0.0',
      TOTALRECLAW_EXTRACT_EVERY_TURNS: '1',
      TOTALRECLAW_RANKING_WEIGHTS: '0.25,0.25,0.25,0.25',
      TOTALRECLAW_TWO_TIER_SEARCH: 'false',
      TOTALRECLAW_CACHE_TTL_MS: '0',
    },
    pluginPath: PLUGIN_PATH,
  },
  {
    id: 'subgraph-improved',
    mode: 'subgraph',
    improvements: true,
    env: {
      TOTALRECLAW_RELEVANCE_THRESHOLD: '0.3',
      TOTALRECLAW_EXTRACT_EVERY_TURNS: '5',
      TOTALRECLAW_RANKING_WEIGHTS: '0.25,0.25,0.25,0.25',
      TOTALRECLAW_TWO_TIER_SEARCH: 'true',
      TOTALRECLAW_CACHE_TTL_MS: '300000',
      TOTALRECLAW_SUBGRAPH_MODE: 'true',
      TOTALRECLAW_SUBGRAPH_ENDPOINT: 'http://localhost:28000/subgraphs/name/totalreclaw',
    },
    pluginPath: PLUGIN_PATH,
  },
  {
    id: 'subgraph-baseline',
    mode: 'subgraph',
    improvements: false,
    env: {
      TOTALRECLAW_RELEVANCE_THRESHOLD: '0.0',
      TOTALRECLAW_EXTRACT_EVERY_TURNS: '1',
      TOTALRECLAW_TWO_TIER_SEARCH: 'false',
      TOTALRECLAW_CACHE_TTL_MS: '0',
      TOTALRECLAW_SUBGRAPH_MODE: 'true',
      TOTALRECLAW_SUBGRAPH_ENDPOINT: 'http://localhost:28000/subgraphs/name/totalreclaw',
    },
    pluginPath: PLUGIN_PATH,
  },
  {
    id: 'server-recency',
    mode: 'server',
    improvements: true,
    env: {
      TOTALRECLAW_RELEVANCE_THRESHOLD: '0.3',
      TOTALRECLAW_EXTRACT_EVERY_TURNS: '5',
      TOTALRECLAW_RANKING_WEIGHTS: '0.2,0.2,0.2,0.4',
      TOTALRECLAW_TWO_TIER_SEARCH: 'true',
      TOTALRECLAW_CACHE_TTL_MS: '300000',
    },
    pluginPath: PLUGIN_PATH,
  },
];

// ---------------------------------------------------------------------------
// Scenario loading
// ---------------------------------------------------------------------------

/** Maps scenario letter IDs to their module paths. */
const SCENARIO_MODULES: Record<string, string> = {
  A: './scenarios/scenario-a-preferences.js',
  B: './scenarios/scenario-b-technical.js',
  C: './scenarios/scenario-c-noise.js',
  D: './scenarios/scenario-d-topics.js',
  E: './scenarios/scenario-e-long.js',
  F: './scenarios/scenario-f-subgraph.js',
  G: './scenarios/scenario-g-pagination.js',
  H: './scenarios/scenario-h-freeform.js',
};

/**
 * Load a scenario definition from the scenarios/ directory.
 *
 * Scenario files export a ConversationScenario either as `default` or as a
 * named export (`scenarioA`, `scenarioE`, etc.). This function normalizes
 * access and overrides the pluginPath to match the instance config.
 */
async function loadScenario(
  scenarioId: string,
  pluginPath: string,
): Promise<ConversationScenario> {
  const modulePath = SCENARIO_MODULES[scenarioId];
  if (!modulePath) {
    throw new Error(
      `Unknown scenario ID: ${scenarioId}. Available: ${Object.keys(SCENARIO_MODULES).join(', ')}`,
    );
  }

  const mod = await import(modulePath);

  // Scenario files use either `export default` or `export const scenarioX`
  const scenario: ConversationScenario =
    mod.default ??
    mod[`scenario${scenarioId}`] ??
    Object.values(mod).find(
      (v: any) => v && typeof v === 'object' && 'turns' in v && 'id' in v,
    );

  if (!scenario) {
    throw new Error(
      `Scenario module ${modulePath} does not export a ConversationScenario`,
    );
  }

  // Override pluginPath to match the instance being tested
  return { ...scenario, pluginPath };
}

// ---------------------------------------------------------------------------
// Assertion loading
// ---------------------------------------------------------------------------

/**
 * Collect all assertion functions for a given scenario letter.
 *
 * Assertions are exported from `assertions/scenario-assertions.ts` with naming
 * convention `scenarioX_assertion_name`. This function filters to those matching
 * the requested scenario and returns them as a name -> function map.
 */
function getAssertionsForScenario(
  scenarioId: string,
): Record<string, (metrics: TestMetrics) => void> {
  const prefix = `scenario${scenarioId}_`;
  const result: Record<string, (metrics: TestMetrics) => void> = {};

  for (const [name, fn] of Object.entries(scenarioAssertions)) {
    if (name.startsWith(prefix) && typeof fn === 'function') {
      result[name] = fn as (metrics: TestMetrics) => void;
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

interface CliArgs {
  instances: string[];
  scenarios: string[];
}

function parseArgs(): CliArgs {
  const args = process.argv.slice(2);
  let instances: string[] | null = null;
  let scenarios: string[] | null = null;

  for (const arg of args) {
    if (arg.startsWith('--instances=')) {
      instances = arg.split('=')[1].split(',').map((s) => s.trim());
    } else if (arg.startsWith('--scenarios=')) {
      scenarios = arg.split('=')[1].split(',').map((s) => s.trim().toUpperCase());
    }
  }

  return {
    instances: instances ?? ALL_INSTANCES.map((i) => i.id),
    scenarios: scenarios ?? Object.keys(SCENARIO_APPLICABILITY),
  };
}

// ---------------------------------------------------------------------------
// Assertion runner
// ---------------------------------------------------------------------------

function runAssertions(
  assertions: Record<string, (metrics: TestMetrics) => void>,
  metrics: TestMetrics,
): Record<string, AssertionResult> {
  const results: Record<string, AssertionResult> = {};

  for (const [name, fn] of Object.entries(assertions)) {
    try {
      fn(metrics);
      results[name] = { passed: true, message: 'PASS' };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      results[name] = { passed: false, message };
    }
  }

  return results;
}

// ---------------------------------------------------------------------------
// Environment variable management
// ---------------------------------------------------------------------------

function setInstanceEnv(config: InstanceConfig): Record<string, string | undefined> {
  const previous: Record<string, string | undefined> = {};
  for (const [key, value] of Object.entries(config.env)) {
    previous[key] = process.env[key];
    process.env[key] = value;
  }
  return previous;
}

function restoreEnv(previous: Record<string, string | undefined>): void {
  for (const [key, value] of Object.entries(previous)) {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
}

// ---------------------------------------------------------------------------
// Main execution
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const startTime = performance.now();
  const cliArgs = parseArgs();

  console.log('='.repeat(70));
  console.log('  TotalReclaw E2E Functional Test Suite');
  console.log('='.repeat(70));
  console.log(`  Instances: ${cliArgs.instances.join(', ')}`);
  console.log(`  Scenarios: ${cliArgs.scenarios.join(', ')}`);
  console.log('='.repeat(70));
  console.log();

  // Filter instances to those requested
  const instances = ALL_INSTANCES.filter((i) => cliArgs.instances.includes(i.id));
  if (instances.length === 0) {
    console.error(
      `No matching instances found for: ${cliArgs.instances.join(', ')}`,
    );
    console.error(
      `Available: ${ALL_INSTANCES.map((i) => i.id).join(', ')}`,
    );
    process.exit(1);
  }

  // Collect all results keyed by instanceId -> scenarioId
  const allResults: Record<string, InstanceReport> = {};
  let totalAssertions = 0;
  let totalPassed = 0;
  let totalFailed = 0;
  let scenariosRun = 0;

  for (const instance of instances) {
    console.log(
      `\n--- Instance: ${instance.id} (${instance.mode}, improvements=${instance.improvements}) ---\n`,
    );
    allResults[instance.id] = { scenarios: {} };

    // Install GraphQL interceptor for subgraph instances
    if (instance.mode === 'subgraph') {
      installGraphQLInterceptor();
    }

    for (const scenarioId of cliArgs.scenarios) {
      // Check scenario applicability (section 7.4)
      const applicableInstances = SCENARIO_APPLICABILITY[scenarioId];
      if (!applicableInstances || !applicableInstances.includes(instance.id)) {
        console.log(`  [SKIP] Scenario ${scenarioId} -- not applicable for ${instance.id}`);
        continue;
      }

      console.log(`  [RUN]  Scenario ${scenarioId} on ${instance.id}...`);
      const scenarioStart = performance.now();

      try {
        // Load scenario definition with instance-specific pluginPath
        const scenario = await loadScenario(scenarioId, instance.pluginPath);

        // Collect assertions for this scenario
        const assertions = getAssertionsForScenario(scenarioId);

        // Save and set environment
        const previousEnv = setInstanceEnv(instance);

        // Reset GraphQL captures for this scenario
        resetCaptures();

        // Create driver and run scenario
        const driver = new ConversationDriver(instance, scenario);
        const metrics = await driver.runScenario();

        // Enrich metrics with interceptor data
        if (instance.mode === 'subgraph') {
          metrics.graphqlQueries = getGraphQLCaptures();
        }
        metrics.cacheEvents = analyzeCacheEvents(driver.getLogs(), metrics.injectionEvents);
        metrics.extractionEvents = analyzeExtractionEvents(
          driver.getLogs(),
          scenario.turns.length,
        );

        // Run assertions
        const assertionResults = runAssertions(assertions, metrics);

        // Tally results
        for (const result of Object.values(assertionResults)) {
          totalAssertions++;
          if (result.passed) totalPassed++;
          else totalFailed++;
        }
        scenariosRun++;

        // Store report
        allResults[instance.id].scenarios[scenarioId] = {
          metrics,
          assertions: assertionResults,
        };

        // Restore environment
        restoreEnv(previousEnv);

        const elapsed = ((performance.now() - scenarioStart) / 1000).toFixed(1);
        const passCount = Object.values(assertionResults).filter((r) => r.passed).length;
        const failCount = Object.values(assertionResults).filter((r) => !r.passed).length;
        const status = failCount === 0 ? 'PASS' : 'FAIL';
        console.log(
          `  [${status}] Scenario ${scenarioId} -- ${passCount} passed, ${failCount} failed (${elapsed}s)`,
        );

        // Print individual failures
        for (const [name, result] of Object.entries(assertionResults)) {
          if (!result.passed) {
            console.log(`         FAIL: ${name} -- ${result.message}`);
          }
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        console.error(`  [ERROR] Scenario ${scenarioId} -- ${message}`);
        allResults[instance.id].scenarios[scenarioId] = {
          metrics: {
            instanceId: instance.id,
            scenarioId,
            hookInvocations: [],
            cacheEvents: [],
            extractionEvents: [],
            injectionEvents: [],
            graphqlQueries: [],
            turnMetrics: [],
          },
          assertions: {
            _scenario_error: { passed: false, message },
          },
        };
        totalAssertions++;
        totalFailed++;
        scenariosRun++;
      }
    }
  }

  // -------------------------------------------------------------------------
  // Generate report
  // -------------------------------------------------------------------------

  const durationSeconds = (performance.now() - startTime) / 1000;

  const report = generateReport({
    allResults,
    durationSeconds,
    totalAssertions,
    totalPassed,
    totalFailed,
    scenariosRun,
    instancesUsed: instances.length,
  });

  // Write JSON report to results/
  await writeReportToFile(report);

  // Print summary
  console.log();
  printSummary(report);

  // Exit with appropriate code
  process.exit(totalFailed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(2);
});
