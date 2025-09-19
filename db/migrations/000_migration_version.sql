-- 000_migration_version.sql: Migration version tracking table

-- Create schema for migration tracking
CREATE SCHEMA IF NOT EXISTS _migration;

-- Create migration version tracking table
CREATE TABLE IF NOT EXISTS _migration.schema_version (
    id SERIAL PRIMARY KEY,
    version INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_by TEXT NOT NULL DEFAULT CURRENT_USER,
    execution_time_ms INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'applied', 'failed')),
    error_message TEXT,
    rollback_sql TEXT,
    CONSTRAINT unique_version UNIQUE(version)
);

-- Create index on version for fast lookups
CREATE INDEX IF NOT EXISTS idx_migration_version ON _migration.schema_version(version);
CREATE INDEX IF NOT EXISTS idx_migration_status ON _migration.schema_version(status);
CREATE INDEX IF NOT EXISTS idx_migration_applied_at ON _migration.schema_version(applied_at DESC);

-- Create migration history table for audit trail
CREATE TABLE IF NOT EXISTS _migration.schema_history (
    id SERIAL PRIMARY KEY,
    version INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('apply', 'rollback', 'skip')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    error_message TEXT,
    metadata JSONB
);

-- Create function to record migration start
CREATE OR REPLACE FUNCTION _migration.record_migration_start(
    p_version INTEGER,
    p_action TEXT
) RETURNS INTEGER AS $$
DECLARE
    v_history_id INTEGER;
BEGIN
    INSERT INTO _migration.schema_history (version, action, status)
    VALUES (p_version, p_action, 'running')
    RETURNING id INTO v_history_id;

    RETURN v_history_id;
END;
$$ LANGUAGE plpgsql;

-- Create function to record migration completion
CREATE OR REPLACE FUNCTION _migration.record_migration_complete(
    p_history_id INTEGER,
    p_status TEXT,
    p_error_message TEXT DEFAULT NULL
) RETURNS VOID AS $$
DECLARE
    v_started_at TIMESTAMPTZ;
    v_duration_ms INTEGER;
BEGIN
    SELECT started_at INTO v_started_at
    FROM _migration.schema_history
    WHERE id = p_history_id;

    v_duration_ms := EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - v_started_at)) * 1000;

    UPDATE _migration.schema_history
    SET completed_at = CURRENT_TIMESTAMP,
        duration_ms = v_duration_ms,
        status = p_status,
        error_message = p_error_message
    WHERE id = p_history_id;
END;
$$ LANGUAGE plpgsql;

-- Create view for current migration status
CREATE OR REPLACE VIEW _migration.current_version AS
SELECT
    COALESCE(MAX(version), 0) AS version,
    COUNT(*) AS total_migrations,
    COUNT(CASE WHEN status = 'applied' THEN 1 END) AS applied_migrations,
    COUNT(CASE WHEN status = 'failed' THEN 1 END) AS failed_migrations
FROM _migration.schema_version
WHERE status = 'applied';

-- Grant permissions
GRANT USAGE ON SCHEMA _migration TO trading_user;
GRANT SELECT ON ALL TABLES IN SCHEMA _migration TO trading_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA _migration TO trading_user;