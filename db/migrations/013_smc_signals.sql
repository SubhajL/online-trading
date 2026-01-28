-- 013_smc_signals.sql: SMC signal persistence for benchmark/validation workflows

CREATE TABLE IF NOT EXISTS smc_signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    direction VARCHAR(4) NOT NULL,
    entry_price NUMERIC(20,8) NOT NULL,
    stop_loss NUMERIC(20,8),
    take_profit NUMERIC(20,8),
    confidence NUMERIC(4,3) NOT NULL,
    reasoning TEXT,
    zone_id UUID,
    zone_type VARCHAR(30),
    zone_top_price NUMERIC(20,8),
    zone_bottom_price NUMERIC(20,8),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_smc_signals_symbol_timestamp
    ON smc_signals (symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_smc_signals_active_timestamp
    ON smc_signals (is_active, timestamp DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON smc_signals TO trading_user;

