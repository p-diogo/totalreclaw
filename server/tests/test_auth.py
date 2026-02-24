"""
Tests for authentication module.
"""
import pytest
import hashlib
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.auth import (
    generate_salt,
    derive_auth_key,
    hash_auth_key,
    verify_auth_key,
    generate_user_id,
    AUTH_KEY_INFO,
    HKDF_LENGTH,
    SALT_LENGTH
)


class TestSaltGeneration:
    """Tests for salt generation."""

    def test_generate_salt_length(self):
        """Salt should be 32 bytes."""
        salt = generate_salt()
        assert len(salt) == SALT_LENGTH

    def test_generate_salt_randomness(self):
        """Each salt should be unique."""
        salt1 = generate_salt()
        salt2 = generate_salt()
        assert salt1 != salt2


class TestKeyDerivation:
    """Tests for HKDF key derivation."""

    def test_derive_auth_key_length(self):
        """Derived key should be 32 bytes."""
        master_password = "test_password_123"
        salt = generate_salt()
        auth_key = derive_auth_key(master_password, salt)
        assert len(auth_key) == HKDF_LENGTH

    def test_derive_auth_key_deterministic(self):
        """Same password + salt should produce same key."""
        master_password = "test_password_123"
        salt = generate_salt()
        key1 = derive_auth_key(master_password, salt)
        key2 = derive_auth_key(master_password, salt)
        assert key1 == key2

    def test_derive_auth_key_different_password(self):
        """Different passwords should produce different keys."""
        salt = generate_salt()
        key1 = derive_auth_key("password1", salt)
        key2 = derive_auth_key("password2", salt)
        assert key1 != key2

    def test_derive_auth_key_different_salt(self):
        """Different salts should produce different keys."""
        master_password = "test_password"
        key1 = derive_auth_key(master_password, generate_salt())
        key2 = derive_auth_key(master_password, generate_salt())
        assert key1 != key2


class TestKeyHashing:
    """Tests for auth key hashing."""

    def test_hash_auth_key_length(self):
        """SHA256 hash should be 32 bytes."""
        auth_key = os.urandom(32)
        hashed = hash_auth_key(auth_key)
        assert len(hashed) == 32

    def test_hash_auth_key_deterministic(self):
        """Same key should produce same hash."""
        auth_key = os.urandom(32)
        hash1 = hash_auth_key(auth_key)
        hash2 = hash_auth_key(auth_key)
        assert hash1 == hash2

    def test_hash_auth_key_different_keys(self):
        """Different keys should produce different hashes."""
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        hash1 = hash_auth_key(key1)
        hash2 = hash_auth_key(key2)
        assert hash1 != hash2


class TestKeyVerification:
    """Tests for auth key verification."""

    def test_verify_auth_key_correct(self):
        """Correct key should verify."""
        auth_key = os.urandom(32)
        hashed = hash_auth_key(auth_key)
        assert verify_auth_key(auth_key, hashed) is True

    def test_verify_auth_key_incorrect(self):
        """Incorrect key should not verify."""
        auth_key = os.urandom(32)
        wrong_key = os.urandom(32)
        hashed = hash_auth_key(auth_key)
        assert verify_auth_key(wrong_key, hashed) is False

    def test_verify_auth_key_empty(self):
        """Empty key should not verify."""
        auth_key = os.urandom(32)
        hashed = hash_auth_key(auth_key)
        assert verify_auth_key(b"", hashed) is False


class TestUserIDGeneration:
    """Tests for user ID generation."""

    def test_generate_user_id_format(self):
        """User ID should be a valid UUID string."""
        user_id = generate_user_id()
        # UUID format: 8-4-4-4-12 hex digits
        parts = user_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_generate_user_id_unique(self):
        """Each user ID should be unique."""
        id1 = generate_user_id()
        id2 = generate_user_id()
        assert id1 != id2


class TestFullAuthFlow:
    """Tests for complete authentication flow."""

    def test_registration_flow(self):
        """Test complete registration flow."""
        # Client side
        master_password = "my_secure_password_123"
        salt = generate_salt()
        auth_key = derive_auth_key(master_password, salt)
        auth_key_hash = hash_auth_key(auth_key)

        # Server stores hash and salt
        # (In real app, this goes to database)

        # Client later authenticates
        auth_key_again = derive_auth_key(master_password, salt)

        # Server verifies
        assert verify_auth_key(auth_key_again, auth_key_hash) is True

    def test_wrong_password_fails(self):
        """Test that wrong password fails verification."""
        # Client registers with password
        master_password = "correct_password"
        salt = generate_salt()
        auth_key = derive_auth_key(master_password, salt)
        auth_key_hash = hash_auth_key(auth_key)

        # Attacker tries with wrong password
        wrong_password = "wrong_password"
        wrong_auth_key = derive_auth_key(wrong_password, salt)

        # Verification should fail
        assert verify_auth_key(wrong_auth_key, auth_key_hash) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
