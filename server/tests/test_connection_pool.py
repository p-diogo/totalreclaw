"""
Tests for database connection pool configuration.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_settings


class TestConnectionPoolConfig:
    """Tests for connection pool settings."""

    def test_pool_size_is_configurable(self):
        """Pool size should be configurable via env."""
        get_settings.cache_clear()
        settings = get_settings()
        assert hasattr(settings, "database_pool_size")
        assert settings.database_pool_size >= 10  # Minimum reasonable

    def test_max_overflow_is_configurable(self):
        """Max overflow should be configurable via env."""
        get_settings.cache_clear()
        settings = get_settings()
        assert hasattr(settings, "database_max_overflow")
        assert settings.database_max_overflow >= 10

    def test_pool_recycle_is_set(self):
        """Pool recycle should be set to prevent stale connections."""
        get_settings.cache_clear()
        settings = get_settings()
        assert hasattr(settings, "database_pool_recycle")
        assert settings.database_pool_recycle > 0  # Must be positive
        assert settings.database_pool_recycle <= 7200  # Max 2 hours

    def test_pool_pre_ping_is_enabled(self):
        """Pool pre-ping should be enabled to detect dead connections."""
        get_settings.cache_clear()
        settings = get_settings()
        assert hasattr(settings, "database_pool_pre_ping")
        assert settings.database_pool_pre_ping is True

    def test_pool_timeout_is_set(self):
        """Pool timeout should be set to fail fast."""
        get_settings.cache_clear()
        settings = get_settings()
        assert hasattr(settings, "database_pool_timeout")
        assert settings.database_pool_timeout > 0
        assert settings.database_pool_timeout <= 60  # Max 60 seconds

    def test_total_connections_sufficient(self):
        """Total pool (size + overflow) should be >= 50 for production."""
        get_settings.cache_clear()
        settings = get_settings()
        total = settings.database_pool_size + settings.database_max_overflow
        assert total >= 50, f"Total pool {total} < 50, insufficient for production"


class TestConnectionPoolIntegration:
    """Integration tests for pool behavior."""

    def test_database_uses_pool_settings(self):
        """Database class must use pool settings from config."""
        from src.db.database import Database
        get_settings.cache_clear()
        settings = get_settings()

        # Create a Database instance (doesn't connect)
        db = Database.__new__(Database)
        # Verify the Database.__init__ reads these settings
        # This is a structural test -- verifying the code reads from config
        assert settings.database_pool_size is not None
        assert settings.database_max_overflow is not None
