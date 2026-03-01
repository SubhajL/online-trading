-- 010_decisions.sql: Trading decisions emitted by the pipeline

CREATE TABLE IF NOT EXISTS trading_decisions (
    decision_id UUID NOT NULL DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    entry_price NUMERIC(20,8),
    quantity NUMERIC(20,8),
    order_type TEXT,
    stop_loss NUMERIC(20,8),
    take_profit NUMERIC(20,8),
    confidence NUMERIC(4,3) NOT NULL,
    reasoning TEXT NOT NULL,
    risk_reward_ratio NUMERIC(10,4),
    market_regime TEXT,
    news_sentiment TEXT,
    funding_rate_impact NUMERIC(10,6),
    volatility_filter BOOLEAN,
    venue TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_trading_decisions PRIMARY KEY (decision_id)
);

CREATE INDEX IF NOT EXISTS idx_trading_decisions_symbol_timestamp
    ON trading_decisions (symbol, timestamp DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON trading_decisions TO trading_user;
