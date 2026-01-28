-- 008_add_foreign_keys.sql: Add foreign key constraints for referential integrity

-- TimescaleDB limitation: hypertables cannot participate in foreign keys where
-- either side is a hypertable. Candles/indicators/smc_events/zones are modeled
-- as hypertables for time-series performance, so we intentionally avoid FKs here.

-- Add indexes for foreign key performance
CREATE INDEX IF NOT EXISTS idx_orders_decision_id ON orders(decision_id);
CREATE INDEX IF NOT EXISTS idx_positions_decision_id ON positions(decision_id);
CREATE INDEX IF NOT EXISTS idx_indicators_candle_ref ON indicators(venue, symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_zones_candle_ref ON zones(venue, symbol, timeframe, created_at);

-- Add check constraints for data integrity
ALTER TABLE orders
ADD CONSTRAINT chk_orders_quantity_positive CHECK (quantity > 0);

ALTER TABLE orders
ADD CONSTRAINT chk_orders_filled_quantity CHECK (filled_quantity >= 0 AND filled_quantity <= quantity);

ALTER TABLE positions
ADD CONSTRAINT chk_positions_size_positive CHECK (size > 0);

ALTER TABLE positions
ADD CONSTRAINT chk_positions_leverage CHECK (leverage > 0 AND leverage <= 125);

ALTER TABLE candles
ADD CONSTRAINT chk_candles_price_order CHECK (low_price <= open_price AND low_price <= close_price AND high_price >= open_price AND high_price >= close_price);

ALTER TABLE candles
ADD CONSTRAINT chk_candles_volume_positive CHECK (volume >= 0 AND quote_volume >= 0 AND trades >= 0);
