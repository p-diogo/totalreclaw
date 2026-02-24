/**
 * Search Module Tests
 *
 * Tests for BM25 scoring, cosine similarity, RRF fusion, and decay calculation.
 */

import {
  cosineSimilarity,
  BM25Scorer,
  rrfFusion,
  normalizeScores,
  combineSignals,
} from '../src/search/rerank';
import {
  calculateDecayScore,
  exponentialDecay,
  halfLifeToDecayRate,
  daysUntilThreshold,
  boostOnAccess,
  multiFactorDecay,
} from '../src/search/decay';

describe('Search Module', () => {
  describe('Cosine Similarity', () => {
    test('should return 1 for identical vectors', () => {
      const vec = [1, 2, 3, 4, 5];
      expect(cosineSimilarity(vec, vec)).toBeCloseTo(1, 5);
    });

    test('should return 0 for orthogonal vectors', () => {
      const vec1 = [1, 0, 0];
      const vec2 = [0, 1, 0];
      expect(cosineSimilarity(vec1, vec2)).toBeCloseTo(0, 5);
    });

    test('should return -1 for opposite vectors', () => {
      const vec1 = [1, 2, 3];
      const vec2 = [-1, -2, -3];
      expect(cosineSimilarity(vec1, vec2)).toBeCloseTo(-1, 5);
    });

    test('should handle zero vectors', () => {
      const vec1 = [0, 0, 0];
      const vec2 = [1, 2, 3];
      expect(cosineSimilarity(vec1, vec2)).toBe(0);
    });

    test('should throw on length mismatch', () => {
      expect(() => cosineSimilarity([1, 2], [1, 2, 3])).toThrow('mismatch');
    });

    test('should compute similarity for normalized vectors', () => {
      // Two normalized vectors at 60 degree angle
      const vec1 = [1, 0];
      const vec2 = [0.5, Math.sqrt(3) / 2];
      expect(cosineSimilarity(vec1, vec2)).toBeCloseTo(0.5, 5);
    });
  });

  describe('BM25 Scorer', () => {
    let scorer: BM25Scorer;

    beforeEach(() => {
      scorer = new BM25Scorer();
    });

    test('should index documents', () => {
      scorer.indexDocuments([
        { id: '1', text: 'hello world' },
        { id: '2', text: 'goodbye world' },
      ]);

      expect(scorer.getDocCount()).toBe(2);
    });

    test('should score documents with matching terms', () => {
      scorer.indexDocuments([
        { id: '1', text: 'hello world' },
        { id: '2', text: 'goodbye world' },
      ]);

      const score1 = scorer.score('hello', '1', 'hello world');
      const score2 = scorer.score('hello', '2', 'goodbye world');

      // Document 1 should score higher for 'hello' query
      expect(score1).toBeGreaterThan(score2);
    });

    test('should return 0 for no matching terms', () => {
      scorer.indexDocuments([
        { id: '1', text: 'hello world' },
      ]);

      const score = scorer.score('goodbye', '1', 'hello world');
      expect(score).toBe(0);
    });

    test('should compute quick score without indexing', () => {
      const score = scorer.quickScore('hello', 'hello world');
      expect(score).toBeGreaterThan(0);
    });

    test('should handle empty documents', () => {
      scorer.indexDocuments([
        { id: '1', text: '' },
      ]);

      expect(scorer.getDocCount()).toBe(1);
    });
  });

  describe('RRF Fusion', () => {
    test('should combine single ranking', () => {
      const rankings = [[{ id: 'a' }, { id: 'b' }, { id: 'c' }]];
      const scores = rrfFusion(rankings);

      expect(scores.size).toBe(3);
      expect(scores.get('a')!).toBeGreaterThan(scores.get('b')!);
      expect(scores.get('b')!).toBeGreaterThan(scores.get('c')!);
    });

    test('should combine multiple rankings', () => {
      const rankings = [
        [{ id: 'a' }, { id: 'b' }, { id: 'c' }],
        [{ id: 'c' }, { id: 'b' }, { id: 'a' }],
      ];
      const scores = rrfFusion(rankings);

      expect(scores.size).toBe(3);

      // Just verify that all items have a score
      expect(scores.get('a')).toBeDefined();
      expect(scores.get('b')).toBeDefined();
      expect(scores.get('c')).toBeDefined();

      // All scores should be positive
      expect(scores.get('a')!).toBeGreaterThan(0);
      expect(scores.get('b')!).toBeGreaterThan(0);
      expect(scores.get('c')!).toBeGreaterThan(0);
    });

    test('should handle different items in rankings', () => {
      const rankings = [
        [{ id: 'a' }, { id: 'b' }],
        [{ id: 'c' }, { id: 'd' }],
      ];
      const scores = rrfFusion(rankings);

      expect(scores.size).toBe(4);
      // All should have same score since they appear only once
      expect(scores.get('a')).toBe(scores.get('c'));
    });
  });

  describe('Normalize Scores', () => {
    test('should normalize to [0, 1] range', () => {
      const scores = [0, 5, 10];
      const normalized = normalizeScores(scores);

      expect(normalized[0]).toBe(0);
      expect(normalized[1]).toBe(0.5);
      expect(normalized[2]).toBe(1);
    });

    test('should handle empty array', () => {
      const normalized = normalizeScores([]);
      expect(normalized).toEqual([]);
    });

    test('should handle uniform values', () => {
      const normalized = normalizeScores([5, 5, 5]);
      expect(normalized).toEqual([0.5, 0.5, 0.5]);
    });
  });

  describe('Combine Signals', () => {
    test('should combine signals with weights', () => {
      const signal1 = new Map([['a', 1], ['b', 0]]);
      const signal2 = new Map([['a', 0], ['b', 1]]);

      const combined = combineSignals([signal1, signal2], [0.5, 0.5]);

      expect(combined.length).toBe(2);
      // Both 'a' and 'b' should have same combined score
      const aScore = combined.find((r) => r.id === 'a')!.score;
      const bScore = combined.find((r) => r.id === 'b')!.score;
      expect(aScore).toBeCloseTo(bScore, 5);
    });

    test('should throw on mismatched weights', () => {
      const signal1 = new Map([['a', 1]]);
      expect(() => combineSignals([signal1], [0.5, 0.5])).toThrow('must match');
    });

    test('should throw on weights not summing to 1', () => {
      const signal1 = new Map([['a', 1]]);
      expect(() => combineSignals([signal1], [0.6])).toThrow('must sum to 1');
    });
  });

  describe('Decay Calculation', () => {
    test('should calculate decay score', () => {
      const score = calculateDecayScore(1.0, 0, 0);
      expect(score).toBe(1.0);
    });

    test('should decay over time', () => {
      const freshScore = calculateDecayScore(1.0, 0, 0);
      const oldScore = calculateDecayScore(1.0, 30, 0);

      expect(oldScore).toBeLessThan(freshScore);
    });

    test('should boost with access count', () => {
      const noAccess = calculateDecayScore(1.0, 10, 0);
      const withAccess = calculateDecayScore(1.0, 10, 5);

      expect(withAccess).toBeGreaterThan(noAccess);
    });

    test('should cap access boost', () => {
      const moderateAccess = calculateDecayScore(1.0, 10, 5);
      const excessiveAccess = calculateDecayScore(1.0, 10, 1000);

      // Should not differ much due to cap
      expect(excessiveAccess).toBeLessThanOrEqual(moderateAccess * 1.5);
    });

    test('should respect minimum score', () => {
      const score = calculateDecayScore(1.0, 1000, 0);
      expect(score).toBeGreaterThan(0);
    });

    test('should clamp importance to valid range', () => {
      const score1 = calculateDecayScore(2.0, 0, 0); // Over 1
      const score2 = calculateDecayScore(-0.5, 0, 0); // Under 0

      expect(score1).toBeLessThanOrEqual(1);
      expect(score2).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Exponential Decay', () => {
    test('should halve at half-life', () => {
      const score = exponentialDecay(1.0, 30, 30);
      expect(score).toBeCloseTo(0.5, 5);
    });

    test('should preserve value at day 0', () => {
      const score = exponentialDecay(0.8, 0, 30);
      expect(score).toBeCloseTo(0.8, 5);
    });
  });

  describe('Half-life Conversion', () => {
    test('should convert half-life to decay rate', () => {
      const rate = halfLifeToDecayRate(30);
      expect(rate).toBeGreaterThan(0);
      expect(rate).toBeLessThan(1);
    });
  });

  describe('Days Until Threshold', () => {
    test('should calculate days correctly', () => {
      const days = daysUntilThreshold(1.0, 0.5, halfLifeToDecayRate(30));
      expect(days).toBeCloseTo(30, 1);
    });

    test('should return 0 if already below threshold', () => {
      const days = daysUntilThreshold(0.3, 0.5, 0.1);
      expect(days).toBe(0);
    });
  });

  describe('Boost on Access', () => {
    test('should boost score towards 1', () => {
      const boosted = boostOnAccess(0.5, 0.5);
      expect(boosted).toBeGreaterThan(0.5);
      expect(boosted).toBeLessThanOrEqual(1);
    });

    test('should not exceed 1', () => {
      const boosted = boostOnAccess(0.9, 0.5);
      expect(boosted).toBeLessThanOrEqual(1);
    });
  });

  describe('Multi-factor Decay', () => {
    test('should combine multiple factors', () => {
      const score = multiFactorDecay({
        importance: 1.0,
        daysSinceCreation: 10,
        daysSinceAccess: 5,
        accessCount: 3,
      });

      expect(score).toBeGreaterThan(0);
      expect(score).toBeLessThanOrEqual(1);
    });

    test('should give higher score to recently accessed', () => {
      const fresh = multiFactorDecay({
        importance: 1.0,
        daysSinceCreation: 30,
        daysSinceAccess: 1,
        accessCount: 1,
      });

      const stale = multiFactorDecay({
        importance: 1.0,
        daysSinceCreation: 30,
        daysSinceAccess: 30,
        accessCount: 1,
      });

      expect(fresh).toBeGreaterThan(stale);
    });

    test('should give higher score to frequently accessed', () => {
      const popular = multiFactorDecay({
        importance: 1.0,
        daysSinceCreation: 30,
        daysSinceAccess: 10,
        accessCount: 100,
      });

      const unpopular = multiFactorDecay({
        importance: 1.0,
        daysSinceCreation: 30,
        daysSinceAccess: 10,
        accessCount: 1,
      });

      expect(popular).toBeGreaterThan(unpopular);
    });
  });
});
