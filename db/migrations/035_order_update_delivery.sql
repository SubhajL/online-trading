CREATE TABLE IF NOT EXISTS router_order_update_sequences (
    aggregate_id TEXT PRIMARY KEY,
    next_sequence BIGINT NOT NULL DEFAULT 1 CHECK (next_sequence >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS router_order_update_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence >= 1),
    event_version INTEGER NOT NULL DEFAULT 1 CHECK (event_version = 1),
    event_type TEXT NOT NULL CHECK (event_type = 'order_update.v1'),
    payload JSONB NOT NULL,
    payload_hash CHAR(64) NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    event_key_hash CHAR(64) NOT NULL CHECK (event_key_hash ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'DELIVERING', 'DELIVERED', 'DEAD')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMPTZ,
    UNIQUE (aggregate_id, sequence),
    UNIQUE (aggregate_id, event_key_hash)
);

ALTER TABLE router_order_update_outbox
    ADD COLUMN IF NOT EXISTS event_key_hash CHAR(64);

UPDATE router_order_update_outbox
SET event_key_hash = encode(digest((payload - 'update_time')::text, 'sha256'), 'hex')
WHERE event_key_hash IS NULL;

ALTER TABLE router_order_update_outbox
    ALTER COLUMN event_key_hash SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_router_order_update_outbox_event_key
    ON router_order_update_outbox (aggregate_id, event_key_hash);

CREATE INDEX IF NOT EXISTS idx_router_order_update_outbox_dispatch
    ON router_order_update_outbox (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'DELIVERING');

CREATE TABLE IF NOT EXISTS engine_order_update_inbox (
    event_id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence >= 1),
    event_version INTEGER NOT NULL CHECK (event_version = 1),
    payload JSONB NOT NULL,
    payload_hash CHAR(64) NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL DEFAULT 'RECEIVED'
        CHECK (state IN ('RECEIVED', 'PROCESSING', 'PARKED', 'PROCESSED', 'FAILED')),
    processing_started_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    last_error TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (aggregate_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_engine_order_update_inbox_aggregate
    ON engine_order_update_inbox (aggregate_id, sequence);

CREATE OR REPLACE FUNCTION enqueue_bracket_leg_order_update()
RETURNS TRIGGER AS $$
DECLARE
    bracket_row brackets%ROWTYPE;
    aggregate_key TEXT;
    next_seq BIGINT;
    normalized_status TEXT;
    payload_json JSONB;
    event_side TEXT;
    event_order_type TEXT;
BEGIN
    IF NEW.status NOT IN ('PLACED', 'FILLED', 'CANCELED', 'EXPIRED', 'FAILED') THEN
        RETURN NEW;
    END IF;
    SELECT * INTO bracket_row FROM brackets WHERE bracket_id = NEW.bracket_id;
    aggregate_key := bracket_row.venue || ':' || NEW.client_order_id;
	PERFORM pg_advisory_xact_lock(hashtextextended(aggregate_key, 0));
    normalized_status := CASE NEW.status
        WHEN 'PLACED' THEN 'NEW'
        WHEN 'FAILED' THEN 'REJECTED'
        ELSE NEW.status
    END;
    event_side := CASE WHEN NEW.role = 'ENTRY' THEN bracket_row.side
        WHEN bracket_row.side = 'BUY' THEN 'SELL' ELSE 'BUY' END;
    event_order_type := CASE NEW.role
        WHEN 'ENTRY' THEN CASE WHEN bracket_row.entry_price = 0 THEN 'MARKET' ELSE 'LIMIT' END
        WHEN 'SL' THEN 'STOP_MARKET'
        ELSE 'LIMIT'
    END;
    payload_json := jsonb_build_object(
        'event_type', 'order_update.v1',
        'venue', bracket_row.venue,
        'symbol', bracket_row.symbol,
        'order_id', NEW.exchange_order_id,
        'client_order_id', NEW.client_order_id,
        'status', normalized_status,
        'side', event_side,
        'order_type', event_order_type,
        'price', CASE WHEN NEW.role = 'SL' THEN NEW.stop_price ELSE NEW.price END,
        'quantity', NEW.quantity,
        'executed_qty', CASE
            WHEN NEW.status = 'FILLED' THEN NEW.quantity
            ELSE COALESCE((
                SELECT (prior.payload->>'executed_qty')::numeric
                FROM router_order_update_outbox AS prior
                WHERE prior.aggregate_id = aggregate_key
                ORDER BY prior.sequence DESC
                LIMIT 1
            ), 0)
        END,
        'update_time', CURRENT_TIMESTAMP
    );
    INSERT INTO router_order_update_sequences (aggregate_id, next_sequence)
    VALUES (aggregate_key, 2)
    ON CONFLICT (aggregate_id) DO UPDATE
    SET next_sequence = router_order_update_sequences.next_sequence + 1,
        updated_at = CURRENT_TIMESTAMP
    RETURNING next_sequence - 1 INTO next_seq;
    INSERT INTO router_order_update_outbox (
        event_id, aggregate_id, sequence, event_version, event_type,
        payload, payload_hash, event_key_hash, status, next_attempt_at
    ) VALUES (
        gen_random_uuid(), aggregate_key, next_seq, 1, 'order_update.v1',
        payload_json, encode(digest(payload_json::text, 'sha256'), 'hex'),
        encode(digest((payload_json - 'update_time')::text, 'sha256'), 'hex'),
        'PENDING', CURRENT_TIMESTAMP
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bracket_leg_order_update_outbox ON bracket_legs;
CREATE TRIGGER trg_bracket_leg_order_update_outbox
AFTER UPDATE OF status, exchange_order_id ON bracket_legs
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.exchange_order_id IS DISTINCT FROM NEW.exchange_order_id
)
EXECUTE FUNCTION enqueue_bracket_leg_order_update();

GRANT SELECT, INSERT, UPDATE, DELETE ON router_order_update_sequences TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON router_order_update_outbox TO trading_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON engine_order_update_inbox TO trading_user;
