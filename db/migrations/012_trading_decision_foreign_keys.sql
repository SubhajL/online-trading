-- 012_trading_decision_foreign_keys.sql: Link orders/positions to trading decisions

ALTER TABLE orders
ADD CONSTRAINT fk_orders_trading_decision
FOREIGN KEY (decision_id)
REFERENCES trading_decisions(decision_id)
ON DELETE SET NULL;

ALTER TABLE positions
ADD CONSTRAINT fk_positions_trading_decision
FOREIGN KEY (decision_id)
REFERENCES trading_decisions(decision_id)
ON DELETE SET NULL;

