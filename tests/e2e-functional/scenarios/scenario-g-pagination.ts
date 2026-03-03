/**
 * Scenario G: Subgraph Pagination Stress Test (10 turns + 500 pre-seeded facts)
 *
 * Validates:
 * - A4: Cursor-based pagination activates when a batch returns exactly 1000
 *   results (PAGE_SIZE limit)
 * - Pagination fires only on saturated batches (common terms), not on rare terms
 *
 * Before running turns, the test runner should ingest 500 facts using the E2E
 * benchmark ingestion pipeline (reusing code from subgraph/tests/e2e-ombh-validation.ts).
 * The `preSeedCount` field signals this requirement.
 *
 * Turns 1-5 target common search terms that should produce enough blind index
 * matches to trigger PaginateBlindIndex queries.
 * Turns 6-10 target rare/unique terms that should NOT trigger pagination.
 *
 * Only runs against subgraph instances (C and D).
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 3.7)
 */

import type { ConversationScenario, Turn } from '../types.js';

const turns: Turn[] = [
  // ─── Turns 1-5: Common-term queries (may saturate and trigger pagination) ───

  {
    index: 0,
    userMessage:
      'What did I learn about cooking? Tell me all the recipes, techniques, and food preparation tips I have mentioned.',
  },
  {
    index: 1,
    userMessage:
      'Tell me about all my work projects and professional tasks. Include anything related to my job, career, or professional development.',
  },
  {
    index: 2,
    userMessage:
      'What have I mentioned about travel and vacations? List all the places, trips, and destinations I have discussed.',
  },
  {
    index: 3,
    userMessage:
      'Recall everything I have said about programming, software development, and technology. Include tools, languages, and frameworks.',
  },
  {
    index: 4,
    userMessage:
      'What do I know about health, fitness, exercise, and wellness? Include any routines, goals, or medical information.',
  },

  // ─── Turns 6-10: Rare-term queries (should NOT trigger pagination) ───

  {
    index: 5,
    userMessage:
      'What did I say about my bearded dragon named Ziggy? Any details about his care or age?',
  },
  {
    index: 6,
    userMessage:
      'Do you remember the details about my Breville Barista Express espresso machine? How much did I pay for it?',
  },
  {
    index: 7,
    userMessage:
      'What was the name of the veterinary clinic where Pixel has her next checkup scheduled?',
  },
  {
    index: 8,
    userMessage:
      'Tell me about the Fushimi Inari shrine visit I mentioned. What time of day did I go and why?',
  },
  {
    index: 9,
    userMessage:
      'What did I say about the Schuylkill Navy sailing courses? When do they start?',
  },
];

export const scenarioG: ConversationScenario & { preSeedCount: number } = {
  id: 'G',
  name: 'Pagination Stress Test',
  description:
    'Forces A4 (cursor-based pagination) to activate by pre-loading 500 facts ' +
    'so that common-term queries saturate the PAGE_SIZE (1000) limit. ' +
    'Turns 1-5 use broad, common-term queries (cooking, work, travel, programming, health) ' +
    'that should trigger PaginateBlindIndex queries in the GraphQL captures. ' +
    'Turns 6-10 use rare, specific queries (Ziggy the bearded dragon, Breville espresso machine, ' +
    'Society Hill vet, Fushimi Inari, Schuylkill Navy) that should NOT trigger pagination. ' +
    'Only runs against subgraph instances.',
  pluginPath: '../../skill/plugin/index.js',
  turns,
  triggerCompaction: false,
  preSeedCount: 500,
};
