CREATE TABLE IF NOT EXISTS outbound_alert_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attempted_at TIMESTAMPTZ NOT NULL,
    channel TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    delivery_method TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    chat_id TEXT,
    dedup_key TEXT,
    telegram_message_id BIGINT,
    message_text TEXT,
    response_status INTEGER,
    response_body TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbound_alert_audit_attempted_at
    ON outbound_alert_audit (attempted_at DESC);

CREATE INDEX IF NOT EXISTS idx_outbound_alert_audit_channel_status
    ON outbound_alert_audit (channel, status, attempted_at DESC);

CREATE INDEX IF NOT EXISTS idx_outbound_alert_audit_alert_type
    ON outbound_alert_audit (alert_type, attempted_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON outbound_alert_audit TO trading_user;
