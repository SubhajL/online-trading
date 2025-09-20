-- 001_candles.sql: OHLCV candle data with TimescaleDB hypertable

-- Enable TimescaleDB extension if not already enabled
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create candles table
CREATE TABLE IF NOT EXISTS candles (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time TIMESTAMPTZ NOT NULL,
    close_time TIMESTAMPTZ NOT NULL,
    open_price NUMERIC(18,8) NOT NULL CHECK (open_price > 0),
    high_price NUMERIC(18,8) NOT NULL CHECK (high_price > 0),
    low_price NUMERIC(18,8) NOT NULL CHECK (low_price > 0),
    close_price NUMERIC(18,8) NOT NULL CHECK (close_price > 0),
    volume NUMERIC(18,8) NOT NULL CHECK (volume >= 0),
    quote_volume NUMERIC(18,8) NOT NULL CHECK (quote_volume >= 0),
    trades INTEGER NOT NULL CHECK (trades >= 0),
    taker_buy_base_volume NUMERIC(18,8) NOT NULL CHECK (taker_buy_base_volume >= 0),
    taker_buy_quote_volume NUMERIC(18,8) NOT NULL CHECK (taker_buy_quote_volume >= 0),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_candles PRIMARY KEY (venue, symbol, timeframe, open_time),
    CONSTRAINT chk_high_low CHECK (high_price >= low_price),
    CONSTRAINT chk_high_open_close CHECK (high_price >= open_price AND high_price >= close_price),
    CONSTRAINT chk_low_open_close CHECK (low_price <= open_price AND low_price <= close_price),
    CONSTRAINT chk_time_order CHECK (close_time > open_time)
);

-- Create hypertable on open_time
SELECT create_hypertable(
    'candles',
    'open_time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Create indexes as specified in PRD
CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_time
    ON candles (symbol, timeframe, open_time DESC);

CREATE INDEX IF NOT EXISTS idx_candles_venue_symbol_time
    ON candles (venue, symbol, open_time DESC);

CREATE INDEX IF NOT EXISTS idx_candles_close_time
    ON candles (close_time DESC);

-- Create updated_at trigger function if not exists
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add trigger for updated_at
DROP TRIGGER IF EXISTS update_candles_updated_at ON candles;
CREATE TRIGGER update_candles_updated_at
    BEFORE UPDATE ON candles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Set compression policy for older data
ALTER TABLE candles SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, timeframe',
    timescaledb.compress_orderby = 'open_time DESC'
);

-- Add compression policy (compress data older than 7 days)
SELECT add_compression_policy(
    'candles',
    compress_after => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Add retention policy (optional - keep data for 2 years)
SELECT add_retention_policy(
    'candles',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON candles TO trading_user;