-- 024_add_venue_to_decisions.sql: Add venue column to decisions table for benchmark filtering
-- Venue indicates which exchange/market (spot, usdm) the decision targets

ALTER TABLE decisions ADD COLUMN IF NOT EXISTS venue TEXT;

-- Default existing rows to NULL (will be populated by new code)
-- No default constraint - venue is optional for backwards compatibility

-- Create index for filtering by venue
CREATE INDEX IF NOT EXISTS idx_decisions_venue_symbol_timestamp
    ON decisions (venue, symbol, timestamp DESC)
    WHERE venue IS NOT NULL;

COMMENT ON COLUMN decisions.venue IS 'Exchange venue: spot, usdm, etc. NULL for legacy rows.';
