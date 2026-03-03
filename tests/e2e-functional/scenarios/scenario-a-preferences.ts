/**
 * Scenario A: Personal Preferences (25 turns)
 *
 * Tests basic memory storage and retrieval across a realistic personal conversation.
 * Validates:
 *   - B1: Importance-weighted ranking (Stripe/job facts rank high)
 *   - B2: Relevance threshold gate (noise turns get no injection)
 *   - C2: Semantic cache (same-topic follow-ups hit cache)
 *   - C3: Extraction throttle (every 5 turns, not every turn)
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md section 3.1
 */

import type { ConversationScenario } from '../types.js';

const scenarioA: ConversationScenario = {
  id: 'scenario-a-preferences',
  name: 'Personal Preferences',
  description:
    'Personal details conversation testing extraction throttle (C3), relevance gate (B2), importance ranking (B1), and semantic cache (C2) across 25 turns.',
  pluginPath: '../../skill/plugin/index.js',
  triggerCompaction: false,
  turns: [
    // --- Turns 1-5: Seeding personal details (extraction fires at turn 5) ---
    {
      index: 0,
      userMessage:
        'Hi there! I just moved to Portland, Oregon last month. Still getting settled in but really loving the vibe so far.',
      assistantResponse:
        'Welcome to Portland! It is a great city. How are you finding the adjustment so far?',
    },
    {
      index: 1,
      userMessage:
        "Yeah, I'm loving it here. The food scene is incredible -- I've become obsessed with Thai food, especially pad see ew. There's this little place on Division Street that makes the best I've ever had.",
      assistantResponse:
        'Portland has an amazing Thai food scene. Division Street has a ton of great spots.',
    },
    {
      index: 2,
      userMessage:
        "For work, I'm a senior backend engineer at Stripe. I mainly work with Go and PostgreSQL -- we run a pretty standard microservices stack.",
      assistantResponse:
        'Nice, Stripe is a great company. Go and PostgreSQL are a solid combination for backend work.',
    },
    {
      index: 3,
      userMessage:
        "My work schedule is pretty flexible -- I usually start at 10am and wrap up around 6pm Pacific. One of the perks of remote work, honestly.",
      assistantResponse:
        'That is a nice schedule. The flexibility of remote work makes a big difference.',
    },
    {
      index: 4,
      userMessage:
        "On weekends I like hiking in the Columbia River Gorge. Eagle Creek Trail is my favorite -- the views are unreal, especially in the fall.",
      assistantResponse:
        'Eagle Creek Trail is stunning. The Columbia River Gorge is one of the best parts of living in the Pacific Northwest.',
    },

    // --- Turn 6: Additional fact (guitar), post first extraction ---
    {
      index: 5,
      userMessage:
        'I also play guitar -- mostly fingerstyle acoustic. Been working on some Tommy Emmanuel arrangements lately.',
      assistantResponse:
        'Tommy Emmanuel is incredible. Fingerstyle acoustic is a great discipline to develop.',
    },

    // --- Turns 7-8: Recall questions (should inject relevant memories) ---
    {
      index: 6,
      userMessage: 'Do you remember where I work?',
      assistantResponse:
        'You mentioned you work at Stripe as a senior backend engineer, using Go and PostgreSQL.',
    },
    {
      index: 7,
      userMessage: 'What kind of food do I like?',
      assistantResponse:
        'You said you love Thai food, especially pad see ew from a spot on Division Street in Portland.',
    },

    // --- Turns 9-10: Noise / filler (B2: should NOT inject) ---
    {
      index: 8,
      userMessage: 'ok thanks',
      assistantResponse: 'You are welcome!',
    },
    {
      index: 9,
      userMessage: 'great',
      assistantResponse: 'Glad I could help.',
    },

    // --- Turns 11-15: Same-topic follow-ups about Portland (C2: cache hits expected) ---
    {
      index: 10,
      userMessage:
        'What are some other good neighborhoods to explore in Portland?',
      assistantResponse:
        'Alberta Arts District, Hawthorne, and the Pearl District are all worth checking out.',
    },
    {
      index: 11,
      userMessage:
        "Any good Portland hiking trails besides Eagle Creek that you'd suggest?",
      assistantResponse:
        'Multnomah Falls, Angels Rest, and the Wildwood Trail in Forest Park are all fantastic options near Portland.',
    },
    {
      index: 12,
      userMessage:
        'How about Portland coffee shops? I need a good workspace for remote days.',
      assistantResponse:
        'Heart Coffee, Coava, and Sterling are popular spots with good wifi and work-friendly vibes.',
    },
    {
      index: 13,
      userMessage:
        "I keep hearing about Portland's food cart scene. What's the deal with those?",
      assistantResponse:
        'Portland has massive food cart pods all over the city. They are a huge part of the food culture here.',
    },
    {
      index: 14,
      userMessage:
        "Is the Portland weather really as rainy as people say? I'm still adjusting.",
      assistantResponse:
        'The rain is real but it is mostly drizzle from October through May. Summers are gorgeous though.',
    },

    // --- Turn 16: Topic shift (C2: cache miss expected) ---
    {
      index: 15,
      userMessage:
        "Actually, I want to switch topics. What programming languages should I learn next? I've been curious about Rust.",
      assistantResponse:
        'Given your Go background, Rust would be a natural progression. It shares some concurrency patterns but adds a strong ownership model.',
    },

    // --- Turn 17: Explicit tool call to remember shellfish allergy ---
    {
      index: 16,
      userMessage:
        "Remember that I'm allergic to shellfish -- this is really important for restaurant recommendations.",
      assistantResponse:
        'Got it, I have noted your shellfish allergy. I will keep that in mind for any food recommendations.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: {
            text: 'User is allergic to shellfish. This is critical for restaurant and food recommendations.',
            importance: 9,
          },
        },
      ],
    },

    // --- Turns 18-20: Recall questions (quality tests) ---
    {
      index: 17,
      userMessage: 'What are my dietary restrictions?',
      assistantResponse:
        'You mentioned that you are allergic to shellfish, which is important for restaurant recommendations.',
    },
    {
      index: 18,
      userMessage:
        'Where do I like to eat? I want to try somewhere new this weekend.',
      assistantResponse:
        'You love Thai food, especially pad see ew. There is a great spot on Division Street you mentioned. Just remember your shellfish allergy when ordering.',
    },
    {
      index: 19,
      userMessage: "What's my work schedule again? I'm trying to plan a dentist appointment.",
      assistantResponse:
        'You typically work from 10am to 6pm Pacific time, so mornings before 10 would be ideal for appointments.',
    },

    // --- Turns 21-25: Wind-down conversation ---
    {
      index: 20,
      userMessage:
        "Thanks for all that. I think I'm going to head out for a hike this afternoon actually.",
      assistantResponse:
        'Sounds like a great plan. Enjoy the Gorge!',
    },
    {
      index: 21,
      userMessage:
        "Yeah, might try Oneonta Gorge this time. I've heard the tunnel of ferns is something else.",
      assistantResponse:
        'Oneonta Gorge is beautiful. Bring waterproof shoes -- you wade through the creek to get to the falls.',
    },
    {
      index: 22,
      userMessage:
        "Good call. I'll pack my trail runners. Might grab some Thai takeout on the way back.",
      assistantResponse:
        'Solid plan. Post-hike pad see ew sounds like the perfect reward.',
    },
    {
      index: 23,
      userMessage: "Ha, exactly. Alright, I'm heading out. Talk later!",
      assistantResponse: 'Have a great hike! Talk soon.',
    },
    {
      index: 24,
      userMessage: 'See ya!',
      assistantResponse: 'Bye!',
    },
  ],
};

export default scenarioA;
