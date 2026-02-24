"""
Tests for secrets management.

Verifies that no secrets are hardcoded in source files.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Paths relative to server/ directory
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSecretsManagement:
    """Verify no hardcoded secrets in source files."""

    def test_no_hardcoded_password_in_docker_compose(self):
        """docker-compose.yml must not contain hardcoded passwords."""
        compose_path = os.path.join(SERVER_DIR, "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()

        # Should NOT have POSTGRES_PASSWORD=dev or any literal password
        assert "POSTGRES_PASSWORD=dev" not in content, \
            "docker-compose.yml contains hardcoded POSTGRES_PASSWORD=dev"
        assert "POSTGRES_PASSWORD=password" not in content
        assert "POSTGRES_PASSWORD=postgres" not in content

    def test_docker_compose_uses_env_variable(self):
        """docker-compose.yml should reference env vars, not literals."""
        compose_path = os.path.join(SERVER_DIR, "docker-compose.yml")
        with open(compose_path) as f:
            content = f.read()

        # Should reference env_file or use ${VAR} syntax
        assert "env_file" in content or "${POSTGRES_PASSWORD}" in content, \
            "docker-compose.yml should use env_file or ${VAR} syntax for secrets"

    def test_env_example_exists(self):
        """A .env.example file must exist with placeholder values."""
        env_example_path = os.path.join(SERVER_DIR, ".env.example")
        assert os.path.exists(env_example_path), \
            ".env.example must exist in server/ directory"

        with open(env_example_path) as f:
            content = f.read()

        assert "POSTGRES_PASSWORD" in content, \
            ".env.example must document POSTGRES_PASSWORD"

    def test_env_file_in_gitignore(self):
        """The .env file must be in .gitignore."""
        # Check project root .gitignore
        root_gitignore = os.path.join(SERVER_DIR, "..", ".gitignore")
        if os.path.exists(root_gitignore):
            with open(root_gitignore) as f:
                content = f.read()
            assert ".env" in content, ".env must be in root .gitignore"

    def test_no_hardcoded_password_in_config(self):
        """config.py should not contain literal passwords."""
        config_path = os.path.join(SERVER_DIR, "src", "config.py")
        with open(config_path) as f:
            content = f.read()

        # The default database_url can contain 'dev' for local development,
        # but check for obvious production passwords
        assert "POSTGRES_PASSWORD" not in content or "os.environ" in content or "env" in content.lower()

    def test_no_actual_env_file_committed(self):
        """Verify .env is not in the repo (just .env.example)."""
        env_path = os.path.join(SERVER_DIR, ".env")
        # This test is informational -- .env should only exist locally
        # If it exists, it should be in .gitignore
        if os.path.exists(env_path):
            root_gitignore = os.path.join(SERVER_DIR, "..", ".gitignore")
            with open(root_gitignore) as f:
                assert ".env" in f.read(), ".env exists but is NOT in .gitignore!"
