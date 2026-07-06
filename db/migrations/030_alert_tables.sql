DO $$
BEGIN
    CREATE TYPE alerts_type_enum AS ENUM ('order', 'position', 'decision', 'smc', 'error', 'info');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE alerts_priority_enum AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type alerts_type_enum NOT NULL,
    priority alerts_priority_enum NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at
    ON alerts (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_read_created_at
    ON alerts (read, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_type_created_at
    ON alerts (type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_priority_created_at
    ON alerts (priority, created_at DESC);

CREATE TABLE IF NOT EXISTS alert_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id VARCHAR(255) NOT NULL UNIQUE,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    image_path TEXT NOT NULL,
    meta JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_snapshots_signal_id
    ON alert_snapshots (signal_id);

CREATE INDEX IF NOT EXISTS idx_alert_snapshots_symbol_created_at
    ON alert_snapshots (symbol, created_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON alerts TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON alert_snapshots TO trading_user;
