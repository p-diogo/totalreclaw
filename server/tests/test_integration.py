"""
Integration tests for TotalReclaw Server using testcontainers.

Tests PostgreSQL-specific features against a real database:
- GIN index overlap queries (blind index search)
- sequence_id auto-increment
- Unique constraint on (user_id, content_fp) for active facts
- Concurrent store + search operations
- Soft delete + tombstone
- Delta sync ordering

Requires Docker to be available. Tests are skipped gracefully if Docker
is not running.

Usage:
    # Run only integration tests:
    python -m pytest tests/test_integration.py -v -m integration

    # Run all tests (unit + integration):
    python -m pytest tests/ -v
"""
import asyncio
import os
import sys
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Docker availability check
# ---------------------------------------------------------------------------

def _docker_is_available() -> bool:
    """Check whether Docker daemon is reachable."""
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


DOCKER_AVAILABLE = _docker_is_available()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker is not available"),
    pytest.mark.asyncio(loop_scope="module"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_async_pg_url(sync_url: str) -> str:
    """Convert a psycopg2 connection URL to an asyncpg one.

    testcontainers returns a URL like:
        postgresql+psycopg2://user:pass@host:port/db
    We need:
        postgresql+asyncpg://user:pass@host:port/db
    """
    return sync_url.replace("+psycopg2", "+asyncpg").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="module")
def pg_container():
    """Start an ephemeral PostgreSQL 16 container for the test module.

    The container is shared across all tests in this module for speed,
    but each test creates its own user/data via unique UUIDs, so there
    is no cross-test interference.
    """
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16", driver="psycopg2") as pg:
        yield pg


@pytest.fixture(scope="module")
def database_url(pg_container) -> str:
    """Return an asyncpg connection URL for the running container."""
    sync_url = pg_container.get_connection_url()
    return _make_async_pg_url(sync_url)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db(database_url):
    """Create a Database instance connected to the testcontainer and
    initialise the schema (create_all).

    The Database constructor reads Settings which may try to load .env.
    We patch get_settings to supply minimal defaults so it doesn't
    interfere.
    """
    from src.config import Settings
    from src.db.database import Database

    # Provide minimal settings so Database.__init__ doesn't fail
    minimal_settings = Settings(
        database_url=database_url,
        database_pool_size=5,
        database_max_overflow=2,
        database_pool_recycle=300,
        database_pool_pre_ping=True,
        database_pool_timeout=10,
        debug=False,
    )

    with patch("src.db.database.get_settings", return_value=minimal_settings):
        database = Database(database_url)

    await database.init()
    yield database
    await database.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    """Generate a random user_id."""
    return str(uuid.uuid4())


def _fid() -> str:
    """Generate a random fact_id."""
    return str(uuid.uuid4())


def _hex64() -> str:
    """Generate a valid 64-char hex string (fake blind index / trapdoor)."""
    return uuid.uuid4().hex + uuid.uuid4().hex  # 32+32 = 64 hex chars


async def _create_test_user(db, user_id: str | None = None) -> str:
    """Insert a minimal test user and return its user_id."""
    uid = user_id or _uid()
    auth_hash = os.urandom(32)
    salt = os.urandom(32)
    await db.create_user(uid, auth_hash, salt)
    return uid


async def _store_test_fact(
    db,
    user_id: str,
    blind_indices: list[str] | None = None,
    content_fp: str | None = None,
    decay_score: float = 1.0,
):
    """Store a fact with sensible defaults and return it."""
    fact_id = _fid()
    indices = blind_indices or [_hex64()]
    return await db.store_fact(
        fact_id=fact_id,
        user_id=user_id,
        encrypted_blob=os.urandom(64),
        blind_indices=indices,
        decay_score=decay_score,
        source="integration_test",
        content_fp=content_fp,
    )


# ===================================================================
# (a) GIN Index Overlap Queries
# ===================================================================

