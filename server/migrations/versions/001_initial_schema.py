"""Initial schema -- users, facts, raw_events, tombstones.

Revision ID: 001
Revises: None
Create Date: 2026-02-24

This migration matches the existing schema.sql and is the baseline
for all future migrations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Users table
    op.create_table(
        "users",
        sa.Column("user_id", sa.Text, primary_key=True),
        sa.Column("auth_key_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("salt", sa.LargeBinary(32), nullable=False),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_auth_hash", "users", ["auth_key_hash"])

    # Raw events table
    op.create_table(
        "raw_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_bytes", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_events_user", "raw_events", ["user_id", sa.text("created_at DESC")])

    # Facts table
    op.create_table(
        "facts",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("encrypted_blob", sa.LargeBinary, nullable=False),
        sa.Column("blind_indices", ARRAY(sa.Text), nullable=False),
        sa.Column("decay_score", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_facts_user", "facts", ["user_id"])
    op.create_index("idx_facts_active_decay", "facts", ["user_id", "is_active", sa.text("decay_score DESC")])
    op.create_index("idx_facts_blind_gin", "facts", ["blind_indices"], postgresql_using="gin")
    op.create_index("idx_facts_search", "facts", ["user_id", "is_active"], postgresql_where=sa.text("is_active = true"))

    # Tombstones table
    op.create_table(
        "tombstones",
        sa.Column("fact_id", sa.Text, sa.ForeignKey("facts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_tombstones_expiry", "tombstones", ["deleted_at"])

    # Update trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trigger_facts_updated_at
            BEFORE UPDATE ON facts
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trigger_facts_updated_at ON facts")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at()")
    op.drop_table("tombstones")
    op.drop_table("facts")
    op.drop_table("raw_events")
    op.drop_table("users")
