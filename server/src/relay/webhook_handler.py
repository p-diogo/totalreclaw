"""
Pimlico sponsorship webhook handler for TotalReclaw Server.

When a UserOp requests gas sponsorship via a Pimlico sponsorship policy,
Pimlico calls our webhook to ask: "Should I sponsor this UserOp?"

The webhook handler:
    1. Verifies the request signature (HMAC-SHA256 with webhook secret)
    2. Extracts the sender (Smart Account address) from the UserOp
    3. Checks subscription status (pro tier or free-tier quota remaining)
    4. Returns {"sponsor": true/false, "reason": "..."}

This is the core authorization gate that prevents sybil attacks and enforces
billing tiers.

Pimlico webhook event types:
    - user_operation.sponsorship.requested — Ask for approval. We respond.
    - user_operation.sponsorship.finalized — Notification after sponsorship.

Signature verification:
    Pimlico signs webhook payloads with HMAC-SHA256 using the webhook secret
    configured in the sponsorship policy settings. The signature is sent in
    a request header (typically X-Pimlico-Signature or similar). The Python
    implementation mirrors the @pimlico/webhook npm package behavior.
"""
import hashlib
import hmac
import json
import logging
from typing import Optional

from sqlalchemy import text

from ..config import get_settings
from ..db import Database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_pimlico_signature(
    payload: bytes,
    signature: str,
    webhook_secret: Optional[str] = None,
) -> bool:
    """
    Verify a Pimlico webhook signature using HMAC-SHA256.

    The signature is computed as HMAC-SHA256(webhook_secret, payload) and
    compared using constant-time comparison to prevent timing attacks.

    Args:
        payload: Raw request body bytes.
        signature: The signature from the webhook request header.
        webhook_secret: The webhook secret from Pimlico dashboard.
                        Falls back to settings.pimlico_webhook_secret.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not webhook_secret:
        settings = get_settings()
        webhook_secret = settings.pimlico_webhook_secret

    if not webhook_secret:
        logger.error("PIMLICO_WEBHOOK_SECRET not configured")
        return False

    if not signature:
        logger.warning("Empty signature in webhook request")
        return False

    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

class WebhookHandler:
    """
    Processes Pimlico sponsorship policy webhook events.

    The handler checks subscription status in the database and returns
    a sponsorship decision. It is independent from the billing module
    but queries the same subscriptions table.
    """

    # Free-tier monthly write quota. Override via FREE_TIER_RELAY_LIMIT env.
    FREE_TIER_RELAY_LIMIT: int = 100

    def __init__(self, db: Database):
        self.db = db

    async def handle_sponsorship_request(self, payload: dict) -> dict:
        """
        Process a Pimlico sponsorship webhook event.

        Called when Pimlico sends a webhook for event type
        ``user_operation.sponsorship.requested``. Extracts the sender
        address from the UserOp and checks whether the wallet has an
        active subscription or remaining free-tier quota.

        Args:
            payload: The parsed webhook JSON body. Expected structure:
                {
                    "type": "user_operation.sponsorship.requested",
                    "data": {
                        "object": {
                            "userOperation": { "sender": "0x..." },
                            "entryPoint": "0x...",
                            "chainId": 100,
                            "sponsorshipPolicyId": "sp_...",
                            "apiKey": "..."
                        }
                    }
                }

        Returns:
            {
                "sponsor": True/False,
                "reason": "..." (human-readable explanation)
            }
        """
        event_type = payload.get("type", "")

        # Only handle sponsorship requests. Finalized events are informational.
        if event_type == "user_operation.sponsorship.finalized":
            logger.info("Sponsorship finalized notification received")
            return {"sponsor": True, "reason": "finalized_notification"}

        if event_type != "user_operation.sponsorship.requested":
            logger.warning(
                "Unknown webhook event type: %s", event_type
            )
            return {"sponsor": False, "reason": f"unknown_event_type: {event_type}"}

        # Extract sender (Smart Account address) from the UserOp
        data_obj = payload.get("data", {}).get("object", {})
        user_op = data_obj.get("userOperation", {})
        sender = user_op.get("sender", "").lower()
        chain_id = data_obj.get("chainId")

        if not sender:
            logger.warning("Webhook payload missing sender address")
            return {"sponsor": False, "reason": "missing_sender_address"}

        logger.info(
            "Sponsorship request received",
            extra={
                "sender": sender,
                "chain_id": chain_id,
                "policy_id": data_obj.get("sponsorshipPolicyId"),
            },
        )

        # Check subscription status
        try:
            decision = await self._check_subscription(sender)
            logger.info(
                "Sponsorship decision",
                extra={
                    "sender": sender,
                    "sponsor": decision["sponsor"],
                    "reason": decision["reason"],
                },
            )
            return decision

        except Exception as exc:
            # On database errors, deny sponsorship to prevent unbounded spend.
            # This is a conservative fail-closed approach.
            logger.error(
                "Subscription check failed — denying sponsorship",
                extra={"sender": sender, "error": str(exc)},
                exc_info=True,
            )
            return {"sponsor": False, "reason": "internal_error"}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_subscription(self, wallet_address: str) -> dict:
        """
        Check whether a wallet address is authorized for gas sponsorship.

        Authorization rules:
            1. Pro tier with active (non-expired) subscription — always sponsor.
            2. Free tier with remaining monthly quota — sponsor.
            3. Free tier with exhausted quota — deny, suggest upgrade.
            4. No subscription row — treat as free tier with 0 usage.

        Args:
            wallet_address: The sender's Smart Account address (lowercase).

        Returns:
            {"sponsor": True/False, "reason": str}
        """
        from datetime import datetime, timezone

        async with self.db.session() as session:
            result = await session.execute(
                text("""
                    SELECT tier, expires_at, free_writes_used,
                           free_writes_reset_at
                    FROM subscriptions
                    WHERE wallet_address = :addr
                """),
                {"addr": wallet_address},
            )
            row = result.fetchone()

        # No subscription row — treat as free tier with 0 usage
        if row is None:
            return {
                "sponsor": True,
                "reason": "free_tier",
            }

        now = datetime.now(timezone.utc)

        # Pro tier check
        if row.tier == "pro":
            # Verify not expired
            if row.expires_at is None or row.expires_at > now:
                return {
                    "sponsor": True,
                    "reason": "active_subscription",
                }
            # Expired pro — fall through to free-tier logic
            logger.info(
                "Pro subscription expired, checking free tier",
                extra={"wallet_address": wallet_address},
            )

        # Free-tier usage check with monthly reset
        free_writes_used = row.free_writes_used or 0
        reset_at = row.free_writes_reset_at

        # Monthly reset: if reset_at is before current month start, treat as 0
        month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        if reset_at is None or reset_at < month_start:
            free_writes_used = 0

        if free_writes_used < self.FREE_TIER_RELAY_LIMIT:
            return {
                "sponsor": True,
                "reason": "free_tier",
            }

        return {
            "sponsor": False,
            "reason": "upgrade_required",
        }
