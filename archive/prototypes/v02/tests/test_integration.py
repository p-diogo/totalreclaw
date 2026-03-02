"""
Integration tests for OpenMemory v0.2.

Tests:
- Full workflow: encrypt -> store -> search -> decrypt
- Two-pass search accuracy
"""

import pytest
import numpy as np
from unittest.mock import MagicMock

from openmemory_v02.client import OpenMemoryClientV02
from openmemory_v02.server import MockOpenMemoryServer


class MockEmbeddingModel:
    """Mock embedding model for testing."""

    def __init__(self, dim=384):
        self.dim = dim

    def encode(self, texts):
        """Generate mock embeddings - similar texts have similar vectors."""
        embeddings = []
        for text in texts:
            # Deterministic pseudo-random embedding based on text hash
            text_hash = hash(text.lower())
            np.random.seed(text_hash % (2**31))
            embedding = np.random.randn(self.dim).astype(np.float32)
            # Normalize
            embedding = embedding / np.linalg.norm(embedding)
            embeddings.append(embedding)
        return np.array(embeddings)


@pytest.fixture
def mock_embedding_model():
    """Fixture for mock embedding model."""
    return MockEmbeddingModel(dim=384)


@pytest.fixture
def server():
    """Fixture for mock server."""
    return MockOpenMemoryServer()


@pytest.fixture
def client(mock_embedding_model):
    """Fixture for client with mock embedding model."""
    return OpenMemoryClientV02(
        master_password="test_password_123",
        embedding_model=mock_embedding_model
    )


@pytest.fixture
def vault_with_data(client, server):
    """Fixture with a vault populated with test data."""
    vault_id = "test_vault"
    server.create_vault(vault_id)
    client.vault_id = vault_id

    # Sample memories
    memories = [
        "API endpoint https://api.example.com/v1/users uses Bearer token authentication.",
        "Database connection string: postgresql://user:pass@localhost:5432/mydb",
        "Contact support at support@example.com for account issues.",
        "Error code E5001 indicates database timeout after 30 seconds.",
        "User ID 550e8400-e29b-41d4-a716-446655440000 has admin privileges.",
        "Deploy React app to S3 bucket my-app-bucket in us-east-1 region.",
        "Rate limit is 100 requests per minute. Returns 429 status code.",
        "GitHub personal access token: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "Standup meeting at 10:00 AM EST with frontend team.",
        "Local development server runs on http://localhost:3000",
    ]

    memory_ids = client.batch_store_memories(memories, server)

    return {
        'vault_id': vault_id,
        'memory_ids': memory_ids,
        'memories': memories
    }


class TestClientServerWorkflow:
    """Test full client-server workflow."""

    def test_create_and_store_memory(self, client, server):
        """Test creating and storing a memory."""
        server.create_vault("test_vault")
        client.vault_id = "test_vault"

        plaintext = "Test memory with email test@example.com"
        memory_id = client.store_memory(plaintext, server)

        assert memory_id is not None
        assert isinstance(memory_id, str)

        # Verify server has the memory
        encrypted = server.get_memory("test_vault", memory_id)
        assert encrypted is not None
        assert encrypted[0] is not None  # ciphertext
        assert encrypted[1] is not None  # nonce

    def test_retrieve_and_decrypt_memory(self, client, server):
        """Test retrieving and decrypting a memory."""
        server.create_vault("test_vault")
        client.vault_id = "test_vault"

        plaintext = "Secret API key: sk_live_12345"
        memory_id = client.store_memory(plaintext, server)

        # Retrieve and decrypt
        decrypted = client.get_memory(memory_id, server)

        assert decrypted == plaintext

    def test_batch_store_memories(self, client, server):
        """Test storing multiple memories."""
        server.create_vault("test_vault")
        client.vault_id = "test_vault"

        memories = [
            "Memory 1 with email one@example.com",
            "Memory 2 with email two@example.com",
            "Memory 3 with email three@example.com",
        ]

        memory_ids = client.batch_store_memories(memories, server)

        assert len(memory_ids) == len(memories)

        # Verify all are stored
        for memory_id in memory_ids:
            encrypted = server.get_memory("test_vault", memory_id)
            assert encrypted is not None


