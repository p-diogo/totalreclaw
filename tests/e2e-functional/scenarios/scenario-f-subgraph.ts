/**
 * Scenario F: Subgraph-Specific Improvements (20 turns)
 *
 * Validates:
 * - A2: Parallel batches (TRAPDOOR_BATCH_SIZE=5)
 * - A3: Ordering (orderBy: id, orderDirection: desc)
 * - A4: Cursor-based pagination (unlikely with only 50 facts; see Scenario G)
 *
 * Turns 1-10 seed 50 facts (5 per turn) via totalreclaw_remember across
 * diverse topics: work, hobbies, preferences, travel, food, pets, health,
 * goals, decisions, events.
 * Turns 11-20 issue recall queries to test batch behavior and ordering.
 *
 * Only runs against subgraph instances (C and D).
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 3.6)
 */

import type { ConversationScenario, Turn } from '../types.js';

const turns: Turn[] = [
  // ─── Turns 1-10: Seed 50 facts (5 per turn) ───

  // Turn 1: Work facts
  {
    index: 0,
    userMessage: 'Let me share some important details about my work life.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I work as a senior data engineer at Datadog, building real-time observability pipelines',
          importance: 8,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My team uses Apache Kafka and Apache Flink for stream processing at work',
          importance: 7,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I report to my manager Rachel Kim who joined Datadog from Google in 2024',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My work hours are 9am to 5:30pm Eastern time, fully remote from Philadelphia',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I am interviewing for a staff engineer promotion in Q2 2026',
          importance: 8,
        },
      },
    ],
  },

  // Turn 2: Hobbies
  {
    index: 1,
    userMessage: 'Here are some things about my hobbies.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I play indoor volleyball every Tuesday evening at a recreational league in Center City Philadelphia',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I am learning watercolor painting and attend a class at Fleisher Art Memorial every Saturday morning',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I collect vintage vinyl records, mostly jazz from the 1960s and progressive rock from the 1970s',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I built a custom mechanical keyboard with Cherry MX Brown switches and SA profile keycaps',
          importance: 4,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I am training for a century ride — a 100-mile bicycle ride — scheduled for September 2026',
          importance: 7,
        },
      },
    ],
  },

  // Turn 3: Preferences and dietary
  {
    index: 2,
    userMessage: 'Some dietary preferences and food info to store.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I have been vegetarian for 8 years, since 2018',
          importance: 8,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My favorite cuisine is Ethiopian — I love injera with misir wot from Abyssinia restaurant in Philadelphia',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I am allergic to tree nuts, especially walnuts and cashews — this is medically serious',
          importance: 9,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'For dinner I usually cook tofu stir-fry with vegetables, dal with naan bread, or mushroom risotto',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I drink oat milk in my coffee — Oatly Barista Edition is my preferred brand',
          importance: 4,
        },
      },
    ],
  },

  // Turn 4: Travel
  {
    index: 3,
    userMessage: 'Storing some travel memories.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I spent two weeks in Portugal last summer visiting Lisbon, Porto, and the Algarve coast',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My favorite city I have ever visited is Kyoto, Japan — the bamboo grove in Arashiyama was unforgettable',
          importance: 7,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I backpacked through Southeast Asia for a month after college — Thailand, Vietnam, and Cambodia',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My next planned trip is Iceland in January 2027 to see the Northern Lights',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I have a Global Entry membership that expires in March 2028',
          importance: 4,
        },
      },
    ],
  },

  // Turn 5: Pets
  {
    index: 4,
    userMessage: 'Info about my pets and family.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I have a tabby cat named Pixel who is 6 years old, adopted from the SPCA in 2020',
          importance: 7,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I also have a bearded dragon named Ziggy who is 3 years old',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My partner Sam is a physical therapist at Penn Medicine',
          importance: 7,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My parents live in Cherry Hill, New Jersey — about 20 minutes from my apartment',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My younger sister Mia is studying biomedical engineering at Johns Hopkins University',
          importance: 6,
        },
      },
    ],
  },

  // Turn 6: Health
  {
    index: 5,
    userMessage: 'Some health and fitness details to remember.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I take vitamin D and B12 supplements daily because of my vegetarian diet',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I had LASIK eye surgery in 2023 and no longer need glasses or contacts',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My dentist appointment is every 6 months at Penn Dental Medicine — next one is April 2026',
          importance: 3,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I meditate for 10 minutes every morning using the Waking Up app by Sam Harris',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I sleep 7 to 8 hours per night and track sleep quality with an Oura Ring Generation 3',
          importance: 4,
        },
      },
    ],
  },

  // Turn 7: Goals
  {
    index: 6,
    userMessage: 'Here are my goals and plans for this year.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I want to read 40 books this year — currently at 11 books as of early March',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I am saving for a down payment on a rowhome in the Fishtown neighborhood of Philadelphia',
          importance: 8,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I plan to get my AWS Solutions Architect Professional certification by June 2026',
          importance: 7,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'Sam and I are considering getting a dog — probably a whippet or a greyhound rescue',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I want to learn to sail this summer — the Schuylkill Navy has beginner courses in June',
          importance: 4,
        },
      },
    ],
  },

  // Turn 8: Decisions
  {
    index: 7,
    userMessage: 'Some recent decisions I have made.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I switched from iPhone to a Pixel 8 Pro last month because I prefer stock Android',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I cancelled my Netflix subscription and kept only Apple TV Plus and Criterion Channel',
          importance: 4,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I started using Obsidian instead of Notion for personal notes because of local-first storage',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I decided to switch to a credit union — Vio Bank — for better savings interest rates',
          importance: 4,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I committed to doing a no-buy month in April 2026 for all non-essential purchases',
          importance: 3,
        },
      },
    ],
  },

  // Turn 9: Events
  {
    index: 8,
    userMessage: 'Some important upcoming events to track.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'Sam and I are attending a wedding in Napa Valley on April 12, 2026',
          importance: 7,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My college reunion at Carnegie Mellon is in May 2026 — class of 2016, tenth anniversary',
          importance: 6,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I am presenting a talk on real-time feature stores at Data Council conference in June 2026',
          importance: 8,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'Pixel the cat has a vet checkup scheduled for March 15 at Society Hill Veterinary Hospital',
          importance: 4,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My apartment lease renews in August — current rent is $2,100 per month for a 2-bedroom in Rittenhouse Square',
          importance: 7,
        },
      },
    ],
  },

  // Turn 10: Mixed extras
  {
    index: 9,
    userMessage: 'Last batch of things to store.',
    toolCalls: [
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My favorite coffee shop in Philadelphia is Elixr Coffee Roasters on Sydenham Street',
          importance: 4,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I use a Breville Barista Express for espresso at home — purchased refurbished for $400',
          importance: 3,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My car is a 2021 Subaru Crosstrek in cool gray khaki, mainly used for weekend trips',
          importance: 5,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'I volunteer at Coded by Kids teaching Python to high school students on Saturday mornings',
          importance: 7,
        },
      },
      {
        name: 'totalreclaw_remember',
        params: {
          text: 'My preferred contact method is Signal and my phone number ends in 4827',
          importance: 6,
        },
      },
    ],
  },

  // ─── Turns 11-20: Recall queries ───

  // Turn 11: A2 test — parallel batches for food query
  {
    index: 10,
    userMessage: 'What do I like to eat for dinner?',
  },

  // Turn 12: A2+A3 test — parallel batches + ordering for work query
  {
    index: 11,
    userMessage: 'Tell me everything about my work.',
  },

  // Turn 13: A4 test — broad recall with tool call
  {
    index: 12,
    userMessage: 'Can you recall everything I\'ve told you?',
    toolCalls: [
      {
        name: 'totalreclaw_recall',
        params: { query: "everything I've told you" },
      },
    ],
  },

  // Turns 14-20: Targeted recall queries
  {
    index: 13,
    userMessage: 'What pets do I have? Tell me their names and details.',
  },
  {
    index: 14,
    userMessage: 'Where have I traveled and what trips am I planning?',
  },
  {
    index: 15,
    userMessage: 'What are my dietary restrictions and food allergies?',
  },
  {
    index: 16,
    userMessage: 'What hobbies and sports do I enjoy?',
  },
  {
    index: 17,
    userMessage: 'What are my major goals and plans for 2026?',
  },
  {
    index: 18,
    userMessage: 'What upcoming events do I have in the next few months?',
  },
  {
    index: 19,
    userMessage: 'What technology and gear do I use day to day?',
  },
];

export const scenarioF: ConversationScenario = {
  id: 'F',
  name: 'Subgraph-Specific Improvements',
  description:
    'Validates A2 (parallel batches), A3 (ordering), and A4 (cursor-based pagination) ' +
    'in the subgraph search path. Seeds 50 diverse facts via totalreclaw_remember ' +
    'across 10 turns (work, hobbies, dietary, travel, pets, health, goals, decisions, ' +
    'events, extras), then issues 10 recall queries to test batch behavior, result ' +
    'ordering, and recall quality. Only runs against subgraph instances.',
  pluginPath: '../../skill/plugin/index.js',
  turns,
  triggerCompaction: false,
};
