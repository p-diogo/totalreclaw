"""
Data models for OpenMemory infrastructure.

Defines the structure of encrypted vault entries and search results.
Compatible with OpenClaw data format.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class EncryptedVault:
    """
    Represents an encrypted memory chunk in the vault.

    Attributes:
        id: Database row ID
        vault_id: User vault identifier
        agent_id: Agent that created the memory
        ciphertext: AES-256-GCM encrypted content
        nonce: 12-byte GCM nonce
        tag: 16-byte GCM authentication tag
        embedding: 384-dimensional vector (list of floats for pgvector)
        blind_indices: Hashed search terms for blind indexing
        source_file: OpenClaw: original source filename
        source_type: OpenClaw: MEMORY.md, memory-daily, or imported
        chunk_index: OpenClaw: chunk sequence number
        category: Optional category classification
        created_at: Timestamp of creation
    """

    id: Optional[int] = None
    vault_id: Optional[UUID] = None
    agent_id: str = ""
    ciphertext: bytes = b""
    nonce: bytes = b""
    tag: bytes = b""
    embedding: list[float] | bytes = None  # type: ignore[assignment]
    blind_indices: list[str] = None  # type: ignore[assignment]
    source_file: Optional[str] = None
    source_type: Optional[str] = None  # 'MEMORY.md', 'memory-daily', 'imported'
    chunk_index: int = 0
    category: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.blind_indices is None:
            self.blind_indices = []
        if self.embedding is None:
            self.embedding = []


@dataclass
class VectorSearchResult:
    """
    Result from a vector similarity search.

    Attributes:
        vault_id: Vault identifier for the matching memory
        chunk_index: Chunk sequence number
        similarity: Cosine similarity score (0-1, higher is better)
        distance: Euclidean distance (lower is better)
        category: Optional category of the result
        metadata: Additional metadata about the result
    """

    vault_id: UUID
    chunk_index: int
    similarity: float
    distance: float
    category: Optional[str] = None
    metadata: dict = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# Source type constants for OpenClaw compatibility
SOURCE_TYPE_MEMORY_MD = "MEMORY.md"
SOURCE_TYPE_MEMORY_DAILY = "memory-daily"
SOURCE_TYPE_IMPORTED = "imported"

VALID_SOURCE_TYPES = {SOURCE_TYPE_MEMORY_MD, SOURCE_TYPE_MEMORY_DAILY, SOURCE_TYPE_IMPORTED}
