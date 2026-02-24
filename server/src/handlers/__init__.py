"""
API handlers for OpenMemory Server.
"""
from .register import router as register_router
from .store import router as store_router
from .search import router as search_router
from .health import router as health_router
from .account import router as account_router
from .sync import router as sync_router
from .relay import relay_router

__all__ = [
    "register_router",
    "store_router",
    "search_router",
    "health_router",
    "account_router",
    "sync_router",
    "relay_router",
]
