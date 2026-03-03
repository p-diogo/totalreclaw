/**
 * Scenario E: Long Conversation / Extraction Throttle (55 turns)
 *
 * Validates C3 (extraction fires every 5 turns, not every turn) over a long
 * conversation, and tests compaction hook behavior.
 *
 * Phase 1 (turns 1-25): Daily routine, meal plans, exercise, work projects.
 * Phase 2 (turns 26-50): Vacation stories, books read, movies watched.
 * Phase 3 (turns 51-55): Wind-down conversation + compaction trigger.
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md (section 3.5)
 */

import type { ConversationScenario, Turn } from '../types.js';

const turns: Turn[] = [
  // ─── Phase 1: Daily Routine, Meal Plans, Exercise, Work (turns 1-25) ───

  {
    index: 0,
    userMessage:
      'I usually wake up at 6:30am and make pour-over coffee with beans from Onyx Coffee Lab. It\'s become my morning ritual.',
  },
  {
    index: 1,
    userMessage:
      'For breakfast I alternate between overnight oats with blueberries and chia seeds, and avocado toast on sourdough from the bakery down the street.',
  },
  {
    index: 2,
    userMessage:
      'My main project at work right now is migrating our monolith to microservices. We\'re using Go for the new services and keeping the Python Django legacy app running in parallel.',
  },
  {
    index: 3,
    userMessage:
      'I try to work out every morning before work. Monday, Wednesday, Friday I do strength training at the gym -- mostly compound lifts like squats, deadlifts, and bench press.',
  },
  {
    index: 4,
    userMessage:
      'Tuesday and Thursday I go for a 5K run along the river trail near my apartment. My current best time is 24 minutes flat.',
  },
  {
    index: 5,
    userMessage:
      'For lunch I usually meal prep on Sundays. This week it\'s chicken tikka masala with basmati rice. I make a big batch that lasts all week.',
  },
  {
    index: 6,
    userMessage:
      'My team at work has four engineers plus me as the tech lead. We do standups at 9:15am every day and sprint planning on Monday afternoons.',
  },
  {
    index: 7,
    userMessage:
      'I\'ve been learning Rust on the side, mostly through Exercism and reading "Programming Rust" by Blandy and Orendorff. I\'m about halfway through the book.',
  },
  {
    index: 8,
    userMessage:
      'Dinner is usually the meal where I experiment. Last night I made Thai green curry with tofu and Japanese eggplant. I use Mae Ploy curry paste as a base.',
  },
  {
    index: 9,
    userMessage:
      'On Saturdays I go to the farmers market at Pioneer Square. I always get the honey crisp apples from the orchard stand and fresh sourdough from Tabor Bread.',
  },
  {
    index: 10,
    userMessage:
      'I\'ve been tracking my macros for the past three months. I aim for about 180g protein, 250g carbs, and 70g fat per day. It\'s been helping with my strength gains.',
  },
  {
    index: 11,
    userMessage:
      'At work we just adopted Kubernetes for our deployment pipeline. I spent all last week writing Helm charts and setting up ArgoCD for GitOps-style continuous deployment.',
  },
  {
    index: 12,
    userMessage:
      'I take a 20-minute nap after lunch almost every day. I read a study that said it improves afternoon productivity by 30%. I set my alarm for 1:15pm.',
  },
  {
    index: 13,
    userMessage:
      'My apartment is a two-bedroom in the Pearl District. I use the second bedroom as a home office. My desk setup is a standing desk from Uplift with an LG 34-inch ultrawide monitor.',
  },
  {
    index: 14,
    userMessage:
      'I\'ve been doing yoga on Sunday mornings at a studio called Yoga Union. The 9am vinyasa flow class with instructor Maya is my favorite.',
  },
  {
    index: 15,
    userMessage:
      'For snacks I keep almonds, dark chocolate (85% cacao from Theo Chocolate), and protein bars at my desk. I try to avoid snacking after 8pm.',
  },
  {
    index: 16,
    userMessage:
      'Our codebase at work has about 400,000 lines of Python. The biggest challenge with the migration is the 200+ Django models that share a single PostgreSQL database.',
  },
  {
    index: 17,
    userMessage:
      'I drink about 3 liters of water a day. I have a Hydro Flask that I refill four times. I also drink green tea in the afternoon instead of more coffee.',
  },
  {
    index: 18,
    userMessage:
      'Wednesday evenings I play basketball at the community center with a group of coworkers. We\'ve been doing it for about a year now -- usually 5v5 pickup games.',
  },
  {
    index: 19,
    userMessage:
      'I\'m trying to eat more fish. I\'ve been making baked salmon with lemon and dill twice a week. I get the salmon from the seafood counter at New Seasons Market.',
  },
  {
    index: 20,
    userMessage:
      'My manager Sarah wants us to hit the microservices milestone by end of Q2. We\'re about 40% done with extracting the payment service, which is the most complex piece.',
  },
  {
    index: 21,
    userMessage:
      'I started doing cold showers in the morning after reading about the health benefits. Just the last 60 seconds of my shower. It\'s brutal but I feel more alert.',
  },
  {
    index: 22,
    userMessage:
      'For dinner tonight I\'m making pasta aglio e olio with roasted cherry tomatoes. It\'s one of those 20-minute meals that tastes way better than the effort involved.',
  },
  {
    index: 23,
    userMessage:
      'I keep a bullet journal for tracking habits and tasks. I\'ve been doing it for two years now. I review my weekly goals every Sunday evening.',
  },
  {
    index: 24,
    userMessage:
      'My sleep schedule is pretty consistent -- I\'m in bed by 10:30pm and asleep by 11pm. I use a sleep mask and keep the bedroom at 67 degrees Fahrenheit.',
  },

  // ─── Phase 2: Vacations, Books, Movies (turns 26-50) ───

  {
    index: 25,
    userMessage:
      'Last month I went to Costa Rica for ten days. The Arenal volcano hike was incredible -- we hiked the 1968 lava flow trail and could see the summit through the clouds.',
  },
  {
    index: 26,
    userMessage:
      'In Costa Rica we also went zip-lining through the cloud forest in Monteverde. There were 13 cables, the longest one was over 750 meters. My partner was terrified but loved it.',
  },
  {
    index: 27,
    userMessage:
      'I just finished reading "Project Hail Mary" by Andy Weir. The friendship between Ryland Grace and Rocky is one of the best character dynamics I\'ve ever read. Gave it 5 stars.',
  },
  {
    index: 28,
    userMessage:
      'Before Costa Rica I read "Atomic Habits" by James Clear. That\'s actually what inspired my habit tracking in the bullet journal. The chapter on habit stacking changed my routine.',
  },
  {
    index: 29,
    userMessage:
      'We watched "Dune: Part Two" last weekend. Denis Villeneuve is a genius -- the sandworm riding scene was even better than I imagined from the book. Probably my favorite sci-fi film now.',
  },
  {
    index: 30,
    userMessage:
      'Two years ago I did a solo trip to Japan for three weeks. Spent time in Tokyo, Kyoto, and Osaka. The ramen in Osaka at Ichiran was the best I\'ve ever had.',
  },
  {
    index: 31,
    userMessage:
      'I\'m currently reading "The Pragmatic Programmer" for the second time. It holds up really well. The section on DRY principle is especially relevant to our microservices work.',
  },
  {
    index: 32,
    userMessage:
      'In Kyoto I visited Fushimi Inari at sunrise to avoid crowds. Walked through thousands of orange torii gates for about two hours. It was completely surreal and peaceful.',
  },
  {
    index: 33,
    userMessage:
      'I\'ve been watching "Shogun" on FX -- the 2024 version. James Clavell\'s world-building is incredible, and the production quality is on par with anything I\'ve seen.',
  },
  {
    index: 34,
    userMessage:
      'For our anniversary next month we\'re planning a trip to Sedona, Arizona. I want to do the Devil\'s Bridge hike and visit some of the wineries in the Verde Valley.',
  },
  {
    index: 35,
    userMessage:
      'One of my favorite books from last year was "Tomorrow, and Tomorrow, and Tomorrow" by Gabrielle Zevin. It\'s about game design and friendship -- really resonated with me as a developer.',
  },
  {
    index: 36,
    userMessage:
      'We binge-watched all of "The Bear" over two weekends. It made me want to cook more ambitiously. I even tried making the braciole from season 2 -- turned out pretty good.',
  },
  {
    index: 37,
    userMessage:
      'My bucket list trip is New Zealand. I want to do the Milford Track -- it\'s a 4-day guided walk through Fiordland National Park. You have to book it months in advance.',
  },
  {
    index: 38,
    userMessage:
      'I watched "Oppenheimer" in IMAX 70mm. The Trinity test sequence was the most intense cinema experience I\'ve ever had. Christopher Nolan really outdid himself.',
  },
  {
    index: 39,
    userMessage:
      'During the Costa Rica trip we also spent two days at a beach town called Santa Teresa. I tried surfing for the first time -- stood up on the board on my fourth attempt.',
  },
  {
    index: 40,
    userMessage:
      'I\'m listening to "Sapiens" by Yuval Noah Harari on audiobook during my runs. The narrator is excellent and the chapter on the agricultural revolution is mind-blowing.',
  },
  {
    index: 41,
    userMessage:
      'Last summer we did a road trip along the Oregon coast. Cannon Beach was beautiful but my favorite spot was Cape Perpetua -- the Thor\'s Well at high tide is mesmerizing.',
  },
  {
    index: 42,
    userMessage:
      'I rewatched "Arrival" last week -- it\'s still my all-time favorite sci-fi movie. The nonlinear time perception concept is so beautifully executed. Amy Adams was robbed of the Oscar.',
  },
  {
    index: 43,
    userMessage:
      'I\'m about to start "System Design Interview" by Alex Xu. My coworker recommended it for preparing for our architecture review of the microservices migration.',
  },
  {
    index: 44,
    userMessage:
      'We went to a food and wine festival in Willamette Valley last October. Discovered an amazing Pinot Noir from Domaine Drouhin. I bought a case and we\'re slowly working through it.',
  },
  {
    index: 45,
    userMessage:
      'I saw "Past Lives" in theaters -- such a quiet, beautiful film about connection and what-ifs. Greta Lee was phenomenal. It lingered with me for days.',
  },
  {
    index: 46,
    userMessage:
      'My partner and I are planning our first camping trip to Crater Lake in August. We\'re renting a campsite at Mazama Village and plan to hike the Garfield Peak trail.',
  },
  {
    index: 47,
    userMessage:
      'Just finished "Designing Data-Intensive Applications" by Martin Kleppmann. It\'s now my go-to reference for distributed systems. The chapter on consensus algorithms was especially dense.',
  },
  {
    index: 48,
    userMessage:
      'We watched every episode of "Severance" in three nights. The concept of work-life separation taken literally is such a clever premise. Can\'t wait for season 2.',
  },
  {
    index: 49,
    userMessage:
      'I want to visit Iceland next winter to see the northern lights. Planning a trip around late February or early March when there\'s still enough darkness but temperatures aren\'t the absolute worst.',
  },

  // ─── Phase 3: Wind-down (turns 51-55) ───

  {
    index: 50,
    userMessage:
      'Thanks for chatting with me about all this. It\'s nice to have a record of everything -- my routines, trips, and things I\'ve been reading and watching.',
  },
  {
    index: 51,
    userMessage:
      'Do you remember what my morning routine looks like? Like the coffee and exercise parts?',
  },
  {
    index: 52,
    userMessage:
      'What about the books I\'ve read recently -- can you list them?',
  },
  {
    index: 53,
    userMessage:
      'And what trips do I have planned coming up?',
  },
  {
    index: 54,
    userMessage:
      'Perfect, thanks for keeping track of all that. I think that covers everything for now.',
  },
];

export const scenarioE: ConversationScenario = {
  id: 'E',
  name: 'Long Conversation / Extraction Throttle',
  description:
    'Validates C3 (extraction fires every 5 turns) over a 55-turn conversation ' +
    'with rich factual content across daily routines, travel, books, and movies. ' +
    'Also tests compaction hook behavior at conversation end.',
  pluginPath: '../../skill/plugin/index.js',
  turns,
  triggerCompaction: true,
};
