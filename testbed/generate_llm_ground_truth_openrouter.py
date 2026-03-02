#!/usr/bin/env python3
"""
Generate ground truth using LLM-based relevance judgment via OpenRouter.
Uses DeepSeek R1 0528 (free model).
"""

import json
import os
import sys
import time
import requests
from typing import List, Dict

sys.path.insert(0, 'src')

# Load data
print("Loading data...")
with open('data/processed/memories_1500_final.json', 'r') as f:
    data = json.load(f)
    memories = data['memories']

with open('data/queries/test_queries.json', 'r') as f:
    queries = json.load(f)

print(f"Loaded {len(memories)} documents and {len(queries)} queries")

class OpenRouterLLM:
    def __init__(self, api_key: str, model: str = "deepseek/deepseek-r1-0528:free"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
    
    def complete(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://totalreclaw.ai",
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }
        response = requests.post(self.base_url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        message = result['choices'][0]['message']
        # Handle reasoning models (like DeepSeek R1) that put content in 'reasoning' field
        content = message.get('content', '')
        reasoning = message.get('reasoning', '')
        # Return reasoning if content is empty (common for reasoning models), otherwise return content
        return reasoning if not content else content

def judge_relevance_batch(llm, query: str, documents: List[Dict], batch_size: int = 10) -> Dict[int, bool]:
    doc_descriptions = []
    for doc in documents[:batch_size]:
        text = doc['content'][:400].replace('\n', ' ')
        doc_descriptions.append(f"[{doc['id']}] {text}")
    
    prompt = f"""You are evaluating search relevance. For the query below, determine which documents are RELEVANT.

Query: "{query}"

Documents:
{chr(10).join(doc_descriptions)}

A document is RELEVANT if it contains information that would help answer the query.

Respond with the IDs of relevant documents in format: "id1, id2, id3" or "none" if none are relevant."""

    try:
        response = llm.complete(prompt)
        return parse_llm_response(response, documents[:batch_size])
    except Exception as e:
        print(f"  LLM error: {e}")
        return {}

def parse_llm_response(response: str, documents: List[Dict]) -> Dict[int, bool]:
    results = {}
    response_clean = response.strip().lower()
    if 'none' in response_clean or 'no relevant' in response_clean:
        return {doc['id']: False for doc in documents}
    for doc in documents:
        doc_id = doc['id']
        if str(doc_id) in response_clean or f"[{doc_id}]" in response_clean:
            results[doc_id] = True
        else:
            results[doc_id] = False
    return results

def generate_llm_ground_truth(queries: List[Dict], memories: List[Dict], llm, top_k: int = 20, batch_size: int = 10) -> Dict[str, Dict]:
    from baseline.bm25_only import bm25_only_search
    from baseline.vector_only import vector_only_search, compute_embeddings
    
    print("\nComputing embeddings for candidate selection...")
    documents = [mem['content'] for mem in memories]
    embeddings = compute_embeddings(documents, model_name='all-MiniLM-L6-v2')
    
    ground_truth = {}
    total_labels = 0
    
    for i, query in enumerate(queries):
        query_id = query['id']
        query_text = query['text']
        
        bm25_results = bm25_only_search(query_text, documents, top_k=top_k)
        vector_results = vector_only_search(query_text, embeddings, top_k=top_k)
        
        candidate_ids = set()
        for idx, _ in bm25_results:
            candidate_ids.add(idx)
        for idx, _ in vector_results:
            candidate_ids.add(idx)
        
        candidate_docs = [{'id': idx, 'content': documents[idx]} for idx in sorted(candidate_ids)]
        
        print(f"\n[{i+1}/{len(queries)}] {query_text[:50]}...")
        print(f"  Judging {len(candidate_docs)} documents with LLM ({llm.model})...")
        
        relevant_ids = set()
        for j in range(0, len(candidate_docs), batch_size):
            batch = candidate_docs[j:j+batch_size]
            judgments = judge_relevance_batch(llm, query_text, batch, batch_size)
            relevant_ids.update({doc_id for doc_id, is_rel in judgments.items() if is_rel})
            total_labels += len(batch)
            if (j // batch_size + 1) % 2 == 0:
                print(f"  Processed {min(j + batch_size, len(candidate_docs))}/{len(candidate_docs)} documents...")
        
        ground_truth[query_id] = {
            'text': query_text,
            'category': query.get('category', 'unknown'),
            'relevant': sorted(list(relevant_ids))
        }
        
        if (i + 1) % 5 == 0:
            print(f"\nProgress: {i+1}/{len(queries)} queries, ~{total_labels} total labels...")
    
    return ground_truth

# Main
if __name__ == '__main__':
    print("="*60)
    print("LLM-BASED GROUND TRUTH (OpenRouter + DeepSeek R1)")
    print("="*60)
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY environment variable not set.")
        print("Get your key from: https://openrouter.ai/keys")
        sys.exit(1)
    # Using non-reasoning model (Arcee Trinity) for fast, direct relevance judgments
    model = "arcee-ai/trinity-large-preview:free"

    print(f"Using model: {model}")

    llm = OpenRouterLLM(api_key, model)
    
    print("\nGenerating LLM-based ground truth...")
    print("Estimated time: 10-20 minutes\n")
    
    start_time = time.time()
    ground_truth = generate_llm_ground_truth(queries, memories, llm, top_k=20)
    elapsed = time.time() - start_time
    
    import os
    os.makedirs('data/ground_truth', exist_ok=True)
    
    output_path = 'data/ground_truth/ground_truth_llm.json'
    with open(output_path, 'w') as f:
        json.dump(ground_truth, f, indent=2)
    
    total_relevant = sum(len(v['relevant']) for v in ground_truth.values())
    avg_relevant = total_relevant / len(ground_truth)
    
    print(f"\n" + "="*60)
    print("LLM GROUND TRUTH COMPLETE!")
    print("="*60)
    print(f"Queries: {len(ground_truth)}")
    print(f"Total relevant judgments: {total_relevant}")
    print(f"Avg relevant per query: {avg_relevant:.1f}")
    print(f"Time: {elapsed/60:.1f} minutes")
    print(f"Saved to: {output_path}")
    print("="*60)
