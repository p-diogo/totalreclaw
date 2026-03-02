"""
Vector Embedding Module

Generates embeddings using all-MiniLM-L6-v2 (384-dimensional) as specified
in the TotalReclaw testbed requirements.
"""

import numpy as np
from typing import List, Union, Optional
from pathlib import Path
import hashlib

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    import onnxruntime as ort
except ImportError:
    ort = None


class EmbeddingModel:
    """Base class for embedding models"""

    def encode(self, texts: Union[str, List[str]]) -> np.ndarray:
        """Encode text(s) to embeddings"""
        raise NotImplementedError


class SentenceTransformerEmbedding(EmbeddingModel):
    """SentenceTransformer implementation using all-MiniLM-L6-v2"""

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def __init__(self, model_name: Optional[str] = None):
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers is required. "
                "Install with: pip install sentence-transformers"
            )

        self.model_name = model_name or self.MODEL_NAME
        self.model = SentenceTransformer(self.model_name)
        self.embedding_dim = self.EMBEDDING_DIM

    def encode(
        self,
        texts: Union[str, List[str]],
        normalize: bool = True
    ) -> np.ndarray:
        """
        Encode text(s) to embeddings

        Args:
            texts: Single text string or list of strings
            normalize: Whether to L2-normalize embeddings (for cosine similarity)

        Returns:
            numpy array of shape (n_texts, embedding_dim) or (embedding_dim,)
        """
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False
        )

        return embeddings

    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        normalize: bool = True
    ) -> np.ndarray:
        """
        Encode a batch of texts efficiently

        Args:
            texts: List of text strings
            batch_size: Batch size for encoding
            normalize: Whether to L2-normalize embeddings

        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=True
        )

        return embeddings


class ONNXEmbedding(EmbeddingModel):
    """
    ONNX Runtime implementation for all-MiniLM-L6-v2

    This is the production deployment option for TotalReclaw,
    providing faster inference with quantized models.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    # Mean pooling for sentence-transformers models
    @staticmethod
    def mean_pooling(token_embeddings, attention_mask):
        """Mean pooling to get sentence embeddings from token embeddings"""
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def __init__(self, model_path: Optional[Path] = None):
        if ort is None:
            raise ImportError(
                "onnxruntime is required. "
                "Install with: pip install onnxruntime"
            )

        # Try to import torch for preprocessing
        try:
            import torch
            from transformers import AutoTokenizer
            self.torch_available = True
            self.tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
            self.torch = torch
        except ImportError:
            self.torch_available = False
            print("Warning: torch not available, ONNX model will be limited")

        if model_path is None:
            # Use default ONNX model path
            model_path = Path(__file__).parent.parent.parent / "models" / "all-MiniLM-L6-v2.onnx"

        if not model_path.exists():
            raise FileNotFoundError(
                f"ONNX model not found at {model_path}. "
                "Please download or export the model first."
            )

        self.session = ort.InferenceSession(str(model_path))
        self.embedding_dim = self.EMBEDDING_DIM

    def encode(
        self,
        texts: Union[str, List[str]],
        normalize: bool = True
    ) -> np.ndarray:
        """Encode text(s) to embeddings using ONNX model"""
        if not self.torch_available:
            raise RuntimeError("ONNX encoding requires torch for tokenization")

        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        embeddings = []
        for text in texts:
            # Tokenize
            encoded = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                return_tensors="pt"
            )

            # Run ONNX inference
            inputs = {
                "input_ids": encoded["input_ids"].numpy(),
                "attention_mask": encoded["attention_mask"].numpy(),
            }

            # Add token_type_ids if model expects it
            if "token_type_ids" in [i.name for i in self.session.get_inputs()]:
                inputs["token_type_ids"] = encoded.get("token_type_ids",
                    self.torch.zeros_like(encoded["input_ids"])).numpy()

            outputs = self.session.run(None, inputs)

            # Mean pooling (sentence-transformers style)
            last_hidden_state = outputs[0]
            attention_mask = encoded["attention_mask"].numpy()
            input_mask_expanded = np.expand_dims(attention_mask, -1)
            sum_embeddings = np.sum(last_hidden_state * input_mask_expanded, 1)
            sum_mask = np.clip(np.sum(input_mask_expanded, 1), a_min=1e-9)
            embedding = sum_embeddings / sum_mask[:, np.newaxis]

            # Normalize if requested
            if normalize:
                embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)

            embeddings.append(embedding[0])

        embeddings = np.array(embeddings)
        return embeddings[0] if single_input else embeddings


