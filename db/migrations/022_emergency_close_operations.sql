-- 022_emergency_close_operations.sql: Idempotent emergency-close operations

CREATE TABLE IF NOT EXISTS emergency_close_operations (
    idempotency_key TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('ALL', 'SPOT', 'FUTURES')),
    stop_engine BOOLEAN NOT NULL DEFAULT FALSE,
    request_signature TEXT NOT NULL,
    response JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_emergency_close_operations PRIMARY KEY (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_emergency_close_operations_created_at
    ON emergency_close_operations (created_at DESC);

DROP TRIGGER IF EXISTS update_emergency_close_operations_updated_at ON emergency_close_operations;
CREATE TRIGGER update_emergency_close_operations_updated_at
    BEFORE UPDATE ON emergency_close_operations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

GRANT SELECT, INSERT, UPDATE, DELETE ON emergency_close_operations TO trading_user;

