#!/usr/bin/env python3
"""
Synthetic Benchmark Dataset Generator for TotalReclaw 4-Way Benchmark.

Generates:
- 50-100 diverse persona templates
- 1000 realistic multi-turn conversations (10-20 messages each)
- Ground truth facts (~3000-5000 extractable facts)
- 2000-4000 test queries with relevance scores and categories

Uses OpenRouter free models via the OMBH LLM client pattern.
Supports checkpointing and resume for long-running generation.

Usage:
    cd ombh
    python scripts/generate_synthetic_benchmark.py --output synthetic-benchmark/ --conversations 1000
    python scripts/generate_synthetic_benchmark.py --output synthetic-benchmark/ --dry-run  # 10 conversations only
    python scripts/generate_synthetic_benchmark.py --output synthetic-benchmark/ --resume   # resume from checkpoint
"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Ensure ombh package is importable when running from ombh/ directory
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_OMBH_ROOT = _SCRIPT_DIR.parent
if str(_OMBH_ROOT) not in sys.path:
    sys.path.insert(0, str(_OMBH_ROOT))

from ombh.llm.client import LLMClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Persona Generation
# ============================================================================

# Topic pools for diverse conversation generation
OCCUPATION_POOL = [
    "Senior Software Engineer at Nexus Labs",
    "Product Designer at a fintech startup",
    "Data Scientist at BioGenesis Pharma",
    "Freelance Graphic Designer",
    "High School Math Teacher",
    "Emergency Room Nurse at City Hospital",
    "Mechanical Engineer at Tesla",
    "Marketing Manager at a SaaS company",
    "PhD Student in Computational Linguistics",
    "Chef and Restaurant Owner",
    "Civil Rights Attorney",
    "Indie Game Developer",
    "Veterinarian at a rural practice",
    "Journalist covering technology",
    "Architect at a sustainable design firm",
    "Music Producer and DJ",
    "Physical Therapist specializing in sports injuries",
    "Startup Founder (pre-seed, AI tools)",
    "Park Ranger at Yellowstone",
    "Financial Analyst at Goldman Sachs",
    "UX Researcher at a big tech company",
    "Electrician running own business",
    "Marine Biologist studying coral reefs",
    "Yoga Instructor and Wellness Coach",
    "DevOps Engineer at a cloud platform",
    "Real Estate Agent in Austin, TX",
    "Documentary Filmmaker",
    "Cybersecurity Consultant",
    "Elementary School Principal",
    "Aerospace Engineer at SpaceX",
    "Pastry Chef at a Michelin-starred restaurant",
    "Social Worker specializing in foster care",
    "Robotics Researcher at MIT",
    "Podcast Host covering true crime",
    "Agricultural Scientist working on drought-resistant crops",
    "Fashion Buyer for a luxury department store",
    "Paramedic in a major city",
    "Software QA Lead at a healthcare company",
    "Professional Rock Climber and Guide",
    "Librarian at a university research library",
    "Blockchain Developer at a DeFi protocol",
    "Interior Designer for commercial spaces",
    "Pediatrician in a community clinic",
    "Video Game Streamer and Content Creator",
    "Environmental Policy Advisor",
    "Opera Singer performing internationally",
    "Truck Driver (long-haul, owner-operator)",
    "AI Ethics Researcher at a think tank",
    "Wedding Planner running own agency",
    "Geologist working in mining exploration",
]

INTEREST_POOL = [
    "rock climbing", "rust programming", "japanese cuisine", "photography",
    "marathon running", "board games", "gardening", "piano",
    "sci-fi novels", "hiking", "coffee brewing", "yoga",
    "woodworking", "painting", "baking sourdough", "chess",
    "birdwatching", "home automation", "mountain biking", "meditation",
    "travel blogging", "vintage cars", "crossword puzzles", "astronomy",
    "cooking Thai food", "3D printing", "podcast listening", "skiing",
    "pottery", "urban sketching", "Brazilian jiu-jitsu", "aquariums",
    "mechanical keyboards", "fermentation", "stand-up comedy", "surfing",
    "calligraphy", "drone photography", "volunteer firefighting", "knitting",
    "speedcubing", "beekeeping", "origami", "salsa dancing",
    "home brewing beer", "triathlon training", "reading philosophy", "archery",
    "mushroom foraging", "leatherworking", "DJing", "tennis",
]

LIFE_CONTEXT_TEMPLATES = [
    "Recently moved to {city}. Has a {pet_type} named {pet_name}.",
    "Married with {num_kids} kid(s). Lives in {city}.",
    "Single, shares an apartment with roommates in {city}.",
    "Just went through a career change from {old_career}.",
    "Training for a {event} next month.",
    "Recently bought a house in {city} and renovating it.",
    "Travels frequently for work, based in {city}.",
    "Working remotely from {city} after leaving the Bay Area.",
    "Taking care of aging parents while working full-time in {city}.",
    "Just started a side project: {side_project}.",
    "Recovering from a {injury} and adjusting routines.",
    "Planning a wedding for next year.",
    "Recently adopted a {pet_type} named {pet_name} from a shelter.",
    "Finishing a part-time MBA while working in {city}.",
    "Expecting first child in a few months.",
    "Just returned from a sabbatical traveling through {region}.",
    "Commutes 45 minutes each way to work in {city}.",
    "Dealing with chronic back pain, exploring treatment options.",
    "Volunteering at a {volunteer_place} on weekends.",
    "Learning {language} in preparation for a move to {country}.",
]

CITIES = [
    "Portland, OR", "Austin, TX", "Denver, CO", "Seattle, WA",
    "Brooklyn, NY", "Chicago, IL", "San Diego, CA", "Nashville, TN",
    "Boston, MA", "Miami, FL", "Minneapolis, MN", "Lisbon, Portugal",
    "Barcelona, Spain", "Tokyo, Japan", "Berlin, Germany", "Toronto, Canada",
    "Melbourne, Australia", "Amsterdam, Netherlands", "Raleigh, NC",
    "Salt Lake City, UT", "Pittsburgh, PA", "Phoenix, AZ",
]

PET_NAMES = [
    "Luna", "Max", "Bella", "Charlie", "Milo", "Daisy", "Coco",
    "Rocky", "Ollie", "Nala", "Finn", "Pepper", "Scout", "Maple",
    "Bear", "Ziggy", "Rosie", "Thor", "Willow", "Biscuit",
]

TOPIC_CATEGORIES = [
    "work projects", "cooking and food", "fitness and health",
    "tech choices and tools", "travel experiences", "family and relationships",
    "hobbies and side projects", "finance and budgeting",
    "home improvement", "career decisions", "books and media",
    "pets and animals", "learning new skills", "social events",
    "daily routines", "environmental concerns",
]

FIRST_NAMES = [
    "Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley",
    "Avery", "Quinn", "Jamie", "Cameron", "Drew", "Reese", "Blake",
    "Hayden", "Sage", "Rowan", "Dakota", "Emery", "Finley",
    "Harper", "Kai", "Logan", "Parker", "River", "Skyler", "Tatum",
    "Wren", "Zion", "Ellis", "Devon", "Harley", "Lennox", "Phoenix",
    "Remy", "Shiloh", "Spencer", "Sterling", "Sutton", "Winter",
    "Aiden", "Brooke", "Carter", "Dana", "Ezra", "Frankie", "Gray",
    "India", "Jules", "Kit",
]

LAST_NAMES = [
    "Chen", "Patel", "Kim", "Nguyen", "Garcia", "Rodriguez",
    "Williams", "Brown", "Jones", "Davis", "Martinez", "Anderson",
    "Taylor", "Thomas", "Moore", "Jackson", "White", "Harris",
    "Clark", "Lewis", "Robinson", "Walker", "Hall", "Allen",
    "Young", "King", "Wright", "Scott", "Green", "Baker",
    "Adams", "Nelson", "Hill", "Campbell", "Mitchell", "Roberts",
    "Turner", "Phillips", "Evans", "Morales", "Reyes", "Cruz",
    "Flores", "Ramirez", "Diaz", "Nakamura", "Tanaka", "Schmidt",
    "Mueller", "Johansson",
]


def generate_personas(count: int, seed: int = 42) -> List[Dict[str, Any]]:
    """Generate diverse persona templates."""
    rng = random.Random(seed)
    personas = []
    used_names: Set[str] = set()

    for i in range(count):
        # Generate unique name
        while True:
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            full_name = f"{first} {last}"
            if full_name not in used_names:
                used_names.add(full_name)
                break

        age = rng.randint(22, 65)
        occupation = OCCUPATION_POOL[i % len(OCCUPATION_POOL)]
        interests = rng.sample(INTEREST_POOL, k=rng.randint(3, 6))
        topics = rng.sample(TOPIC_CATEGORIES, k=rng.randint(3, 5))

        # Generate life context
        template = rng.choice(LIFE_CONTEXT_TEMPLATES)
        city = rng.choice(CITIES)
        pet_type = rng.choice(["golden retriever", "cat", "border collie", "parrot", "rabbit"])
        pet_name = rng.choice(PET_NAMES)
        life_context = template.format(
            city=city,
            pet_type=pet_type,
            pet_name=pet_name,
            num_kids=rng.randint(1, 3),
            old_career=rng.choice(["finance", "teaching", "retail management", "journalism"]),
            event=rng.choice(["marathon", "triathlon", "charity bike ride", "5K"]),
            side_project=rng.choice([
                "a budgeting app", "a board game", "an online course",
                "a community garden", "a YouTube channel",
            ]),
            injury=rng.choice(["knee injury", "shoulder surgery", "broken wrist"]),
            region=rng.choice(["Southeast Asia", "South America", "Eastern Europe", "Japan"]),
            volunteer_place=rng.choice(["food bank", "animal shelter", "youth center", "hospital"]),
            language=rng.choice(["Spanish", "Japanese", "French", "Portuguese", "Mandarin"]),
            country=rng.choice(["Spain", "Japan", "France", "Brazil", "Taiwan"]),
        )

        persona = {
            "id": f"persona-{i+1:03d}",
            "name": full_name,
            "age": age,
            "occupation": occupation,
            "interests": interests,
            "life_context": life_context,
            "topics": topics,
        }
        personas.append(persona)

    return personas


# ============================================================================
# Conversation Generation
# ============================================================================

CONVERSATION_SYSTEM_PROMPT = """You are a conversation simulator. Generate realistic multi-turn conversations between a user and an AI assistant.

