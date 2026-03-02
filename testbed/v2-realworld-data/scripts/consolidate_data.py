#!/usr/bin/env python3
"""
Data Consolidation Script
Merges all parsed data sources into a unified memory corpus.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from collections import defaultdict


class DataConsolidator:
    """Consolidates parsed data from multiple sources."""

    def __init__(self, processed_path: str, output_path: str):
        self.processed_path = Path(processed_path)
        self.output_path = Path(output_path)
        self.all_memories = []
        self.stats = defaultdict(int)

    def load_source(self, source_file: Path) -> List[Dict]:
        """Load memories from a source file."""
        memories = []

        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                memories = data
            elif isinstance(data, dict):
                memories = data.get('memories', [])

            print(f"  Loaded {len(memories)} memories from {source_file.name}")
            self.stats[source_file.stem] = len(memories)

        except Exception as e:
            print(f"  Error loading {source_file}: {e}")

        return memories

    def merge_sources(self) -> None:
        """Merge all data sources into unified corpus."""
        print("Loading data sources...")

        # Source files
        source_files = {
            'whatsapp': self.processed_path / 'whatsapp_memories.json',
            'telegram': self.processed_path / 'telegram_memories.json',
            'gmail': self.processed_path / 'gmail_memories.json',
        }

        # Load each source
        for source_name, source_file in source_files.items():
            if source_file.exists():
                print(f"\n{source_name.upper()}:")
                memories = self.load_source(source_file)
                self.all_memories.extend(memories)
            else:
                print(f"\n{source_name.upper()}: File not found, skipping...")

        print(f"\nTotal memories loaded: {len(self.all_memories)}")

    def deduplicate(self) -> None:
        """Remove duplicate memories based on content hash."""
        print(f"\nDeduplicating {len(self.all_memories)} memories...")

        seen = set()
        unique_memories = []

        for memory in self.all_memories:
            # Create a unique key based on content and timestamp
            content = memory.get('content', '')
            timestamp = memory.get('timestamp', '')
            source = memory.get('source', '')

            key = f"{source}:{timestamp}:{hash(content)}"

            if key not in seen:
                seen.add(key)
                unique_memories.append(memory)

        removed = len(self.all_memories) - len(unique_memories)
        print(f"Removed {removed} duplicates")
        self.all_memories = unique_memories

    def sort_chronologically(self) -> None:
        """Sort memories by timestamp."""
        self.all_memories.sort(
            key=lambda m: m.get('timestamp', ''),
            reverse=True  # Newest first
        )

    def generate_statistics(self) -> Dict:
        """Generate statistics about the consolidated corpus."""
        stats = {
            'total_memories': len(self.all_memories),
            'sources': defaultdict(int),
            'date_range': {},
            'avg_content_length': 0,
        }

        timestamps = []
        content_lengths = []

        for memory in self.all_memories:
            source = memory.get('source', 'unknown')
            stats['sources'][source] += 1

            timestamp = memory.get('timestamp')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamps.append(dt)
                except:
                    pass

            content = memory.get('content', '')
            content_lengths.append(len(content))

        if timestamps:
            stats['date_range'] = {
                'earliest': min(timestamps).isoformat(),
                'latest': max(timestamps).isoformat(),
            }

        if content_lengths:
            stats['avg_content_length'] = sum(content_lengths) / len(content_lengths)

        return stats

    def save_consolidated(self) -> None:
        """Save the consolidated corpus."""
        self.output_path.mkdir(parents=True, exist_ok=True)

        output_file = self.output_path / 'consolidated_memories.json'

        output_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'version': '2.0',
                'statistics': self.generate_statistics(),
            },
            'memories': self.all_memories,
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"\nConsolidated corpus saved to {output_file}")

        # Print statistics
        stats = output_data['metadata']['statistics']
        print(f"\n=== Corpus Statistics ===")
        print(f"Total memories: {stats['total_memories']}")
        print(f"Sources:")
        for source, count in stats['sources'].items():
            print(f"  {source}: {count}")
        if stats['date_range']:
            print(f"Date range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")
        print(f"Average content length: {stats['avg_content_length']:.0f} characters")

    def run(self) -> None:
        """Run the consolidation pipeline."""
        print("=" * 50)
        print("Data Consolidation Pipeline")
        print("=" * 50)

        self.merge_sources()
        self.deduplicate()
        self.sort_chronologically()
        self.save_consolidated()

        print("\n" + "=" * 50)
        print("Consolidation complete!")
        print("=" * 50)


def main():
    if len(sys.argv) < 3:
        print("Usage: consolidate_data.py <processed_path> <output_path>")
        print("Example: consolidate_data.py processed/ output/")
        sys.exit(1)

    processed_path = sys.argv[1]
    output_path = sys.argv[2]

    consolidator = DataConsolidator(processed_path, output_path)
    consolidator.run()


if __name__ == '__main__':
    main()
