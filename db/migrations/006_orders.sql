-- 006_orders.sql: Order tracking with status updates

CREATE TABLE IF NOT EXISTS orders (
    order_id UUID NOT NULL DEFAULT gen_random_uuid(),
    client_order_id TEXT NOT NULL,
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    type TEXT NOT NULL CHECK (type IN ('MARKET', 'LIMIT', 'STOP_LOSS', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT', 'TAKE_PROFIT_LIMIT')),
    quantity NUMERIC(18,8) NOT NULL CHECK (quantity > 0),
    price NUMERIC(18,8) CHECK (price IS NULL OR price > 0),
    stop_price NUMERIC(18,8) CHECK (stop_price IS NULL OR stop_price > 0),
    time_in_force TEXT NOT NULL DEFAULT 'GTC' CHECK (time_in_force IN ('GTC', 'IOC', 'FOK', 'GTX')),
    status TEXT NOT NULL CHECK (status IN ('NEW', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')),
    filled_quantity NUMERIC(18,8) NOT NULL DEFAULT 0 CHECK (filled_quantity >= 0),
    average_fill_price NUMERIC(18,8) CHECK (average_fill_price IS NULL OR average_fill_price > 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    decision_id UUID,
    exchange_order_id TEXT,
    last_update_time TIMESTAMPTZ,
    commission NUMERIC(18,8) DEFAULT 0 CHECK (commission >= 0),
    commission_asset TEXT,
    reduce_only BOOLEAN DEFAULT FALSE,
    post_only BOOLEAN DEFAULT FALSE,
    close_position BOOLEAN DEFAULT FALSE,
    activation_price NUMERIC(18,8) CHECK (activation_price IS NULL OR activation_price > 0),
    callback_rate NUMERIC(5,2) CHECK (callback_rate IS NULL OR (callback_rate > 0 AND callback_rate <= 100)),
    working_type TEXT CHECK (working_type IN ('MARK_PRICE', 'CONTRACT_PRICE')),
    price_protect BOOLEAN DEFAULT FALSE,
    reject_reason TEXT,
    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_client_order_id UNIQUE (venue, client_order_id),
    CONSTRAINT chk_filled_quantity CHECK (filled_quantity <= quantity),
    CONSTRAINT chk_limit_order_price CHECK (
        (type NOT IN ('LIMIT', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT_LIMIT')) OR price IS NOT NULL
    ),
    CONSTRAINT chk_stop_order_price CHECK (
        (type NOT IN ('STOP_LOSS', 'STOP_LOSS_LIMIT')) OR stop_price IS NOT NULL
    )
);

-- Create hypertable on created_at
SELECT create_hypertable(
    'orders',
    'created_at',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Create indexes as specified in PRD
CREATE INDEX IF NOT EXISTS idx_orders_symbol_created
    ON orders (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_venue_symbol_created
    ON orders (venue, symbol, created_at DESC);

-- Index for client order ID lookup
CREATE INDEX IF NOT EXISTS idx_orders_client_order_id
    ON orders (client_order_id);

-- Index for exchange order ID lookup
CREATE INDEX IF NOT EXISTS idx_orders_exchange_order_id
    ON orders (exchange_order_id)
    WHERE exchange_order_id IS NOT NULL;

-- Index for active orders
CREATE INDEX IF NOT EXISTS idx_orders_active
    ON orders (symbol, created_at DESC)
    WHERE status IN ('NEW', 'PARTIALLY_FILLED');

-- Index for decision tracking
CREATE INDEX IF NOT EXISTS idx_orders_decision_id
    ON orders (decision_id)
    WHERE decision_id IS NOT NULL;

-- Index for filled orders
CREATE INDEX IF NOT EXISTS idx_orders_filled
    ON orders (symbol, created_at DESC)
    WHERE status = 'FILLED';

-- Add updated_at trigger
DROP TRIGGER IF EXISTS update_orders_updated_at ON orders;
CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Set compression policy
ALTER TABLE orders SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'venue, symbol, status',
    timescaledb.compress_orderby = 'created_at DESC'
);

-- Add compression policy
SELECT add_compression_policy(
    'orders',
    compress_after => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Add retention policy
SELECT add_retention_policy(
    'orders',
    drop_after => INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON orders TO trading_user;