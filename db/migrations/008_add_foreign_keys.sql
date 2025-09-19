-- 008_add_foreign_keys.sql: Add foreign key constraints for referential integrity

-- Add foreign key from orders to decisions
ALTER TABLE orders
ADD CONSTRAINT fk_orders_decision
FOREIGN KEY (decision_id)
REFERENCES decisions(decision_id)
ON DELETE SET NULL;

-- Add foreign key from positions to decisions
ALTER TABLE positions
ADD CONSTRAINT fk_positions_decision
FOREIGN KEY (decision_id)
REFERENCES decisions(decision_id)
ON DELETE SET NULL;

-- Add foreign key from indicators to candles (compound key)
ALTER TABLE indicators
ADD CONSTRAINT fk_indicators_candle
FOREIGN KEY (venue, symbol, timeframe, timestamp)
REFERENCES candles(venue, symbol, timeframe, open_time)
ON DELETE CASCADE;

-- Add foreign key from smc_events to candles for base_candle_time
ALTER TABLE smc_events
ADD CONSTRAINT fk_smc_events_base_candle
FOREIGN KEY (venue, symbol, timeframe, base_candle_time)
REFERENCES candles(venue, symbol, timeframe, open_time)
ON DELETE CASCADE;

-- Add foreign key from smc_events to candles for event_candle_time
ALTER TABLE smc_events
ADD CONSTRAINT fk_smc_events_event_candle
FOREIGN KEY (venue, symbol, timeframe, event_candle_time)
REFERENCES candles(venue, symbol, timeframe, open_time)
ON DELETE CASCADE;

-- Add foreign key from zones to candles for creation time
ALTER TABLE zones
ADD CONSTRAINT fk_zones_candle
FOREIGN KEY (venue, symbol, timeframe, created_at)
REFERENCES candles(venue, symbol, timeframe, open_time)
ON DELETE CASCADE;

-- Add indexes for foreign key performance
CREATE INDEX IF NOT EXISTS idx_orders_decision_id ON orders(decision_id);
CREATE INDEX IF NOT EXISTS idx_positions_decision_id ON positions(decision_id);
CREATE INDEX IF NOT EXISTS idx_indicators_candle_ref ON indicators(venue, symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_smc_events_base_candle ON smc_events(venue, symbol, timeframe, base_candle_time);
CREATE INDEX IF NOT EXISTS idx_smc_events_event_candle ON smc_events(venue, symbol, timeframe, event_candle_time);
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