"""
Tests for Caddy reverse proxy configuration.

These tests validate the Caddyfile syntax and docker-compose integration
without requiring a running Caddy instance.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCaddyConfiguration:
    """Tests for Caddy configuration files."""

    def test_caddyfile_exists(self):
        """Caddyfile must exist in server/ directory."""
        caddyfile_path = os.path.join(SERVER_DIR, "Caddyfile")
        assert os.path.exists(caddyfile_path), "Caddyfile must exist"

    def test_caddyfile_has_reverse_proxy(self):
        """Caddyfile must proxy to the FastAPI backend."""
        caddyfile_path = os.path.join(SERVER_DIR, "Caddyfile")
        with open(caddyfile_path) as f:
            content = f.read()

        assert "reverse_proxy" in content, "Caddyfile must have reverse_proxy directive"
        assert "totalreclaw-server" in content or "8080" in content, \
            "Caddyfile must proxy to totalreclaw-server or port 8080"

    def test_caddyfile_has_security_headers(self):
        """Caddyfile must set security headers."""
        caddyfile_path = os.path.join(SERVER_DIR, "Caddyfile")
        with open(caddyfile_path) as f:
            content = f.read()

        assert "Strict-Transport-Security" in content, "Caddyfile must set HSTS"
        assert "X-Content-Type-Options" in content, "Caddyfile must set X-Content-Type-Options"

    def test_caddyfile_has_request_size_limit(self):
        """Caddyfile must limit request body size."""
        caddyfile_path = os.path.join(SERVER_DIR, "Caddyfile")
        with open(caddyfile_path) as f:
            content = f.read()

        assert "request_body" in content or "max_size" in content, \
            "Caddyfile must limit request body size"

    def test_docker_compose_has_caddy_service(self):
        """docker-compose.yml must include a Caddy service."""
        compose_path = os.path.join(SERVER_DIR, "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()

        assert "caddy" in content.lower(), \
            "docker-compose.yml must include a Caddy service"

    def test_caddy_exposes_443_and_80(self):
        """Caddy must expose ports 80 and 443."""
        compose_path = os.path.join(SERVER_DIR, "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()

        assert "443" in content, "docker-compose.yml must expose port 443 for HTTPS"
        assert "80" in content, "docker-compose.yml must expose port 80 for HTTP redirect"
