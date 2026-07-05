-- 031_bracket_leg_placing.sql: PLACING claim state for fill-triggered legs.
-- The leg armer claims a PLANNED leg (compare-and-set to PLACING) before
-- POSTing so duplicate fill events cannot double-place protective legs.

ALTER TABLE bracket_legs DROP CONSTRAINT IF EXISTS bracket_legs_status_check;
ALTER TABLE bracket_legs ADD CONSTRAINT bracket_legs_status_check CHECK (
    status IN ('PLANNED', 'PLACING', 'PLACED', 'FILLED', 'CANCELED', 'EXPIRED', 'FAILED')
);

-- The leg armer resolves every user-data event by leg client order id
CREATE INDEX IF NOT EXISTS idx_bracket_legs_client_order_id ON bracket_legs (client_order_id);
