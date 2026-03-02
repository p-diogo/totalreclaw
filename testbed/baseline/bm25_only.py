"""
BM25-Only Search Algorithm

Pure keyword search using the BM25 ranking function from rank-bm25.

This is the simplest baseline and establishes the floor for keyword matching performance.
It performs well for exact matches (emails, IDs, error codes) but fails on semantic queries.
"""

from typing import List, Tuple
import re
import numpy as np
from .rank_bm25_portable import BM25OkapiPortable as BM25Okapi


def simple_tokenize(text: str) -> List[str]:
    """
    Simple tokenization for BM25.

    This tokenizes on word boundaries and handles common cases like emails, URLs,
    and code identifiers properly.
    """
    # Extract special tokens (emails, UUIDs, code identifiers)
    special_patterns = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # emails
        r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b',  # UUIDs
        r'\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\b',  # code identifiers
    ]

    # Find all special tokens
    special_tokens = []
    for pattern in special_patterns:
        matches = re.findall(pattern, text)
        special_tokens.extend(matches)

    # Remove special tokens from text and tokenize the rest
    for token in set(special_tokens):
        text = text.replace(token, ' ')

    # Tokenize remaining text on word boundaries
    words = re.findall(r'\b\w+\b', text.lower())

    # Combine special tokens (lowercased) with words
    return words + [t.lower() for t in special_tokens]


def bm25_only_search(
    query: str,
    documents: List[str],
    top_k: int = 5,
    k1: float = 1.5,
    b: float = 0.75,
    epsilon: float = 0.25
) -> List[Tuple[int, float]]:
    """
    Pure BM25 keyword search on plaintext documents.

    This function implements BM25 ranking, which improves upon TF-IDF by
    accounting for document length normalization and term frequency saturation.

    Args:
        query: The search query string
        documents: List of document strings to search
        top_k: Number of top results to return
        k1: BM25 parameter for term frequency saturation (default: 1.5)
        b: BM25 parameter for document length normalization (default: 0.75)
        epsilon: BM25 parameter for IDF floor (default: 0.25)

    Returns:
        List of tuples (doc_index, score) sorted by score descending

    Example:
        >>> docs = ["API key: sk-proj-abc123", "Database connection pool settings"]
        >>> results = bm25_only_search("API key configuration", docs, top_k=1)
        >>> results[0]  # (0, 2.34) - first document matches "API key"
    """
    if not documents:
        return []

    if not query or not query.strip():
        return []

    # Tokenize corpus and query
    tokenized_corpus = [simple_tokenize(doc) for doc in documents]
    tokenized_query = simple_tokenize(query)

    if not tokenized_query:
        return []

    # Initialize BM25
    bm25 = BM25Okapi(tokenized_corpus, k1=k1, b=b, epsilon=epsilon)

    # Get scores for all documents
    scores = bm25.get_scores(tokenized_query)

    # Filter out documents with negative scores (no matches)
    valid_indices = np.where(scores > 0)[0]

    if len(valid_indices) == 0:
        return []

    # Sort by score descending and get top-k
    top_indices = valid_indices[np.argsort(scores[valid_indices])[::-1][:top_k]]

    return [(int(idx), float(scores[idx])) for idx in top_indices]
