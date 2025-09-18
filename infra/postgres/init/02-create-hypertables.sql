-- Create tables for time-series data with TimescaleDB

-- Candles table for OHLCV data
CREATE TABLE IF NOT EXISTS candles (
    time TIMESTAMPTZ NOT NULL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume NUMERIC NOT NULL,
    quote_volume NUMERIC,
    trade_count INTEGER,
    taker_buy_volume NUMERIC,
    taker_buy_quote_volume NUMERIC,
    UNIQUE (venue, symbol, timeframe, time)
);

-- Trades table for individual trade data
CREATE TABLE IF NOT EXISTS trades (
    time TIMESTAMPTZ NOT NULL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_id BIGINT NOT NULL,
    price NUMERIC NOT NULL,
    quantity NUMERIC NOT NULL,
    quote_quantity NUMERIC NOT NULL,
    is_buyer_maker BOOLEAN NOT NULL,
    UNIQUE (venue, symbol, trade_id)
);

-- Order updates table for tracking order state changes
CREATE TABLE IF NOT EXISTS order_updates (
    time TIMESTAMPTZ NOT NULL,
    venue TEXT NOT NULL,
    order_id TEXT NOT NULL,
    client_order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    status TEXT NOT NULL,
    price NUMERIC,
    quantity NUMERIC NOT NULL,
    filled_quantity NUMERIC DEFAULT 0,
    time_in_force TEXT,
    update_type TEXT NOT NULL,
    UNIQUE (venue, order_id, time)
);

-- Positions table for tracking current positions
CREATE TABLE IF NOT EXISTS positions (
    time TIMESTAMPTZ NOT NULL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    entry_price NUMERIC NOT NULL,
    mark_price NUMERIC,
    unrealized_pnl NUMERIC,
    realized_pnl NUMERIC DEFAULT 0,
    margin_used NUMERIC,
    liquidation_price NUMERIC
);

-- Convert tables to hypertables
SELECT create_hypertable('candles', 'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

SELECT create_hypertable('trades', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

SELECT create_hypertable('order_updates', 'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

SELECT create_hypertable('positions', 'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_candles_symbol_time
    ON candles (symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_candles_venue_symbol_timeframe_time
    ON candles (venue, symbol, timeframe, time DESC);

CREATE INDEX IF NOT EXISTS idx_trades_symbol_time
    ON trades (symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_trades_venue_symbol_time
    ON trades (venue, symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_order_updates_symbol_time
    ON order_updates (symbol, time DESC);

CREATE INDEX IF NOT EXISTS idx_order_updates_order_id
    ON order_updates (order_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_positions_symbol_time
    ON positions (symbol, time DESC);

-- Create continuous aggregates for different timeframes
-- 5-minute candles from 1-minute data
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_5m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS time,
    venue,
    symbol,
    '5m' AS timeframe,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trade_count) AS trade_count
FROM candles
WHERE timeframe = '1m'
GROUP BY time_bucket('5 minutes', time), venue, symbol;

-- 15-minute candles
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_15m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', time) AS time,
    venue,
    symbol,
    '15m' AS timeframe,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trade_count) AS trade_count
FROM candles
WHERE timeframe = '1m'
GROUP BY time_bucket('15 minutes', time), venue, symbol;

-- 1-hour candles
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS time,
    venue,
    symbol,
    '1h' AS timeframe,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trade_count) AS trade_count
FROM candles
WHERE timeframe = '1m'
GROUP BY time_bucket('1 hour', time), venue, symbol;

-- 4-hour candles
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_4h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('4 hours', time) AS time,
    venue,
    symbol,
    '4h' AS timeframe,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trade_count) AS trade_count
FROM candles
WHERE timeframe = '1m'
GROUP BY time_bucket('4 hours', time), venue, symbol;

-- Daily candles
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS time,
    venue,
    symbol,
    '1d' AS timeframe,
    first(open, time) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, time) AS close,
    sum(volume) AS volume,
    sum(quote_volume) AS quote_volume,
    sum(trade_count) AS trade_count
FROM candles
WHERE timeframe = '1m'
GROUP BY time_bucket('1 day', time), venue, symbol;

-- Add refresh policies for continuous aggregates
SELECT add_continuous_aggregate_policy('candles_5m',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('candles_15m',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('candles_1h',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('candles_4h',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '4 hours',
    if_not_exists => TRUE
);

SELECT add_continuous_aggregate_policy('candles_1d',
    start_offset => INTERVAL '2 days',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Set compression policies for older data
ALTER TABLE candles SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, timeframe',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('candles',
    compress_after => INTERVAL '7 days',
    if_not_exists => TRUE
);

ALTER TABLE trades SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol',
    timescaledb.compress_orderby = 'time DESC, trade_id'
);

SELECT add_compression_policy('trades',
    compress_after => INTERVAL '30 days',
    if_not_exists => TRUE
);

ALTER TABLE order_updates SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol',
    timescaledb.compress_orderby = 'time DESC, order_id'
);

SELECT add_compression_policy('order_updates',
    compress_after => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Set data retention policies
SELECT add_retention_policy('candles',
    drop_after => INTERVAL '1 year',
    if_not_exists => TRUE
);

SELECT add_retention_policy('trades',
    drop_after => INTERVAL '1 year',
    if_not_exists => TRUE
);

SELECT add_retention_policy('order_updates',
    drop_after => INTERVAL '1 year',
    if_not_exists => TRUE
);

SELECT add_retention_policy('positions',
    drop_after => INTERVAL '1 year',
    if_not_exists => TRUE
);

-- Create helper functions for data management
CREATE OR REPLACE FUNCTION refresh_all_continuous_aggregates()
RETURNS void AS $$
BEGIN
    CALL refresh_continuous_aggregate('candles_5m', NULL, NULL);
    CALL refresh_continuous_aggregate('candles_15m', NULL, NULL);
    CALL refresh_continuous_aggregate('candles_1h', NULL, NULL);
    CALL refresh_continuous_aggregate('candles_4h', NULL, NULL);
    CALL refresh_continuous_aggregate('candles_1d', NULL, NULL);
END;
$$ LANGUAGE plpgsql;

-- Grant permissions to trading_user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO trading_user;