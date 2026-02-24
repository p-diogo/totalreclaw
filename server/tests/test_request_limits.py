"""
Tests for request size limits.
"""
import pytest
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRequestSizeLimits:
    """Tests for request body and field size validation.

    These tests verify that Pydantic model validation enforces size limits.
    When auth is not mocked, auth failure (401) may precede validation (422),
    so both are accepted. The key assertion is that oversized requests
    never succeed (200 with success=True).
    """

    def test_encrypted_blob_max_1mb(self, client, mock_db):
        """Encrypted blob must be rejected if > 1MB (2MB hex = 1MB binary)."""
        from unittest.mock import AsyncMock, MagicMock
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))

        oversized_blob = "aa" * (1024 * 1024 + 1)  # 1MB + 1 byte, hex-encoded
        fact = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "encrypted_blob": oversized_blob,
            "blind_indices": ["abc123"],
            "decay_score": 1.0,
            "is_active": True,
            "version": 1,
            "source": "test"
        }
        response = client.post(
            "/v1/store",
            json={"user_id": "test", "facts": [fact]},
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        # Should fail validation (422 from Pydantic) or fail with error in body
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
        else:
            assert response.status_code == 422

    def test_blind_indices_max_1000_items(self, client, mock_db):
        """blind_indices array must be rejected if > 1000 items."""
        from unittest.mock import AsyncMock, MagicMock
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))

        fact = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "encrypted_blob": "aabb" * 10,
            "blind_indices": [f"index_{i}" for i in range(1001)],
            "decay_score": 1.0,
            "is_active": True,
            "version": 1,
            "source": "test"
        }
        response = client.post(
            "/v1/store",
            json={"user_id": "test", "facts": [fact]},
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
        else:
            assert response.status_code == 422

    def test_trapdoors_max_1000_in_search(self, client, mock_db):
        """Search trapdoors list must be rejected if > 1000 items."""
        from unittest.mock import AsyncMock, MagicMock
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))

        response = client.post(
            "/v1/search",
            json={
                "user_id": "test",
                "trapdoors": [f"trap_{i}" for i in range(1001)],
                "max_candidates": 100
            },
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
        else:
            assert response.status_code == 422

    def test_max_facts_per_store_request(self, client, mock_db):
        """A single /store request must not accept more than 500 facts."""
        from unittest.mock import AsyncMock, MagicMock
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test", auth_key_hash=b'\xaa' * 32, salt=b'\xbb' * 32
        ))

        facts = [
            {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "encrypted_blob": "aabb",
                "blind_indices": ["idx"],
                "decay_score": 1.0,
                "is_active": True,
                "version": 1,
                "source": "test"
            }
            for _ in range(501)
        ]
        response = client.post(
            "/v1/store",
            json={"user_id": "test", "facts": facts},
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
        else:
            assert response.status_code == 422

    def test_valid_sizes_accepted(self, client):
        """Normal-sized requests should not be rejected by size limits."""
        fact = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "encrypted_blob": "aabb" * 100,
            "blind_indices": ["abc123", "def456"],
            "decay_score": 1.0,
            "is_active": True,
            "version": 1,
            "source": "test"
        }
        response = client.post(
            "/v1/store",
            json={"user_id": "test", "facts": [fact]},
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        # Will fail auth (401) but should NOT fail validation (422)
        assert response.status_code in [200, 401]
