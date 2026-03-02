"""
Schema management module for OpenMemory.

Provides utilities for database schema creation, migration, and verification.
"""

from pathlib import Path
from typing import Optional

from .database import Database


class SchemaManager:
    """
    Manages database schema for OpenMemory.

    Handles schema creation, migrations, and validation.
    """

    def __init__(self, db: Database, schema_dir: Optional[Path] = None):
        """
        Initialize the schema manager.

        Args:
            db: Database instance
            schema_dir: Directory containing schema SQL files
        """
        self.db = db
        self.schema_dir = schema_dir or Path(__file__).parent.parent.parent / "database"

    async def apply_schema(self, schema_file: str = "schema.sql") -> None:
        """
        Apply a schema file to the database.

        Args:
            schema_file: Name of the schema file
        """
        schema_path = self.schema_dir / schema_file
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path) as f:
            schema_sql = f.read()

        async with self.db.connection() as conn:
            # Split and execute statements (handle PostgreSQL's limited SQL parser)
            # For complex schemas, use a proper migration tool
            await conn.execute(schema_sql)
            await conn.commit()

    async def verify_schema(self) -> dict[str, bool]:
        """
        Verify that required tables and indexes exist.

        Returns:
            Dictionary with verification results
        """
        results = {}

        async with self.db.connection() as conn:
            # Check tables
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'encrypted_vault'
                    )
                    """
                )
                results["table_encrypted_vault"] = (await cur.fetchone())[0]

                # Check indexes
                await cur.execute(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'encrypted_vault'
                    """
                )
                indexes = {row[0] for row in await cur.fetchall()}

                results["index_vault_id"] = "idx_vault_id" in indexes
                results["index_agent_id"] = "idx_agent_id" in indexes
                results["index_blind_indices"] = "idx_blind_indices" in indexes
                results["index_routing"] = "idx_routing" in indexes

        return results

    async def drop_all(self) -> None:
        """Drop all tables (useful for testing)."""
        async with self.db.connection() as conn:
            await conn.execute("DROP TABLE IF EXISTS encrypted_vault CASCADE")
            await conn.commit()

    async def get_table_info(self, table_name: str = "encrypted_vault") -> dict:
        """
        Get information about a table's structure.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with column information
        """
        async with self.db.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (table_name,),
                )
                columns = await cur.fetchall()

                return {
                    "columns": [
                        {
                            "name": col[0],
                            "type": col[1],
                            "nullable": col[2] == "YES",
                            "default": col[3],
                        }
                        for col in columns
                    ]
                }


async def setup_database(
    db: Database,
    schema_file: str = "schema.sql",
    drop_existing: bool = False,
) -> None:
    """
    Set up the database schema.

    Args:
        db: Database instance
        schema_file: Schema file to apply
        drop_existing: Whether to drop existing tables first
    """
    manager = SchemaManager(db)

    if drop_existing:
        await manager.drop_all()

    await manager.apply_schema(schema_file)

    # Verify setup
    verification = await manager.verify_schema()
    if not all(verification.values()):
        raise ValueError(f"Schema verification failed: {verification}")
