/**
 * TotalReclaw MCP — `derived-bundle-v1` credential bundle (Option E Phase 2 /
 * #581, P2-13 — the MCP adapter).
 *
 * A bundle is what an agent host holds *instead of* the BIP-39 recovery
 * phrase: the four HKDF-derived vault-global working keys plus a signing
 * key, but never the phrase or the 64-byte seed that reproduces it. See
 * `docs/specs/totalreclaw/client-consistency.md` ("Credential Material") for
 * the full cross-client contract this file implements.
 *
 * Shared-core-first (CLAUDE.md): every byte of derivation, parsing, and
 * validation lives in `rust/totalreclaw-core/src/bundle.rs` and crosses into
 * TS only via the `@totalreclaw/core` WASM bindings (`parseBundleV1`,
 * `validateBundleV1`, `deriveBundleFromMnemonic`). This module is a THIN
 * adapter: it types the wire shape, calls the WASM binding, and converts hex
 * fields to `Buffer` where the rest of the MCP codebase expects buffers. It
 * does not reimplement HKDF, hex validation, or any §4.7 invariant — the
 * mnemonic-mode `deriveKeys`/`deriveLshSeed` in `subgraph/crypto.ts` are the
 * pattern followed here: WASM-backed wrappers, no local crypto.
 *
 * Mirrors `python/src/totalreclaw/bundle.py`'s shape (frozen dataclasses,
 * zero logic) as closely as TS allows.
 *
 * **Dependency note (release gate — see PR body):** as of this writing, no
 * published `@totalreclaw/core` npm release exposes `parseBundleV1` /
 * `validateBundleV1` / `deriveBundleFromMnemonic` (checked: latest dist-tag
 * 2.6.0-rc.1 does not carry them). This module was developed and tested
 * against a WASM package built locally from `rust/totalreclaw-core` (already
 * merged on `origin/main`, PR #587) via `build-wasm.sh`, copied over
 * `mcp/node_modules/@totalreclaw/core` for local `npm test`/`npm run build`.
 * `mcp/package.json`'s declared `@totalreclaw/core` range must be bumped to
 * whatever release first publishes these bindings before this branch can
 * build against the real npm registry (CI included) — tracked as an
 * explicit release-gate item, not silently assumed.
 */

// eslint-disable-next-line @typescript-eslint/no-var-requires
const wasm = require('@totalreclaw/core') as typeof import('@totalreclaw/core');

// ---------------------------------------------------------------------------
// Wire types — field names match the canonical JSON in
// client-consistency.md's "Credential Material" section exactly (snake_case;
// the WASM binding's `serde_wasm_bindgen` output preserves Rust struct field
// names verbatim — no camelCase rename layer here, deliberately, so the
// on-wire shape and the in-process shape never drift).
// ---------------------------------------------------------------------------

/** The four HKDF-derived vault-global working keys, hex-encoded (64 chars, no `0x`). */
export interface BundleVaultHex {
  encryption_key: string;
  dedup_key: string;
  auth_key: string;
  lsh_seed: string;
}

export interface BundleSigningOwnerEoa {
  kind: 'owner-eoa';
  private_key: string; // 64 hex chars
  address: string; // 0x-prefixed, EIP-55 checksummed
}

export interface BundleSigningSessionKey {
  kind: 'session-key';
  private_key: string;
  address: string;
  grant: unknown; // SessionKeyPermissionGrant v1 — opaque to this crate/adapter
}

export type BundleSigning = BundleSigningOwnerEoa | BundleSigningSessionKey;

export interface BundleAccountRef {
  smart_account: string; // 0x-prefixed, EIP-55 checksummed
  chain_id: number;
}

/** A fully parsed + `parse_bundle_v1`-validated `derived-bundle-v1` bundle. */
export interface DerivedBundleV1 {
  vault: BundleVaultHex;
  signing: BundleSigning;
  account: BundleAccountRef;
  provisioned_at: string;
  provisioned_by: string;
}

// ---------------------------------------------------------------------------
// Parsing / validation — delegates to @totalreclaw/core. Never re-implements
// any derived-bundle-v1.md §4.7 invariant locally.
// ---------------------------------------------------------------------------

