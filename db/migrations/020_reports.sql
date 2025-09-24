-- Migration 020: Reports and Paper Trading Tables
-- Add backtesting reports and paper trading infrastructure

BEGIN;

-- Reports table for backtest/WFO runs
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type VARCHAR(20) NOT NULL CHECK (run_type IN ('backtest', 'wfo', 'paper')),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    config_hash VARCHAR(64) NOT NULL,
    git_sha VARCHAR(40) NOT NULL,

    -- Performance metrics
    total_pnl DECIMAL(18, 8),
    total_pnl_pct DECIMAL(10, 4),
    profit_factor DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    calmar_ratio DECIMAL(10, 4),
    max_drawdown_pct DECIMAL(10, 4),
    max_drawdown_duration_hours INTEGER,

    -- Trade statistics
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    hit_rate_pct DECIMAL(10, 4),
    avg_win_r DECIMAL(10, 4),
    avg_loss_r DECIMAL(10, 4),
    avg_r DECIMAL(10, 4),
    largest_win_r DECIMAL(10, 4),
    largest_loss_r DECIMAL(10, 4),

    -- Exposure and costs
    exposure_pct DECIMAL(10, 4),
    total_fees DECIMAL(18, 8),
    total_slippage DECIMAL(18, 8),
    total_funding DECIMAL(18, 8),

    -- Metadata
    runtime_ms INTEGER,
    artifacts_path TEXT,
    s3_bucket TEXT,
    s3_key TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Individual trade records
CREATE TABLE IF NOT EXISTS report_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,

    -- Trade identification
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('long', 'short')),
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ,

    -- Price and size
    entry_price DECIMAL(18, 8) NOT NULL,
    exit_price DECIMAL(18, 8),
    size DECIMAL(18, 8) NOT NULL,

    -- PnL breakdown
    gross_pnl DECIMAL(18, 8),
    gross_pnl_r DECIMAL(10, 4),  -- in R units
    fees DECIMAL(18, 8) DEFAULT 0,
    slippage DECIMAL(18, 8) DEFAULT 0,
    funding DECIMAL(18, 8) DEFAULT 0,
    net_pnl DECIMAL(18, 8),
    net_pnl_r DECIMAL(10, 4),

    -- Trade metadata
    stop_loss DECIMAL(18, 8),
    take_profits JSONB,  -- [{price: X, size: Y, filled: bool}]
    exit_reason VARCHAR(20) CHECK (exit_reason IN ('tp', 'sl', 'manual', 'timeout')),
    duration_minutes INTEGER,

    -- Signal context
    signal_type VARCHAR(50),
    signal_confidence DECIMAL(5, 4),
    regime VARCHAR(20),
    market_conditions JSONB,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Paper trading orders
CREATE TABLE IF NOT EXISTS paper_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_order_id VARCHAR(50) UNIQUE NOT NULL,

    -- Order details
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    type VARCHAR(20) NOT NULL CHECK (type IN ('MARKET', 'LIMIT', 'STOP_MARKET', 'STOP_LIMIT')),
    quantity DECIMAL(18, 8) NOT NULL,
    price DECIMAL(18, 8),
    stop_price DECIMAL(18, 8),

    -- Order state
    status VARCHAR(20) NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')),
    filled_quantity DECIMAL(18, 8) DEFAULT 0,
    remaining_quantity DECIMAL(18, 8),

    -- Time and execution
    order_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fill_time TIMESTAMPTZ,
    last_fill_time TIMESTAMPTZ,

    -- Special flags
    reduce_only BOOLEAN DEFAULT FALSE,
    time_in_force VARCHAR(10) DEFAULT 'GTC' CHECK (time_in_force IN ('GTC', 'IOC', 'FOK')),

    -- Paper trading specific
    paper_session_id UUID,  -- Group related orders

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Paper trading positions
CREATE TABLE IF NOT EXISTS paper_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,

    -- Position state
    side VARCHAR(10) CHECK (side IN ('LONG', 'SHORT')),
    quantity DECIMAL(18, 8) NOT NULL DEFAULT 0,
    entry_price DECIMAL(18, 8),
    mark_price DECIMAL(18, 8),

    -- PnL tracking
    unrealized_pnl DECIMAL(18, 8) DEFAULT 0,
    realized_pnl DECIMAL(18, 8) DEFAULT 0,
    total_fees DECIMAL(18, 8) DEFAULT 0,
    total_funding DECIMAL(18, 8) DEFAULT 0,

    -- Risk management
    stop_loss DECIMAL(18, 8),
    take_profit DECIMAL(18, 8),
    breakeven_moved BOOLEAN DEFAULT FALSE,
    trail_price DECIMAL(18, 8),
    trail_offset DECIMAL(18, 8),

    -- Metadata
    paper_session_id UUID,
    opened_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_paper_position UNIQUE (symbol, paper_session_id)
);

-- Paper trading fills
CREATE TABLE IF NOT EXISTS paper_fills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES paper_orders(id),
    position_id UUID REFERENCES paper_positions(id),

    -- Fill details
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity DECIMAL(18, 8) NOT NULL,
    price DECIMAL(18, 8) NOT NULL,

    -- Costs
    fee DECIMAL(18, 8) DEFAULT 0,
    fee_currency VARCHAR(10) DEFAULT 'USDT',
    slippage DECIMAL(18, 8) DEFAULT 0,

    -- Execution context
    fill_time TIMESTAMPTZ NOT NULL,
    fill_reason VARCHAR(20) CHECK (fill_reason IN ('market', 'limit', 'stop', 'liquidation')),

    -- Market data context
    candle_open_time TIMESTAMPTZ,
    candle_high DECIMAL(18, 8),
    candle_low DECIMAL(18, 8),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_reports_symbol_tf ON reports(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_reports_run_type ON reports(run_type);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_report_trades_report_id ON report_trades(report_id);
CREATE INDEX IF NOT EXISTS idx_report_trades_symbol ON report_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_report_trades_entry_time ON report_trades(entry_time);

CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON paper_orders(symbol);
CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders(status);
CREATE INDEX IF NOT EXISTS idx_paper_orders_session ON paper_orders(paper_session_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_client_id ON paper_orders(client_order_id);

CREATE INDEX IF NOT EXISTS idx_paper_positions_symbol ON paper_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_paper_positions_session ON paper_positions(paper_session_id);

CREATE INDEX IF NOT EXISTS idx_paper_fills_order_id ON paper_fills(order_id);
CREATE INDEX IF NOT EXISTS idx_paper_fills_symbol ON paper_fills(symbol);
CREATE INDEX IF NOT EXISTS idx_paper_fills_time ON paper_fills(fill_time);

COMMIT;