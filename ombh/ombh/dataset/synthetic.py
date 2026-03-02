"""Synthetic conversation generator for OMBH."""

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Persona:
    """Synthetic user persona."""
    name: str
    role: str
    preferences: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    communication_style: str = "casual"


PERSONAS = [
    Persona(
        name="Alex Chen",
        role="Senior Software Engineer",
        preferences=[
            "prefers TypeScript over JavaScript",
            "likes dark mode themes",
            "uses VSCode as primary editor",
            "prefers functional programming",
            "dislikes pineapple on pizza",
        ],
        tech_stack=["TypeScript", "React", "Node.js", "PostgreSQL"],
        communication_style="technical",
    ),
    Persona(
        name="Jordan Smith",
        role="Full-Stack Developer",
        preferences=[
            "prefers Python for backend",
            "uses vim keybindings",
            "likes minimal UI design",
            "prefers async/await over promises",
        ],
        tech_stack=["Python", "FastAPI", "Vue.js", "MongoDB"],
        communication_style="casual",
    ),
]


class SyntheticGenerator:
    """Generate synthetic OpenClaw-style conversations."""

    def __init__(
        self,
        seed: int = 42,
        model: str = "claude-3-5-sonnet-20241022",
    ):
        self.seed = seed
        self.model = model
        random.seed(seed)

    def generate_conversation(
        self,
        conversation_id: str,
        num_sessions: int = 5,
        turns_per_session: int = 20,
        persona: Optional[Persona] = None,
    ) -> Dict[str, Any]:
        """Generate a single multi-session conversation."""
        if persona is None:
            persona = random.choice(PERSONAS)

        sessions = []
        base_time = datetime.now() - timedelta(days=num_sessions * 2)

        for i in range(num_sessions):
            session = self._generate_session(
                session_id=f"{conversation_id}_sess_{i}",
                num_turns=turns_per_session,
                start_time=base_time + timedelta(days=i * 2),
                persona=persona,
                pre_compaction=(i > 0 and i % 2 == 0),  # Every other session
            )
            sessions.append(session)

        ground_truth = self._generate_ground_truth(persona, sessions)

        return {
            "conversation_id": conversation_id,
            "persona": {
                "name": persona.name,
                "role": persona.role,
                "preferences": persona.preferences,
                "tech_stack": persona.tech_stack,
            },
            "sessions": sessions,
            "ground_truth_queries": ground_truth,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator_seed": self.seed,
            },
        }

    def _generate_session(
        self,
        session_id: str,
        num_turns: int,
        start_time: datetime,
        persona: Persona,
        pre_compaction: bool,
    ) -> Dict[str, Any]:
        """Generate a single session."""
        turns = []
        current_time = start_time

        for i in range(num_turns):
            # Alternate user/assistant
            if i % 2 == 0:
                role = "user"
                content = self._generate_user_turn(persona, i, turns)
            else:
                role = "assistant"
                content = self._generate_assistant_turn(persona, i, turns)

            turns.append({
                "role": role,
                "content": content,
                "timestamp": current_time.isoformat(),
            })
            current_time += timedelta(minutes=random.randint(1, 5))

        return {
            "session_id": session_id,
            "turns": turns,
            "pre_compaction_moment": pre_compaction,
            "start_time": start_time.isoformat(),
        }

    def _generate_user_turn(
        self,
        persona: Persona,
        turn_index: int,
        previous_turns: List[Dict],
    ) -> str:
        """Generate a user message."""
        # TODO: Use LLM for realistic generation
        templates = [
            "Can you help me with {tech}?",
            "I'm thinking about {topic}. What do you think?",
            "Remember that I {preference}.",
            "Let's work on {task}.",
            "I need to {action}.",
        ]

        tech = random.choice(persona.tech_stack)
        preference = random.choice(persona.preferences) if persona.preferences else "code cleanly"
        topic = random.choice(["architecture", "testing", "deployment", "refactoring"])
        task = random.choice(["fixing a bug", "adding a feature", "optimizing performance"])
        action = random.choice(["review this code", "debug this issue", "implement this"])

        return random.choice(templates).format(
            tech=tech,
            preference=preference,
            topic=topic,
            task=task,
            action=action,
        )

    def _generate_assistant_turn(
        self,
        persona: Persona,
        turn_index: int,
        previous_turns: List[Dict],
    ) -> str:
        """Generate an assistant response."""
        # TODO: Use LLM for realistic generation
        if previous_turns:
            last_user = previous_turns[-1]["content"]
            return f"I'd be happy to help with that. Let me think about {last_user[:30]}..."

        return "Hello! How can I assist you today?"

    def _generate_ground_truth(
        self,
        persona: Persona,
        sessions: List[Dict],
    ) -> List[Dict[str, Any]]:
        """Generate ground truth queries for evaluation."""
        queries = []

        # Preference-based queries
        for pref in persona.preferences[:3]:
            queries.append({
                "query": f"What are my preferences about {pref.split()[1]}?",
                "expected_facts": [pref],
                "ideal_answer": f"Based on our conversations, you {pref}.",
            })

        # Temporal queries
        queries.append({
            "query": "What did we work on in the first session?",
            "expected_facts": [],
            "ideal_answer": "We discussed your initial project setup.",
        })

        return queries

    def generate_batch(
        self,
        num_conversations: int,
        output_path: Path,
    ) -> None:
        """Generate and save multiple conversations."""
        with open(output_path, "w") as f:
            for i in range(num_conversations):
                conv = self.generate_conversation(
                    conversation_id=f"synth_{i:04d}",
                    num_sessions=random.randint(3, 7),
                    turns_per_session=random.randint(15, 30),
                )
                f.write(json.dumps(conv) + "\n")

        print(f"Generated {num_conversations} conversations to {output_path}")
