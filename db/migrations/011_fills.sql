-- 011_fills.sql: Trade fills + provenance columns for router execution tracking

CREATE TABLE IF NOT EXISTS fills (
    fill_id UUID NOT NULL DEFAULT gen_random_uuid(),
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_id BIGINT NOT NULL,
    client_order_id TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    price NUMERIC(18,8) NOT NULL CHECK (price > 0),
    quantity NUMERIC(18,8) NOT NULL CHECK (quantity > 0),
    commission NUMERIC(18,8) NOT NULL DEFAULT 0 CHECK (commission >= 0),
    commission_asset TEXT,
    realized_pnl NUMERIC(18,8),
    slippage NUMERIC(18,8) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_fills PRIMARY KEY (fill_id),
    CONSTRAINT uq_fills_trade UNIQUE (venue, symbol, trade_id)
);

CREATE INDEX IF NOT EXISTS idx_fills_client_order_id
    ON fills (client_order_id);

CREATE INDEX IF NOT EXISTS idx_fills_created_at
    ON fills (created_at DESC);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS requested_price NUMERIC(18,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_commission NUMERIC(18,8) NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_slippage NUMERIC(18,8) NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS timeframe TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS zone JSONB;

ALTER TABLE positions ADD COLUMN IF NOT EXISTS slippage_paid NUMERIC(18,8) NOT NULL DEFAULT 0;

ALTER TABLE positions DROP CONSTRAINT IF EXISTS positions_size_check;
ALTER TABLE positions ADD CONSTRAINT positions_size_check CHECK (size >= 0);

-- Router places futures stop loss as STOP_MARKET; allow it in orders table.
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_type_check;
ALTER TABLE orders ADD CONSTRAINT orders_type_check CHECK (
    type IN (
        'MARKET',
        'LIMIT',
        'STOP_MARKET',
        'STOP_LOSS',
        'STOP_LOSS_LIMIT',
        'TAKE_PROFIT',
        'TAKE_PROFIT_LIMIT'
    )
);

-- Enforce stop_price for stop orders including STOP_MARKET.
ALTER TABLE orders DROP CONSTRAINT IF EXISTS chk_stop_order_price;
ALTER TABLE orders ADD CONSTRAINT chk_stop_order_price CHECK (
    (type NOT IN ('STOP_MARKET', 'STOP_LOSS', 'STOP_LOSS_LIMIT')) OR stop_price IS NOT NULL
);

GRANT SELECT, INSERT, UPDATE, DELETE ON fills TO trading_user;
