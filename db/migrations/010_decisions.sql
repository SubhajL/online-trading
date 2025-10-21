-- 010_decisions.sql: Minimal decisions table to satisfy FKs and tests

CREATE TABLE IF NOT EXISTS decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL
);

GRANT SELECT, INSERT, UPDATE, DELETE ON decisions TO trading_user;

