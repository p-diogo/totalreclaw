/**
 * Importance Decay Calculation
 *
 * Implements time-based decay for memory importance, accounting for
 * access frequency and recency.
 */

/** Default decay parameters */
const DEFAULT_DECAY_PARAMS = {
  /** Base decay rate per day (default: 0.1) */
  baseDecayRate: 0.1,
  /** Half-life in days (default: 30 days) */
  halfLifeDays: 30,
  /** Access boost factor (default: 0.1 boost per access) */
  accessBoostFactor: 0.1,
  /** Maximum access boost (default: 0.5 = 50% boost cap) */
  maxAccessBoost: 0.5,
  /** Minimum decay score (default: 0.01) */
  minDecayScore: 0.01,
};

/**
 * Decay parameters
 */
export interface DecayParams {
  baseDecayRate?: number;
  halfLifeDays?: number;
  accessBoostFactor?: number;
  maxAccessBoost?: number;
  minDecayScore?: number;
}

/**
 * Calculate the decay score for a memory
 *
 * The decay score represents how "fresh" a memory is, decreasing over time
 * but being boosted by access frequency.
 *
 * Formula:
 *   decay = importance * e^(-rate * days) * (1 + min(accessBoost * accessCount, maxBoost))
 *
 * @param importance - Initial importance (0-1)
 * @param daysSinceAccess - Days since last access
 * @param accessCount - Number of times this memory has been accessed
 * @param params - Optional decay parameters
 * @returns Decay score (0-1 range)
 */
export function calculateDecayScore(
  importance: number,
  daysSinceAccess: number,
  accessCount: number,
  params: DecayParams = {}
): number {
  const {
    baseDecayRate,
    accessBoostFactor,
    maxAccessBoost,
    minDecayScore,
  } = { ...DEFAULT_DECAY_PARAMS, ...params };

  // Clamp importance to valid range
  importance = Math.max(0, Math.min(1, importance));

  // Calculate time-based decay (exponential)
  const timeDecay = Math.exp(-baseDecayRate * daysSinceAccess);

  // Calculate access boost (capped)
  const accessBoost = Math.min(
    accessBoostFactor * accessCount,
    maxAccessBoost
  );

  // Combine factors
  let score = importance * timeDecay * (1 + accessBoost);

  // Apply minimum floor
  score = Math.max(minDecayScore, score);

  // Clamp to valid range
  return Math.max(0, Math.min(1, score));
}

/**
 * Calculate exponential decay with half-life
 *
 * Uses the formula: score = initial * (1/2)^(days / halfLife)
 *
 * @param initial - Initial score
 * @param days - Days elapsed
 * @param halfLife - Half-life in days
 * @returns Decayed score
 */
export function exponentialDecay(
  initial: number,
  days: number,
  halfLife: number = DEFAULT_DECAY_PARAMS.halfLifeDays
): number {
  return initial * Math.pow(0.5, days / halfLife);
}

/**
 * Calculate decay rate from half-life
 *
 * @param halfLife - Half-life in days
 * @returns Decay rate
 */
export function halfLifeToDecayRate(halfLife: number): number {
  return Math.log(2) / halfLife;
}

/**
 * Calculate days until score drops below threshold
 *
 * @param initialScore - Initial score
 * @param threshold - Target threshold
 * @param decayRate - Decay rate per day
 * @returns Number of days until threshold is reached
 */
export function daysUntilThreshold(
  initialScore: number,
  threshold: number,
  decayRate: number = DEFAULT_DECAY_PARAMS.baseDecayRate
): number {
  if (initialScore <= threshold) return 0;
  return Math.log(threshold / initialScore) / -decayRate;
}

/**
 * Boost decay score on access
 *
 * @param currentScore - Current decay score
 * @param boostAmount - Amount to boost (default: restore to 80% of original)
 * @returns Boosted decay score
 */
export function boostOnAccess(
  currentScore: number,
  boostAmount: number = 0.8
): number {
  // Access restores the score towards 1
  const restored = currentScore + (1 - currentScore) * boostAmount;
  return Math.min(1, restored);
}

/**
 * Multi-factor decay combining time, importance, and usage patterns
 *
 * @param params - Memory parameters
 * @returns Combined decay score
 */
export function multiFactorDecay(params: {
  importance: number;
  daysSinceCreation: number;
  daysSinceAccess: number;
  accessCount: number;
  userWeight?: number; // User-defined importance weight
  decayParams?: DecayParams;
}): number {
  const { decayParams = {} } = params;
  const { baseDecayRate, minDecayScore } = {
    ...DEFAULT_DECAY_PARAMS,
    ...decayParams,
  };

  // Factor 1: Base importance
  const importance = Math.max(0, Math.min(1, params.importance));

  // Factor 2: Age decay (slower than access decay)
  const ageDecay = Math.exp(-baseDecayRate * 0.5 * params.daysSinceCreation);

  // Factor 3: Access recency (faster decay)
  const accessRecency = Math.exp(-baseDecayRate * params.daysSinceAccess);

  // Factor 4: Access frequency boost
  const frequencyBoost = Math.log10(1 + params.accessCount) / 3; // Caps at ~0.33 for 1000 accesses

  // Factor 5: User weight (if provided)
  const userWeight = params.userWeight ?? 1.0;

  // Combine all factors
  const score =
    importance *
    ageDecay *
    accessRecency *
    (1 + frequencyBoost) *
    userWeight;

  return Math.max(minDecayScore, Math.min(1, score));
}

/**
 * Calculate effective decay for search ranking
 *
 * This combines the stored decay score with a query-time recency boost.
 *
 * @param storedDecayScore - Pre-computed decay score from storage
 * @param documentTimestamp - When the document was created
 * @param currentTime - Current time (default: now)
 * @param recencyBoostWeight - How much to boost recent items (0-1)
 * @returns Adjusted decay score for ranking
 */
export function searchTimeDecay(
  storedDecayScore: number,
  documentTimestamp: Date,
  currentTime: Date = new Date(),
  recencyBoostWeight: number = 0.2
): number {
  const daysSinceCreation =
    (currentTime.getTime() - documentTimestamp.getTime()) / (1000 * 60 * 60 * 24);

  // Recent items get a boost
  const recencyBoost =
    recencyBoostWeight * Math.exp(-0.1 * daysSinceCreation);

  return storedDecayScore * (1 + recencyBoost);
}

/**
 * Batch update decay scores for multiple memories
 *
 * @param memories - Array of memories with decay metadata
 * @param params - Decay parameters
 * @returns Updated decay scores
 */
export function batchUpdateDecayScores(
  memories: Array<{
    id: string;
    importance: number;
    lastAccessed: Date;
    accessCount: number;
  }>,
  params: DecayParams = {}
): Array<{ id: string; newDecayScore: number }> {
  const now = new Date();

  return memories.map((memory) => {
    const daysSinceAccess =
      (now.getTime() - memory.lastAccessed.getTime()) / (1000 * 60 * 60 * 24);

    const newDecayScore = calculateDecayScore(
      memory.importance,
      daysSinceAccess,
      memory.accessCount,
      params
    );

    return {
      id: memory.id,
      newDecayScore,
    };
  });
}
