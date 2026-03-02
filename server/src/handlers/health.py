"""
Health check endpoint for TotalReclaw Server.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import get_settings
from ..db import get_db, Database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Database = Depends(get_db)):
    """
    Health check endpoint.

    Returns server status and database connectivity.
    Used by Docker health checks and load balancers.
    """
    settings = get_settings()
    db_health = await db.health_check()

    return HealthResponse(
        status="healthy" if db_health["status"] == "connected" else "degraded",
        version=settings.api_version,
        database=db_health["status"]
    )


@router.get("/ready")
async def readiness_check(db: Database = Depends(get_db)):
    """
    Readiness check for Kubernetes/container orchestration.

    Returns 200 only if database is connected.
    """
    db_health = await db.health_check()
    if db_health["status"] == "connected":
        return {"ready": True}
    return {"ready": False, "reason": db_health.get("message", "Database not connected")}
