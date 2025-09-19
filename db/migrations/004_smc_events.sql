-- 004_smc_events.sql: Smart Money Concepts structure breaks (CHOCH, BOS)

CREATE TABLE IF NOT EXISTS smc_events (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    structure_type TEXT NOT NULL CHECK (structure_type IN ('HH', 'HL', 'LH', 'LL', 'EH', 'EL')),
    price NUMERIC(18,8) NOT NULL CHECK (price > 0),
    previous_structure TEXT CHECK (previous_structure IN ('HH', 'HL', 'LH', 'LL', 'EH', 'EL')),
    trend_direction TEXT CHECK (trend_direction IN ('bullish', 'bearish', 'neutral')),
    event_type TEXT NOT NULL CHECK (event_type IN ('CHOCH', 'BOS', 'STRUCTURE')),
    break_price NUMERIC(18,8) CHECK (break_price > 0),
    volume_at_break NUMERIC(18,8) CHECK (volume_at_break >= 0),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_smc_events PRIMARY KEY (venue, symbol, timeframe, timestamp, structure_type)
);

-- Create hypertable
SELECT create_hypertable(
    'smc_events',
    'timestamp',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Create indexes as specified in PRD
CREATE INDEX IF NOT EXISTS idx_smc_events_symbol_tf_time
    ON smc_events (symbol, timeframe, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_smc_events_venue_symbol_time
    ON smc_events (venue, symbol, timestamp DESC);

-- Index for CHOCH (Change of Character) events
CREATE INDEX IF NOT EXISTS idx_smc_events_choch
    ON smc_events (symbol, timeframe, timestamp DESC)
    WHERE event_type = 'CHOCH';

-- Index for BOS (Break of Structure) events
CREATE INDEX IF NOT EXISTS idx_smc_events_bos
    ON smc_events (symbol, timeframe, timestamp DESC)
    WHERE event_type = 'BOS';

-- Index for trend changes
CREATE INDEX IF NOT EXISTS idx_smc_events_trend_change
    ON smc_events (symbol, timeframe, timestamp DESC)
    WHERE previous_structure IS NOT NULL AND
          ((previous_structure IN ('HH', 'HL') AND structure_type IN ('LH', 'LL')) OR
           (previous_structure IN ('LH', 'LL') AND structure_type IN ('HH', 'HL')));

-- Set compression policy
ALTER TABLE smc_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, timeframe',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy
SELECT add_compression_policy(
    'smc_events',
    compress_after => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Add retention policy
SELECT add_retention_policy(
    'smc_events',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON smc_events TO trading_user;