class TestGINIndexOverlapQueries:
    """Verify that the PostgreSQL array overlap (&&) operator works
    correctly via the GIN index on blind_indices."""

    async def test_search_matching_single_trapdoor(self, db):
        """Store facts with known blind_indices and search with a matching trapdoor."""
        uid = await _create_test_user(db)
        idx_a = _hex64()
        idx_b = _hex64()
        idx_c = _hex64()

        # Store three facts with different index combinations
        await _store_test_fact(db, uid, blind_indices=[idx_a, idx_b])
        await _store_test_fact(db, uid, blind_indices=[idx_b, idx_c])
        await _store_test_fact(db, uid, blind_indices=[idx_c])

        # Search for idx_a -- should match only the first fact
        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx_a]
        )
        assert total == 1
        assert len(results) == 1

    async def test_search_multiple_trapdoors_or_semantics(self, db):
        """Multiple trapdoors use OR semantics -- any overlap is a match."""
        uid = await _create_test_user(db)
        idx_a = _hex64()
        idx_b = _hex64()
        idx_c = _hex64()

        await _store_test_fact(db, uid, blind_indices=[idx_a])
        await _store_test_fact(db, uid, blind_indices=[idx_b])
        await _store_test_fact(db, uid, blind_indices=[idx_c])

        # Search with idx_a and idx_b -- should match 2 facts
        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx_a, idx_b]
        )
        assert total == 2
        assert len(results) == 2

    async def test_search_non_matching_trapdoors_returns_empty(self, db):
        """Trapdoors that don't overlap with any stored indices return empty."""
        uid = await _create_test_user(db)
        stored_idx = _hex64()
        search_idx = _hex64()

        await _store_test_fact(db, uid, blind_indices=[stored_idx])

        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[search_idx]
        )
        assert total == 0
        assert len(results) == 0

    async def test_search_respects_user_isolation(self, db):
        """Facts from user A should not be returned when searching as user B."""
        uid_a = await _create_test_user(db)
        uid_b = await _create_test_user(db)
        shared_idx = _hex64()

        await _store_test_fact(db, uid_a, blind_indices=[shared_idx])
        await _store_test_fact(db, uid_b, blind_indices=[shared_idx])

        results_a, total_a = await db.search_facts_by_blind_indices(
            user_id=uid_a, trapdoors=[shared_idx]
        )
        results_b, total_b = await db.search_facts_by_blind_indices(
            user_id=uid_b, trapdoors=[shared_idx]
        )
        assert total_a == 1
        assert total_b == 1
        assert results_a[0].id != results_b[0].id

    async def test_search_with_decay_score_filter(self, db):
        """min_decay_score parameter filters out low-scoring facts."""
        uid = await _create_test_user(db)
        idx = _hex64()

        await _store_test_fact(db, uid, blind_indices=[idx], decay_score=0.9)
        await _store_test_fact(db, uid, blind_indices=[idx], decay_score=0.3)
        await _store_test_fact(db, uid, blind_indices=[idx], decay_score=0.1)

        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx], min_decay_score=0.5
        )
        assert total == 1
        assert len(results) == 1
        assert results[0].decay_score == pytest.approx(0.9)

    async def test_search_max_candidates_limits_results(self, db):
        """max_candidates caps the number of returned facts."""
        uid = await _create_test_user(db)
        idx = _hex64()

        for _ in range(10):
            await _store_test_fact(db, uid, blind_indices=[idx])

        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx], max_candidates=3
        )
        assert total == 10  # total matched (before LIMIT)
        assert len(results) == 3  # capped by max_candidates

    async def test_search_results_ordered_by_decay_desc(self, db):
        """Results are returned in descending decay_score order."""
        uid = await _create_test_user(db)
        idx = _hex64()

        for score in [0.2, 0.8, 0.5, 1.0, 0.1]:
            await _store_test_fact(db, uid, blind_indices=[idx], decay_score=score)

        results, _ = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx]
        )
        scores = [r.decay_score for r in results]
        assert scores == sorted(scores, reverse=True)


# ===================================================================
# (b) sequence_id Auto-Increment
# ===================================================================

