/**
 * Scenario B: Technical Learning (20 turns)
 *
 * Tests cross-referencing of technical concepts, embedding-based semantic search,
 * and MMR diversity.
 * Validates:
 *   - B3: MMR diversity (memory safety query should return diverse concepts)
 *   - C1: Two-tier search (tool call uses full search path)
 *   - C3: Extraction throttle (fires at turns 5, 10, 15, 20)
 *   - Semantic recall (paraphrased queries still find relevant memories)
 *
 * See: docs/specs/totalreclaw/functional-e2e-test-plan.md section 3.2
 */

import type { ConversationScenario } from '../types.js';

const scenarioB: ConversationScenario = {
  id: 'scenario-b-technical',
  name: 'Technical Learning',
  description:
    'Technical Rust learning conversation testing MMR diversity (B3), two-tier search (C1), extraction throttle (C3), and semantic recall across 20 turns.',
  pluginPath: '../../skill/plugin/index.js',
  triggerCompaction: false,
  turns: [
    // --- Turns 1-5: Learning Rust concepts (extraction fires at turn 5) ---
    {
      index: 0,
      userMessage:
        "I've been diving into Rust this week. The ownership system is fascinating -- every value has exactly one owner, and when the owner goes out of scope, the value is dropped.",
      assistantResponse:
        'Ownership is the core concept that makes Rust unique. It eliminates the need for a garbage collector.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: { text: 'Rust ownership system: every value has exactly one owner, when owner goes out of scope the value is dropped' },
        },
      ],
    },
    {
      index: 1,
      userMessage:
        "The borrow checker is tricky though. I keep running into issues where I have a mutable reference and then try to use an immutable one. The compiler yells at me every time.",
      assistantResponse:
        'That is one of the most common stumbling blocks. You can have either one mutable reference or any number of immutable references, but not both at the same time.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: { text: 'Rust borrow checker: can have either one mutable reference or any number of immutable references, but not both' },
        },
      ],
    },
    {
      index: 2,
      userMessage:
        "Lifetimes are the part that really messes with my head. The 'a syntax for annotating how long references live -- it feels so foreign compared to Go.",
      assistantResponse:
        'Lifetimes are definitely the steepest part of the learning curve. They let the compiler verify that references are always valid.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: { text: "Rust lifetimes: the 'a syntax for annotating how long references live, compiler verifies references are always valid" },
        },
      ],
    },
    {
      index: 3,
      userMessage:
        "Traits are interesting though -- they're like interfaces but more powerful. I like how you can implement a trait for any type, even ones from other crates.",
      assistantResponse:
        'Traits are one of the best parts of Rust. They enable polymorphism without inheritance and work really well with generics.',
      toolCalls: [
        {
          name: 'totalreclaw_remember',
          params: { text: 'Rust traits: like interfaces but more powerful, can implement a trait for any type including ones from other crates' },
        },
      ],
    },
    {
      index: 4,
      userMessage:
        "And async/await in Rust is wild. It's zero-cost abstractions all the way down -- futures don't allocate unless you box them. Totally different from Go's goroutine model.",
      assistantResponse:
        'Rust async is very different from Go goroutines. The zero-cost model means you have more control but also more complexity.',
    },

    // --- Turns 6-10: Rust project details (extraction fires at turn 10) ---
    {
      index: 5,
      userMessage:
        "So I've started a project -- building a CLI tool in Rust for processing large log files. It needs to handle streaming data and parse structured JSON logs.",
      assistantResponse:
        'A log processing CLI is a great first Rust project. It will exercise file I/O, parsing, and error handling.',
    },
    {
      index: 6,
      userMessage:
        "I'm using Tokio for the async runtime. It's the de facto standard for async Rust, right? The multi-threaded scheduler is really impressive.",
      assistantResponse:
        'Yes, Tokio is the most widely used async runtime in the Rust ecosystem. Its work-stealing scheduler handles concurrency very well.',
    },
    {
      index: 7,
      userMessage:
        "For serialization I'm using serde -- it's amazing how it generates all the boilerplate at compile time with derive macros. Serde JSON parsing is incredibly fast.",
      assistantResponse:
        'Serde is one of the crown jewels of the Rust ecosystem. The derive macros make it effortless to serialize and deserialize any struct.',
    },
    {
      index: 8,
      userMessage:
        "I also pulled in clap for argument parsing. The derive API is really clean -- you just annotate your struct fields and it generates the entire CLI interface.",
      assistantResponse:
        'Clap is great for CLI tools. The derive API has gotten much better in recent versions.',
    },
    {
      index: 9,
      userMessage:
        "The error handling patterns with thiserror and anyhow are really nice too. thiserror for library code, anyhow for application code -- that seems to be the convention.",
      assistantResponse:
        'That is the standard pattern. thiserror gives you precise error types for libraries, anyhow gives you convenient error handling in applications.',
    },

    // --- Turn 11: Memory safety query (B3: diverse results expected) ---
    {
      index: 10,
      userMessage: 'How does Rust handle memory safety?',
      assistantResponse:
        'Rust ensures memory safety through its ownership system, borrow checker, and lifetime annotations -- all enforced at compile time with zero runtime cost.',
    },

    // --- Turn 12: Library recall ---
    {
      index: 11,
      userMessage: 'What libraries am I using in my project?',
      assistantResponse:
        'You mentioned using Tokio for async, serde for serialization, clap for CLI argument parsing, and thiserror/anyhow for error handling.',
    },

    // --- Turns 13-15: Paraphrased queries (semantic search test) ---
    {
      index: 12,
      userMessage:
        "What did I learn about memory management in that systems language I've been studying?",
      assistantResponse:
        'In Rust, memory is managed through ownership -- each value has exactly one owner, and the borrow checker enforces reference rules at compile time.',
    },
    {
      index: 13,
      userMessage:
        "What's the concurrency framework I picked for my log processing tool?",
      assistantResponse:
        'You chose Tokio as your async runtime for the Rust CLI log processing tool.',
    },
    {
      index: 14,
      userMessage:
        'How does the language I am learning prevent dangling pointers and use-after-free bugs?',
      assistantResponse:
        'Rust prevents those through lifetime annotations and the borrow checker, which ensures references never outlive the data they point to.',
    },

    // --- Turn 16: Explicit totalreclaw_recall tool call (C1: full search path) ---
    {
      index: 15,
      userMessage: 'Let me search my memories for everything about Rust async patterns.',
      assistantResponse:
        'Here is what I found about Rust async patterns from your previous conversations.',
      toolCalls: [
        {
          name: 'totalreclaw_recall',
          params: {
            query: 'Rust async patterns',
            k: 10,
          },
        },
      ],
    },

    // --- Turns 17-20: Follow-up technical questions ---
    {
      index: 16,
      userMessage:
        'Based on what I know so far, should I try writing a web server in Rust next? Something with Axum maybe?',
      assistantResponse:
        'Given your Tokio experience, Axum would be a natural next step. It is built on Tokio and hyper, so you already understand the foundation.',
    },
    {
      index: 17,
      userMessage:
        'How does the borrow checker interact with async code? I imagine passing references across await points gets complicated.',
      assistantResponse:
        'It can be tricky. References held across await points must satisfy lifetime requirements, which sometimes means cloning data or using Arc.',
    },
    {
      index: 18,
      userMessage:
        'What about testing? Are there good testing patterns for async Rust? I want to make sure my CLI tool is well tested.',
      assistantResponse:
        'Tokio has a test macro that sets up a runtime for async tests. You can also use mockall for mocking traits in unit tests.',
    },
    {
      index: 19,
      userMessage:
        "Alright, I think I have a solid grasp of the fundamentals now. Time to go write some code. Thanks for the Rust deep-dive!",
      assistantResponse:
        'Good luck with the project! You have a strong foundation to build on.',
    },
  ],
};

export default scenarioB;
