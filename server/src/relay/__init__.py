"""
Relay module for TotalReclaw Server.

Provides the Pimlico paymaster integration for gas-sponsored ERC-4337
UserOperations on Gnosis Chain. The relay module is independent from the
billing module but imports billing services to check subscription status.

Components:
    PaymasterService  — Core JSON-RPC integration with Pimlico bundler/paymaster.
    WebhookHandler    — Verifies and processes Pimlico sponsorship policy webhooks.
    relay_router      — FastAPI routes for /v1/relay/* endpoints.
    proxy_router      — Transparent proxy endpoints for /v1/bundler and /v1/subgraph.
"""
from .paymaster_service import PaymasterService
from .webhook_handler import WebhookHandler, verify_pimlico_signature
from .routes import router as relay_api_router
from .proxy import router as proxy_router

__all__ = [
    "PaymasterService",
    "WebhookHandler",
    "verify_pimlico_signature",
    "relay_api_router",
    "proxy_router",
]
