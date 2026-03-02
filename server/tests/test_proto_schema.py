"""
Tests for v0.3.1b Protobuf schema completeness.

Validates that the .proto file contains all required v0.3.1b fields.
This is a static schema validation test -- no runtime protobuf compilation needed.
"""
import pytest
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROTO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "proto", "totalreclaw.proto"
)


def read_proto():
    """Read the .proto file content."""
    with open(PROTO_PATH, "r") as f:
        return f.read()


class TestProtoSchemaV031b:
    """Test that totalreclaw.proto has all v0.3.1b fields."""

    def test_proto_file_exists(self):
        """Proto file must exist."""
        assert os.path.exists(PROTO_PATH), f"Proto file not found at {PROTO_PATH}"

    def test_totalreclaw_fact_has_content_fp(self):
        """TotalReclawFact message must have content_fp field."""
        content = read_proto()
        assert "content_fp" in content, "TotalReclawFact missing content_fp field"

    def test_totalreclaw_fact_has_agent_id(self):
        """TotalReclawFact message must have agent_id field."""
        content = read_proto()
        assert "agent_id" in content, "TotalReclawFact missing agent_id field"

    def test_totalreclaw_fact_has_sequence_id(self):
        """TotalReclawFact message must have sequence_id field."""
        content = read_proto()
        # Check for sequence_id in any message
        assert "sequence_id" in content, "Proto missing sequence_id field"

    def test_store_response_has_duplicate_ids(self):
        """StoreResponse must have duplicate_ids field."""
        content = read_proto()
        assert "duplicate_ids" in content, "StoreResponse missing duplicate_ids field"

    def test_error_code_has_duplicate_content(self):
        """ErrorCode enum must have DUPLICATE_CONTENT value."""
        content = read_proto()
        assert "DUPLICATE_CONTENT" in content, "ErrorCode missing DUPLICATE_CONTENT"

    def test_sync_request_message_exists(self):
        """SyncRequest message must exist."""
        content = read_proto()
        assert re.search(r'message\s+SyncRequest\s*\{', content), (
            "Missing SyncRequest message"
        )

    def test_sync_response_message_exists(self):
        """SyncResponse message must exist."""
        content = read_proto()
        assert re.search(r'message\s+SyncResponse\s*\{', content), (
            "Missing SyncResponse message"
        )

    def test_sync_response_has_latest_sequence(self):
        """SyncResponse must have latest_sequence field."""
        content = read_proto()
        assert "latest_sequence" in content, "SyncResponse missing latest_sequence"

    def test_sync_response_has_has_more(self):
        """SyncResponse must have has_more field."""
        content = read_proto()
        assert "has_more" in content, "SyncResponse missing has_more"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
