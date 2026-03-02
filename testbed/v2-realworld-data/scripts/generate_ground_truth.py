#!/usr/bin/env python3
"""
Ground Truth Generation Script
Generates query-document relevance pairs for evaluation using LLM.
"""

import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests


class GroundTruthGenerator:
    """Generates ground truth data for evaluation."""

    def __init__(self, memories_file: str, output_file: str, api_key: str):
        self.memories_file = Path(memories_file)
        self.output_file = Path(output_file)
        self.api_key = api_key
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "arcee-ai/trinity-large-preview:free"
        self.memories = []
        self.queries = []

    def load_memories(self) -> None:
        """Load consolidated memories."""
        print(f"Loading memories from {self.memories_file}")

        with open(self.memories_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.memories = data.get('memories', [])
        print(f"Loaded {len(self.memories)} memories")

    def call_llm(self, prompt: str, max_tokens: int = 2000) -> str:
        """Call OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that generates search queries and identifies relevant documents. Always respond with valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except Exception as e:
            print(f"LLM API error: {e}")
            return ""

    def generate_sample_queries(self, num_queries: int = 20) -> List[Dict]:
        """Generate sample queries based on memory content (template-based)."""
        print(f"\nGenerating {num_queries} sample queries (template-based)...")

        # Sample diverse memories
        sample_size = min(num_queries * 5, len(self.memories))
        sampled_memories = random.sample(self.memories, sample_size)

        query_templates = [
            "What did {source} say about {topic}?",
            "When was the last time we discussed {topic}?",
            "Who mentioned {topic} in {chat}?",
            "Show me conversations about {topic}",
            "What happened on {date}?",
            "Tell me about {source}'s message",
        ]

        queries = []
        for i, memory in enumerate(sampled_memories[:num_queries]):
            content = memory.get('content', '')
            source = memory.get('source', 'unknown')
            chat_name = memory.get('chat_name', '')

            # Extract a potential topic (first few words)
            words = content.split()[:5]
            topic = ' '.join(words) if words else 'that'

            query = {
                'id': f"q{i+1}",
                'text': f"What was discussed about {topic}?",
                'type': random.choice(['factual', 'temporal', 'summarization']),
                'relevant_docs': [
                    {
                        'memory_id': memory['id'],
                        'relevance': 1.0
                    }
                ],
                'metadata': {
                    'source_memory': memory['id'],
                    'generated_from': 'template'
                }
            }
            queries.append(query)

        return queries

    def generate_llm_queries(self, num_queries: int = 50) -> List[Dict]:
        """Generate diverse queries using LLM with relevance judgments."""
        print(f"\nGenerating {num_queries} diverse queries using LLM...")

        # Sample diverse memories for context
        sample_size = min(100, len(self.memories))
        sampled_memories = random.sample(self.memories, sample_size)

        queries = []
        query_id = 0

        # Categories for diverse queries
        categories = [
            "factual",
            "temporal",
            "semantic",
            "keyword",
            "person-based",
            "event-based"
        ]

        # Process memories in batches for LLM
        batch_size = 10
        for i in range(0, len(sampled_memories), batch_size):
            batch = sampled_memories[i:i+batch_size]

            # Create prompt for query generation
            memories_text = "\n\n".join([
                f"Memory {j+1} (ID: {m['id']}):\n{m.get('content', '')[:500]}"
                for j, m in enumerate(batch)
            ])

            category = categories[i // batch_size % len(categories)]

            prompt = f"""Based on these WhatsApp memories, generate {min(5, num_queries - query_id)} diverse natural search queries.

Category: {category}

Memories:
{memories_text}

For each query, also identify which memory IDs are relevant (relevance score 0-1).

Respond in this JSON format:
{{
  "queries": [
    {{
      "text": "natural search question",
      "type": "factual|temporal|semantic|keyword",
      "relevant_docs": [
        {{"memory_id": "ID", "relevance": 0.9}}
      ]
    }}
  ]
}}

Generate queries that:
1. Are natural and realistic (like what a user would ask)
2. Cover different aspects of the conversations
3. Have clear relevance to specific memories
4. Include different query types"""

            response = self.call_llm(prompt, max_tokens=1500)

            if response:
                try:
                    # Try to parse JSON response
                    # Handle potential markdown code blocks
                    if "```json" in response:
                        response = response.split("```json")[1].split("```")[0].strip()
                    elif "```" in response:
                        response = response.split("```")[1].split("```")[0].strip()

                    result = json.loads(response)

                    for q in result.get('queries', []):
                        if query_id >= num_queries:
                            break

                        # Validate and add query
                        if q.get('text') and q.get('relevant_docs'):
                            query_obj = {
                                'id': f"q{query_id + 1}",
                                'text': q['text'],
                                'type': q.get('type', 'semantic'),
                                'relevant_docs': q.get('relevant_docs', []),
                                'metadata': {
                                    'generated_from': 'llm',
                                    'category': category
                                }
                            }
                            queries.append(query_obj)
                            query_id += 1

                except json.JSONDecodeError as e:
                    print(f"Failed to parse LLM response: {e}")
                    print(f"Response was: {response[:500]}")
                except Exception as e:
                    print(f"Error processing LLM response: {e}")

            if query_id >= num_queries:
                break

        print(f"Generated {len(queries)} queries")
        return queries

    def calculate_statistics(self) -> Dict:
        """Calculate ground truth statistics."""
        total_queries = len(self.queries)
        queries_with_relevant = sum(1 for q in self.queries if q.get('relevant_docs'))
        total_relevant = sum(len(q.get('relevant_docs', [])) for q in self.queries)

        coverage = (queries_with_relevant / total_queries * 100) if total_queries > 0 else 0

        return {
            'total_queries': total_queries,
            'queries_with_relevant_docs': queries_with_relevant,
            'coverage_percent': round(coverage, 2),
            'avg_relevant_docs': round(total_relevant / total_queries, 2) if total_queries > 0 else 0,
            'total_relevant_pairs': total_relevant,
        }

    def save_ground_truth(self) -> None:
        """Save ground truth to file."""
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        output_data = {
            'metadata': {
                'version': '2.0',
                'created': datetime.now().isoformat(),
                'method': 'llm',
                'model': self.model,
                'description': 'Ground truth for v2 testbed evaluation',
                'num_memories': len(self.memories)
            },
            'queries': self.queries,
            'statistics': self.calculate_statistics(),
        }

        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"\nGround truth saved to {self.output_file}")
        stats = output_data['statistics']
        print(f"Total queries: {stats['total_queries']}")
        print(f"Queries with relevant docs: {stats['queries_with_relevant_docs']}")
        print(f"Coverage: {stats['coverage_percent']}%")
        print(f"Avg relevant docs per query: {stats['avg_relevant_docs']}")

    def run(self, method: str = 'llm', num_queries: int = 50) -> None:
        """Run the ground truth generation."""
        print("=" * 50)
        print("Ground Truth Generation")
        print("=" * 50)

        self.load_memories()

        if method == 'template':
            self.queries = self.generate_sample_queries(num_queries)
        elif method == 'llm':
            self.queries = self.generate_llm_queries(num_queries)
        else:
            raise ValueError(f"Unknown method: {method}")

        self.save_ground_truth()

        print("\n" + "=" * 50)
        print("Ground truth generation complete!")
        print("=" * 50)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate ground truth for evaluation')
    parser.add_argument('memories_file', help='Path to consolidated memories JSON')
    parser.add_argument('output_file', help='Path to output ground truth JSON')
    parser.add_argument('--method', choices=['template', 'llm'], default='llm',
                        help='Query generation method')
    parser.add_argument('--num-queries', type=int, default=50,
                        help='Number of queries to generate')
    parser.add_argument('--api-key', help='OpenRouter API key (or set OPENROUTER_API_KEY env var)')

    args = parser.parse_args()

    # Get API key from argument or environment
    api_key = args.api_key or os.environ.get('OPENROUTER_API_KEY')
    if not api_key and args.method == 'llm':
        print("Warning: No API key provided, falling back to template method")
        args.method = 'template'

    generator = GroundTruthGenerator(args.memories_file, args.output_file, api_key or "")
    generator.run(method=args.method, num_queries=args.num_queries)


if __name__ == '__main__':
    main()
