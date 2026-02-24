"""
/relay endpoint — UserOperation relay to Pimlico bundler.

Accepts ERC-4337 UserOperations from the client, validates them,
and submits to the Pimlico bundler for inclusion on Base L2.

Security:
- Validates that the target is the EventfulDataEdge contract.
- Rate-limits per sender (Smart Account address).
- Does NOT validate the UserOp signature (the EntryPoint does that on-chain).

Rate limiting:
- In-memory sliding window per sender address.
- Configurable via RELAY_RATE_LIMIT_OPS and RELAY_RATE_LIMIT_WINDOW_SECONDS.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, Optional, List

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings

logger = logging.getLogger(__name__)

relay_router = APIRouter(tags=["relay"])


# --- Request/Response Models ---

class UserOperationPayload(BaseModel):
    """The UserOperation JSON as produced by the client's buildUserOperation()."""
    sender: str
    nonce: str
    initCode: str = "0x"
    callData: str
    callGasLimit: str = "0x50000"
    verificationGasLimit: str = "0x60000"
    preVerificationGas: str = "0x10000"
    maxFeePerGas: str = "0x0"
    maxPriorityFeePerGas: str = "0x0"
    paymasterAndData: str = "0x"
    signature: str


class RelayRequest(BaseModel):
    """POST /relay request body."""
    userOperation: UserOperationPayload
    target: str = Field(..., description="Target contract address (must be EventfulDataEdge)")


class RelayResponse(BaseModel):
    """POST /relay response body."""
    success: bool
    transactionHash: Optional[str] = None
    userOpHash: Optional[str] = None
    error_message: Optional[str] = None


# --- Rate Limiter ---

class RateLimiter:
    """In-memory sliding window rate limiter per sender address."""

    def __init__(self, max_ops: int, window_seconds: int):
        self.max_ops = max_ops
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def check(self, sender: str) -> bool:
        """Return True if the sender is within rate limits."""
        now = time.time()
        cutoff = now - self.window_seconds
        sender_lower = sender.lower()

        # Prune expired entries
        self._requests[sender_lower] = [
            t for t in self._requests[sender_lower] if t > cutoff
        ]

        if len(self._requests[sender_lower]) >= self.max_ops:
            return False

        self._requests[sender_lower].append(now)
        return True

    def get_count(self, sender: str) -> int:
        """Return current request count for a sender."""
        now = time.time()
        cutoff = now - self.window_seconds
        sender_lower = sender.lower()
        self._requests[sender_lower] = [
            t for t in self._requests[sender_lower] if t > cutoff
        ]
        return len(self._requests[sender_lower])


# Initialize rate limiter (will be reconfigured on first request)
_rate_limiter: Optional[RateLimiter] = None


def _get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = RateLimiter(
            max_ops=settings.relay_rate_limit_ops,
            window_seconds=settings.relay_rate_limit_window_seconds,
        )
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None


# --- Bundler Submission ---

async def submit_to_bundler(user_op: dict, entry_point: str) -> dict:
    """
    Submit a UserOperation to the Pimlico bundler via JSON-RPC.

    The bundler will:
    1. Simulate the UserOp on-chain
    2. If valid, include it in a bundle
    3. Submit the bundle to the mempool
    4. Return the UserOp hash

    Args:
        user_op: The UserOperation JSON
        entry_point: The EntryPoint contract address

    Returns:
        JSON-RPC response from the bundler
    """
    settings = get_settings()

    if not settings.pimlico_api_key:
        raise HTTPException(
            status_code=503,
            detail="Bundler not configured (missing PIMLICO_API_KEY)",
        )

    bundler_url = f"{settings.pimlico_bundler_url}?apikey={settings.pimlico_api_key}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_sendUserOperation",
        "params": [user_op, entry_point],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(bundler_url, json=payload)

        if response.status_code != 200:
            logger.error(f"Bundler returned {response.status_code}: {response.text}")
            raise HTTPException(
                status_code=502,
                detail="Bundler request failed",
            )

        result = response.json()

        if "error" in result:
            logger.error(f"Bundler RPC error: {result['error']}")
            raise HTTPException(
                status_code=400,
                detail="Bundler rejected the UserOperation",
            )

        return result


# --- Endpoint ---

@relay_router.post("/relay", response_model=RelayResponse)
async def relay_user_operation(request: RelayRequest):
    """
    Relay a signed UserOperation to the Pimlico bundler.

    The client builds and signs the UserOp locally, then sends it here.
    This server validates the target, applies rate limiting, and forwards
    to the bundler. The bundler handles on-chain signature verification.

    Returns the transaction hash on success.
    """
    settings = get_settings()

    # Validate target is our DataEdge contract
    if not settings.data_edge_address:
        raise HTTPException(
            status_code=503,
            detail="Relay not configured (missing DATA_EDGE_ADDRESS)",
        )

    if request.target.lower() != settings.data_edge_address.lower():
        raise HTTPException(
            status_code=403,
            detail="Invalid target contract address",
        )

    # Validate calldata is not empty
    if not request.userOperation.callData or request.userOperation.callData == "0x":
        raise HTTPException(
            status_code=400,
            detail="Empty calldata. Nothing to write.",
        )

    # Rate limit check
    limiter = _get_rate_limiter()
    sender = request.userOperation.sender
    if not limiter.check(sender):
        count = limiter.get_count(sender)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited. {count}/{limiter.max_ops} operations in current window.",
        )

    # Build the UserOp dict for the bundler
    user_op_dict = request.userOperation.model_dump()

    # Submit to bundler
    try:
        result = await submit_to_bundler(
            user_op=user_op_dict,
            entry_point=settings.entry_point_address,
        )

        user_op_hash = result.get("result", "")

        logger.info(
            f"UserOp relayed: sender={sender}, "
            f"userOpHash={user_op_hash}, "
            f"calldataSize={len(request.userOperation.callData) // 2 - 1} bytes"
        )

        return RelayResponse(
            success=True,
            userOpHash=user_op_hash,
            transactionHash=None,  # Available after bundler mines the tx
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Relay failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal relay error",
        )
