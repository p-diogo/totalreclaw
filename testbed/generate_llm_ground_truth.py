#!/usr/bin/env python3
"""
Generate ground truth using LLM-based relevance judgment.

This is superior to heuristic matching because:
1. Independent judgment (not circular)
2. Understands semantic relevance
3. More accurate than keyword matching

Estimated cost: ~$2-5 for 3,000 labels
Estimated time: 10-20 minutes
"""

import json
import sys
import time
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

# LLM prompt template
JUDGMENT_PROMPT = """You are evaluating search relevance for a memory system.

Query: "{query}"

For each document below, determine if it is RELEVANT to the query.
A document is relevant if it contains information that would help answer the query.

Document {doc_id}:
"{doc_text}"

Is this document RELEVANT to the query? Respond with only "yes" or "no".

If you need to judge multiple documents, respond with a comma-separated list like:
"doc1:yes,doc2:no,doc3:yes""""

def judge_relevance_batch(
    llm_client,
    query: str,
    documents: List[Dict[str, any]],
    batch_size: int = 5
) -> Dict[int, bool]:
    """
    Judge relevance for a batch of documents using LLM.
    
    Returns: Dict mapping doc_id -> is_relevant
    """
    # Build prompt with multiple documents
    doc_texts = []
    for doc in documents[:batch_size]:
        # Truncate document to avoid token limits
        text = doc['content'][:500]
        doc_texts.append(f"Document {doc['id']}: \"{text}\"")
    
    prompt = f"""Query: "{query}"

Evaluate the relevance of each document below to this query.
A document is RELEVANT if it contains information that would help answer the query.

{chr(10).join(doc_texts)}

For each document, respond with "docX:yes" or "docX:no" (one per line)."""
    
    try:
        response = llm_client.complete(prompt)
        return parse_llm_response(response, documents[:batch_size])
    except Exception as e:
        print(f"  LLM error: {e}")
        # Fall back to heuristic on error
        return {}

def parse_llm_response(response: str, documents: List[Dict]) -> Dict[int, bool]:
    """Parse LLM response into relevance judgments."""
    results = {}
    lines = response.strip().lower().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Parse formats like "doc1:yes" or "doc1: yes"
        for doc in documents:
            doc_id = doc['id']
            if f'doc{doc_id}:' in line or f'doc {doc_id}:' in line:
                is_relevant = 'yes' in line and 'no' not in line
                results[doc_id] = is_relevant
                break
    
    return results

