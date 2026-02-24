"""
Per-user rate limiting middleware for OpenMemory Server.

Design:
- In-memory sliding window counter
- Authenticated endpoints: keyed on auth_hash from Authorization header
- Unauthenticated endpoints (/v1/register): keyed on client IP
- Skipped for /health, /metrics, /docs, /redoc, /openapi.json
- Returns 429 with JSON body and Retry-After header

Does NOT touch relay.py rate limiting (that uses its own per-address limiter).
"""
import time
import logging
from collections import deque
from typing import Dict, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..config import get_settings
from ..metrics import RATE_LIMIT_HITS_TOTAL

logger = logging.getLogger(__name__)

# Counter for periodic cleanup
_request_counter = 0
_CLEANUP_INTERVAL = 100


class SlidingWindowCounter:
    """In-memory sliding window rate limiter using deques of timestamps."""

    def __init__(self):
        self._windows: Dict[str, deque] = {}

    def check_and_record(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if the key is within rate limits and record the request.

        Returns:
            (allowed, retry_after_seconds)
            - allowed: True if request is allowed
            - retry_after_seconds: seconds until the oldest entry expires (0 if allowed)
        """
        now = time.time()
        cutoff = now - window_seconds

        if key not in self._windows:
            self._windows[key] = deque()

        window = self._windows[key]

        # Prune expired entries
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= max_requests:
            # Calculate retry_after: time until the oldest entry in the window expires
            oldest = window[0]
            retry_after = int(oldest + window_seconds - now) + 1
            return False, max(retry_after, 1)

        window.append(now)
        return True, 0

    def cleanup_expired(self, window_seconds: int) -> int:
        """
        Remove keys whose windows are entirely expired.

        Returns the number of keys removed.
        """
        now = time.time()
        cutoff = now - window_seconds
        expired_keys = []

        for key, window in self._windows.items():
            # Prune expired entries
            while window and window[0] <= cutoff:
                window.popleft()
            if not window:
                expired_keys.append(key)

        for key in expired_keys:
            del self._windows[key]

        return len(expired_keys)

    def get_count(self, key: str, window_seconds: int) -> int:
        """Return the current request count for a key within the window."""
        now = time.time()
        cutoff = now - window_seconds

        if key not in self._windows:
            return 0

        window = self._windows[key]
        while window and window[0] <= cutoff:
            window.popleft()

        return len(window)

    def reset(self):
        """Clear all entries (for testing)."""
        self._windows.clear()


# Module-level singleton
_counter = SlidingWindowCounter()


def get_counter() -> SlidingWindowCounter:
    """Get the shared rate limit counter instance."""
    return _counter


def reset_counter() -> None:
    """Reset the rate limit counter (for testing)."""
    _counter.reset()


# Route configuration: path prefix -> (max_requests, window_seconds)
# These are the defaults; actual values come from Settings.
_SKIP_PATHS = frozenset({
    "/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json", "/"
})

_IP_BASED_PATHS = frozenset({
    "/v1/register"
})


def _get_client_ip(request: Request) -> str:
    """Extract client IP, only trusting X-Forwarded-For from configured trusted proxies.

    If the direct client IP (request.client.host) is in the trusted_proxies list,
    we use the first IP from X-Forwarded-For. Otherwise, we use the direct IP
    to prevent X-Forwarded-For spoofing.
    """
    direct_ip = request.client.host if request.client else "unknown"

    settings = get_settings()
    trusted = settings.trusted_proxy_list

    if trusted and direct_ip in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return direct_ip


def _get_auth_hash(request: Request) -> Optional[str]:
    """Extract the raw auth token from the Authorization header for rate-limit keying.

    We do NOT do a DB lookup here -- we just use the bearer token value as the key.
    This is fast and sufficient for rate limiting purposes.
    """
    auth = request.headers.get("authorization", "")
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _get_route_limits(path: str) -> Optional[Tuple[int, int]]:
    """
    Return (max_requests, window_seconds) for the given path.

    Returns None if the path should not be rate-limited.
    """
    settings = get_settings()

    if path in _SKIP_PATHS:
        return None

    # Match route prefixes (all API routes are under /v1/)
    if path == "/v1/register":
        return (settings.rate_limit_register_per_hour, 3600)
    elif path == "/v1/store":
        return (settings.rate_limit_store_per_hour, 3600)
    elif path == "/v1/search":
        return (settings.rate_limit_search_per_hour, 3600)
    elif path == "/v1/sync":
        return (settings.rate_limit_sync_per_hour, 3600)
    elif path == "/v1/account":
        return (settings.rate_limit_account_per_hour, 3600)
    elif path.startswith("/v1/facts/"):
        # DELETE /v1/facts/{id} uses same limit as store
        return (settings.rate_limit_store_per_hour, 3600)
    elif path == "/v1/export":
        return (settings.rate_limit_search_per_hour, 3600)
    elif path == "/v1/relay":
        # Relay has its own rate limiter in relay.py -- skip middleware
        return None

    # Default: no rate limiting for unknown paths
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for per-user rate limiting."""

    async def dispatch(self, request: Request, call_next):
        global _request_counter

        path = request.url.path
        method = request.method

        # Skip non-mutating checks for OPTIONS (CORS preflight)
        if method == "OPTIONS":
            return await call_next(request)

        limits = _get_route_limits(path)
        if limits is None:
            return await call_next(request)

        max_requests, window_seconds = limits
        counter = get_counter()

        # Determine the rate-limit key
        if path in _IP_BASED_PATHS:
            key = f"ip:{_get_client_ip(request)}:{path}"
        else:
            auth_hash = _get_auth_hash(request)
            if auth_hash:
                key = f"user:{auth_hash}:{path}"
            else:
                # No auth header -- use IP (will likely fail auth later anyway)
                key = f"ip:{_get_client_ip(request)}:{path}"

        allowed, retry_after = counter.check_and_record(key, max_requests, window_seconds)

        if not allowed:
            # Determine limit type for metrics
            limit_type = "ip" if key.startswith("ip:") else "user"

            # Truncate the key for privacy: show only the type prefix and
            # first 8 characters of the identifier (enough for debugging,
            # not enough to reconstruct a full auth token).
            key_parts = key.split(":")
            if len(key_parts) >= 2:
                identifier = key_parts[1]
                key_prefix = f"{key_parts[0]}:{identifier[:8]}..."
            else:
                key_prefix = key[:12] + "..."

            current_count = counter.get_count(key, window_seconds)

            logger.warning(
                "Rate limited",
                extra={
                    "path": path,
                    "key_prefix": key_prefix,
                    "count": current_count,
                    "limit": max_requests,
                    "limit_type": limit_type,
                    "retry_after": retry_after,
                }
            )

            # Increment Prometheus counter
            RATE_LIMIT_HITS_TOTAL.labels(
                path=path,
                limit_type=limit_type
            ).inc()

            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Periodic cleanup of expired entries
        _request_counter += 1
        if _request_counter % _CLEANUP_INTERVAL == 0:
            removed = counter.cleanup_expired(window_seconds=3600)
            if removed > 0:
                logger.debug(f"Rate limiter cleanup: removed {removed} expired keys")

        return await call_next(request)
