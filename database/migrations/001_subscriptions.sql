-- Migration 001: Create subscriptions table for billing
-- TotalReclaw v0.4 — Stripe Checkout integration
--
-- This table tracks subscription state per wallet address.
-- Free-tier users may or may not have a row (absence = free with 0 usage).

CREATE TABLE IF NOT EXISTS subscriptions (
    wallet_address      TEXT PRIMARY KEY,
    tier                TEXT NOT NULL DEFAULT 'free',            -- 'free' | 'pro'
    source              TEXT,                                    -- 'stripe' | 'coinbase_commerce'
    stripe_id           TEXT,                                    -- Stripe Subscription ID (sub_xxx)
    stripe_customer_id  TEXT,                                    -- Stripe Customer ID (cus_xxx)
    coinbase_id         TEXT,                                    -- Coinbase Commerce charge ID (future)
    expires_at          TIMESTAMPTZ,                             -- NULL for free tier
    free_writes_used    INTEGER NOT NULL DEFAULT 0,
    free_writes_reset_at TIMESTAMPTZ,                            -- Last monthly counter reset
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for Stripe subscription lookups (webhook handler)
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_id
    ON subscriptions (stripe_id)
    WHERE stripe_id IS NOT NULL;

-- Index for Stripe customer lookups (checkout reuse)
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer
    ON subscriptions (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- Index for Coinbase Commerce charge lookups (webhook reconciliation)
CREATE INDEX IF NOT EXISTS idx_subscriptions_coinbase_id
    ON subscriptions (coinbase_id)
    WHERE coinbase_id IS NOT NULL;

-- Trigger to auto-update updated_at on row changes
-- (Reuses update_updated_at() function from migration 001 in server/migrations/)
CREATE OR REPLACE TRIGGER trigger_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

COMMENT ON TABLE subscriptions IS 'Subscription state per wallet address — billing tier, Stripe IDs, free-tier usage';
COMMENT ON COLUMN subscriptions.wallet_address IS 'ERC-4337 Smart Account address (primary key)';
COMMENT ON COLUMN subscriptions.tier IS 'Current subscription tier: free or pro';
COMMENT ON COLUMN subscriptions.source IS 'Payment source: stripe or coinbase_commerce';
COMMENT ON COLUMN subscriptions.stripe_id IS 'Stripe Subscription ID (sub_xxx)';
COMMENT ON COLUMN subscriptions.stripe_customer_id IS 'Stripe Customer ID (cus_xxx) for session reuse';
COMMENT ON COLUMN subscriptions.coinbase_id IS 'Coinbase Commerce charge ID (future use)';
COMMENT ON COLUMN subscriptions.expires_at IS 'When current billing period ends (NULL for free)';
COMMENT ON COLUMN subscriptions.free_writes_used IS 'Number of writes consumed in current free-tier month';
COMMENT ON COLUMN subscriptions.free_writes_reset_at IS 'Timestamp of last monthly free_writes_used reset';
