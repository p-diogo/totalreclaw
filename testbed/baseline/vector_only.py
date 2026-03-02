"""
Vector-Only Search Algorithm

Pure semantic search using cosine similarity on document embeddings.

This baseline establishes the floor for semantic search performance. It performs
well on conceptual queries and paraphrases but struggles with exact matches like
IDs, error codes, or specific strings.
"""

from typing import List, Tuple
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Global model cache to avoid reloading
_model = None
_model_name = 'all-MiniLM-L6-v2'


def _get_embedding_model():
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(_model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for vector search. "
                "Install it with: pip install sentence-transformers"
            )
    return _model


def vector_only_search(
    query: str,
    embeddings: np.ndarray,
    top_k: int = 5,
    model_name: str = 'all-MiniLM-L6-v2'
) -> List[Tuple[int, float]]:
    """
    Pure vector semantic search using cosine similarity.

    This function encodes the query using the same embedding model used for
    documents, then calculates cosine similarity to find the most semantically
    similar documents.

    Args:
        query: The search query string
        embeddings: Pre-computed document embeddings as numpy array (n_docs, dim)
        top_k: Number of top results to return
        model_name: Name of the sentence-transformers model to use

    Returns:
        List of tuples (doc_index, score) sorted by score descending

    Example:
        >>> embeddings = np.array([[0.1, 0.2], [0.3, 0.4]])
        >>> results = vector_only_search("database connection", embeddings)
        >>> results[0]  # (1, 0.98) - second document is most similar
    """
    if embeddings is None or len(embeddings) == 0:
        return []

    if not query or not query.strip():
        return []

    # Get or reload model if model name changed
    global _model, _model_name
    if _model is None or _model_name != model_name:
        _model_name = model_name
        _model = _get_embedding_model()

    # Encode query
    query_embedding = _model.encode([query])[0]

    # Calculate cosine similarity
    # Reshape query to (1, dim) for sklearn
    similarities = cosine_similarity([query_embedding], embeddings)[0]

    # Get top-k indices
    top_k = min(top_k, len(similarities))
    top_indices = np.argsort(similarities)[::-1][:top_k]

    # Return results with positive similarity only
    results = []
    for idx in top_indices:
        score = similarities[idx]
        if score > 0:  # Only return results with positive similarity
            results.append((int(idx), float(score)))

    return results


def compute_embeddings(
    documents: List[str],
    model_name: str = 'all-MiniLM-L6-v2',
    batch_size: int = 32
) -> np.ndarray:
    """
    Compute embeddings for a list of documents.

    Args:
        documents: List of document strings
        model_name: Name of the sentence-transformers model
        batch_size: Batch size for encoding

    Returns:
        Numpy array of shape (n_docs, embedding_dim)
    """
    if not documents:
        return np.array([])

    model = _get_embedding_model()
    embeddings = model.encode(documents, batch_size=batch_size, show_progress_bar=False)
    return np.array(embeddings)


def clear_model_cache():
    """Clear the cached model. Useful for testing or memory management."""
    global _model
    _model = None
