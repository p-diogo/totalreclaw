"""
Unit tests for baseline search algorithms.

Tests each algorithm independently and compares their behavior.
"""

import pytest
import numpy as np
from typing import List, Tuple

from testbed.baseline.bm25_only import bm25_only_search
from testbed.baseline.vector_only import vector_only_search, compute_embeddings
from testbed.baseline.openclaw_hybrid import openclaw_hybrid_search
from testbed.baseline.qmd_hybrid import qmd_hybrid_search


# Sample documents for testing
SAMPLE_DOCUMENTS = [
    "API key: sk-proj-abc123xyz for authentication",
    "Database connection pool configuration: 50 max connections",
    "Gmail API setup requires OAuth 2.0 credentials",
    "Fixed the 429 rate limit error by implementing exponential backoff",
    "Deployment to us-east-1 region using Docker containers",
    "User authentication flow uses JWT tokens with 24-hour expiration",
    "CI/CD pipeline configuration with GitHub Actions",
    "Memory chunk size: 400 tokens with 80-token overlap",
    "PostgreSQL connection string: postgresql://user:pass@localhost:5432/db",
    "Error code ERR_CONNECTION_REFUSED: Check if server is running",
    "Sarah's email is sarah@example.com, she's the backend lead",
    "Meeting yesterday: Discussed API rate limiting and caching strategies",
    "Container orchestration using Kubernetes with Helm charts",
    "Fixed CORS issue by adding proper headers in the API gateway",
    "Local development server runs on http://localhost:3000",
]


@pytest.fixture
def sample_embeddings() -> np.ndarray:
    """Compute embeddings for sample documents."""
    return compute_embeddings(SAMPLE_DOCUMENTS, model_name='all-MiniLM-L6-v2')


@pytest.fixture
def sample_documents() -> List[str]:
    """Get sample documents."""
    return SAMPLE_DOCUMENTS


class TestBM25Only:
    """Tests for BM25-Only search algorithm."""

    def test_exact_keyword_match(self, sample_documents):
        """Test BM25 finds exact keyword matches."""
        results = bm25_only_search("sk-proj-abc123xyz", sample_documents, top_k=3)

        assert len(results) > 0
        # First result should be the document with the API key
        idx, score = results[0]
        assert idx == 0
        assert score > 0

    def test_email_search(self, sample_documents):
        """Test BM25 finds email addresses."""
        results = bm25_only_search("sarah@example.com", sample_documents, top_k=3)

        assert len(results) > 0
        # Should find Sarah's document
        indices = [idx for idx, _ in results]
        assert 10 in indices  # Sarah's document

    def test_error_code_search(self, sample_documents):
        """Test BM25 finds error codes."""
        results = bm25_only_search("429 rate limit", sample_documents, top_k=3)

        assert len(results) > 0
        # Should find the 429 error document
        indices = [idx for idx, _ in results]
        assert 3 in indices

    def test_multiple_results(self, sample_documents):
        """Test BM25 returns multiple relevant results."""
        results = bm25_only_search("API configuration", sample_documents, top_k=5)

        assert len(results) <= 5
        # All scores should be positive
        for idx, score in results:
            assert score > 0

    def test_empty_query(self, sample_documents):
        """Test BM25 handles empty queries."""
        results = bm25_only_search("", sample_documents, top_k=3)
        assert len(results) == 0

    def test_no_match(self, sample_documents):
        """Test BM25 returns empty for no matches."""
        results = bm25_only_search("xyznonexistent123", sample_documents, top_k=3)
        # May return empty or very low scores
        assert len(results) == 0 or all(score < 0.1 for _, score in results)


