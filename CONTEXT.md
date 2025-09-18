# CONTEXT.md - Architecture and Module Contracts

## System Architecture

### Three Planes Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA PLANE (Real-time)                    │
│  WS Ingestors → Features → SMC → Decision → Router → Exchange│
└─────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────┐
│                   CONTROL PLANE (Batch & Ops)                │
│    Backtester ← Parameter Store → Risk Limits → Calendars    │
└─────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────┐
│                 EXPERIENCE PLANE (UI & Alerts)               │
│        Next.js UI ← BFF API/WS → Telegram/LINE Alerts       │
└─────────────────────────────────────────────────────────────┘
```

## Module Boundaries

### 1. Core Engine (Python - `/app/engine`)

**Purpose**: Central trading logic with async event-driven architecture

**Modules**:
- `ingest/` - WebSocket & REST data ingestion from Binance
- `features/` - Technical indicator calculations
- `smc/` - Smart Money Concepts analysis
- `retest/` - Zone retest validation
- `regime_vol/` - Market regime classification
- `news_funding_guards/` - Risk management guards
- `decision/` - Trading decision engine
- `paper/` - Paper trading simulator
- `backtest/` - Historical strategy testing
- `plugins/` - Extensible plugin system

**Internal Communication**: Async in-memory event bus (no network hops)

### 2. Order Router (Go - `/app/router`)

**Purpose**: Isolated order execution with strict idempotency

**Responsibilities**:
- Order signing and submission to Binance
- Exchange info caching and rounding rules
- Order status reconciliation
- Kill-switch implementation

**API Contract**:
```go
POST /api/v1/order
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "type": "LIMIT",
  "quantity": "0.001",
  "price": "50000.00",
  "clientOrderId": "unique_id_123"
}
```

### 3. BFF/UI (TypeScript - `/app/bff` & `/app/ui`)

**Purpose**: User interface and API gateway

**Components**:
- NestJS backend with REST/WebSocket APIs
- Next.js frontend with real-time charts
- Lightweight Charts for visualization

**API Contract**:
```typescript
// WebSocket events
interface CandleUpdate {
  type: 'candle';
  symbol: string;
  timeframe: string;
  data: Candle;
}

interface SignalUpdate {
  type: 'signal';
  symbol: string;
  signal: TradingSignal;
}
```

## Event Contracts

### Core Events (Engine Internal)

#### candles.v1
```json
{
  "venue": "binance_spot",
  "symbol": "BTCUSDT",
  "tf": "15m",
  "open_time": "2025-01-01T00:00:00Z",
  "open": 50000.00,
  "high": 50500.00,
  "low": 49500.00,
  "close": 50250.00,
  "volume": 100.5
}
```

#### features.v1
```json
{
  "symbol": "BTCUSDT",
  "tf": "15m",
  "ts": "2025-01-01T00:15:00Z",
  "ema20": 50100.00,
  "ema50": 49900.00,
  "rsi14": 55.5,
  "macd": 150.00,
  "macd_signal": 140.00,
  "atr14": 500.00
}
```

#### smc_events.v1
```json
{
  "symbol": "BTCUSDT",
  "tf": "15m",
  "ts": "2025-01-01T00:15:00Z",
  "kind": "BOS_UP",
  "ref_ts": "2025-01-01T00:00:00Z",
  "level": 49800.00
}
```

#### zones.v1
```json
{
  "symbol": "BTCUSDT",
  "tf": "15m",
  "kind": "ORDER_BLOCK",
  "side": "DEMAND",
  "price_lo": 49700.00,
  "price_hi": 49900.00,
  "created_ts": "2025-01-01T00:00:00Z",
  "strength": 8
}
```

#### signals_raw.v1
```json
{
  "agent": "retest_analyzer",
  "symbol": "BTCUSDT",
  "tf": "15m",
  "side_hint": "LONG",
  "entry_hint": 50000.00,
  "sl_hint": 49500.00,
  "tpR": [1.5, 2.0, 3.0],
  "features": {
    "ema200_up": true,
    "macd_hist_up": true,
    "rsi_mid_bounce": true
  },
  "score": 0.74,
  "ttl_bars": 6
}
```

#### decision.v1
```json
{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "size": 0.001,
  "entry": 50000.00,
  "sl": 49500.00,
  "tp_ladder": [
    {"price": 50750.00, "qty": 0.00033},
    {"price": 51000.00, "qty": 0.00033},
    {"price": 51500.00, "qty": 0.00034}
  ],
  "risk": {
    "position_value": 50.00,
    "risk_amount": 0.50,
    "risk_reward": 2.0
  }
}
```

## Database Schema

### TimescaleDB Tables

```sql
-- Hypertable for time-series data
CREATE TABLE candles (
  venue TEXT,
  symbol TEXT,
  tf TEXT,
  open_time TIMESTAMPTZ,
  close_time TIMESTAMPTZ,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC,
  PRIMARY KEY (venue, symbol, tf, open_time)
);
SELECT create_hypertable('candles', 'open_time');

