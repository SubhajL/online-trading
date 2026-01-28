-- 024_add_venue_to_decisions.sql: Ensure venue exists on trading_decisions for benchmark filtering
-- Venue indicates which exchange/market (spot, usdm) the decision targets.

-- Add venue to trading_decisions (primary table used by benchmark validator)
ALTER TABLE trading_decisions ADD COLUMN IF NOT EXISTS venue TEXT;

-- Create index for filtering by venue
CREATE INDEX IF NOT EXISTS idx_trading_decisions_venue_symbol_timestamp
    ON trading_decisions (venue, symbol, timestamp DESC)
    WHERE venue IS NOT NULL;

COMMENT ON COLUMN trading_decisions.venue IS 'Exchange venue: spot, usdm, etc. NULL for legacy rows.';
