"""
FastAPI routes for TotalReclaw relay (Pimlico paymaster integration).

Endpoints:
    POST /v1/relay/sponsor               — Sponsor and submit a UserOp (auth required)
    POST /v1/relay/webhook/pimlico        — Pimlico sponsorship policy webhook (no wallet auth)
    GET  /v1/relay/status/{user_op_hash}  — Check UserOp status (auth required)
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..config import get_settings
from ..db import get_db, Database
from ..dependencies import get_current_user
from .paymaster_service import PaymasterService, PaymasterServiceError
from .webhook_handler import WebhookHandler, verify_pimlico_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relay", tags=["relay"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class UserOperationDict(BaseModel):
    """ERC-4337 UserOperation fields as produced by the client."""
    sender: str = Field(..., description="Smart Account address")
    nonce: str = Field(..., description="Account nonce (hex)")
    initCode: str = Field("0x", description="Account init code (hex)")
    callData: str = Field(..., description="Encoded call data (hex)")
    callGasLimit: str = Field("0x0", description="Gas limit for the call (hex)")
    verificationGasLimit: str = Field("0x0", description="Gas limit for verification (hex)")
    preVerificationGas: str = Field("0x0", description="Pre-verification gas (hex)")
    maxFeePerGas: str = Field("0x0", description="Max fee per gas (hex)")
    maxPriorityFeePerGas: str = Field("0x0", description="Max priority fee per gas (hex)")
    paymasterAndData: str = Field("0x", description="Paymaster address and data (hex)")
    signature: str = Field("0x", description="User signature (hex)")


class SponsorRequest(BaseModel):
    """POST /v1/relay/sponsor request body."""
    userOperation: UserOperationDict = Field(
        ..., description="The UserOperation to sponsor and submit"
    )
    target: str = Field(
        ..., description="Target contract address (must be EventfulDataEdge)"
    )
    sponsorshipPolicyId: Optional[str] = Field(
        None, description="Pimlico sponsorship policy ID (optional)"
    )


class SponsorResponse(BaseModel):
    """POST /v1/relay/sponsor response body."""
    success: bool
    userOpHash: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class StatusResponse(BaseModel):
    """GET /v1/relay/status/{user_op_hash} response body."""
    success: bool
    status: Optional[str] = None  # "pending" | "included" | "failed"
    transactionHash: Optional[str] = None
    blockNumber: Optional[int] = None
    gasUsed: Optional[str] = None
    userOpSuccess: Optional[bool] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class WebhookResponse(BaseModel):
    """POST /v1/relay/webhook/pimlico response body."""
    sponsor: bool
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /v1/relay/sponsor — Sponsor and submit a UserOp
# ---------------------------------------------------------------------------

@router.post("/sponsor", response_model=SponsorResponse)
async def sponsor_user_operation(
    body: SponsorRequest,
    user_id: str = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Sponsor a UserOperation via Pimlico paymaster, then submit it to the
    bundler for on-chain inclusion.

    Flow:
        1. Validate that the target is the EventfulDataEdge contract.
        2. Call Pimlico to get gas estimates and paymaster signature.
        3. Submit the sponsored, signed UserOp to the Pimlico bundler.
        4. Return the UserOperation hash for polling.

    Requires wallet-based authentication (Bearer token).
    """
    settings = get_settings()

    # Validate target is our DataEdge contract
    if not settings.data_edge_address:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Relay not configured (missing DATA_EDGE_ADDRESS)",
        )

    if body.target.lower() != settings.data_edge_address.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid target contract address",
        )

    # Validate calldata is not empty
    if not body.userOperation.callData or body.userOperation.callData == "0x":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty calldata. Nothing to write.",
        )

    user_op_dict = body.userOperation.model_dump()
    wallet_address = body.userOperation.sender

    try:
        svc = PaymasterService()

        # Step 1: Sponsor — get gas estimates + paymaster signature
        sponsored_op = await svc.sponsor_user_operation(
            user_op=user_op_dict,
            wallet_address=wallet_address,
            sponsorship_policy_id=body.sponsorshipPolicyId,
        )

        # Step 2: Submit to bundler
        # The client has already signed the UserOp. The sponsor step adds
        # paymaster data. Now we submit the fully prepared UserOp.
        user_op_hash = await svc.submit_user_operation(sponsored_op)

        logger.info(
            "UserOp sponsored and submitted",
            extra={
                "user_op_hash": user_op_hash,
                "wallet_address": wallet_address,
                "user_id": user_id,
            },
        )

        return SponsorResponse(
            success=True,
            userOpHash=user_op_hash,
        )

    except PaymasterServiceError as exc:
        logger.error(
            "Sponsorship/submission failed: %s",
            exc.message,
            extra={
                "wallet_address": wallet_address,
                "rpc_error": exc.rpc_error,
            },
        )
        return SponsorResponse(
            success=False,
            error_code="SPONSORSHIP_FAILED",
            error_message=exc.message,
        )
    except Exception as exc:
        logger.error(
            "Unexpected relay error: %s", exc, exc_info=True,
        )
        return SponsorResponse(
            success=False,
            error_code="INTERNAL_ERROR",
            error_message="Internal relay error. Please try again.",
        )


