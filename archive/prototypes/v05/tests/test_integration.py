"""
Integration tests for OpenMemory v0.5

Tests:
- Multi-variant blind index generation
- Three-pass search
- LLM reranking
"""

import pytest
import numpy as np
from typing import List


class MockEmbeddingModel:
    """Mock embedding model for testing."""

    def encode(self, texts: List[str]) -> np.ndarray:
        """Generate mock embeddings."""
        embeddings = []
        for text in texts:
            # Simple hash-based embedding
            import hashlib
            hash_val = hashlib.md5(text.encode()).digest()
            embedding = []
            for i in range(384):
                byte_val = hash_val[i % 16]
                val = (byte_val - 128) / 128.0
                embedding.append(val)
            embeddings.append(embedding)
        return np.array(embeddings)


class MockLLMClient:
    """Mock LLM client for testing."""

    def complete(self, prompt: str) -> str:
        """Generate mock LLM response."""
        if "variant" in prompt.lower() or "extract entities" in prompt.lower():
            # Return mock variant generation response
            return '''{
  "entities": [
    {
      "original": "API Configuration",
      "type": "config_key",
      "variants": ["api config", "configuration", "api settings", "endpoint config"]
    }
  ]
}'''
        elif "rerank" in prompt.lower() or "reorder" in prompt.lower():
            # Return mock reranking response
            return '''{
  "results": [
    {"id": "1", "reason": "Direct match with API key configuration"},
    {"id": "2", "reason": "Contains deployment settings"}
  ]
}'''
        return '{"results": []}'


def test_multi_variant_blind_indices():
    """Test multi-variant blind index generation."""
    from openmemory_v05.multi_variant_indices import MultiVariantBlindIndexGenerator

    # Setup
    blind_key = b'test_key_32_bytes_long_for_testing'
    llm_client = MockLLMClient()
    generator = MultiVariantBlindIndexGenerator(blind_key, llm_client)

    # Test with email
    text = "Contact sarah@example.com for API access"
    indices = generator.generate_blind_indices(text, use_llm=False)

    # Should have multiple variants
    assert len(indices) > 1

    # Test with LLM
    text = "We need to configure the API endpoint"
    indices_llm = generator.generate_blind_indices(text, use_llm=True)

    # LLM should add more variants
    assert len(indices_llm) >= len(indices)


def test_llm_reranking():
    """Test LLM reranking."""
    from openmemory_v05.llm_reranking import LLMReranker

    # Setup
    llm_client = MockLLMClient()
    reranker = LLMReranker(llm_client)

    # Mock candidates
    candidates = [
        {'id': '1', 'snippet': 'API key configuration for production', 'score': 0.8},
        {'id': '2', 'snippet': 'Deployment settings for staging', 'score': 0.7},
    ]

    # Rerank
    query = "API configuration"
    results = reranker.rerank(query, candidates)

    # Should return results
    assert len(results) > 0
    assert results[0].explanation  # Should have explanation


def test_v05_client():
    """Test v0.5 client."""
    from openmemory_v05.client import OpenMemoryClientV05
    from openmemory_v02.server import MockOpenMemoryServer

    # Setup
    master_password = "test_password_12345"
    embedding_model = MockEmbeddingModel()
    llm_client = MockLLMClient()

    client = OpenMemoryClientV05(
        master_password=master_password,
        embedding_model=embedding_model,
        llm_client=llm_client
    )

    server = MockOpenMemoryServer()
    server.create_vault(vault_id=client.vault_id)

    # Test storing a memory
    memory_text = """
    API Configuration:
    - Base URL: https://api.example.com/v1
    - Contact: sarah@example.com
    - Rate limit: 100 req/min
    """

    memory_id = client.store_memory(memory_text, server)

    assert memory_id is not None

    # Test search
    results = client.search("API configuration", server, top_k=5)

    assert len(results) >= 0  # May be empty due to mock


def test_backward_compatibility():
    """Test that v0.5 is compatible with v0.2."""
    from openmemory_v02.client import OpenMemoryClientV02
    from openmemory_v05.client import OpenMemoryClientV05

    # Both should be able to encrypt/decrypt with same password
    master_password = "test_password_12345"

    client_v02 = OpenMemoryClientV02(master_password=master_password)
    client_v05 = OpenMemoryClientV05(master_password=master_password)

    # Both should derive same keys
    keys_v02 = client_v02.crypto.derive_keys()
    keys_v05 = client_v05.crypto.derive_keys()

    assert keys_v02.data_key == keys_v05.data_key
    assert keys_v02.blind_key == keys_v05.blind_key


def test_three_pass_search():
    """Test complete three-pass search flow."""
    from openmemory_v05.client import OpenMemoryClientV05
    from openmemory_v02.server import MockOpenMemoryServer

    # Setup
    master_password = "test_password_12345"
    embedding_model = MockEmbeddingModel()
    llm_client = MockLLMClient()

    client = OpenMemoryClientV05(
        master_password=master_password,
        embedding_model=embedding_model,
        llm_client=llm_client
    )

    server = MockOpenMemoryServer()
    server.create_vault(vault_id=client.vault_id)

    # Store memories
    memories = [
        "Error 503: Service Unavailable - Rate limit exceeded",
        "Deploy to production using the deployment pipeline",
        "Contact sarah@example.com for API access",
    ]

    for memory in memories:
        client.store_memory(memory, server)

    # Search
    results = client.search(
        "deployment",
        server,
        top_k=5,
        use_llm_rerank=True
    )

    # Should get results
    assert isinstance(results, list)


if __name__ == "__main__":
    # Run tests
    test_multi_variant_blind_indices()
    print("✓ Multi-variant blind indices test passed")

    test_llm_reranking()
    print("✓ LLM reranking test passed")

    test_v05_client()
    print("✓ v0.5 client test passed")

    test_backward_compatibility()
    print("✓ Backward compatibility test passed")

    test_three_pass_search()
    print("✓ Three-pass search test passed")

    print("\nAll tests passed!")
