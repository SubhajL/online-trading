-- 014_external_telegram_tables.sql: Captain benchmark ingestion + validations

CREATE TABLE IF NOT EXISTS external_telegram_messages (
    source VARCHAR(50) NOT NULL,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    grouped_id BIGINT,
    timestamp TIMESTAMPTZ NOT NULL,
    text TEXT,
    has_photo BOOLEAN NOT NULL DEFAULT FALSE,
    photo_path TEXT,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS external_telegram_signals (
    source VARCHAR(50) NOT NULL,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    kind VARCHAR(30) NOT NULL,
    strategy VARCHAR(50),
    symbol VARCHAR(20),
    timeframe VARCHAR(10),
    direction VARCHAR(4),
    entry_price DECIMAL(20,8),
    stop_loss DECIMAL(20,8),
    take_profits JSONB,
    parse_confidence DECIMAL(4,3),
    parse_sources JSONB,
    ocr_raw_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS external_telegram_signal_validations (
    source VARCHAR(50) NOT NULL,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    internal_kind VARCHAR(30),
    internal_id UUID,
    internal_timestamp TIMESTAMPTZ,
    score DECIMAL(4,3) NOT NULL,
    breakdown JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS benchmark_validation_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    validated_at TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT,
    snapshot_version INT NOT NULL DEFAULT 1,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_snapshot_key UNIQUE (
        source, chat_id, message_id, validated_at, snapshot_version
    )
);

CREATE INDEX IF NOT EXISTS idx_bvs_symbol_time
    ON benchmark_validation_snapshots (symbol, validated_at DESC);

CREATE INDEX IF NOT EXISTS idx_bvs_source_time
    ON benchmark_validation_snapshots (source, validated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ext_tg_messages_timestamp
    ON external_telegram_messages (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ext_tg_signals_symbol_timeframe_timestamp
    ON external_telegram_signals (symbol, timeframe, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ext_tg_validations_timestamp
    ON external_telegram_signal_validations (timestamp DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON external_telegram_messages TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON external_telegram_signals TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON external_telegram_signal_validations TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON benchmark_validation_snapshots TO trading_user;

