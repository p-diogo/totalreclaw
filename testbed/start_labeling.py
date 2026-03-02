#!/usr/bin/env python3
"""
Start the web-based labeling interface with TotalReclaw data.
"""

import sys
import json
import os

# Add src to path
sys.path.insert(0, 'src')

from src.labeling.interface import LabelingInterface

# Load memories
with open('../data/processed/memories_1500_final.json', 'r') as f:
    data = json.load(f)
    memories = data['memories']

# Create documents dict: id -> content
documents = {
    i: mem['content']
    for i, mem in enumerate(memories)
}

# Load queries
with open('data/queries/test_queries.json', 'r') as f:
    queries = json.load(f)

print(f"Loaded {len(documents)} documents")
print(f"Loaded {len(queries)} queries")

# Create interface
interface = LabelingInterface(
    queries=queries,
    documents=documents,
    evaluator_ids=['eval1', 'eval2', 'eval3'],
    labels_per_query=20,
    output_dir='data/ground_truth'
)

print("\n" + "="*60)
print("Starting labeling interface...")
print("="*60)
print("\nOpen http://localhost:5000 in your browser")
print("Select an evaluator ID (eval1, eval2, or eval3)")
print("\nLabeling task:")
print(f"  - {len(queries)} queries")
print(f"  - {20} documents per query")
print(f"  - Total: {len(queries) * 20} labels per evaluator")
print("\nPress Ctrl+C to stop the server")
print("="*60 + "\n")

interface.run(host='127.0.0.1', port=5000, debug=False)