# ---------------------------------------------------------------------------
# POST /v1/relay/webhook/pimlico — Pimlico sponsorship webhook
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/pimlico",
    response_model=WebhookResponse,
    include_in_schema=False,  # Hide from public API docs
)
async def pimlico_webhook(
    request: Request,
    db: Database = Depends(get_db),
):
    """
    Pimlico sponsorship policy webhook.

    Called by Pimlico when a UserOp requests gas sponsorship via a
    sponsorship policy with a webhook attached. This endpoint checks
    the user's subscription status and returns a sponsor/deny decision.

    No wallet auth — authenticated via Pimlico HMAC-SHA256 signature.
    The signature is sent in the X-Pimlico-Signature header.
    """
    payload_bytes = await request.body()
    sig_header = request.headers.get("x-pimlico-signature", "")

    if not sig_header:
        logger.warning("Pimlico webhook missing signature header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Pimlico-Signature header",
        )

    # Verify HMAC-SHA256 signature
    if not verify_pimlico_signature(payload_bytes, sig_header):
        logger.warning("Pimlico webhook signature verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # Parse and process the webhook event
    try:
        payload = json.loads(payload_bytes)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed webhook payload: {exc}",
        )

    handler = WebhookHandler(db)
    result = await handler.handle_sponsorship_request(payload)

    return WebhookResponse(
        sponsor=result["sponsor"],
        reason=result.get("reason"),
    )


# ---------------------------------------------------------------------------
# GET /v1/relay/status/{user_op_hash} — Check UserOp status
# ---------------------------------------------------------------------------

@router.get("/status/{user_op_hash}", response_model=StatusResponse)
async def get_user_op_status(
    user_op_hash: str,
    user_id: str = Depends(get_current_user),
):
    """
    Check the status of a submitted UserOperation.

    Polls the Pimlico bundler for the receipt. Returns "pending" if
    the UserOp has not been mined yet.

    Requires wallet-based authentication (Bearer token).
    """
    # Validate hash format (should be 0x-prefixed hex, 66 chars)
    if not user_op_hash.startswith("0x") or len(user_op_hash) != 66:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UserOperation hash format (expected 0x + 64 hex chars)",
        )

    try:
        svc = PaymasterService()
        receipt = await svc.get_user_op_receipt(user_op_hash)

        if receipt is None:
            return StatusResponse(
                success=True,
                status="pending",
            )

        # Extract receipt details
        tx_receipt = receipt.get("receipt", {})
        user_op_success = receipt.get("success")

        return StatusResponse(
            success=True,
            status="included" if user_op_success else "failed",
            transactionHash=tx_receipt.get("transactionHash"),
            blockNumber=(
                int(tx_receipt["blockNumber"], 16)
                if tx_receipt.get("blockNumber")
                else None
            ),
            gasUsed=tx_receipt.get("gasUsed"),
            userOpSuccess=user_op_success,
        )

    except PaymasterServiceError as exc:
        logger.error(
            "UserOp status check failed: %s",
            exc.message,
            extra={"user_op_hash": user_op_hash},
        )
        return StatusResponse(
            success=False,
            error_code="STATUS_CHECK_FAILED",
            error_message=exc.message,
        )
    except Exception as exc:
        logger.error(
            "Unexpected error checking UserOp status: %s",
            exc,
            exc_info=True,
        )
        return StatusResponse(
            success=False,
            error_code="INTERNAL_ERROR",
            error_message="Failed to check UserOp status.",
        )
