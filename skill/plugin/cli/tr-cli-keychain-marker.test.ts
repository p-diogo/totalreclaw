/**
 * Wiring-level test for the #545 keychain-marker guard in tr-cli.ts
 * `buildContext()`.
 *
 * The helper-only unit tests in `keychain-marker.test.ts` cover
 * `isKeychainMarker()` / `KEYCHAIN_MARKER_SETUP_MSG` in isolation, but they
 * don't prove the guard is actually WIRED into every read→derive call site.
 * A Sonnet-high review of this PR found exactly that gap: `index.ts`
 * `initialize()` was patched, but `cli/tr-cli.ts` `buildContext()` — the
 * shared credential-load path behind `tr remember`, `tr forget`, and
 * `tr export` — still fed a keychain marker straight into
 * `setRecoveryPhraseOverride()` + `deriveKeys()`, reproducing the exact
 * unhandled "invalid mnemonic: expected 12 or 24 words, got 1" crash this
 * PR exists to fix.
 *
 * This test drives the REAL `buildContext()` path end-to-end (as a
 * subprocess, since tr-cli.ts has no exports and runs `main()` as a
 * top-of-module side effect) against a marker-shaped `credentials.json`
 * fixture, and asserts:
 *   - the process exits via the new `die()` guard (code 1, `tr: ` prefix)
 *   - NOT via the old unhandled-rejection path (`main().catch` → `tr: fatal:`,
 *     code 2)
 *   - the actionable KEYCHAIN_MARKER_SETUP_MSG guidance is on stderr
 *   - the raw BIP-39 crash text ("invalid mnemonic") never appears
 *   - the marker's payload (the fake EOA suffix) is never echoed
 *
 * `tr forget <factId>` is used because it reaches `buildContext()` after
 * only a UUID-shape check on argv — no live relay/network call happens
 * before the marker guard fires (die() short-circuits before
 * `createApiClient` is ever reached).
 *
 * Run with: npx tsx cli/tr-cli-keychain-marker.test.ts
 *
 * TAP-style output, no jest dependency (mirrors keychain-marker.test.ts /
 * pairing/credentials-bootstrap.test.ts).
 */

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const TR_CLI_PATH = path.join(__dirname, 'tr-cli.ts');

let passed = 0;
let failed = 0;

function assert(condition: boolean, name: string): void {
  const n = passed + failed + 1;
  if (condition) {
    console.log(`ok ${n} - ${name}`);
    passed++;
  } else {
    console.log(`not ok ${n} - ${name}`);
    failed++;
  }
}

function mkTmpCredentials(contents: Record<string, unknown>): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tr-cli-marker-'));
  const credPath = path.join(dir, 'credentials.json');
  fs.writeFileSync(credPath, JSON.stringify(contents), { mode: 0o600 });
  return credPath;
}

// A syntactically-plausible fake marker — NOT a real wallet, this is a
// fixture, but the test still never echoes it in an assertion message.
const FAKE_MARKER = '__keychain__:v1:0x' + 'b'.repeat(40);
const FAKE_FACT_ID = '00000000-0000-4000-8000-000000000000';

function runForget(credentialsPath: string): { code: number | null; stdout: string; stderr: string } {
  const res = spawnSync('npx', ['tsx', TR_CLI_PATH, 'forget', FAKE_FACT_ID, '--json'], {
    cwd: __dirname,
    encoding: 'utf-8',
    env: {
      ...process.env,
      TOTALRECLAW_CREDENTIALS_PATH: credentialsPath,
      // Force away from any real relay — the marker guard should fire
      // long before a network call would be attempted anyway.
      TOTALRECLAW_SERVER_URL: 'https://api-staging.totalreclaw.xyz',
    },
    // NEVER pass TOTALRECLAW_RECOVERY_PHRASE — that would bypass the
    // credentials.json read entirely and defeat the point of this test.
    timeout: 30_000,
  });
  return { code: res.status, stdout: res.stdout ?? '', stderr: res.stderr ?? '' };
}

// ---------------------------------------------------------------------------
// 1. marker-shaped credentials.json (mnemonic field) → soft die(), not crash
// ---------------------------------------------------------------------------
{
  const credPath = mkTmpCredentials({
    version: 1,
    userId: 'u-test',
    salt: 'a'.repeat(64),
    mnemonic: FAKE_MARKER,
    keychain_wrapped: true,
  });

  const { code, stderr } = runForget(credPath);

  assert(code === 1, `exit code is 1 (die()), not 0/2 (got ${code})`);
  assert(/^tr: /.test(stderr), `stderr starts with the die() "tr: " prefix (got: ${JSON.stringify(stderr.slice(0, 40))})`);
  assert(!/^tr: fatal:/.test(stderr), 'stderr does NOT start with "tr: fatal:" (the old unhandled-rejection path)');
  assert(
    stderr.includes('TOTALRECLAW_RECOVERY_PHRASE'),
    'stderr points to the TOTALRECLAW_RECOVERY_PHRASE escape hatch',
  );
  assert(
    stderr.includes('TOTALRECLAW_NO_KEYCHAIN'),
    'stderr mentions the TOTALRECLAW_NO_KEYCHAIN kill-switch',
  );
  assert(
    !/invalid mnemonic/i.test(stderr),
    'stderr does NOT contain the raw BIP-39 "invalid mnemonic" crash text',
  );
  assert(
    !stderr.includes(FAKE_MARKER),
    'stderr never echoes the marker payload itself',
  );
}

// ---------------------------------------------------------------------------
// 2. marker-shaped credentials.json (legacy recovery_phrase field) → same
// ---------------------------------------------------------------------------
{
  const credPath = mkTmpCredentials({
    version: 1,
    userId: 'u-test-2',
    salt: 'a'.repeat(64),
    recovery_phrase: FAKE_MARKER,
    keychain_wrapped: true,
  });

  const { code, stderr } = runForget(credPath);

  assert(code === 1, `recovery_phrase field: exit code is 1 (got ${code})`);
  assert(
    stderr.includes('TOTALRECLAW_RECOVERY_PHRASE') && stderr.includes('TOTALRECLAW_NO_KEYCHAIN'),
    'recovery_phrase field: actionable message present',
  );
  assert(!/invalid mnemonic/i.test(stderr), 'recovery_phrase field: no raw BIP-39 crash text');
}

// ---------------------------------------------------------------------------
// 3. sanity control: a plaintext (non-marker) mnemonic does NOT trip the
//    marker guard — it should proceed past buildContext() and fail later
//    for an unrelated reason (network/relay), never with the marker message.
// ---------------------------------------------------------------------------
{
  const PLAIN_MNEMONIC =
    'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
  const credPath = mkTmpCredentials({
    version: 1,
    userId: 'u-test-3',
    salt: 'a'.repeat(64),
    mnemonic: PLAIN_MNEMONIC,
  });

  const { stderr } = runForget(credPath);

  assert(
    !stderr.includes('OS keychain') && !stderr.includes('keychain-wrapped'),
    'control: a plaintext mnemonic never trips the keychain-marker guard',
  );
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