class TestSequenceIdAutoIncrement:
    """Verify that sequence_id is assigned monotonically increasing values."""

    async def test_sequence_id_monotonically_increases(self, db):
        """Each stored fact gets a strictly increasing sequence_id."""
        uid = await _create_test_user(db)

        seq_ids = []
        for _ in range(5):
            fact = await _store_test_fact(db, uid)
            seq_ids.append(fact.sequence_id)

        # sequence_id must be strictly increasing
        for i in range(1, len(seq_ids)):
            assert seq_ids[i] > seq_ids[i - 1], (
                f"sequence_id did not increase: {seq_ids}"
            )

    async def test_sequence_id_not_none(self, db):
        """Every newly stored fact must have a non-null sequence_id."""
        uid = await _create_test_user(db)
        fact = await _store_test_fact(db, uid)
        assert fact.sequence_id is not None
        assert isinstance(fact.sequence_id, int)

    async def test_get_facts_since_sequence_returns_newer(self, db):
        """get_facts_since_sequence only returns facts after the given sequence."""
        uid = await _create_test_user(db)

        # Store 3 facts
        f1 = await _store_test_fact(db, uid)
        f2 = await _store_test_fact(db, uid)
        f3 = await _store_test_fact(db, uid)

        # Get facts since f1's sequence -- should return f2 and f3
        facts, latest_seq, has_more = await db.get_facts_since_sequence(
            user_id=uid, since_sequence=f1.sequence_id
        )
        returned_ids = {f.id for f in facts}
        assert f2.id in returned_ids
        assert f3.id in returned_ids
        assert f1.id not in returned_ids
        assert latest_seq == f3.sequence_id

    async def test_get_facts_since_zero_returns_all(self, db):
        """since_sequence=0 returns all facts for the user."""
        uid = await _create_test_user(db)

        facts_created = []
        for _ in range(3):
            f = await _store_test_fact(db, uid)
            facts_created.append(f)

        facts, latest_seq, has_more = await db.get_facts_since_sequence(
            user_id=uid, since_sequence=0
        )
        assert len(facts) == 3
        assert latest_seq == facts_created[-1].sequence_id


# ===================================================================
# (c) Unique Constraint on (user_id, content_fp)
# ===================================================================

class TestUniqueConstraintContentFp:
    """Verify the partial unique index on (user_id, content_fp) WHERE is_active = true."""

    async def test_duplicate_content_fp_rejected(self, db):
        """Same user_id + content_fp with is_active=true should be rejected."""
        uid = await _create_test_user(db)
        fp = _hex64()

        # First insert succeeds
        await _store_test_fact(db, uid, content_fp=fp)

        # Second insert with same user + fp should raise
        with pytest.raises(Exception) as exc_info:
            await _store_test_fact(db, uid, content_fp=fp)

        # The error should be an IntegrityError or similar from the unique index
        error_str = str(exc_info.value).lower()
        assert (
            "unique" in error_str
            or "duplicate" in error_str
            or "idx_facts_user_fp" in error_str
        )

    async def test_different_user_same_fp_allowed(self, db):
        """Different user_id with the same content_fp should be allowed."""
        uid_a = await _create_test_user(db)
        uid_b = await _create_test_user(db)
        fp = _hex64()

        f1 = await _store_test_fact(db, uid_a, content_fp=fp)
        f2 = await _store_test_fact(db, uid_b, content_fp=fp)

        assert f1.id != f2.id

    async def test_soft_deleted_fp_allows_new_insert(self, db):
        """After soft-deleting a fact, a new fact with the same content_fp is allowed."""
        uid = await _create_test_user(db)
        fp = _hex64()

        # Store fact, then soft delete it
        f1 = await _store_test_fact(db, uid, content_fp=fp)
        deleted = await db.soft_delete_fact(f1.id, uid)
        assert deleted is True

        # Now a new insert with the same fp should succeed
        f2 = await _store_test_fact(db, uid, content_fp=fp)
        assert f2.id != f1.id

    async def test_null_content_fp_not_constrained(self, db):
        """Multiple facts with content_fp=None should be allowed (NULLs are not equal)."""
        uid = await _create_test_user(db)

        f1 = await _store_test_fact(db, uid, content_fp=None)
        f2 = await _store_test_fact(db, uid, content_fp=None)

        assert f1.id != f2.id

    async def test_find_fact_by_fingerprint(self, db):
        """find_fact_by_fingerprint returns the existing fact_id for a duplicate."""
        uid = await _create_test_user(db)
        fp = _hex64()

        f1 = await _store_test_fact(db, uid, content_fp=fp)

        existing_id = await db.find_fact_by_fingerprint(uid, fp)
        assert existing_id == f1.id

    async def test_find_fact_by_fingerprint_not_found(self, db):
        """find_fact_by_fingerprint returns None when no duplicate exists."""
        uid = await _create_test_user(db)

        result = await db.find_fact_by_fingerprint(uid, _hex64())
        assert result is None


# ===================================================================
# (d) Concurrent Store + Search
# ===================================================================

