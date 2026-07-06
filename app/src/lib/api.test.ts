import { describe, it, expect } from "vitest";
import { decryptFacts } from "./api";
import { encryptBlob } from "./crypto";
import { MemoryClaimV1, RawFact, SessionKeys } from "./types";

// Canonical enc key for the BIP-39 all-zeros test mnemonic (see crypto.test.ts).
// decryptFacts only touches keys.encryptionKey, so the rest of SessionKeys is
// stubbed to the minimum the type requires.
const GOLDEN_ENC_KEY_HEX =
  "a58fdc56e1d768461d95cd46b49e03727b2eb342ac558b9f3ebf1255b871f703";

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2)
    out[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  return out;
}

const ENC_KEY = hexToBytes(GOLDEN_ENC_KEY_HEX);

const KEYS: SessionKeys = {
  mnemonic: "",
  authKey: new Uint8Array(),
  encryptionKey: ENC_KEY,
  authKeyHex: "",
  eoaAddress: "0x0",
  walletAddress: "0x0",
  chainId: 84532,
};

// Build a RawFact whose encrypted_blob is the encrypted JSON of `claim`.
// `raw` lets us inject fields that violate the MemoryClaimV1 type (out-of-enum
// source/scope, legacy type tokens) which the on-chain blob may legitimately
// carry from older writers.
function makeFact(
  claim: Partial<MemoryClaimV1> & Record<string, unknown>,
  overrides: Partial<RawFact> = {},
): RawFact {
  const blob = encryptBlob(JSON.stringify(claim), ENC_KEY);
  return {
    id: (claim.id as string) ?? "fact-1",
    encrypted_blob: blob,
    blind_indices: [],
    decay_score: 1,
    version: 4,
    source: "",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}

const baseClaim = {
  id: "c1",
  text: "hello",
  type: "claim",
  source: "user",
  created_at: "2026-01-01T00:00:00.000Z",
  schema_version: "1.0",
};

describe("decryptFacts", () => {
  it("decrypts a valid fact into a normalized VaultItem", () => {
    const items = decryptFacts([makeFact(baseClaim)], KEYS);
    expect(items).toHaveLength(1);
    const item = items[0];
    expect(item.id).toBe("c1");
    expect(item.claim.text).toBe("hello");
    expect(item.claim.source).toBe("user");
    expect(item.type).toBe("claim");
    expect(item.pinned).toBe(false);
    expect(item.createdAt).toEqual(new Date("2026-01-01T00:00:00.000Z"));
    expect(item.decayScore).toBe(1);
  });

  it("clamps an out-of-enum source to 'external'", () => {
    const items = decryptFacts(
      [makeFact({ ...baseClaim, source: "space-alien" })],
      KEYS,
    );
    expect(items[0].claim.source).toBe("external");
  });

  it("preserves a valid non-default source", () => {
    const items = decryptFacts(
      [makeFact({ ...baseClaim, source: "user-inferred" })],
      KEYS,
    );
    expect(items[0].claim.source).toBe("user-inferred");
  });

  it("clamps an out-of-enum scope to 'unspecified'", () => {
    const items = decryptFacts(
      [makeFact({ ...baseClaim, scope: "outer-space" })],
      KEYS,
    );
    expect(items[0].claim.scope).toBe("unspecified");
  });

  it("preserves a valid scope", () => {
    const items = decryptFacts(
      [makeFact({ ...baseClaim, scope: "health" })],
      KEYS,
    );
    expect(items[0].claim.scope).toBe("health");
  });

  it("leaves an absent scope undefined (not clamped)", () => {
    const items = decryptFacts([makeFact(baseClaim)], KEYS);
    expect(items[0].claim.scope).toBeUndefined();
  });

  it("marks pinned when pin_status is 'pinned'", () => {
    const items = decryptFacts(
      [makeFact({ ...baseClaim, pin_status: "pinned" })],
      KEYS,
    );
    expect(items[0].pinned).toBe(true);
  });

  it("skips undecryptable facts without throwing", () => {
    const good = makeFact(baseClaim);
    const corrupt: RawFact = {
      ...good,
      id: "corrupt",
      encrypted_blob: "deadbeef".repeat(10), // valid hex, invalid ciphertext/tag
    };
    const items = decryptFacts([corrupt, good], KEYS);
    expect(items).toHaveLength(1);
    expect(items[0].id).toBe("c1");
  });

  it("skips a fact whose plaintext is not valid JSON", () => {
    // Encrypt a non-JSON payload directly so decrypt succeeds but JSON.parse fails.
    const blob = encryptBlob("this is not json", ENC_KEY);
    const fact: RawFact = { ...makeFact(baseClaim), id: "notjson", encrypted_blob: blob };
    const items = decryptFacts([fact], KEYS);
    expect(items).toHaveLength(0);
  });

  it("returns an empty array for an empty input", () => {
    expect(decryptFacts([], KEYS)).toEqual([]);
  });
});

describe("resolveType (via decryptFacts)", () => {
  it("uses claim.type when it is a valid v1 type", () => {
    const items = decryptFacts(
      [makeFact({ ...baseClaim, type: "preference" })],
      KEYS,
    );
    expect(items[0].type).toBe("preference");
  });

  it("falls back to tags[0] when claim.type is missing", () => {
    const claim = { ...baseClaim, tags: ["directive", "other"] };
    delete (claim as Record<string, unknown>).type;
    const items = decryptFacts([makeFact(claim)], KEYS);
    expect(items[0].type).toBe("directive");
  });

  it("passes a legacy v0 type token through the `| string` escape hatch", () => {
    // v0 tokens (fact, context, decision, episodic, goal, rule) predate the v1
    // closed enum. resolveType surfaces tags[0] verbatim when it is not a v1 type.
    const claim = { ...baseClaim, tags: ["decision"] };
    delete (claim as Record<string, unknown>).type;
    const items = decryptFacts([makeFact(claim)], KEYS);
    expect(items[0].type).toBe("decision");
  });

  it("defaults to 'claim' when neither type nor tags are present", () => {
    const claim = { ...baseClaim };
    delete (claim as Record<string, unknown>).type;
    const items = decryptFacts([makeFact(claim)], KEYS);
    expect(items[0].type).toBe("claim");
  });

  it("prefers a valid claim.type over tags[0]", () => {
    const items = decryptFacts(
      [makeFact({ ...baseClaim, type: "summary", tags: ["episode"] })],
      KEYS,
    );
    expect(items[0].type).toBe("summary");
  });
});
