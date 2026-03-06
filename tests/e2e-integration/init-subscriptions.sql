-- E2E Integration: Ensure subscriptions table exists with all columns,
-- and apply any pending migrations not yet in schema.sql.
-- The server's schema.sql (mounted as 01-schema.sql) already creates this table,
-- but this file serves as a safety net and adds the update_updated_at() function
-- if not already present (needed by the subscriptions trigger).

-- Migration 002: Add encrypted_embedding column to facts table (PoC v2)
ALTER TABLE facts ADD COLUMN IF NOT EXISTS encrypted_embedding TEXT;

-- Ensure the trigger function exists (created by 01-schema.sql but just in case)
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Ensure subscriptions table exists with all columns
CREATE TABLE IF NOT EXISTS subscriptions (
    wallet_address      TEXT PRIMARY KEY,
    tier                TEXT NOT NULL DEFAULT 'free',
    source              TEXT,
    stripe_id           TEXT,
    stripe_customer_id  TEXT,
    coinbase_id         TEXT,
    expires_at          TIMESTAMPTZ,
    free_writes_used    INTEGER NOT NULL DEFAULT 0,
    free_writes_reset_at TIMESTAMPTZ,
    free_reads_used     INTEGER NOT NULL DEFAULT 0,
    free_reads_reset_at TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for billing lookups
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_id
    ON subscriptions (stripe_id)
    WHERE stripe_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer
    ON subscriptions (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_subscriptions_coinbase_id
    ON subscriptions (coinbase_id)
    WHERE coinbase_id IS NOT NULL;

-- Apply updated_at trigger
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trigger_subscriptions_updated_at'
    ) THEN
        CREATE TRIGGER trigger_subscriptions_updated_at
            BEFORE UPDATE ON subscriptions
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at();
    END IF;
END;
$$;
