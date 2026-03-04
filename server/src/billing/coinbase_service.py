"""
Coinbase Commerce integration for TotalReclaw Server.

Handles creating charges and verifying webhook signatures for
crypto payments (USDC, USDT, ETH on Base, Ethereum, Solana, Polygon, Arbitrum).

Coinbase Commerce does NOT have an official Python SDK.
All API calls use httpx directly.
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import text

from ..config import get_settings
from ..db import Database

logger = logging.getLogger(__name__)

# Coinbase Commerce API
COINBASE_COMMERCE_BASE_URL = "https://api.commerce.coinbase.com"
CHARGE_ENDPOINT = f"{COINBASE_COMMERCE_BASE_URL}/charges"

# Subscription duration for a single charge
SUBSCRIPTION_DAYS = 30


class CoinbaseServiceError(Exception):
    """Error raised when Coinbase Commerce API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class CoinbaseWebhookError(Exception):
    """Error raised when webhook verification or processing fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CoinbaseService:
    """
    Coinbase Commerce service for creating charges and handling webhooks.

    Each charge is a one-time payment that activates 30 days of Pro tier.
    There is no recurring billing through Coinbase Commerce -- the agent
    creates a new charge each month (or prompts the user to renew).
    """

    def __init__(self, db: Database):
        settings = get_settings()
        self.db = db
        self.api_key = settings.coinbase_commerce_api_key
        self.webhook_secret = settings.coinbase_commerce_webhook_secret

    async def create_charge(
        self,
        wallet_address: str,
        amount: str = "5.00",
        currency: str = "USD",
    ) -> str:
        """
        Create a Coinbase Commerce charge for a TotalReclaw Pro subscription.

        Args:
            wallet_address: The user's ERC-4337 Smart Account address.
            amount: Price amount as a string (e.g., "5.00").
            currency: Price currency code (e.g., "USD").

        Returns:
            The hosted checkout URL where the user completes payment.

        Raises:
            CoinbaseServiceError: If the API call fails.
        """
        if not self.api_key:
            raise CoinbaseServiceError(
                "COINBASE_COMMERCE_API_KEY not configured",
                status_code=500,
            )

        payload = {
            "name": "TotalReclaw Pro",
            "description": "Monthly subscription to TotalReclaw Pro",
            "pricing_type": "fixed_price",
            "local_price": {
                "amount": amount,
                "currency": currency,
            },
            "metadata": {
                "wallet_address": wallet_address,
            },
            "redirect_url": "https://totalreclaw.com/payment/success",
            "cancel_url": "https://totalreclaw.com/payment/cancel",
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CC-Api-Key": self.api_key,
            "X-CC-Version": "2018-03-22",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    CHARGE_ENDPOINT,
                    json=payload,
                    headers=headers,
                )

            if response.status_code not in (200, 201):
                error_body = response.text
                logger.error(
                    "Coinbase Commerce create charge failed",
                    extra={
                        "status_code": response.status_code,
                        "body": error_body[:500],
                        "wallet_address": wallet_address,
                    },
                )
                raise CoinbaseServiceError(
                    f"Coinbase Commerce API error: {response.status_code}",
                    status_code=response.status_code,
                )

            data = response.json().get("data", {})
            hosted_url = data.get("hosted_url")
            charge_id = data.get("id") or data.get("code")

            if not hosted_url:
                raise CoinbaseServiceError(
                    "Coinbase Commerce response missing hosted_url"
                )

            logger.info(
                "Coinbase Commerce charge created",
                extra={
                    "charge_id": charge_id,
                    "wallet_address": wallet_address,
                    "amount": amount,
                    "currency": currency,
                },
            )

            return hosted_url

        except httpx.HTTPError as exc:
            logger.error(
                "Coinbase Commerce HTTP error",
                extra={"error": str(exc), "wallet_address": wallet_address},
            )
            raise CoinbaseServiceError(
                f"Failed to connect to Coinbase Commerce: {exc}"
            ) from exc

    def verify_webhook_signature(
        self, payload: bytes, sig_header: str
    ) -> bool:
        """
        Verify the Coinbase Commerce webhook signature.

        Coinbase Commerce signs webhook payloads with HMAC-SHA256
        using the shared webhook secret. The signature is sent in
        the ``X-CC-Webhook-Signature`` header.

        Args:
            payload: Raw request body bytes.
            sig_header: Value of the X-CC-Webhook-Signature header.

        Returns:
            True if the signature is valid.
        """
        if not self.webhook_secret:
            logger.error("COINBASE_COMMERCE_WEBHOOK_SECRET not configured")
            return False

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, sig_header)

    async def handle_webhook(
        self, payload: bytes, sig_header: str
    ) -> dict:
        """
        Process a Coinbase Commerce webhook event.

        Verifies the HMAC-SHA256 signature, then dispatches based on
        event type:
          - ``charge:confirmed`` -- activate Pro subscription for 30 days
          - ``charge:failed``    -- log and return failure status
          - ``charge:pending``   -- log and return pending status

        Args:
            payload: Raw request body bytes.
            sig_header: Value of the X-CC-Webhook-Signature header.

        Returns:
            Dict with ``status`` key indicating processing outcome.

        Raises:
            CoinbaseWebhookError: On invalid signature or missing data.
        """
        # 1. Verify signature
        if not self.verify_webhook_signature(payload, sig_header):
            logger.warning("Coinbase webhook signature verification failed")
            raise CoinbaseWebhookError("Invalid webhook signature")

        # 2. Parse event
        try:
            event = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CoinbaseWebhookError(f"Malformed webhook payload: {exc}")

        event_type = event.get("event", {}).get("type")
        event_data = event.get("event", {}).get("data", {})
        charge_id = event_data.get("id") or event_data.get("code")
        metadata = event_data.get("metadata", {})
        wallet_address = metadata.get("wallet_address")

        logger.info(
            "Coinbase webhook received",
            extra={
                "event_type": event_type,
                "charge_id": charge_id,
                "wallet_address": wallet_address,
            },
        )

        if not wallet_address:
            raise CoinbaseWebhookError(
                "Webhook payload missing wallet_address in metadata"
            )

        # 3. Dispatch by event type
        if event_type == "charge:confirmed":
            await self._activate_subscription(wallet_address, charge_id)
            return {"status": "activated", "wallet_address": wallet_address}

        elif event_type == "charge:failed":
            logger.warning(
                "Coinbase charge failed",
                extra={
                    "charge_id": charge_id,
                    "wallet_address": wallet_address,
                },
            )
            return {"status": "failed", "wallet_address": wallet_address}

        elif event_type == "charge:pending":
            logger.info(
                "Coinbase charge pending",
                extra={
                    "charge_id": charge_id,
                    "wallet_address": wallet_address,
                },
            )
            return {"status": "pending", "wallet_address": wallet_address}

        else:
            logger.info(
                "Coinbase webhook event type ignored",
                extra={"event_type": event_type},
            )
            return {"status": "ignored", "event_type": event_type}

    async def _activate_subscription(
        self, wallet_address: str, charge_id: str
    ) -> None:
        """
        Activate or extend a Pro subscription after confirmed payment.

        If the user already has an active Pro subscription (from Stripe or
        a previous Coinbase charge), the expiry is extended by 30 days from
        whichever is later: now or the current expiry.

        Args:
            wallet_address: User's ERC-4337 Smart Account address.
            charge_id: Coinbase Commerce charge ID for audit trail.
        """
        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(days=SUBSCRIPTION_DAYS)

        async with self.db.session() as session:
            # Check if this charge was already processed (idempotency)
            result = await session.execute(
                text(
                    "SELECT coinbase_id, tier, expires_at "
                    "FROM subscriptions "
                    "WHERE wallet_address = :addr"
                ),
                {"addr": wallet_address},
            )
            row = result.fetchone()

            if row and row.coinbase_id == charge_id:
                logger.info(
                    "Charge already processed (idempotent)",
                    extra={"charge_id": charge_id},
                )
                return

            if row is None:
                # First-time payment: insert new subscription
                await session.execute(
                    text(
                        "INSERT INTO subscriptions "
                        "(wallet_address, tier, source, coinbase_id, expires_at) "
                        "VALUES (:addr, 'pro', 'coinbase_commerce', :cid, :exp)"
                    ),
                    {
                        "addr": wallet_address,
                        "cid": charge_id,
                        "exp": new_expires,
                    },
                )
            else:
                # Existing subscription: extend from max(now, current expiry)
                current_expires = row.expires_at
                if (
                    current_expires
                    and current_expires.tzinfo
                    and current_expires > now
                ):
                    new_expires = current_expires + timedelta(
                        days=SUBSCRIPTION_DAYS
                    )

                await session.execute(
                    text(
                        "UPDATE subscriptions "
                        "SET tier = 'pro', "
                        "    source = 'coinbase_commerce', "
                        "    coinbase_id = :cid, "
                        "    expires_at = :exp, "
                        "    updated_at = NOW() "
                        "WHERE wallet_address = :addr"
                    ),
                    {
                        "addr": wallet_address,
                        "cid": charge_id,
                        "exp": new_expires,
                    },
                )

        logger.info(
            "Subscription activated via Coinbase Commerce",
            extra={
                "wallet_address": wallet_address,
                "charge_id": charge_id,
                "expires_at": new_expires.isoformat(),
            },
        )
