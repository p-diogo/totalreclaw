/**
 * Blind Index Generation
 *
 * Creates SHA-256 hashes of tokens and LSH buckets for searchable encryption.
 * The server can match these hashes without knowing the original content.
 */

import * as crypto from 'crypto';
import { TotalReclawError, TotalReclawErrorCode } from '../types';

/**
 * Tokenize text into words for blind indexing
 *
 * Performs basic tokenization:
 * - Converts to lowercase
 * - Removes punctuation
 * - Splits on whitespace
 * - Filters out short tokens (< 2 chars)
 *
 * @param text - Text to tokenize
 * @returns Array of tokens
 */
export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ') // Remove punctuation, keep letters/numbers
    .split(/\s+/)
    .filter((token) => token.length >= 2);
}

/**
 * Compute SHA-256 hash of a string
 *
 * @param input - String to hash
 * @returns Hex-encoded SHA-256 hash
 */
export function sha256Hash(input: string): string {
  return crypto.createHash('sha256').update(input, 'utf-8').digest('hex');
}

/**
 * Generate blind indices from text and LSH buckets
 *
 * Creates SHA-256 hashes of:
 * 1. All tokens in the text (for keyword search)
 * 2. All LSH bucket identifiers (for semantic search)
 *
 * @param text - Document text
 * @param lshBuckets - Array of LSH bucket identifiers
 * @returns Array of blind indices (hex-encoded SHA-256 hashes)
 */
export function generateBlindIndices(
  text: string,
  lshBuckets: string[]
): string[] {
  const indices: Set<string> = new Set();

  // Hash all tokens from the text
  const tokens = tokenize(text);
  for (const token of tokens) {
    indices.add(sha256Hash(token));
  }

  // Hash all LSH buckets
  for (const bucket of lshBuckets) {
    indices.add(sha256Hash(bucket));
  }

  return Array.from(indices);
}

/**
 * Generate trapdoors for search query
 *
 * Trapdoors are SHA-256 hashes of:
 * 1. All tokens in the query (for keyword matching)
 * 2. All LSH bucket identifiers from query embedding (for semantic matching)
 *
 * The server can use these to find matching documents without knowing
 * the original query content.
 *
 * @param query - Search query text
 * @param lshBuckets - LSH bucket identifiers from query embedding
 * @returns Array of trapdoors (hex-encoded SHA-256 hashes)
 */
export function generateTrapdoors(
  query: string,
  lshBuckets: string[]
): string[] {
  const trapdoors: Set<string> = new Set();

  // Hash query tokens for keyword matching
  const tokens = tokenize(query);
  for (const token of tokens) {
    trapdoors.add(sha256Hash(token));
  }

  // Hash LSH buckets for semantic matching
  for (const bucket of lshBuckets) {
    trapdoors.add(sha256Hash(bucket));
  }

  return Array.from(trapdoors);
}

/**
 * Generate only token-based blind indices (without LSH)
 *
 * Useful for keyword-only search or when embedding is not available.
 *
 * @param text - Text to index
 * @returns Array of blind indices for tokens only
 */
export function generateTokenIndices(text: string): string[] {
  const tokens = tokenize(text);
  return tokens.map(sha256Hash);
}

/**
 * Generate only LSH-based blind indices (without tokens)
 *
 * Useful for pure semantic search.
 *
 * @param lshBuckets - LSH bucket identifiers
 * @returns Array of blind indices for LSH buckets only
 */
export function generateLSHIndices(lshBuckets: string[]): string[] {
  return lshBuckets.map(sha256Hash);
}

/**
 * Verify that a blind index matches a trapdoor
 *
 * Since both are SHA-256 hashes, this is a simple equality check.
 *
 * @param blindIndex - Blind index from stored document
 * @param trapdoor - Trapdoor from search query
 * @returns True if they match
 */
export function verifyBlindIndexMatch(
  blindIndex: string,
  trapdoor: string
): boolean {
  return blindIndex === trapdoor;
}

/**
 * Compute the overlap between two sets of blind indices
 *
 * Used to estimate recall quality during development.
 *
 * @param indices1 - First set of indices
 * @param indices2 - Second set of indices
 * @returns Number of matching indices
 */
export function computeIndexOverlap(
  indices1: string[],
  indices2: string[]
): number {
  const set1 = new Set(indices1);
  const set2 = new Set(indices2);
  let overlap = 0;

  for (const index of set1) {
    if (set2.has(index)) {
      overlap++;
    }
  }

  return overlap;
}

/**
 * Generate n-gram tokens from text
 *
 * Useful for fuzzy matching of partial words.
 *
 * @param text - Text to tokenize
 * @param n - N-gram size (default: 3)
 * @returns Array of n-gram tokens
 */
export function generateNgrams(text: string, n: number = 3): string[] {
  const normalized = text.toLowerCase().replace(/\s+/g, ' ');
  const ngrams: string[] = [];

  for (let i = 0; i <= normalized.length - n; i++) {
    ngrams.push(normalized.substring(i, i + n));
  }

  return ngrams;
}

/**
 * Generate blind indices with n-gram support for fuzzy matching
 *
 * @param text - Text to index
 * @param lshBuckets - LSH bucket identifiers
 * @param includeNgrams - Whether to include n-gram indices
 * @param ngramSize - Size of n-grams (default: 3)
 * @returns Array of blind indices
 */
export function generateBlindIndicesWithNgrams(
  text: string,
  lshBuckets: string[],
  includeNgrams: boolean = false,
  ngramSize: number = 3
): string[] {
  const indices: Set<string> = new Set();

  // Standard token indices
  const tokens = tokenize(text);
  for (const token of tokens) {
    indices.add(sha256Hash(token));
  }

  // N-gram indices for fuzzy matching
  if (includeNgrams) {
    const ngrams = generateNgrams(text, ngramSize);
    for (const ngram of ngrams) {
      indices.add(sha256Hash(ngram));
    }
  }

  // LSH bucket indices
  for (const bucket of lshBuckets) {
    indices.add(sha256Hash(bucket));
  }

  return Array.from(indices);
}
