"""
Database connection and utility module for OpenMemory.

Provides a singleton Database class that manages PostgreSQL connections
and common operations for the encrypted_vault table.

Usage:
    from openmemory_infrastructure import get_database

    db = get_database()
    await db.initialize()

    # Insert a record
    await db.insert_encrypted_memory(vault_id, agent_id, ciphertext, ...)

    # Search by vector similarity
    results = await db.vector_search(query_embedding, limit=10)
"""

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Optional
from uuid import UUID

import numpy as np
import psycopg
from psycopg.rows import dict_row

from .models import EncryptedVault, VectorSearchResult


class Database:
    """
    Database connection manager for OpenMemory.

    Manages database connections and provides async methods for
    encrypted memory storage and retrieval.
    """

    # Default connection parameters
    DEFAULT_CONFIG = {
        "host": "localhost",
        "port": 5433,  # Docker PostgreSQL with pgvector
        "dbname": "openmemory",
        "user": "postgres",
        "password": "openmemory",
        "autocommit": False,
    }

    def __init__(self, config: Optional[Mapping[str, str | int]] = None):
        """
        Initialize the database manager.

        Args:
            config: Optional database connection config. Uses DEFAULT_CONFIG if None.
        """
        self._config = {**self.DEFAULT_CONFIG, **(config or {})}
        self._conn: Optional[psycopg.AsyncConnection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the database connection."""
        if self._conn is not None:
            return

        async with self._lock:
            if self._conn is not None:
                return

            self._conn = await psycopg.AsyncConnection.connect(**self._config)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def connection(
        self,
    ) -> AsyncIterator[psycopg.AsyncConnection]:
        """Get a database connection."""
        if self._conn is None:
            await self.initialize()
        assert self._conn is not None
        yield self._conn

    async def insert_encrypted_memory(
        self,
        vault_id: UUID,
        agent_id: str,
        ciphertext: bytes,
        nonce: bytes,
        tag: bytes,
        embedding: np.ndarray | list[float] | bytes,
        blind_indices: list[str] | None = None,
        source_file: str | None = None,
        source_type: str | None = None,
        chunk_index: int = 0,
        category: str | None = None,
    ) -> int:
        """
        Insert an encrypted memory into the vault.

        Args:
            vault_id: User vault identifier
            agent_id: Agent that created the memory
            ciphertext: Encrypted content bytes
            nonce: GCM nonce (12 bytes)
            tag: GCM authentication tag (16 bytes)
            embedding: 384-dimensional vector or pre-serialized bytes
            blind_indices: List of hashed search terms
            source_file: Source filename (OpenClaw compatibility)
            source_type: Source type (OpenClaw compatibility)
            chunk_index: Chunk sequence number
            category: Optional category classification

        Returns:
            The ID of the inserted row
        """
        # Convert embedding to list for pgvector (needs array format)
        if isinstance(embedding, bytes):
            # If bytes, deserialize to list
            embedding_list = np.frombuffer(embedding, dtype=np.float32).tolist()
        elif isinstance(embedding, np.ndarray):
            embedding_list = embedding.astype(np.float32).tolist()
        else:
            # Already a list
            embedding_list = [float(x) for x in embedding]

        if blind_indices is None:
            blind_indices = []

        async with self.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO encrypted_vault
                    (vault_id, agent_id, ciphertext, nonce, tag, embedding,
                     blind_indices, source_file, source_type, chunk_index, category)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        vault_id,
                        agent_id,
                        ciphertext,
                        nonce,
                        tag,
                        embedding_list,  # pgvector accepts float array
                        blind_indices,
                        source_file,
                        source_type,
                        chunk_index,
                        category,
                    ),
                )
                result = await cur.fetchone()
                await conn.commit()
                return result[0] if result else -1

    async def get_by_id(self, record_id: int) -> Optional[EncryptedVault]:
        """Retrieve a record by its database ID."""
        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM encrypted_vault WHERE id = %s",
                    (record_id,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                return self._row_to_vault(row)

    async def get_by_vault(
        self,
        vault_id: UUID,
        source_type: str | None = None,
        limit: int = 100,
    ) -> list[EncryptedVault]:
        """Retrieve records for a vault, optionally filtered by source type."""
        query = "SELECT * FROM encrypted_vault WHERE vault_id = %s"
        params: list = [vault_id]

        if source_type:
            query += " AND source_type = %s"
            params.append(source_type)

        query += " ORDER BY chunk_index ASC LIMIT %s"
        params.append(limit)

        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
                return [self._row_to_vault(row) for row in rows]

    async def vector_search(
        self,
        query_embedding: np.ndarray | list[float] | bytes,
        vault_id: UUID | None = None,
        limit: int = 10,
        threshold: float = 0.0,
    ) -> list[VectorSearchResult]:
        """
        Perform vector similarity search using pgvector's HNSW index.

        Uses native PostgreSQL cosine similarity operator with HNSW indexing.

        Args:
            query_embedding: Query vector (384 dimensions)
            vault_id: Optional vault ID to filter results
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0-1)

        Returns:
            List of search results ranked by similarity
        """
        # Convert query embedding to list for pgvector
        if isinstance(query_embedding, bytes):
            query_list = np.frombuffer(query_embedding, dtype=np.float32).tolist()
        elif isinstance(query_embedding, np.ndarray):
            query_list = query_embedding.astype(np.float32).tolist()
        else:
            query_list = [float(x) for x in query_embedding]

        # Build query with pgvector cosine similarity
        # The <=> operator returns cosine distance (0 = identical, 2 = opposite)
        # So we use (1 - (embedding <=> query)) for similarity
        base_query = """
            SELECT
                id, vault_id, agent_id, chunk_index, category, source_type,
                1 - (embedding <=> %s::vector) as similarity
            FROM encrypted_vault
        """
        params: list = [query_list]

        if vault_id:
            base_query += " WHERE vault_id = %s"
            params.append(vault_id)

        base_query += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([query_list, limit])

        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(base_query, params)
                rows = await cur.fetchall()

        # Convert to VectorSearchResult
        results = []
        for row in rows:
            similarity = row["similarity"]
            if similarity >= threshold:
                vault_id_val = row["vault_id"]
                if not isinstance(vault_id_val, UUID):
                    vault_id_val = UUID(vault_id_val)

                results.append(
                    VectorSearchResult(
                        vault_id=vault_id_val,
                        chunk_index=row["chunk_index"],
                        similarity=float(similarity),
                        distance=float(1 - similarity),
                        category=row.get("category"),
                        metadata={
                            "id": row["id"],
                            "agent_id": row["agent_id"],
                            "source_type": row.get("source_type"),
                        },
                    )
                )

        return results

    @staticmethod
    def _row_to_vault(row: Mapping) -> EncryptedVault:
        """Convert a database row to EncryptedVault model."""
        vault_id = row.get("vault_id")
        # psycopg returns UUID objects directly, no need to convert
        if vault_id is not None and not isinstance(vault_id, UUID):
            vault_id = UUID(vault_id)

        return EncryptedVault(
            id=row["id"],
            vault_id=vault_id,
            agent_id=row["agent_id"],
            ciphertext=row["ciphertext"],
            nonce=row["nonce"],
            tag=row["tag"],
            embedding=row["embedding"],
            blind_indices=row.get("blind_indices") or [],
            source_file=row.get("source_file"),
            source_type=row.get("source_type"),
            chunk_index=row.get("chunk_index", 0),
            category=row.get("category"),
            created_at=row.get("created_at"),
        )

    async def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            async with self.connection() as conn:
                await conn.execute("SELECT 1")
                return True
        except Exception:
            return False


# Singleton instance
_db: Optional[Database] = None
_db_lock = asyncio.Lock()


@lru_cache
def get_database(
    config: Optional[Mapping[str, str | int]] = None,
) -> Database:
    """
    Get the singleton Database instance.

    Args:
        config: Optional database configuration

    Returns:
        Database instance
    """
    return Database(config)
