-- 032_orders_limit_maker.sql: spot OCO exits.
-- OCO take-profit legs are LIMIT_MAKER orders, and legs placed inside an
-- order list carry the exchange's orderListId for reconciliation.

ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_type_check;
ALTER TABLE orders ADD CONSTRAINT orders_type_check CHECK (
    type IN (
        'MARKET',
        'LIMIT',
        'LIMIT_MAKER',
        'STOP_MARKET',
        'STOP_LOSS',
        'STOP_LOSS_LIMIT',
        'TAKE_PROFIT',
        'TAKE_PROFIT_LIMIT'
    )
);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_list_id BIGINT;