The conversations should:
1. Feel natural and human-like (the user side)
2. Contain specific, extractable facts about the user (names, preferences, events, decisions, locations, dates)
3. Mix casual chat with information-dense segments
4. Include the AI assistant responding helpfully and asking follow-up questions
5. Be diverse in tone: some casual, some information-heavy, some decision-making, some emotional

IMPORTANT:
- The user reveals personal details naturally through conversation, NOT by listing them
- Include specific names, numbers, dates, places where possible
- Each conversation should contain 3-8 clearly extractable facts
- Some facts should overlap with other conversations (for dedup testing)

Output ONLY valid JSON - no markdown, no explanations."""


def build_conversation_prompt(
    personas: List[Dict[str, Any]],
    conversation_indices: List[int],
    topic_hint: str,
    message_count_range: Tuple[int, int] = (10, 20),
) -> str:
    """Build a prompt to generate multiple conversations in one LLM call."""
    conversations_spec = []

    for idx in conversation_indices:
        persona = personas[idx % len(personas)]
        msg_count = random.randint(*message_count_range)

        conversations_spec.append({
            "conversation_id": f"conv-{idx+1:04d}",
            "persona_name": persona["name"],
            "persona_age": persona["age"],
            "persona_occupation": persona["occupation"],
            "persona_interests": persona["interests"],
            "persona_life_context": persona["life_context"],
            "topic": topic_hint,
            "message_count": msg_count,
        })

    prompt = f"""Generate {len(conversations_spec)} realistic multi-turn conversations.

For each conversation, the user is chatting with an AI assistant. The user naturally reveals personal information during the conversation.

Conversation specifications:
{json.dumps(conversations_spec, indent=2)}

For each conversation, generate exactly the specified number of messages alternating between "user" and "assistant" roles (starting with "user").

Each conversation MUST contain 3-8 specific, extractable facts about the user such as:
- Where they work/live
- Their preferences (food, tech, hobbies)
- Life events (trips, moves, purchases)
- Decisions they've made
- People they mention (colleagues, family, friends)
- Specific numbers/dates

