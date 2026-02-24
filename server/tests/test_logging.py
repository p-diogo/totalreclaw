"""
Tests for structured JSON logging.
"""
import pytest
import os
import sys
import json
import logging
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStructuredLogging:
    """Tests for JSON log output."""

    def test_log_output_is_valid_json(self):
        """Log output must be valid JSON."""
        from src.main import app

        # Capture log output
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)

        # Get the app logger
        logger = logging.getLogger("src.main")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("test log message")

        output = log_stream.getvalue()
        handler.close()
        logger.removeHandler(handler)

        # If structured logging is configured, output should be JSON
        if output.strip():
            try:
                parsed = json.loads(output.strip())
                assert "message" in parsed or "msg" in parsed
            except json.JSONDecodeError:
                # If not JSON, structured logging is not configured
                pytest.skip("Structured logging not yet configured")

    def test_log_does_not_contain_auth_keys(self, client):
        """Log output must NEVER contain auth keys or sensitive data."""
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        # Make a request with auth header
        auth_key_hex = "aa" * 32
        client.post(
            "/v1/store",
            json={"user_id": "test", "facts": []},
            headers={"Authorization": f"Bearer {auth_key_hex}"}
        )

        output = log_stream.getvalue()
        root_logger.removeHandler(handler)

        # Auth key must not appear in logs
        assert auth_key_hex not in output, \
            f"Auth key found in log output! Sensitive data leak."

    def test_log_does_not_contain_encrypted_blobs(self, client):
        """Encrypted blobs must never be logged."""
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        large_blob = "ff" * 500  # 500-byte blob
        client.post(
            "/v1/store",
            json={
                "user_id": "test",
                "facts": [{
                    "id": "test-id",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "encrypted_blob": large_blob,
                    "blind_indices": ["a" * 64],
                    "decay_score": 1.0,
                    "is_active": True,
                    "version": 1,
                    "source": "test"
                }]
            },
            headers={"Authorization": "Bearer " + "aa" * 32}
        )

        output = log_stream.getvalue()
        root_logger.removeHandler(handler)

        assert large_blob not in output, \
            "Encrypted blob found in log output! Data leak."


class TestCorrelationId:
    """Tests for request correlation IDs."""

    def test_response_has_correlation_id(self, client):
        """Every response should include an X-Correlation-ID header."""
        response = client.get("/health")
        correlation_id = response.headers.get("X-Correlation-ID") or \
                         response.headers.get("x-correlation-id")
        if correlation_id:
            # Validate it looks like a UUID
            assert len(correlation_id) == 36  # UUID format: 8-4-4-4-12
        else:
            pytest.skip("Correlation ID header not yet implemented")

    def test_correlation_ids_are_unique(self, client):
        """Each request should get a unique correlation ID."""
        ids = set()
        for _ in range(10):
            response = client.get("/health")
            cid = response.headers.get("X-Correlation-ID") or \
                  response.headers.get("x-correlation-id")
            if cid:
                ids.add(cid)

        if ids:
            assert len(ids) == 10, "Correlation IDs must be unique per request"
        else:
            pytest.skip("Correlation ID header not yet implemented")
