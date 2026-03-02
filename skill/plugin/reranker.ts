/**
 * TotalReclaw Plugin - Client-Side Re-Ranker
 *
 * Replaces the naive `textScore` word-overlap scorer with a proper ranking
 * pipeline:
 *   1. Okapi BM25 — term frequency / inverse document frequency
 *   2. Cosine similarity — between query and fact embeddings
 *   3. RRF (Reciprocal Rank Fusion) — combines multiple ranking lists
 *
 * All functions are pure TypeScript with zero external dependencies (except
 * porter-stemmer for morphological normalization). This module runs
 * CLIENT-SIDE after decrypting candidates from the server.
 */

import { stemmer } from 'porter-stemmer';

// ---------------------------------------------------------------------------
// Tokenization
// ---------------------------------------------------------------------------

/**
 * Tokenize a text string for BM25 scoring.
 *
 * Matches the tokenization rules used for blind indices in crypto.ts:
 *   1. Lowercase
 *   2. Remove punctuation (keep Unicode letters, numbers, whitespace)
 *   3. Split on whitespace
 *   4. Filter tokens shorter than 2 characters
 *
 * Optionally removes common English stop words (enabled by default) to
 * improve BM25 signal — stop words have low IDF and add noise.
 */
const STOP_WORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'do', 'for',
  'from', 'had', 'has', 'have', 'he', 'her', 'him', 'his', 'how', 'if',
  'in', 'into', 'is', 'it', 'its', 'me', 'my', 'no', 'not', 'of', 'on',
  'or', 'our', 'out', 'she', 'so', 'than', 'that', 'the', 'their', 'them',
  'then', 'there', 'these', 'they', 'this', 'to', 'up', 'us', 'was', 'we',
  'were', 'what', 'when', 'where', 'which', 'who', 'whom', 'why', 'will',
  'with', 'you', 'your',
]);

export function tokenize(text: string, removeStopWords: boolean = true): string[] {
  let tokens = text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter((t) => t.length >= 2);

  if (removeStopWords) {
    tokens = tokens.filter((t) => !STOP_WORDS.has(t));
  }

  // Stem each token for morphological normalization.
  // This ensures BM25 matches "gaming" with "games" (both stem to "game").
  return tokens.map((t) => stemmer(t));
}

// ---------------------------------------------------------------------------
// BM25 Scoring (Okapi BM25)
// ---------------------------------------------------------------------------

/**
 * Compute the Okapi BM25 score for a single document against a query.
 *
 * Formula:
 *   score = SUM_i IDF(qi) * (f(qi, D) * (k1 + 1)) / (f(qi, D) + k1 * (1 - b + b * |D| / avgdl))
 *
 * where:
 *   IDF(qi) = ln((N - n(qi) + 0.5) / (n(qi) + 0.5) + 1)
 *   f(qi, D) = frequency of term qi in document D
 *   |D| = length of document D (in tokens)
 *   avgdl = average document length across the corpus
 *   N = total number of documents
 *   n(qi) = number of documents containing term qi
 *
 * @param queryTerms  - Tokenized query terms
 * @param docTerms    - Tokenized document terms
 * @param avgDocLen   - Average document length (in tokens) across the candidate corpus
 * @param docCount    - Total number of documents in the candidate corpus
 * @param termDocFreqs - Map from term to number of documents containing that term
 * @param k1          - BM25 k1 parameter (default 1.2)
 * @param b           - BM25 b parameter (default 0.75)
 */
export function bm25Score(
  queryTerms: string[],
  docTerms: string[],
  avgDocLen: number,
  docCount: number,
  termDocFreqs: Map<string, number>,
  k1: number = 1.2,
  b: number = 0.75,
): number {
  if (docTerms.length === 0 || avgDocLen === 0 || docCount === 0) return 0;

  // Count term frequencies in this document.
  const docTf = new Map<string, number>();
  for (const term of docTerms) {
    docTf.set(term, (docTf.get(term) ?? 0) + 1);
  }

  const docLen = docTerms.length;
  let score = 0;

  for (const qi of queryTerms) {
    const freq = docTf.get(qi) ?? 0;
    if (freq === 0) continue;

    const nqi = termDocFreqs.get(qi) ?? 0;

    // IDF with Robertson-Walker floor: ln((N - n + 0.5) / (n + 0.5) + 1)
    // The +1 inside ln ensures IDF is always >= 0 even when n > N/2.
    const idf = Math.log((docCount - nqi + 0.5) / (nqi + 0.5) + 1);

    // TF saturation with length normalization.
    const tfNorm = (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * docLen / avgDocLen));

    score += idf * tfNorm;
  }

  return score;
}

// ---------------------------------------------------------------------------
// Cosine Similarity
// ---------------------------------------------------------------------------

/**
 * Compute cosine similarity between two vectors.
 *
 * Returns dot(a, b) / (||a|| * ||b||).
 * Returns 0 if either vector has zero magnitude (avoids division by zero).
 */
