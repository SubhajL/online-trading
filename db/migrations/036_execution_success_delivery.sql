CREATE TABLE IF NOT EXISTS execution_success_deliveries (
    venue TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    delivery_kind TEXT NOT NULL
        CHECK (delivery_kind IN ('SNAPSHOT', 'ORDER_PLACED')),
    delivery_payload JSONB,
    state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING', 'DELIVERING', 'DELIVERED')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_token TEXT,
    lease_expires_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMPTZ,
    CONSTRAINT pk_execution_success_deliveries
        PRIMARY KEY (venue, idempotency_key, delivery_kind),
    CONSTRAINT fk_execution_success_deliveries_intent
        FOREIGN KEY (venue, idempotency_key)
        REFERENCES execution_intents (venue, idempotency_key)
        ON DELETE CASCADE,
    CONSTRAINT chk_execution_success_delivery_lease
        CHECK (
            (state = 'DELIVERING'
                AND lease_token IS NOT NULL
                AND lease_expires_at IS NOT NULL)
            OR (state IN ('PENDING', 'DELIVERED')
                AND lease_token IS NULL
                AND lease_expires_at IS NULL)
        ),
    CONSTRAINT chk_execution_success_delivery_delivered_at
        CHECK (
            (state = 'DELIVERED' AND delivered_at IS NOT NULL)
            OR (state IN ('PENDING', 'DELIVERING') AND delivered_at IS NULL)
        ),
    CONSTRAINT chk_execution_success_delivery_payload
        CHECK (
            (state IN ('PENDING', 'DELIVERING') AND delivery_payload IS NOT NULL)
            OR state = 'DELIVERED'
        )
);

ALTER TABLE execution_success_deliveries
    ADD COLUMN IF NOT EXISTS delivery_payload JSONB;

ALTER TABLE execution_success_deliveries
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'execution_success_deliveries'::regclass
          AND conname = 'chk_execution_success_delivery_payload'
    ) THEN
        ALTER TABLE execution_success_deliveries
            ADD CONSTRAINT chk_execution_success_delivery_payload
            CHECK (
                (state IN ('PENDING', 'DELIVERING') AND delivery_payload IS NOT NULL)
                OR state = 'DELIVERED'
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_execution_success_deliveries_claim
    ON execution_success_deliveries (state, lease_expires_at, updated_at)
    WHERE state IN ('PENDING', 'DELIVERING');

CREATE INDEX IF NOT EXISTS idx_execution_success_deliveries_due_claim
    ON execution_success_deliveries (venue, next_attempt_at, created_at)
    WHERE state IN ('PENDING', 'DELIVERING');

INSERT INTO execution_success_deliveries (
    venue,
    idempotency_key,
    delivery_kind,
    state,
    attempts,
    delivery_payload,
    next_attempt_at,
    created_at,
    updated_at,
    delivered_at
)
SELECT
    venue,
    idempotency_key,
    'ORDER_PLACED',
    'DELIVERED',
    0,
    NULL,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM execution_intents
WHERE state = 'ACKNOWLEDGED'
ON CONFLICT (venue, idempotency_key, delivery_kind) DO NOTHING;

GRANT SELECT, INSERT, UPDATE, DELETE ON execution_success_deliveries TO trading_user;
