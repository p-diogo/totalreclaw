"""
Shared pytest fixtures for OpenMemory Server tests.

The 'client' fixture creates a FastAPI TestClient. When PostgreSQL is not
running, the app lifespan's init_db() call will fail. We patch init_db and
close_db to no-ops so that unit tests (which use mock_db) can run without
a real database. Integration tests that need a real DB should use the
'test_db' fixture directly.
"""
import os
import sys
import pytest
import asyncio
from typing import AsyncGenerator
from datetime import datetime, timezone
import uuid
from unittest.mock import AsyncMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from httpx import AsyncClient

# Import after path setup
from src.auth import (
    generate_salt,
    derive_auth_key,
    hash_auth_key,
    generate_user_id
)
from src.db import Database, init_db, close_db, get_db


# ============ Test Database Setup ============

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://openmemory:dev@localhost:5432/openmemory_test"
)


def _postgres_is_available() -> bool:
    """Quick check whether PostgreSQL is reachable."""
    try:
        import socket
        s = socket.create_connection(("localhost", 5432), timeout=1)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_db():
    """Initialize test database (requires running PostgreSQL)."""
    if not _postgres_is_available():
        pytest.skip("PostgreSQL is not running -- skipping integration test")
    db = Database(TEST_DATABASE_URL)
    await db.init()
    yield db
    await db.close()


# ============ Test Client ============

class _DefaultMockDB:
    """Minimal mock DB that returns auth-failure for all lookups.

    Provides a fallback so that endpoints can resolve get_db() even
    when no real database is available. Tests that need specific DB
    behavior should use the mock_db fixture to override.
    """
    async def get_user_by_auth_hash(self, auth_hash):
        return None

    async def create_user(self, user_id, auth_hash, salt):
        return type("User", (), {
            "user_id": user_id,
            "auth_key_hash": auth_hash,
            "salt": salt
        })()

    async def store_fact(self, **kwargs):
        return type("Fact", (), {
            "id": kwargs.get("fact_id"),
            "version": 1
        })()

    async def search_facts_by_blind_indices(self, **kwargs):
        return []

    async def update_last_seen(self, user_id):
        pass

    async def health_check(self):
        return {"status": "connected"}

    async def log_raw_event(self, user_id, event_bytes):
        pass

    async def soft_delete_user(self, user_id):
        return True

    async def soft_delete_fact(self, fact_id, user_id):
        return True

    async def get_all_facts(self, user_id):
        return []

    async def get_facts_paginated(self, user_id, limit=1000, cursor=None):
        return [], None, False, 0

    async def find_fact_by_fingerprint(self, user_id, content_fp):
        return None

    async def get_facts_since_sequence(self, user_id, since_sequence, limit=1000):
        return [], 0, False


def _patch_all_get_db(monkeypatch_or_patcher, mock):
    """Patch get_db everywhere it's used to return mock.

    We patch both the canonical source (src.db.database) and the
    re-exports (src.db), plus each handler module that imports it.
    This ensures FastAPI's Depends(get_db) resolves correctly.
    """
    modules = [
        "src.db.database",
        "src.db",
        "src.dependencies",
        "src.handlers.store",
        "src.handlers.search",
        "src.handlers.register",
        "src.handlers.health",
        "src.handlers.account",
    ]
    optional_modules = [
        "src.handlers.sync",
    ]

    for mod in modules:
        monkeypatch_or_patcher(f"{mod}.get_db", lambda: mock)
    for mod in optional_modules:
        try:
            monkeypatch_or_patcher(f"{mod}.get_db", lambda: mock)
        except Exception:
            pass


