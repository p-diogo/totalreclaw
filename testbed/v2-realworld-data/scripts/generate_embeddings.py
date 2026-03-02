#!/usr/bin/env python3
"""
Embedding Generation Script
Generates embeddings for consolidated memory corpus.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import numpy as np
except ImportError:
    print("NumPy not found. Install with: pip install numpy")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("sentence-transformers not found. Install with: pip install sentence-transformers")
    sys.exit(1)


class EmbeddingGenerator:
    """Generates embeddings for memory corpus."""

    def __init__(self, input_file: str, output_path: str, model_name: str = "all-MiniLM-L6-v2"):
        self.input_file = Path(input_file)
        self.output_path = Path(output_path)
        self.model_name = model_name
        self.model = None
        self.memories = []
        self.embeddings = None

    def load_model(self) -> None:
        """Load the embedding model."""
        print(f"Loading embedding model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        print(f"Model loaded. Dimension: {self.model.get_sentence_embedding_dimension()}")

    def load_memories(self) -> None:
        """Load memories from consolidated file."""
        print(f"Loading memories from {self.input_file}")

        with open(self.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.memories = data.get('memories', [])
        print(f"Loaded {len(self.memories)} memories")

    def prepare_texts(self) -> List[str]:
        """Prepare text content for embedding."""
        print("Preparing texts for embedding...")

        texts = []
        for memory in self.memories:
            # Combine content with context for better embeddings
            source = memory.get('source', 'unknown')
            chat_name = memory.get('chat_name', memory.get('subject', ''))
            content = memory.get('content', '')

            # Format: [Source] Chat Name: Content
            if chat_name:
                text = f"[{source}] {chat_name}: {content}"
            else:
                text = f"[{source}]: {content}"

            texts.append(text)

        return texts

    def generate_embeddings(self, texts: List[str], batch_size: int = 32) -> None:
        """Generate embeddings for all texts."""
        print(f"Generating embeddings for {len(texts)} texts...")
        print(f"Batch size: {batch_size}")

        self.embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
        )

        print(f"Generated embeddings with shape: {self.embeddings.shape}")

    def save_embeddings(self) -> None:
        """Save embeddings to disk."""
        self.output_path.mkdir(parents=True, exist_ok=True)

        # Save embeddings as numpy array
        embeddings_file = self.output_path / 'embeddings.npy'
        np.save(embeddings_file, self.embeddings)
        print(f"Saved embeddings to {embeddings_file}")

        # Save metadata
        metadata_file = self.output_path / 'embeddings_metadata.json'
        metadata = {
            'model_name': self.model_name,
            'dimension': int(self.embeddings.shape[1]),
            'count': int(self.embeddings.shape[0]),
            'shape': list(self.embeddings.shape),
        }

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        print(f"Saved metadata to {metadata_file}")

        # Save memory index (ID to position mapping)
        index_file = self.output_path / 'memory_index.json'
        memory_index = {
            memory['id']: idx
            for idx, memory in enumerate(self.memories)
        }

        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(memory_index, f, indent=2)

        print(f"Saved memory index to {index_file}")

    def run(self) -> None:
        """Run the embedding generation pipeline."""
        print("=" * 50)
        print("Embedding Generation Pipeline")
        print("=" * 50)

        self.load_model()
        self.load_memories()
        texts = self.prepare_texts()
        self.generate_embeddings(texts)
        self.save_embeddings()

        print("\n" + "=" * 50)
        print("Embedding generation complete!")
        print("=" * 50)


class EmbeddingSearcher:
    """Search functionality using generated embeddings."""

    def __init__(self, embeddings_path: str, memories_path: str, model_name: str = "all-MiniLM-L6-v2"):
        self.embeddings_path = Path(embeddings_path)
        self.memories_path = Path(memories_path)
        self.model_name = model_name
        self.model = None
        self.embeddings = None
        self.memories = []

    def load(self) -> None:
        """Load embeddings and memories."""
        print(f"Loading model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)

        print(f"Loading embeddings from {self.embeddings_path}")
        self.embeddings = np.load(self.embeddings_path)
        print(f"Loaded embeddings with shape: {self.embeddings.shape}")

        print(f"Loading memories from {self.memories_path}")
        with open(self.memories_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.memories = data.get('memories', [])
        print(f"Loaded {len(self.memories)} memories")

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """Search for similar memories."""
        if self.embeddings is None or self.model is None:
            raise RuntimeError("Not loaded. Call load() first.")

        # Generate query embedding
        query_embedding = self.model.encode([query], convert_to_numpy=True)

        # Calculate similarities
        from sklearn.metrics.pairwise import cosine_similarity
        similarities = cosine_similarity(query_embedding, self.embeddings)[0]

        # Get top k results
        top_indices = similarities.argsort()[-top_k:][::-1]

        results = []
        for idx in top_indices:
            result = {
                'memory': self.memories[idx],
                'score': float(similarities[idx]),
                'rank': len(results) + 1,
            }
            results.append(result)

        return results


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_embeddings.py <input_json> <output_path> [model_name]")
        print("Example: generate_embeddings.py processed/consolidated_memories.json processed/")
        sys.exit(1)

    input_file = sys.argv[1]
    output_path = sys.argv[2]
    model_name = sys.argv[3] if len(sys.argv) > 3 else "all-MiniLM-L6-v2"

    generator = EmbeddingGenerator(input_file, output_path, model_name)
    generator.run()


if __name__ == '__main__':
    main()
