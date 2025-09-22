-- 009_balances.sql: Account balance snapshots

CREATE TABLE IF NOT EXISTS balances (
    asset TEXT NOT NULL,
    venue TEXT NOT NULL CHECK (venue IN ('SPOT', 'USD_M')),
    free NUMERIC(18,8) NOT NULL CHECK (free >= 0),
    locked NUMERIC(18,8) NOT NULL CHECK (locked >= 0),
    total NUMERIC(18,8) NOT NULL GENERATED ALWAYS AS (free + locked) STORED,
    usd_value NUMERIC(18,8) CHECK (usd_value IS NULL OR usd_value >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_balances PRIMARY KEY (asset, venue)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_balances_venue
    ON balances (venue, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_balances_asset
    ON balances (asset, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_balances_updated_at
    ON balances (updated_at DESC);

-- Create a view for latest non-zero balances
CREATE OR REPLACE VIEW latest_balances AS
SELECT
    asset,
    venue,
    free,
    locked,
    total,
    usd_value,
    updated_at
FROM balances
WHERE total > 0
ORDER BY venue, asset;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON balances TO trading_user;
GRANT SELECT ON latest_balances TO trading_user;

-- Create function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_balance_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update timestamp
DROP TRIGGER IF EXISTS update_balances_updated_at ON balances;
CREATE TRIGGER update_balances_updated_at
    BEFORE UPDATE ON balances
    FOR EACH ROW
    EXECUTE FUNCTION update_balance_timestamp();