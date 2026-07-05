-- 030_brackets.sql: Durable bracket reservations and leg-level state.
-- Owned by the Go router. The in-memory idempotency map dies with the
-- process; these tables make check-and-reserve and replay repair survive
-- restarts. `orders` stays exchange-acked-only; planned-but-unplaced legs
-- live here.

CREATE TABLE IF NOT EXISTS brackets (
    bracket_id UUID NOT NULL DEFAULT gen_random_uuid(),
    venue TEXT NOT NULL CHECK (venue IN ('SPOT', 'USD_M')),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity NUMERIC(18,8) NOT NULL CHECK (quantity > 0),
    entry_price NUMERIC(18,8) CHECK (entry_price IS NULL OR entry_price >= 0),
    stop_loss_price NUMERIC(18,8) NOT NULL CHECK (stop_loss_price > 0),
    entry_client_order_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('RESERVED', 'ENTRY_PLACED', 'ENTRY_FILLED', 'LEGS_PLACED', 'CLOSED', 'FAILED')
    ),
    legs_on_fill BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_brackets PRIMARY KEY (bracket_id),
    CONSTRAINT uq_brackets_entry_client_order_id UNIQUE (venue, entry_client_order_id)
);

CREATE INDEX IF NOT EXISTS idx_brackets_status ON brackets (status);
CREATE INDEX IF NOT EXISTS idx_brackets_symbol_status ON brackets (symbol, status);
CREATE INDEX IF NOT EXISTS idx_brackets_created_at ON brackets (created_at);

CREATE TABLE IF NOT EXISTS bracket_legs (
    leg_id UUID NOT NULL DEFAULT gen_random_uuid(),
    bracket_id UUID NOT NULL REFERENCES brackets (bracket_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('ENTRY', 'TP', 'SL')),
    tp_index INT NOT NULL DEFAULT 0 CHECK (tp_index >= 0),
    client_order_id TEXT NOT NULL,
    exchange_order_id BIGINT,
    price NUMERIC(18,8) CHECK (price IS NULL OR price >= 0),
    stop_price NUMERIC(18,8) CHECK (stop_price IS NULL OR stop_price >= 0),
    quantity NUMERIC(18,8) NOT NULL CHECK (quantity >= 0),
    status TEXT NOT NULL CHECK (
        status IN ('PLANNED', 'PLACED', 'FILLED', 'CANCELED', 'EXPIRED', 'FAILED')
    ),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_bracket_legs PRIMARY KEY (leg_id),
    CONSTRAINT uq_bracket_legs_client_order_id UNIQUE (bracket_id, client_order_id)
);

CREATE INDEX IF NOT EXISTS idx_bracket_legs_bracket_id ON bracket_legs (bracket_id);
CREATE INDEX IF NOT EXISTS idx_bracket_legs_status ON bracket_legs (status);
