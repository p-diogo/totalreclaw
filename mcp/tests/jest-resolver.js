/**
 * Custom Jest resolver that handles ESM-style .js extension imports
 * in TypeScript source files compiled via ts-jest with CJS output.
 *
 * When TypeScript is configured with module: "NodeNext", imports like
 * `import { foo } from './bar.js'` resolve to `./bar.ts` at compile time.
 * Jest needs help with this because it uses CJS resolution.
 *
 * For npm packages like @noble/hashes that use .js subpath exports
 * (e.g., `@noble/hashes/hkdf.js`), the file literally exists as hkdf.js
 * so no mapping is needed. For local .ts files imported as .js, we remap.
 */
module.exports = (path, options) => {
  // Use the default resolver first
  try {
    return options.defaultResolver(path, options);
  } catch (err) {
    // If the default resolver fails and the path ends with .js,
    // try resolving without .js (for subpath exports) or with .ts
    if (path.endsWith('.js')) {
      // Try stripping .js and adding .ts (local TS file imports)
      try {
        return options.defaultResolver(path.replace(/\.js$/, '.ts'), options);
      } catch (_) {
        // Try stripping .js entirely (package subpath exports)
        try {
          return options.defaultResolver(path.replace(/\.js$/, ''), options);
        } catch (__) {
          // Fall through to original error
        }
      }
    }
    throw err;
  }
};