class CachedEmbedding(EmbeddingModel):
    """Wrapper that caches embeddings to avoid recomputation"""

    def __init__(self, base_model: EmbeddingModel):
        self.base_model = base_model
        self.cache = {}

    def encode(
        self,
        texts: Union[str, List[str]],
        normalize: bool = True
    ) -> np.ndarray:
        """Encode with caching"""
        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        results = []
        cache_hits = 0

        for text in texts:
            # Create cache key
            key = hashlib.md5(text.encode()).hexdigest()

            if key in self.cache:
                cache_hits += 1
                results.append(self.cache[key])
            else:
                embedding = self.base_model.encode([text], normalize=normalize)[0]
                self.cache[key] = embedding
                results.append(embedding)

        # Log cache efficiency for batches
        if len(texts) > 10:
            hit_rate = cache_hits / len(texts)
            print(f"Cache hit rate: {hit_rate:.1%}")

        results = np.array(results)
        return results[0] if single_input else results

    def clear_cache(self):
        """Clear the embedding cache"""
        self.cache.clear()


def get_embedding_model(
    model_type: str = "sentence-transformer",
    model_path: Optional[Path] = None,
    use_cache: bool = True
) -> EmbeddingModel:
    """
    Get an embedding model instance

    Args:
        model_type: Type of model ("sentence-transformer" or "onnx")
        model_path: Path to ONNX model (for ONNX type)
        use_cache: Whether to use caching

    Returns:
        EmbeddingModel instance
    """
    if model_type == "sentence-transformer":
        model = SentenceTransformerEmbedding()
    elif model_type == "onnx":
        model = ONNXEmbedding(model_path)
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    if use_cache:
        model = CachedEmbedding(model)

    return model


# Convenience functions for backward compatibility
def encode_texts(texts: Union[str, List[str]]) -> np.ndarray:
    """
    Encode text(s) using the default model

    Args:
        texts: Text string or list of strings

    Returns:
        Embedding array
    """
    model = SentenceTransformerEmbedding()
    return model.encode(texts)


def compute_similarity(embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between two sets of embeddings

    Args:
        embeddings1: Array of shape (n1, dim) or (dim,)
        embeddings2: Array of shape (n2, dim) or (dim,)

    Returns:
        Similarity matrix of shape (n1, n2) or scalar
    """
    # Ensure 2D arrays
    if embeddings1.ndim == 1:
        embeddings1 = embeddings1.reshape(1, -1)
    if embeddings2.ndim == 1:
        embeddings2 = embeddings2.reshape(1, -1)

    # Normalize for cosine similarity
    embeddings1 = embeddings1 / np.linalg.norm(embeddings1, axis=1, keepdims=True)
    embeddings2 = embeddings2 / np.linalg.norm(embeddings2, axis=1, keepdims=True)

    # Compute dot product
    return embeddings1 @ embeddings2.T


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate embeddings")
    parser.add_argument("--text", "-t", help="Text to encode")
    parser.add_argument("--batch", "-b", help="File with texts to encode (one per line)")
    parser.add_argument("--output", "-o", help="Output numpy file for embeddings")

    args = parser.parse_args()

    model = get_embedding_model()

    if args.text:
        embedding = model.encode(args.text)
        print(f"Embedding shape: {embedding.shape}")
        print(f"First 10 values: {embedding[:10]}")
    elif args.batch:
        with open(args.batch) as f:
            texts = [line.strip() for line in f if line.strip()]

        embeddings = model.encode_batch(texts)
        print(f"Generated {len(embeddings)} embeddings of shape {embeddings.shape}")

        if args.output:
            np.save(args.output, embeddings)
            print(f"Saved to {args.output}")
