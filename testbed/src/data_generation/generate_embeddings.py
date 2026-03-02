#!/usr/bin/env python3
"""
Generate embeddings for memory chunks

This script loads generated memories from JSON and computes
embeddings using all-MiniLM-L6-v2 (384-dimensional).
"""

import sys
import json
import numpy as np
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from search.vector import get_embedding_model
from data_generation.memory_generator import Memory, MemoryCategory, SourceType, Entity


def load_memories(json_path: str) -> list[Memory]:
    """Load memories from JSON file"""
    with open(json_path) as f:
        data = json.load(f)

    memories = []
    for m_data in data["memories"][:1500]:  # Limit to 1500
        entities = [
            Entity(
                entity_type=e["type"],
                value=e["value"],
                start_pos=e["start_pos"],
                end_pos=e["end_pos"]
            )
            for e in m_data.get("entities", [])
        ]

        memory = Memory(
            id=m_data["id"],
            content=m_data["content"],
            category=MemoryCategory(m_data["category"]),
            source_file=m_data["source_file"],
            source_type=m_data["source_type"],
            chunk_index=m_data["chunk_index"],
            total_chunks=m_data["total_chunks"],
            line_start=m_data["line_start"],
            line_end=m_data["line_end"],
            created_at=datetime.fromisoformat(m_data["created_at"]),
            entities=entities,
            embedding=np.array(m_data["embedding"]) if m_data.get("embedding") else None
        )
        memories.append(memory)

    return memories


def save_memories_with_embeddings(memories: list[Memory], output_path: str):
    """Save memories with embeddings to JSON"""
    data = {
        "memories": [m.to_dict() for m in memories],
        "total_count": len(memories),
        "generated_at": datetime.now().isoformat()
    }

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    from datetime import datetime

    input_path = "data/processed/memories.json"
    output_path = "data/processed/memories_with_embeddings.json"

    print("Loading memories...")
    memories = load_memories(input_path)
    print(f"Loaded {len(memories)} memories")

    print("\nInitializing embedding model...")
    model = get_embedding_model(model_type="sentence-transformer", use_cache=True)
    print(f"Model: all-MiniLM-L6-v2 (embedding_dim={model.embedding_dim})")

    print("\nGenerating embeddings...")
    texts = [m.content for m in memories]
    embeddings = model.encode_batch(texts, batch_size=32)

    print(f"Generated {len(embeddings)} embeddings of shape {embeddings.shape}")

    # Assign embeddings to memories
    for memory, embedding in zip(memories, embeddings):
        memory.embedding = embedding

    # Save with embeddings
    print(f"\nSaving memories with embeddings to {output_path}...")
    save_memories_with_embeddings(memories, output_path)

    # Statistics
    print("\nEmbedding Statistics:")
    print(f"  Shape: {embeddings.shape}")
    print(f"  Min value: {embeddings.min():.4f}")
    print(f"  Max value: {embeddings.max():.4f}")
    print(f"  Mean: {embeddings.mean():.4f}")
    print(f"  Std: {embeddings.std():.4f}")
    print(f"  Norm (should be ~1.0 for normalized): {np.linalg.norm(embeddings[0]):.4f}")

    print("\nDone!")
