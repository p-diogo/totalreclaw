"""
Tests for search endpoint.
"""
import pytest
import os
import sys
from datetime import datetime
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSearchEndpoint:
    """Tests for the /search endpoint."""

    @pytest.fixture
    def auth_headers(self, test_user):
        """Create auth headers for requests."""
        return {"Authorization": f"Bearer {test_user['auth_key'].hex()}"}

    @pytest.fixture
    def stored_facts_with_indices(self, client, auth_headers):
        """Store multiple facts with different blind indices."""
        facts = []
        for i in range(10):
            fact = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "encrypted_blob": f"blob_{i}" + "00" * 50,
                "blind_indices": [f"index_{i % 3}", f"common_index"],
                "decay_score": 1.0 - (i * 0.05),
                "is_active": True,
                "version": 1,
                "source": "test"
            }
            facts.append(fact)

        response = client.post(
            "/v1/store",
            json={"user_id": "test_user_123", "facts": facts},
            headers=auth_headers
        )
        assert response.status_code == 200
        return facts

    def test_search_with_trapdoors(self, client, auth_headers, stored_facts_with_indices):
        """Test search with matching trapdoors."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["index_0"],  # Should match facts 0, 3, 6, 9
                "max_candidates": 100,
                "min_decay_score": 0.0
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["results"]) >= 3  # At least facts with index_0

    def test_search_with_common_index(self, client, auth_headers, stored_facts_with_indices):
        """Test search with common index should return all facts."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["common_index"],
                "max_candidates": 100,
                "min_decay_score": 0.0
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["results"]) == 10  # All facts have common_index

    def test_search_with_decay_filter(self, client, auth_headers, stored_facts_with_indices):
        """Test search with decay score filter."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["common_index"],
                "max_candidates": 100,
                "min_decay_score": 0.8  # Only facts with decay >= 0.8
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Facts 0-4 have decay >= 0.8
        assert len(data["results"]) == 5

    def test_search_max_candidates_limit(self, client, auth_headers, stored_facts_with_indices):
        """Test search respects max_candidates limit."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["common_index"],
                "max_candidates": 3,
                "min_decay_score": 0.0
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["results"]) == 3

    def test_search_no_matching_trapdoors(self, client, auth_headers, stored_facts_with_indices):
        """Test search with non-matching trapdoors."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["nonexistent_index"],
                "max_candidates": 100,
                "min_decay_score": 0.0
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["results"]) == 0

    def test_search_empty_trapdoors(self, client, auth_headers):
        """Test search with empty trapdoors list."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": [],
                "max_candidates": 100
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "INVALID_REQUEST"

    def test_search_without_auth(self, client):
        """Test search without authentication."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["test"]
            }
        )
        assert response.status_code == 401

    def test_search_user_id_mismatch(self, client, auth_headers):
        """Test search with mismatched user ID."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "different_user",
                "trapdoors": ["test"]
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_code"] == "AUTH_FAILED"

    def test_search_result_format(self, client, auth_headers, stored_facts_with_indices):
        """Test search result contains correct fields."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["common_index"],
                "max_candidates": 1
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["results"]) > 0

        result = data["results"][0]
        assert "fact_id" in result
        assert "encrypted_blob" in result
        assert "decay_score" in result
        assert "timestamp" in result
        assert "version" in result

    def test_search_results_ordered_by_decay(self, client, auth_headers, stored_facts_with_indices):
        """Test search results are ordered by decay score (descending)."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["common_index"],
                "max_candidates": 100,
                "min_decay_score": 0.0
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Check ordering
        decay_scores = [r["decay_score"] for r in data["results"]]
        assert decay_scores == sorted(decay_scores, reverse=True)

    def test_search_multiple_trapdoors(self, client, auth_headers, stored_facts_with_indices):
        """Test search with multiple trapdoors (OR logic)."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["index_0", "index_1"],  # Should match all
                "max_candidates": 100,
                "min_decay_score": 0.0
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # With common_index, all facts should match
        assert len(data["results"]) == 10


class TestSearchEdgeCases:
    """Edge case tests for search."""

    @pytest.fixture
    def auth_headers(self, test_user):
        """Create auth headers for requests."""
        return {"Authorization": f"Bearer {test_user['auth_key'].hex()}"}

    def test_search_large_max_candidates(self, client, auth_headers):
        """Test search with very large max_candidates (should be clamped)."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["test"],
                "max_candidates": 1000000  # Should be clamped to 10000
            },
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_search_negative_max_candidates(self, client, auth_headers):
        """Test search with negative max_candidates (should be clamped to 1)."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["test"],
                "max_candidates": -1
            },
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_search_negative_decay_score(self, client, auth_headers):
        """Test search with negative min_decay_score."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test_user_123",
                "trapdoors": ["test"],
                "min_decay_score": -1.0
            },
            headers=auth_headers
        )
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
