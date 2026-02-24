"""
Tests for per-user rate limiting middleware.

Tests are standalone (no DB needed) and validate:
- Different users have separate counters
- Same user hitting the limit gets 429
- Counter resets after window expires
- /register uses IP-based limiting
- Retry-After header is present
- Cleanup of expired entries
"""
import os
import sys
import time
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.middleware.rate_limit import (
    SlidingWindowCounter,
    get_counter,
    reset_counter,
)


# ============ Unit Tests for SlidingWindowCounter ============

class TestSlidingWindowCounter:
    """Low-level tests for the sliding window counter."""

    def test_allows_under_limit(self):
        """Requests under the limit should be allowed."""
        counter = SlidingWindowCounter()
        for i in range(5):
            allowed, retry = counter.check_and_record("key1", max_requests=5, window_seconds=60)
            assert allowed is True
            assert retry == 0

    def test_blocks_at_limit(self):
        """The request that exceeds the limit should be blocked."""
        counter = SlidingWindowCounter()
        for i in range(10):
            counter.check_and_record("key1", max_requests=10, window_seconds=60)

        allowed, retry = counter.check_and_record("key1", max_requests=10, window_seconds=60)
        assert allowed is False
        assert retry > 0

    def test_different_keys_are_independent(self):
        """Rate limits for different keys should be independent."""
        counter = SlidingWindowCounter()

        # Fill up key1
        for i in range(5):
            counter.check_and_record("key1", max_requests=5, window_seconds=60)

        # key1 should be blocked
        allowed, _ = counter.check_and_record("key1", max_requests=5, window_seconds=60)
        assert allowed is False

        # key2 should still be allowed
        allowed, _ = counter.check_and_record("key2", max_requests=5, window_seconds=60)
        assert allowed is True

    def test_window_expiry(self):
        """Entries should expire after the window period."""
        counter = SlidingWindowCounter()

        # Fill up the counter with a very short window
        for i in range(3):
            counter.check_and_record("key1", max_requests=3, window_seconds=1)

        # Should be blocked now
        allowed, _ = counter.check_and_record("key1", max_requests=3, window_seconds=1)
        assert allowed is False

        # Wait for the window to expire
        time.sleep(1.1)

        # Should be allowed again
        allowed, _ = counter.check_and_record("key1", max_requests=3, window_seconds=1)
        assert allowed is True

    def test_retry_after_is_positive(self):
        """retry_after should always be a positive integer when blocked."""
        counter = SlidingWindowCounter()
        for i in range(5):
            counter.check_and_record("key1", max_requests=5, window_seconds=3600)

        _, retry = counter.check_and_record("key1", max_requests=5, window_seconds=3600)
        assert retry > 0
        assert isinstance(retry, int)

    def test_cleanup_expired(self):
        """cleanup_expired should remove keys with all-expired entries."""
        counter = SlidingWindowCounter()

        # Add an entry that will expire quickly
        counter.check_and_record("expire_me", max_requests=100, window_seconds=1)

        # Wait for the entry to expire
        time.sleep(1.1)

        # Add a fresh entry that should NOT expire
        counter.check_and_record("keep_me", max_requests=100, window_seconds=3600)

        # Cleanup with a 1-second window: expire_me's entry is > 1s old, keep_me's is fresh
        removed = counter.cleanup_expired(window_seconds=1)
        assert removed >= 1  # expire_me should be gone

        # keep_me should still have entries
        count = counter.get_count("keep_me", window_seconds=3600)
        assert count == 1

    def test_get_count(self):
        """get_count should return the correct number of entries in the window."""
        counter = SlidingWindowCounter()
        counter.check_and_record("key1", max_requests=100, window_seconds=60)
        counter.check_and_record("key1", max_requests=100, window_seconds=60)
        counter.check_and_record("key1", max_requests=100, window_seconds=60)

        assert counter.get_count("key1", window_seconds=60) == 3
        assert counter.get_count("nonexistent", window_seconds=60) == 0

    def test_reset(self):
        """reset() should clear all entries."""
        counter = SlidingWindowCounter()
        counter.check_and_record("key1", max_requests=100, window_seconds=60)
        counter.check_and_record("key2", max_requests=100, window_seconds=60)

        counter.reset()

        assert counter.get_count("key1", window_seconds=60) == 0
        assert counter.get_count("key2", window_seconds=60) == 0


