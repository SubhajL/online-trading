-- 005_zones.sql: Supply/demand zones and order blocks

CREATE TABLE IF NOT EXISTS zones (
    zone_id UUID NOT NULL DEFAULT gen_random_uuid(),
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    zone_type TEXT NOT NULL CHECK (zone_type IN ('SUPPLY', 'DEMAND', 'ORDER_BLOCK_BULLISH', 'ORDER_BLOCK_BEARISH', 'FAIR_VALUE_GAP')),
    top_price NUMERIC(18,8) NOT NULL CHECK (top_price > 0),
    bottom_price NUMERIC(18,8) NOT NULL CHECK (bottom_price > 0),
    created_at TIMESTAMPTZ NOT NULL,
    strength INTEGER NOT NULL CHECK (strength >= 1 AND strength <= 10),
    volume_profile NUMERIC(18,8) NOT NULL CHECK (volume_profile >= 0),
    touches INTEGER NOT NULL DEFAULT 0 CHECK (touches >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    tested_at TIMESTAMPTZ,
    invalidated_at TIMESTAMPTZ,
    invalidation_reason TEXT,
    origin_candle_time TIMESTAMPTZ,
    origin_swing_price NUMERIC(18,8) CHECK (origin_swing_price > 0),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_zones PRIMARY KEY (zone_id),
    CONSTRAINT uq_zones_unique_zone UNIQUE (venue, symbol, timeframe, zone_type, created_at, top_price, bottom_price),
    CONSTRAINT chk_price_order CHECK (top_price > bottom_price),
    CONSTRAINT chk_tested_after_created CHECK (tested_at IS NULL OR tested_at >= created_at),
    CONSTRAINT chk_invalidated_after_created CHECK (invalidated_at IS NULL OR invalidated_at >= created_at)
);

-- Create hypertable on created_at (when zone was identified)
SELECT create_hypertable(
    'zones',
    'created_at',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Create indexes as specified in PRD
CREATE INDEX IF NOT EXISTS idx_zones_symbol_tf_created
    ON zones (symbol, timeframe, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_zones_venue_symbol_created
    ON zones (venue, symbol, created_at DESC);

-- Index for active zones only
CREATE INDEX IF NOT EXISTS idx_zones_active
    ON zones (symbol, timeframe, created_at DESC)
    WHERE is_active = TRUE;

-- Index for zone types
CREATE INDEX IF NOT EXISTS idx_zones_by_type
    ON zones (symbol, zone_type, created_at DESC)
    WHERE is_active = TRUE;

-- Index for high strength zones
CREATE INDEX IF NOT EXISTS idx_zones_high_strength
    ON zones (symbol, timeframe, created_at DESC)
    WHERE is_active = TRUE AND strength >= 7;

-- Index for untested zones
CREATE INDEX IF NOT EXISTS idx_zones_untested
    ON zones (symbol, timeframe, created_at DESC)
    WHERE is_active = TRUE AND touches = 0;

-- Index for price range queries
CREATE INDEX IF NOT EXISTS idx_zones_price_range
    ON zones (symbol, bottom_price, top_price)
    WHERE is_active = TRUE;

-- Add updated_at trigger
DROP TRIGGER IF EXISTS update_zones_updated_at ON zones;
CREATE TRIGGER update_zones_updated_at
    BEFORE UPDATE ON zones
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Set compression policy
ALTER TABLE zones SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, timeframe, zone_type',
    timescaledb.compress_orderby = 'created_at DESC'
);

-- Add compression policy
SELECT add_compression_policy(
    'zones',
    compress_after => INTERVAL '90 days',
    if_not_exists => TRUE
);

-- Add retention policy
SELECT add_retention_policy(
    'zones',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON zones TO trading_user;