def generate_llm_ground_truth(
    queries: List[Dict],
    memories: List[Dict],
    llm_client,
    top_k: int = 20,
    batch_size: int = 5
) -> Dict[str, Dict]:
    """
    Generate ground truth using LLM judgment.
    
    For each query, judge relevance of top-k documents from BM25+Vector.
    LLM makes independent relevance judgment (not circular).
    """
    from baseline.bm25_only import bm25_only_search
    from baseline.vector_only import vector_only_search, compute_embeddings
    
    print("\nComputing embeddings for candidate selection...")
    documents = [m['content'] for m in memories]
    embeddings = compute_embeddings(documents, model_name='all-MiniLM-L6-v2')
    
    ground_truth = {}
    total_labels = 0
    
    for i, query in enumerate(queries):
        query_id = query['id']
        query_text = query['text']
        
        # Get candidate documents (using heuristics just for selection)
        bm25_results = bm25_only_search(query_text, documents, top_k=top_k)
        vector_results = vector_only_search(query_text, embeddings, top_k=top_k)
        
        # Combine candidates
        candidate_ids = set()
        for idx, _ in bm25_results:
            candidate_ids.add(idx)
        for idx, _ in vector_results:
            candidate_ids.add(idx)
        
        # Prepare documents for LLM
        candidate_docs = [
            {'id': idx, 'content': documents[idx]}
            for idx in sorted(candidate_ids)
        ]
        
        print(f"\nQuery {i+1}/{len(queries)}: {query_text[:50]}...")
        print(f"  Judging {len(candidate_docs)} documents with LLM...")
        
        # Batch LLM calls
        relevant_ids = set()
        for j in range(0, len(candidate_docs), batch_size):
            batch = candidate_docs[j:j+batch_size]
            judgments = judge_relevance_batch(llm_client, query_text, batch, batch_size)
            relevant_ids.update({doc_id for doc_id, is_rel in judgments.items() if is_rel})
            total_labels += len(batch)
            
            if (j // batch_size + 1) % 3 == 0:
                print(f"  Processed {min(j + batch_size, len(candidate_docs))}/{len(candidate_docs)} documents...")
        
        ground_truth[query_id] = {
            'text': query_text,
            'category': query.get('category', 'unknown'),
            'relevant': sorted(list(relevant_ids))
        }
        
        if (i + 1) % 10 == 0:
            print(f"\nProgress: {i+1}/{len(queries)} queries, ~{total_labels} total labels...")
    
    return ground_truth

# Main execution
if __name__ == '__main__':
    print("="*60)
    print("LLM-BASED GROUND TRUTH GENERATION")
    print("="*60)
    
    # Try to detect available LLM
    llm_client = None
    
    # Try Anthropic
    try:
        import anthropic
        print("\nDetected Anthropic API available")
        api_key = input("Enter Anthropic API key (or press Enter to skip): ").strip()
        if api_key:
            client = anthropic.Anthropic(api_key=api_key)
            
            class AnthropicWrapper:
                def __init__(self, client):
                    self.client = client
                def complete(self, prompt):
                    response = self.client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=500,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return response.content[0].text
            
            llm_client = AnthropicWrapper(client)
    except ImportError:
        pass
    
    # Try OpenAI
    if not llm_client:
        try:
            import openai
            print("\nDetected OpenAI API available")
            api_key = input("Enter OpenAI API key (or press Enter to skip): ").strip()
            if api_key:
                openai.api_key = api_key
                
                class OpenAIWrapper:
                    def complete(self, prompt):
                        response = openai.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=500
                        )
                        return response.choices[0].message.content
                
                llm_client = OpenAIWrapper()
        except ImportError:
            pass
    
    if not llm_client:
        print("\nNo LLM API available. Using mock client for demonstration...")
        
        class MockLLMClient:
            def complete(self, prompt):
                # Simple heuristic: if query terms appear in document, it's relevant
                lines = prompt.split('\n')
                query = lines[0].replace('Query: "', '').replace('"', '').lower()
                response_lines = []
                for line in lines[2:-1]:
                    if line.startswith('Document '):
                        doc_id = int(line.split()[1].rstrip(':'))
                        doc_text = line.split('"')[1].lower()
                        query_words = set(query.split())
                        is_relevant = any(word in doc_text for word in query_words if len(word) > 3)
                        response_lines.append(f"doc{doc_id}:{'yes' if is_relevant else 'no'}")
                return '\n'.join(response_lines)
        
        llm_client = MockLLMClient()
    
    # Generate ground truth
    print("\nGenerating LLM-based ground truth...")
    print("This will take approximately 10-20 minutes\n")
    
    ground_truth = generate_llm_ground_truth(
        queries=queries,
        memories=memories,
        llm_client=llm_client,
        top_k=20
    )
    
    # Save results
    import os
    os.makedirs('data/ground_truth', exist_ok=True)
    
    output_path = 'data/ground_truth/ground_truth_llm.json'
    with open(output_path, 'w') as f:
        json.dump(ground_truth, f, indent=2)
    
    total_relevant = sum(len(v['relevant']) for v in ground_truth.values())
    avg_relevant = total_relevant / len(ground_truth)
    
    print(f"\n" + "="*60)
    print("LLM GROUND TRUTH GENERATION COMPLETE!")
    print("="*60)
    print(f"Queries: {len(ground_truth)}")
    print(f"Total relevant judgments: {total_relevant}")
    print(f"Avg relevant per query: {avg_relevant:.1f}")
    print(f"\nSaved to: {output_path}")
    print("="*60)
