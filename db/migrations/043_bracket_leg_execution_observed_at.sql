-- 043_bracket_leg_execution_observed_at.sql: preserve exchange observation time
-- in durable bracket-leg order-update payloads.

ALTER TABLE bracket_legs
    ADD COLUMN IF NOT EXISTS execution_observed_at TIMESTAMPTZ;

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
    durable_executed_quantity NUMERIC;
    prior_executed_quantity NUMERIC;
BEGIN
    IF NEW.status NOT IN ('PLACED', 'FILLED', 'CANCELED', 'EXPIRED', 'FAILED') THEN
        RETURN NEW;
    END IF;

    SELECT * INTO bracket_row
    FROM brackets
    WHERE bracket_id = NEW.bracket_id;

    aggregate_key := bracket_row.venue || ':' || NEW.client_order_id;
    PERFORM pg_advisory_xact_lock(hashtextextended(aggregate_key, 0));

    durable_executed_quantity := COALESCE(NEW.executed_quantity, 0);
    SELECT NULLIF(prior.payload->>'executed_qty', '')::numeric
    INTO prior_executed_quantity
    FROM router_order_update_outbox AS prior
    WHERE prior.aggregate_id = aggregate_key
    ORDER BY prior.sequence DESC
    LIMIT 1;
    normalized_status := CASE
        WHEN NEW.role = 'ENTRY'
             AND NEW.status = 'PLACED'
             AND durable_executed_quantity > 0
            THEN 'PARTIALLY_FILLED'
        WHEN NEW.status = 'PLACED' THEN 'NEW'
        WHEN NEW.status = 'FAILED' THEN 'REJECTED'
        ELSE NEW.status
    END;

    event_side := CASE
        WHEN NEW.role = 'ENTRY' THEN bracket_row.side
        WHEN bracket_row.side = 'BUY' THEN 'SELL'
        ELSE 'BUY'
    END;

    event_order_type := CASE NEW.role
        WHEN 'ENTRY' THEN CASE
            WHEN bracket_row.entry_price = 0 THEN 'MARKET'
            ELSE 'LIMIT'
        END
        WHEN 'SL' THEN CASE
            WHEN bracket_row.venue = 'SPOT' THEN 'STOP_LOSS_LIMIT'
            ELSE 'STOP_MARKET'
        END
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
        'price', CASE
            WHEN event_order_type IN ('STOP_MARKET', 'MARKET') THEN NULL
            ELSE NEW.price
        END,
        'stop_price', CASE
            WHEN NEW.role = 'SL' THEN NEW.stop_price
            ELSE NULL
        END,
        'quantity', NEW.quantity,
        'executed_qty', CASE
            WHEN NEW.status = 'FILLED' THEN NEW.quantity
            WHEN durable_executed_quantity > 0 THEN durable_executed_quantity
            WHEN NEW.role <> 'ENTRY' THEN COALESCE(prior_executed_quantity, 0)
            ELSE durable_executed_quantity
        END,
        'average_fill_price', COALESCE(
            NEW.average_fill_price,
            (
                SELECT o.average_fill_price
                FROM orders AS o
                WHERE o.venue = bracket_row.venue
                  AND o.client_order_id = NEW.client_order_id
                ORDER BY o.updated_at DESC
                LIMIT 1
            ),
            (
                SELECT NULLIF(prior.payload->>'average_fill_price', '')::numeric
                FROM router_order_update_outbox AS prior
                WHERE prior.aggregate_id = aggregate_key
                ORDER BY prior.sequence DESC
                LIMIT 1
            )
        ),
        'update_time', COALESCE(NEW.execution_observed_at, CURRENT_TIMESTAMP)
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
        payload_json,
        encode(digest(payload_json::text, 'sha256'), 'hex'),
        encode(digest((payload_json - 'update_time')::text, 'sha256'), 'hex'),
        'PENDING', CURRENT_TIMESTAMP
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