class TestConcurrentOperations:
    """Verify that concurrent store and search operations don't cause
    data corruption or deadlocks."""

    async def test_concurrent_stores_unique_sequence_ids(self, db):
        """Multiple concurrent stores must each get a unique sequence_id."""
        uid = await _create_test_user(db)
        idx = _hex64()

        async def store_one():
            return await _store_test_fact(db, uid, blind_indices=[idx])

        # Run 20 concurrent stores
        facts = await asyncio.gather(*[store_one() for _ in range(20)])

        seq_ids = [f.sequence_id for f in facts]
        # All sequence_ids must be unique
        assert len(set(seq_ids)) == 20, f"Duplicate sequence_ids found: {seq_ids}"
        # All must be positive integers
        for sid in seq_ids:
            assert sid is not None
            assert sid > 0

    async def test_concurrent_store_and_search(self, db):
        """Interleaved stores and searches should not deadlock or corrupt data."""
        uid = await _create_test_user(db)
        idx = _hex64()

        # Pre-populate some data
        for _ in range(5):
            await _store_test_fact(db, uid, blind_indices=[idx])

        async def store_task():
            return await _store_test_fact(db, uid, blind_indices=[idx])

        async def search_task():
            return await db.search_facts_by_blind_indices(
                user_id=uid, trapdoors=[idx]
            )

        # Run stores and searches concurrently
        tasks = []
        for _ in range(10):
            tasks.append(store_task())
            tasks.append(search_task())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # No exceptions should have occurred
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Exceptions during concurrent ops: {exceptions}"

    async def test_concurrent_stores_for_different_users(self, db):
        """Concurrent stores for different users should not interfere."""
        users = []
        for _ in range(5):
            uid = await _create_test_user(db)
            users.append(uid)

        async def store_for_user(uid):
            facts = []
            for _ in range(5):
                f = await _store_test_fact(db, uid)
                facts.append(f)
            return uid, facts

        results = await asyncio.gather(*[store_for_user(u) for u in users])

        for uid, facts in results:
            count = await db.count_active_facts(uid)
            assert count == 5, f"User {uid} has {count} facts, expected 5"


# ===================================================================
# (e) Soft Delete + Tombstone
# ===================================================================

class TestSoftDeleteAndTombstone:
    """Verify soft delete creates tombstone and hides facts from search."""

    async def test_soft_delete_hides_from_search(self, db):
        """After soft delete, the fact should not appear in search results."""
        uid = await _create_test_user(db)
        idx = _hex64()

        f1 = await _store_test_fact(db, uid, blind_indices=[idx])

        # Confirm it is searchable
        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx]
        )
        assert total == 1

        # Soft delete
        deleted = await db.soft_delete_fact(f1.id, uid)
        assert deleted is True

        # No longer searchable
        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx]
        )
        assert total == 0
        assert len(results) == 0

    async def test_tombstone_record_exists_after_delete(self, db):
        """A tombstone record should be created for the deleted fact."""
        from sqlalchemy import text as sa_text

        uid = await _create_test_user(db)
        f1 = await _store_test_fact(db, uid)

        await db.soft_delete_fact(f1.id, uid)

        # Verify tombstone exists
        async with db.session() as session:
            result = await session.execute(
                sa_text(
                    "SELECT fact_id, user_id FROM tombstones WHERE fact_id = :fid"
                ),
                {"fid": f1.id},
            )
            row = result.fetchone()
            assert row is not None
            assert row.fact_id == f1.id
            assert row.user_id == uid

    async def test_soft_delete_preserves_fact_record(self, db):
        """Soft delete sets is_active=false but the row still exists."""
        uid = await _create_test_user(db)
        f1 = await _store_test_fact(db, uid)

        await db.soft_delete_fact(f1.id, uid)

        # The fact row should still exist but be inactive
        fact = await db.get_fact_by_id(f1.id, uid)
        assert fact is not None
        assert fact.is_active is False

    async def test_soft_delete_does_not_affect_other_facts(self, db):
        """Deleting one fact should not affect other facts for the same user."""
        uid = await _create_test_user(db)
        idx = _hex64()

        f1 = await _store_test_fact(db, uid, blind_indices=[idx])
        f2 = await _store_test_fact(db, uid, blind_indices=[idx])

        await db.soft_delete_fact(f1.id, uid)

        results, total = await db.search_facts_by_blind_indices(
            user_id=uid, trapdoors=[idx]
        )
        assert total == 1
        assert results[0].id == f2.id

    async def test_active_fact_count_after_delete(self, db):
        """Active fact count should decrease by one after soft delete."""
        uid = await _create_test_user(db)

        f1 = await _store_test_fact(db, uid)
        await _store_test_fact(db, uid)

        assert await db.count_active_facts(uid) == 2

        await db.soft_delete_fact(f1.id, uid)

        assert await db.count_active_facts(uid) == 1


