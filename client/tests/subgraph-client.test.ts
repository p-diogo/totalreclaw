import { SubgraphClient } from "../src/subgraph/client";

const mockFetch = jest.fn();
global.fetch = mockFetch as any;

describe("SubgraphClient", () => {
  let client: SubgraphClient;

  beforeEach(() => {
    client = new SubgraphClient("http://localhost:8000/subgraphs/name/totalreclaw");
    mockFetch.mockReset();
  });

  describe("search", () => {
    it("should query with hash_in for blind index lookup", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            blindIndices: [
              { fact: { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: "enc1", decayScore: "0.9", isActive: true } },
              { fact: { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: "enc1", decayScore: "0.9", isActive: true } },
              { fact: { id: "f2", encryptedBlob: "0xdef", encryptedEmbedding: null, decayScore: "0.5", isActive: true } },
            ]
          }
        })
      });

      const results = await client.search("0xowner", ["hash1", "hash2", "hash3"]);

      expect(results).toHaveLength(2);
      expect(results[0].id).toBe("f1");
      expect(results[1].id).toBe("f2");

      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.query).toContain("hash_in");
      expect(body.variables.trapdoors).toEqual(["hash1", "hash2", "hash3"]);
    });

    it("should paginate when trapdoors exceed GraphQL limit", async () => {
      const manyTrapdoors = Array.from({ length: 600 }, (_, i) => `hash${i}`);

      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ data: { blindIndices: [] } })
      });

      await client.search("0xowner", manyTrapdoors);

      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it("should handle empty results", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: { blindIndices: [] } })
      });

      const results = await client.search("0xowner", ["hash1"]);
      expect(results).toHaveLength(0);
    });
  });

  describe("fetchAllFacts", () => {
    it("should fetch all facts for an owner", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            facts: [
              { id: "f1", encryptedBlob: "0xabc", encryptedEmbedding: "enc1", decayScore: "0.9", isActive: true, sequenceId: "1", blockNumber: "100", timestamp: "1000" },
            ]
          }
        })
      });

      const facts = await client.fetchAllFacts("0xowner");
      expect(facts).toHaveLength(1);
      expect(facts[0].id).toBe("f1");
    });

    it("should paginate when more than PAGE_SIZE facts", async () => {
      const page1 = Array.from({ length: 1000 }, (_, i) => ({
        id: `f${i}`, encryptedBlob: "0x", encryptedEmbedding: null, decayScore: "1.0", isActive: true
      }));
      const page2 = [{ id: "f1000", encryptedBlob: "0x", encryptedEmbedding: null, decayScore: "1.0", isActive: true }];

      mockFetch
        .mockResolvedValueOnce({ ok: true, json: async () => ({ data: { facts: page1 } }) })
        .mockResolvedValueOnce({ ok: true, json: async () => ({ data: { facts: page2 } }) });

      const facts = await client.fetchAllFacts("0xowner");
      expect(facts).toHaveLength(1001);
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });
  });

  describe("deltaSyncFacts", () => {
    it("should fetch facts since a given block number", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            facts: [
              { id: "f2", encryptedBlob: "0xdef", encryptedEmbedding: null, decayScore: "0.7", isActive: true, sequenceId: "2", blockNumber: "200", timestamp: "2000" },
            ]
          }
        })
      });

      const facts = await client.deltaSyncFacts("0xowner", 100);
      expect(facts).toHaveLength(1);

      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.variables.sinceBlock).toBe("100");
    });
  });

  describe("getFactCount", () => {
    it("should return total fact count for an owner", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          data: {
            facts: [{ id: "f1" }, { id: "f2" }, { id: "f3" }]
          }
        })
      });

      const count = await client.getFactCount("0xowner");
      expect(count).toBe(3);
    });

    it("should return 0 for empty result", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: { facts: [] } })
      });

      const count = await client.getFactCount("0xowner");
      expect(count).toBe(0);
    });
  });

  describe("error handling", () => {
    it("should throw on HTTP error", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
      });

      await expect(client.search("0xowner", ["hash1"])).rejects.toThrow("Subgraph query failed: 500");
    });

    it("should throw on GraphQL error", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          errors: [{ message: "Query too complex" }]
        })
      });

      await expect(client.search("0xowner", ["hash1"])).rejects.toThrow("Subgraph query error: Query too complex");
    });
  });
});