# ============ Integration Tests with FastAPI TestClient ============

class TestRateLimitMiddleware:
    """Tests for rate limiting via the FastAPI test client."""

    @pytest.fixture(autouse=True)
    def reset_rate_limiter(self):
        """Reset the rate limiter before each test."""
        reset_counter()
        yield
        reset_counter()

    def test_register_rate_limit_uses_ip(self, client):
        """POST /v1/register should use IP-based rate limiting."""
        # With default limit of 10/hour, sending 10 should work, 11th should fail
        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 3
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            for i in range(3):
                response = client.post(
                    "/v1/register",
                    json={
                        "auth_key_hash": f"{'aa' * 32}",
                        "salt": f"{'bb' * 32}"
                    }
                )
                # Should succeed or fail for other reasons (not 429)
                assert response.status_code != 429, f"Request {i+1} should not be rate limited"

            # 4th request should be rate limited
            response = client.post(
                "/v1/register",
                json={
                    "auth_key_hash": f"{'cc' * 32}",
                    "salt": f"{'dd' * 32}"
                }
            )
            assert response.status_code == 429

    def test_authenticated_endpoints_use_auth_hash(self, client):
        """Authenticated endpoints should rate-limit per auth_hash."""
        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 10
            settings.rate_limit_store_per_hour = 2
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            user1_token = "aa" * 32
            user2_token = "bb" * 32

            # User 1 makes 2 requests (hits limit)
            for i in range(2):
                response = client.post(
                    "/v1/store",
                    json={"user_id": "test", "facts": []},
                    headers={"Authorization": f"Bearer {user1_token}"}
                )
                assert response.status_code != 429

            # User 1 should now be blocked
            response = client.post(
                "/v1/store",
                json={"user_id": "test", "facts": []},
                headers={"Authorization": f"Bearer {user1_token}"}
            )
            assert response.status_code == 429

            # User 2 should still be allowed (separate counter)
            response = client.post(
                "/v1/store",
                json={"user_id": "test", "facts": []},
                headers={"Authorization": f"Bearer {user2_token}"}
            )
            assert response.status_code != 429

    def test_429_includes_retry_after_header(self, client):
        """429 responses should include a Retry-After header."""
        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 1
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            # First request OK
            client.post(
                "/v1/register",
                json={"auth_key_hash": "aa" * 32, "salt": "bb" * 32}
            )

            # Second request should be rate limited
            response = client.post(
                "/v1/register",
                json={"auth_key_hash": "cc" * 32, "salt": "dd" * 32}
            )
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            retry_after = int(response.headers["Retry-After"])
            assert retry_after > 0

    def test_429_includes_json_body(self, client):
        """429 responses should include a JSON body with detail and retry_after."""
        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 1
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            client.post(
                "/v1/register",
                json={"auth_key_hash": "aa" * 32, "salt": "bb" * 32}
            )

            response = client.post(
                "/v1/register",
                json={"auth_key_hash": "cc" * 32, "salt": "dd" * 32}
            )
            assert response.status_code == 429
            data = response.json()
            assert "detail" in data
            assert "retry_after" in data
            assert data["retry_after"] > 0
            assert "Rate limit exceeded" in data["detail"]

    def test_health_endpoint_not_rate_limited(self, client):
        """GET /health should never be rate limited."""
        reset_counter()

        for i in range(20):
            response = client.get("/health")
            assert response.status_code != 429

    def test_metrics_endpoint_not_rate_limited(self, client):
        """GET /metrics should never be rate limited."""
        reset_counter()

        for i in range(20):
            response = client.get("/metrics")
            assert response.status_code != 429

    def test_different_paths_have_separate_limits(self, client):
        """Rate limits for /v1/store and /v1/search should be independent."""
        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 10
            settings.rate_limit_store_per_hour = 2
            settings.rate_limit_search_per_hour = 2
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            token = "aa" * 32

            # Use up /v1/store limit
            for i in range(2):
                client.post(
                    "/v1/store",
                    json={"user_id": "test", "facts": []},
                    headers={"Authorization": f"Bearer {token}"}
                )

            # /v1/store should be blocked
            response = client.post(
                "/v1/store",
                json={"user_id": "test", "facts": []},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 429

            # /v1/search should still work (separate limit)
            response = client.post(
                "/v1/search",
                json={"user_id": "test", "trapdoors": ["abc"], "max_candidates": 10},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code != 429

    def test_store_under_limit_not_blocked(self, client):
        """A single /v1/store request should not be rate limited."""
        reset_counter()

        response = client.post(
            "/v1/store",
            json={"user_id": "test", "facts": []},
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        # Will be 401 (no auth in mock DB) but NOT 429
        assert response.status_code != 429


class TestSlidingWindowCounterExpiry:
    """Tests focused on time-based expiry behavior."""

    def test_partial_window_expiry(self):
        """Only expired entries should be pruned, not the entire key."""
        counter = SlidingWindowCounter()

        # Add 3 entries with a 2-second window
        counter.check_and_record("key1", max_requests=10, window_seconds=2)
        time.sleep(0.5)
        counter.check_and_record("key1", max_requests=10, window_seconds=2)
        time.sleep(0.5)
        counter.check_and_record("key1", max_requests=10, window_seconds=2)

        # Wait for first entry to expire but not the others
        time.sleep(1.2)

        count = counter.get_count("key1", window_seconds=2)
        # First entry should be expired, but the other two should remain
        assert count == 2

    def test_counter_resets_after_full_window(self):
        """After the full window period, all entries should be expired."""
        counter = SlidingWindowCounter()

        # Fill up the limit
        for i in range(5):
            counter.check_and_record("key1", max_requests=5, window_seconds=1)

        # Should be blocked
        allowed, _ = counter.check_and_record("key1", max_requests=5, window_seconds=1)
        assert allowed is False

        # Wait for full window to pass
        time.sleep(1.1)

        # Should be allowed again, and can fill up to 5 again
        for i in range(5):
            allowed, _ = counter.check_and_record("key1", max_requests=5, window_seconds=1)
            assert allowed is True


# ============ Observability Tests: Logging & Prometheus Metrics ============

class TestRateLimitObservability:
    """Tests for rate limit logging and Prometheus metrics."""

    @pytest.fixture(autouse=True)
    def reset_rate_limiter(self):
        """Reset the rate limiter before each test."""
        reset_counter()
        yield
        reset_counter()

    def test_rate_limit_logs_warning_on_429(self, client, caplog):
        """When a user is rate limited, a WARNING log should be emitted."""
        import logging

        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 1
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            # First request OK
            client.post(
                "/v1/register",
                json={"auth_key_hash": "aa" * 32, "salt": "bb" * 32}
            )

            # Second request should be rate limited and logged
            with caplog.at_level(logging.WARNING, logger="src.middleware.rate_limit"):
                response = client.post(
                    "/v1/register",
                    json={"auth_key_hash": "cc" * 32, "salt": "dd" * 32}
                )

            assert response.status_code == 429

            # Check that a warning was logged
            rate_limit_logs = [
                r for r in caplog.records
                if r.levelno == logging.WARNING and "Rate limited" in r.getMessage()
            ]
            assert len(rate_limit_logs) >= 1, "Expected at least one 'Rate limited' warning log"

    def test_rate_limit_log_contains_path(self, client, caplog):
        """Rate limit log entry must contain the path that was limited."""
        import logging

        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 1
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            client.post(
                "/v1/register",
                json={"auth_key_hash": "aa" * 32, "salt": "bb" * 32}
            )

            with caplog.at_level(logging.WARNING, logger="src.middleware.rate_limit"):
                client.post(
                    "/v1/register",
                    json={"auth_key_hash": "cc" * 32, "salt": "dd" * 32}
                )

            rate_limit_logs = [
                r for r in caplog.records
                if r.levelno == logging.WARNING and "Rate limited" in r.getMessage()
            ]
            assert len(rate_limit_logs) >= 1
            log_record = rate_limit_logs[0]
            assert log_record.path == "/v1/register"

    def test_rate_limit_log_contains_count_and_limit(self, client, caplog):
        """Rate limit log must include count and limit values."""
        import logging

        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 2
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            # Use up the limit
            for _ in range(2):
                client.post(
                    "/v1/register",
                    json={"auth_key_hash": "aa" * 32, "salt": "bb" * 32}
                )

            with caplog.at_level(logging.WARNING, logger="src.middleware.rate_limit"):
                client.post(
                    "/v1/register",
                    json={"auth_key_hash": "cc" * 32, "salt": "dd" * 32}
                )

            rate_limit_logs = [
                r for r in caplog.records
                if r.levelno == logging.WARNING and "Rate limited" in r.getMessage()
            ]
            assert len(rate_limit_logs) >= 1
            log_record = rate_limit_logs[0]
            assert log_record.limit == 2
            assert log_record.count >= 2

    def test_rate_limit_log_truncates_key(self, client, caplog):
        """Rate limit log key_prefix must be truncated (not full auth token)."""
        import logging

        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 10
            settings.rate_limit_store_per_hour = 1
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            full_token = "ab" * 32  # 64-char hex token

            # First request OK
            client.post(
                "/v1/store",
                json={"user_id": "test", "facts": []},
                headers={"Authorization": f"Bearer {full_token}"}
            )

            with caplog.at_level(logging.WARNING, logger="src.middleware.rate_limit"):
                client.post(
                    "/v1/store",
                    json={"user_id": "test", "facts": []},
                    headers={"Authorization": f"Bearer {full_token}"}
                )

            rate_limit_logs = [
                r for r in caplog.records
                if r.levelno == logging.WARNING and "Rate limited" in r.getMessage()
            ]
            assert len(rate_limit_logs) >= 1
            log_record = rate_limit_logs[0]
            key_prefix = log_record.key_prefix
            # The full 64-char token should NOT appear in the log
            assert full_token not in key_prefix
            # But it should contain a truncated prefix
            assert "..." in key_prefix

    def test_rate_limit_increments_prometheus_counter(self, client):
        """Rate limiting should increment rate_limit_hits_total Prometheus counter."""
        from src.metrics import RATE_LIMIT_HITS_TOTAL

        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 1
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            # Get baseline counter value
            before = RATE_LIMIT_HITS_TOTAL.labels(
                path="/v1/register", limit_type="ip"
            )._value.get()

            # First request OK
            client.post(
                "/v1/register",
                json={"auth_key_hash": "aa" * 32, "salt": "bb" * 32}
            )

            # Second request should be rate limited
            response = client.post(
                "/v1/register",
                json={"auth_key_hash": "cc" * 32, "salt": "dd" * 32}
            )
            assert response.status_code == 429

            after = RATE_LIMIT_HITS_TOTAL.labels(
                path="/v1/register", limit_type="ip"
            )._value.get()
            assert after > before, "Prometheus counter should have been incremented"

    def test_rate_limit_counter_uses_correct_limit_type(self, client):
        """IP-based routes should use limit_type=ip, auth routes should use limit_type=user."""
        from src.metrics import RATE_LIMIT_HITS_TOTAL

        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 10
            settings.rate_limit_store_per_hour = 1
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            token = "ee" * 32

            # Get baseline for user limit_type
            before_user = RATE_LIMIT_HITS_TOTAL.labels(
                path="/v1/store", limit_type="user"
            )._value.get()

            # First request OK
            client.post(
                "/v1/store",
                json={"user_id": "test", "facts": []},
                headers={"Authorization": f"Bearer {token}"}
            )

            # Second request rate limited
            response = client.post(
                "/v1/store",
                json={"user_id": "test", "facts": []},
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 429

            after_user = RATE_LIMIT_HITS_TOTAL.labels(
                path="/v1/store", limit_type="user"
            )._value.get()
            assert after_user > before_user

    def test_rate_limit_metrics_visible_in_metrics_endpoint(self, client):
        """rate_limit_hits_total should appear in /metrics output."""
        with patch("src.middleware.rate_limit.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.rate_limit_register_per_hour = 1
            settings.rate_limit_store_per_hour = 1000
            settings.rate_limit_search_per_hour = 1000
            settings.rate_limit_sync_per_hour = 1000
            settings.rate_limit_account_per_hour = 10

            reset_counter()

            # Trigger a rate limit
            client.post(
                "/v1/register",
                json={"auth_key_hash": "aa" * 32, "salt": "bb" * 32}
            )
            client.post(
                "/v1/register",
                json={"auth_key_hash": "cc" * 32, "salt": "dd" * 32}
            )

        # Check that rate_limit_hits_total appears in metrics
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "rate_limit_hits_total" in response.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
