"""
OpenMemory v0.5 - Enhanced E2EE with Three-Pass Search

This module extends v0.2 with:
- Multi-variant blind indices (regex + LLM)
- Three-pass search (add LLM reranking)
- Context-aware entity extraction

Zero-Knowledge Properties:
- Server never sees plaintext, keys, or query plaintext
- All LLM operations happen locally
- Server stores: ciphertext, embeddings, blind indices only
"""

from .client import OpenMemoryClientV05
from .multi_variant_indices import MultiVariantBlindIndexGenerator
from .llm_reranking import LLMReranker
from .prompts import LLMVariantPrompt, LLMRerankPrompt

__version__ = "0.5.0"
__all__ = [
    "OpenMemoryClientV05",
    "MultiVariantBlindIndexGenerator",
    "LLMReranker",
    "LLMVariantPrompt",
    "LLMRerankPrompt",
]
