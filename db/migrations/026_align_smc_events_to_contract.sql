-- 026_align_smc_events_to_contract.sql: Add columns to smc_events matching smc_events.v1 contract schema.
-- The original table (004) used structure_type as part of PK and different column names.
-- We add the contract-aligned columns so insert_smc_event_v1 can persist directly.

ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS event_time TIMESTAMPTZ;
ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS direction TEXT;
ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS price_level NUMERIC(18,8);
ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS previous_pivot_price NUMERIC(18,8);
ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS previous_pivot_time TIMESTAMPTZ;
ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS broken_pivot_price NUMERIC(18,8);
ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS broken_pivot_time TIMESTAMPTZ;
ALTER TABLE smc_events ADD COLUMN IF NOT EXISTS version TEXT;

-- Unique constraint for v1 contract-based inserts (ON CONFLICT target)
CREATE UNIQUE INDEX IF NOT EXISTS uq_smc_events_v1
    ON smc_events (symbol, timeframe, event_time, event_type, direction)
    WHERE event_time IS NOT NULL AND direction IS NOT NULL;
