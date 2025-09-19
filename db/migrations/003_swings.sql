-- 003_swings.sql: Pivot points for swing detection

CREATE TABLE IF NOT EXISTS swings (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    price NUMERIC(18,8) NOT NULL CHECK (price > 0),
    is_high BOOLEAN NOT NULL,
    strength INTEGER NOT NULL CHECK (strength >= 1 AND strength <= 10),
    volume_profile NUMERIC(18,8) CHECK (volume_profile IS NULL OR volume_profile >= 0),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_swings PRIMARY KEY (venue, symbol, timeframe, timestamp, is_high)
);

-- Create hypertable
SELECT create_hypertable(
    'swings',
    'timestamp',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Create indexes as specified in PRD
CREATE INDEX IF NOT EXISTS idx_swings_symbol_tf_time
    ON swings (symbol, timeframe, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_swings_venue_symbol_time
    ON swings (venue, symbol, timestamp DESC);

-- Index for high strength pivots
CREATE INDEX IF NOT EXISTS idx_swings_high_strength
    ON swings (symbol, timeframe, timestamp DESC)
    WHERE strength >= 7;

-- Separate indexes for swing highs and lows
CREATE INDEX IF NOT EXISTS idx_swings_highs
    ON swings (symbol, timeframe, timestamp DESC)
    WHERE is_high = true;

CREATE INDEX IF NOT EXISTS idx_swings_lows
    ON swings (symbol, timeframe, timestamp DESC)
    WHERE is_high = false;

-- Set compression policy
ALTER TABLE swings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, timeframe, is_high',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy
SELECT add_compression_policy(
    'swings',
    compress_after => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Add retention policy
SELECT add_retention_policy(
    'swings',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON swings TO trading_user;