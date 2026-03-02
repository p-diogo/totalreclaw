"""
Unit tests for cryptographic operations in OpenMemory v0.2.

Tests:
- Key derivation from master password
- AES-GCM encryption/decryption
- Blind index generation
"""

import pytest
import numpy as np

from openmemory_v02.crypto import CryptoManager, EncryptedMemory


class TestKeyDerivation:
    """Test HKDF key derivation."""

    def test_derive_keys_generates_correct_length(self):
        """Test that derived keys are 64 bytes total (32 + 32)."""
        crypto = CryptoManager("test_password_123")
        keys = crypto.derive_keys()

        assert len(keys.data_key) == 32
        assert len(keys.blind_key) == 32
        assert isinstance(keys.data_key, bytes)
        assert isinstance(keys.blind_key, bytes)

    def test_derive_keys_deterministic_with_same_salt(self):
        """Test that same password + salt produces same keys."""
        crypto1 = CryptoManager("test_password_123")
        crypto2 = CryptoManager("test_password_123")

        salt = b"test_salt"
        keys1 = crypto1.derive_keys(salt=salt)
        keys2 = crypto2.derive_keys(salt=salt)

        assert keys1.data_key == keys2.data_key
        assert keys1.blind_key == keys2.blind_key

    def test_derive_keys_different_with_different_passwords(self):
        """Test that different passwords produce different keys."""
        crypto1 = CryptoManager("password_123")
        crypto2 = CryptoManager("password_456")

        keys1 = crypto1.derive_keys()
        keys2 = crypto2.derive_keys()

        assert keys1.data_key != keys2.data_key
        assert keys1.blind_key != keys2.blind_key


class TestEncryption:
    """Test AES-GCM encryption/decryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption are inverses."""
        crypto = CryptoManager("test_password_123")
        plaintext = "This is a test memory with some sensitive information."

        encrypted = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(encrypted.ciphertext, encrypted.nonce)

        assert decrypted == plaintext

    def test_encrypt_generates_unique_nonce(self):
        """Test that each encryption generates a unique nonce."""
        crypto = CryptoManager("test_password_123")
        plaintext = "Test memory"

        encrypted1 = crypto.encrypt(plaintext)
        encrypted2 = crypto.encrypt(plaintext)

        assert encrypted1.nonce != encrypted2.nonce
        assert len(encrypted1.nonce) == 12  # GCM standard nonce size

    def test_encrypt_same_plaintext_different_ciphertext(self):
        """Test that encrypting same plaintext twice produces different ciphertext."""
        crypto = CryptoManager("test_password_123")
        plaintext = "Test memory"

        encrypted1 = crypto.encrypt(plaintext)
        encrypted2 = crypto.encrypt(plaintext)

        assert encrypted1.ciphertext != encrypted2.ciphertext

    def test_decrypt_with_wrong_nonce_fails(self):
        """Test that decrypting with wrong nonce fails."""
        crypto = CryptoManager("test_password_123")
        plaintext = "Test memory"

        encrypted = crypto.encrypt(plaintext)

        # Try to decrypt with different nonce
        with pytest.raises(Exception):  # InvalidTag
            crypto.decrypt(encrypted.ciphertext, b"wrong_nonce_12")


class TestBlindIndices:
    """Test blind index generation."""

    def test_generate_blind_indices_for_email(self):
        """Test that emails are extracted and hashed."""
        crypto = CryptoManager("test_password_123")
        plaintext = "Contact support@example.com for help."

        keys = crypto.derive_keys()
        indices = crypto._generate_blind_indices(plaintext, keys.blind_key)

        assert len(indices) > 0
        # Should have generated a blind hash for the email
        assert all(isinstance(idx, str) for idx in indices)
        assert all(len(idx) == 64 for idx in indices)  # SHA256 hex = 64 chars

    def test_generate_blind_indices_for_uuid(self):
        """Test that UUIDs are extracted and hashed."""
        crypto = CryptoManager("test_password_123")
        plaintext = "User ID: 550e8400-e29b-41d4-a716-446655440000"

        keys = crypto.derive_keys()
        indices = crypto._generate_blind_indices(plaintext, keys.blind_key)

        assert len(indices) > 0

    def test_generate_blind_indices_for_api_key(self):
        """Test that API keys are extracted and hashed."""
        crypto = CryptoManager("test_password_123")
        # Pattern-like API key
        plaintext = "API key: sk_live_51MwN8hGpX7xK2yJ4zW9vB0cN3mF6qL8xT4nV5rY2bK9jH3gP7sD1fA6zC0wE4xR"

        keys = crypto.derive_keys()
        indices = crypto._generate_blind_indices(plaintext, keys.blind_key)

        assert len(indices) > 0

    def test_generate_blind_indices_deduplicates(self):
        """Test that duplicate entities produce single blind index."""
        crypto = CryptoManager("test_password_123")
        plaintext = "Email test@example.com and TEST@EXAMPLE.COM (same email)"

        keys = crypto.derive_keys()
        indices = crypto._generate_blind_indices(plaintext, keys.blind_key)

        # Should deduplicate case-insensitive
        # Email appears twice but should produce unique indices (normalized to lowercase)
        assert len(indices) == 1

    def test_generate_blind_indices_consistent(self):
        """Test that same entity produces same blind hash."""
        crypto1 = CryptoManager("test_password_123")
        crypto2 = CryptoManager("test_password_123")

        plaintext1 = "Email test@example.com"
        plaintext2 = "Email test@example.com"

        keys1 = crypto1.derive_keys()
        keys2 = crypto2.derive_keys()

        indices1 = crypto1._generate_blind_indices(plaintext1, keys1.blind_key)
        indices2 = crypto2._generate_blind_indices(plaintext2, keys2.blind_key)

        assert indices1 == indices2

    def test_query_blind_indices_match(self):
        """Test that query blind indices match entity indices."""
        crypto = CryptoManager("test_password_123")

        plaintext = "Contact support@example.com for help."
        query = "support@example.com"

        # Generate blind indices for both
        entity_indices = crypto.generate_query_blind_indices(plaintext)
        query_indices = crypto.generate_query_blind_indices(query)

        # Should have at least one matching index
        assert len(set(entity_indices) & set(query_indices)) > 0


class TestCryptoManager:
    """Test CryptoManager high-level operations."""

    def test_clear_keys(self):
        """Test that clear_keys removes derived keys."""
        crypto = CryptoManager("test_password_123")
        crypto.derive_keys()

        assert crypto._derived_keys is not None

        crypto.clear_keys()

        assert crypto._derived_keys is None

    def test_full_encrypt_search_workflow(self):
        """Test encrypt -> generate query blind indices -> match."""
        crypto = CryptoManager("test_password_123")

        # Encrypt a memory
        memory = "User john@example.com has UUID 550e8400-e29b-41d4-a716-446655440000"
        encrypted = crypto.encrypt(memory)

        assert encrypted.ciphertext is not None
        assert len(encrypted.blind_indices) >= 2  # At least email and UUID

        # Generate query blind indices
        query = "john@example.com"
        query_indices = crypto.generate_query_blind_indices(query)

        # Should match
        assert len(set(encrypted.blind_indices) & set(query_indices)) > 0
