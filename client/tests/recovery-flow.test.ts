import { restoreFromMnemonic, RestoreOptions } from "../src/recovery/restore";
import { existsSync, unlinkSync } from "fs";

const mockFetch = jest.fn();
global.fetch = mockFetch as any;

const TEST_CACHE_PATH = "/tmp/totalreclaw-test-recovery-cache.enc";

// Mock key derivation
const mockDeriveKeys = jest.fn().mockReturnValue({
  encryptionKeyHex: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  smartAccountAddress: "0x1234567890abcdef1234567890abcdef12345678",
});

// Mock decryption
const mockDecrypt = jest.fn();

const defaultOptions: RestoreOptions = {
  subgraphEndpoint: "http://localhost:8000/subgraphs/name/totalreclaw",
  cachePath: TEST_CACHE_PATH,
  deriveKeys: mockDeriveKeys,
  decrypt: mockDecrypt,
};

describe("Recovery Flow", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockDeriveKeys.mockClear();
    mockDecrypt.mockReset();
    if (existsSync(TEST_CACHE_PATH)) unlinkSync(TEST_CACHE_PATH);
  });

  afterEach(() => {
    if (existsSync(TEST_CACHE_PATH)) unlinkSync(TEST_CACHE_PATH);
  });

  it("should restore all facts from a mnemonic", async () => {
    // Mock subgraph returning 3 facts
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          facts: [
            { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: null, decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000", version: 2 },
            { id: "f2", encryptedBlob: "0xdef", encryptedEmbedding: null, decayScore: "0.7", isActive: true, sequenceId: "2", blockNumber: "200", timestamp: "2000", version: 2 },
            { id: "f3", encryptedBlob: "0x123", encryptedEmbedding: null, decayScore: "0.5", isActive: true, sequenceId: "3", blockNumber: "300", timestamp: "3000", version: 2 },
          ]
        }
      })
    });

    // Mock decryption returning different docs
    mockDecrypt
      .mockReturnValueOnce(JSON.stringify({ text: "User is a software engineer", metadata: { type: "fact", importance: 0.9 } }))
      .mockReturnValueOnce(JSON.stringify({ text: "User likes TypeScript", metadata: { type: "preference", importance: 0.7 } }))
      .mockReturnValueOnce(JSON.stringify({ text: "User lives in Lisbon", metadata: { type: "fact", importance: 0.8 } }));

    const result = await restoreFromMnemonic("test mnemonic phrase here twelve words for testing only please", defaultOptions);

    expect(result.totalFacts).toBe(3);
    expect(result.restoredFacts).toHaveLength(3);
    expect(result.failedDecryptions).toBe(0);
    expect(result.hotCachePopulated).toBe(true);
    expect(result.smartAccountAddress).toBe("0x1234567890abcdef1234567890abcdef12345678");

    // Verify fact content
    expect(result.restoredFacts[0].text).toBe("User is a software engineer");
    expect(result.restoredFacts[0].importance).toBe(9); // 0.9 * 10
    expect(result.restoredFacts[1].text).toBe("User likes TypeScript");
  });

  it("should handle empty subgraph (new user)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { facts: [] } })
    });

    const result = await restoreFromMnemonic("empty wallet mnemonic twelve words for testing only please", defaultOptions);

    expect(result.totalFacts).toBe(0);
    expect(result.restoredFacts).toHaveLength(0);
    expect(result.failedDecryptions).toBe(0);
  });

  it("should handle decryption failures gracefully", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          facts: [
            { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: null, decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000", version: 2 },
            { id: "f2", encryptedBlob: "0xcorrupt", encryptedEmbedding: null, decayScore: "0.5", isActive: true, sequenceId: "2", blockNumber: "200", timestamp: "2000", version: 2 },
          ]
        }
      })
    });

    mockDecrypt
      .mockReturnValueOnce(JSON.stringify({ text: "Valid fact", metadata: { type: "fact", importance: 0.8 } }))
      .mockImplementationOnce(() => { throw new Error("Decryption failed"); });

    const result = await restoreFromMnemonic("test mnemonic twelve words for testing only please ignore this", defaultOptions);

    expect(result.totalFacts).toBe(2);
    expect(result.restoredFacts).toHaveLength(1);
    expect(result.failedDecryptions).toBe(1);
    expect(result.restoredFacts[0].text).toBe("Valid fact");
  });

  it("should populate hot cache after recovery", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          facts: [
            { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: null, decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000", version: 2 },
          ]
        }
      })
    });

    mockDecrypt.mockReturnValueOnce(JSON.stringify({ text: "Cached fact", metadata: { type: "fact", importance: 0.9 } }));

    const result = await restoreFromMnemonic("cache test mnemonic twelve words for testing only please ignore", defaultOptions);

    expect(result.hotCachePopulated).toBe(true);
    expect(existsSync(TEST_CACHE_PATH)).toBe(true);
  });

  it("should derive keys from the mnemonic", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: { facts: [] } })
    });

    await restoreFromMnemonic("derive keys test twelve words for testing only please ignore it", defaultOptions);

    expect(mockDeriveKeys).toHaveBeenCalledWith("derive keys test twelve words for testing only please ignore it");
  });

  it("should handle hot cache failure gracefully", async () => {
    // Use an invalid cache path that will cause flush() to fail
    const badOptions: RestoreOptions = {
      ...defaultOptions,
      cachePath: "/nonexistent/deeply/nested/path/that/cannot/be/created\0invalid/cache.enc",
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          facts: [
            { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: null, decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000", version: 2 },
          ]
        }
      })
    });

    mockDecrypt.mockReturnValueOnce(JSON.stringify({ text: "Fact without cache", metadata: { type: "fact", importance: 0.8 } }));

    const result = await restoreFromMnemonic("cache fail mnemonic twelve words for testing only please ignore", badOptions);

    // Facts should still be restored even if cache fails
    expect(result.totalFacts).toBe(1);
    expect(result.restoredFacts).toHaveLength(1);
    expect(result.hotCachePopulated).toBe(false);
  });

  it("should parse decayScore from string to number", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          facts: [
            { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: null, decayScore: "0.12345", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000", version: 2 },
          ]
        }
      })
    });

    mockDecrypt.mockReturnValueOnce(JSON.stringify({ text: "Decay test", metadata: { type: "fact", importance: 0.5 } }));

    const result = await restoreFromMnemonic("decay test mnemonic twelve words for testing only please ignore", defaultOptions);

    expect(result.restoredFacts[0].decayScore).toBe(0.12345);
    expect(typeof result.restoredFacts[0].decayScore).toBe("number");
  });

  it("should handle facts without importance metadata", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          facts: [
            { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: null, decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000", version: 2 },
          ]
        }
      })
    });

    // No metadata at all
    mockDecrypt.mockReturnValueOnce(JSON.stringify({ text: "Simple fact without metadata" }));

    const result = await restoreFromMnemonic("no metadata mnemonic twelve words for testing only please ignore", defaultOptions);

    expect(result.restoredFacts[0].importance).toBeUndefined();
    expect(result.restoredFacts[0].type).toBeUndefined();
    expect(result.restoredFacts[0].text).toBe("Simple fact without metadata");
  });

  it("should pass encrypted blobs to decrypt function correctly", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        data: {
          facts: [
            { id: "f1", encryptedBlob: "0xdeadbeef", encryptedEmbedding: null, decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000", version: 2 },
          ]
        }
      })
    });

    mockDecrypt.mockReturnValueOnce(JSON.stringify({ text: "Test" }));

    await restoreFromMnemonic("decrypt args mnemonic twelve words for testing only please ignore", defaultOptions);

    expect(mockDecrypt).toHaveBeenCalledWith(
      "0xdeadbeef",
      "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    );
  });
});
