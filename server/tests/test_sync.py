"""
Tests for GET /sync endpoint (v0.3.1b delta sync).

Spec: docs/specs/totalreclaw/server.md v0.3.1b section 4, 8.2

Unit tests using mocked database to validate sync handler logic.
"""
import pytest
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.handlers.sync import SyncedFactJSON, SyncResponseJSON


class TestSyncModels:
    """Test that v0.3.1b sync pydantic models are correct."""

    def test_synced_fact_json_model(self):
        """SyncedFactJSON should accept all v0.3.1b fields."""
        fact = SyncedFactJSON(
            id="fact-1",
            sequence_id=42,
            encrypted_blob="aabb",
            blind_indices=["idx1", "idx2"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test",
            content_fp="ddeeff00" * 8,
            agent_id="agent-1",
            created_at="2026-02-24T12:00:00",
            updated_at="2026-02-24T12:00:00",
        )
        assert fact.id == "fact-1"
        assert fact.sequence_id == 42
        assert fact.content_fp == "ddeeff00" * 8
        assert fact.agent_id == "agent-1"

    def test_synced_fact_json_optional_fields(self):
        """SyncedFactJSON optional fields should default to None."""
        fact = SyncedFactJSON(
            id="fact-1",
            encrypted_blob="aabb",
            blind_indices=["idx1"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test",
        )
        assert fact.sequence_id is None
        assert fact.content_fp is None
        assert fact.agent_id is None

    def test_sync_response_json_model(self):
        """SyncResponseJSON should include facts, latest_sequence, has_more."""
        resp = SyncResponseJSON(
            success=True,
            facts=[],
            latest_sequence=100,
            has_more=False,
        )
        assert resp.success is True
        assert resp.latest_sequence == 100
        assert resp.has_more is False
        assert resp.facts == []


class TestSyncHandler:
    """Test the sync endpoint handler logic."""

    def _make_mock_fact(self, fact_id, seq_id=1, content_fp=None, agent_id=None, encrypted_embedding=None):
        """Create a mock Fact object."""
        fact = MagicMock()
        fact.id = fact_id
        fact.user_id = "user-1"
        fact.encrypted_blob = b"\xaa\xbb\xcc"
        fact.blind_indices = ["idx1"]
        fact.decay_score = 1.0
        fact.is_active = True
        fact.version = 1
        fact.source = "test"
        fact.created_at = datetime(2026, 2, 24, tzinfo=timezone.utc)
        fact.updated_at = datetime(2026, 2, 24, tzinfo=timezone.utc)
        fact.sequence_id = seq_id
        fact.content_fp = content_fp
        fact.agent_id = agent_id
        fact.encrypted_embedding = encrypted_embedding
        return fact

    @pytest.mark.asyncio
    async def test_sync_returns_facts(self):
        """sync handler returns facts from get_facts_since_sequence."""
        from src.handlers.sync import sync

        mock_db = AsyncMock()
        mock_facts = [
            self._make_mock_fact("f1", seq_id=1, agent_id="agent-a"),
            self._make_mock_fact("f2", seq_id=2, agent_id="agent-b"),
        ]
        mock_db.get_facts_since_sequence = AsyncMock(
            return_value=(mock_facts, 2, False)
        )

        result = await sync(
            since_sequence=0,
            limit=1000,
            user_id="user-1",
            db=mock_db
        )

        assert result.success is True
        assert len(result.facts) == 2
        assert result.latest_sequence == 2
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_sync_passes_since_sequence(self):
        """sync handler passes since_sequence to the DB query."""
        from src.handlers.sync import sync

        mock_db = AsyncMock()
        mock_db.get_facts_since_sequence = AsyncMock(
            return_value=([], 0, False)
        )

        await sync(since_sequence=42, limit=1000, user_id="user-1", db=mock_db)

        mock_db.get_facts_since_sequence.assert_called_once_with(
            user_id="user-1",
            since_sequence=42,
            limit=1000
        )

    @pytest.mark.asyncio
    async def test_sync_has_more_pagination(self):
        """When DB returns has_more=True, response should reflect it."""
        from src.handlers.sync import sync

        mock_db = AsyncMock()
        mock_facts = [self._make_mock_fact("f1", seq_id=1)]
        mock_db.get_facts_since_sequence = AsyncMock(
            return_value=(mock_facts, 5, True)
        )

        result = await sync(since_sequence=0, limit=1, user_id="user-1", db=mock_db)

        assert result.success is True
        assert result.has_more is True
        assert result.latest_sequence == 5

    @pytest.mark.asyncio
    async def test_sync_empty_when_no_facts(self):
        """Sync with no matching facts returns empty list."""
        from src.handlers.sync import sync

        mock_db = AsyncMock()
        mock_db.get_facts_since_sequence = AsyncMock(
            return_value=([], 0, False)
        )

        result = await sync(since_sequence=999999, limit=1000, user_id="user-1", db=mock_db)

        assert result.success is True
        assert len(result.facts) == 0
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_sync_includes_metadata(self):
        """Synced facts include content_fp, agent_id, blind_indices."""
        from src.handlers.sync import sync

        mock_db = AsyncMock()
        mock_fact = self._make_mock_fact(
            "f1", seq_id=10, content_fp="fp-abc", agent_id="agent-sync"
        )
        mock_db.get_facts_since_sequence = AsyncMock(
            return_value=([mock_fact], 10, False)
        )

        result = await sync(since_sequence=0, limit=1000, user_id="user-1", db=mock_db)

        assert len(result.facts) == 1
        fact = result.facts[0]
        assert fact.content_fp == "fp-abc"
        assert fact.agent_id == "agent-sync"
        assert fact.sequence_id == 10
        assert fact.encrypted_blob == "aabbcc"  # hex of b"\xaa\xbb\xcc"
        assert fact.blind_indices == ["idx1"]

    @pytest.mark.asyncio
    async def test_sync_error_handled(self):
        """Database errors are caught and returned gracefully."""
        from src.handlers.sync import sync

        mock_db = AsyncMock()
        mock_db.get_facts_since_sequence = AsyncMock(
            side_effect=RuntimeError("DB connection failed")
        )

        result = await sync(since_sequence=0, limit=1000, user_id="user-1", db=mock_db)

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
