# Vendored `@totalreclaw/core` — WEB target

This directory holds a **web-target** (`wasm-pack --target web`) build of
`@totalreclaw/core`, loaded lazily by `src/lib/wasm.ts` on the first curation
write (A.2 delete/pin/…).

## Why vendored (and not the npm dependency)

The npm-published `@totalreclaw/core` is built with `wasm-pack --target nodejs`
(`require('fs').readFileSync(__dirname/…)`, CommonJS). That artifact runs in
Node (vitest, the E2E harness, the plugin/MCP) but **cannot run in a browser
bundle**. The SPA therefore ships a `--target web` build of the **same core
version**, which initializes via `fetch(new URL('…_bg.wasm', import.meta.url))`
and is Vite-friendly (the `.wasm` lands in its own async chunk, never in the
read-path `index-*.js`).

`@totalreclaw/core` is pinned in `package.json` (devDependencies) as the
version-of-record; the vendored files here MUST be regenerated from that same
version.

## Current version

`2.5.5` — matches `devDependencies["@totalreclaw/core"]`.

## Regenerating (on a core version bump)

```bash
cd rust/totalreclaw-core
wasm-pack build --target web --out-dir pkg-web --features wasm
cp pkg-web/totalreclaw_core.js          ../../app/src/vendor/core-wasm/
cp pkg-web/totalreclaw_core.d.ts        ../../app/src/vendor/core-wasm/
cp pkg-web/totalreclaw_core_bg.wasm     ../../app/src/vendor/core-wasm/
cp pkg-web/totalreclaw_core_bg.wasm.d.ts ../../app/src/vendor/core-wasm/
```

Then update the version above + `package.json`, and re-run the golden vectors
(`app/src/lib/userop.golden.test.ts`). If the wire format changed intentionally,
regenerate the frozen constants with `scratchpad/gen-golden.mjs` and note why.

> Follow-up (tracked for CI): build this artifact in `deploy-app.yml` from the
> pinned core version instead of committing the 2.3 MB binary, so the vendored
> copy can't drift from the published core.
