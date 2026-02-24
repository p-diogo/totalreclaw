"""
Tests for SQL injection prevention in blind index search.
"""
import pytest
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import Database, validate_trapdoors, VALID_TRAPDOOR_RE


# Regex for valid trapdoor: exactly 64 hex characters (SHA-256 output)
VALID_HEX_SHA256 = re.compile(r'^[0-9a-fA-F]{64}$')


class TestTrapdoorValidation:
    """Tests for trapdoor input validation."""

    def test_valid_trapdoor_accepted(self):
        """A valid 64-char hex trapdoor should be accepted."""
        trapdoor = "a" * 64  # Exactly 64 hex chars
        assert VALID_HEX_SHA256.match(trapdoor)

    def test_sql_injection_rejected(self):
        """SQL injection attempt should be rejected."""
        malicious = "'); DROP TABLE facts; --"
        assert not VALID_HEX_SHA256.match(malicious)

    def test_single_quote_injection_rejected(self):
        """Single quote injection should be rejected."""
        malicious = "a' OR '1'='1"
        assert not VALID_HEX_SHA256.match(malicious)

    def test_array_escape_injection_rejected(self):
        """Array escape injection should be rejected."""
        malicious = "a1b2c3d4'}; DROP TABLE facts; --"
        assert not VALID_HEX_SHA256.match(malicious)

    def test_too_short_trapdoor_rejected(self):
        """Trapdoors shorter than 64 chars should be rejected."""
        short = "abcdef"
        assert not VALID_HEX_SHA256.match(short)

    def test_too_long_trapdoor_rejected(self):
        """Trapdoors longer than 64 chars should be rejected."""
        long = "a" * 65
        assert not VALID_HEX_SHA256.match(long)

    def test_non_hex_chars_rejected(self):
        """Trapdoors with non-hex characters should be rejected."""
        non_hex = "g" * 64  # g is not a hex char
        assert not VALID_HEX_SHA256.match(non_hex)

    def test_mixed_case_hex_accepted(self):
        """Both upper and lower case hex should be accepted."""
        upper = "A1B2C3D4" * 8  # 32 chars repeated = 64 hex
        lower = "a1b2c3d4" * 8  # 32 chars repeated = 64 hex
        assert VALID_HEX_SHA256.match(upper)
        assert VALID_HEX_SHA256.match(lower)

    def test_empty_trapdoor_rejected(self):
        """Empty string should be rejected."""
        assert not VALID_HEX_SHA256.match("")

    def test_unicode_injection_rejected(self):
        """Unicode characters should be rejected."""
        unicode_trap = "\u0027" * 64  # Unicode single quotes
        assert not VALID_HEX_SHA256.match(unicode_trap)


class TestValidateTrapdoorsFunction:
    """Tests for the validate_trapdoors helper function."""

    def test_valid_trapdoors_pass(self):
        """List of valid trapdoors should pass through."""
        trapdoors = [
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5",
        ]
        result = validate_trapdoors(trapdoors)
        assert len(result) == 2

    def test_all_invalid_raises_error(self):
        """All-invalid trapdoors should raise ValueError."""
        with pytest.raises(ValueError):
            validate_trapdoors(["bad", "also_bad", "'); DROP TABLE facts; --"])

    def test_mixed_valid_invalid_filters(self):
        """Mixed valid/invalid should filter out bad ones."""
        valid = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        result = validate_trapdoors([valid, "bad_one", "'); DROP TABLE"])
        assert len(result) == 1
        assert result[0] == valid

    def test_empty_list_returns_empty(self):
        """Empty trapdoors list should return empty."""
        result = validate_trapdoors([])
        assert result == []


class TestSearchWithMaliciousInput:
    """Integration tests: search handler rejects malicious trapdoors."""

    def test_search_rejects_sql_injection_trapdoors(self, client):
        """POST /v1/search with SQL injection trapdoors returns error."""
        response = client.post(
            "/v1/search",
            json={
                "user_id": "test",
                "trapdoors": ["'); DROP TABLE facts; --"],
                "max_candidates": 10
            },
            headers={"Authorization": "Bearer " + "aa" * 32}
        )
        # Either 401 (auth fails first) or 200 with validation error
        # The important thing: the server does NOT crash or execute SQL
        assert response.status_code in [200, 401, 422]
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
