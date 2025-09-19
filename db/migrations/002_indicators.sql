-- 002_indicators.sql: Technical indicators (EMA, RSI, MACD, ATR, BB)

CREATE TABLE IF NOT EXISTS indicators (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    -- Moving Averages
    ema_9 NUMERIC(18,8),
    ema_21 NUMERIC(18,8),
    ema_50 NUMERIC(18,8),
    ema_200 NUMERIC(18,8),
    -- RSI
    rsi_14 NUMERIC(5,2) CHECK (rsi_14 IS NULL OR (rsi_14 >= 0 AND rsi_14 <= 100)),
    -- MACD
    macd_line NUMERIC(18,8),
    macd_signal NUMERIC(18,8),
    macd_histogram NUMERIC(18,8),
    -- ATR
    atr_14 NUMERIC(18,8) CHECK (atr_14 IS NULL OR atr_14 >= 0),
    -- Bollinger Bands
    bb_upper NUMERIC(18,8),
    bb_middle NUMERIC(18,8),
    bb_lower NUMERIC(18,8),
    bb_width NUMERIC(18,8) CHECK (bb_width IS NULL OR bb_width >= 0),
    bb_percent NUMERIC(5,2),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_indicators PRIMARY KEY (venue, symbol, timeframe, timestamp),
    CONSTRAINT chk_bb_order CHECK (
        (bb_upper IS NULL AND bb_middle IS NULL AND bb_lower IS NULL) OR
        (bb_upper >= bb_middle AND bb_middle >= bb_lower)
    )
);

-- Create hypertable
SELECT create_hypertable(
    'indicators',
    'timestamp',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Create indexes as specified in PRD
CREATE INDEX IF NOT EXISTS idx_indicators_symbol_tf_time
    ON indicators (symbol, timeframe, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_indicators_venue_symbol_time
    ON indicators (venue, symbol, timestamp DESC);

-- Index for RSI extremes (oversold/overbought)
CREATE INDEX IF NOT EXISTS idx_indicators_rsi_extremes
    ON indicators (symbol, timeframe, timestamp DESC)
    WHERE rsi_14 <= 30 OR rsi_14 >= 70;

-- Index for MACD crossovers
CREATE INDEX IF NOT EXISTS idx_indicators_macd_cross
    ON indicators (symbol, timeframe, timestamp DESC)
    WHERE ABS(macd_line - macd_signal) < 0.0001;

-- Add updated_at trigger
DROP TRIGGER IF EXISTS update_indicators_updated_at ON indicators;
CREATE TRIGGER update_indicators_updated_at
    BEFORE UPDATE ON indicators
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Set compression policy
ALTER TABLE indicators SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, timeframe',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy
SELECT add_compression_policy(
    'indicators',
    compress_after => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Add retention policy
SELECT add_retention_policy(
    'indicators',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON indicators TO trading_user;