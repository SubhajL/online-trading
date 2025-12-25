-- 021_equity_samples.sql: Equity curve samples (backend-owned)

CREATE TABLE IF NOT EXISTS equity_samples (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    equity NUMERIC(18,8) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_equity_samples PRIMARY KEY (id)
);

-- Convert to hypertable for time-series efficiency
SELECT create_hypertable('equity_samples', 'timestamp', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_equity_samples_timestamp
    ON equity_samples (timestamp DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON equity_samples TO trading_user;

