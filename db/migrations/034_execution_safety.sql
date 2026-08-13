-- 034_execution_safety.sql: durable execution identities and safety state.

ALTER TABLE brackets
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS request_hash TEXT;

UPDATE brackets
SET idempotency_key = 'legacy:' || entry_client_order_id
WHERE idempotency_key IS NULL;

UPDATE brackets
SET request_hash = repeat('0', 64)
WHERE request_hash IS NULL;

ALTER TABLE brackets
    ALTER COLUMN idempotency_key SET NOT NULL,
    ALTER COLUMN request_hash SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_brackets_idempotency_key
    ON brackets (venue, idempotency_key);

ALTER TABLE brackets
    DROP CONSTRAINT IF EXISTS ck_brackets_request_hash_length;

ALTER TABLE brackets
    ADD CONSTRAINT ck_brackets_request_hash_length CHECK (length(request_hash) = 64);

CREATE TABLE IF NOT EXISTS execution_intents (
    idempotency_key TEXT NOT NULL,
    decision_id UUID NOT NULL,
    signal_id TEXT,
    venue TEXT NOT NULL CHECK (venue IN ('SPOT', 'USD_M')),
    symbol TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    request_payload JSONB NOT NULL,
    response_payload JSONB,
    state TEXT NOT NULL CHECK (
        state IN ('PREPARED', 'SUBMITTING', 'ACKNOWLEDGED', 'REJECTED', 'AMBIGUOUS')
    ),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_execution_intents PRIMARY KEY (venue, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_execution_intents_state
    ON execution_intents (state, updated_at);

CREATE TABLE IF NOT EXISTS execution_control (
    scope TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('RUNNING', 'HALTED')),
    generation BIGINT NOT NULL CHECK (generation > 0),
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_execution_control PRIMARY KEY (scope),
    CONSTRAINT uq_execution_control_idempotency_key UNIQUE (idempotency_key)
);

INSERT INTO execution_control (
    scope, state, generation, reason, requested_by, idempotency_key
) VALUES (
    'GLOBAL', 'HALTED', 1, 'Deployment starts halted', 'migration', 'migration-034-default-halt'
)
ON CONFLICT (scope) DO NOTHING;

CREATE TABLE IF NOT EXISTS execution_control_requests (
    idempotency_key TEXT NOT NULL,
    scope TEXT NOT NULL,
    target_state TEXT NOT NULL CHECK (target_state IN ('RUNNING', 'HALTED')),
    generation BIGINT NOT NULL CHECK (generation > 0),
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_execution_control_requests PRIMARY KEY (idempotency_key)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON execution_intents TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON execution_control TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON execution_control_requests TO trading_user;