Output format (JSON array of conversations):
{{
  "conversations": [
    {{
      "id": "conv-XXXX",
      "persona_id": "persona-XXX",
      "topic": "topic string",
      "messages": [
        {{"role": "user", "content": "message text"}},
        {{"role": "assistant", "content": "message text"}}
      ]
    }}
  ]
}}"""

    return prompt


# ============================================================================
# Fact Extraction
# ============================================================================

FACT_EXTRACTION_SYSTEM_PROMPT = """You are a fact extraction engine. Given a conversation, extract ALL facts that a memory system should remember about the user.

Guidelines:
1. Each fact should be atomic (one piece of information)
2. Include the user's name if mentioned
3. Types: factual, preference, decision, episodic, goal
4. Importance: 1-10 (1=trivial, 10=critical)
5. Be exhaustive - extract everything worth remembering

Output ONLY valid JSON - no markdown, no explanations."""


def build_fact_extraction_prompt(
    conversation_id: str,
    messages: List[Dict[str, str]],
) -> str:
    """Build prompt to extract ground truth facts from a conversation."""
    formatted = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

    return f"""Extract ALL facts worth remembering from this conversation.

Conversation ID: {conversation_id}

{formatted}

Output format:
{{
  "facts": [
    {{
      "text": "specific atomic fact about the user",
      "type": "factual|preference|decision|episodic|goal",
      "importance": 8
    }}
  ]
}}

Extract 3-8 facts. Be specific - include names, numbers, places. Skip trivial pleasantries."""


# ============================================================================
# Query Generation
# ============================================================================

QUERY_GENERATION_SYSTEM_PROMPT = """You are a test query generator for a memory retrieval system. Given a set of facts from a user's conversations with an AI assistant, generate diverse search queries that the user might ask to recall information.

STRICT rules — violating ANY of these makes the output INVALID:
1. You MUST generate EXACTLY the number of queries requested for each category. Count them before outputting.
2. The "category" field MUST be one of: "factual", "semantic", "cross_conversation", "negative". No other values allowed.
3. Factual queries: Direct questions using similar wording to the facts. MUST have 2-3+ relevant_facts entries.
4. Semantic queries: Rephrase facts using COMPLETELY DIFFERENT wording — synonyms, different sentence structures, indirect references. MUST have 2-3+ relevant_facts entries.
5. Cross-conversation queries: MUST combine facts from BOTH "Primary facts" AND "Other conversation facts" sections. Include fact IDs from BOTH sections in relevant_facts. These are the MOST IMPORTANT queries.
6. Negative queries: Ask about plausible topics NOT covered by ANY fact. relevant_facts MUST be an empty array [].
7. Output ONLY valid JSON — no markdown fences, no explanations, no trailing commas."""


def build_query_generation_prompt(
    facts_batch: List[Dict[str, Any]],
    queries_per_batch: int = 10,
    all_fact_ids: Optional[List[str]] = None,
    cross_conv_facts: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build prompt to generate test queries from a batch of facts.

    Args:
        facts_batch: Primary facts to generate queries about.
        queries_per_batch: Total number of queries to generate.
        all_fact_ids: All fact IDs (unused, kept for compat).
        cross_conv_facts: Facts from OTHER conversations, used for
            cross_conversation queries. The LLM is asked to generate
            queries that combine primary facts with these.
    """
    facts_text = "\n".join(
        f"[{f['id']}] ({f['type']}, importance={f['importance']}): {f['text']}"
        for f in facts_batch
    )

    # Calculate target distribution for this batch — use round() so small
    # batch sizes still produce cross_conversation queries.
    n_factual = max(1, round(queries_per_batch * 0.30))
    n_semantic = max(1, round(queries_per_batch * 0.40))
    n_cross = max(1, round(queries_per_batch * 0.20))
    n_negative = max(1, queries_per_batch - n_factual - n_semantic - n_cross)
    # If total exceeds budget, trim negative first
    while n_factual + n_semantic + n_cross + n_negative > queries_per_batch and n_negative > 0:
        n_negative -= 1
    # Then trim cross if still over
    while n_factual + n_semantic + n_cross + n_negative > queries_per_batch and n_cross > 0:
        n_cross -= 1

    # Build cross-conversation context section
    cross_section = ""
    if cross_conv_facts:
        cross_text = "\n".join(
            f"[{f['id']}] ({f['type']}, importance={f['importance']}): {f['text']}"
            for f in cross_conv_facts
        )
        cross_section = f"""

Other conversation facts (from DIFFERENT conversations — use these for cross_conversation queries):
{cross_text}

IMPORTANT for cross_conversation queries: Create questions that naturally combine or compare
information from the primary facts above AND these other conversation facts. For example:
- "What are all the places the user has traveled to?" (combining travel facts from multiple conversations)
- "Does the user prefer working remotely or in-office?" (combining work-related facts from different conversations)
- "What programming languages and tools does the user use?" (combining tech facts from multiple conversations)
Include fact IDs from BOTH sections in the relevant_facts list for cross_conversation queries."""

    return f"""Generate EXACTLY {queries_per_batch} test queries based on these facts.

Primary facts (from this conversation batch):
{facts_text}
{cross_section}

REQUIRED distribution — count carefully before outputting:
- EXACTLY {n_factual} queries with category "factual": Direct questions about specific primary facts using similar wording. Each MUST have 2-3+ entries in relevant_facts.
- EXACTLY {n_semantic} queries with category "semantic": Rephrase facts using COMPLETELY DIFFERENT words, synonyms, and indirect references. Each MUST have 2-3+ entries in relevant_facts.
- EXACTLY {n_cross} queries with category "cross_conversation": Questions that naturally combine information from BOTH the primary facts AND the other conversation facts. You MUST include fact IDs from BOTH sections in relevant_facts. Example: "What are all the user's hobbies?" combining hobby facts from different conversations.
- EXACTLY {n_negative} queries with category "negative": Questions about plausible topics NOT covered by ANY listed fact. relevant_facts MUST be exactly [].

VERIFY before outputting: Count each category. You need exactly {n_factual} factual + {n_semantic} semantic + {n_cross} cross_conversation + {n_negative} negative = {queries_per_batch} total.

For each query, provide relevance scores (0.0-1.0) for EVERY fact that is relevant:
- 1.0 = perfectly relevant (fact directly answers the query)
- 0.7-0.9 = highly relevant (fact is closely related)
- 0.4-0.6 = partially relevant (fact provides some context)
- Omit facts with relevance < 0.4

IMPORTANT: Reference as many facts as possible per query. Most factual and semantic queries should have 2-3+ relevant facts.

Output format:
{{
  "queries": [
    {{
      "text": "natural search question",
      "category": "factual|semantic|cross_conversation|negative",
      "relevant_facts": [
        {{"fact_id": "fact-XXXX", "relevance": 0.95}},
        {{"fact_id": "fact-YYYY", "relevance": 0.6}}
      ]
    }}
  ]
}}"""


