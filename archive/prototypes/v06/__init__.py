"""
OpenMemory v0.6 - Encrypted BM25 Index

This module implements the v0.6 specification with:
- Full corpus BM25 index (encrypted storage)
- Query expansion for improved recall
- RRF fusion of BM25 + vector search
- Zero-knowledge encryption

Components:
- BM25Index: Serializable BM25 index with add/remove/search
- QueryExpansion: LLM-based query expansion
- EncryptedBM25Index: AES-GCM encrypted index storage
"""

from .bm25_index import BM25Index, EncryptedBM25Index
from .query_expansion import ExpandedQuery, expand_query
from .search import search_v06, SearchTiming, SearchResult

__version__ = "0.6.0"
__all__ = [
    "BM25Index",
    "EncryptedBM25Index",
    "ExpandedQuery",
    "expand_query",
    "search_v06",
    "SearchTiming",
    "SearchResult",
]
