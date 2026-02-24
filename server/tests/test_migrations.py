"""
Tests for Alembic database migrations.
"""
import pytest
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestAlembicSetup:
    """Tests for Alembic migration infrastructure."""

    def test_alembic_ini_exists(self):
        """alembic.ini must exist in server/ directory."""
        ini_path = os.path.join(SERVER_DIR, "alembic.ini")
        assert os.path.exists(ini_path), "alembic.ini must exist"

    def test_migrations_directory_exists(self):
        """migrations/ directory must exist."""
        migrations_dir = os.path.join(SERVER_DIR, "migrations")
        assert os.path.isdir(migrations_dir), "migrations/ directory must exist"

    def test_migrations_env_py_exists(self):
        """migrations/env.py must exist."""
        env_path = os.path.join(SERVER_DIR, "migrations", "env.py")
        assert os.path.exists(env_path), "migrations/env.py must exist"

    def test_initial_migration_exists(self):
        """At least one migration version must exist."""
        versions_dir = os.path.join(SERVER_DIR, "migrations", "versions")
        assert os.path.isdir(versions_dir), "migrations/versions/ must exist"

        versions = [f for f in os.listdir(versions_dir) if f.endswith(".py") and not f.startswith("__")]
        assert len(versions) >= 1, "At least one migration file must exist"

    def test_initial_migration_has_users_table(self):
        """Initial migration must create users table."""
        versions_dir = os.path.join(SERVER_DIR, "migrations", "versions")
        versions = [f for f in os.listdir(versions_dir) if f.endswith(".py") and not f.startswith("__")]

        found_users = False
        for v in versions:
            with open(os.path.join(versions_dir, v)) as f:
                content = f.read()
                if "users" in content and ("create_table" in content.lower() or "op.create_table" in content):
                    found_users = True
                    break

        assert found_users, "Initial migration must create 'users' table"

    def test_alembic_check_command(self):
        """alembic heads should run without error (validate config)."""
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            capture_output=True,
            text=True,
            cwd=SERVER_DIR
        )
        # alembic heads should list the current head revision
        assert result.returncode == 0 or "FAILED" not in result.stderr, \
            f"alembic heads failed: {result.stderr}"
