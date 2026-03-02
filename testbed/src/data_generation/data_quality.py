"""
Data Quality Report Module

Generates quality reports for generated memory data, including
category distribution, entity density, and other statistics.
"""

import numpy as np
from typing import List, Dict, Any
from dataclasses import dataclass
from collections import Counter
import json
from pathlib import Path
from datetime import datetime

from .memory_generator import Memory, MemoryCategory, Entity


@dataclass
class QualityMetrics:
    """Quality metrics for generated data"""
    total_memories: int
    total_chunks: int
    avg_chunk_size: float
    avg_entities_per_chunk: float
    category_distribution: Dict[str, int]
    entity_type_distribution: Dict[str, int]
    source_type_distribution: Dict[str, int]
    date_range: Dict[str, str]
    unique_entities: Dict[str, int]
    entity_density: Dict[str, float]


class DataQualityReporter:
    """Generates quality reports for memory data"""

    def __init__(self, memories: List[Memory]):
        self.memories = memories

    def generate_report(self) -> QualityMetrics:
        """Generate comprehensive quality report"""

        # Basic counts
        total_memories = len(self.memories)
        total_chunks = sum(m.chunk_index + 1 for m in self.memories)

        # Chunk sizes
        chunk_sizes = [len(m.content) for m in self.memories]
        avg_chunk_size = np.mean(chunk_sizes)

        # Entity counts
        entity_counts = [len(m.entities) for m in self.memories]
        avg_entities_per_chunk = np.mean(entity_counts)

        # Category distribution
        category_counts = Counter(m.category.value for m in self.memories)

        # Entity type distribution
        entity_types = Counter()
        for memory in self.memories:
            for entity in memory.entities:
                entity_types[entity.entity_type] += 1

        # Source type distribution
        source_counts = Counter(m.source_type.value for m in self.memories)

        # Date range
        dates = [m.created_at for m in self.memories]
        date_range = {
            "earliest": min(dates).isoformat(),
            "latest": max(dates).isoformat()
        }

        # Unique entities by type
        unique_entities = {}
        for entity_type in entity_types.keys():
            values = set()
            for memory in self.memories:
                for entity in memory.entities:
                    if entity.entity_type == entity_type:
                        values.add(entity.value.lower())
            unique_entities[entity_type] = len(values)

        # Entity density (entities per 1000 characters)
        entity_density = {}
        for entity_type in entity_types.keys():
            total_chars = sum(len(m.content) for m in self.memories)
            count = entity_types[entity_type]
            entity_density[entity_type] = (count / total_chars) * 1000

        return QualityMetrics(
            total_memories=total_memories,
            total_chunks=total_chunks,
            avg_chunk_size=avg_chunk_size,
            avg_entities_per_chunk=avg_entities_per_chunk,
            category_distribution=dict(category_counts),
            entity_type_distribution=dict(entity_types),
            source_type_distribution=dict(source_counts),
            date_range=date_range,
            unique_entities=unique_entities,
            entity_density=entity_density
        )

    def print_report(self, metrics: QualityMetrics):
        """Print formatted report to console"""
        print("=" * 60)
        print("MEMORY DATA QUALITY REPORT")
        print("=" * 60)

        print(f"\nTotal Memories: {metrics.total_memories}")
        print(f"Total Chunks: {metrics.total_chunks}")
        print(f"Avg Chunk Size: {metrics.avg_chunk_size:.0f} characters")
        print(f"Avg Entities per Chunk: {metrics.avg_entities_per_chunk:.2f}")

        print("\n" + "-" * 40)
        print("CATEGORY DISTRIBUTION")
        print("-" * 40)
        for category, count in sorted(
            metrics.category_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (count / metrics.total_memories) * 100
            print(f"  {category:30s}: {count:4d} ({pct:5.1f}%)")

        print("\n" + "-" * 40)
        print("ENTITY TYPE DISTRIBUTION")
        print("-" * 40)
        for entity_type, count in sorted(
            metrics.entity_type_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            unique = metrics.unique_entities.get(entity_type, 0)
            density = metrics.entity_density.get(entity_type, 0)
            print(f"  {entity_type:15s}: {count:5d} total, {unique:4d} unique ({density:.2f} per 1k chars)")

        print("\n" + "-" * 40)
        print("SOURCE TYPE DISTRIBUTION")
        print("-" * 40)
        for source_type, count in sorted(
            metrics.source_type_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (count / metrics.total_memories) * 100
            print(f"  {source_type:20s}: {count:4d} ({pct:5.1f}%)")

        print("\n" + "-" * 40)
        print("DATE RANGE")
        print("-" * 40)
        print(f"  Earliest: {metrics.date_range['earliest']}")
        print(f"  Latest:   {metrics.date_range['latest']}")

        print("\n" + "=" * 60)

    def save_report(self, metrics: QualityMetrics, output_path: Path):
        """Save report to JSON file"""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "summary": {
                "total_memories": metrics.total_memories,
                "total_chunks": metrics.total_chunks,
                "avg_chunk_size": metrics.avg_chunk_size,
                "avg_entities_per_chunk": metrics.avg_entities_per_chunk
            },
            "category_distribution": metrics.category_distribution,
            "entity_type_distribution": metrics.entity_type_distribution,
            "source_type_distribution": metrics.source_type_distribution,
            "date_range": metrics.date_range,
            "unique_entities": metrics.unique_entities,
            "entity_density": metrics.entity_density
        }

        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2)

        print(f"\nReport saved to: {output_path}")

    def generate_markdown_report(self, metrics: QualityMetrics) -> str:
        """Generate markdown formatted report"""
        lines = [
            "# Memory Data Quality Report",
            "",
            "## Summary",
            "",
            f"- **Total Memories:** {metrics.total_memories:,}",
            f"- **Total Chunks:** {metrics.total_chunks:,}",
            f"- **Average Chunk Size:** {metrics.avg_chunk_size:.0f} characters",
            f"- **Average Entities per Chunk:** {metrics.avg_entities_per_chunk:.2f}",
            "",
            "## Category Distribution",
            "",
            "| Category | Count | Percentage |",
            "|----------|-------|------------|"
        ]

        for category, count in sorted(
            metrics.category_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (count / metrics.total_memories) * 100
            lines.append(f"| {category} | {count} | {pct:.1f}% |")

        lines.extend([
            "",
            "## Entity Type Distribution",
            "",
            "| Entity Type | Total | Unique | Density (per 1k chars) |",
            "|-------------|-------|--------|------------------------|"
        ])

        for entity_type in sorted(metrics.entity_type_distribution.keys()):
            count = metrics.entity_type_distribution[entity_type]
            unique = metrics.unique_entities.get(entity_type, 0)
            density = metrics.entity_density.get(entity_type, 0)
            lines.append(f"| {entity_type} | {count} | {unique} | {density:.2f} |")

        lines.extend([
            "",
            "## Source Type Distribution",
            "",
            "| Source Type | Count | Percentage |",
            "|-------------|-------|------------|"
        ])

        for source_type, count in sorted(
            metrics.source_type_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = (count / metrics.total_memories) * 100
            lines.append(f"| {source_type} | {count} | {pct:.1f}% |")

        lines.extend([
            "",
            "## Date Range",
            "",
            f"- **Earliest:** {metrics.date_range['earliest']}",
            f"- **Latest:** {metrics.date_range['latest']}",
            "",
            f"*Generated by TotalReclaw Testbed Data Quality Reporter*"
        ])

        return "\n".join(lines)


def validate_memories(memories: List[Memory]) -> List[str]:
    """
    Validate memories and return list of issues

    Returns:
        List of validation issue descriptions
    """
    issues = []

    # Check for empty content
    empty_count = sum(1 for m in memories if not m.content.strip())
    if empty_count > 0:
        issues.append(f"Found {empty_count} memories with empty content")

    # Check for duplicates (by content hash)
    import hashlib
    content_hashes = {}
    for memory in memories:
        h = hashlib.md5(memory.content.encode()).hexdigest()
        if h in content_hashes:
            issues.append(f"Duplicate content found: {memory.id} matches {content_hashes[h]}")
        else:
            content_hashes[h] = memory.id

    # Check for missing embeddings (if expected)
    missing_embeddings = sum(1 for m in memories if m.embedding is None)
    if missing_embeddings > 0:
        issues.append(f"{missing_embeddings} memories missing embeddings")

    # Check for unusual chunk sizes
    sizes = [len(m.content) for m in memories]
    median_size = np.median(sizes)
    outliers = [m for m in memories if len(m.content) < median_size * 0.1 or len(m.content) > median_size * 10]
    if outliers:
        issues.append(f"Found {len(outliers)} chunks with unusual sizes")

    return issues


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Generate data quality report")
    parser.add_argument("--input", "-i", required=True, help="Input JSON file with memories")
    parser.add_argument("--output", "-o", help="Output file for report")
    parser.add_argument("--format", "-f", choices=["json", "markdown", "both"], default="both")

    args = parser.parse_args()

    # Load memories
    with open(args.input) as f:
        data = json.load(f)

    # Reconstruct Memory objects
    memories = []
    for m_data in data["memories"]:
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
            entities=entities
        )
        memories.append(memory)

    # Generate report
    reporter = DataQualityReporter(memories)
    metrics = reporter.generate_report()

    # Print to console
    reporter.print_report(metrics)

    # Save report
    if args.output or args.format != "both":
        if args.format in ["json", "both"]:
            output_path = args.output or "quality_report.json"
            reporter.save_report(metrics, Path(output_path))

        if args.format in ["markdown", "both"]:
            md_path = args.output or "quality_report.md"
            if args.format == "both":
                md_path = str(Path(md_path).with_suffix(".md"))
            with open(md_path, 'w') as f:
                f.write(reporter.generate_markdown_report(metrics))
            print(f"\nMarkdown report saved to: {md_path}")