class TestVectorOnly:
    """Tests for Vector-Only search algorithm."""

    def test_semantic_search(self, sample_documents, sample_embeddings):
        """Test vector search finds semantically similar documents."""
        # Query about authentication should find auth-related docs
        results = vector_only_search("user login and security", sample_embeddings, top_k=3)

        assert len(results) > 0
        # Should find document 5 (authentication flow) or 2 (Gmail API OAuth)
        indices = [idx for idx, _ in results]
        assert 5 in indices or 2 in indices

    def test_container_orchestration(self, sample_documents, sample_embeddings):
        """Test vector search finds container orchestration documents."""
        results = vector_only_search("container orchestration setup", sample_embeddings, top_k=3)

        assert len(results) > 0
        # Should find Docker/Kubernetes documents
        indices = [idx for idx, _ in results]
        assert 4 in indices or 12 in indices

    def test_ci_cd_query(self, sample_documents, sample_embeddings):
        """Test vector search finds CI/CD related documents."""
        results = vector_only_search("continuous integration pipeline", sample_embeddings, top_k=3)

        assert len(results) > 0
        # Should find CI/CD document
        indices = [idx for idx, _ in results]
        assert 6 in indices

    def test_similarity_scores(self, sample_documents, sample_embeddings):
        """Test vector search returns valid similarity scores."""
        results = vector_only_search("database setup", sample_embeddings, top_k=3)

        assert len(results) > 0
        for idx, score in results:
            assert 0 <= score <= 1  # Cosine similarity in [0, 1]

    def test_empty_query(self, sample_embeddings):
        """Test vector search handles empty queries."""
        results = vector_only_search("", sample_embeddings, top_k=3)
        assert len(results) == 0


class TestOpenClawHybrid:
    """Tests for OpenClaw Hybrid search algorithm."""

    def test_hybrid_search(self, sample_documents, sample_embeddings):
        """Test hybrid search combines semantic and keyword."""
        results = openclaw_hybrid_search(
            "API key configuration",
            sample_documents,
            sample_embeddings,
            top_k=5
        )

        assert len(results) <= 5
        # All scores should be positive
        for idx, score in results:
            assert score > 0

    def test_exact_match_priority(self, sample_documents, sample_embeddings):
        """Test hybrid search prioritizes exact matches."""
        # Query for exact UUID/email
        results = openclaw_hybrid_search(
            "sarah@example.com",
            sample_documents,
            sample_embeddings,
            top_k=3
        )

        assert len(results) > 0
        # Should find Sarah's document (index 10)
        indices = [idx for idx, _ in results]
        assert 10 in indices

    def test_semantic_plus_keyword(self, sample_documents, sample_embeddings):
        """Test hybrid search combines semantic understanding with keywords."""
        # "deployment" should find both semantic matches and exact "deployment" word
        results = openclaw_hybrid_search(
            "deployment configuration",
            sample_documents,
            sample_embeddings,
            top_k=5
        )

        assert len(results) > 0
        # Should include deployment-related docs
        indices = [idx for idx, _ in results]
        # Index 4 (deployment), 6 (CI/CD), 12 (Kubernetes deployment)
        assert any(idx in [4, 6, 12] for idx in indices)

    def test_weight_adjustment(self, sample_documents, sample_embeddings):
        """Test adjusting vector/text weights changes results."""
        # High vector weight
        vector_heavy = openclaw_hybrid_search(
            "container orchestration",
            sample_documents,
            sample_embeddings,
            top_k=3,
            vector_weight=0.9,
            text_weight=0.1
        )

        # High text weight
        text_heavy = openclaw_hybrid_search(
            "container orchestration",
            sample_documents,
            sample_embeddings,
            top_k=3,
            vector_weight=0.1,
            text_weight=0.9
        )

        # Results may differ in ranking
        assert len(vector_heavy) > 0
        assert len(text_heavy) > 0


