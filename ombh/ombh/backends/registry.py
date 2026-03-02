"""
Backend Registry

Provides a centralized registry for memory backends.
"""

from typing import Dict, Optional, Type

from ombh.backends.base import BackendType, MemoryBackend

# Global registry
_REGISTRY: Dict[BackendType, Type[MemoryBackend]] = {}


def register_backend(backend_type: BackendType) -> callable:
    """
    Decorator to register a backend class.

    Usage:
        @register_backend(BackendType.TOTALRECLAW_E2EE)
        class TotalReclawBackend(MemoryBackend):
            ...
    """
    def decorator(cls: Type[MemoryBackend]) -> Type[MemoryBackend]:
        _REGISTRY[backend_type] = cls
        return cls
    return decorator


def get_backend(
    backend_type: BackendType,
    **kwargs,
) -> MemoryBackend:
    """
    Get an instance of a backend by type.

    Args:
        backend_type: The type of backend to instantiate
        **kwargs: Arguments passed to the backend constructor

    Returns:
        Instantiated backend

    Raises:
        ValueError: If backend type is not registered
    """
    if backend_type not in _REGISTRY:
        available = [t.value for t in _REGISTRY.keys()]
        raise ValueError(
            f"Backend '{backend_type.value}' not registered. "
            f"Available: {available}"
        )

    cls = _REGISTRY[backend_type]
    return cls(**kwargs)


def list_backends() -> list[str]:
    """List all registered backend types."""
    return [t.value for t in _REGISTRY.keys()]


def is_registered(backend_type: BackendType) -> bool:
    """Check if a backend type is registered."""
    return backend_type in _REGISTRY
