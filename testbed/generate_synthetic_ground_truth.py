#!/usr/bin/env python3
"""
Generate synthetic ground truth using heuristic matching.
"""

import json
import sys
import numpy as np
from collections import defaultdict

sys.path.insert(0, 'src')

from baseline.bm25_only import bm25_only_search
from baseline.vector_only import vector_only_search, compute_embeddings

# Load data
with open('data/processed/memories_1500_final.json', 'r') as f:
    data = json.load(f)
    memories = data['memories']

documents = [mem['content'] for mem in memories]
doc_ids = list(range(len(documents)))

with open('data/queries/test_queries.json', 'r') as f:
    queries = json.load(f)

print(f"Loaded {len(documents)} documents and {len(queries)} queries")

# Compute embeddings (this might take a minute)
print("\nComputing embeddings...")
embeddings = compute_embeddings(documents, model_name='all-MiniLM-L6-v2')

# Generate ground truth using heuristic matching
ground_truth = {}
top_k = 20  # Top 20 results per query = "relevant"

print(f"\nGenerating ground truth (top {top_k} per query)...")

for i, query in enumerate(queries):
    query_id = query['id']
    query_text = query['text']
    
    # Get BM25 and Vector results
    bm25_results = bm25_only_search(query_text, documents, top_k=top_k)
    vector_results = vector_only_search(query_text, embeddings, top_k=top_k)
    
    # Combine results: a document is "relevant" if it appears in either top-k
    relevant_ids = set()
    for idx, _ in bm25_results:
        relevant_ids.add(idx)
    for idx, _ in vector_results:
        relevant_ids.add(idx)
    
    ground_truth[query_id] = {
        'text': query_text,
        'category': query.get('category', 'unknown'),
        'relevant': sorted(list(relevant_ids))
    }
    
    if (i + 1) % 30 == 0:
        print(f"  Processed {i + 1}/{len(queries)} queries...")

# Save ground truth
output_path = 'data/ground_truth/ground_truth.json'
import os
os.makedirs('data/ground_truth', exist_ok=True)

with open(output_path, 'w') as f:
    json.dump(ground_truth, f, indent=2)

# Print summary
total_relevant = sum(len(v['relevant']) for v in ground_truth.values())
avg_relevant = total_relevant / len(ground_truth)

print(f"\n" + "="*60)
print("Ground truth generation complete!")
print("="*60)
print(f"Queries: {len(ground_truth)}")
print(f"Total relevant judgments: {total_relevant}")
print(f"Avg relevant per query: {avg_relevant:.1f}")
print(f"\nSaved to: {output_path}")
print("="*60)

# Category breakdown
category_counts = defaultdict(list)
for qid, data in ground_truth.items():
    category_counts[data['category']].append(len(data['relevant']))

print("\nRelevant documents by category:")
for cat, counts in sorted(category_counts.items()):
    avg = sum(counts) / len(counts)
    print(f"  {cat}: {len(counts)} queries, avg {avg:.1f} relevant/query")
