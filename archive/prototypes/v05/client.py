"""
OpenMemoryClientV05 - Enhanced E2EE Client with Three-Pass Search

Extends v0.2 with:
- Multi-variant blind indices (regex + LLM)
- Three-pass search (add LLM reranking)
"""

import uuid
from typing import List, Optional, Dict, Callable, Any
from dataclasses import dataclass
import numpy as np

# Import v0.2 as base
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from openmemory_v02.client import OpenMemoryClientV02
from openmemory_v02.crypto import CryptoManager
from openmemory_v02.search import SearchResult

from .multi_variant_indices import MultiVariantBlindIndexGenerator
from .llm_reranking import LLMReranker, RerankedResult


@dataclass
class V05SearchResult(SearchResult):
    """Extended search result with LLM explanation."""
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.memory_id if hasattr(self, 'memory_id') else self.id,
            "content": self.content,
            "score": self.score,
            "explanation": self.explanation,
            "vector_rank": getattr(self, 'vector_rank', None),
            "bm25_rank": getattr(self, 'bm25_rank', None)
        }


class OpenMemoryClientV05(OpenMemoryClientV02):
    """
    OpenMemory v0.5 client with three-pass search.

    Three-Pass Search:
    1. Pass 1 (Remote, ~100ms): Vector KNN + blind index boost
    2. Pass 2 (Local, ~500ms): BM25 + RRF fusion
    3. Pass 3 (Local, ~500ms): LLM reranking

    Multi-Variant Blind Indices:
    - Fast path: Regex-based variants (lowercase, separators, etc.)
    - Smart path: LLM-based context-aware variants

    Zero-Knowledge Properties:
    - All encryption/decryption happens client-side
    - LLM operates locally on decrypted data
    - Server never sees plaintext or keys
    """

    def __init__(
        self,
        master_password: str,
        api_url: str = None,
        embedding_model=None,
        vault_id: str = None,
        llm_client=None
    ):
        """
        Initialize OpenMemory v0.5 client.

        Args:
            master_password: Master password for key derivation
            api_url: Server API URL (for production)
            embedding_model: Embedding model (e.g., SentenceTransformer)
            vault_id: Optional vault ID
            llm_client: LLM client for variant generation and reranking
        """
        # Initialize v0.2 base
        super().__init__(
            master_password=master_password,
            api_url=api_url,
            embedding_model=embedding_model,
            vault_id=vault_id
        )

        # Store LLM client
        self.llm_client = llm_client

        # Replace blind index generator with multi-variant version
        keys = self.crypto.derive_keys()
        self.blind_index_gen = MultiVariantBlindIndexGenerator(
            blind_key=keys.blind_key,
            llm_client=llm_client
        )

        # Initialize LLM reranker
        if llm_client:
            self.reranker = LLMReranker(
                llm_client=llm_client,
                max_candidates=50,
                top_k=5
            )
        else:
            self.reranker = None

    def encrypt_memory(
        self,
        plaintext: str,
        embedding: np.ndarray = None,
        use_llm_variants: bool = True
    ) -> dict:
        """
        Encrypt a memory with multi-variant blind indices.

        Args:
            plaintext: The plaintext memory to encrypt
            embedding: Pre-computed embedding (generated if not provided)
            use_llm_variants: Whether to use LLM for variant generation

        Returns:
            Dict with ciphertext, nonce, embedding, blind_indices, memory_id
        """
        # Generate embedding if not provided
        if embedding is None:
            if self.embedding_model is None:
                raise ValueError("Embedding model not configured")
            embedding = self._generate_embedding(plaintext)

        # Encrypt with v0.2 crypto (gets ciphertext, nonce)
        encrypted_v02 = self.crypto.encrypt(plaintext)

        # Generate multi-variant blind indices
        blind_indices = self.blind_index_gen.generate_blind_indices(
            plaintext,
            use_llm=use_llm_variants
        )

        return {
            'memory_id': str(uuid.uuid4()),
            'ciphertext': encrypted_v02.ciphertext,
            'nonce': encrypted_v02.nonce,
            'embedding': embedding,
            'blind_indices': list(blind_indices)
        }

    def store_memory(
        self,
        plaintext: str,
        server,
        embedding: np.ndarray = None,
        use_llm_variants: bool = True
    ) -> str:
        """
        Encrypt and store a memory with multi-variant blind indices.

        Args:
            plaintext: The plaintext memory
            server: MockOpenMemoryServer instance
            embedding: Optional pre-computed embedding
            use_llm_variants: Whether to use LLM for variant generation

        Returns:
            The memory ID
        """
        encrypted = self.encrypt_memory(plaintext, embedding, use_llm_variants)

        server.store(
            vault_id=self.vault_id,
            memory_id=encrypted['memory_id'],
            ciphertext=encrypted['ciphertext'],
            nonce=encrypted['nonce'],
            embedding=encrypted['embedding'],
            blind_indices=encrypted['blind_indices']
        )

        return encrypted['memory_id']

    def search(
        self,
        query: str,
        server,
        top_k: int = 5,
        candidate_pool_size: int = 250,
        use_llm_rerank: bool = True,
        use_llm_query_expansion: bool = False
    ) -> List[SearchResult]:
        """
        Three-pass search: remote vector + local BM25 + LLM reranking.

        Args:
            query: Search query
            server: MockOpenMemoryServer instance
            top_k: Number of results to return
            candidate_pool_size: Candidate pool size for Pass 1
            use_llm_rerank: Whether to use LLM reranking (Pass 3)
            use_llm_query_expansion: Whether to use LLM for query expansion

        Returns:
            List of SearchResult with decrypted content
        """
        # Generate query embedding
        if self.embedding_model is None:
            raise ValueError("Embedding model not configured")

        query_vector = self._generate_embedding(query)

        # Generate multi-variant query blind indices
        query_blind_hashes = list(
            self.blind_index_gen.generate_query_blind_indices(
                query,
                use_llm=use_llm_query_expansion
            )
        )

        # Pass 1: Remote search (server-side)
        candidates = server.search(
            vault_id=self.vault_id,
            query_vector=query_vector,
            blind_hashes=query_blind_hashes,
            limit=candidate_pool_size
        )

        # Build stored memories dict for Pass 2
        stored_memories = {}
        for candidate in candidates:
            stored_memories[candidate['memory_id']] = (
                candidate['ciphertext'],
                candidate['nonce']
            )

        # Format candidates for Pass 2
        pass1_candidates = [
            (c['memory_id'], c['vector_score'], c['is_blind_match'])
            for c in candidates
        ]

        # Pass 2: Local reranking (BM25 + RRF)
        pass2_results = self.search_engine.pass2_local_rerank(
            candidates=pass1_candidates,
            query=query,
            stored_memories=stored_memories,
            top_k=50  # Always get 50 for Pass 3 input
        )

        # Pass 3: LLM reranking (if enabled)
        if use_llm_rerank and self.reranker:
            results = self._pass3_llm_rerank(query, pass2_results)
        else:
            results = pass2_results[:top_k]

        return results

    def _pass3_llm_rerank(
        self,
        query: str,
        pass2_results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        Pass 3: LLM reranking of top 50 candidates.

        Args:
            query: Original search query
            pass2_results: Top 50 results from Pass 2

        Returns:
            Top 5 reranked results
        """
        if not self.reranker:
            return pass2_results[:5]

        # Format candidates for LLM
        candidates = []
        for result in pass2_results[:50]:
            candidates.append({
                'id': result.memory_id,
                'snippet': result.content[:700],
                'score': result.score
            })

        # Rerank with LLM
        reranked = self.reranker.rerank(query, candidates)

        # Convert back to SearchResult format
        final_results = []
        for r in reranked[:5]:
            final_results.append(SearchResult(
                content=r.content,
                score=r.score,
                vector_rank=None,  # Lost in reranking
                bm25_rank=None,
                memory_id=r.id
            ))

        return final_results

    def generate_multi_variant_blind_indices(
        self,
        plaintext: str,
        llm_client=None
    ) -> List[str]:
        """
        Generate multi-variant blind indices for a memory.

        Args:
            plaintext: The memory content
            llm_client: Optional LLM client (uses self.llm_client if not provided)

        Returns:
            List of hex-encoded blind index hashes
        """
        if llm_client is None:
            llm_client = self.llm_client

        generator = MultiVariantBlindIndexGenerator(
            blind_key=self.crypto.derive_keys().blind_key,
            llm_client=llm_client
        )

        blind_indices = generator.generate_blind_indices(plaintext, use_llm=llm_client is not None)

        return list(blind_indices)

    def pass3_llm_rerank(
        self,
        query: str,
        top_50_candidates: List[Dict[str, Any]],
        llm_client=None
    ) -> List[Dict[str, Any]]:
        """
        Standalone LLM reranking function.

        Args:
            query: Search query
            top_50_candidates: Top 50 results from Pass 2
            llm_client: Optional LLM client

        Returns:
            Top 5 reranked results with explanations
        """
        if llm_client is None:
            llm_client = self.llm_client

        if llm_client is None:
            raise ValueError("LLM client required for reranking")

        reranker = LLMReranker(llm_client)

        reranked = reranker.rerank(query, top_50_candidates)

        return [
            {
                'id': r.id,
                'content': r.content,
                'score': r.score,
                'explanation': r.explanation,
                'rank': r.rank
            }
            for r in reranked
        ]
