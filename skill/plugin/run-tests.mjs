// scanner-sim: allow — dev-only test runner, not in the npm tarball ("files" allowlist in package.json excludes it) and never reaches the OpenClaw runtime sandbox. Spawning test files via child_process is this script's entire purpose; the import is test-infrastructure only and not shipped. Invoked only as `node run-tests.mjs` (see package.json "test"), so no shebang is needed.
// Test runner for skill/plugin: discovers every *.test.ts under this package
// (recursively, excluding node_modules/ and dist/) and runs each via `npx tsx`
// sequentially, failing fast-free (runs all, reports every failure) with a
// per-file pass/fail summary and a non-zero exit if any file fails.
//
// Replaces the previously hand-enumerated `test` script, which had drifted:
// 33 *.test.ts files existed but were never listed, so CI never ran them.
//
// Run a single file the same way it always worked: `npx tsx <file>.test.ts`.

import { readdirSync, statSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const ROOT = dirname(fileURLToPath(import.meta.url));

// Explicit, visible exclusions. Anything here is NOT run by `npm test`.
// Each entry MUST carry a reason. These are files that require a build
// artifact, live network, or secret env vars — i.e. cannot pass in plain CI.
const EXCLUDE = new Map([
  [
    'dist-esm-smoke.test.ts',
    'Requires a built ./dist (ESM smoke test of compiled output). Run via `npm run smoke:dist` after `npm run build`.',
  ],
]);

const SKIP_DIRS = new Set(['node_modules', 'dist', '.git']);

function discover(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (SKIP_DIRS.has(name)) continue;
      out.push(...discover(full));
    } else if (name.endsWith('.test.ts')) {
      out.push(full);
    }
  }
  return out;
}

const all = discover(ROOT)
  .map((f) => relative(ROOT, f))
  .sort();

const excluded = [];
const toRun = [];
for (const f of all) {
  if (EXCLUDE.has(f)) excluded.push(f);
  else toRun.push(f);
}

console.log(`Discovered ${all.length} test file(s): ${toRun.length} to run, ${excluded.length} excluded.`);
if (excluded.length) {
  console.log('Excluded:');
  for (const f of excluded) console.log(`  - ${f}: ${EXCLUDE.get(f)}`);
}
console.log('');

const failures = [];
const started = Date.now();

for (let i = 0; i < toRun.length; i++) {
  const file = toRun[i];
  const label = `[${i + 1}/${toRun.length}] ${file}`;
  const t0 = Date.now();
  const res = spawnSync('npx', ['tsx', file], {
    cwd: ROOT,
    stdio: 'inherit',
    encoding: 'utf8',
  });
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  if (res.status === 0) {
    console.log(`PASS ${label} (${secs}s)`);
  } else {
    console.log(`FAIL ${label} (exit ${res.status}, ${secs}s)`);
    failures.push({ file, status: res.status });
  }
  console.log('');
}

const total = ((Date.now() - started) / 1000).toFixed(1);
console.log('='.repeat(60));
console.log(`Ran ${toRun.length} file(s) in ${total}s. ${toRun.length - failures.length} passed, ${failures.length} failed.`);
if (failures.length) {
  console.log('Failures:');
  for (const { file, status } of failures) console.log(`  - ${file} (exit ${status})`);
  process.exit(1);
}
console.log('All tests passed.');