@pytest.fixture
def client(monkeypatch):
    """Create a test client.

    Patches init_db/close_db to no-ops so the app lifespan doesn't
    require a running PostgreSQL instance. Also installs a default
    mock DB so that dependency injection doesn't raise RuntimeError.
    Tests that need specific DB behavior should use the mock_db fixture.
    """
    from src import main as main_module
    from src.db import database as db_module

    async def _noop_init(url=None):
        pass

    async def _noop_close():
        pass

    # Install default mock DB at the source level so get_db() works
    default_mock = _DefaultMockDB()
    _patch_all_get_db(monkeypatch.setattr, default_mock)
    # Also set the global _db so the original get_db function returns our mock
    monkeypatch.setattr(db_module, "_db", default_mock)

    with patch.object(main_module, "init_db", side_effect=_noop_init), \
         patch.object(main_module, "close_db", side_effect=_noop_close):
        with TestClient(main_module.app) as c:
            yield c


@pytest.fixture
async def async_client(monkeypatch):
    """Create an async test client."""
    from src import main as main_module
    from src.db import database as db_module

    async def _noop_init(url=None):
        pass

    async def _noop_close():
        pass

    default_mock = _DefaultMockDB()
    _patch_all_get_db(monkeypatch.setattr, default_mock)
    monkeypatch.setattr(db_module, "_db", default_mock)

    with patch.object(main_module, "init_db", side_effect=_noop_init), \
         patch.object(main_module, "close_db", side_effect=_noop_close):
        async with AsyncClient(app=main_module.app, base_url="http://test") as c:
            yield c


# ============ User Fixtures ============

@pytest.fixture
def test_user(test_db):
    """Create a test user and return credentials (requires running PostgreSQL)."""
    # Generate credentials
    master_password = "test_master_password_123"
    salt = generate_salt()
    auth_key = derive_auth_key(master_password, salt)
    auth_key_hash = hash_auth_key(auth_key)
    user_id = generate_user_id()

    # Store in database
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        test_db.create_user(user_id, auth_key_hash, salt)
    )

    return {
        "user_id": user_id,
        "auth_key": auth_key,
        "salt": salt,
        "master_password": master_password
    }


@pytest.fixture
def test_user_headers(test_user):
    """Return auth headers for test user."""
    return {"Authorization": f"Bearer {test_user['auth_key'].hex()}"}


# ============ Fact Fixtures ============

@pytest.fixture
def sample_fact():
    """Create a sample fact for testing."""
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "encrypted_blob": "a1b2c3d4e5f6" + "00" * 100,
        "blind_indices": ["abc123", "def456"],
        "decay_score": 1.0,
        "is_active": True,
        "version": 1,
        "source": "test"
    }


@pytest.fixture
def stored_fact(client, test_user_headers, sample_fact):
    """Store a fact and return it."""
    response = client.post(
        "/v1/store",
        json={"user_id": "test_user_123", "facts": [sample_fact]},
        headers=test_user_headers
    )
    assert response.status_code == 200
    return sample_fact


@pytest.fixture
def multiple_stored_facts(client, test_user_headers):
    """Store multiple facts and return them."""
    facts = []
    for i in range(5):
        fact = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "encrypted_blob": f"blob_{i}" + "00" * 50,
            "blind_indices": [f"index_{i}"],
            "decay_score": 1.0 - (i * 0.1),
            "is_active": True,
            "version": 1,
            "source": "test"
        }
        facts.append(fact)

    response = client.post(
        "/v1/store",
        json={"user_id": "test_user_123", "facts": facts},
        headers=test_user_headers
    )
    assert response.status_code == 200
    return facts


# ============ Mock Fixtures ============

@pytest.fixture
def mock_db(monkeypatch):
    """Mock database for unit tests without DB dependency.

    Returns the mock instance so tests can customize behavior
    (e.g., mock_db.get_user_by_auth_hash = AsyncMock(...)).
    Overrides the default mock installed by the client fixture.
    """
    from src.db import database as db_module

    mock = _DefaultMockDB()
    _patch_all_get_db(monkeypatch.setattr, mock)
    # Override the global _db so get_db() returns this mock
    monkeypatch.setattr(db_module, "_db", mock)
    return mock
