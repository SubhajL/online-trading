-- 027_smc_events_v1.sql: Dedicated table for smc_events.v1 contract schema.
-- Replaces the approach of adding columns to the legacy smc_events table.

CREATE TABLE IF NOT EXISTS smc_events_v1 (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CHOCH', 'BOS')),
    direction TEXT NOT NULL CHECK (direction IN ('bullish', 'bearish')),
    price_level NUMERIC(18,8) NOT NULL CHECK (price_level > 0),
    previous_pivot_price NUMERIC(18,8) NOT NULL CHECK (previous_pivot_price > 0),
    previous_pivot_time TIMESTAMPTZ NOT NULL,
    broken_pivot_price NUMERIC(18,8) NOT NULL CHECK (broken_pivot_price > 0),
    broken_pivot_time TIMESTAMPTZ NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_smc_events_v1 PRIMARY KEY (venue, symbol, timeframe, event_time, event_type, direction)
);

-- Create hypertable
SELECT create_hypertable(
    'smc_events_v1',
    'event_time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_smc_events_v1_symbol_tf_time
    ON smc_events_v1 (symbol, timeframe, event_time DESC);

CREATE INDEX IF NOT EXISTS idx_smc_events_v1_venue_symbol_time
    ON smc_events_v1 (venue, symbol, event_time DESC);

CREATE INDEX IF NOT EXISTS idx_smc_events_v1_choch
    ON smc_events_v1 (symbol, timeframe, event_time DESC)
    WHERE event_type = 'CHOCH';

CREATE INDEX IF NOT EXISTS idx_smc_events_v1_bos
    ON smc_events_v1 (symbol, timeframe, event_time DESC)
    WHERE event_type = 'BOS';

-- Compression
ALTER TABLE smc_events_v1 SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, timeframe',
    timescaledb.compress_orderby = 'event_time DESC'
);

SELECT add_compression_policy(
    'smc_events_v1',
    compress_after => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Retention
SELECT add_retention_policy(
    'smc_events_v1',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON smc_events_v1 TO trading_user;
