"""
OpenMemory v0.2 Client Implementation

Provides the main client interface for:
- Encrypting and storing memories
- Two-pass search (remote vector + local BM25)
"""

import uuid
from typing import List, Optional, Dict
import numpy as np

from .crypto import CryptoManager
from .search import TwoPassSearch, SearchResult


class OpenMemoryClientV02:
    """
    Client for OpenMemory v0.2 zero-knowledge E2EE memory system.

    Two-Pass Search Algorithm:
    - Pass 1 (Remote, ~100ms): Server performs vector KNN search
    - Pass 2 (Local, ~500ms): Client decrypts and runs BM25 reranking

    Zero-Knowledge Properties:
    - Server never sees plaintext or cryptographic keys
    - All encryption/decryption happens client-side
    """

    def __init__(
        self,
        master_password: str,
        api_url: str = None,
        embedding_model = None,
        vault_id: str = None
    ):
        """
        Initialize OpenMemory client.

        Args:
            master_password: Master password for key derivation
            api_url: Server API URL (for production use)
            embedding_model: Embedding model instance (e.g., SentenceTransformer)
            vault_id: Optional vault ID (auto-generated if not provided)
        """
        self.master_password = master_password
        self.api_url = api_url
        self.vault_id = vault_id or str(uuid.uuid4())

        # Initialize crypto manager
        self.crypto = CryptoManager(master_password)

        # Embedding model (injected for testbed flexibility)
        self.embedding_model = embedding_model

        # Search engine (initialized with decrypt function)
        self.search_engine = TwoPassSearch(decrypt_fn=self.crypto.decrypt)

    def encrypt_memory(
        self,
        plaintext: str,
        embedding: np.ndarray = None
    ) -> dict:
        """
        Encrypt a memory for storage.

        Args:
            plaintext: The plaintext memory to encrypt
            embedding: Pre-computed embedding (generated if not provided)

        Returns:
            Dict with ciphertext, nonce, embedding, blind_indices, memory_id
        """
        # Generate embedding if not provided
        if embedding is None:
            if self.embedding_model is None:
                raise ValueError(
                    "Embedding model not configured. Provide embedding parameter "
                    "or initialize client with embedding_model."
                )
            embedding = self._generate_embedding(plaintext)

        # Encrypt plaintext
        encrypted = self.crypto.encrypt(plaintext)

        return {
            'memory_id': str(uuid.uuid4()),
            'ciphertext': encrypted.ciphertext,
            'nonce': encrypted.nonce,
            'embedding': embedding,
            'blind_indices': encrypted.blind_indices
        }

    def store_memory(
        self,
        plaintext: str,
        server,
        embedding: np.ndarray = None
    ) -> str:
        """
        Encrypt and store a memory on the server.

        Args:
            plaintext: The plaintext memory
            server: MockOpenMemoryServer instance (for testbed)
            embedding: Optional pre-computed embedding

        Returns:
            The memory ID
        """
        encrypted = self.encrypt_memory(plaintext, embedding)

        server.store(
            vault_id=self.vault_id,
            memory_id=encrypted['memory_id'],
            ciphertext=encrypted['ciphertext'],
            nonce=encrypted['nonce'],
            embedding=encrypted['embedding'],
            blind_indices=encrypted['blind_indices']
        )

        return encrypted['memory_id']

    def batch_store_memories(
        self,
        plaintexts: List[str],
        server
    ) -> List[str]:
        """
        Encrypt and store multiple memories.

        Args:
            plaintexts: List of plaintext memories
            server: MockOpenMemoryServer instance

        Returns:
            List of memory IDs
        """
        memory_ids = []

        for plaintext in plaintexts:
            memory_id = self.store_memory(plaintext, server)
            memory_ids.append(memory_id)

        return memory_ids

    def search(
        self,
        query: str,
        server,
        top_k: int = 5,
        candidate_pool_size: int = 250
    ) -> List[SearchResult]:
        """
        Two-pass search: remote vector + local BM25 reranking.

        Args:
            query: Search query
            server: MockOpenMemoryServer instance
            top_k: Number of results to return
            candidate_pool_size: Candidate pool size for Pass 2

        Returns:
            List of SearchResult with decrypted content
        """
        # Generate query embedding
        if self.embedding_model is None:
            raise ValueError(
                "Embedding model not configured. Initialize client with "
                "embedding_model to perform search."
            )

        query_vector = self._generate_embedding(query)

        # Generate query blind indices
        query_blind_hashes = self.crypto.generate_query_blind_indices(query)

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

        # Pass 2: Local reranking (client-side)
        results = self.search_engine.pass2_local_rerank(
            candidates=pass1_candidates,
            query=query,
            stored_memories=stored_memories,
            top_k=top_k
        )

        return results

    def _generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Args:
            text: The text to embed

        Returns:
            Embedding vector as numpy array
        """
        if self.embedding_model is None:
            raise ValueError("Embedding model not configured")

        # Handle different embedding model interfaces
        if hasattr(self.embedding_model, 'encode'):
            # SentenceTransformer interface
            return self.embedding_model.encode([text])[0]
        elif hasattr(self.embedding_model, 'embed'):
            # Generic embed method
            return self.embedding_model.embed(text)
        else:
            raise ValueError(
                f"Unsupported embedding model interface. "
                f"Model must have 'encode' or 'embed' method."
            )

    def get_memory(self, memory_id: str, server) -> Optional[str]:
        """
        Retrieve and decrypt a memory by ID.

        Args:
            memory_id: The memory ID
            server: MockOpenMemoryServer instance

        Returns:
            Decrypted plaintext or None if not found
        """
        encrypted = server.get_memory(self.vault_id, memory_id)

        if encrypted is None:
            return None

        ciphertext, nonce = encrypted
        return self.crypto.decrypt(ciphertext, nonce)

    def clear_keys(self):
        """
        Clear derived keys from memory.

        Call this after operations to minimize key exposure.
        """
        self.crypto.clear_keys()
