-- 023_add_order_timing_columns.sql: Add timing columns for execution quality tracking
-- Tracks full timestamp chain: decision → router_received → router_sent → exchange_ack → first_fill → filled

ALTER TABLE orders ADD COLUMN IF NOT EXISTS decision_ts TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS expected_price NUMERIC(20, 8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS router_received_ts TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS router_sent_ts TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS exchange_ack_ts TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS first_fill_ts TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS filled_ts TIMESTAMPTZ;

-- Index for execution quality queries by venue and time range
CREATE INDEX IF NOT EXISTS idx_orders_venue_router_received
ON orders (venue, router_received_ts DESC)
WHERE router_received_ts IS NOT NULL;

-- Index for execution quality queries by symbol and time range
CREATE INDEX IF NOT EXISTS idx_orders_symbol_router_received
ON orders (symbol, router_received_ts DESC)
WHERE router_received_ts IS NOT NULL;

-- Index for latency analysis (decision to router)
CREATE INDEX IF NOT EXISTS idx_orders_decision_ts
ON orders (decision_ts DESC)
WHERE decision_ts IS NOT NULL;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON orders TO trading_user;
