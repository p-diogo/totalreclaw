/**
 * E2E (Option E Phase 1, #582): decline escrow at bootstrap → assert no
 * POST /v1/escrow was ever issued → vault fully functional. Against
 * STAGING, via a WebAuthn virtual authenticator with prf support.
 *
 * GATED: the "later enable from Settings → recovery then works" half of
 * this scenario (spa-passkey-unlock.md §10.2) requires the relay's
 * /v1/escrow endpoints (totalreclaw-relay PR #46) to be live on staging.
 * This script covers everything that does NOT depend on that merge —
 * decline flow + the network-observability assertion — and stops there
 * rather than silently skipping the gated half. Re-run in full once #46
 * merges to staging.
 *
 * L3 — phrase-safety: reads the phrase from the DOM only to satisfy the
 * backup-confirm gate. Never logs it.
 *
 * Run: dev server up on :5173 (VITE_SERVER_URL=staging), then
 * `node e2e/escrow-decline.mjs`.
 */
import { chromium } from "@playwright/test";

const BASE = "http://localhost:5173";
const out = (m) => console.log(`[e2e] ${m}`);
let failed = false;
function check(name, cond) {
  out(`${cond ? "PASS" : "FAIL"} — ${name}`);
  if (!cond) failed = true;
}

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();

page.on("pageerror", (e) => out(`PAGEERROR: ${e.message}`));

// Track every request path hit during the run — the core assertion of this
// script is what's ABSENT from this list.
const requestedPaths = [];
page.on("request", (req) => {
  try {
    requestedPaths.push(new URL(req.url()).pathname);
  } catch {
    /* ignore */
  }
});

const cdp = await context.newCDPSession(page);
await cdp.send("WebAuthn.enable");
await cdp.send("WebAuthn.addVirtualAuthenticator", {
  options: {
    protocol: "ctap2",
    transport: "internal",
    hasResidentKey: true,
    hasUserVerification: true,
    hasPrf: true,
    automaticPresenceSimulation: true,
    isUserVerified: true,
  },
});

try {
  await page.goto(`${BASE}/bootstrap`, { waitUntil: "domcontentloaded" });
  await page.getByText("Create a new vault", { exact: true }).waitFor({ timeout: 15000 });
  await page.getByText("Create a new vault", { exact: true }).click();
  await page.getByText("Write this down").waitFor({ timeout: 10000 });

  const words = await page.$$eval("ol li", (lis) =>
    lis.map((li) => li.querySelectorAll("span")[1]?.textContent?.trim() ?? ""),
  );
  await page.getByText("I’ve written it down").click();
  await page.getByText("Confirm your backup").waitFor({ timeout: 10000 });
  const labels = await page.$$("label");
  for (const label of labels) {
    const span = await label.$("span");
    const txt = (await span?.textContent()) ?? "";
    const m = txt.match(/#(\d+)/);
    if (!m) continue;
    const n = parseInt(m[1], 10);
    const input = await label.$("input");
    await input?.fill(words[n - 1]);
  }
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByText("Back up your recovery phrase?").waitFor({ timeout: 10000 });
  check("escrow consent step shown before working", true);

  await page.getByRole("button", { name: "Not now" }).click();
  await page.waitForURL("**/memory", { timeout: 30000 });
  check("declining escrow still lands on a working vault", page.url().endsWith("/memory"));

  const escrowRequests = requestedPaths.filter((p) => p.startsWith("/v1/escrow"));
  check("declining issued NO request to any /v1/escrow* endpoint", escrowRequests.length === 0);

  // Settings renders the Passkeys & backup section — reachable even though
  // the relay's /v1/escrow route doesn't exist on staging yet (pre-#46), so
  // the list surfaces its error state rather than "no backups yet". Once
  // #46 is live this should read "No relay backups yet." instead — that
  // flip is itself a signal the gate has cleared.
  await page.goto(`${BASE}/settings`, { waitUntil: "domcontentloaded" });
  await page.getByText("Passkeys & backup").waitFor({ timeout: 10000 });
  check("Settings → Passkeys & backup section renders after decline", true);
  await page
    .getByText(/No relay backups yet\.|Couldn.t reach TotalReclaw to check your backups\./)
    .waitFor({ timeout: 10000 });
  check("backup list renders a definite state (empty or a graceful relay-unreachable message)", true);
} catch (e) {
  out(`EXCEPTION: ${e.message}`);
  failed = true;
  try {
    await page.screenshot({ path: "e2e/shot-escrow-decline-failure.png" });
  } catch {}
}

out("GATED (not run): enabling escrow from Settings + recovering with it — requires totalreclaw-relay PR #46 live on staging.");

await browser.close();
out(failed ? "RESULT: FAIL" : "RESULT: PASS (partial — see GATED note above)");
process.exit(failed ? 1 : 0);