# ===================================================================
# (f) Delta Sync Ordering
# ===================================================================

class TestDeltaSyncOrdering:
    """Verify get_facts_since_sequence returns correct facts in order."""

    async def test_delta_sync_returns_only_newer_facts(self, db):
        """Only facts with sequence_id > since_sequence are returned."""
        uid = await _create_test_user(db)

        batch_1 = []
        for _ in range(3):
            f = await _store_test_fact(db, uid)
            batch_1.append(f)

        # Record the sequence boundary
        mid_seq = batch_1[-1].sequence_id

        batch_2 = []
        for _ in range(3):
            f = await _store_test_fact(db, uid)
            batch_2.append(f)

        # Fetch only facts after mid_seq
        facts, latest_seq, has_more = await db.get_facts_since_sequence(
            user_id=uid, since_sequence=mid_seq
        )

        returned_ids = {f.id for f in facts}
        batch_1_ids = {f.id for f in batch_1}
        batch_2_ids = {f.id for f in batch_2}

        assert returned_ids == batch_2_ids
        assert returned_ids.isdisjoint(batch_1_ids)
        assert has_more is False

    async def test_delta_sync_ascending_sequence_order(self, db):
        """Returned facts must be ordered by sequence_id ASC."""
        uid = await _create_test_user(db)

        for _ in range(5):
            await _store_test_fact(db, uid)

        facts, _, _ = await db.get_facts_since_sequence(
            user_id=uid, since_sequence=0
        )

        seq_ids = [f.sequence_id for f in facts]
        assert seq_ids == sorted(seq_ids), f"Not in ascending order: {seq_ids}"

    async def test_delta_sync_has_more_flag(self, db):
        """When more facts exist than the limit, has_more should be True."""
        uid = await _create_test_user(db)

        for _ in range(5):
            await _store_test_fact(db, uid)

        facts, latest_seq, has_more = await db.get_facts_since_sequence(
            user_id=uid, since_sequence=0, limit=3
        )

        assert len(facts) == 3
        assert has_more is True

    async def test_delta_sync_latest_sequence_reflects_all(self, db):
        """latest_seq should reflect the max sequence_id for the user,
        even when limit truncates the result set."""
        uid = await _create_test_user(db)

        all_facts = []
        for _ in range(5):
            f = await _store_test_fact(db, uid)
            all_facts.append(f)

        max_seq = max(f.sequence_id for f in all_facts)

        facts, latest_seq, _ = await db.get_facts_since_sequence(
            user_id=uid, since_sequence=0, limit=2
        )

        assert len(facts) == 2
        assert latest_seq == max_seq

    async def test_delta_sync_includes_soft_deleted_facts(self, db):
        """Delta sync returns ALL facts (including inactive) for replication."""
        uid = await _create_test_user(db)

        f1 = await _store_test_fact(db, uid)
        f2 = await _store_test_fact(db, uid)

        # Soft delete f1
        await db.soft_delete_fact(f1.id, uid)

        # Delta sync should still include f1 (is_active=false)
        facts, _, _ = await db.get_facts_since_sequence(
            user_id=uid, since_sequence=0
        )

        returned_ids = {f.id for f in facts}
        assert f1.id in returned_ids
        assert f2.id in returned_ids

    async def test_delta_sync_user_isolation(self, db):
        """Delta sync should only return facts for the specified user."""
        uid_a = await _create_test_user(db)
        uid_b = await _create_test_user(db)

        for _ in range(3):
            await _store_test_fact(db, uid_a)
        for _ in range(2):
            await _store_test_fact(db, uid_b)

        facts_a, _, _ = await db.get_facts_since_sequence(
            user_id=uid_a, since_sequence=0
        )
        facts_b, _, _ = await db.get_facts_since_sequence(
            user_id=uid_b, since_sequence=0
        )

        assert len(facts_a) == 3
        assert len(facts_b) == 2
        assert all(f.user_id == uid_a for f in facts_a)
        assert all(f.user_id == uid_b for f in facts_b)
