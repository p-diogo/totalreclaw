"""
SQLAlchemy model for the subscriptions table.

Tracks user subscription state (free vs pro), payment source,
and free-tier usage counters.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Text, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..db.models import Base


class Subscription(Base):
    """
    Subscription model for billing state.

    Each wallet address has at most one subscription row.
    Free-tier users may not have a row at all (treated as free with 0 writes used).

    Columns:
        wallet_address: ERC-4337 Smart Account address (primary key)
        tier: 'free' or 'pro'
        source: Payment source — 'stripe' or 'coinbase_commerce'
        stripe_id: Stripe Subscription ID (sub_xxx)
        stripe_customer_id: Stripe Customer ID (cus_xxx) for reuse across sessions
        coinbase_id: Coinbase Commerce charge ID (future)
        expires_at: When the current billing period ends (NULL for free tier)
        free_writes_used: Count of writes consumed in current free-tier period
        free_writes_reset_at: When free_writes_used was last reset (monthly)
        created_at: Row creation timestamp
        updated_at: Last modification timestamp
    """
    __tablename__ = "subscriptions"

    wallet_address: Mapped[str] = mapped_column(Text, primary_key=True)
    tier: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="free"
    )
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stripe_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    coinbase_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    free_writes_used: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    free_writes_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription(wallet={self.wallet_address}, "
            f"tier={self.tier}, source={self.source})>"
        )
