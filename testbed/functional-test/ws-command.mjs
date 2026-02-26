#!/usr/bin/env node
/**
 * ws-command.mjs — Send messages and slash commands to OpenClaw via its CLI.
 *
 * Designed to be copied into the OpenClaw container and executed there.
 * Copy with: docker cp ws-command.mjs openclaw-test:/home/node/ws-command.mjs
 * (NOTE: /tmp is a tmpfs in the container, use /home/node instead)
 *
 * Approach:
 * - Regular messages: `openclaw agent --session-id <id> --message <text>`
 *   Goes through the full agent pipeline (before_agent_start hook fires).
 * - Slash commands: `openclaw gateway call chat.send` with session key
 *   Triggers gateway slash-command processing. Confirmed working hooks:
 *     /compact  -> before_compaction hook fires, extracts facts from messages
 *     /new      -> creates new session (before_reset does NOT fire in v2026.2.22)
 *     /reset    -> creates new session (before_reset does NOT fire in v2026.2.22)
 *
 * Usage (from host):
 *   docker exec openclaw-test node /home/node/ws-command.mjs "Hello, agent!"
 *   docker exec openclaw-test node /home/node/ws-command.mjs /compact
 *   docker exec openclaw-test node /home/node/ws-command.mjs /new
 *
 * Environment variables:
 *   OPENCLAW_TOKEN     - Gateway auth token (default: hardcoded test token)
 *   OPENCLAW_SESSION   - Session key (default: agent:main:main)
 *   OPENCLAW_TIMEOUT   - Timeout in seconds (default: 120 for messages, 60 for slash cmds)
 */

import { execSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const OPENCLAW_BIN = '/app/openclaw.mjs';
const DEFAULT_SESSION_KEY = 'agent:main:main';
const DEFAULT_TOKEN = process.env.OPENCLAW_TOKEN || 'e6a13aa43a07820b3a80755748a6c856fdb2cd9a8a6be0b6';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function usage() {
  console.log(`
Usage: node ws-command.mjs <message-or-slash-command>

Examples:
  node ws-command.mjs "I like cats and my birthday is March 15"
  node ws-command.mjs /compact
  node ws-command.mjs /new

Options:
  --session-id <id>    Use a specific session ID (default: auto-detect main session)
  --session-key <key>  Use a specific session key (default: agent:main:main)
  --timeout <seconds>  Override timeout (default: 120 for messages, 60 for slash)
  --json               Output raw JSON response
  --quiet              Suppress informational output
`);
  process.exit(1);
}

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    message: null,
    sessionId: null,
    sessionKey: DEFAULT_SESSION_KEY,
    timeout: null,
    json: false,
    quiet: false,
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--session-id' && i + 1 < args.length) {
      opts.sessionId = args[++i];
    } else if (arg === '--session-key' && i + 1 < args.length) {
      opts.sessionKey = args[++i];
    } else if (arg === '--timeout' && i + 1 < args.length) {
      opts.timeout = parseInt(args[++i], 10);
    } else if (arg === '--json') {
      opts.json = true;
    } else if (arg === '--quiet') {
      opts.quiet = true;
    } else if (arg === '--help' || arg === '-h') {
      usage();
    } else if (!opts.message) {
      opts.message = arg;
    }
  }

  if (!opts.message) {
    console.error('Error: no message provided.');
    usage();
  }

  return opts;
}

function isSlashCommand(msg) {
  return msg.startsWith('/');
}

function log(opts, ...args) {
  if (!opts.quiet) {
    console.error(...args);
  }
}

/**
 * Get the session ID for the main session by querying gateway status.
 */
function getMainSessionId(token) {
  try {
    const result = execSync(
      `node ${OPENCLAW_BIN} gateway call status --token "${token}" --json 2>/dev/null`,
      { encoding: 'utf-8', timeout: 15000 }
    );
    const status = JSON.parse(result);
    const sessions = status?.sessions?.recent || [];
    const mainSession = sessions.find(s => s.key === 'agent:main:main');
    return mainSession?.sessionId || null;
  } catch (err) {
    return null;
  }
}

