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

Write operations (eth_sendUserOperation) are rate-limited more strictly
than read-like RPC calls (gas estimation, receipt polling).
"""
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

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
# Monthly usage tracker (in-memory, resets on server restart)
#
# In production, this should be backed by a database counter (like the
# subscriptions.free_writes_used column). For the proxy PoC, in-memory
# tracking is acceptable — it's conservative (resets to 0 on restart,
# giving the user a fresh allowance).
# ---------------------------------------------------------------------------

class _MonthlyUsageTracker:
    """
    Per-user monthly usage counter.

    Tracks how many write and read proxy operations each user has performed
    in the current calendar month. Automatically resets when a new month
    starts.
    """

    def __init__(self):
        self._writes: Dict[str, List[float]] = defaultdict(list)
        self._reads: Dict[str, List[float]] = defaultdict(list)
        self._current_month: Optional[str] = None

    def _maybe_reset(self) -> None:
        """Reset all counters if the calendar month has changed."""
        now = datetime.now(timezone.utc)
        month_key = f"{now.year}-{now.month:02d}"
        if self._current_month != month_key:
            self._writes.clear()
            self._reads.clear()
            self._current_month = month_key

    def record_write(self, user_id: str) -> None:
        self._maybe_reset()
        self._writes[user_id].append(time.time())

    def record_read(self, user_id: str) -> None:
        self._maybe_reset()
        self._reads[user_id].append(time.time())

    def get_write_count(self, user_id: str) -> int:
        self._maybe_reset()
        return len(self._writes.get(user_id, []))

    def get_read_count(self, user_id: str) -> int:
        self._maybe_reset()
        return len(self._reads.get(user_id, []))


_usage = _MonthlyUsageTracker()


def _reset_usage_tracker() -> None:
    """Reset usage tracker (for testing)."""
    global _usage
    _usage = _MonthlyUsageTracker()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_tier(
    user_id: str,
    db: Database,
    wallet_address: Optional[str] = None,
) -> str:
    """
    Determine the user's subscription tier.

    The subscriptions table is keyed by wallet_address (not user_id).
    The client can provide a wallet_address via the X-Wallet-Address
    header to allow the server to look up the subscription.

    If no wallet_address is provided or the lookup fails, defaults to
    the free tier.

    Args:
        user_id: The authenticated user's ID (for logging).
        db: Database instance.
        wallet_address: Optional wallet address for subscription lookup.

    Returns:
        "pro" or "free"
    """
    if not wallet_address:
        return "free"

    from sqlalchemy import text as sa_text

    try:
        async with db.session() as session:
            result = await session.execute(
                sa_text("""
                    SELECT tier, expires_at
                    FROM subscriptions
                    WHERE wallet_address = :addr
                """),
                {"addr": wallet_address.lower()},
            )
            row = result.fetchone()

            if row is None:
                return "free"

            # Check expiration for pro tier
            if row.tier == "pro":
                if row.expires_at and row.expires_at < datetime.now(timezone.utc):
                    return "free"
                return "pro"

            return "free"

    except Exception as exc:
        # On DB errors, default to free tier (conservative)
        logger.warning(
            "Failed to check subscription tier for user %s (wallet %s): %s",
            user_id, wallet_address, exc,
        )
        return "free"


def _check_write_quota(user_id: str, tier: str) -> Optional[JSONResponse]:
    """
    Check if the user has remaining write quota.

    Returns None if allowed, or a 403 JSONResponse if quota exceeded.
    """
    settings = get_settings()

    if tier == "pro":
        limit = settings.pro_tier_writes_per_month
    else:
        limit = settings.free_tier_writes_per_month

    count = _usage.get_write_count(user_id)

    if count >= limit:
        return JSONResponse(
            status_code=403,
            content={
                "error": "quota_exceeded",
                "message": (
                    f"{'Free' if tier == 'free' else 'Pro'} tier write limit "
                    f"reached ({count}/{limit} this month)"
                ),
                "upgrade_url": "https://totalreclaw.com/pricing",
            },
        )
    return None


def _check_read_quota(user_id: str, tier: str) -> Optional[JSONResponse]:
    """
    Check if the user has remaining read quota.

    Returns None if allowed, or a 403 JSONResponse if quota exceeded.
    """
    settings = get_settings()

    if tier == "pro":
        limit = settings.pro_tier_reads_per_month
    else:
        limit = settings.free_tier_reads_per_month

    count = _usage.get_read_count(user_id)

    if count >= limit:
        return JSONResponse(
            status_code=403,
            content={
                "error": "quota_exceeded",
                "message": (
                    f"{'Free' if tier == 'free' else 'Pro'} tier read limit "
                    f"reached ({count}/{limit} this month)"
                ),
                "upgrade_url": "https://totalreclaw.com/pricing",
            },
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

    # Only check billing for write operations
    if is_write:
        tier = await _get_user_tier(user_id, db, x_wallet_address)
        quota_error = _check_write_quota(user_id, tier)
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

    # Record usage after successful forwarding (for write operations)
    if is_write:
        _usage.record_write(user_id)

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

    # Check read quota
    tier = await _get_user_tier(user_id, db, x_wallet_address)
    quota_error = _check_read_quota(user_id, tier)
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

    # Record usage after successful forwarding
    _usage.record_read(user_id)

    # Return the subgraph response as-is
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )
