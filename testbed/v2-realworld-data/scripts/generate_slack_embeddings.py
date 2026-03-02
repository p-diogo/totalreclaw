#!/usr/bin/env python3
"""
Slack Embedding Generation Script
Generates embeddings for Slack memories with proper field mapping.
"""

import json
import os
import sys
import time
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


class SlackEmbeddingGenerator:
    """Generates embeddings for Slack memory corpus."""

    def __init__(self, input_file: str, output_path: str, model_name: str = "all-MiniLM-L6-v2"):
        self.input_file = Path(input_file)
        self.output_path = Path(output_path)
        self.model_name = model_name
        self.model = None
        self.memories = []
        self.embeddings = None
        self.start_time = None

    def load_model(self) -> None:
        """Load the embedding model."""
        print(f"Loading embedding model: {self.model_name}")
        self.model = SentenceTransformer(self.model_name)
        print(f"Model loaded. Dimension: {self.model.get_sentence_embedding_dimension()}")

    def load_memories(self) -> None:
        """Load memories from Slack JSON file."""
        print(f"Loading memories from {self.input_file}")

        with open(self.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.memories = data.get('memories', [])
        print(f"Loaded {len(self.memories)} memories")

    def prepare_texts(self) -> List[str]:
        """Prepare text content for embedding with Slack-specific format."""
        print("Preparing texts for embedding...")

        texts = []
        for memory in self.memories:
            # Slack-specific field mapping
            source = memory.get('source', 'slack')
            channel_name = memory.get('channel_name', '')
            content = memory.get('content', '')

            # Format: [slack] channel_name: content
            if channel_name:
                text = f"[{source}] {channel_name}: {content}"
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
        """Save embeddings to disk with Slack-specific filenames."""
        self.output_path.mkdir(parents=True, exist_ok=True)

        # Save embeddings as numpy array
        embeddings_file = self.output_path / 'slack_embeddings.npy'
        np.save(embeddings_file, self.embeddings)
        print(f"Saved embeddings to {embeddings_file}")

        # Save metadata
        metadata_file = self.output_path / 'slack_embeddings_metadata.json'
        processing_time = time.time() - self.start_time
        metadata = {
            'model_name': self.model_name,
            'dimension': int(self.embeddings.shape[1]),
            'count': int(self.embeddings.shape[0]),
            'shape': list(self.embeddings.shape),
            'processing_time_seconds': round(processing_time, 2),
            'source_file': str(self.input_file.name),
        }

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        print(f"Saved metadata to {metadata_file}")

        # Save memory index (ID to position mapping)
        index_file = self.output_path / 'slack_memory_index.json'
        memory_index = {
            memory['id']: idx
            for idx, memory in enumerate(self.memories)
        }

        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(memory_index, f, indent=2)

        print(f"Saved memory index to {index_file}")

    def run(self) -> Dict:
        """Run the embedding generation pipeline and return statistics."""
        print("=" * 50)
        print("Slack Embedding Generation Pipeline")
        print("=" * 50)

        self.start_time = time.time()

        self.load_model()
        self.load_memories()
        texts = self.prepare_texts()
        self.generate_embeddings(texts)
        self.save_embeddings()

        processing_time = time.time() - self.start_time

        stats = {
            'total_embeddings': len(self.memories),
            'embedding_dimension': int(self.embeddings.shape[1]),
            'processing_time_seconds': round(processing_time, 2),
            'model_name': self.model_name,
        }

        print("\n" + "=" * 50)
        print("Embedding generation complete!")
        print(f"Total embeddings: {stats['total_embeddings']}")
        print(f"Embedding dimension: {stats['embedding_dimension']}")
        print(f"Processing time: {stats['processing_time_seconds']}s")
        print("=" * 50)

        return stats


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_slack_embeddings.py <input_json> <output_path> [model_name]")
        print("Example: generate_slack_embeddings.py processed/slack_memories.json processed/")
        sys.exit(1)

    input_file = sys.argv[1]
    output_path = sys.argv[2]
    model_name = sys.argv[3] if len(sys.argv) > 3 else "all-MiniLM-L6-v2"

    generator = SlackEmbeddingGenerator(input_file, output_path, model_name)
    stats = generator.run()

    # Return stats for further processing
    return stats


if __name__ == '__main__':
    main()
