"""
Tests for v0.3.1b schema migration: content_fp, sequence_id, agent_id columns.
"""
import pytest
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.models import Fact, Base


class TestSchemaV031b:
    """Test that the Fact model has v0.3.1b columns."""

    def test_fact_model_has_content_fp_column(self):
        """Fact model must have content_fp column (TEXT, nullable)."""
        columns = {c.name: c for c in Fact.__table__.columns}
        assert "content_fp" in columns, "Fact model missing content_fp column"
        assert columns["content_fp"].nullable is True

    def test_fact_model_has_sequence_id_column(self):
        """Fact model must have sequence_id column (BIGINT, auto-increment)."""
        columns = {c.name: c for c in Fact.__table__.columns}
        assert "sequence_id" in columns, "Fact model missing sequence_id column"

    def test_fact_model_has_agent_id_column(self):
        """Fact model must have agent_id column (TEXT, nullable)."""
        columns = {c.name: c for c in Fact.__table__.columns}
        assert "agent_id" in columns, "Fact model missing agent_id column"
        assert columns["agent_id"].nullable is True

    def test_fact_model_unique_index_user_fp(self):
        """Fact model must have unique index on (user_id, content_fp) WHERE is_active=true."""
        indexes = {idx.name: idx for idx in Fact.__table__.indexes}
        assert "idx_facts_user_fp" in indexes, (
            "Missing unique index idx_facts_user_fp on facts(user_id, content_fp)"
        )
        idx = indexes["idx_facts_user_fp"]
        assert idx.unique is True
        # Check the index covers user_id and content_fp
        col_names = [c.name for c in idx.columns]
        assert "user_id" in col_names
        assert "content_fp" in col_names

    def test_fact_model_index_user_seq(self):
        """Fact model must have index on (user_id, sequence_id)."""
        indexes = {idx.name: idx for idx in Fact.__table__.indexes}
        assert "idx_facts_user_seq" in indexes, (
            "Missing index idx_facts_user_seq on facts(user_id, sequence_id)"
        )
        idx = indexes["idx_facts_user_seq"]
        col_names = [c.name for c in idx.columns]
        assert "user_id" in col_names
        assert "sequence_id" in col_names

    def test_fact_can_be_instantiated_with_new_fields(self):
        """Fact model accepts content_fp, agent_id at construction."""
        fact = Fact(
            id="test-id",
            user_id="user-1",
            encrypted_blob=b"encrypted",
            blind_indices=["idx1", "idx2"],
            decay_score=1.0,
            source="test",
            content_fp="abcdef1234567890",
            agent_id="agent-abc123"
        )
        assert fact.content_fp == "abcdef1234567890"
        assert fact.agent_id == "agent-abc123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
