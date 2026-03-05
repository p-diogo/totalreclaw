"""
Transparent proxy endpoints for TotalReclaw Server.

Allows clients (MCP server, OpenClaw plugin) to talk to Pimlico and
Graph Studio without holding any third-party API keys. The relay server
appends the credentials and forwards requests as-is.

Endpoints:
    POST /v1/bundler   -- JSON-RPC proxy to Pimlico bundler
    POST /v1/subgraph  -- GraphQL proxy to Graph Studio subgraph

Both endpoints require wallet-based auth (Authorization: Bearer <auth_key>)
and enforce per-user monthly usage limits based on subscription tier.
Usage tracking is persistent (PostgreSQL-backed via the subscriptions table).

Write operations (eth_sendUserOperation) are rate-limited more strictly
than read-like RPC calls (gas estimation, receipt polling).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from ..billing.stripe_service import StripeService
from ..config import get_settings
from ..db import get_db, Database
from ..dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxy"])


# ---------------------------------------------------------------------------
# JSON-RPC methods that count as "write" operations
# ---------------------------------------------------------------------------

_WRITE_RPC_METHODS = frozenset({
    "eth_sendUserOperation",
})


# ---------------------------------------------------------------------------
# Testing helper (no-op — kept for backward compatibility with test code
# that may import it; DB-backed tracking needs no in-memory reset).
# ---------------------------------------------------------------------------

def _reset_usage_tracker() -> None:
    """No-op. Retained for backward compatibility with test imports.

    DB-backed usage tracking does not require an in-memory reset.
    """
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _check_write_quota(
    wallet_address: Optional[str],
    user_id: str,
    db: Database,
) -> Optional[JSONResponse]:
    """
    Check if the user has remaining write quota (DB-backed).

    Uses StripeService.check_and_increment_free_usage() which handles:
    - Monthly reset (checks free_writes_reset_at vs current month start)
    - Atomic increment (SELECT FOR UPDATE + UPDATE)
    - Pro tier bypass
    - Returns True/False

    If no wallet_address is provided, falls back to allowing the request
    (user-id-only clients cannot be quota-tracked via the subscriptions
    table which is keyed by wallet_address).

    Returns None if allowed, or a 403 JSONResponse if quota exceeded.
    """
    if not wallet_address:
        # Without a wallet address we cannot look up the subscription.
        # Allow the request — the relay is still auth-gated.
        return None

    try:
        svc = StripeService(db)
        allowed = await svc.check_and_increment_free_usage(wallet_address)
        if not allowed:
            settings = get_settings()
            return JSONResponse(
                status_code=403,
                content={
                    "error": "quota_exceeded",
                    "message": (
                        f"Write limit reached for this month. "
                        f"Upgrade for higher limits."
                    ),
                    "upgrade_url": "https://totalreclaw.xyz/pricing",
                },
            )
        return None
    except Exception as exc:
        # On DB errors, log and allow the request (fail-open for proxy).
        logger.warning(
            "Failed to check write quota for user %s (wallet %s): %s",
            user_id, wallet_address, exc,
        )
        return None


async def _check_read_quota(
    wallet_address: Optional[str],
    user_id: str,
    db: Database,
) -> Optional[JSONResponse]:
    """
    Check if the user has remaining read quota (DB-backed).

    Uses StripeService.check_and_increment_free_read_usage() which handles:
    - Monthly reset (checks free_reads_reset_at vs current month start)
    - Atomic increment (SELECT FOR UPDATE + UPDATE)
    - Pro/free tier limit selection
    - Returns True/False

    If no wallet_address is provided, falls back to allowing the request.

    Returns None if allowed, or a 403 JSONResponse if quota exceeded.
    """
    if not wallet_address:
        # Without a wallet address we cannot look up the subscription.
        # Allow the request — the relay is still auth-gated.
        return None

    try:
        svc = StripeService(db)
        allowed = await svc.check_and_increment_free_read_usage(wallet_address)
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "quota_exceeded",
                    "message": (
                        f"Read limit reached for this month. "
                        f"Upgrade for higher limits."
                    ),
                    "upgrade_url": "https://totalreclaw.xyz/pricing",
                },
            )
        return None
    except Exception as exc:
        # On DB errors, log and allow the request (fail-open for proxy).
        logger.warning(
            "Failed to check read quota for user %s (wallet %s): %s",
            user_id, wallet_address, exc,
        )
        return None


# ---------------------------------------------------------------------------
# POST /v1/bundler — JSON-RPC proxy to Pimlico
# ---------------------------------------------------------------------------

@router.post("/bundler")
async def proxy_bundler(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: Database = Depends(get_db),
    x_wallet_address: Optional[str] = Header(None),
):
    """
    Transparent JSON-RPC proxy to the Pimlico bundler.

    Receives ERC-4337 JSON-RPC requests from the permissionless SDK and
    forwards them to Pimlico with the server's API key appended.

    Write operations (eth_sendUserOperation) are subject to monthly
    write quotas based on the user's subscription tier. Read-like
    operations (gas estimation, receipt polling, etc.) are allowed freely.

    The request body is forwarded as-is without parsing or modification.
    The response from Pimlico is returned as-is.

    Optional headers:
        X-Wallet-Address: The user's Smart Account address, used to look
                          up subscription tier for quota enforcement.
    """
    settings = get_settings()

    if not settings.pimlico_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bundler proxy not configured (missing PIMLICO_API_KEY)",
        )

    # Read the raw request body
    try:
        body = await request.body()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read request body: {exc}",
        )

    # Peek at the JSON-RPC method to determine if this is a write operation.
    # We parse minimally — only to extract the "method" field.
    is_write = False
    try:
        payload = json.loads(body)
        rpc_method = payload.get("method", "")
        is_write = rpc_method in _WRITE_RPC_METHODS
    except (json.JSONDecodeError, AttributeError, TypeError):
        # If we can't parse the body, forward it anyway and let Pimlico
        # handle the error. We don't quota-gate unparseable requests.
        pass

    # Check + increment write quota BEFORE forwarding (atomic DB check).
    # The StripeService method increments the counter as part of the check,
    # so we do NOT need a separate "record" step after forwarding.
    if is_write:
        quota_error = await _check_write_quota(x_wallet_address, user_id, db)
        if quota_error is not None:
            return quota_error

    # Build the target URL with API key
    target_url = settings.pimlico_rpc_url  # Already includes ?apikey=...

    # Forward the request
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                target_url,
                content=body,
                headers={"Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        logger.error("Pimlico bundler proxy timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Pimlico bundler request timed out",
        )
    except httpx.HTTPError as exc:
        logger.error("Pimlico bundler proxy connection error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Pimlico bundler",
        )

    # Return Pimlico's response as-is
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


# ---------------------------------------------------------------------------
# POST /v1/subgraph — GraphQL proxy to Graph Studio
# ---------------------------------------------------------------------------

@router.post("/subgraph")
async def proxy_subgraph(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: Database = Depends(get_db),
    x_wallet_address: Optional[str] = Header(None),
):
    """
    Transparent GraphQL proxy to the Graph Studio subgraph endpoint.

    Receives GraphQL queries from clients and forwards them to the
    configured subgraph endpoint. The server holds the subgraph URL
    (which may include an API key for Graph Studio hosted service).

    Read operations are subject to monthly read quotas based on the
    user's subscription tier.

    The request body is forwarded as-is without parsing or modification.
    The response from Graph Studio is returned as-is.

    Optional headers:
        X-Wallet-Address: The user's Smart Account address, used to look
                          up subscription tier for quota enforcement.
    """
    settings = get_settings()

    if not settings.subgraph_endpoint:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subgraph proxy not configured (missing SUBGRAPH_ENDPOINT)",
        )

    # Read the raw request body
    try:
        body = await request.body()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read request body: {exc}",
        )

    # Check + increment read quota BEFORE forwarding (atomic DB check).
    quota_error = await _check_read_quota(x_wallet_address, user_id, db)
    if quota_error is not None:
        return quota_error

    # Forward the request
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                settings.subgraph_endpoint,
                content=body,
                headers={"Content-Type": "application/json"},
            )
    except httpx.TimeoutException:
        logger.error("Subgraph proxy timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Subgraph endpoint request timed out",
        )
    except httpx.HTTPError as exc:
        logger.error("Subgraph proxy connection error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to subgraph endpoint",
        )

    # Return the subgraph response as-is
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )
