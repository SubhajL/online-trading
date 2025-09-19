-- 007_positions.sql: Current and historical positions

CREATE TABLE IF NOT EXISTS positions (
    position_id UUID NOT NULL DEFAULT gen_random_uuid(),
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    size NUMERIC(18,8) NOT NULL CHECK (size > 0),
    entry_price NUMERIC(18,8) NOT NULL CHECK (entry_price > 0),
    current_price NUMERIC(18,8) NOT NULL CHECK (current_price > 0),
    unrealized_pnl NUMERIC(18,8) NOT NULL,
    realized_pnl NUMERIC(18,8) NOT NULL DEFAULT 0,
    margin_used NUMERIC(18,8) NOT NULL CHECK (margin_used >= 0),
    leverage NUMERIC(5,2) NOT NULL DEFAULT 1 CHECK (leverage >= 1),
    opened_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    stop_loss NUMERIC(18,8) CHECK (stop_loss IS NULL OR stop_loss > 0),
    take_profit NUMERIC(18,8) CHECK (take_profit IS NULL OR take_profit > 0),
    decision_id UUID,
    liquidation_price NUMERIC(18,8) CHECK (liquidation_price IS NULL OR liquidation_price > 0),
    max_drawdown NUMERIC(18,8) DEFAULT 0,
    max_profit NUMERIC(18,8) DEFAULT 0,
    commission_paid NUMERIC(18,8) DEFAULT 0 CHECK (commission_paid >= 0),
    funding_paid NUMERIC(18,8) DEFAULT 0,
    close_reason TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    entry_order_id UUID,
    CONSTRAINT pk_positions PRIMARY KEY (position_id),
    CONSTRAINT uq_positions_active UNIQUE (venue, symbol, is_active) WHERE is_active = TRUE,
    CONSTRAINT chk_pnl_calculation CHECK (
        unrealized_pnl = (current_price - entry_price) * size * CASE WHEN side = 'BUY' THEN 1 ELSE -1 END
    ),
    CONSTRAINT chk_stop_loss_side CHECK (
        stop_loss IS NULL OR
        (side = 'BUY' AND stop_loss < entry_price) OR
        (side = 'SELL' AND stop_loss > entry_price)
    ),
    CONSTRAINT chk_take_profit_side CHECK (
        take_profit IS NULL OR
        (side = 'BUY' AND take_profit > entry_price) OR
        (side = 'SELL' AND take_profit < entry_price)
    ),
    CONSTRAINT chk_closed_timestamp CHECK (
        (closed_at IS NULL AND is_active = TRUE) OR
        (closed_at IS NOT NULL AND is_active = FALSE AND closed_at >= opened_at)
    )
);

-- Create hypertable on opened_at
SELECT create_hypertable(
    'positions',
    'opened_at',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Create indexes as specified in PRD
CREATE INDEX IF NOT EXISTS idx_positions_symbol_opened
    ON positions (symbol, opened_at DESC);

CREATE INDEX IF NOT EXISTS idx_positions_venue_symbol_opened
    ON positions (venue, symbol, opened_at DESC);

-- Index for active positions
CREATE INDEX IF NOT EXISTS idx_positions_active
    ON positions (symbol, opened_at DESC)
    WHERE is_active = TRUE;

-- Index for closed positions
CREATE INDEX IF NOT EXISTS idx_positions_closed
    ON positions (symbol, closed_at DESC)
    WHERE is_active = FALSE;

-- Index for decision tracking
CREATE INDEX IF NOT EXISTS idx_positions_decision_id
    ON positions (decision_id)
    WHERE decision_id IS NOT NULL;

-- Index for entry order tracking
CREATE INDEX IF NOT EXISTS idx_positions_entry_order_id
    ON positions (entry_order_id)
    WHERE entry_order_id IS NOT NULL;

-- Index for profitable positions
CREATE INDEX IF NOT EXISTS idx_positions_profitable
    ON positions (symbol, closed_at DESC)
    WHERE is_active = FALSE AND realized_pnl > 0;

-- Set compression policy
ALTER TABLE positions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, is_active',
    timescaledb.compress_orderby = 'opened_at DESC'
);

-- Add compression policy
SELECT add_compression_policy(
    'positions',
    compress_after => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Add retention policy
SELECT add_retention_policy(
    'positions',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON positions TO trading_user;