# ============================================================================
# Checkpoint Manager
# ============================================================================

@dataclass
class Checkpoint:
    """Tracks generation progress for resume capability."""
    phase: str = "personas"  # personas, conversations, facts, queries, validation
    conversations_generated: int = 0
    facts_extracted: int = 0
    query_batches_processed: int = 0
    total_conversations: int = 0
    total_fact_batches: int = 0
    total_query_batches: int = 0
    started_at: str = ""
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "conversations_generated": self.conversations_generated,
            "facts_extracted": self.facts_extracted,
            "query_batches_processed": self.query_batches_processed,
            "total_conversations": self.total_conversations,
            "total_fact_batches": self.total_fact_batches,
            "total_query_batches": self.total_query_batches,
            "started_at": self.started_at,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Checkpoint":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path) -> None:
        self.last_updated = datetime.now().isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "Checkpoint":
        with open(path) as f:
            return cls.from_dict(json.load(f))


# ============================================================================
# JSON Parsing Helpers
# ============================================================================

def parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()

    # Strip markdown code blocks
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Strip <think>...</think> blocks (DeepSeek-R1)
    import re
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find the first JSON object/array in the text
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find the matching closing bracket
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not parse JSON from response: {text[:200]}...")


# ============================================================================
# Main Generator
# ============================================================================

