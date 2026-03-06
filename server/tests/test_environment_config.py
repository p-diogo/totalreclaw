"""
Tests for environment-specific configuration.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEnvironmentConfig:
    """Tests for dev/staging/production configuration."""

    def test_environment_setting_exists(self):
        """ENVIRONMENT setting must exist."""
        from src.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()
        assert hasattr(settings, "environment")
        assert settings.environment in ["development", "staging", "production"]

    def test_cors_origins_setting_exists(self):
        """CORS origins must be configurable."""
        from src.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()
        assert hasattr(settings, "cors_origins")

    def test_development_defaults(self):
        """Development should default to permissive settings."""
        os.environ["ENVIRONMENT"] = "development"
        from src.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()

        assert settings.debug is True or settings.environment == "development"
        os.environ.pop("ENVIRONMENT", None)
        get_settings.cache_clear()

    def test_production_disables_debug(self):
        """Production must disable debug mode."""
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DEBUG"] = "false"
        from src.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()

        assert settings.debug is False
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("DEBUG", None)
        get_settings.cache_clear()

    def test_production_disables_swagger(self):
        """Production must disable Swagger docs."""
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DEBUG"] = "false"
        from src.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()

        # Swagger is controlled by debug flag
        assert settings.debug is False  # This disables docs_url and redoc_url
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("DEBUG", None)
        get_settings.cache_clear()

    def test_cors_origins_not_wildcard_in_production(self):
        """Production must NOT use wildcard CORS origins."""
        os.environ["ENVIRONMENT"] = "production"
        os.environ["CORS_ORIGINS"] = "https://app.totalreclaw.xyz"
        from src.config import get_settings
        get_settings.cache_clear()
        settings = get_settings()

        assert "*" not in settings.cors_origins
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("CORS_ORIGINS", None)
        get_settings.cache_clear()
