"""
OpenMemory v0.2 - Zero-Knowledge E2EE Memory System

This module implements the two-pass encrypted search system:
- Pass 1 (Remote): Vector KNN search on embeddings (server-side)
- Pass 2 (Local): BM25 reranking on decrypted plaintext (client-side)

Zero-Knowledge Properties:
- Server never sees plaintext, keys, or query plaintext
- Server stores: ciphertext, embeddings, blind indices only
"""

from .client import OpenMemoryClientV02
from .server import MockOpenMemoryServer
from .crypto import CryptoManager
from .search import SearchResult, TwoPassSearch

__version__ = "0.2.0"
__all__ = [
    "OpenMemoryClientV02",
    "MockOpenMemoryServer",
    "CryptoManager",
    "SearchResult",
    "TwoPassSearch",
]
