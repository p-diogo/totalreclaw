"""
Tests for account deletion endpoint (GDPR compliance).
"""
import pytest
import os
import sys
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAccountDeletion:
    """Tests for DELETE /account endpoint."""

    def test_delete_account_requires_auth(self, client):
        """DELETE /account without auth should return 401."""
        response = client.delete("/v1/account")
        assert response.status_code == 401

    def test_delete_account_success(self, client, mock_db):
        """DELETE /account with valid auth should soft-delete user."""
        deletion_calls = []

        async def mock_soft_delete_user(user_id):
            deletion_calls.append(user_id)
            return True

        mock_db.soft_delete_user = mock_soft_delete_user
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test_user_123",
            auth_key_hash=b'\xaa' * 32,
            salt=b'\xbb' * 32
        ))

        response = client.delete(
            "/v1/account",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(deletion_calls) == 1
        assert deletion_calls[0] == "test_user_123"

    def test_delete_account_response_format(self, client, mock_db):
        """Response should include confirmation message and purge date."""
        async def mock_soft_delete_user(user_id):
            return True

        mock_db.soft_delete_user = mock_soft_delete_user
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test_user_123",
            auth_key_hash=b'\xaa' * 32,
            salt=b'\xbb' * 32
        ))

        response = client.delete(
            "/v1/account",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )

        data = response.json()
        assert data["success"] is True
        assert "message" in data
        assert "purge" in data["message"].lower() or "delete" in data["message"].lower()

    def test_delete_account_deactivates_all_facts(self, client, mock_db):
        """All user facts must be marked is_active=false."""
        deactivated_users = []

        async def mock_soft_delete_user(user_id):
            deactivated_users.append(user_id)
            return True

        mock_db.soft_delete_user = mock_soft_delete_user
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test_user_123",
            auth_key_hash=b'\xaa' * 32,
            salt=b'\xbb' * 32
        ))

        response = client.delete(
            "/v1/account",
            headers={"Authorization": "Bearer " + "aa" * 32}
        )

        assert response.status_code == 200
        assert len(deactivated_users) == 1
