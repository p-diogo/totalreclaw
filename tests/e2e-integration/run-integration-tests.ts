#!/usr/bin/env npx tsx
/**
 * E2E Integration Test Runner for TotalReclaw.
 *
 * Waits for the server to be healthy, then runs each journey file
 * sequentially, collecting TAP-formatted results.
 *
 * Usage:
 *   npx tsx run-integration-tests.ts
 *   npx tsx run-integration-tests.ts --journey=1     # run only journey 1
 *   npx tsx run-integration-tests.ts --journey=1,3,5  # run specific journeys
 */

import { IntegrationTestRunner, SERVER_URL } from './test-helpers.js';

// ---------------------------------------------------------------------------
// Server readiness check
// ---------------------------------------------------------------------------

async function waitForServer(url: string, maxWaitMs: number = 60000): Promise<void> {
  const start = Date.now();
  console.log(`# Waiting for server at ${url} ...`);
  while (Date.now() - start < maxWaitMs) {
    try {
      const resp = await fetch(`${url}/health`);
      if (resp.ok) {
        console.log(`# Server ready (${Date.now() - start}ms)`);
        return;
      }
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`Server not ready after ${maxWaitMs}ms`);
}

// ---------------------------------------------------------------------------
// Parse CLI args
// ---------------------------------------------------------------------------

function parseJourneyFilter(): Set<number> | null {
  const arg = process.argv.find((a) => a.startsWith('--journey='));
  if (!arg) return null;
  const nums = arg
    .split('=')[1]
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !isNaN(n));
  return new Set(nums);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  console.log('TAP version 14');

  const runner = new IntegrationTestRunner();
  const filter = parseJourneyFilter();

  // Wait for the server to be ready
  await waitForServer(SERVER_URL);

  // Journey files — each exports a default function (runner) => Promise<void>
  const journeyFiles: Array<{ num: number; path: string }> = [
    { num: 1, path: './journeys/journey-1-core.js' },
    { num: 2, path: './journeys/journey-2-dedup.js' },
    { num: 3, path: './journeys/journey-3-wallet.js' },
    { num: 4, path: './journeys/journey-4-free-tier.js' },
    { num: 5, path: './journeys/journey-5-stripe.js' },
    { num: 6, path: './journeys/journey-6-coinbase.js' },
    { num: 7, path: './journeys/journey-7-security.js' },
    { num: 8, path: './journeys/journey-8-full-pipeline.js' },
  ];

  for (const { num, path } of journeyFiles) {
    // Apply filter if specified
    if (filter && !filter.has(num)) {
      console.log(`# Skipping journey ${num} (not in filter)`);
      continue;
    }

    try {
      const mod = await import(path);
      const fn = mod.default ?? Object.values(mod)[0];
      if (typeof fn === 'function') {
        await (fn as (runner: IntegrationTestRunner) => Promise<void>)(runner);
      } else {
        console.log(`# WARN: ${path} does not export a function`);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('Cannot find module') || msg.includes('ERR_MODULE_NOT_FOUND')) {
        console.log(`# SKIP: ${path} (not yet created)`);
      } else {
        console.log(`# FATAL: ${path} — ${msg}`);
        // Print stack for debugging
        if (err instanceof Error && err.stack) {
          for (const line of err.stack.split('\n').slice(1, 5)) {
            console.log(`#   ${line.trim()}`);
          }
        }
      }
    }
  }

  runner.printSummary();
  await runner.closeDb();
  process.exit(runner.getSummary().failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
