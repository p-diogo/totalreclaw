/**
 * Lazy loader for the `@totalreclaw/core` WASM (browser / web target).
 *
 * The published npm `@totalreclaw/core` is a wasm-pack **nodejs** build
 * (`require('fs')` + `__dirname`), which cannot run in a browser bundle. The
 * SPA therefore ships a vendored **web**-target build of the SAME core version
 * (see `src/vendor/core-wasm/README.md`), lazy-loaded here.
 *
 * IMPORTANT (bundle discipline): this module — and everything it pulls in
 * (`bundler.ts`, `userop.ts`, the 2.3 MB `.wasm`) — must be reached ONLY via a
 * dynamic `import()` on the FIRST write path (see `api.ts` deleteFact). It must
 * NEVER be statically imported by a read-path module, or the WASM would land in
 * the initial `index-*.js` chunk. Verified against the Vite chunk graph.
 */

// `?url` gives Vite an asset URL for the wasm without inlining it into JS.
import coreWasmUrl from "../vendor/core-wasm/totalreclaw_core_bg.wasm?url";

export type Core = typeof import("../vendor/core-wasm/totalreclaw_core.js");

let corePromise: Promise<Core> | null = null;

/**
 * Initialize and return the core WASM module (memoized). First call fetches +
 * instantiates the vendored `.wasm`; subsequent calls resolve immediately.
 */
export function loadCore(): Promise<Core> {
  if (!corePromise) {
    corePromise = (async () => {
      const mod = await import("../vendor/core-wasm/totalreclaw_core.js");
      // Web-target init: `default(url)` fetches + instantiates the wasm.
      await mod.default(coreWasmUrl);
      return mod as unknown as Core;
    })();
  }
  return corePromise;
}
