"""
Tests for the /relay endpoint.

These tests verify the UserOperation relay functionality without
requiring a database or real Pimlico bundler connection.
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.handlers.relay import (
    RateLimiter,
    RelayRequest,
    RelayResponse,
    UserOperationPayload,
    reset_rate_limiter,
)


# --- Rate Limiter Tests ---

class TestRateLimiter:
    """Tests for the in-memory rate limiter."""

    def test_allows_first_request(self):
        limiter = RateLimiter(max_ops=10, window_seconds=3600)
        assert limiter.check("0x1234") is True

    def test_counts_requests(self):
        limiter = RateLimiter(max_ops=10, window_seconds=3600)
        limiter.check("0x1234")
        limiter.check("0x1234")
        limiter.check("0x1234")
        assert limiter.get_count("0x1234") == 3

    def test_blocks_after_limit(self):
        limiter = RateLimiter(max_ops=3, window_seconds=3600)
        assert limiter.check("0x1234") is True
        assert limiter.check("0x1234") is True
        assert limiter.check("0x1234") is True
        assert limiter.check("0x1234") is False  # 4th should fail

    def test_different_senders_independent(self):
        limiter = RateLimiter(max_ops=2, window_seconds=3600)
        assert limiter.check("0xaaaa") is True
        assert limiter.check("0xaaaa") is True
        assert limiter.check("0xaaaa") is False
        # Different sender should still work
        assert limiter.check("0xbbbb") is True

    def test_case_insensitive(self):
        limiter = RateLimiter(max_ops=10, window_seconds=3600)
        limiter.check("0xABCD")
        assert limiter.get_count("0xabcd") == 1

    def test_initial_count_is_zero(self):
        limiter = RateLimiter(max_ops=10, window_seconds=3600)
        assert limiter.get_count("0xnew") == 0


# --- Request Validation Tests ---

class TestRelayRequestValidation:
    """Tests for the Pydantic request/response models."""

    def test_valid_request(self):
        req = RelayRequest(
            userOperation=UserOperationPayload(
                sender="0x" + "11" * 20,
                nonce="0x0",
                callData="0x" + "ff" * 128,
                signature="0x" + "aa" * 65,
            ),
            target="0x" + "ab" * 20,
        )
        assert req.target == "0x" + "ab" * 20
        assert req.userOperation.sender == "0x" + "11" * 20

    def test_defaults_for_optional_fields(self):
        req = RelayRequest(
            userOperation=UserOperationPayload(
                sender="0x" + "11" * 20,
                nonce="0x0",
                callData="0x" + "ff" * 10,
                signature="0x" + "aa" * 65,
            ),
            target="0x" + "ab" * 20,
        )
        assert req.userOperation.initCode == "0x"
        assert req.userOperation.callGasLimit == "0x50000"
        assert req.userOperation.paymasterAndData == "0x"

    def test_response_model_success(self):
        resp = RelayResponse(
            success=True,
            userOpHash="0x" + "cc" * 32,
        )
        assert resp.success is True
        assert resp.transactionHash is None

    def test_response_model_error(self):
        resp = RelayResponse(
            success=False,
            error_message="Rate limited",
        )
        assert resp.success is False
        assert resp.error_message == "Rate limited"


# --- Endpoint Integration Tests (using TestClient) ---

class TestRelayEndpoint:
    """
    Tests for POST /relay endpoint.

    These use FastAPI's TestClient to exercise the full endpoint,
    with mocked settings and bundler.
    """

    @pytest.fixture(autouse=True)
    def reset_limiter(self):
        """Reset the rate limiter before each test."""
        reset_rate_limiter()
        yield
        reset_rate_limiter()

    @pytest.fixture
    def edge_address(self):
        return "0x" + "ab" * 20

    @pytest.fixture
    def valid_payload(self, edge_address):
        return {
            "userOperation": {
                "sender": "0x" + "11" * 20,
                "nonce": "0x0",
                "initCode": "0x",
                "callData": "0x" + "ff" * 128,
                "callGasLimit": "0x50000",
                "verificationGasLimit": "0x60000",
                "preVerificationGas": "0x10000",
                "maxFeePerGas": "0x0",
                "maxPriorityFeePerGas": "0x0",
                "paymasterAndData": "0x",
                "signature": "0x" + "aa" * 65,
            },
            "target": edge_address,
        }

    @pytest.fixture
    def mock_settings(self, edge_address):
        """Patch settings for relay testing."""
        from src.config import Settings

        mock = MagicMock(spec=Settings)
        mock.pimlico_api_key = "test-api-key"
        mock.pimlico_bundler_url = "https://api.pimlico.io/v2/84532/rpc"
        mock.data_edge_address = edge_address
        mock.entry_point_address = "0x0000000071727De22E5E9d8BAf0edAc6f37da032"
        mock.relay_rate_limit_ops = 100
        mock.relay_rate_limit_window_seconds = 3600
        # Also need standard settings for other middleware
        mock.debug = True
        mock.environment = "development"
        mock.is_development = True
        mock.is_production = False
        mock.api_version = "0.3.1"
        mock.cors_origin_list = ["http://localhost:3000"]
        mock.cors_origins = "http://localhost:3000"
        mock.database_url = "sqlite+aiosqlite:///test.db"
        mock.host = "127.0.0.1"
        mock.port = 8080
        mock.rate_limit_register_per_hour = 10
        mock.rate_limit_store_per_hour = 1000
        mock.rate_limit_search_per_hour = 1000
        mock.rate_limit_sync_per_hour = 1000
        mock.rate_limit_account_per_hour = 10
        mock.database_pool_size = 5
        mock.database_max_overflow = 10
        mock.database_pool_recycle = 3600
        mock.database_pool_pre_ping = True
        mock.database_pool_timeout = 30
        return mock

    def test_relay_rejects_wrong_target(self, mock_settings, valid_payload):
        """Should return 403 if target is not the DataEdge contract."""
        from fastapi.testclient import TestClient

        valid_payload["target"] = "0x" + "00" * 20  # Wrong target

        with patch("src.handlers.relay.get_settings", return_value=mock_settings):
            from src.handlers.relay import relay_router
            from fastapi import FastAPI

            test_app = FastAPI()
            test_app.include_router(relay_router)

            with TestClient(test_app) as client:
                response = client.post("/relay", json=valid_payload)
                assert response.status_code == 403

    def test_relay_rejects_empty_calldata(self, mock_settings, valid_payload):
        """Should reject operations with empty calldata."""
        from fastapi.testclient import TestClient

        valid_payload["userOperation"]["callData"] = "0x"

        with patch("src.handlers.relay.get_settings", return_value=mock_settings):
            from src.handlers.relay import relay_router
            from fastapi import FastAPI

            test_app = FastAPI()
            test_app.include_router(relay_router)

            with TestClient(test_app) as client:
                response = client.post("/relay", json=valid_payload)
                assert response.status_code == 400

    def test_relay_enforces_rate_limit(self, mock_settings, valid_payload):
        """Should return 429 after rate limit exceeded."""
        from fastapi.testclient import TestClient

        mock_settings.relay_rate_limit_ops = 2

        with patch("src.handlers.relay.get_settings", return_value=mock_settings):
            from src.handlers.relay import relay_router, reset_rate_limiter
            from fastapi import FastAPI

            reset_rate_limiter()

            test_app = FastAPI()
            test_app.include_router(relay_router)

            # Mock the bundler call so it doesn't actually try to connect
            with patch("src.handlers.relay.submit_to_bundler", new_callable=AsyncMock) as mock_bundler:
                mock_bundler.return_value = {"result": "0x" + "cc" * 32}

                with TestClient(test_app) as client:
                    # First 2 should succeed
                    r1 = client.post("/relay", json=valid_payload)
                    assert r1.status_code == 200, f"First request failed: {r1.json()}"
                    r2 = client.post("/relay", json=valid_payload)
                    assert r2.status_code == 200, f"Second request failed: {r2.json()}"
                    # 3rd should be rate limited
                    r3 = client.post("/relay", json=valid_payload)
                    assert r3.status_code == 429

    def test_relay_returns_success_on_valid_op(self, mock_settings, valid_payload):
        """Should relay successfully when bundler mock returns hash."""
        from fastapi.testclient import TestClient

        expected_hash = "0x" + "dd" * 32

        with patch("src.handlers.relay.get_settings", return_value=mock_settings):
            with patch("src.handlers.relay.submit_to_bundler", new_callable=AsyncMock) as mock_bundler:
                mock_bundler.return_value = {"result": expected_hash}

                from src.handlers.relay import relay_router
                from fastapi import FastAPI

                test_app = FastAPI()
                test_app.include_router(relay_router)

                with TestClient(test_app) as client:
                    response = client.post("/relay", json=valid_payload)
                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert data["userOpHash"] == expected_hash

    def test_relay_rejects_missing_data_edge_config(self, mock_settings, valid_payload):
        """Should return 503 if data_edge_address is not configured."""
        from fastapi.testclient import TestClient

        mock_settings.data_edge_address = ""

        with patch("src.handlers.relay.get_settings", return_value=mock_settings):
            from src.handlers.relay import relay_router
            from fastapi import FastAPI

            test_app = FastAPI()
            test_app.include_router(relay_router)

            with TestClient(test_app) as client:
                response = client.post("/relay", json=valid_payload)
                assert response.status_code == 503

    def test_relay_rejects_missing_bundler_config(self, mock_settings, valid_payload):
        """Should return 503 if pimlico_api_key is not configured."""
        from fastapi.testclient import TestClient

        mock_settings.pimlico_api_key = ""

        with patch("src.handlers.relay.get_settings", return_value=mock_settings):
            from src.handlers.relay import relay_router
            from fastapi import FastAPI

            test_app = FastAPI()
            test_app.include_router(relay_router)

            with TestClient(test_app) as client:
                response = client.post("/relay", json=valid_payload)
                # Should fail at bundler submission with 503
                assert response.status_code == 503