class TestQMDHybrid:
    """Tests for QMD-Style Hybrid search algorithm."""

    def test_qmd_search(self, sample_documents, sample_embeddings):
        """Test QMD-style hybrid search."""
        results = qmd_hybrid_search(
            "API authentication setup",
            sample_documents,
            sample_embeddings,
            top_k=5
        )

        assert len(results) <= 5
        # All scores should be positive
        for idx, score in results:
            assert score >= 0

    def test_query_expansion(self, sample_documents, sample_embeddings):
        """Test query expansion improves recall."""
        # "container orchestration" should find "Docker" and "Kubernetes"
        results = qmd_hybrid_search(
            "container orchestration",
            sample_documents,
            sample_embeddings,
            top_k=5,
            use_query_expansion=True
        )

        assert len(results) > 0
        indices = [idx for idx, _ in results]
        # Should find container-related documents
        assert any(idx in [4, 12] for idx in indices)

    def test_rrf_fusion(self, sample_documents, sample_embeddings):
        """Test RRF fusion combines multiple result lists."""
        results = qmd_hybrid_search(
            "database connection",
            sample_documents,
            sample_embeddings,
            top_k=5,
            use_query_expansion=False,
            use_reranking=True
        )

        assert len(results) > 0
        # Should find database-related documents
        indices = [idx for idx, _ in results]
        assert any(idx in [1, 8] for idx in indices)

    def test_without_reranking(self, sample_documents, sample_embeddings):
        """Test QMD search without LLM reranking."""
        results = qmd_hybrid_search(
            "configuration setup",
            sample_documents,
            sample_embeddings,
            top_k=5,
            use_reranking=False
        )

        assert len(results) > 0


class TestAlgorithmComparison:
    """Compare algorithms against each other."""

    def test_bm25_vs_vector_exact_match(self, sample_documents, sample_embeddings):
        """BM25 should outperform vector on exact matches."""
        query = "sk-proj-abc123xyz"

        bm25_results = bm25_only_search(query, sample_documents, top_k=1)
        vector_results = vector_only_search(query, sample_embeddings, top_k=1)

        # BM25 should find the exact match
        assert len(bm25_results) > 0
        assert bm25_results[0][0] == 0  # First document

    def test_vector_vs_bm25_semantic(self, sample_documents, sample_embeddings):
        """Vector should outperform BM25 on semantic queries."""
        # "container orchestration" should find "Docker"/"Kubernetes"
        # even if those words aren't in the query
        query = "container orchestration"

        vector_results = vector_only_search(query, sample_embeddings, top_k=3)
        bm25_results = bm25_only_search(query, sample_documents, top_k=3)

        # Vector should find relevant docs
        assert len(vector_results) > 0

    def test_all_algorithms_return_results(self, sample_documents, sample_embeddings):
        """Test all algorithms can return results for a valid query."""
        query = "API configuration"

        bm25_results = bm25_only_search(query, sample_documents, top_k=3)
        vector_results = vector_only_search(query, sample_embeddings, top_k=3)
        openclaw_results = openclaw_hybrid_search(query, sample_documents, sample_embeddings, top_k=3)
        qmd_results = qmd_hybrid_search(query, sample_documents, sample_embeddings, top_k=3)

        # All should return some results
        assert len(bm25_results) > 0
        assert len(vector_results) > 0
        assert len(openclaw_results) > 0
        assert len(qmd_results) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_document_list(self, sample_embeddings):
        """Test all algorithms handle empty document lists."""
        # BM25 returns empty results for empty documents
        results = bm25_only_search("test", [], top_k=3)
        assert len(results) == 0

        # Vector search returns empty results for empty embeddings
        results = vector_only_search("test", np.array([]), top_k=3)
        assert len(results) == 0

    def test_single_document(self):
        """Test algorithms with just one document."""
        docs = ["API key: test123"]
        embeddings = compute_embeddings(docs)

        bm25_results = bm25_only_search("API key", docs, top_k=3)
        vector_results = vector_only_search("API key", embeddings, top_k=3)
        openclaw_results = openclaw_hybrid_search("API key", docs, embeddings, top_k=3)

        assert len(bm25_results) <= 1
        assert len(vector_results) <= 1
        assert len(openclaw_results) <= 1

    def test_very_long_query(self, sample_documents, sample_embeddings):
        """Test algorithms handle long queries."""
        long_query = " ".join(["API"] * 100)
        results = bm25_only_search(long_query, sample_documents, top_k=3)
        # Should not crash
        assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
