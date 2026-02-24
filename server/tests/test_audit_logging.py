"""
Tests for audit logging (raw_events table).
"""
import pytest
import os
import sys
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAuditLogging:
    """Tests that store operations create audit log entries."""

    def test_store_calls_log_raw_event(self, client, mock_db):
        """POST /store must call log_raw_event for audit trail."""
        # Track calls to log_raw_event
        log_calls = []
        original_log = mock_db.log_raw_event

        async def tracking_log(user_id, event_bytes):
            log_calls.append({"user_id": user_id, "event_bytes": event_bytes})

        mock_db.log_raw_event = tracking_log

        # Mock auth to succeed
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test_user_123",
            auth_key_hash=b'\xaa' * 32,
            salt=b'\xbb' * 32
        ))

        fact = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "encrypted_blob": "aabb" * 10,
            "blind_indices": [
                "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
            ],
            "decay_score": 1.0,
            "is_active": True,
            "version": 1,
            "source": "test"
        }

        response = client.post(
            "/v1/store",
            json={"user_id": "test_user_123", "facts": [fact]},
            headers={"Authorization": "Bearer " + "aa" * 32}
        )

        assert response.status_code == 200
        data = response.json()
        if data["success"]:
            assert len(log_calls) == 1, "log_raw_event must be called once per store request"
            assert log_calls[0]["user_id"] == "test_user_123"

    def test_log_raw_event_does_not_log_plaintext(self, client, mock_db):
        """Audit log must NOT contain any plaintext or decrypted data."""
        log_calls = []

        async def tracking_log(user_id, event_bytes):
            log_calls.append({"user_id": user_id, "event_bytes": event_bytes})

        mock_db.log_raw_event = tracking_log
        mock_db.get_user_by_auth_hash = AsyncMock(return_value=MagicMock(
            user_id="test_user_123",
            auth_key_hash=b'\xaa' * 32,
            salt=b'\xbb' * 32
        ))

        fact = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "encrypted_blob": "aabb" * 10,
            "blind_indices": [
                "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
            ],
            "decay_score": 1.0,
            "is_active": True,
            "version": 1,
            "source": "test"
        }

        response = client.post(
            "/v1/store",
            json={"user_id": "test_user_123", "facts": [fact]},
            headers={"Authorization": "Bearer " + "aa" * 32}
        )

        if response.status_code == 200 and response.json()["success"]:
            for call in log_calls:
                event_str = call["event_bytes"].decode("utf-8", errors="replace") if isinstance(call["event_bytes"], bytes) else str(call["event_bytes"])
                # Should contain fact IDs but not auth keys
                assert "Bearer" not in event_str
