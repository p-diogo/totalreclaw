"""
Shared FastAPI dependencies for TotalReclaw Server.

Provides the common get_current_user dependency used across all
authenticated endpoints. Centralizes auth validation logic to
avoid duplication and ensure consistent security checks.
"""
from fastapi import Depends, HTTPException, status, Header
from typing import Optional

from .auth import hash_auth_key
from .db import get_db, Database

# Expected hex string length for a 32-byte auth key
_AUTH_KEY_HEX_LENGTH = 64


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Database = Depends(get_db)
) -> str:
    """
    Extract and validate user from Authorization header.

    Expects: Authorization: Bearer <hex-encoded-auth-key>

    Validates:
    - Header presence and format
    - Token length (must be exactly 64 hex chars = 32 bytes)
    - Hex encoding
    - Credential lookup against database

    Returns user_id if valid, raises HTTPException otherwise.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format"
        )

    token_hex = parts[1]

    # Input length validation: reject tokens that are not exactly 64 hex chars
    # (32 bytes). This prevents DoS via extremely long tokens that would waste
    # CPU on hex decoding and SHA-256 hashing.
    if len(token_hex) != _AUTH_KEY_HEX_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth key format"
        )

    try:
        auth_key = bytes.fromhex(token_hex)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth key format"
        )

    # Hash and look up user
    auth_key_hash = hash_auth_key(auth_key)
    user = await db.get_user_by_auth_hash(auth_key_hash)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Update last seen
    await db.update_last_seen(user.user_id)

    return user.user_id
