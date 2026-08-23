UPDATE orders AS order_projection
SET exchange_order_id = NULL
FROM execution_intents AS execution_intent
WHERE execution_intent.venue = order_projection.venue
  AND order_projection.exchange_order_id IS NOT NULL
  AND execution_intent.response_payload->>'bracket_order_id' IS NOT NULL
  AND order_projection.exchange_order_id = execution_intent.response_payload->>'bracket_order_id';
