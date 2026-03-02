#!/usr/bin/env python3
"""
Database initialization script for OpenMemory.

Run this script to verify and initialize the OpenMemory database.

Usage:
    python src/db_init.py [--verify] [--reset]
"""

import argparse
import asyncio
import sys

# Add src to path for imports
sys.path.insert(0, "/Users/pdiogo/Documents/code/openmemory/src")

from openmemory_infrastructure import Database, SchemaManager, get_database


async def verify_database(db: Database) -> bool:
    """Verify database schema and connection."""
    print("Verifying database setup...")

    # Health check
    is_healthy = await db.health_check()
    print(f"  Connection: {'OK' if is_healthy else 'FAILED'}")

    # Schema verification
    manager = SchemaManager(db)
    verification = await manager.verify_schema()

    all_ok = is_healthy
    for item, status in verification.items():
        symbol = "OK" if status else "MISSING"
        print(f"  {item}: {symbol}")
        all_ok = all_ok and status

    return all_ok


async def reset_database(db: Database) -> None:
    """Reset the database (drop and recreate tables)."""
    print("Resetting database...")
    manager = SchemaManager(db)

    # Drop existing tables
    await manager.drop_all()
    print("  Dropped existing tables")

    # Reapply schema
    schema_path = "/Users/pdiogo/Documents/code/openmemory/database/schema.sql"
    with open(schema_path) as f:
        schema_sql = f.read()

    async with db.connection() as conn:
        await conn.execute(schema_sql)
        await conn.commit()

    print("  Schema applied successfully")


async def main() -> int:
    parser = argparse.ArgumentParser(description="OpenMemory database initialization")
    parser.add_argument("--verify", action="store_true", help="Verify database setup")
    parser.add_argument("--reset", action="store_true", help="Reset database (drops all tables)")
    args = parser.parse_args()

    # Get database instance
    db = get_database()

    try:
        await db.initialize()

        if args.reset:
            await reset_database(db)
            # Verify after reset
            await verify_database(db)
        elif args.verify or not args.reset:
            ok = await verify_database(db)
            if not ok:
                print("\nDatabase verification failed. Run with --reset to reinitialize.")
                return 1

        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
