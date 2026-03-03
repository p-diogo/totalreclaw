#!/usr/bin/env tsx
/**
 * report.ts -- JSON report generation and stdout summary table.
 *
 * Generates the TestReport structure defined in section 4.2 of the spec,
 * including per-instance per-scenario metrics, assertion results, and
 * a cross-instance comparison matrix.
 *
 * Can also be invoked standalone to re-process existing result JSON files:
 *   tsx report.ts [results-dir]
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type {
  TestReport,
  InstanceReport,
  ComparisonMatrix,
  ComparisonEntry,
  TestMetrics,
} from './types.js';

// ---------------------------------------------------------------------------
// Report generation
// ---------------------------------------------------------------------------

export interface ReportInput {
  allResults: Record<string, InstanceReport>;
  durationSeconds: number;
  totalAssertions: number;
  totalPassed: number;
  totalFailed: number;
  scenariosRun: number;
  instancesUsed: number;
}

export function generateReport(input: ReportInput): TestReport {
  const comparison = buildComparisonMatrix(input.allResults);

  return {
    timestamp: new Date().toISOString(),
    duration_seconds: Math.round(input.durationSeconds * 100) / 100,
    instances: input.allResults,
    comparison,
    summary: {
      total_assertions: input.totalAssertions,
      passed: input.totalPassed,
      failed: input.totalFailed,
      scenarios_run: input.scenariosRun,
      instances_used: input.instancesUsed,
    },
  };
}

// ---------------------------------------------------------------------------
// Comparison matrix (section 5)
// ---------------------------------------------------------------------------

function buildComparisonMatrix(
  allResults: Record<string, InstanceReport>,
): ComparisonMatrix {
  return {
    serverImprovedVsBaseline: compareInstances(
      allResults['server-improved'],
      allResults['server-baseline'],
      'Server Improved vs Baseline',
    ),
    subgraphImprovedVsBaseline: compareInstances(
      allResults['subgraph-improved'],
      allResults['subgraph-baseline'],
      'Subgraph Improved vs Baseline',
    ),
    subgraphVsServer: compareInstances(
      allResults['subgraph-improved'],
      allResults['server-improved'],
      'Subgraph Improved vs Server Improved',
    ),
  };
}

function compareInstances(
  improved: InstanceReport | undefined,
  baseline: InstanceReport | undefined,
  _label: string,
): ComparisonEntry[] {
  if (!improved || !baseline) return [];

  const entries: ComparisonEntry[] = [];

  // Find scenarios that exist in both instances
  const commonScenarios = Object.keys(improved.scenarios).filter(
    (s) => s in baseline.scenarios,
  );

  for (const scenarioId of commonScenarios) {
    const impMetrics = improved.scenarios[scenarioId].metrics;
    const baseMetrics = baseline.scenarios[scenarioId].metrics;

    // C3: Extraction count comparison
    const impExtractions = impMetrics.extractionEvents.filter((e) => e.extracted).length;
    const baseExtractions = baseMetrics.extractionEvents.filter((e) => e.extracted).length;
    if (baseExtractions > 0) {
      const reduction = 1 - impExtractions / baseExtractions;
      entries.push({
        metric: `${scenarioId}: Extraction reduction`,
        improved: impExtractions,
        baseline: baseExtractions,
        delta: `${(reduction * 100).toFixed(1)}%`,
        target: '>= 70%',
        passed: reduction >= 0.7,
      });
    }

    // B2: Noise injection rate
    const impNoiseInjections = impMetrics.injectionEvents.filter(
      (e) => !e.injected,
    ).length;
    const baseNoiseInjections = baseMetrics.injectionEvents.filter(
      (e) => !e.injected,
    ).length;
    entries.push({
      metric: `${scenarioId}: Non-injection turns`,
      improved: impNoiseInjections,
      baseline: baseNoiseInjections,
      delta: `${impNoiseInjections - baseNoiseInjections}`,
      target: 'improved >= baseline',
      passed: impNoiseInjections >= baseNoiseInjections,
    });

    // Latency: Hook p95
    const impLatencies = impMetrics.hookInvocations
      .filter((h) => h.hookName === 'before_agent_start')
      .map((h) => h.durationMs)
      .sort((a, b) => a - b);
    const baseLatencies = baseMetrics.hookInvocations
      .filter((h) => h.hookName === 'before_agent_start')
      .map((h) => h.durationMs)
      .sort((a, b) => a - b);

    const impP95 = impLatencies[Math.floor(impLatencies.length * 0.95)] ?? 0;
    const baseP95 = baseLatencies[Math.floor(baseLatencies.length * 0.95)] ?? 0;

    entries.push({
      metric: `${scenarioId}: Hook p95 latency (ms)`,
      improved: Math.round(impP95),
      baseline: Math.round(baseP95),
      delta: `${impP95 > 0 ? ((impP95 / Math.max(baseP95, 1)) * 100 - 100).toFixed(1) : '0'}%`,
      target: '<= baseline * 1.5',
      passed: impP95 <= baseP95 * 1.5,
    });

    // Cache hit rate (for improved only -- baseline should be 0)
    const impCacheHits = impMetrics.cacheEvents.filter((e) => e.type === 'hit').length;
    const baseCacheHits = baseMetrics.cacheEvents.filter((e) => e.type === 'hit').length;
    entries.push({
      metric: `${scenarioId}: Cache hits`,
      improved: impCacheHits,
      baseline: baseCacheHits,
      delta: `${impCacheHits - baseCacheHits}`,
      target: 'improved > 0 (if applicable)',
      passed: true, // informational
    });

    // Average injected context length
    const impAvgCtx = avgContextLength(impMetrics);
    const baseAvgCtx = avgContextLength(baseMetrics);
    entries.push({
      metric: `${scenarioId}: Avg injected context (chars)`,
      improved: Math.round(impAvgCtx),
      baseline: Math.round(baseAvgCtx),
      delta: `${impAvgCtx > 0 ? ((impAvgCtx / Math.max(baseAvgCtx, 1)) * 100 - 100).toFixed(1) : '0'}%`,
      target: 'Lower or equal',
      passed: impAvgCtx <= baseAvgCtx * 1.1, // 10% tolerance
    });
  }

  return entries;
}

function avgContextLength(metrics: TestMetrics): number {
  const injected = metrics.injectionEvents.filter((e) => e.injected);
  if (injected.length === 0) return 0;
  return (
    injected.reduce((sum, e) => sum + (e.contextSnippet?.length ?? 0), 0) /
    injected.length
  );
}

// ---------------------------------------------------------------------------
// Stdout summary table
// ---------------------------------------------------------------------------

export function printSummary(report: TestReport): void {
  console.log('='.repeat(70));
  console.log('  TEST SUMMARY');
  console.log('='.repeat(70));
  console.log(`  Timestamp:   ${report.timestamp}`);
  console.log(`  Duration:    ${report.duration_seconds}s`);
  console.log(`  Instances:   ${report.summary.instances_used}`);
  console.log(`  Scenarios:   ${report.summary.scenarios_run}`);
  console.log(`  Assertions:  ${report.summary.total_assertions}`);
  console.log(
    `  Passed:      ${report.summary.passed} (${((report.summary.passed / Math.max(report.summary.total_assertions, 1)) * 100).toFixed(1)}%)`,
  );
  console.log(`  Failed:      ${report.summary.failed}`);
  console.log('='.repeat(70));

  // Per-instance breakdown
  for (const [instanceId, instanceReport] of Object.entries(report.instances)) {
    console.log(`\n  Instance: ${instanceId}`);
    for (const [scenarioId, scenarioReport] of Object.entries(
      instanceReport.scenarios,
    )) {
      const assertions = Object.entries(scenarioReport.assertions);
      const passed = assertions.filter(([, r]) => r.passed).length;
      const failed = assertions.filter(([, r]) => !r.passed).length;
      const status = failed === 0 ? 'PASS' : 'FAIL';
      console.log(`    ${status}  Scenario ${scenarioId}: ${passed}/${assertions.length} assertions`);

      for (const [name, result] of assertions) {
        if (!result.passed) {
          console.log(`      -> ${name}: ${result.message}`);
        }
      }
    }
  }

  // Comparison matrix
  const comparisons = [
    { label: 'Server: Improved vs Baseline', data: report.comparison.serverImprovedVsBaseline },
    { label: 'Subgraph: Improved vs Baseline', data: report.comparison.subgraphImprovedVsBaseline },
    { label: 'Subgraph vs Server (improved)', data: report.comparison.subgraphVsServer },
  ];

  for (const { label, data } of comparisons) {
    if (data.length === 0) continue;
    console.log(`\n  Comparison: ${label}`);
    console.log('  ' + '-'.repeat(66));
    console.log(
      '  ' +
        'Metric'.padEnd(40) +
        'Improved'.padEnd(10) +
        'Baseline'.padEnd(10) +
        'Delta'.padEnd(10) +
        'Result',
    );
    console.log('  ' + '-'.repeat(66));
    for (const entry of data) {
      const status = entry.passed ? 'PASS' : 'FAIL';
      console.log(
        '  ' +
          entry.metric.padEnd(40).slice(0, 40) +
          String(entry.improved).padEnd(10) +
          String(entry.baseline).padEnd(10) +
          entry.delta.padEnd(10) +
          status,
      );
    }
  }

  console.log();
}

// ---------------------------------------------------------------------------
// File I/O
// ---------------------------------------------------------------------------

export async function writeReportToFile(report: TestReport): Promise<string> {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const dir = path.join(__dirname, 'results');
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const filename = `report-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
  const filepath = path.join(dir, filename);
  fs.writeFileSync(filepath, JSON.stringify(report, null, 2));
  console.log(`Report written to: ${filepath}`);
  return filepath;
}

// ---------------------------------------------------------------------------
// Standalone mode: re-process existing result files
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const resultsDir = process.argv[2] ?? path.join(__dirname, 'results');

  if (!fs.existsSync(resultsDir)) {
    console.error(`Results directory not found: ${resultsDir}`);
    console.error('Run tests first: tsx run-all.ts');
    process.exit(1);
  }

  // Find the most recent report file
  const files = fs
    .readdirSync(resultsDir)
    .filter((f) => f.startsWith('report-') && f.endsWith('.json'))
    .sort()
    .reverse();

  if (files.length === 0) {
    console.error('No report files found. Run tests first: tsx run-all.ts');
    process.exit(1);
  }

  const latestReport = path.join(resultsDir, files[0]);
  console.log(`Loading report: ${latestReport}`);

  const report: TestReport = JSON.parse(fs.readFileSync(latestReport, 'utf-8'));
  printSummary(report);
}

// Only run main when executed directly (not imported)
const __reportFile = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(__reportFile)) {
  main().catch((err) => {
    console.error('Error:', err);
    process.exit(1);
  });
}
