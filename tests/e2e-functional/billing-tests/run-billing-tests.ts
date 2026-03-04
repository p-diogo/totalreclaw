#!/usr/bin/env tsx
/**
 * Billing E2E Test Orchestrator
 *
 * Starts the mock billing server, runs all three Journey test files
 * (A: Free Tier, B: Stripe, C: Coinbase Commerce), and reports results
 * in TAP (Test Anything Protocol) format.
 *
 * Usage:
 *   cd tests/e2e-functional && npx tsx billing-tests/run-billing-tests.ts
 *   cd tests/e2e-functional && npx tsx billing-tests/run-billing-tests.ts --journey=A
 *   cd tests/e2e-functional && npx tsx billing-tests/run-billing-tests.ts --journey=B,C
 */

import { startBillingMockServer, type BillingMockServer } from './mock-billing-server.js';
import { runJourneyA, type TestResult } from './journey-a.test.js';
import { runJourneyB } from './journey-b.test.js';
import { runJourneyC } from './journey-c.test.js';

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------

interface CliArgs {
  journeys: string[];
}

function parseArgs(): CliArgs {
  const args = process.argv.slice(2);
  let journeys: string[] | null = null;

  for (const arg of args) {
    if (arg.startsWith('--journey=') || arg.startsWith('--journeys=')) {
      journeys = arg.split('=')[1].split(',').map((s) => s.trim().toUpperCase());
    }
  }

  return {
    journeys: journeys ?? ['A', 'B', 'C'],
  };
}

// ---------------------------------------------------------------------------
// TAP output helpers
// ---------------------------------------------------------------------------

let tapIndex = 0;

function tapOk(result: TestResult): void {
  tapIndex++;
  const status = result.passed ? 'ok' : 'not ok';
  const duration = result.durationMs.toFixed(1);
  console.log(`${status} ${tapIndex} - [${result.id}] ${result.name} (${duration}ms)`);
  if (!result.passed) {
    // TAP diagnostic line (indented with #)
    console.log(`#   FAIL: ${result.message}`);
  }
}

// ---------------------------------------------------------------------------
// Journey runner map
// ---------------------------------------------------------------------------

const JOURNEY_RUNNERS: Record<string, (server: BillingMockServer) => Promise<TestResult[]>> = {
  A: runJourneyA,
  B: runJourneyB,
  C: runJourneyC,
};

const JOURNEY_NAMES: Record<string, string> = {
  A: 'Free Tier',
  B: 'Stripe Paid',
  C: 'Coinbase Commerce Paid',
};

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const startTime = performance.now();
  const cliArgs = parseArgs();

  // Validate journey IDs
  for (const j of cliArgs.journeys) {
    if (!JOURNEY_RUNNERS[j]) {
      console.error(`Unknown journey: ${j}. Available: ${Object.keys(JOURNEY_RUNNERS).join(', ')}`);
      process.exit(1);
    }
  }

  // Start mock server
  const server = await startBillingMockServer();

  console.log('');
  console.log('='.repeat(70));
  console.log('  TotalReclaw Billing E2E Tests');
  console.log('='.repeat(70));
  console.log(`  Mock Server:  ${server.url}`);
  console.log(`  Journeys:     ${cliArgs.journeys.map((j) => `${j} (${JOURNEY_NAMES[j]})`).join(', ')}`);
  console.log('='.repeat(70));
  console.log('');

  // Collect all results
  const allResults: TestResult[] = [];
  const journeyResults: Record<string, TestResult[]> = {};

  for (const journeyId of cliArgs.journeys) {
    const runner = JOURNEY_RUNNERS[journeyId];
    const journeyName = JOURNEY_NAMES[journeyId];

    console.log(`--- Journey ${journeyId}: ${journeyName} ---`);
    console.log('');

    try {
      const results = await runner(server);
      journeyResults[journeyId] = results;
      allResults.push(...results);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`  FATAL: Journey ${journeyId} runner threw: ${message}`);
      allResults.push({
        id: `T-${journeyId}00`,
        name: `Journey ${journeyId} runner error`,
        passed: false,
        message,
        durationMs: 0,
      });
    }

    console.log('');
  }

  // -------------------------------------------------------------------------
  // TAP output
  // -------------------------------------------------------------------------

  console.log('');
  console.log(`TAP version 13`);
  console.log(`1..${allResults.length}`);

  tapIndex = 0;
  for (const result of allResults) {
    tapOk(result);
  }

  // -------------------------------------------------------------------------
  // Summary
  // -------------------------------------------------------------------------

  const durationSeconds = (performance.now() - startTime) / 1000;
  const passed = allResults.filter((r) => r.passed).length;
  const failed = allResults.filter((r) => !r.passed).length;
  const total = allResults.length;

  console.log('');
  console.log('='.repeat(70));
  console.log(`  RESULTS: ${passed}/${total} passed, ${failed} failed`);
  console.log(`  Duration: ${durationSeconds.toFixed(2)}s`);

  // Per-journey summary
  for (const journeyId of cliArgs.journeys) {
    const jr = journeyResults[journeyId] ?? [];
    const jp = jr.filter((r) => r.passed).length;
    const jf = jr.filter((r) => !r.passed).length;
    const status = jf === 0 ? 'PASS' : 'FAIL';
    console.log(`  Journey ${journeyId} (${JOURNEY_NAMES[journeyId]}): ${status} - ${jp}/${jr.length} passed`);
  }

  console.log('='.repeat(70));
  console.log('');

  // Print failures for easy scanning
  if (failed > 0) {
    console.log('FAILURES:');
    for (const result of allResults) {
      if (!result.passed) {
        console.log(`  [${result.id}] ${result.name}: ${result.message}`);
      }
    }
    console.log('');
  }

  // Cleanup
  await server.stop();

  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(2);
});
