DROP INDEX IF EXISTS uq_orders_venue_exchange_order_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_venue_exchange_order_id
    ON orders (venue, symbol, exchange_order_id)
    WHERE exchange_order_id IS NOT NULL;
