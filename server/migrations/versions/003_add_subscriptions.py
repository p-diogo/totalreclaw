"""Add subscriptions table for billing.

Revision ID: 003
Revises: 002
Create Date: 2026-03-03

Tracks subscription state per wallet address: tier (free/pro),
Stripe IDs, free-tier usage counters, and expiry timestamps.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("wallet_address", sa.Text, primary_key=True),
        sa.Column("tier", sa.Text, nullable=False, server_default="free"),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("stripe_id", sa.Text, nullable=True),
        sa.Column("stripe_customer_id", sa.Text, nullable=True),
        sa.Column("coinbase_id", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("free_writes_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("free_writes_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Index for webhook handler — lookup by Stripe Subscription ID
    op.create_index(
        "idx_subscriptions_stripe_id",
        "subscriptions",
        ["stripe_id"],
        postgresql_where=sa.text("stripe_id IS NOT NULL"),
    )

    # Index for checkout session reuse — lookup by Stripe Customer ID
    op.create_index(
        "idx_subscriptions_stripe_customer",
        "subscriptions",
        ["stripe_customer_id"],
        postgresql_where=sa.text("stripe_customer_id IS NOT NULL"),
    )

    # Index for Coinbase Commerce charge reconciliation
    op.create_index(
        "idx_subscriptions_coinbase_id",
        "subscriptions",
        ["coinbase_id"],
        postgresql_where=sa.text("coinbase_id IS NOT NULL"),
    )

    # Reuse the update_updated_at() trigger function from migration 001
    op.execute("""
        CREATE TRIGGER trigger_subscriptions_updated_at
            BEFORE UPDATE ON subscriptions
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trigger_subscriptions_updated_at ON subscriptions")
    op.drop_table("subscriptions")
