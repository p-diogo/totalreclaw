"""
OpenMemory Infrastructure Package

Provides database utilities, schema management, and connection handling
for the OpenMemory testbed. Other agents import from this module.

Data Storage Format Specification:
- ciphertext: BYTEA - AES-256-GCM encrypted content
- nonce: BYTEA - 12-byte GCM nonce
- tag: BYTEA - 16-byte GCM authentication tag
- embedding: BYTEA - 384-dimensional float32 array (1536 bytes)
- blind_indices: TEXT[] - Array of hashed search terms
- source_type: VARCHAR(50) - 'MEMORY.md', 'memory-daily', or 'imported'
- chunk_index: INTEGER - Chunk sequence number
"""

from .database import Database, get_database
from .models import EncryptedVault, VectorSearchResult
from .schema import SchemaManager

__all__ = [
    "Database",
    "get_database",
    "EncryptedVault",
    "VectorSearchResult",
    "SchemaManager",
]
