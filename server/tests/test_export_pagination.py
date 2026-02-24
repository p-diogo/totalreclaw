"""
Tests for cursor-based pagination on the /export endpoint.

Tests are standalone (no DB needed) and validate:
- Default pagination parameters
- Custom limit and cursor
- Empty results
- Max limit enforcement
- Response shape (cursor, has_more, total_count)
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_mock_fact(fact_id, idx=0):
    """Create a mock Fact object for testing."""
    return MagicMock(
        id=fact_id,
        user_id="test-user",
        encrypted_blob=b"\xaa\xbb\xcc" * 10,
        blind_indices=["idx1", "idx2"],
        decay_score=0.9 - (idx * 0.1),
        is_active=True,
        version=1,
        source="test",
        created_at=datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestExportPagination:
    """Tests for /export endpoint pagination behavior."""

    def test_export_returns_pagination_fields(self, client, mock_db):
        """Export response must include cursor, has_more, total_count."""
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=([], None, False, 0))

        response = client.get(
            "/v1/export",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cursor" in data
        assert "has_more" in data
        assert "total_count" in data
        assert "facts" in data

    def test_export_first_page(self, client, mock_db):
        """First page of export (no cursor) returns facts and pagination info."""
        facts = [_make_mock_fact(f"fact-{i}", i) for i in range(3)]
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=(facts, "fact-2", True, 10))

        response = client.get(
            "/v1/export",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["facts"]) == 3
        assert data["cursor"] == "fact-2"
        assert data["has_more"] is True
        assert data["total_count"] == 10

    def test_export_next_page_with_cursor(self, client, mock_db):
        """Passing cursor returns the next page of results."""
        facts = [_make_mock_fact(f"fact-{i+3}", i) for i in range(3)]
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=(facts, "fact-5", True, 10))

        response = client.get(
            "/v1/export?cursor=fact-2",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["facts"]) == 3
        assert data["cursor"] == "fact-5"
        assert data["has_more"] is True

        # Verify get_facts_paginated was called with the cursor
        mock_db.get_facts_paginated.assert_called_once()
        _, kwargs = mock_db.get_facts_paginated.call_args
        assert kwargs.get("cursor") == "fact-2"

    def test_export_last_page(self, client, mock_db):
        """Last page returns has_more=False and cursor=None."""
        facts = [_make_mock_fact("fact-last", 0)]
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=(facts, None, False, 1))

        response = client.get(
            "/v1/export?cursor=some-prev-cursor",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["facts"]) == 1
        assert data["cursor"] is None
        assert data["has_more"] is False
        assert data["total_count"] == 1

    def test_export_empty_results(self, client, mock_db):
        """Export for a user with no facts returns empty list."""
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=([], None, False, 0))

        response = client.get(
            "/v1/export",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["facts"] == []
        assert data["cursor"] is None
        assert data["has_more"] is False
        assert data["total_count"] == 0

    def test_export_custom_limit(self, client, mock_db):
        """Custom limit parameter is respected."""
        facts = [_make_mock_fact(f"fact-{i}", i) for i in range(2)]
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=(facts, "fact-1", True, 10))

        response = client.get(
            "/v1/export?limit=2",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["facts"]) == 2

        # Verify the DB was called with limit=2
        _, kwargs = mock_db.get_facts_paginated.call_args
        assert kwargs.get("limit") == 2

    def test_export_max_limit_enforcement(self, client, mock_db):
        """Limit > 5000 should be rejected by FastAPI validation."""
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=([], None, False, 0))

        response = client.get(
            "/v1/export?limit=10000",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        # FastAPI Query(le=5000) should return 422
        assert response.status_code == 422

    def test_export_zero_limit_rejected(self, client, mock_db):
        """Limit of 0 should be rejected by FastAPI validation."""
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))

        response = client.get(
            "/v1/export?limit=0",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 422

    def test_export_negative_limit_rejected(self, client, mock_db):
        """Negative limit should be rejected by FastAPI validation."""
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))

        response = client.get(
            "/v1/export?limit=-5",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 422

    def test_export_requires_auth(self, client):
        """Export without auth should return 401."""
        response = client.get("/v1/export")
        assert response.status_code == 401

    def test_export_fact_fields(self, client, mock_db):
        """Each fact in the response must include the expected fields."""
        fact = _make_mock_fact("fact-0")
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test-user", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))
        mock_db.get_facts_paginated = AsyncMock(return_value=([fact], None, False, 1))

        response = client.get(
            "/v1/export",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        assert response.status_code == 200
        data = response.json()
        f = data["facts"][0]
        assert "id" in f
        assert "encrypted_blob" in f
        assert "blind_indices" in f
        assert "decay_score" in f
        assert "version" in f
        assert "source" in f
        assert "created_at" in f
        assert "updated_at" in f


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
