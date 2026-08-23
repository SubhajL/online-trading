ALTER TABLE execution_intents
    ADD COLUMN IF NOT EXISTS recovery_lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS recovery_attempts INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'execution_intents'::regclass
          AND conname = 'chk_execution_intents_recovery_attempts'
    ) THEN
        ALTER TABLE execution_intents
            ADD CONSTRAINT chk_execution_intents_recovery_attempts
            CHECK (recovery_attempts >= 0);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_execution_intents_recovery_claim
    ON execution_intents (venue, updated_at, recovery_lease_expires_at)
    WHERE state IN ('SUBMITTING', 'AMBIGUOUS');

GRANT SELECT, UPDATE ON execution_intents TO trading_user;