/**
 * Send a slash command via gateway call chat.send.
 * This triggers the gateway's slash-command processing pipeline.
 * Confirmed: /compact fires before_compaction hook.
 * Note: /new and /reset do NOT fire before_reset in OpenClaw v2026.2.22;
 * they simply create a new session. The before_reset hook may need a
 * different trigger or may not be implemented in this OpenClaw version.
 */
function sendSlashCommand(opts) {
  const { message, sessionKey, timeout } = opts;
  const effectiveTimeout = (timeout || 60) * 1000;
  const idempotencyKey = `wscmd-${randomUUID()}`;

  const params = JSON.stringify({
    sessionKey,
    message,
    idempotencyKey,
  });

  log(opts, `[ws-command] Sending slash command: ${message}`);
  log(opts, `[ws-command] Session key: ${sessionKey}`);
  log(opts, `[ws-command] Idempotency key: ${idempotencyKey}`);

  try {
    const result = execSync(
      `node ${OPENCLAW_BIN} gateway call chat.send` +
        ` --token "${DEFAULT_TOKEN}"` +
        ` --params '${params}'` +
        ` --json` +
        ` --expect-final` +
        ` --timeout ${effectiveTimeout}`,
      { encoding: 'utf-8', timeout: effectiveTimeout + 5000 }
    );

    const parsed = JSON.parse(result);

    if (opts.json) {
      console.log(JSON.stringify(parsed, null, 2));
    } else {
      log(opts, `[ws-command] Status: ${parsed.status || 'unknown'}`);
      if (parsed.status === 'started') {
        log(opts, `[ws-command] Command accepted (run ID: ${parsed.runId})`);
        log(opts, `[ws-command] The slash command is processing asynchronously.`);
        log(opts, `[ws-command] Check logs: cat /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep -i "${message.slice(1)}"`);
      }
      console.log(JSON.stringify(parsed, null, 2));
    }

    return parsed;
  } catch (err) {
    console.error(`[ws-command] Error sending slash command: ${err.message}`);
    if (err.stdout) console.error(`[ws-command] stdout: ${err.stdout}`);
    if (err.stderr) console.error(`[ws-command] stderr: ${err.stderr}`);
    process.exit(1);
  }
}

/**
 * Send a regular message via openclaw agent CLI.
 * This goes through the full agent pipeline with before_agent_start hook.
 */
function sendMessage(opts) {
  const { message, sessionId, timeout } = opts;
  const effectiveTimeout = timeout || 120;

  // If no session ID provided, try to find the main session
  let sid = sessionId;
  if (!sid) {
    log(opts, `[ws-command] Looking up main session ID...`);
    sid = getMainSessionId(DEFAULT_TOKEN);
    if (!sid) {
      console.error('[ws-command] Could not find main session ID. Use --session-id to specify one.');
      process.exit(1);
    }
    log(opts, `[ws-command] Found session: ${sid}`);
  }

  log(opts, `[ws-command] Sending message: ${message}`);
  log(opts, `[ws-command] Session ID: ${sid}`);
  log(opts, `[ws-command] Timeout: ${effectiveTimeout}s`);

  try {
    const result = execSync(
      `node ${OPENCLAW_BIN} agent` +
        ` --session-id "${sid}"` +
        ` --message "${message.replace(/"/g, '\\"')}"` +
        ` --json` +
        ` --timeout ${effectiveTimeout}`,
      { encoding: 'utf-8', timeout: (effectiveTimeout + 10) * 1000 }
    );

    const parsed = JSON.parse(result);

    if (opts.json) {
      console.log(JSON.stringify(parsed, null, 2));
    } else {
      const text = parsed?.result?.payloads?.[0]?.text || '(no response text)';
      const duration = parsed?.result?.meta?.durationMs;
      log(opts, `[ws-command] Response received (${duration ? duration + 'ms' : 'unknown duration'})`);
      console.log(text);
    }

    return parsed;
  } catch (err) {
    console.error(`[ws-command] Error sending message: ${err.message}`);
    if (err.stdout) console.error(`[ws-command] stdout: ${err.stdout}`);
    if (err.stderr) console.error(`[ws-command] stderr: ${err.stderr}`);
    process.exit(1);
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const opts = parseArgs();

if (isSlashCommand(opts.message)) {
  sendSlashCommand(opts);
} else {
  sendMessage(opts);
}
