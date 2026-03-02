"""
Mock server implementation for OpenMemory v0.2 testbed.

Simulates the server-side behavior:
- Stores encrypted memories, embeddings, and blind indices
- Performs Pass 1 vector search
- Never sees plaintext or cryptographic keys
"""

from typing import Dict, List, Tuple, Optional
import uuid
import numpy as np

from .search import TwoPassSearch


class MockOpenMemoryServer:
    """
    Mock server for OpenMemory v0.2 testbed.

    Zero-Knowledge Properties:
    - Server stores: ciphertext, embeddings, blind indices only
    - Server never sees: plaintext, master password, derived keys
    """

    def __init__(self):
        """Initialize empty mock server."""
        # Storage vaults (keyed by vault_id)
        self._vaults: Dict[str, dict] = {}

    def create_vault(self, vault_id: str = None) -> str:
        """
        Create a new vault.

        Args:
            vault_id: Optional vault ID (auto-generated if not provided)

        Returns:
            The vault ID
        """
        if vault_id is None:
            vault_id = str(uuid.uuid4())

        if vault_id in self._vaults:
            raise ValueError(f"Vault {vault_id} already exists")

        self._vaults[vault_id] = {
            'memories': {},  # memory_id -> encrypted data
            'embeddings': {},  # memory_id -> embedding vector
            'blind_indices': {},  # memory_id -> list of blind hashes
        }

        return vault_id

    def store(
        self,
        vault_id: str,
        memory_id: str,
        ciphertext: bytes,
        nonce: bytes,
        embedding: np.ndarray,
        blind_indices: List[str]
    ) -> None:
        """
        Store an encrypted memory.

        Args:
            vault_id: The vault to store in
            memory_id: Unique identifier for this memory
            ciphertext: Encrypted content
            nonce: Nonce used for encryption
            embedding: Pre-computed embedding vector
            blind_indices: List of blind index hashes
        """
        if vault_id not in self._vaults:
            raise ValueError(f"Vault {vault_id} does not exist")

        vault = self._vaults[vault_id]

        vault['memories'][memory_id] = (ciphertext, nonce)
        vault['embeddings'][memory_id] = embedding
        vault['blind_indices'][memory_id] = blind_indices

    def batch_store(
        self,
        vault_id: str,
        memories: List[dict]
    ) -> None:
        """
        Store multiple encrypted memories in batch.

        Args:
            vault_id: The vault to store in
            memories: List of dicts with keys: memory_id, ciphertext, nonce,
                      embedding, blind_indices
        """
        for memory in memories:
            self.store(
                vault_id,
                memory['memory_id'],
                memory['ciphertext'],
                memory['nonce'],
                memory['embedding'],
                memory['blind_indices']
            )

    def search(
        self,
        vault_id: str,
        query_vector: np.ndarray,
        blind_hashes: List[str],
        limit: int = 250
    ) -> List[dict]:
        """
        Pass 1 search: Vector KNN + blind index matching.

        Args:
            vault_id: The vault to search
            query_vector: Query embedding vector
            blind_hashes: Blind indices from query (for exact matching)
            limit: Maximum candidates to return

        Returns:
            List of candidate results with memory_id, vector_score, is_blind_match
        """
        if vault_id not in self._vaults:
            raise ValueError(f"Vault {vault_id} does not exist")

        vault = self._vaults[vault_id]

        # Use TwoPassSearch for the vector search logic
        search_engine = TwoPassSearch(decrypt_fn=None)  # Not used in Pass 1

        candidates = search_engine.pass1_remote_search(
            query_vector=query_vector,
            blind_hashes=blind_hashes,
            stored_embeddings=vault['embeddings'],
            stored_blind_indices=vault['blind_indices'],
            candidate_pool_size=limit
        )

        # Format results
        results = []
        for memory_id, vector_score, is_blind_match in candidates:
            ciphertext, nonce = vault['memories'][memory_id]
            results.append({
                'memory_id': memory_id,
                'ciphertext': ciphertext,
                'nonce': nonce,
                'vector_score': vector_score,
                'is_blind_match': is_blind_match
            })

        return results

    def get_memory(self, vault_id: str, memory_id: str) -> Optional[Tuple[bytes, bytes]]:
        """
        Retrieve encrypted memory by ID.

        Args:
            vault_id: The vault
            memory_id: The memory ID

        Returns:
            Tuple of (ciphertext, nonce) or None if not found
        """
        if vault_id not in self._vaults:
            return None

        return self._vaults[vault_id]['memories'].get(memory_id)

    def get_vault_stats(self, vault_id: str) -> dict:
        """
        Get statistics about a vault.

        Args:
            vault_id: The vault

        Returns:
            Dict with memory_count, embedding_dim, etc.
        """
        if vault_id not in self._vaults:
            raise ValueError(f"Vault {vault_id} does not exist")

        vault = self._vaults[vault_id]
        memory_ids = list(vault['memories'].keys())

        if not memory_ids:
            return {
                'memory_count': 0,
                'embedding_dim': 0,
                'blind_index_count': 0
            }

        # Get embedding dimension from first memory
        first_embedding = vault['embeddings'][memory_ids[0]]
        embedding_dim = len(first_embedding)

        # Count total blind indices
        total_blind_indices = sum(
            len(indices) for indices in vault['blind_indices'].values()
        )

        return {
            'memory_count': len(memory_ids),
            'embedding_dim': embedding_dim,
            'blind_index_count': total_blind_indices
        }

    def delete_vault(self, vault_id: str) -> bool:
        """
        Delete a vault.

        Args:
            vault_id: The vault to delete

        Returns:
            True if deleted, False if not found
        """
        if vault_id in self._vaults:
            del self._vaults[vault_id]
            return True
        return False

    def clear_all(self) -> None:
        """Clear all vaults (useful for testing)."""
        self._vaults.clear()
