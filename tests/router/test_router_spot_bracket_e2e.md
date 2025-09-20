# Order Router E2E Test Script

This document provides manual test scripts and curl examples for testing the Order Router against Binance Testnet.

## Prerequisites

1. Get Binance Testnet API Keys:
   - Spot Testnet: https://testnet.binance.vision/
   - Futures Testnet: https://testnet.binancefuture.com/

2. Set environment variables:
```bash
export BINANCE_SPOT_API_KEY="your_spot_testnet_api_key"
export BINANCE_SPOT_SECRET_KEY="your_spot_testnet_secret_key"
export BINANCE_FUTURES_API_KEY="your_futures_testnet_api_key"
export BINANCE_FUTURES_SECRET_KEY="your_futures_testnet_secret_key"
export BINANCE_TESTNET=true
export SERVER_PORT=8081
```

3. Start the router:
```bash
cd app/router
go run cmd/router/main.go
```

## Test Cases

### 1. Health Check

```bash
# Test health endpoint
curl -X GET http://localhost:8081/healthz

# Expected response:
# {"service":"order-router","status":"healthy"}
```

### 2. Readiness Check

```bash
# Test readiness endpoint
curl -X GET http://localhost:8081/readyz

# Expected response:
# {"service":"order-router","status":"ready"}
```

### 3. Place Spot Bracket Order - Market Entry

```bash
# Place a spot bracket order with market entry
curl -X POST http://localhost:8081/place_bracket \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": "0.001",
    "take_profit_prices": ["70000", "71000"],
    "stop_loss_price": "60000",
    "is_futures": false
  }'

# Expected response:
# {
#   "bracket_order_id": "uuid-here",
#   "client_order_ids": {
#     "main": "uuid_MAIN_timestamp",
#     "take_profits": ["uuid_TP1_timestamp", "uuid_TP2_timestamp"],
#     "stop_loss": "uuid_SL_timestamp"
#   },
#   "symbol": "BTCUSDT",
#   "side": "BUY",
#   "quantity": "0.001",
#   "created_at": "2024-01-01T00:00:00Z"
# }
```

### 4. Place Spot Bracket Order - Limit Entry

```bash
# Place a spot bracket order with limit entry
curl -X POST http://localhost:8081/place_bracket \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETHUSDT",
    "side": "BUY",
    "quantity": "0.01",
    "entry_price": "3000",
    "take_profit_prices": ["3200", "3300"],
    "stop_loss_price": "2900",
    "order_type": "LIMIT",
    "is_futures": false
  }'
```

### 5. Place Futures Bracket Order

```bash
# Place a futures bracket order
curl -X POST http://localhost:8081/place_bracket \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": "0.001",
    "entry_price": "65000",
    "take_profit_prices": ["70000", "71000", "72000"],
    "stop_loss_price": "63000",
    "order_type": "LIMIT",
    "is_futures": true
  }'

# Note: Futures orders will use ReduceOnly for TPs and STOP_MARKET for SL
```

### 6. Cancel Order

```bash
# Cancel an order by order ID
curl -X POST http://localhost:8081/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "order_id": 123456789
  }'

# Expected response:
# {"status":"success"}
```

### 7. Close All Positions

```bash
# Close all positions for a symbol
curl -X POST http://localhost:8081/close_all \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "is_futures": false
  }'

# Expected response:
# {"status":"success"}
```

## Error Test Cases

### 8. Invalid Side

```bash
# Test with invalid side
curl -X POST http://localhost:8081/place_bracket \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "INVALID",
    "quantity": "0.001",
    "take_profit_prices": ["70000"],
    "stop_loss_price": "60000",
    "is_futures": false
  }'

# Expected error:
# {"error":"invalid bracket request: invalid side: INVALID"}
```

### 9. Invalid Price Relationships

```bash
# Test with SL above entry for buy order
curl -X POST http://localhost:8081/place_bracket \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": "0.001",
    "entry_price": "65000",
    "take_profit_prices": ["70000"],
    "stop_loss_price": "66000",
    "is_futures": false
  }'

# Expected error:
# {"error":"invalid bracket request: stop loss must be below entry for buy orders"}
```

### 10. Insufficient Balance

```bash
# Test with large quantity
curl -X POST http://localhost:8081/place_bracket \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "side": "BUY",
    "quantity": "100",
    "take_profit_prices": ["70000"],
    "stop_loss_price": "60000",
    "is_futures": false
  }'

# Expected error:
# {"error":"insufficient balance for quantity: 100"}
```

## Order Update Events

If `ORDER_UPDATE_URL` is configured, the router will POST order updates:

```json
{
  "event_type": "order_update.v1",
  "symbol": "BTCUSDT",
  "order_id": 123456789,
  "client_order_id": "uuid_MAIN_timestamp",
  "status": "NEW",
  "side": "BUY",
  "order_type": "LIMIT",
  "price": "65000",
  "quantity": "0.001",
  "executed_qty": "0",
  "update_time": "2024-01-01T00:00:00Z"
}
```

## Monitoring

Monitor the router logs for:
- Order placement confirmations
- API errors (rate limits, insufficient balance)
- Order update events
- Rounding adjustments

## Common Issues

1. **Time Sync Error (-1021)**
   - Ensure system time is synchronized
   - Router automatically retries with adjusted timestamp

2. **Insufficient Balance**
   - Testnet accounts start with limited balance
   - Request testnet funds from faucet

3. **Invalid Symbol**
   - Some symbols may not be available on testnet
   - Check exchange info endpoint for available symbols

4. **Rate Limiting**
   - Testnet has lower rate limits than production
   - Router includes retry logic with exponential backoff

## Troubleshooting

1. Check router logs for detailed error messages
2. Verify API keys are for testnet (not production)
3. Ensure network connectivity to Binance testnet
4. Verify order parameters meet exchange requirements

## Notes

- All orders use `newClientOrderId` for idempotency
- Prices and quantities are automatically rounded per symbol rules
- Futures orders use ONE-WAY position mode
- Stop orders on spot are simulated with limit orders (testnet limitation)