/**
 * Parse and fully validate a `derived-bundle-v1` JSON string.
 *
 * Runs every §4.7 invariant inside `totalreclaw-core::bundle::parse_bundle_v1`
 * (wrong version/schema, malformed hex, unknown `signing.kind`, an
 * `owner-eoa` bundle carrying a `grant`, a `session-key` bundle with an
 * inconsistent `grant`, `signing.address` not matching `address(private_key)`,
 * …). Throws a plain `Error` — never a silent downgrade — on any violation.
 *
 * The thrown error's message is core's own message, which never contains
 * hex key material (core's validation errors describe *shape* violations,
 * not values).
 */
export function parseBundleV1(json: string): DerivedBundleV1 {
  // wasm.parseBundleV1 throws a JsError on any validation failure — surface
  // it as a normal Error with a stable, actionable prefix so callers don't
  // need to know this crossed a WASM boundary.
  let parsed: unknown;
  try {
    parsed = wasm.parseBundleV1(json);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`derived-bundle-v1: invalid bundle — ${msg}`);
  }
  return parsed as DerivedBundleV1;
}

/**
 * Validate a `derived-bundle-v1` JSON string without returning the parsed
 * object. Throws on any violation; no-op on success.
 */
export function validateBundleV1(json: string): void {
  try {
    wasm.validateBundleV1(json);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`derived-bundle-v1: invalid bundle — ${msg}`);
  }
}

/**
 * Derive a `derived-bundle-v1` bundle from a BIP-39 mnemonic.
 *
 * NOT part of MCP's read-side credential-loading scope (P2-13) — MCP never
 * derives a bundle from a mnemonic on its own initiative; that is Hermes's
 * `local-migration` job (P2-9) or the SPA's `provisioned_by: "spa"` job.
 * Exported anyway because the test fixtures (parity + pair-bundle tests)
 * need a way to mint a bundle for `parseBundleV1` round-trip coverage
 * without hand-rolling JSON, and because a future MCP-side migration tool
 * (tracked as a known gap — see mcp/README.md) will need exactly this call.
 */
export function deriveBundleFromMnemonic(
  mnemonic: string,
  chainId: number,
  provisionedBy: string,
  smartAccount: string,
): string {
  return wasm.deriveBundleFromMnemonic(mnemonic.trim(), BigInt(chainId), provisionedBy, smartAccount);
}

// ---------------------------------------------------------------------------
// Buffer conversion — the rest of the MCP codebase (subgraph/crypto.ts,
// subgraph/lsh.ts, encrypt/decrypt) works in `Buffer`, not hex strings.
// ---------------------------------------------------------------------------

export interface BundleVaultBuffers {
  encryptionKey: Buffer;
  dedupKey: Buffer;
  authKey: Buffer;
  lshSeed: Buffer;
}

/** Convert a parsed bundle's hex vault keys to `Buffer`s. */
export function bundleVaultToBuffers(bundle: DerivedBundleV1): BundleVaultBuffers {
  return {
    encryptionKey: Buffer.from(bundle.vault.encryption_key, 'hex'),
    dedupKey: Buffer.from(bundle.vault.dedup_key, 'hex'),
    authKey: Buffer.from(bundle.vault.auth_key, 'hex'),
    lshSeed: Buffer.from(bundle.vault.lsh_seed, 'hex'),
  };
}

// ---------------------------------------------------------------------------
// Redaction — derived-bundle-v1.md §4.6 point 5: no value under `vault` or
// `signing.private_key` may ever be logged, printed, or included in an
// exception message. Python's `bundle.py` enforces this with `__repr__`
// overrides on frozen dataclasses; TS has no dataclass-repr equivalent, so
// every call site that might log a bundle MUST route through this helper
// instead of `JSON.stringify(bundle)` / `console.error(bundle)` directly.
// ---------------------------------------------------------------------------

/**
 * A safe-to-log summary of a bundle: everything EXCEPT `vault.*` and
 * `signing.private_key`. Use this (never the raw bundle object) in any
 * `console.error` / log line that touches a bundle.
 */
export function redactedBundleSummary(bundle: DerivedBundleV1): Record<string, unknown> {
  return {
    schema: 'derived-bundle-v1',
    signing_kind: bundle.signing.kind,
    signing_address: bundle.signing.address,
    smart_account: bundle.account.smart_account,
    chain_id: bundle.account.chain_id,
    provisioned_at: bundle.provisioned_at,
    provisioned_by: bundle.provisioned_by,
  };
}
