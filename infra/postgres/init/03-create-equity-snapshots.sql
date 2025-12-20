-- Create equity_snapshots table for dashboard monitoring
-- Stores periodic snapshots of account equity for drawdown tracking and P&L history

CREATE TABLE IF NOT EXISTS equity_snapshots (
    time TIMESTAMPTZ NOT NULL,
    venue TEXT NOT NULL,
    -- Account totals
    total_equity NUMERIC NOT NULL,
    available_margin NUMERIC NOT NULL,
    margin_used NUMERIC DEFAULT 0,
    margin_usage_pct NUMERIC DEFAULT 0,
    -- Position exposure
    total_notional NUMERIC DEFAULT 0,
    spot_notional NUMERIC DEFAULT 0,
    futures_notional NUMERIC DEFAULT 0,
    position_count INTEGER DEFAULT 0,
    spot_position_count INTEGER DEFAULT 0,
    futures_position_count INTEGER DEFAULT 0,
    -- P&L metrics
    unrealized_pnl NUMERIC DEFAULT 0,
    realized_pnl_today NUMERIC DEFAULT 0,
    realized_pnl_total NUMERIC DEFAULT 0,
    -- Drawdown tracking
    peak_equity NUMERIC NOT NULL,
    drawdown_pct NUMERIC DEFAULT 0,
    max_drawdown_pct NUMERIC DEFAULT 0,
    -- Trigger source
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('TIMER', 'POSITION_CHANGE', 'MANUAL')),
    -- Unique constraint per venue per timestamp
    UNIQUE (venue, time)
);

-- Convert to hypertable with 1-day chunks (equity snapshots are less frequent)
SELECT create_hypertable('equity_snapshots', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_equity_snapshots_venue_time
    ON equity_snapshots (venue, time DESC);

CREATE INDEX IF NOT EXISTS idx_equity_snapshots_drawdown
    ON equity_snapshots (venue, drawdown_pct DESC, time DESC);

-- Compression policy for older snapshots (compress after 7 days)
ALTER TABLE equity_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('equity_snapshots',
    compress_after => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Retention policy (keep 1 year of snapshots)
SELECT add_retention_policy('equity_snapshots',
    drop_after => INTERVAL '1 year',
    if_not_exists => TRUE
);

-- Grant permissions to trading_user
GRANT ALL PRIVILEGES ON equity_snapshots TO trading_user;

-- Create helper function to get latest snapshot per venue
CREATE OR REPLACE FUNCTION get_latest_equity_snapshot(p_venue TEXT)
RETURNS TABLE (
    time TIMESTAMPTZ,
    venue TEXT,
    total_equity NUMERIC,
    available_margin NUMERIC,
    margin_usage_pct NUMERIC,
    total_notional NUMERIC,
    unrealized_pnl NUMERIC,
    realized_pnl_today NUMERIC,
    drawdown_pct NUMERIC,
    max_drawdown_pct NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        es.time,
        es.venue,
        es.total_equity,
        es.available_margin,
        es.margin_usage_pct,
        es.total_notional,
        es.unrealized_pnl,
        es.realized_pnl_today,
        es.drawdown_pct,
        es.max_drawdown_pct
    FROM equity_snapshots es
    WHERE es.venue = p_venue
    ORDER BY es.time DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Create function to get equity curve for a time range
CREATE OR REPLACE FUNCTION get_equity_curve(
    p_venue TEXT,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS TABLE (
    time TIMESTAMPTZ,
    total_equity NUMERIC,
    drawdown_pct NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        es.time,
        es.total_equity,
        es.drawdown_pct
    FROM equity_snapshots es
    WHERE es.venue = p_venue
      AND es.time >= p_start_time
      AND es.time <= p_end_time
    ORDER BY es.time ASC;
END;
$$ LANGUAGE plpgsql;

-- Create function to calculate max drawdown for a period
CREATE OR REPLACE FUNCTION calculate_period_max_drawdown(
    p_venue TEXT,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS NUMERIC AS $$
DECLARE
    v_max_drawdown NUMERIC;
BEGIN
    SELECT MAX(drawdown_pct) INTO v_max_drawdown
    FROM equity_snapshots
    WHERE venue = p_venue
      AND time >= p_start_time
      AND time <= p_end_time;

    RETURN COALESCE(v_max_drawdown, 0);
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION get_latest_equity_snapshot(TEXT) TO trading_user;
GRANT EXECUTE ON FUNCTION get_equity_curve(TEXT, TIMESTAMPTZ, TIMESTAMPTZ) TO trading_user;
GRANT EXECUTE ON FUNCTION calculate_period_max_drawdown(TEXT, TIMESTAMPTZ, TIMESTAMPTZ) TO trading_user;