class SyntheticBenchmarkGenerator:
    """Generates the complete synthetic benchmark dataset."""

    def __init__(
        self,
        output_dir: str,
        num_conversations: int = 1000,
        num_personas: int = 50,
        queries_per_batch: int = 4,
        conversations_per_llm_call: int = 5,
        fact_extraction_batch: int = 3,
        query_fact_batch_size: int = 10,
        resume: bool = False,
        seed: int = 42,
    ):
        self.output_dir = Path(output_dir)
        self.num_conversations = num_conversations
        self.num_personas = num_personas
        self.queries_per_batch = queries_per_batch
        self.conversations_per_llm_call = conversations_per_llm_call
        self.fact_extraction_batch = fact_extraction_batch
        self.query_fact_batch_size = query_fact_batch_size
        self.resume = resume
        self.seed = seed
        self.rng = random.Random(seed)

        # Directories
        self.conv_dir = self.output_dir / "conversations"
        self.gt_dir = self.output_dir / "ground-truth"
        self.persona_dir = self.output_dir / "personas"
        self.checkpoint_path = self.output_dir / ".checkpoint.json"

        # State
        self.personas: List[Dict[str, Any]] = []
        self.all_facts: List[Dict[str, Any]] = []
        self.all_queries: List[Dict[str, Any]] = []
        self.checkpoint = Checkpoint()

        # LLM client (initialized lazily)
        self._llm: Optional[LLMClient] = None

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient(
                temperature=0.7,  # diversity for conversations
                max_tokens=8192,  # 8k for multi-conversation batches (Gemini is verbose)
                request_json=True,
                timeout=180.0,
            )
        return self._llm

    @property
    def _is_local_llm(self) -> bool:
        """Check if the active LLM is a local model (Ollama) — no rate limiting needed."""
        return self.llm._using_ollama

    def _llm_for_extraction(self) -> LLMClient:
        """Return a client configured for extraction (lower temperature).

        Uses GPT-4.1 Mini via OpenRouter for higher quality structured
        JSON extraction (fact extraction + query generation).  Explicit
        api_key + base_url to skip the Gemini/Z.AI fallback chain.
        """
        import os
        or_key = os.environ.get("OPENROUTER_API_KEY", "")
        return LLMClient(
            api_key=or_key,
            base_url="https://openrouter.ai/api/v1",
            model="openai/gpt-4.1-mini",
            fallback_models=["openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct"],
            temperature=0.3,
            max_tokens=4096,
            request_json=True,
            timeout=180.0,
        )

    # ------------------------------------------------------------------
    # Phase 1a: Personas
    # ------------------------------------------------------------------

    def generate_and_save_personas(self) -> None:
        """Generate persona templates and save to disk."""
        logger.info("Phase 1a: Generating %d personas...", self.num_personas)
        self.personas = generate_personas(self.num_personas, self.seed)

        self.persona_dir.mkdir(parents=True, exist_ok=True)
        with open(self.persona_dir / "personas.json", "w") as f:
            json.dump(self.personas, f, indent=2, ensure_ascii=False)

        logger.info("Saved %d personas to %s", len(self.personas), self.persona_dir / "personas.json")

    def load_personas(self) -> None:
        """Load personas from disk."""
        path = self.persona_dir / "personas.json"
        if path.exists():
            with open(path) as f:
                self.personas = json.load(f)
            logger.info("Loaded %d personas from disk", len(self.personas))
        else:
            self.generate_and_save_personas()

    # ------------------------------------------------------------------
    # Phase 1b: Conversations
    # ------------------------------------------------------------------

    async def generate_conversations(self) -> None:
        """Generate all conversations using batched LLM calls."""
        logger.info(
            "Phase 1b: Generating %d conversations (%d per LLM call)...",
            self.num_conversations,
            self.conversations_per_llm_call,
        )
        self.conv_dir.mkdir(parents=True, exist_ok=True)

        start_from = self.checkpoint.conversations_generated
        batch_size = self.conversations_per_llm_call

        # Determine total batches
        total_batches = (self.num_conversations + batch_size - 1) // batch_size
        self.checkpoint.total_conversations = self.num_conversations

        # Create a topic rotation
        topic_rotation = list(TOPIC_CATEGORIES)
        self.rng.shuffle(topic_rotation)

        batch_idx = start_from // batch_size

        for batch_start in range(start_from, self.num_conversations, batch_size):
            batch_end = min(batch_start + batch_size, self.num_conversations)
            indices = list(range(batch_start, batch_end))

            # Pick topic for this batch
            topic = topic_rotation[batch_idx % len(topic_rotation)]

            # Determine message count range; ~5% should be short (3 msg), rest normal
            if self.rng.random() < 0.05:
                msg_range = (3, 5)  # edge case: very short
            elif self.rng.random() < 0.10:
                msg_range = (18, 24)  # edge case: very long
            else:
                msg_range = (10, 18)  # normal

            prompt = build_conversation_prompt(
                self.personas, indices, topic, msg_range
            )

            logger.info(
                "[%d/%d] Generating conversations %d-%d (topic: %s, msgs: %s)...",
                batch_idx + 1,
                total_batches,
                batch_start + 1,
                batch_end,
                topic,
                msg_range,
            )

            try:
                response = await self.llm.complete(
                    system=CONVERSATION_SYSTEM_PROMPT,
                    user=prompt,
                    max_tokens=8192,
                )

                parsed = parse_json_response(response)
                conversations = parsed.get("conversations", [])

                if not conversations:
                    logger.warning("Empty response for batch %d, retrying...", batch_idx)
                    # Retry once
                    response = await self.llm.complete(
                        system=CONVERSATION_SYSTEM_PROMPT,
                        user=prompt,
                        max_tokens=8192,
                    )
                    parsed = parse_json_response(response)
                    conversations = parsed.get("conversations", [])

                # Save each conversation as a separate JSONL file
                for j, conv in enumerate(conversations):
                    conv_idx = batch_start + j
                    conv_id = f"conv-{conv_idx + 1:04d}"
                    messages = conv.get("messages", [])

                    if not messages:
                        logger.warning("Empty messages for %s, skipping", conv_id)
                        continue

                    # Ensure conversation has the correct ID
                    conv["id"] = conv_id

                    # Assign persona_id
                    persona_idx = conv_idx % len(self.personas)
                    conv["persona_id"] = self.personas[persona_idx]["id"]

                    # Write JSONL
                    jsonl_path = self.conv_dir / f"{conv_id}.jsonl"
                    with open(jsonl_path, "w") as f:
                        for msg in messages:
                            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

                    # Also save full metadata
                    meta_path = self.conv_dir / f"{conv_id}.meta.json"
                    with open(meta_path, "w") as f:
                        json.dump(
                            {
                                "id": conv_id,
                                "persona_id": conv.get("persona_id", ""),
                                "topic": conv.get("topic", topic),
                                "message_count": len(messages),
                            },
                            f,
                            indent=2,
                        )

                # Update checkpoint
                self.checkpoint.conversations_generated = min(
                    batch_end, self.num_conversations
                )
                self.checkpoint.phase = "conversations"
                self.checkpoint.save(self.checkpoint_path)

                logger.info(
                    "  Saved %d conversations (total: %d/%d)",
                    len(conversations),
                    self.checkpoint.conversations_generated,
                    self.num_conversations,
                )

            except Exception as e:
                logger.error("Error generating batch %d: %s", batch_idx, e)
                # Continue to next batch rather than crash
                self.checkpoint.conversations_generated = batch_end
                self.checkpoint.save(self.checkpoint_path)

            batch_idx += 1

    # ------------------------------------------------------------------
    # Phase 1c: Fact Extraction
    # ------------------------------------------------------------------

    async def extract_facts(self) -> None:
        """Extract ground truth facts from all conversations."""
        logger.info("Phase 1c: Extracting ground truth facts...")
        self.gt_dir.mkdir(parents=True, exist_ok=True)

        # Load existing facts if resuming
        facts_path = self.gt_dir / "facts.json"
        existing_facts: Dict[str, List[Dict]] = {}
        if self.resume and facts_path.exists():
            with open(facts_path) as f:
                data = json.load(f)
                for fact in data.get("facts", []):
                    for src in fact.get("source_conversations", []):
                        existing_facts.setdefault(src, []).append(fact)
            logger.info("Loaded %d existing facts", sum(len(v) for v in existing_facts.values()))

        # Get all conversation files
        conv_files = sorted(self.conv_dir.glob("conv-*.jsonl"))
        logger.info("Found %d conversation files", len(conv_files))

        extraction_client = self._llm_for_extraction()
        all_facts: List[Dict[str, Any]] = []
        fact_counter = 0

        # Re-add existing facts first
        seen_fact_ids: Set[str] = set()
        for facts_list in existing_facts.values():
            for f in facts_list:
                if f["id"] not in seen_fact_ids:
                    all_facts.append(f)
                    seen_fact_ids.add(f["id"])
                    fact_counter = max(fact_counter, int(f["id"].split("-")[1]))

        # Process conversations in batches
        batch_size = self.fact_extraction_batch
        start_idx = self.checkpoint.facts_extracted

        for i in range(start_idx, len(conv_files), batch_size):
            batch_files = conv_files[i:i + batch_size]

            for conv_file in batch_files:
                conv_id = conv_file.stem  # e.g., "conv-0001"

                # Skip if already extracted
                if conv_id in existing_facts:
                    continue

                # Load conversation messages
                messages = []
                with open(conv_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            messages.append(json.loads(line))

                if not messages:
                    continue

                prompt = build_fact_extraction_prompt(conv_id, messages)

                try:
                    response = await extraction_client.complete(
                        system=FACT_EXTRACTION_SYSTEM_PROMPT,
                        user=prompt,
                        max_tokens=4096,
                    )

                    parsed = parse_json_response(response)
                    facts = parsed.get("facts", [])

                    for raw_fact in facts:
                        fact_counter += 1
                        fact = {
                            "id": f"fact-{fact_counter:04d}",
                            "text": raw_fact.get("text", ""),
                            "type": raw_fact.get("type", "factual"),
                            "importance": raw_fact.get("importance", 5),
                            "source_conversations": [conv_id],
                            "first_mentioned": conv_id,
                        }
                        if fact["text"]:
                            all_facts.append(fact)

                except Exception as e:
                    logger.error("Error extracting facts from %s: %s", conv_id, e)

            # Update checkpoint
            self.checkpoint.facts_extracted = min(i + batch_size, len(conv_files))
            self.checkpoint.phase = "facts"
            self.checkpoint.save(self.checkpoint_path)

            logger.info(
                "  Extracted facts from %d/%d conversations (total facts: %d)",
                self.checkpoint.facts_extracted,
                len(conv_files),
                len(all_facts),
            )

        self.all_facts = all_facts

        # Save facts
        with open(facts_path, "w") as f:
            json.dump(
                {
                    "metadata": {
                        "version": "1.0",
                        "created": datetime.now().isoformat(),
                        "total_facts": len(all_facts),
                        "total_conversations_processed": len(conv_files),
                    },
                    "facts": all_facts,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        logger.info("Saved %d facts to %s", len(all_facts), facts_path)

    # ------------------------------------------------------------------
    # Phase 1d: Query Generation
    # ------------------------------------------------------------------

    async def generate_queries(self) -> None:
        """Generate test queries from extracted facts."""
        logger.info("Phase 1d: Generating test queries...")

        # Load facts if not already loaded
        if not self.all_facts:
            facts_path = self.gt_dir / "facts.json"
            if facts_path.exists():
                with open(facts_path) as f:
                    data = json.load(f)
                    self.all_facts = data.get("facts", [])
            if not self.all_facts:
                logger.error("No facts found. Run fact extraction first.")
                return

        logger.info("Generating queries from %d facts...", len(self.all_facts))

        # Load existing queries if resuming
        queries_path = self.gt_dir / "queries.json"
        existing_queries: List[Dict] = []
        if self.resume and queries_path.exists():
            with open(queries_path) as f:
                data = json.load(f)
                existing_queries = data.get("queries", [])
            logger.info("Loaded %d existing queries", len(existing_queries))

        extraction_client = self._llm_for_extraction()
        all_queries = list(existing_queries)
        query_counter = len(existing_queries)

        # Process facts in batches
        batch_size = self.query_fact_batch_size
        start_batch = self.checkpoint.query_batches_processed
        total_batches = (len(self.all_facts) + batch_size - 1) // batch_size
        self.checkpoint.total_query_batches = total_batches

        all_fact_ids = [f["id"] for f in self.all_facts]

        # Pre-build an index of facts by source conversation for cross-conv sampling
        facts_by_conv: Dict[str, List[Dict[str, Any]]] = {}
        for f in self.all_facts:
            for conv_id in f.get("source_conversations", []):
                facts_by_conv.setdefault(conv_id, []).append(f)

        for batch_idx in range(start_batch, total_batches):
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(self.all_facts))
            facts_batch = self.all_facts[batch_start:batch_end]

            # Collect conversation IDs from this batch
            batch_conv_ids: Set[str] = set()
            for f in facts_batch:
                for conv_id in f.get("source_conversations", []):
                    batch_conv_ids.add(conv_id)

            # Sample facts from OTHER conversations for cross-conversation queries
            other_conv_ids = [c for c in facts_by_conv if c not in batch_conv_ids]
            cross_conv_facts: List[Dict[str, Any]] = []
            if other_conv_ids:
                # Pick 2-3 random other conversations and sample a few facts from each
                sample_convs = self.rng.sample(other_conv_ids, min(3, len(other_conv_ids)))
                for conv_id in sample_convs:
                    conv_facts = facts_by_conv[conv_id]
                    sample_size = min(3, len(conv_facts))
                    cross_conv_facts.extend(self.rng.sample(conv_facts, sample_size))

            prompt = build_query_generation_prompt(
                facts_batch,
                self.queries_per_batch,
                all_fact_ids,
                cross_conv_facts=cross_conv_facts if cross_conv_facts else None,
            )

            logger.info(
                "[%d/%d] Generating queries for facts %d-%d...",
                batch_idx + 1,
                total_batches,
                batch_start + 1,
                batch_end,
            )

            try:
                response = await extraction_client.complete(
                    system=QUERY_GENERATION_SYSTEM_PROMPT,
                    user=prompt,
                    max_tokens=4096,
                )

                parsed = parse_json_response(response)
                queries = parsed.get("queries", [])

                for raw_query in queries:
                    query_counter += 1
                    query = {
                        "id": f"query-{query_counter:04d}",
                        "text": raw_query.get("text", ""),
                        "category": raw_query.get("category", "factual"),
                        "relevant_facts": raw_query.get("relevant_facts", []),
                        "source_fact_batch": [f["id"] for f in facts_batch],
                    }
                    if query["text"]:
                        all_queries.append(query)

            except Exception as e:
                logger.error("Error generating queries for batch %d: %s", batch_idx, e)

            # Update checkpoint
            self.checkpoint.query_batches_processed = batch_idx + 1
            self.checkpoint.phase = "queries"
            self.checkpoint.save(self.checkpoint_path)

            if (batch_idx + 1) % 10 == 0:
                logger.info(
                    "  Progress: %d/%d batches, %d queries generated",
                    batch_idx + 1,
                    total_batches,
                    len(all_queries),
                )

            # Small delay to avoid burst rate limits on OpenRouter
            if not self._is_local_llm:
                await asyncio.sleep(0.2)

        self.all_queries = all_queries

        # Save queries
        with open(queries_path, "w") as f:
            json.dump(
                {
                    "metadata": {
                        "version": "1.0",
                        "created": datetime.now().isoformat(),
                        "total_queries": len(all_queries),
                        "total_facts_processed": len(self.all_facts),
                        "queries_per_batch": self.queries_per_batch,
                    },
                    "queries": all_queries,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        logger.info("Saved %d queries to %s", len(all_queries), queries_path)

    # ------------------------------------------------------------------
    # Phase 1e: Quality Validation
    # ------------------------------------------------------------------

    def validate_and_statistics(self) -> Dict[str, Any]:
        """Validate the dataset and compute statistics."""
        logger.info("Phase 1e: Validating dataset and computing statistics...")

        stats: Dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "seed": self.seed,
        }

        # Conversation stats
        conv_files = sorted(self.conv_dir.glob("conv-*.jsonl"))
        msg_counts = []
        empty_convs = 0
        for conv_file in conv_files:
            count = 0
            with open(conv_file) as f:
                for line in f:
                    if line.strip():
                        count += 1
            msg_counts.append(count)
            if count == 0:
                empty_convs += 1

        stats["conversations"] = {
            "total": len(conv_files),
            "empty": empty_convs,
            "avg_messages": round(sum(msg_counts) / max(len(msg_counts), 1), 1),
            "min_messages": min(msg_counts) if msg_counts else 0,
            "max_messages": max(msg_counts) if msg_counts else 0,
            "total_messages": sum(msg_counts),
        }

        # Fact stats
        facts_path = self.gt_dir / "facts.json"
        if facts_path.exists():
            with open(facts_path) as f:
                facts_data = json.load(f)
            facts = facts_data.get("facts", [])

            type_dist = {}
            importance_dist = {}
            for fact in facts:
                ft = fact.get("type", "unknown")
                type_dist[ft] = type_dist.get(ft, 0) + 1
                imp = fact.get("importance", 0)
                bucket = f"{imp}"
                importance_dist[bucket] = importance_dist.get(bucket, 0) + 1

            conv_with_facts = set()
            for fact in facts:
                for src in fact.get("source_conversations", []):
                    conv_with_facts.add(src)

            stats["facts"] = {
                "total": len(facts),
                "type_distribution": type_dist,
                "importance_distribution": importance_dist,
                "conversations_with_facts": len(conv_with_facts),
                "avg_facts_per_conversation": round(
                    len(facts) / max(len(conv_files), 1), 2
                ),
            }
        else:
            stats["facts"] = {"total": 0, "error": "facts.json not found"}

        # Query stats
        queries_path = self.gt_dir / "queries.json"
        if queries_path.exists():
            with open(queries_path) as f:
                queries_data = json.load(f)
            queries = queries_data.get("queries", [])

            category_dist = {}
            queries_with_relevance = 0
            total_relevance_pairs = 0

            for query in queries:
                cat = query.get("category", "unknown")
                category_dist[cat] = category_dist.get(cat, 0) + 1
                rels = query.get("relevant_facts", [])
                if rels:
                    queries_with_relevance += 1
                    total_relevance_pairs += len(rels)

            stats["queries"] = {
                "total": len(queries),
                "category_distribution": category_dist,
                "with_relevance_scores": queries_with_relevance,
                "total_relevance_pairs": total_relevance_pairs,
                "avg_relevant_facts_per_query": round(
                    total_relevance_pairs / max(len(queries), 1), 2
                ),
            }

            # Orphan check: facts not referenced by any query
            referenced_facts = set()
            for query in queries:
                for rel in query.get("relevant_facts", []):
                    referenced_facts.add(rel.get("fact_id", ""))

            all_fact_ids = set()
            if facts_path.exists():
                for fact in facts:
                    all_fact_ids.add(fact["id"])

            orphan_facts = all_fact_ids - referenced_facts
            stats["quality"] = {
                "orphan_facts_count": len(orphan_facts),
                "orphan_facts_pct": round(
                    len(orphan_facts) / max(len(all_fact_ids), 1) * 100, 1
                ),
                "empty_queries": sum(1 for q in queries if not q.get("text")),
                "queries_with_no_relevance": len(queries) - queries_with_relevance,
            }
        else:
            stats["queries"] = {"total": 0, "error": "queries.json not found"}
            stats["quality"] = {}

        # Persona stats
        persona_path = self.persona_dir / "personas.json"
        if persona_path.exists():
            with open(persona_path) as f:
                personas = json.load(f)
            stats["personas"] = {"total": len(personas)}
        else:
            stats["personas"] = {"total": 0}

        # LLM usage stats
        if self._llm:
            stats["llm_usage"] = self._llm.usage.to_dict()

        # Save statistics
        self.gt_dir.mkdir(parents=True, exist_ok=True)
        stats_path = self.gt_dir / "statistics.json"
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=2)

        logger.info("Statistics saved to %s", stats_path)
        self._print_summary(stats)

        return stats

    def _print_summary(self, stats: Dict[str, Any]) -> None:
        """Print a human-readable summary of the dataset."""
        print("\n" + "=" * 60)
        print("SYNTHETIC BENCHMARK DATASET SUMMARY")
        print("=" * 60)

        conv = stats.get("conversations", {})
        print(f"\nConversations: {conv.get('total', 0)}")
        print(f"  Total messages: {conv.get('total_messages', 0)}")
        print(f"  Avg messages/conversation: {conv.get('avg_messages', 0)}")
        print(f"  Range: {conv.get('min_messages', 0)}-{conv.get('max_messages', 0)}")
        print(f"  Empty conversations: {conv.get('empty', 0)}")

        facts = stats.get("facts", {})
        print(f"\nFacts: {facts.get('total', 0)}")
        if "type_distribution" in facts:
            print(f"  Type distribution: {json.dumps(facts['type_distribution'])}")
        print(f"  Avg facts/conversation: {facts.get('avg_facts_per_conversation', 0)}")

        queries = stats.get("queries", {})
        print(f"\nQueries: {queries.get('total', 0)}")
        if "category_distribution" in queries:
            print(f"  Category distribution: {json.dumps(queries['category_distribution'])}")
        print(f"  Avg relevant facts/query: {queries.get('avg_relevant_facts_per_query', 0)}")

        quality = stats.get("quality", {})
        if quality:
            print(f"\nQuality checks:")
            print(f"  Orphan facts (not in any query): {quality.get('orphan_facts_count', 0)} ({quality.get('orphan_facts_pct', 0)}%)")
            print(f"  Empty queries: {quality.get('empty_queries', 0)}")
            print(f"  Queries with no relevance scores: {quality.get('queries_with_no_relevance', 0)}")

        llm = stats.get("llm_usage", {})
        if llm:
            print(f"\nLLM Usage:")
            print(f"  Total calls: {llm.get('total_calls', 0)}")
            print(f"  Total tokens: {llm.get('total_tokens', 0)}")
            print(f"  Avg latency: {llm.get('avg_latency_ms', 0):.0f}ms")
            print(f"  Errors: {llm.get('total_errors', 0)}")
            print(f"  Retries: {llm.get('total_retries', 0)}")

        print("\n" + "=" * 60)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    async def run(self) -> Dict[str, Any]:
        """Run the complete generation pipeline."""
        start_time = time.time()

        # Initialize checkpoint
        if self.resume and self.checkpoint_path.exists():
            self.checkpoint = Checkpoint.load(self.checkpoint_path)
            logger.info(
                "Resuming from checkpoint: phase=%s, convs=%d, facts=%d, query_batches=%d",
                self.checkpoint.phase,
                self.checkpoint.conversations_generated,
                self.checkpoint.facts_extracted,
                self.checkpoint.query_batches_processed,
            )
        else:
            self.checkpoint = Checkpoint(started_at=datetime.now().isoformat())
            self.checkpoint.save(self.checkpoint_path)

        # Phase 1a: Personas
        self.load_personas()

        # Phase 1b: Conversations
        if self.checkpoint.phase in ("personas", "conversations"):
            if self.checkpoint.conversations_generated < self.num_conversations:
                await self.generate_conversations()
            else:
                logger.info("Conversations already generated (%d), skipping...",
                           self.checkpoint.conversations_generated)

        # Phase 1c: Fact extraction
        if self.checkpoint.phase in ("personas", "conversations", "facts"):
            conv_files = sorted(self.conv_dir.glob("conv-*.jsonl"))
            if self.checkpoint.facts_extracted < len(conv_files):
                await self.extract_facts()
            else:
                logger.info("Facts already extracted, skipping...")

        # Always load facts from disk if not already in memory (needed for query generation)
        if not self.all_facts:
            facts_path = self.gt_dir / "facts.json"
            if facts_path.exists():
                with open(facts_path) as f:
                    data = json.load(f)
                    self.all_facts = data.get("facts", [])
                logger.info("Loaded %d facts from disk", len(self.all_facts))

        # Phase 1d: Query generation
        if self.checkpoint.phase in ("personas", "conversations", "facts", "queries"):
            total_fact_batches = (len(self.all_facts) + self.query_fact_batch_size - 1) // self.query_fact_batch_size
            if self.checkpoint.query_batches_processed < total_fact_batches:
                await self.generate_queries()
            else:
                logger.info("Queries already generated, skipping...")

        # Phase 1e: Validation
        stats = self.validate_and_statistics()

        # Update checkpoint
        self.checkpoint.phase = "completed"
        self.checkpoint.save(self.checkpoint_path)

        elapsed = time.time() - start_time
        logger.info("Complete! Total time: %.1f minutes", elapsed / 60)

        return stats


# ============================================================================
# README Generator
# ============================================================================

def generate_readme(output_dir: Path, stats: Dict[str, Any]) -> None:
    """Generate a README.md for the synthetic benchmark dataset."""
    conv = stats.get("conversations", {})
    facts = stats.get("facts", {})
    queries = stats.get("queries", {})

    readme = f"""# Synthetic Benchmark Dataset

Generated by `ombh/scripts/generate_synthetic_benchmark.py` for the TotalReclaw 4-way benchmark.

## Dataset Summary

| Metric | Value |
|--------|-------|
| Conversations | {conv.get('total', 0)} |
| Total messages | {conv.get('total_messages', 0)} |
| Avg messages/conversation | {conv.get('avg_messages', 0)} |
| Ground truth facts | {facts.get('total', 0)} |
| Avg facts/conversation | {facts.get('avg_facts_per_conversation', 0)} |
| Test queries | {queries.get('total', 0)} |
| Avg relevant facts/query | {queries.get('avg_relevant_facts_per_query', 0)} |

## Structure

```
{output_dir.name}/
  conversations/          # 1 JSONL file per conversation (user/assistant turns)
    conv-0001.jsonl
    conv-0001.meta.json   # Conversation metadata (persona, topic, msg count)
    ...
  ground-truth/
    facts.json            # All extractable facts with types and importance
    queries.json          # Test queries with relevance scores
    statistics.json       # Dataset statistics and quality metrics
  personas/
    personas.json         # Persona templates used for generation
```

## Conversation Format (JSONL)

Each line is a JSON object:
```json
{{"role": "user", "content": "Hey, I just got back from my trip to Tokyo!"}}
{{"role": "assistant", "content": "That sounds amazing! How was it?"}}
```

## Fact Format

```json
{{
  "id": "fact-0001",
  "text": "Alex works at Nexus Labs as a senior software engineer",
  "type": "factual",
  "importance": 8,
  "source_conversations": ["conv-0001", "conv-0005"],
  "first_mentioned": "conv-0001"
}}
```

## Query Categories

| Category | Target % | Description |
|----------|----------|-------------|
| factual | ~30% | Direct questions about stored facts |
| semantic | ~40% | Paraphrased queries (different words, same meaning) |
| cross_conversation | ~20% | Questions spanning multiple facts/conversations |
| negative | ~10% | Questions that should return no matching facts |

## Generation

```bash
cd ombh
python scripts/generate_synthetic_benchmark.py --output synthetic-benchmark/ --conversations 1000
```

Generated: {stats.get('generated_at', 'unknown')}
"""

    with open(output_dir / "README.md", "w") as f:
        f.write(readme)


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic benchmark dataset for TotalReclaw 4-way benchmark"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="synthetic-benchmark",
        help="Output directory (default: synthetic-benchmark/)",
    )
    parser.add_argument(
        "--conversations",
        type=int,
        default=1000,
        help="Number of conversations to generate (default: 1000)",
    )
    parser.add_argument(
        "--queries-per-batch",
        type=int,
        default=4,
        help="Queries to generate per fact batch (default: 4)",
    )
    parser.add_argument(
        "--personas",
        type=int,
        default=50,
        help="Number of persona templates (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate only 10 conversations (for testing)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--conversations-per-call",
        type=int,
        default=5,
        help="Conversations per LLM call (default: 5)",
    )

    args = parser.parse_args()

    if args.dry_run:
        args.conversations = 10
        args.personas = 5
        logger.info("DRY RUN: generating only 10 conversations with 5 personas")

    generator = SyntheticBenchmarkGenerator(
        output_dir=args.output,
        num_conversations=args.conversations,
        num_personas=args.personas,
        queries_per_batch=args.queries_per_batch,
        conversations_per_llm_call=args.conversations_per_call,
        resume=args.resume,
        seed=args.seed,
    )

    stats = asyncio.run(generator.run())

    # Generate README
    generate_readme(Path(args.output), stats)
    logger.info("README.md generated at %s", Path(args.output) / "README.md")


if __name__ == "__main__":
    main()
