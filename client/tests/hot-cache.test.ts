/**
 * Hot Cache Tests
 *
 * Tests for the persistent encrypted hot cache that stores
 * high-importance facts for instant auto-recall.
 */

import { HotCache } from "../src/cache/hot-cache";
import { existsSync, unlinkSync } from "fs";

const TEST_CACHE_PATH = "/tmp/totalreclaw-test-cache.enc";
const TEST_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

describe("HotCache", () => {
  let cache: HotCache;

  beforeEach(() => {
    cache = new HotCache(TEST_CACHE_PATH, TEST_KEY);
    if (existsSync(TEST_CACHE_PATH)) unlinkSync(TEST_CACHE_PATH);
  });

  afterEach(() => {
    if (existsSync(TEST_CACHE_PATH)) unlinkSync(TEST_CACHE_PATH);
  });

  it("should start empty", () => {
    expect(cache.getHotFacts()).toEqual([]);
    expect(cache.getFactCount()).toBe(0);
    expect(cache.getLastSyncedBlock()).toBe(0);
  });

  it("should store and retrieve hot facts", () => {
    const facts = [
      { id: "f1", text: "User is a software engineer", importance: 9 },
      { id: "f2", text: "User likes TypeScript", importance: 7 },
    ];
    cache.setHotFacts(facts);
    expect(cache.getHotFacts()).toEqual(facts);
  });

  it("should persist to disk encrypted and load back", () => {
    const facts = [{ id: "f1", text: "Persistent fact", importance: 8 }];
    cache.setHotFacts(facts);
    cache.setFactCount(42);
    cache.setLastSyncedBlock(12345);
    cache.flush();

    expect(existsSync(TEST_CACHE_PATH)).toBe(true);

    const cache2 = new HotCache(TEST_CACHE_PATH, TEST_KEY);
    cache2.load();
    expect(cache2.getHotFacts()).toEqual(facts);
    expect(cache2.getFactCount()).toBe(42);
    expect(cache2.getLastSyncedBlock()).toBe(12345);
  });

  it("should fail to load with wrong key", () => {
    cache.setHotFacts([{ id: "f1", text: "secret", importance: 9 }]);
    cache.flush();

    const wrongKey = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";
    const cache2 = new HotCache(TEST_CACHE_PATH, wrongKey);
    cache2.load();
    expect(cache2.getHotFacts()).toEqual([]);
  });

  it("should limit hot facts to 30", () => {
    const facts = Array.from({ length: 50 }, (_, i) => ({
      id: `f${i}`, text: `Fact ${i}`, importance: i % 10
    }));
    cache.setHotFacts(facts);
    expect(cache.getHotFacts().length).toBeLessThanOrEqual(30);
  });

  it("should keep highest importance facts when limiting", () => {
    const facts = Array.from({ length: 50 }, (_, i) => ({
      id: `f${i}`, text: `Fact ${i}`, importance: i
    }));
    cache.setHotFacts(facts);
    const hot = cache.getHotFacts();
    // Should keep the 30 highest importance (20-49)
    expect(hot.length).toBe(30);
    expect(hot[0].importance).toBe(49);
    expect(hot[29].importance).toBe(20);
  });

  it("should store Smart Account address", () => {
    cache.setSmartAccountAddress("0x1234567890abcdef");
    cache.flush();

    const cache2 = new HotCache(TEST_CACHE_PATH, TEST_KEY);
    cache2.load();
    expect(cache2.getSmartAccountAddress()).toBe("0x1234567890abcdef");
  });

  it("should handle loading from non-existent file gracefully", () => {
    cache.load();
    expect(cache.getHotFacts()).toEqual([]);
    expect(cache.getFactCount()).toBe(0);
    expect(cache.getLastSyncedBlock()).toBe(0);
    expect(cache.getSmartAccountAddress()).toBe("");
  });

  it("should handle corrupted file gracefully", () => {
    // Write garbage to the file
    const fs = require("fs");
    fs.writeFileSync(TEST_CACHE_PATH, Buffer.from("not-encrypted-data"));

    cache.load();
    expect(cache.getHotFacts()).toEqual([]);
    expect(cache.getFactCount()).toBe(0);
  });

  it("should return a copy of hot facts (not a reference)", () => {
    const facts = [{ id: "f1", text: "Fact 1", importance: 5 }];
    cache.setHotFacts(facts);
    const retrieved = cache.getHotFacts();
    retrieved.push({ id: "f2", text: "Injected", importance: 10 });
    expect(cache.getHotFacts().length).toBe(1);
  });
});
