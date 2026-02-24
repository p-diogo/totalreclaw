"""
Tests for content fingerprint dedup in /store endpoint (v0.3.1b).

Spec: docs/specs/openmemory/server.md v0.3.1b section 8.2

These are unit tests that test the store handler logic and pydantic models
without requiring a running database.
"""
import pytest
import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.handlers.store import FactJSON, StoreRequestJSON, StoreResponseJSON, ErrorCode


class TestDedupModels:
    """Test that v0.3.1b pydantic models accept fingerprint fields."""

    def test_fact_json_accepts_content_fp(self):
        """FactJSON model must accept content_fp field."""
        fact = FactJSON(
            id="test-id",
            timestamp=datetime.utcnow().isoformat(),
            encrypted_blob="aabb" * 20,
            blind_indices=["idx1"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test",
            content_fp="ddeeff00" * 8,
            agent_id="agent-1"
        )
        assert fact.content_fp == "ddeeff00" * 8
        assert fact.agent_id == "agent-1"

    def test_fact_json_content_fp_is_optional(self):
        """FactJSON model content_fp should be optional."""
        fact = FactJSON(
            id="test-id",
            timestamp=datetime.utcnow().isoformat(),
            encrypted_blob="aabb" * 20,
            blind_indices=["idx1"],
            decay_score=1.0,
            is_active=True,
            version=1,
            source="test"
        )
        assert fact.content_fp is None
        assert fact.agent_id is None

    def test_store_response_has_duplicate_ids(self):
        """StoreResponseJSON must support duplicate_ids field."""
        resp = StoreResponseJSON(
            success=True,
            ids=["id-1"],
            duplicate_ids=["existing-id-1", "existing-id-2"]
        )
        assert resp.duplicate_ids == ["existing-id-1", "existing-id-2"]

    def test_store_response_duplicate_ids_optional(self):
        """StoreResponseJSON duplicate_ids should be optional."""
        resp = StoreResponseJSON(success=True, ids=["id-1"])
        assert resp.duplicate_ids is None

    def test_error_code_has_duplicate_content(self):
        """ErrorCode must have DUPLICATE_CONTENT value."""
        assert hasattr(ErrorCode, "DUPLICATE_CONTENT")
        assert ErrorCode.DUPLICATE_CONTENT == "DUPLICATE_CONTENT"


class TestDedupLogic:
    """Test dedup logic in the store handler using mocked database."""

    def _make_fact_dict(self, content_fp=None, agent_id=None):
        """Helper to create a fact dict with optional v0.3.1b fields."""
        fact = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "encrypted_blob": "a1b2c3d4e5f6" * 20,
            "blind_indices": ["idx_" + str(uuid.uuid4())[:8]],
            "decay_score": 1.0,
            "is_active": True,
            "version": 1,
            "source": "conversation",
        }
        if content_fp is not None:
            fact["content_fp"] = content_fp
        if agent_id is not None:
            fact["agent_id"] = agent_id
        return fact

    @pytest.mark.asyncio
    async def test_store_with_content_fp_calls_find(self):
        """When content_fp is provided, the handler should call find_fact_by_fingerprint."""
        from src.handlers.store import store

        mock_db = AsyncMock()
        mock_db.find_fact_by_fingerprint = AsyncMock(return_value=None)
        mock_db.store_fact = AsyncMock(return_value=MagicMock(version=1))
        mock_db.log_raw_event = AsyncMock()

        fact = self._make_fact_dict(content_fp="aabbccdd" * 8, agent_id="agent-1")
        request = StoreRequestJSON(
            user_id="user-1",
            facts=[FactJSON(**fact)]
        )

        result = await store(request_obj=request, user_id="user-1", db=mock_db)

        assert result.success is True
        assert fact["id"] in result.ids
        mock_db.find_fact_by_fingerprint.assert_called_once_with(
            user_id="user-1",
            content_fp="aabbccdd" * 8
        )

    @pytest.mark.asyncio
    async def test_duplicate_content_fp_skipped(self):
        """When find_fact_by_fingerprint returns an ID, the fact should be skipped."""
        from src.handlers.store import store

        mock_db = AsyncMock()
        mock_db.find_fact_by_fingerprint = AsyncMock(return_value="existing-fact-id")
        mock_db.store_fact = AsyncMock(return_value=MagicMock(version=1))
        mock_db.log_raw_event = AsyncMock()

        fact = self._make_fact_dict(content_fp="ddeeff00" * 8)
        request = StoreRequestJSON(
            user_id="user-1",
            facts=[FactJSON(**fact)]
        )

        result = await store(request_obj=request, user_id="user-1", db=mock_db)

        assert result.success is True
        assert fact["id"] not in (result.ids or [])
        assert "existing-fact-id" in (result.duplicate_ids or [])
        # store_fact should NOT have been called
        mock_db.store_fact.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_content_fp_skips_dedup(self):
        """Facts without content_fp bypass the dedup check entirely."""
        from src.handlers.store import store

        mock_db = AsyncMock()
        mock_db.find_fact_by_fingerprint = AsyncMock()
        mock_db.store_fact = AsyncMock(return_value=MagicMock(version=1))
        mock_db.log_raw_event = AsyncMock()

        fact = self._make_fact_dict()  # no content_fp
        request = StoreRequestJSON(
            user_id="user-1",
            facts=[FactJSON(**fact)]
        )

        result = await store(request_obj=request, user_id="user-1", db=mock_db)

        assert result.success is True
        assert fact["id"] in result.ids
        # find_fact_by_fingerprint should NOT have been called
        mock_db.find_fact_by_fingerprint.assert_not_called()

    @pytest.mark.asyncio
    async def test_mixed_batch_new_and_duplicate(self):
        """A batch with both new and duplicate facts should partially succeed."""
        from src.handlers.store import store

        fp = "aabb0011" * 8

        mock_db = AsyncMock()
        # First call: duplicate found. Second call: no duplicate.
        mock_db.find_fact_by_fingerprint = AsyncMock(
            side_effect=["existing-id", None]
        )
        mock_db.store_fact = AsyncMock(return_value=MagicMock(version=1))
        mock_db.log_raw_event = AsyncMock()

        duplicate_fact = self._make_fact_dict(content_fp=fp)
        new_fact = self._make_fact_dict(content_fp="ccdd2233" * 8)

        request = StoreRequestJSON(
            user_id="user-1",
            facts=[
                FactJSON(**duplicate_fact),
                FactJSON(**new_fact),
            ]
        )

        result = await store(request_obj=request, user_id="user-1", db=mock_db)

        assert result.success is True
        assert new_fact["id"] in result.ids
        assert duplicate_fact["id"] not in (result.ids or [])
        assert "existing-id" in (result.duplicate_ids or [])

    @pytest.mark.asyncio
    async def test_store_passes_content_fp_and_agent_id(self):
        """store_fact should receive content_fp and agent_id from the request."""
        from src.handlers.store import store

        mock_db = AsyncMock()
        mock_db.find_fact_by_fingerprint = AsyncMock(return_value=None)
        mock_db.store_fact = AsyncMock(return_value=MagicMock(version=1))
        mock_db.log_raw_event = AsyncMock()

        fact = self._make_fact_dict(content_fp="1122334455667788" * 4, agent_id="agent-xyz")
        request = StoreRequestJSON(
            user_id="user-1",
            facts=[FactJSON(**fact)]
        )

        await store(request_obj=request, user_id="user-1", db=mock_db)

        call_kwargs = mock_db.store_fact.call_args
        assert call_kwargs.kwargs.get("content_fp") == "1122334455667788" * 4
        assert call_kwargs.kwargs.get("agent_id") == "agent-xyz"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