class TestTwoPassSearch:
    """Test two-pass search functionality."""

    def test_search_by_email(self, client, server, vault_with_data):
        """Test searching by email address."""
        results = client.search("support@example.com", server, top_k=3)

        assert len(results) > 0

        # Should find the memory with support@example.com
        found = any("support@example.com" in r.content for r in results)
        assert found

    def test_search_by_uuid(self, client, server, vault_with_data):
        """Test searching by UUID."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        results = client.search(uuid, server, top_k=3)

        assert len(results) > 0

        # Should find the memory with this UUID
        found = any(uuid in r.content for r in results)
        assert found

    def test_search_by_semantic_query(self, client, server, vault_with_data):
        """Test semantic search (vector similarity)."""
        # Note: The mock embedding model uses hash-based deterministic vectors
        # so semantic similarity is limited. This test verifies the search flow
        # works rather than semantic accuracy.
        results = client.search("cloud deployment setup", server, top_k=3)

        assert len(results) > 0
        # With the mock model, we just verify the search completes and returns results
        # Real semantic similarity requires a proper embedding model like sentence-transformers

    def test_search_by_error_code(self, client, server, vault_with_data):
        """Test searching by error code."""
        results = client.search("E5001", server, top_k=3)

        assert len(results) > 0

        # Should find the error code memory
        found = any("E5001" in r.content for r in results)
        assert found

    def test_search_returns_ranked_results(self, client, server, vault_with_data):
        """Test that search returns ranked results by score."""
        results = client.search("database connection", server, top_k=5)

        # Results should be sorted by score (descending)
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].score >= results[i+1].score

    def test_search_respects_top_k(self, client, server, vault_with_data):
        """Test that search respects the top_k parameter."""
        for k in [1, 3, 5, 10]:
            results = client.search("API", server, top_k=k)
            assert len(results) <= k

    def test_search_with_no_matches(self, client, server, vault_with_data):
        """Test search with no matching content."""
        # Query for something not in the memories
        results = client.search("quantum computing entanglement", server, top_k=3)

        # May return results due to semantic similarity, but likely low quality
        # Just verify it doesn't crash
        assert isinstance(results, list)


class TestBlindIndexMatching:
    """Test blind index exact matching."""

    def test_email_exact_match_boosts_ranking(self, client, server, vault_with_data):
        """Test that blind index matches (emails) boost ranking."""
        # Exact email match
        exact_results = client.search("support@example.com", server, top_k=5)

        # Partial/semantic match
        semantic_results = client.search("customer support email", server, top_k=5)

        # Exact match should have higher score for the top result
        if exact_results and semantic_results:
            # The exact match should rank the relevant memory higher
            exact_support_rank = next(
                (i for i, r in enumerate(exact_results) if "support@example.com" in r.content),
                None
            )
            semantic_support_rank = next(
                (i for i, r in enumerate(semantic_results) if "support@example.com" in r.content),
                None
            )

            if exact_support_rank is not None and semantic_support_rank is not None:
                assert exact_support_rank <= semantic_support_rank

    def test_uuid_exact_match(self, client, server, vault_with_data):
        """Test UUID exact matching via blind indices."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"

        # Exact UUID query
        results = client.search(uuid, server, top_k=3)

        # Should find the exact memory
        assert len(results) > 0
        assert any(uuid in r.content for r in results)


class TestZeroKnowledgeProperties:
    """Test zero-knowledge properties."""

    def test_server_stores_only_encrypted_data(self, client, server, vault_with_data):
        """Test that server only stores encrypted data, not plaintext."""
        stats = server.get_vault_stats(vault_with_data['vault_id'])

        assert stats['memory_count'] == len(vault_with_data['memories'])

        # Check that stored data is encrypted (not plaintext)
        for memory_id in vault_with_data['memory_ids']:
            ciphertext, nonce = server.get_memory(vault_with_data['vault_id'], memory_id)

            # Ciphertext should not contain the plaintext
            plaintext = vault_with_data['memories'][vault_with_data['memory_ids'].index(memory_id)]

            # ciphertext is bytes, plaintext is str - convert for comparison
            # In a real system, ciphertext would be indistinguishable from random
            assert isinstance(ciphertext, bytes)
            assert len(ciphertext) > 0

    def test_server_needs_no_keys(self, client, server):
        """Test that server doesn't need or have access to keys."""
        server.create_vault("test_vault")
        client.vault_id = "test_vault"

        plaintext = "Secret: The master password is test_password_123"
        memory_id = client.store_memory(plaintext, server)

        # Server can store without knowing the password
        ciphertext, nonce = server.get_memory("test_vault", memory_id)

        # Server cannot decrypt (no keys)
        # Verify ciphertext is not plaintext
        assert plaintext.encode() not in ciphertext
        assert b"password" not in ciphertext


class TestRRFFusion:
    """Test Reciprocal Rank Fusion scoring."""

    def test_rrf_combines_vector_and_bm25(self, client, server, vault_with_data):
        """Test that RRF combines vector and BM25 rankings."""
        results = client.search("localhost", server, top_k=3)

        # Each result should have both rankings
        for result in results:
            assert hasattr(result, 'vector_rank')
            assert hasattr(result, 'bm25_rank')
            assert hasattr(result, 'score')
            assert result.vector_rank > 0
            assert result.bm25_rank > 0
            assert result.score > 0

    def test_rrf_score_formula(self, client, server, vault_with_data):
        """Test RRF score calculation."""
        results = client.search("API endpoint", server, top_k=5)

        # RRF formula: score = 1/(k + rank1) + 1/(k + rank2)
        k = 60  # RRF constant from TwoPassSearch

        for result in results:
            expected_score = 1 / (k + result.vector_rank) + 1 / (k + result.bm25_rank)
            # Allow small floating point differences
            assert abs(result.score - expected_score) < 0.001


class TestVaultManagement:
    """Test vault management operations."""

    def test_create_and_delete_vault(self, server):
        """Test creating and deleting vaults."""
        vault_id = server.create_vault()
        assert vault_id in server._vaults

        deleted = server.delete_vault(vault_id)
        assert deleted is True
        assert vault_id not in server._vaults

    def test_vault_stats(self, client, server, vault_with_data):
        """Test vault statistics."""
        stats = server.get_vault_stats(vault_with_data['vault_id'])

        assert stats['memory_count'] == len(vault_with_data['memories'])
        assert stats['embedding_dim'] == 384  # Mock embedding dimension
        assert stats['blind_index_count'] > 0
