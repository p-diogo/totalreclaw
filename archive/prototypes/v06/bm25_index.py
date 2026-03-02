"""
BM25 Index Implementation for OpenMemory v0.6

Implements a serializable BM25 index that can be:
1. Incrementally updated (add/remove documents)
2. Serialized to bytes for encrypted storage
3. Deserialized back from bytes
4. Searched on the full corpus (not just candidates)

Based on the v0.6 specification:
- Full corpus BM25 index (unlike v0.5's top-250 only)
- Encrypted storage on server
- Supports incremental updates
"""

import os
import pickle
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np


@dataclass
class BM25Index:
    """
    Serializable BM25 index structure for v0.6.

    This index can be incrementally updated and serialized for encrypted storage.
    Unlike v0.5, this indexes the FULL corpus, not just top-250 candidates.

    Attributes:
        doc_freqs: term -> document frequency
        idf: term -> IDF score
        doc_term_freqs: List of {term: freq} per document
        doc_lengths: List of document lengths (token counts)
        avgdl: Average document length
        version: Index format version
        created_at: ISO timestamp of creation
        doc_count: Number of documents in index
        k1: BM25 term frequency saturation parameter
        b: BM25 length normalization parameter
    """

    # Document frequencies
    doc_freqs: Dict[str, int] = field(default_factory=dict)

    # Inverse document frequencies
    idf: Dict[str, float] = field(default_factory=dict)

    # Term frequencies per document
    doc_term_freqs: List[Dict[str, int]] = field(default_factory=list)

    # Document lengths (token counts)
    doc_lengths: List[int] = field(default_factory=list)

    # Average document length
    avgdl: float = 0.0

    # Metadata
    version: str = "0.6.0"
    created_at: str = ""
    doc_count: int = 0

    # BM25 parameters
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self):
        """Initialize timestamp on creation."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenization for indexing.

        Extracts words and handles common patterns like emails, UUIDs.
        """
        import re

        # Special patterns
        special_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # emails
            r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b',  # UUIDs
            r'\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\b',  # code identifiers
        ]

        # Find special tokens
        special_tokens = []
        for pattern in special_patterns:
            matches = re.findall(pattern, text)
            special_tokens.extend(matches)

        # Remove special tokens and tokenize the rest
        for token in set(special_tokens):
            text = text.replace(token, ' ')

        # Word boundary tokenization
        words = re.findall(r'\b\w+\b', text.lower())

        return words + [t.lower() for t in special_tokens]

    def add_document(self, doc_id: int, content: str) -> None:
        """
        Add a document to the index.

        Args:
            doc_id: Document identifier (integer)
            content: Document text content
        """
        tokens = self._tokenize(content)

        # Ensure we have space for this doc_id
        while len(self.doc_term_freqs) <= doc_id:
            self.doc_term_freqs.append({})
            self.doc_lengths.append(0)

        # Remove old terms if document exists (for update case)
        if self.doc_term_freqs[doc_id]:
            for term in list(self.doc_term_freqs[doc_id].keys()):
                old_freq = self.doc_term_freqs[doc_id][term]
                self.doc_freqs[term] -= old_freq
                if self.doc_freqs[term] <= 0:
                    del self.doc_freqs[term]
                    if term in self.idf:
                        del self.idf[term]

        # Calculate term frequencies
        term_freqs = {}
        for token in tokens:
            term_freqs[token] = term_freqs.get(token, 0) + 1

        # Store term frequencies
        self.doc_term_freqs[doc_id] = term_freqs
        self.doc_lengths[doc_id] = len(tokens)

        # Update document frequencies
        for term in term_freqs:
            self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        # Update document count
        if doc_id >= self.doc_count:
            self.doc_count = doc_id + 1

        # Recalculate average document length
        valid_lengths = [l for l in self.doc_lengths[:self.doc_count] if l > 0]
        self.avgdl = sum(valid_lengths) / len(valid_lengths) if valid_lengths else 0

        # Recalculate IDF for all terms
        self._recalculate_idf()

    def remove_document(self, doc_id: int) -> bool:
        """
        Remove a document from the index.

        Args:
            doc_id: Document identifier to remove

        Returns:
            True if document was removed, False if not found
        """
        if doc_id >= len(self.doc_term_freqs) or not self.doc_term_freqs[doc_id]:
            return False

        # Decrement document frequencies
        for term in self.doc_term_freqs[doc_id]:
            self.doc_freqs[term] -= 1
            if self.doc_freqs[term] <= 0:
                del self.doc_freqs[term]
                if term in self.idf:
                    del self.idf[term]

        # Clear document data
        self.doc_term_freqs[doc_id] = {}
        self.doc_lengths[doc_id] = 0

        # Recalculate average document length
        valid_lengths = [l for l in self.doc_lengths[:self.doc_count] if l > 0]
        self.avgdl = sum(valid_lengths) / len(valid_lengths) if valid_lengths else 0

        # Recalculate IDF
        self._recalculate_idf()

        return True

    def _recalculate_idf(self) -> None:
        """Recalculate IDF scores for all terms in the index."""
        N = self.doc_count
        if N == 0:
            self.idf = {}
            return

        for term, df in self.doc_freqs.items():
            # IDF(qi) = log((N - df(qi) + 0.5) / (df(qi) + 0.5)) + 1
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            self.idf[term] = max(idf, 0.25)  # epsilon floor

    def search(
        self,
        query: str,
        top_k: int = 10,
        k1: Optional[float] = None,
        b: Optional[float] = None
    ) -> List[Tuple[int, float]]:
        """
        Search the full corpus using BM25 ranking.

        Args:
            query: Search query string
            top_k: Number of results to return
            k1: Override BM25 k1 parameter
            b: Override BM25 b parameter

        Returns:
            List of (doc_id, score) tuples sorted by score descending
        """
        k1 = k1 if k1 is not None else self.k1
        b = b if b is not None else self.b

        tokens = self._tokenize(query)

        if not tokens or self.doc_count == 0:
            return []

        # Calculate BM25 scores
        scores = np.zeros(self.doc_count)

        for token in tokens:
            if token not in self.idf:
                continue

            idf = self.idf[token]

            for doc_id in range(self.doc_count):
                if doc_id >= len(self.doc_term_freqs):
                    break

                term_freqs = self.doc_term_freqs[doc_id]
                if not term_freqs:
                    continue

                tf = term_freqs.get(token, 0)
                if tf == 0:
                    continue

                # BM25 formula
                doc_len = self.doc_lengths[doc_id]
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_len / (self.avgdl or 1))
                scores[doc_id] += idf * (numerator / denominator)

        # Get top-k results
        valid_indices = np.where(scores > 0)[0]

        if len(valid_indices) == 0:
            return []

        top_indices = valid_indices[np.argsort(scores[valid_indices])[::-1][:top_k]]

        return [(int(idx), float(scores[idx])) for idx in top_indices]

    def serialize(self) -> bytes:
        """
        Serialize the index to bytes for encrypted storage.

        Returns:
            Pickled bytes representation of the index
        """
        return pickle.dumps({
            'doc_freqs': self.doc_freqs,
            'idf': self.idf,
            'doc_term_freqs': self.doc_term_freqs,
            'doc_lengths': self.doc_lengths,
            'avgdl': self.avgdl,
            'version': self.version,
            'created_at': self.created_at,
            'doc_count': self.doc_count,
            'k1': self.k1,
            'b': self.b,
        })

    @classmethod
    def deserialize(cls, data: bytes) -> 'BM25Index':
        """
        Deserialize the index from bytes.

        Args:
            data: Pickled bytes from serialize()

        Returns:
            BM25Index instance
        """
        payload = pickle.loads(data)
        return cls(**payload)


