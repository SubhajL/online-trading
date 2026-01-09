-- 024_add_venue_to_decisions.sql: Add venue column to trading_decisions table for benchmark filtering
-- Venue indicates which exchange/market (spot, usdm) the decision targets
-- Note: trading_decisions table is created dynamically by Python adapter, but this migration
-- ensures the venue column exists for benchmark validation to filter by venue.

-- Add venue to trading_decisions (primary table used by benchmark validator)
ALTER TABLE trading_decisions ADD COLUMN IF NOT EXISTS venue TEXT;

-- Create index for filtering by venue
CREATE INDEX IF NOT EXISTS idx_trading_decisions_venue_symbol_timestamp
    ON trading_decisions (venue, symbol, timestamp DESC)
    WHERE venue IS NOT NULL;

COMMENT ON COLUMN trading_decisions.venue IS 'Exchange venue: spot, usdm, etc. NULL for legacy rows.';
