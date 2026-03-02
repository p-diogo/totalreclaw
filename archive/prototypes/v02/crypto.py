"""
Cryptographic primitives for OpenMemory v0.2

Implements:
- HKDF key derivation from master password
- AES-GCM encryption/decryption
- HMAC-SHA256 blind indices for exact-match queries
"""

import os
import re
import hmac
import hashlib
from typing import List, Tuple
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass
class DerivedKeys:
    """Derived keys from master password"""
    data_key: bytes  # 32 bytes for AES-256-GCM
    blind_key: bytes  # 32 bytes for HMAC-SHA256


@dataclass
class EncryptedMemory:
    """Encrypted memory stored on server"""
    ciphertext: bytes
    nonce: bytes
    blind_indices: List[str]
    # Note: embeddings are stored separately in vector DB


class CryptoManager:
    """
    Manages cryptographic operations for OpenMemory v0.2

    Zero-Knowledge Properties:
    - Keys are derived client-side only
    - Server never sees plaintext or keys
    """

    # HKDF parameters
    _HKDF_SALT = b'openmemory-v02-salt'  # In production: use random per-vault salt
    _HKDF_INFO = b'openmemory-key-derivation-v02'

    # Blind index patterns (regex)
    _EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    _UUID_PATTERN = re.compile(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b')
    _API_KEY_PATTERN = re.compile(r'\b[A-Za-z0-9/_-]{32,}\b')  # Generic API keys
    _ERROR_CODE_PATTERN = re.compile(r'\b[Ee]rror\s+[A-Z0-9_-]+\b|\b[A-Z]{1,}\d{3,}\b')  # Error codes like E5001

    def __init__(self, master_password: str):
        """
        Initialize crypto manager with master password.

        Args:
            master_password: User's master password (never stored, only used for derivation)
        """
        self.master_password = master_password
        self._derived_keys = None

    def derive_keys(self, salt: bytes = None) -> DerivedKeys:
        """
        Derive data key and blind key from master password using HKDF.

        Args:
            salt: Optional salt for key derivation (uses default if not provided)

        Returns:
            DerivedKeys containing data_key (32B) and blind_key (32B)
        """
        if self._derived_keys is None:
            kdf_salt = salt or self._HKDF_SALT

            # Derive 64 bytes: 32 for data key, 32 for blind key
            kdf = HKDF(
                algorithm=hashes.SHA256(),
                length=64,  # 32 + 32 bytes
                salt=kdf_salt,
                info=self._HKDF_INFO,
            )

            derived = kdf.derive(self.master_password.encode())
            self._derived_keys = DerivedKeys(
                data_key=derived[:32],
                blind_key=derived[32:]
            )

        return self._derived_keys

    def encrypt(self, plaintext: str) -> EncryptedMemory:
        """
        Encrypt plaintext using AES-256-GCM.

        Args:
            plaintext: The plaintext to encrypt

        Returns:
            EncryptedMemory with ciphertext, nonce, and blind indices
        """
        keys = self.derive_keys()

        # Generate random nonce (12 bytes for GCM)
        nonce = os.urandom(12)

        # Encrypt with AES-GCM
        cipher = AESGCM(keys.data_key)
        ciphertext = cipher.encrypt(nonce, plaintext.encode(), associated_data=None)

        # Generate blind indices
        blind_indices = self._generate_blind_indices(plaintext, keys.blind_key)

        return EncryptedMemory(
            ciphertext=ciphertext,
            nonce=nonce,
            blind_indices=blind_indices
        )

    def decrypt(self, ciphertext: bytes, nonce: bytes) -> str:
        """
        Decrypt ciphertext using AES-256-GCM.

        Args:
            ciphertext: The ciphertext to decrypt
            nonce: The nonce used during encryption

        Returns:
            Decrypted plaintext string

        Raises:
            cryptography.exceptions.InvalidTag: If authentication fails
        """
        keys = self.derive_keys()

        cipher = AESGCM(keys.data_key)
        plaintext = cipher.decrypt(nonce, ciphertext, associated_data=None)

        return plaintext.decode()

    def _generate_blind_indices(self, plaintext: str, blind_key: bytes) -> List[str]:
        """
        Generate HMAC-SHA256 blind indices for exact-match entities.

        Blind indices allow exact-match queries without revealing the plaintext
        to the server. The server can match blind hashes but cannot reverse them.

        Args:
            plaintext: The plaintext to extract entities from
            blind_key: The key for HMAC generation

        Returns:
            List of blind index hashes (hex-encoded)
        """
        blind_indices = []

        # Extract entities using regex patterns
        emails = self._EMAIL_PATTERN.findall(plaintext)
        uuids = self._UUID_PATTERN.findall(plaintext)
        api_keys = self._API_KEY_PATTERN.findall(plaintext)
        error_codes = self._ERROR_CODE_PATTERN.findall(plaintext)

        # Normalize and deduplicate entities
        all_entities = list(set([
            *(e.lower() for e in emails),
            *(u.lower() for u in uuids),
            *(k for k in api_keys if self._is_likely_api_key(k)),
            *(e.lower() for e in error_codes)
        ]))

        # Generate blind HMAC for each entity
        for entity in all_entities:
            blind_hash = hmac.new(
                blind_key,
                entity.encode(),
                hashlib.sha256
            ).hexdigest()
            blind_indices.append(blind_hash)

        return list(set(blind_indices))  # Remove duplicates

    def _is_likely_api_key(self, key: str) -> bool:
        """
        Heuristic to filter false positives from generic API key pattern.

        Args:
            key: The potential API key

        Returns:
            True if this looks like a real API key
        """
        # Must be at least 32 chars
        if len(key) < 32:
            return False

        # Check for common API key patterns
        # Has some entropy (mix of chars, not just repeats)
        unique_chars = len(set(key))
        if unique_chars < len(key) * 0.3:
            return False

        # Not just hex (might be a hash, not a key)
        if re.match(r'^[0-9a-fA-F]+$', key):
            return len(key) >= 40  # Allow longer hex keys

        return True

    def generate_query_blind_indices(self, query: str) -> List[str]:
        """
        Generate blind indices for a search query.

        Args:
            query: The search query

        Returns:
            List of blind index hashes
        """
        keys = self.derive_keys()
        return self._generate_blind_indices(query, keys.blind_key)

    def clear_keys(self):
        """
        Clear derived keys from memory.

        Call this after operations complete to minimize key exposure in memory.
        Note: In Python, this is a best-effort approach.
        """
        self._derived_keys = None