export function cosineSimilarity(a: number[], b: number[]): number {
  if (a.length === 0 || b.length === 0) return 0;

  const len = Math.min(a.length, b.length);
  let dot = 0;
  let normA = 0;
  let normB = 0;

  for (let i = 0; i < len; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  if (denom === 0) return 0;

  return dot / denom;
}

// ---------------------------------------------------------------------------
// Reciprocal Rank Fusion (RRF)
// ---------------------------------------------------------------------------

export interface RankedItem {
  id: string;
  score: number;
}

/**
 * Fuse multiple ranking lists using Reciprocal Rank Fusion.
 *
 * For each document d appearing in any ranking list:
 *   rrfScore(d) = SUM_i 1 / (k + rank_i(d))
 *
 * where rank_i(d) is the 1-based rank of document d in the i-th list.
 * Documents not present in a list are not penalized (they simply receive
 * no contribution from that list).
 *
 * @param rankings - Array of ranking lists, each sorted by score descending.
 *                   Each item has an `id` and a `score`.
 * @param k        - RRF smoothing constant (default 60, per the original paper).
 * @returns        - Fused ranking sorted by RRF score descending.
 */
export function rrfFuse(
  rankings: RankedItem[][],
  k: number = 60,
): RankedItem[] {
  const fusedScores = new Map<string, number>();

  for (const ranking of rankings) {
    for (let rank = 0; rank < ranking.length; rank++) {
      const item = ranking[rank];
      const contribution = 1 / (k + rank + 1); // rank is 0-based, formula uses 1-based
      fusedScores.set(item.id, (fusedScores.get(item.id) ?? 0) + contribution);
    }
  }

  const fused: RankedItem[] = [];
  for (const [id, score] of fusedScores) {
    fused.push({ id, score });
  }

  fused.sort((a, b) => b.score - a.score);
  return fused;
}

// ---------------------------------------------------------------------------
// Combined Re-Ranker
// ---------------------------------------------------------------------------

export interface RerankerCandidate {
  id: string;
  text: string;
  embedding?: number[];
}

/**
 * Re-rank decrypted candidates using BM25 + Cosine + RRF fusion.
 *
 * Pipeline:
 *   1. Tokenize query and all candidate texts
 *   2. Build corpus statistics (term document frequencies, average doc length)
 *   3. Score each candidate with BM25
 *   4. Score each candidate with cosine similarity (if embedding available)
 *   5. Rank independently by BM25 and by cosine
 *   6. Fuse rankings with RRF
 *   7. Return top-k candidates sorted by fused score
 *
 * Backward compatibility:
 *   - Candidates without embeddings get cosine score = 0 and are excluded
 *     from the cosine ranking list. They can still rank well via BM25.
 *   - If NO candidates have embeddings, ranking is BM25-only (single list RRF).
 *
 * @param query          - The user's search query (plaintext)
 * @param queryEmbedding - Embedding vector for the query
 * @param candidates     - Decrypted candidates with text and optional embeddings
 * @param topK           - Number of results to return (default 8)
 * @returns              - Top-k candidates sorted by fused score
 */
export function rerank(
  query: string,
  queryEmbedding: number[],
  candidates: RerankerCandidate[],
  topK: number = 8,
): RerankerCandidate[] {
  if (candidates.length === 0) return [];

  // --- Step 1: Tokenize ---
  const queryTerms = tokenize(query);
  const candidateTerms = candidates.map((c) => tokenize(c.text));

  // --- Step 2: Corpus statistics ---
  const docCount = candidates.length;
  let totalDocLen = 0;

  // Count how many documents contain each term.
  const termDocFreqs = new Map<string, number>();
  for (const terms of candidateTerms) {
    totalDocLen += terms.length;
    const uniqueTerms = new Set(terms);
    for (const term of uniqueTerms) {
      termDocFreqs.set(term, (termDocFreqs.get(term) ?? 0) + 1);
    }
  }

  const avgDocLen = docCount > 0 ? totalDocLen / docCount : 0;

  // --- Step 3: BM25 scores ---
  const bm25Ranking: RankedItem[] = [];
  for (let i = 0; i < candidates.length; i++) {
    const score = bm25Score(queryTerms, candidateTerms[i], avgDocLen, docCount, termDocFreqs);
    bm25Ranking.push({ id: candidates[i].id, score });
  }
  bm25Ranking.sort((a, b) => b.score - a.score);

  // --- Step 4: Cosine similarity scores ---
  const cosineRanking: RankedItem[] = [];
  for (const candidate of candidates) {
    if (candidate.embedding && candidate.embedding.length > 0) {
      const score = cosineSimilarity(queryEmbedding, candidate.embedding);
      cosineRanking.push({ id: candidate.id, score });
    }
  }
  cosineRanking.sort((a, b) => b.score - a.score);

  // --- Step 5+6: RRF fusion ---
  const rankings: RankedItem[][] = [bm25Ranking];
  if (cosineRanking.length > 0) {
    rankings.push(cosineRanking);
  }

  const fused = rrfFuse(rankings);

  // --- Step 7: Return top-k ---
  // Build a lookup map from candidate id to candidate object.
  const candidateMap = new Map<string, RerankerCandidate>();
  for (const c of candidates) {
    candidateMap.set(c.id, c);
  }

  const result: RerankerCandidate[] = [];
  for (const item of fused) {
    if (result.length >= topK) break;
    const candidate = candidateMap.get(item.id);
    if (candidate) {
      result.push(candidate);
    }
  }

  return result;
}