-- Indicators table
CREATE TABLE indicators (
  venue TEXT,
  symbol TEXT,
  tf TEXT,
  ts TIMESTAMPTZ,
  ema20 NUMERIC,
  ema50 NUMERIC,
  rsi14 NUMERIC,
  macd NUMERIC,
  atr14 NUMERIC,
  PRIMARY KEY (venue, symbol, tf, ts)
);

-- SMC events
CREATE TABLE smc_events (
  venue TEXT,
  symbol TEXT,
  tf TEXT,
  ts TIMESTAMPTZ,
  kind TEXT CHECK (kind IN ('CHOCH_UP', 'CHOCH_DN', 'BOS_UP', 'BOS_DN')),
  ref_ts TIMESTAMPTZ,
  level NUMERIC,
  PRIMARY KEY (venue, symbol, tf, ts, kind)
);

-- Supply/Demand zones
CREATE TABLE zones (
  venue TEXT,
  symbol TEXT,
  tf TEXT,
  kind TEXT CHECK (kind IN ('OB', 'FVG')),
  side TEXT CHECK (side IN ('DEMAND', 'SUPPLY')),
  price_lo NUMERIC,
  price_hi NUMERIC,
  created_ts TIMESTAMPTZ,
  strength INT,
  PRIMARY KEY (venue, symbol, tf, kind, created_ts)
);

-- Orders
CREATE TABLE orders (
  order_id UUID PRIMARY KEY,
  client_order_id TEXT UNIQUE,
  exchange_order_id TEXT,
  symbol TEXT,
  side TEXT,
  type TEXT,
  quantity NUMERIC,
  price NUMERIC,
  status TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
);

-- Positions
CREATE TABLE positions (
  position_id UUID PRIMARY KEY,
  symbol TEXT,
  side TEXT,
  size NUMERIC,
  entry_price NUMERIC,
  current_price NUMERIC,
  unrealized_pnl NUMERIC,
  realized_pnl NUMERIC,
  opened_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ
);
```

## Style Guide

### Python (Engine)

```python
# Use type hints everywhere
async def calculate_indicators(
    candles: List[Candle],
    config: IndicatorConfig
) -> TechnicalIndicators:
    """Calculate technical indicators from candles."""
    pass

# Prefer async/await
async def process_event(event: BaseEvent) -> None:
    async with self.lock:
        await self._handle_event(event)

# Use Decimal for financial calculations
from decimal import Decimal
price = Decimal("50000.00")
quantity = Decimal("0.001")
```

### Go (Router)

```go
// Use structured errors
type OrderError struct {
    Code    string
    Message string
    OrderID string
}

// Implement interfaces explicitly
var _ OrderService = (*BinanceRouter)(nil)

// Use context for cancellation
func (r *Router) PlaceOrder(ctx context.Context, order Order) error {
    select {
    case <-ctx.Done():
        return ctx.Err()
    default:
        return r.submitOrder(order)
    }
}
```

### TypeScript (BFF/UI)

```typescript
// Use branded types for IDs
type OrderId = string & { readonly brand: unique symbol };

// Prefer const assertions
const TIMEFRAMES = ['1m', '5m', '15m', '1h'] as const;
type TimeFrame = typeof TIMEFRAMES[number];

// Use discriminated unions
type Signal =
  | { type: 'BUY'; entry: number; stop: number }
  | { type: 'SELL'; entry: number; stop: number }
  | { type: 'HOLD'; reason: string };
```

## Performance Targets

| Operation | Target Latency | Critical Path |
|-----------|---------------|---------------|
| Candle close → Features | ≤200ms | Yes |
| Features → SMC signals | ≤200ms | Yes |
| SMC → Decision | ≤100ms | Yes |
| Decision → Router POST | ≤200ms | Yes |
| **Total E2E** | **≤700ms p95** | - |
| REST backfill | <5s | Recovery |
| UI chart update | <150ms | UX |

## Security Considerations

1. **API Keys**: Separate keys for Spot vs Futures, no withdrawal scope
2. **Idempotency**: Every order has unique `clientOrderId`
3. **Rate Limiting**: Respect exchange limits (1200 req/min)
4. **Kill Switch**: Auto-halt on drawdown breach or error spike
5. **Secrets**: Never in code, use environment variables or vault

## Deployment Strategy

### Development
```bash
docker-compose -f docker-compose.dev.yml up
```

### Staging
```yaml
# K8s with small resource limits
resources:
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### Production
```yaml
# K8s with HPA and rolling updates
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```

## Monitoring & Observability

### Key Metrics
- **Latency**: p50, p95, p99 for each pipeline stage
- **Event Counts**: Messages processed per second
- **Error Rates**: By component and error type
- **Trading**: Win rate, PnL, drawdown, Sharpe ratio

### Dashboards
1. **System Health**: CPU, memory, network, disk
2. **Trading Performance**: Equity curve, trade distribution
3. **Market Data**: Candle completeness, WebSocket reconnects
4. **Risk**: Position exposure, drawdown alerts

### Alerts
- WebSocket disconnection > 30s
- Drawdown > 5%
- Error rate > 1%
- Latency p95 > 1s
- Order rejection rate > 5%