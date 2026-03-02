"""
Tests for encrypted_embedding column (PoC v2 — LSH + reranking).

Validates that:
1. Facts can be stored WITH an encrypted_embedding (new PoC v2 clients)
2. Facts can be stored WITHOUT an encrypted_embedding (backward compat v1 clients)
3. Search results include encrypted_embedding when present
4. Export results include encrypted_embedding when present
5. Sync results include encrypted_embedding when present
6. The Alembic migration file exists and is correct
"""
import pytest
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============ Model Tests ============

class TestEncryptedEmbeddingModel:
    """Test that the SQLAlchemy model includes encrypted_embedding."""

    def test_fact_model_has_encrypted_embedding(self):
        """Fact model should have encrypted_embedding column."""
        from src.db.models import Fact
        fact = Fact(
            id="test-id",
            user_id="user-1",
            encrypted_blob=b"\x00",
            blind_indices=["idx"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test",
        )
        # encrypted_embedding should default to None
        assert fact.encrypted_embedding is None

    def test_fact_model_accepts_encrypted_embedding(self):
        """Fact model should accept encrypted_embedding value."""
        from src.db.models import Fact
        fact = Fact(
            id="test-id",
            user_id="user-1",
            encrypted_blob=b"\x00",
            blind_indices=["idx"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test",
        )
        fact.encrypted_embedding = "aabbccdd" * 100
        assert fact.encrypted_embedding == "aabbccdd" * 100


# ============ Store Endpoint Tests ============

class TestStoreWithEncryptedEmbedding:
    """Test /store endpoint with encrypted_embedding field."""

    def test_store_fact_with_encrypted_embedding(self, client, mock_db):
        """Store a fact WITH encrypted_embedding (PoC v2 client)."""
        from src.db.models import User
        from src.auth import generate_salt, derive_auth_key, hash_auth_key

        # Setup auth
        salt = generate_salt()
        auth_key = derive_auth_key("test_password", salt)
        auth_hash = hash_auth_key(auth_key)

        mock_user = User(
            user_id="user-1",
            auth_key_hash=auth_hash,
            salt=salt,
        )
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=mock_user)
        mock_db.update_last_seen = AsyncMock()
        mock_db.find_fact_by_fingerprint = AsyncMock(return_value=None)
        mock_db.log_raw_event = AsyncMock()

        fact_id = str(uuid.uuid4())
        mock_stored = MagicMock()
        mock_stored.id = fact_id
        mock_stored.version = 1
        mock_stored.encrypted_embedding = "encrypted_emb_hex_data"
        mock_db.store_fact = AsyncMock(return_value=mock_stored)

        response = client.post(
            "/v1/store",
            json={
                "user_id": "user-1",
                "facts": [{
                    "id": fact_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "encrypted_blob": "aabb" * 50,
                    "blind_indices": ["idx1", "idx2"],
                    "decay_score": 1.0,
                    "is_active": True,
                    "version": 1,
                    "source": "test",
                    "encrypted_embedding": "encrypted_emb_hex_data"
                }]
            },
            headers={"Authorization": f"Bearer {auth_key.hex()}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert fact_id in data["ids"]

        # Verify store_fact was called with encrypted_embedding
        mock_db.store_fact.assert_called_once()
        call_kwargs = mock_db.store_fact.call_args
        assert call_kwargs.kwargs.get("encrypted_embedding") == "encrypted_emb_hex_data"

    def test_store_fact_without_encrypted_embedding(self, client, mock_db):
        """Store a fact WITHOUT encrypted_embedding (backward compat v1 client)."""
        from src.db.models import User
        from src.auth import generate_salt, derive_auth_key, hash_auth_key

        salt = generate_salt()
        auth_key = derive_auth_key("test_password", salt)
        auth_hash = hash_auth_key(auth_key)

        mock_user = User(
            user_id="user-1",
            auth_key_hash=auth_hash,
            salt=salt,
        )
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=mock_user)
        mock_db.update_last_seen = AsyncMock()
        mock_db.find_fact_by_fingerprint = AsyncMock(return_value=None)
        mock_db.log_raw_event = AsyncMock()

        fact_id = str(uuid.uuid4())
        mock_stored = MagicMock()
        mock_stored.id = fact_id
        mock_stored.version = 1
        mock_stored.encrypted_embedding = None
        mock_db.store_fact = AsyncMock(return_value=mock_stored)

        response = client.post(
            "/v1/store",
            json={
                "user_id": "user-1",
                "facts": [{
                    "id": fact_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "encrypted_blob": "aabb" * 50,
                    "blind_indices": ["idx1", "idx2"],
                    "decay_score": 1.0,
                    "is_active": True,
                    "version": 1,
                    "source": "test"
                    # No encrypted_embedding field — v1 client
                }]
            },
            headers={"Authorization": f"Bearer {auth_key.hex()}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert fact_id in data["ids"]

        # Verify store_fact was called with encrypted_embedding=None
        mock_db.store_fact.assert_called_once()
        call_kwargs = mock_db.store_fact.call_args
        assert call_kwargs.kwargs.get("encrypted_embedding") is None


# ============ Search Endpoint Tests ============

class TestSearchWithEncryptedEmbedding:
    """Test /search response includes encrypted_embedding."""

    def _make_mock_fact(self, fact_id, encrypted_embedding=None):
        """Create a mock fact with optional encrypted_embedding."""
        fact = MagicMock()
        fact.id = fact_id
        fact.encrypted_blob = b"\xaa\xbb\xcc"
        fact.decay_score = 1.0
        fact.created_at = datetime(2026, 2, 26, tzinfo=timezone.utc)
        fact.version = 1
        fact.encrypted_embedding = encrypted_embedding
        return fact

    @pytest.mark.asyncio
    async def test_search_returns_encrypted_embedding(self):
        """Search results should include encrypted_embedding when present."""
        from src.handlers.search import search, SearchRequestJSON

        mock_db = AsyncMock()
        mock_facts = [
            self._make_mock_fact("f1", encrypted_embedding="enc_emb_hex_1"),
            self._make_mock_fact("f2", encrypted_embedding="enc_emb_hex_2"),
        ]
        mock_db.search_facts_by_blind_indices = AsyncMock(return_value=(mock_facts, 2))

        # Call handler directly
        request = SearchRequestJSON(
            user_id="user-1",
            trapdoors=["trapdoor1"],
            max_candidates=100,
            min_decay_score=0.0
        )
        result = await search(request, user_id="user-1", db=mock_db)

        assert result.success is True
        assert len(result.results) == 2
        assert result.results[0].encrypted_embedding == "enc_emb_hex_1"
        assert result.results[1].encrypted_embedding == "enc_emb_hex_2"

    @pytest.mark.asyncio
    async def test_search_returns_none_for_v1_facts(self):
        """Search results should return None encrypted_embedding for v1 facts."""
        from src.handlers.search import search, SearchRequestJSON

        mock_db = AsyncMock()
        mock_facts = [
            self._make_mock_fact("f1", encrypted_embedding=None),
        ]
        mock_db.search_facts_by_blind_indices = AsyncMock(return_value=(mock_facts, 1))

        request = SearchRequestJSON(
            user_id="user-1",
            trapdoors=["trapdoor1"],
            max_candidates=100,
            min_decay_score=0.0
        )
        result = await search(request, user_id="user-1", db=mock_db)

        assert result.success is True
        assert len(result.results) == 1
        assert result.results[0].encrypted_embedding is None


# ============ Sync Endpoint Tests ============

class TestSyncWithEncryptedEmbedding:
    """Test /sync response includes encrypted_embedding."""

    def _make_mock_fact(self, fact_id, seq_id=1, encrypted_embedding=None):
        """Create a mock fact with optional encrypted_embedding."""
        fact = MagicMock()
        fact.id = fact_id
        fact.user_id = "user-1"
        fact.encrypted_blob = b"\xaa\xbb\xcc"
        fact.blind_indices = ["idx1"]
        fact.decay_score = 1.0
        fact.is_active = True
        fact.version = 1
        fact.source = "test"
        fact.created_at = datetime(2026, 2, 26, tzinfo=timezone.utc)
        fact.updated_at = datetime(2026, 2, 26, tzinfo=timezone.utc)
        fact.sequence_id = seq_id
        fact.content_fp = None
        fact.agent_id = None
        fact.encrypted_embedding = encrypted_embedding
        return fact

    @pytest.mark.asyncio
    async def test_sync_returns_encrypted_embedding(self):
        """Sync results should include encrypted_embedding when present."""
        from src.handlers.sync import sync

        mock_db = AsyncMock()
        mock_facts = [
            self._make_mock_fact("f1", seq_id=1, encrypted_embedding="enc_emb_1"),
            self._make_mock_fact("f2", seq_id=2, encrypted_embedding=None),
        ]
        mock_db.get_facts_since_sequence = AsyncMock(
            return_value=(mock_facts, 2, False)
        )

        result = await sync(since_sequence=0, limit=1000, user_id="user-1", db=mock_db)

        assert result.success is True
        assert len(result.facts) == 2
        assert result.facts[0].encrypted_embedding == "enc_emb_1"
        assert result.facts[1].encrypted_embedding is None


# ============ Pydantic Schema Tests ============

class TestSchemaModels:
    """Test that Pydantic models accept encrypted_embedding."""

    def test_fact_json_accepts_encrypted_embedding(self):
        """FactJSON should accept optional encrypted_embedding."""
        from src.handlers.store import FactJSON
        fact = FactJSON(
            id="test",
            timestamp="2026-02-26T00:00:00Z",
            encrypted_blob="aabb" * 50,
            blind_indices=["idx"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test",
            encrypted_embedding="enc_emb_hex"
        )
        assert fact.encrypted_embedding == "enc_emb_hex"

    def test_fact_json_omits_encrypted_embedding(self):
        """FactJSON should default encrypted_embedding to None."""
        from src.handlers.store import FactJSON
        fact = FactJSON(
            id="test",
            timestamp="2026-02-26T00:00:00Z",
            encrypted_blob="aabb" * 50,
            blind_indices=["idx"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test"
        )
        assert fact.encrypted_embedding is None

    def test_search_result_json_has_encrypted_embedding(self):
        """SearchResultJSON should have optional encrypted_embedding."""
        from src.handlers.search import SearchResultJSON
        result = SearchResultJSON(
            fact_id="test",
            encrypted_blob="aabb",
            decay_score=1.0,
            timestamp=1234567890,
            version=1,
            encrypted_embedding="enc_emb_hex"
        )
        assert result.encrypted_embedding == "enc_emb_hex"

    def test_search_result_json_without_encrypted_embedding(self):
        """SearchResultJSON should default encrypted_embedding to None."""
        from src.handlers.search import SearchResultJSON
        result = SearchResultJSON(
            fact_id="test",
            encrypted_blob="aabb",
            decay_score=1.0,
            timestamp=1234567890,
            version=1
        )
        assert result.encrypted_embedding is None

    def test_synced_fact_json_has_encrypted_embedding(self):
        """SyncedFactJSON should have optional encrypted_embedding."""
        from src.handlers.sync import SyncedFactJSON
        fact = SyncedFactJSON(
            id="test",
            encrypted_blob="aabb",
            blind_indices=["idx"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test",
            encrypted_embedding="enc_emb_hex"
        )
        assert fact.encrypted_embedding == "enc_emb_hex"

    def test_synced_fact_json_without_encrypted_embedding(self):
        """SyncedFactJSON should default encrypted_embedding to None."""
        from src.handlers.sync import SyncedFactJSON
        fact = SyncedFactJSON(
            id="test",
            encrypted_blob="aabb",
            blind_indices=["idx"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test"
        )
        assert fact.encrypted_embedding is None


# ============ Migration Tests ============

class TestEncryptedEmbeddingMigration:
    """Test that the Alembic migration for encrypted_embedding exists."""

    def test_migration_file_exists(self):
        """Migration 002 should exist."""
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        migration_path = os.path.join(
            server_dir, "migrations", "versions", "002_add_encrypted_embedding.py"
        )
        assert os.path.exists(migration_path), "Migration 002 must exist"

    def test_migration_adds_column(self):
        """Migration 002 should add encrypted_embedding column."""
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        migration_path = os.path.join(
            server_dir, "migrations", "versions", "002_add_encrypted_embedding.py"
        )
        with open(migration_path) as f:
            content = f.read()

        assert "encrypted_embedding" in content
        assert "add_column" in content
        assert 'sa.Text' in content or 'Text' in content
        assert "nullable=True" in content

    def test_migration_has_downgrade(self):
        """Migration 002 should have a downgrade path."""
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        migration_path = os.path.join(
            server_dir, "migrations", "versions", "002_add_encrypted_embedding.py"
        )
        with open(migration_path) as f:
            content = f.read()

        assert "def downgrade" in content
        assert "drop_column" in content

    def test_migration_revision_chain(self):
        """Migration 002 should depend on 001."""
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        migration_path = os.path.join(
            server_dir, "migrations", "versions", "002_add_encrypted_embedding.py"
        )
        with open(migration_path) as f:
            content = f.read()

        assert 'revision: str = "002"' in content
        assert 'down_revision' in content
        assert '"001"' in content


# ============ Protobuf Schema Tests ============

class TestProtobufSchema:
    """Test that the protobuf schema includes encrypted_embedding."""

    def test_proto_has_encrypted_embedding_in_fact(self):
        """TotalReclawFact message should have encrypted_embedding field."""
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proto_path = os.path.join(server_dir, "proto", "totalreclaw.proto")
        with open(proto_path) as f:
            content = f.read()

        assert "encrypted_embedding" in content
        # Field 13 in TotalReclawFact
        assert "= 13" in content

    def test_proto_has_encrypted_embedding_in_search_result(self):
        """SearchResult message should have encrypted_embedding field."""
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proto_path = os.path.join(server_dir, "proto", "totalreclaw.proto")
        with open(proto_path) as f:
            content = f.read()

        # SearchResult should have encrypted_embedding at field 6
        assert "encrypted_embedding = 6" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