@dataclass
class EncryptedBM25Index:
    """
    Encrypted BM25 index for server storage.

    The serialized index is encrypted using AES-256-GCM with a client-held key.
    The server only stores the ciphertext and cannot read the index contents.

    Attributes:
        ciphertext: Encrypted index data
        nonce: 12-byte nonce for AES-GCM
        tag: 16-byte authentication tag
        version: Index format version
        doc_count: Number of documents in index
        created_at: ISO timestamp
    """

    ciphertext: bytes
    nonce: bytes
    tag: bytes
    version: str = "0.6.0"
    doc_count: int = 0
    created_at: str = ""

    @classmethod
    def from_index(cls, index: BM25Index, encryption_key: bytes) -> 'EncryptedBM25Index':
        """
        Encrypt a BM25 index.

        Args:
            index: BM25Index to encrypt
            encryption_key: 32-byte AES-256 key

        Returns:
            EncryptedBM25Index instance
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        # Serialize the index
        plaintext = index.serialize()

        # Generate random nonce
        nonce = os.urandom(12)

        # Encrypt with AES-GCM
        aesgcm = AESGCM(encryption_key)
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, None)

        # Split ciphertext and tag (last 16 bytes are the tag)
        ciphertext = ciphertext_with_tag[:-16]
        tag = ciphertext_with_tag[-16:]

        return cls(
            ciphertext=ciphertext,
            nonce=nonce,
            tag=tag,
            version=index.version,
            doc_count=index.doc_count,
            created_at=index.created_at,
        )

    def decrypt(self, encryption_key: bytes) -> BM25Index:
        """
        Decrypt the index.

        Args:
            encryption_key: 32-byte AES-256 key

        Returns:
            BM25Index instance
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        # Reconstruct ciphertext with tag
        ciphertext_with_tag = self.ciphertext + self.tag

        # Decrypt
        aesgcm = AESGCM(encryption_key)
        plaintext = aesgcm.decrypt(self.nonce, ciphertext_with_tag, None)

        # Deserialize
        return BM25Index.deserialize(plaintext)
