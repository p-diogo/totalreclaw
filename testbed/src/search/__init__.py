"""Search module for TotalReclaw testbed"""

from .vector import (
    EmbeddingModel,
    SentenceTransformerEmbedding,
    ONNXEmbedding,
    CachedEmbedding,
    get_embedding_model,
    encode_texts,
    compute_similarity
)

__all__ = [
    "EmbeddingModel",
    "SentenceTransformerEmbedding",
    "ONNXEmbedding",
    "CachedEmbedding",
    "get_embedding_model",
    "encode_texts",
    "compute_similarity"
]
