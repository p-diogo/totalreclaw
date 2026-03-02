"""
Two-pass search implementation for OpenMemory v0.2

Pass 1 (Remote, Server-Side):
- Vector KNN search on embeddings
- Blind index matching for exact queries

Pass 2 (Local, Client-Side):
- Decrypt candidates
- BM25 keyword search
- RRF fusion
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Tuple
from collections import Counter
import math

import numpy as np


@dataclass
class SearchResult:
    """Search result with decrypted content"""
    content: str
    score: float
    vector_rank: int
    bm25_rank: int
    memory_id: str


@dataclass
class CandidateResult:
    """Pass 1 result from server (encrypted)"""
    memory_id: str
    ciphertext: bytes
    nonce: bytes
    vector_score: float
    is_blind_match: bool


class TwoPassSearch:
    """
    Implements two-pass hybrid search with RRF fusion.

    Pass 1: Remote vector search + blind index matching
    Pass 2: Local BM25 + RRF fusion
    """

    # RRF constant (higher = more forgiving of rank differences)
    RRF_K = 60

    # Candidate pool size for Pass 2
    CANDIDATE_POOL_SIZE = 250

    def __init__(self, decrypt_fn):
        """
        Initialize search with decryption function.

        Args:
            decrypt_fn: Function to decrypt (ciphertext, nonce) -> plaintext
        """
        self.decrypt = decrypt_fn

    def pass1_remote_search(
        self,
        query_vector: np.ndarray,
        blind_hashes: List[str],
        stored_embeddings: Dict[str, np.ndarray],
        stored_blind_indices: Dict[str, List[str]],
        candidate_pool_size: int = None
    ) -> List[Tuple[str, float, bool]]:
        """
        Pass 1: Remote vector search + blind index matching.

        This runs on the server side with encrypted data only.

        Args:
            query_vector: Query embedding vector
            blind_hashes: Blind indices from query
            stored_embeddings: Dict of memory_id -> embedding
            stored_blind_indices: Dict of memory_id -> blind indices
            candidate_pool_size: Max candidates to return

        Returns:
            List of (memory_id, vector_score, is_blind_match)
        """
        if candidate_pool_size is None:
            candidate_pool_size = self.CANDIDATE_POOL_SIZE

        # Calculate cosine similarities
        similarities = {}
        for memory_id, embedding in stored_embeddings.items():
            sim = self._cosine_similarity(query_vector, embedding)
            similarities[memory_id] = sim

        # Find blind index matches
        blind_matches = set()
        for memory_id, indices in stored_blind_indices.items():
            if any(hash_val in blind_hashes for hash_val in indices):
                blind_matches.add(memory_id)

        # Sort by similarity
        ranked = sorted(similarities.items(), key=lambda x: x[1], reverse=True)

        # Build candidate pool
        candidates = []
        blind_added = set()

        # First, add blind matches (they're prioritized)
        for memory_id, score in ranked:
            if memory_id in blind_matches and memory_id not in blind_added:
                candidates.append((memory_id, score, True))
                blind_added.add(memory_id)

        # Then fill remaining pool with top vector matches
        for memory_id, score in ranked:
            if len(candidates) >= candidate_pool_size:
                break
            if memory_id not in blind_added:
                candidates.append((memory_id, score, False))

        return candidates

    def pass2_local_rerank(
        self,
        candidates: List[Tuple[str, float, bool]],
        query: str,
        stored_memories: Dict[str, Tuple[bytes, bytes]],  # memory_id -> (ciphertext, nonce)
        top_k: int = 5
    ) -> List[SearchResult]:
        """
        Pass 2: Local BM25 + RRF fusion.

        This runs on the client side after decryption.

        Args:
            candidates: Results from Pass 1
            query: Original query text
            stored_memories: Dict of memory_id -> (ciphertext, nonce)
            top_k: Number of results to return

        Returns:
            List of SearchResult with final scores
        """
        # Decrypt all candidates
        decrypted = []
        for memory_id, vector_score, is_blind_match in candidates:
            ciphertext, nonce = stored_memories[memory_id]
            try:
                plaintext = self.decrypt(ciphertext, nonce)
                decrypted.append({
                    'id': memory_id,
                    'content': plaintext,
                    'vector_score': vector_score,
                    'is_blind_match': is_blind_match
                })
            except Exception as e:
                # Skip failed decryptions
                continue

        if not decrypted:
            return []

        # Tokenize for BM25
        tokenized_corpus = [
            self._tokenize(doc['content'].lower())
            for doc in decrypted
        ]
        tokenized_query = self._tokenize(query.lower())

        # Calculate BM25 scores
        bm25_scores = self._bm25_score(tokenized_query, tokenized_corpus)

        # RRF fusion
        results = []

        # Build ranking dictionaries
        # bm25_scores is a list of document indices in rank order
        bm25_rank_map = {doc_idx: rank + 1 for rank, doc_idx in enumerate(bm25_scores)}

        for idx, doc in enumerate(decrypted):
            memory_id = doc['id']
            vector_rank = idx + 1
            bm25_rank = bm25_rank_map.get(idx, len(bm25_scores) + 1)  # 1-indexed, with penalty for unranked

            # RRF formula: score = 1/(k + rank1) + 1/(k + rank2)
            rrf_score = (
                1 / (self.RRF_K + vector_rank) +
                1 / (self.RRF_K + bm25_rank)
            )

            # Boost blind matches
            if doc['is_blind_match']:
                rrf_score *= 1.5

            results.append(SearchResult(
                content=doc['content'],
                score=rrf_score,
                vector_rank=vector_rank,
                bm25_rank=bm25_rank,
                memory_id=memory_id
            ))

        # Sort by final score and return top-k
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return np.dot(vec1, vec2) / (norm1 * norm2)

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenization for BM25.

        Splits on whitespace and punctuation, removes empty tokens.
        """
        # Split on non-word characters
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens

    def _bm25_score(
        self,
        query_tokens: List[str],
        tokenized_corpus: List[List[str]],
        k1: float = 1.5,
        b: float = 0.75
    ) -> List[int]:
        """
        Calculate BM25 scores and return ranking (lower is better).

        Args:
            query_tokens: Tokenized query
            tokenized_corpus: Tokenized documents
            k1: BM25 parameter (term saturation)
            b: BM25 parameter (length normalization)

        Returns:
            List of document indices sorted by BM25 score (descending)
        """
        # Calculate IDF
        N = len(tokenized_corpus)
        doc_freqs = Counter()

        for doc in tokenized_corpus:
            unique_terms = set(doc)
            for term in unique_terms:
                doc_freqs[term] += 1

        # Calculate document lengths
        doc_lengths = [len(doc) for doc in tokenized_corpus]
        avg_doc_length = sum(doc_lengths) / N if N > 0 else 0

        # Calculate BM25 scores
        scores = []
        for doc_idx, doc in enumerate(tokenized_corpus):
            score = 0.0
            doc_length = doc_lengths[doc_idx]
            term_counts = Counter(doc)

            for term in query_tokens:
                if term not in term_counts:
                    continue

                # IDF
                df = doc_freqs.get(term, 0)
                if df == 0:
                    continue
                idf = math.log((N - df + 0.5) / (df + 0.5) + 1)

                # TF component
                tf = term_counts[term]
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_length / avg_doc_length))

                score += idf * (numerator / denominator)

            scores.append((doc_idx, score))

        # Return ranking (sorted by score, descending -> convert to ranks)
        scores.sort(key=lambda x: x[1], reverse=True)
        return [idx for idx, _ in scores]
