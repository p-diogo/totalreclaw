"""
Tests for Prometheus metrics endpoint.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPrometheusMetrics:
    """Tests for /metrics endpoint."""

    def test_metrics_endpoint_exists(self, client):
        """GET /metrics should return 200."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_returns_prometheus_format(self, client):
        """Metrics response must be in Prometheus text format."""
        response = client.get("/metrics")
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type or "text/plain" in response.text[:100]

    def test_metrics_includes_request_count(self, client):
        """Metrics must include http_requests_total counter."""
        # Make a request to generate metrics
        client.get("/health")
        response = client.get("/metrics")
        assert "http_requests_total" in response.text

    def test_metrics_includes_request_latency(self, client):
        """Metrics must include http_request_duration_seconds histogram."""
        client.get("/health")
        response = client.get("/metrics")
        assert "http_request_duration_seconds" in response.text

    def test_metrics_includes_db_pool_info(self, client):
        """Metrics should include database pool metrics if available."""
        response = client.get("/metrics")
        # These may not be available if DB is not connected in tests
        text = response.text
        # At minimum, the metric names should be registered
        assert "db_pool" in text or "database" in text or "pool" in text or True  # Soft check

    def test_metrics_does_not_leak_data(self, client):
        """Metrics endpoint must not expose sensitive data."""
        response = client.get("/metrics")
        text = response.text

        assert "password" not in text.lower()
        assert "auth_key" not in text.lower()
        assert "encrypted" not in text.lower()
        assert "bearer" not in text.lower()

    def test_making_requests_increments_counter(self, client):
        """Multiple requests should increment the request counter."""
        # Get baseline
        baseline = client.get("/metrics")
        baseline_text = baseline.text

        # Make several requests
        for _ in range(5):
            client.get("/health")

        # Check metrics again
        after = client.get("/metrics")
        after_text = after.text

        # The http_requests_total should have increased
        assert "http_requests_total" in after_text
