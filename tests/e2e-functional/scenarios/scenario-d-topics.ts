/**
 * Scenario D: Topic Shifts (30 turns)
 *
 * Tests cache invalidation on topic change and diversity in results when
 * memories span multiple topics.
 *
 * Four phases:
 *   Phase 1 (turns 1-8):   Cooking -- Italian food, pasta techniques, knife skills
 *   Phase 2 (turns 9-16):  Travel -- Japan trip, flights, Kyoto temples
 *   Phase 3 (turns 17-22): Fitness -- marathon training, running schedule, nutrition
 *   Phase 4 (turns 23-30): Cross-topic recall and mixed questions
 *
 * Validates:
 *   - C2: Cache invalidation on topic shift (turns 9, 17 should be cache misses)
 *   - C2: Cache hits within same topic (turns 6-8 within cooking phase)
 *   - B3: MMR cross-topic diversity ("What are all my hobbies?" pulls from all topics)
 *   - C3: Extraction throttle (fires every 5 turns)
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md section 3.4
 */

import type { ConversationScenario } from '../types.js';

const scenarioD: ConversationScenario = {
  id: 'scenario-d-topics',
  name: 'Topic Shifts',
  description:
    'Multi-topic conversation testing cache invalidation on topic shift (C2), within-topic cache hits, and cross-topic MMR diversity (B3) across 30 turns.',
  pluginPath: '../../skill/plugin/index.js',
  triggerCompaction: false,
  turns: [
    // ===================================================================
    // PHASE 1: Cooking (turns 1-8)
    // ===================================================================
    {
      index: 0,
      userMessage:
        "I've been getting really into Italian cooking lately. Made fresh pasta from scratch for the first time last weekend -- just flour and eggs, no machine.",
      assistantResponse:
        'Fresh pasta is so rewarding to make by hand. What kind of pasta did you make?',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: { text: "I've been getting into Italian cooking, made fresh pasta from scratch and served it with cacio e pepe" },
        },
      ],
    },
    {
      index: 1,
      userMessage:
        "Tagliatelle! Rolled it out by hand with a rolling pin. My nonna would be proud. I served it with a simple cacio e pepe -- just pecorino, black pepper, and pasta water.",
      assistantResponse:
        'Cacio e pepe is one of those dishes that is deceptively simple. Getting the emulsification right is the real challenge.',
    },
    {
      index: 2,
      userMessage:
        "Exactly. I've been practicing my knife skills too -- learned the proper rocking motion for mincing garlic and how to chiffonade basil. Mise en place has changed my whole approach.",
      assistantResponse:
        'Good knife technique makes everything faster and more enjoyable. Mise en place is a game changer once you commit to it.',
    },
    {
      index: 3,
      userMessage:
        "Next I want to try making gnocchi. I've read that you need to use starchy potatoes and not overwork the dough or they get gummy.",
      assistantResponse:
        'Russet potatoes work best for gnocchi. Light handling is key -- you want pillowy, not dense.',
    },
    {
      index: 4,
      userMessage:
        "I'm also experimenting with different sauces. I made a bolognese that simmered for four hours last Sunday. The depth of flavor was incredible compared to a quick sauce.",
      assistantResponse:
        'A proper slow-cooked bolognese is a labor of love. Four hours is about right for the flavors to really develop.',
    },
    // --- Turns 6-8: Same cooking topic (C2: cache hits expected) ---
    {
      index: 5,
      userMessage:
        "What's the best way to store fresh pasta if I make a big batch? I don't want it sticking together.",
      assistantResponse:
        'Dust it generously with semolina flour, form it into nests, and either cook within a few hours or freeze on a sheet pan first.',
    },
    {
      index: 6,
      userMessage:
        'How about drying fresh pasta? Is it worth investing in a pasta drying rack?',
      assistantResponse:
        'A drying rack is nice but not essential. You can drape the pasta over a clean broomstick or the back of a chair for an hour or two.',
    },
    {
      index: 7,
      userMessage:
        'One more pasta question -- should I salt the pasta water before or after it boils?',
      assistantResponse:
        'Add salt after the water comes to a rolling boil. You want it salty like the sea.',
    },

    // ===================================================================
    // PHASE 2: Travel -- Japan (turns 9-16)
    // Topic shift at turn 9 -- C2 cache miss expected
    // ===================================================================
    {
      index: 8,
      userMessage:
        "Switching gears completely -- I'm planning a trip to Japan in November. Two weeks, flying into Tokyo and making my way down to Kyoto and Osaka.",
      assistantResponse:
        'November is a beautiful time for Japan. The autumn foliage in Kyoto is spectacular. Two weeks gives you a great pace.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: { text: 'Planning a two-week trip to Japan in November, flying into Tokyo and visiting Kyoto and Osaka' },
        },
      ],
    },
    {
      index: 9,
      userMessage:
        "I'm looking at flights right now. Thinking of booking a direct flight from Portland to Tokyo Narita on ANA. Heard they have amazing service.",
      assistantResponse:
        'ANA is consistently rated one of the best airlines. The direct PDX to NRT route is convenient too.',
    },
    {
      index: 10,
      userMessage:
        "For Kyoto, I really want to visit Fushimi Inari with the thousand torii gates. And Kinkaku-ji -- the golden temple. Those are at the top of my list.",
      assistantResponse:
        'Fushimi Inari is incredible, especially if you go early morning to beat the crowds. Kinkaku-ji is stunning when the light hits the gold leaf.',
    },
    {
      index: 11,
      userMessage:
        "I'm also thinking about getting a JR Pass for the bullet trains between cities. Seems like a great deal for the Tokyo-Kyoto-Osaka triangle.",
      assistantResponse:
        'The JR Pass is excellent value if you are making multiple long-distance trips. The Shinkansen from Tokyo to Kyoto takes about two hours.',
    },
    {
      index: 12,
      userMessage:
        'Food-wise, I want to try authentic ramen in Tokyo, street food in Osaka, and a traditional kaiseki dinner in Kyoto. Any neighborhood recommendations?',
      assistantResponse:
        'For ramen, try Shinjuku or Ikebukuro. Dotonbori in Osaka is street food paradise. For kaiseki, Gion in Kyoto has incredible options.',
    },
    {
      index: 13,
      userMessage:
        "I should also learn some basic Japanese phrases before I go. At least greetings, thank you, and how to ask for directions.",
      assistantResponse:
        'Even basic phrases go a long way. Sumimasen, arigatou gozaimasu, and eigo wa hanasemasu ka will cover most situations.',
    },
    {
      index: 14,
      userMessage:
        "What about accommodation? I'm torn between traditional ryokans and modern hotels. Maybe a mix of both?",
      assistantResponse:
        'A mix is the best approach. Do a ryokan for at least two nights in Kyoto for the full experience -- onsen, futon, and multi-course breakfast.',
    },
    {
      index: 15,
      userMessage:
        "Good idea. I'll book a ryokan in Kyoto and hotels in Tokyo and Osaka. This trip is going to be amazing.",
      assistantResponse:
        'It sounds like a fantastic itinerary. Two weeks is the perfect length for that route.',
    },

    // ===================================================================
    // PHASE 3: Fitness -- Marathon training (turns 17-22)
    // Topic shift at turn 17 -- C2 cache miss expected
    // ===================================================================
    {
      index: 16,
      userMessage:
        "Oh, totally different topic -- I signed up for the Portland Marathon in October! It's my first full marathon. I've done a few halfs before.",
      assistantResponse:
        'Congratulations on signing up! Going from half to full marathon is a big step. When did you start training?',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: { text: 'Signed up for the Portland Marathon in October, first full marathon, have done half marathons before' },
        },
      ],
    },
    {
      index: 17,
      userMessage:
        "Just started a 16-week training plan. Right now I'm doing about 30 miles a week with a long run on Saturdays. Building up gradually to avoid injury.",
      assistantResponse:
        'That is a solid base. Gradual mileage increases are the way to go -- the ten percent rule is a good guideline.',
    },
    {
      index: 18,
      userMessage:
        "My schedule is: easy runs Monday, Wednesday, Friday. Tempo run on Tuesday. Rest or cross-train Thursday. Long run Saturday. Full rest Sunday.",
      assistantResponse:
        'That is a well-balanced schedule. Having dedicated easy days and rest days is important for recovery.',
    },
    {
      index: 19,
      userMessage:
        "Nutrition is the part I'm still figuring out. I know I need to carb-load before long runs and take gels during, but the timing is tricky.",
      assistantResponse:
        'Try taking a gel every 45 minutes during long runs. For carb loading, start increasing intake two days before rather than just the night before.',
    },
    {
      index: 20,
      userMessage:
        "I've been aiming for a 4-hour finish time. My half marathon PR is 1:48, so sub-4 should be doable if I stay consistent.",
      assistantResponse:
        'With a 1:48 half PR, sub-4 is very realistic. That would be about a 9:09 per mile pace for the full.',
    },
    {
      index: 21,
      userMessage:
        "I'm also doing strength training twice a week -- squats, lunges, and core work. Heard it really helps with injury prevention for runners.",
      assistantResponse:
        'Strength training is huge for runners. Strong glutes and core make a noticeable difference in late-race form.',
    },

    // ===================================================================
    // PHASE 4: Cross-topic recall (turns 23-30)
    // ===================================================================
    {
      index: 22,
      userMessage:
        'So between cooking, travel planning, and marathon training, I have a lot going on. What are all my hobbies and interests based on what we have discussed?',
      assistantResponse:
        'From our conversation, you are into Italian cooking and pasta making, planning a Japan trip in November, and training for the Portland Marathon. You also hike the Columbia River Gorge and play guitar.',
    },
    {
      index: 23,
      userMessage:
        'What food-related things have I talked about? Both the cooking and any restaurants or eating preferences.',
      assistantResponse:
        'You have been making fresh pasta, cacio e pepe, bolognese, and want to try gnocchi. You also want to try ramen in Tokyo, street food in Osaka, and kaiseki in Kyoto.',
    },
    {
      index: 24,
      userMessage:
        'When is my Japan trip and what cities am I visiting?',
      assistantResponse:
        'Your Japan trip is in November for two weeks. You are flying into Tokyo, then heading to Kyoto and Osaka.',
    },
    {
      index: 25,
      userMessage:
        'What is my marathon training schedule like?',
      assistantResponse:
        'You run easy days Monday, Wednesday, Friday, a tempo run Tuesday, cross-train or rest Thursday, long run Saturday, and full rest Sunday. About 30 miles per week currently.',
    },
    {
      index: 26,
      userMessage:
        'Do any of my hobbies overlap? Like, does cooking help with marathon nutrition or does travel connect to fitness?',
      assistantResponse:
        'Your cooking skills could definitely help with marathon nutrition planning. And your Japan trip is in November, after the October marathon, so the timing works out well.',
    },
    {
      index: 27,
      userMessage:
        'What specific Italian dishes have I made or want to make?',
      assistantResponse:
        'You made fresh tagliatelle with cacio e pepe and a slow-cooked bolognese. You want to try making gnocchi next.',
    },
    {
      index: 28,
      userMessage:
        'What temples or landmarks am I planning to see in Japan?',
      assistantResponse:
        'Fushimi Inari with the thousand torii gates and Kinkaku-ji, the golden temple, are at the top of your Kyoto list.',
    },
    {
      index: 29,
      userMessage:
        "Alright, I think that covers everything. Thanks for helping me keep track of all this -- I've got a lot of plates spinning right now!",
      assistantResponse:
        'You are juggling a lot but it all sounds exciting. Good luck with the marathon, the Japan trip planning, and the pasta making!',
    },
  ],
};

export default scenarioD;
