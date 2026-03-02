"""
Prometheus metrics for TotalReclaw Server.

Exposes request counts, latency histograms, error counts,
and database pool metrics.
"""
import time
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    REGISTRY
)
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ============ Metrics ============

# Request metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

HTTP_ERRORS_TOTAL = Counter(
    "http_errors_total",
    "Total HTTP errors (4xx and 5xx)",
    ["method", "endpoint", "status_code"]
)

# Rate limiting metrics
RATE_LIMIT_HITS_TOTAL = Counter(
    "rate_limit_hits_total",
    "Total rate limit hits (429 responses)",
    ["path", "limit_type"]
)

# Database pool metrics
DB_POOL_SIZE = Gauge(
    "db_pool_size",
    "Current database connection pool size"
)

DB_POOL_CHECKED_IN = Gauge(
    "db_pool_checked_in",
    "Number of connections currently checked in (available)"
)

DB_POOL_CHECKED_OUT = Gauge(
    "db_pool_checked_out",
    "Number of connections currently checked out (in use)"
)

DB_POOL_OVERFLOW = Gauge(
    "db_pool_overflow",
    "Current number of overflow connections"
)


def get_metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    metrics_output = generate_latest(REGISTRY)
    return Response(
        content=metrics_output,
        media_type=CONTENT_TYPE_LATEST
    )


def record_request(method: str, endpoint: str, status_code: int, duration: float):
    """Record metrics for a completed request."""
    # Normalize endpoint (strip path parameters)
    normalized = normalize_endpoint(endpoint)

    HTTP_REQUESTS_TOTAL.labels(
        method=method,
        endpoint=normalized,
        status_code=str(status_code)
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method,
        endpoint=normalized
    ).observe(duration)

    if status_code >= 400:
        HTTP_ERRORS_TOTAL.labels(
            method=method,
            endpoint=normalized,
            status_code=str(status_code)
        ).inc()


def normalize_endpoint(path: str) -> str:
    """
    Normalize endpoint path for metrics labels.

    Replaces dynamic path segments (UUIDs, IDs) with placeholders
    to prevent label cardinality explosion.
    """
    parts = path.strip("/").split("/")
    normalized = []
    for part in parts:
        # Replace UUID-like segments
        if len(part) == 36 and part.count("-") == 4:
            normalized.append("{id}")
        elif len(part) > 20 and all(c in "0123456789abcdef-" for c in part):
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized) if normalized else "/"


def update_db_pool_metrics(engine):
    """Update database pool metrics from SQLAlchemy engine."""
    try:
        pool = engine.pool
        DB_POOL_SIZE.set(pool.size())
        DB_POOL_CHECKED_IN.set(pool.checkedin())
        DB_POOL_CHECKED_OUT.set(pool.checkedout())
        DB_POOL_OVERFLOW.set(pool.overflow())
    except Exception:
        pass  # Pool metrics are best-effort
