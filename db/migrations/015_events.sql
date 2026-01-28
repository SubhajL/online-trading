-- 015_events.sql: Immutable event log for audit/debugging (Timescale hypertable)

CREATE TABLE IF NOT EXISTS events (
    id UUID DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    timeframe VARCHAR(10),
    event_data JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (timestamp, id)
);

SELECT create_hypertable('events', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_events_type_timestamp
    ON events (event_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_events_symbol_timestamp
    ON events (symbol, timestamp DESC)
    WHERE symbol IS NOT NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON events TO trading_user;

