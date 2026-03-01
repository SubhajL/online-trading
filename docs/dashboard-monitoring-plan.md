# Auto-Trading Monitoring Dashboard - Execution Plan

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01-20 | Initial unified plan |
| 2.0 | 2025-01-20 | Incorporated senior analyst feedback: safety-first hierarchy, canonical P&L model, emergency close state machine, pipeline health |
| 2.1 | 2025-01-20 | Added explicit Engine → BFF → UI event flow documentation |

---

## Overview

Transform the UI from manual trading to **auto-trading monitoring dashboard**. The dashboard answers two questions in order:

1. **"Is the system safe?"** - Guards, exposure, drawdown, emergency controls
2. **"How is it performing?"** - KPIs, equity curve, trade history

Key changes from v1.0:
- Safety-first information hierarchy (guards/exposure before KPIs)
- Canonical equity/P&L model with equity_snapshots table
- Full emergency close state machine with scope selection
- Pipeline health visibility (lag, last candle per symbol)
- Minimum data gates for statistical metrics (Sharpe)

---

## Engine → BFF → UI Event Flow

### Existing Architecture

The BFF already has `EngineClientService` that connects to the engine via Redis pub/sub:

```
Engine (Python)                    BFF (NestJS)                      UI (Next.js)
     │                                  │                                 │
     │ Redis publish                    │                                 │
     │ engine:candles.v1 ─────────────► │ EngineClientService             │
     │ engine:features.v1 ────────────► │   .subscribe('candles.v1')      │
     │ engine:signals_raw.v1 ─────────► │   .subscribe('features.v1')     │
     │ engine:decision.v1 ────────────► │        │                        │
     │                                  │        ▼                        │
     │                                  │ EventEmitter2                   │
     │                                  │   .emit('candles.v1', data)     │
     │                                  │        │                        │
     │                                  │        ▼                        │
     │                                  │ MarketDataGateway               │
     │                                  │   .handleCandleData()           │
     │                                  │        │                        │
     │                                  │        ▼                        │
     │                                  │ Socket.IO ─────────────────────►│ useMarketData()
     │                                  │ server.emit('candles:BTCUSDT')  │   .subscribe()
```

### New Event Channels Required

The following Redis pub/sub channels must be added for dashboard functionality:

| Channel | Publisher | Trigger | Payload |
|---------|-----------|---------|---------|
| `engine:guard_status` | GuardService | On any guard state change | `GuardStatusPayload` |
| `engine:state_changed` | Engine main | On ACTIVE/PAUSED/STOPPED transition | `{ state, reason, timestamp }` |
| `engine:pipeline_health` | PipelineHealthTracker | Every 5 seconds OR on lag spike | `PipelineHealthPayload` |
| `engine:equity_snapshot` | EquityTracker | Every 15 min OR on position change | `EquitySnapshotPayload` |
| `engine:emergency_stop` | RiskGuardManager | On emergency stop triggered | `{ reason, timestamp }` |

### Engine-Side Implementation

```python
# app/engine/monitoring/dashboard_events.py

class DashboardEventPublisher:
    """Publishes dashboard-relevant events to Redis for BFF consumption."""

    def __init__(self, redis_client: Redis, guard_service: GuardService):
        self.redis = redis_client
        self.guard_service = guard_service
        self._last_guard_status: dict | None = None

    async def publish_guard_status_if_changed(self) -> None:
        """Check and publish guard status only on change."""
        current = await self.guard_service.get_guard_status()

        if current != self._last_guard_status:
            await self.redis.publish(
                "engine:guard_status",
                json.dumps(current)
            )
            self._last_guard_status = current

    async def publish_engine_state(self, state: str, reason: str) -> None:
        """Publish engine state transition."""
        await self.redis.publish(
            "engine:state_changed",
            json.dumps({
                "state": state,
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat()
            })
        )

    async def publish_pipeline_health(self, health: dict) -> None:
        """Publish pipeline health metrics."""
        await self.redis.publish(
            "engine:pipeline_health",
            json.dumps(health)
        )
```

### BFF-Side Subscriptions

```typescript
// app/bff/src/dashboard/dashboard.gateway.ts

@WebSocketGateway({ namespace: '/dashboard' })
export class DashboardGateway {
  constructor(private readonly engineClient: EngineClientService) {}

  afterInit(server: Server) {
    // Subscribe to new engine events
    this.engineClient.subscribe('guard_status', (data) => {
      server.to('dashboard').emit('guard.status', data);
    });

    this.engineClient.subscribe('state_changed', (data) => {
      server.to('dashboard').emit('engine.state', data);
    });

    this.engineClient.subscribe('pipeline_health', (data) => {
      server.to('dashboard').emit('pipeline.health', data);
    });

    this.engineClient.subscribe('equity_snapshot', (data) => {
      server.to('dashboard').emit('equity.update', data);
    });

    this.engineClient.subscribe('emergency_stop', (data) => {
      // Broadcast to ALL connected clients, not just dashboard room
      server.emit('emergency.triggered', data);
    });
  }

  @SubscribeMessage('join')
  handleJoin(client: Socket) {
    client.join('dashboard');
    return { success: true };
  }
}
```

### UI-Side Hooks

```typescript
// app/ui/src/hooks/useGuardStatus.ts

export function useGuardStatus() {
  const { service, connected } = useWebSocket('/dashboard');
  const [guardStatus, setGuardStatus] = useState<GuardStatus | null>(null);

  useEffect(() => {
    if (!connected) return;

    // Join dashboard room
    service.emit('join', {});

    // Subscribe to real-time guard updates
    const unsubscribe = service.subscribe<GuardStatus>('guard.status', (data) => {
      setGuardStatus(data);
    });

    // Initial fetch via REST (fallback)
    fetchGuardStatus().then(setGuardStatus);

    return unsubscribe;
  }, [connected]);

  return { guardStatus, loading: !guardStatus };
}
```

### Fallback Strategy

For reliability, UI uses **WebSocket push with REST polling fallback**:

```typescript
// Pattern: Subscribe to WebSocket, poll as backup
useEffect(() => {
  // Primary: WebSocket subscription
  const unsubWs = wsService.subscribe('guard.status', setGuardStatus);

  // Fallback: Poll every 30s in case WS disconnects
  const pollInterval = setInterval(async () => {
    if (!wsConnected) {
      const data = await api.get('/api/engine/guard-status');
      setGuardStatus(data);
    }
  }, 30000);

  return () => {
    unsubWs();
    clearInterval(pollInterval);
  };
}, [wsConnected]);
```

### Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ENGINE (Python :8000)                                                   │
│                                                                         │
│  GuardService ──► DashboardEventPublisher ──► Redis pub engine:*        │
│  RiskGuardManager ─────────────────────────►                            │
│  PipelineHealthTracker ────────────────────►                            │
│  EquityTracker ────────────────────────────►                            │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Redis pub/sub
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ BFF (NestJS :8002)                                                      │
│                                                                         │
│  EngineClientService                                                    │
│    .subscribe('guard_status') ──► DashboardGateway                      │
│    .subscribe('state_changed') ──►  .emit('guard.status')               │
│    .subscribe('pipeline_health')──►  .emit('engine.state')              │
│    .subscribe('equity_snapshot')──►  .emit('pipeline.health')           │
│                                                                         │
│  REST Endpoints (fallback)                                              │
│    GET /api/engine/guard-status                                         │
│    GET /api/engine/pipeline-health                                      │
│    GET /api/dashboard/snapshot                                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Socket.IO
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ UI (Next.js :3000)                                                      │
│                                                                         │
│  useGuardStatus()                                                       │
│    WebSocket: subscribe('guard.status')                                 │
│    Fallback: poll GET /api/engine/guard-status every 30s                │
│                                                                         │
│  usePipelineHealth()                                                    │
│    WebSocket: subscribe('pipeline.health')                              │
│    Fallback: poll every 10s                                             │
│                                                                         │
│  useDashboardSnapshot()                                                 │
│    Initial: GET /api/dashboard/snapshot                                 │
│    Updates: merge from position.updated, order.updated, equity.update   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Information Hierarchy (Revised)

```
+------------------------------------------------------------------+
|  ENGINE STATUS BAR (always visible)                               |
|  [ACTIVE] Engine Running | Guards: 4/4 OK | Emergency: [STOP ALL] |
+------------------------------------------------------------------+
|                                                                   |
|  SAFETY & RISK PANEL (left 30%)  |  PERFORMANCE (center 40%)      |
|  +--------------------------+    |  +------------------------+    |
|  | Guard Status             |    |  | Trading KPIs           |    |
|  | - News: OK               |    |  | Win Rate: 62%          |    |
|  | - Funding: OK            |    |  | Profit Factor: 1.8     |    |
|  | - Volatility: OK         |    |  | Sharpe: 1.2 (30d)      |    |
|  | - Daily Loss: 0.3%/2%    |    |  | Max Drawdown: 4.2%     |    |
|  | - Drawdown: 4.2%/10%     |    |  +------------------------+    |
|  +--------------------------+    |  | Equity Curve           |    |
|  | Exposure                 |    |  | [Chart 1D/1W/1M/ALL]   |    |
|  | - Open Positions: 2      |    |  +------------------------+    |
|  | - Total Notional: $5,200 |    |                                |
|  | - Unrealized P&L: +$82   |    |  PIPELINE HEALTH (right 30%)   |
|  | - Daily P&L: +$156       |    |  +------------------------+    |
|  +--------------------------+    |  | Last Candle            |    |
|                                  |  | BTCUSDT:15m 12:15:00   |    |
|  EMERGENCY CONTROLS              |  | ETHUSDT:15m 12:15:02   |    |
|  +---------------------------+   |  | Lag: 2.1s avg          |    |
|  | [EMERGENCY CLOSE ALL]     |   |  | Last Decision: 12:14   |    |
|  | Scope: [ALL] [SPOT] [FUT] |   |  +------------------------+    |
|  +---------------------------+   |                                |
+------------------------------------------------------------------+
|  POSITIONS & ORDERS (bottom)                                      |
|  [Positions Tab] [Orders Tab] [Trade History Tab]                 |
+------------------------------------------------------------------+
```

---

## Canonical Equity/P&L Model

### Definitions

```python
# Total Equity (point-in-time)
total_equity = sum(balance.usd_value for balance in balances)
             + sum(position.unrealized_pnl for position in open_positions)

# Realized P&L (from closed trades)
realized_pnl = sum(order.realized_pnl for order in filled_orders where is_closing_order)

# Unrealized P&L
unrealized_pnl = calculate_unrealized_pnl(position, current_price)
# Long: (current_price - entry_price) * quantity
# Short: (entry_price - current_price) * quantity

# Daily P&L
daily_pnl = realized_pnl_today + unrealized_pnl_change_today

# Drawdown
current_drawdown = (peak_equity - current_equity) / peak_equity * 100
```

### Data Sources

| Metric | Source | Location |
|--------|--------|----------|
| Balances | Binance API / DB cache | `balances` table |
| Positions | Trading service state | `TradingService.positions` |
| Realized P&L | Order fills | `orders` table with realized_pnl column |
| Unrealized P&L | Real-time calculation | `position_tracker.calculate_unrealized_pnl()` |
| Peak Equity | Periodic snapshots | `equity_snapshots` table (NEW) |
| Funding Paid | Futures only | `funding_payments` table (NEW) |

### New Database Tables

```sql
-- Equity history for drawdown/equity curve
CREATE TABLE equity_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_equity DECIMAL(18,8) NOT NULL,
    realized_pnl_cumulative DECIMAL(18,8) NOT NULL,
    unrealized_pnl DECIMAL(18,8) NOT NULL,
    fees_cumulative DECIMAL(18,8) DEFAULT 0,
    funding_cumulative DECIMAL(18,8) DEFAULT 0,
    open_positions_count INTEGER DEFAULT 0,
    UNIQUE(timestamp)
);
CREATE INDEX idx_equity_snapshots_ts ON equity_snapshots(timestamp DESC);

-- Snapshot frequency: Every 15 minutes OR on position open/close
```

### Statistical Metric Gates

| Metric | Minimum Data Required | Display When Insufficient |
|--------|----------------------|---------------------------|
| Win Rate | 10 closed trades | "10+ trades needed" |
| Profit Factor | 10 closed trades | "10+ trades needed" |
| Sharpe Ratio | 30 trades AND 7 days | "Insufficient data (N/30 trades, D/7 days)" |
| Max Drawdown | 24 hours of equity data | Show available, note "24h minimum" |

---

## Files to Change

### Frontend (app/ui/src/)

| File | Action | Purpose |
|------|--------|---------|
| `components/Dashboard/Dashboard.tsx` | MODIFY | New safety-first layout |
| `components/Dashboard/calculations.ts` | MODIFY | Add KPI calculations with min-N gates |
| `components/Dashboard/EngineStatusBar.tsx` | CREATE | Top banner with engine state + quick actions |
| `components/Dashboard/GuardStatusPanel.tsx` | CREATE | All guard states with blocked reasons |
| `components/Dashboard/ExposurePanel.tsx` | CREATE | Positions count, notional, P&L summary |
| `components/Dashboard/TradingKPIs.tsx` | CREATE | Win rate, profit factor, Sharpe, drawdown |
| `components/Dashboard/EquityCurve.tsx` | CREATE | Lightweight Charts line series |
| `components/Dashboard/PipelineHealth.tsx` | CREATE | Last candle per symbol, lag metrics |
| `components/Dashboard/EmergencyControls.tsx` | CREATE | Full state machine with scope selector |
| `hooks/useDashboardSnapshot.ts` | CREATE | Unified data fetch + WS updates |
| `hooks/useGuardStatus.ts` | CREATE | Guard status polling/subscription |
| `hooks/useEmergencySell.ts` | CREATE | Emergency close state machine |
| `hooks/usePipelineHealth.ts` | CREATE | Pipeline health subscription |
| `services/dashboardApi.ts` | CREATE | API client for dashboard endpoints |
| `types/dashboard.ts` | CREATE | All dashboard-related types |

### Backend (app/bff/src/)

| File | Action | Purpose |
|------|--------|---------|
| `dashboard/dashboard.module.ts` | CREATE | Dashboard feature module |
| `dashboard/dashboard.controller.ts` | CREATE | Unified dashboard endpoints |
| `dashboard/dashboard.service.ts` | CREATE | Aggregate all dashboard data |
| `dashboard/dashboard.gateway.ts` | CREATE | WebSocket gateway for real-time dashboard events |
| `dashboard/dto/dashboard-snapshot.dto.ts` | CREATE | Snapshot response DTO |
| `dashboard/dto/guard-status.dto.ts` | CREATE | Guard status DTO |
| `dashboard/dto/emergency-close.dto.ts` | CREATE | Emergency close request/response |
| `engine/engine.module.ts` | CREATE | Engine proxy module |
| `engine/engine.controller.ts` | CREATE | Guard status, pipeline health endpoints |
| `engine/engine-client.service.ts` | CREATE | HTTP client to Python engine |
| `trading/trading.gateway.ts` | MODIFY | Add engine status broadcasts |
| `trading/trading.service.ts` | MODIFY | Add emergency close all method |
| `app.module.ts` | MODIFY | Import DashboardModule |

### Backend (app/engine/)

| File | Action | Purpose |
|------|--------|---------|
| `monitoring/dashboard_events.py` | CREATE | Publish guard/state/health events to Redis |
| `monitoring/pipeline_health.py` | CREATE | Track candle processing lag per symbol/tf |
| `monitoring/endpoints.py` | MODIFY | Add /guard-status, /pipeline-health endpoints |
| `core/equity_tracker.py` | CREATE | Periodic equity snapshots |
| `core/engine_state.py` | CREATE | ACTIVE/PAUSED/STOPPED state machine |
| `adapters/db/equity_repository.py` | CREATE | Equity snapshots persistence |
| `adapters/redis/event_publisher.py` | MODIFY | Add dashboard event publishing methods |
| `main.py` | MODIFY | Initialize DashboardEventPublisher on startup |

### Router (app/router/)

| File | Action | Purpose |
|------|--------|---------|
| `internal/orders/bracket.go` | MODIFY | CloseAllPositions to support symbol="" for ALL |
| `internal/api/handlers.go` | MODIFY | Add idempotency key support to close_all |

### Database (migrations/)

| File | Action | Purpose |
|------|--------|---------|
| `V20250120__add_equity_snapshots.sql` | CREATE | New equity_snapshots table |
| `V20250120__add_orders_realized_pnl.sql` | CREATE | Add realized_pnl column to orders |

### Contracts (contracts/)

| File | Action | Purpose |
|------|--------|---------|
| `jsonschema/dashboard_snapshot.v1.schema.json` | CREATE | Dashboard snapshot contract |
| `jsonschema/guard_status.v1.schema.json` | CREATE | Guard status contract |
| `jsonschema/pipeline_health.v1.schema.json` | CREATE | Pipeline health contract |

---

## Implementation Phases

### Phase 0: Data Foundation (Day 1)

**Goal**: Establish canonical data sources before building UI

1. Create `equity_snapshots` migration
2. Implement `EquityTracker` in engine with periodic snapshots
3. Add `realized_pnl` column to orders table
4. Define TypeScript types matching Python models

**Validation**:
```bash
# Migration applies
alembic upgrade head

# Snapshots being created
SELECT COUNT(*) FROM equity_snapshots WHERE timestamp > NOW() - INTERVAL '1 hour';
```

### Phase 1: Safety Layer (Day 2-3)

**Goal**: "Is the system safe?" answered first

1. Expose `GuardService.get_guard_status()` via FastAPI endpoint
2. Create BFF `EngineController` to proxy guard status
3. Implement `GuardStatusPanel.tsx` component
4. Implement `ExposurePanel.tsx` component
5. Implement `EngineStatusBar.tsx` with engine state badge

**Validation**:
```bash
# Guard status endpoint works
curl http://localhost:8000/api/engine/guard-status

# UI shows guard states
pnpm --filter @repo/ui test -- GuardStatusPanel
```

### Phase 2: Emergency Controls (Day 3-4)

**Goal**: Full emergency close state machine

1. Update router `CloseAllPositions` to handle symbol="" (all symbols)
2. Add idempotency key to close_all request
3. Implement BFF emergency close orchestration:
   - Cancel all open orders
   - Close all positions at market
   - Optionally trigger engine stop
4. Implement `EmergencyControls.tsx` with:
   - Scope selector (ALL/SPOT/FUTURES/symbol)
   - Position summary before confirmation
   - Typed "CLOSE ALL" confirmation
   - Progress indicators

**State Machine**:
```
IDLE → (click) → CONFIRMING → (type CLOSE ALL) → EXECUTING → COMPLETED/FAILED
                     ↓                                ↓
                  (cancel)                      (show results)
                     ↓                                ↓
                   IDLE                             IDLE
```

**Validation**:
```bash
# E2E test with paper broker
pnpm --filter @repo/ui test -- EmergencyControls
go test ./internal/api -run TestCloseAllHandler
```

### Phase 3: Performance KPIs (Day 4-5)

**Goal**: Display trading performance with appropriate gates

1. Implement KPI calculations with min-N checks:
   - `calculateWinRate(trades, minTrades=10)`
   - `calculateProfitFactor(trades, minTrades=10)`
   - `calculateSharpeRatio(returns, minTrades=30, minDays=7)`
   - `calculateMaxDrawdown(equityCurve)`
2. Create `TradingKPIs.tsx` component
3. Wire to dashboard snapshot endpoint

**Validation**:
```bash
pnpm --filter @repo/ui test -- calculations.spec.ts
pnpm --filter @repo/ui test -- TradingKPIs
```

### Phase 4: Equity Curve (Day 5-6)

**Goal**: Historical equity visualization

1. Implement `GET /api/dashboard/equity-history` endpoint
2. Query `equity_snapshots` table with time range filter
3. Implement `EquityCurve.tsx` with Lightweight Charts
4. Add time range selector (1D/1W/1M/ALL)

**Validation**:
```bash
# Equity history returns data
curl "http://localhost:8002/api/dashboard/equity-history?range=1W"

pnpm --filter @repo/ui test -- EquityCurve
```

### Phase 5: Pipeline Health (Day 6-7)

**Goal**: "Is the pipeline working?" visibility

1. Implement `PipelineHealthTracker` in engine:
   - Track last candle timestamp per (symbol, timeframe)
   - Track processing lag
   - Track last decision with reason
2. Expose via `GET /api/engine/pipeline-health`
3. Implement `PipelineHealth.tsx` component
4. Add lag warning threshold (> 5s = yellow, > 30s = red)

**Validation**:
```bash
curl http://localhost:8000/api/engine/pipeline-health

pnpm --filter @repo/ui test -- PipelineHealth
```

### Phase 6: Integration & Polish (Day 7-8)

1. Integrate all components into `Dashboard.tsx`
2. WebSocket subscriptions for real-time updates
3. Error boundary and loading states
4. Responsive layout testing
5. Full E2E test with paper trading

---

## Test Coverage

### Calculations (calculations.spec.ts)

| Test | Behavior |
|------|----------|
| `calculateWinRate_returns_percentage` | 6 wins, 4 losses → 60% |
| `calculateWinRate_returns_null_insufficient_trades` | < 10 trades → null |
| `calculateProfitFactor_divides_wins_by_losses` | +300/-100 → 3.0 |
| `calculateProfitFactor_returns_infinity_no_losses` | Only wins → Infinity |
| `calculateSharpeRatio_returns_null_insufficient_data` | < 30 trades → null |
| `calculateSharpeRatio_annualizes_correctly` | Daily returns * sqrt(252) |
| `calculateMaxDrawdown_finds_peak_to_trough` | [100,120,90,110] → 25% |
| `buildEquityCurve_sorts_deduplicates` | Unordered input → sorted |

### Guard Status (GuardStatusPanel.spec.tsx)

| Test | Behavior |
|------|----------|
| `renders_all_guard_types` | News, funding, volatility, daily, drawdown visible |
| `shows_blocked_reason_when_guard_triggered` | Red badge + reason text |
| `shows_ok_when_all_guards_pass` | Green badges |
| `shows_upcoming_news_events` | Event list under news guard |
| `shows_progress_bars_for_limits` | Daily loss 0.3%/2% bar |

### Emergency Controls (EmergencyControls.spec.tsx)

| Test | Behavior |
|------|----------|
| `opens_confirmation_modal_on_click` | Modal appears |
| `shows_position_summary_in_modal` | Count, notional, P&L |
| `requires_typed_confirmation` | Button disabled until "CLOSE ALL" typed |
| `scope_selector_filters_correctly` | SPOT only shows spot positions |
| `executes_cancel_then_close_sequence` | Orders canceled before positions closed |
| `shows_progress_during_execution` | Step indicators |
| `handles_partial_failure` | Some closed, some errored |
| `prevents_double_execution` | Button disabled during execution |

### Pipeline Health (PipelineHealth.spec.tsx)

| Test | Behavior |
|------|----------|
| `shows_last_candle_per_symbol` | BTCUSDT:15m timestamp |
| `shows_lag_with_color_coding` | < 5s green, < 30s yellow, > 30s red |
| `shows_last_decision_timestamp` | With reason code |
| `handles_no_data_gracefully` | "Waiting for data..." |

### Backend (*.spec.ts)

| Test | Behavior |
|------|----------|
| `DashboardService_getSnapshot_aggregates_all_data` | Balances + positions + KPIs |
| `DashboardService_emergencyClose_executes_sequence` | Cancel → close → stop |
| `DashboardController_getSnapshot_returns_200` | Auth required, valid response |
| `DashboardController_emergencyClose_rate_limited` | 429 on rapid requests |
| `EngineController_getGuardStatus_proxies_to_engine` | HTTP call to engine |
| `EquitySnapshotter_persists_every_15_minutes` | Timer triggers save |

---

## API Contracts

### GET /api/dashboard/snapshot

```typescript
interface DashboardSnapshotResponse {
  balances: Balance[];
  positions: Position[];
  recentOrders: Order[];
  kpis: {
    winRate: number | null;        // null if insufficient data
    profitFactor: number | null;
    sharpeRatio: number | null;
    maxDrawdown: number;
    totalTrades: number;
    totalPnL: number;
    dailyPnL: number;
  };
  exposure: {
    openPositionsCount: number;
    totalNotional: number;
    totalUnrealizedPnL: number;
  };
  engineStatus: {
    state: 'ACTIVE' | 'PAUSED' | 'STOPPED';
    autoTrading: boolean;
    lastDecisionAt: string | null;
    lastDecisionReason: string | null;
  };
  updatedAt: string;
}
```

### GET /api/engine/guard-status

```typescript
interface GuardStatusResponse {
  guards: {
    news: {
      status: 'OK' | 'BLOCKED';
      reason: string | null;
      upcomingEvents: Array<{
        eventType: string;
        timestamp: string;
        impact: 'HIGH' | 'MEDIUM' | 'LOW';
        currency: string;
      }>;
    };
    funding: {
      status: 'OK' | 'BLOCKED';
      reason: string | null;
      rates: Record<string, number>;  // symbol -> rate
    };
    volatility: {
      status: 'OK' | 'BLOCKED';
      reason: string | null;
    };
    dailyLoss: {
      status: 'OK' | 'BLOCKED';
      currentPct: number;
      limitPct: number;
    };
    drawdown: {
      status: 'OK' | 'BLOCKED';
      currentPct: number;
      limitPct: number;
    };
    positions: {
      status: 'OK' | 'BLOCKED';
      current: number;
      max: number;
    };
  };
  emergencyStop: boolean;
  emergencyReason: string | null;
}
```

### POST /api/dashboard/emergency-close

```typescript
interface EmergencyCloseRequest {
  scope: 'ALL' | 'SPOT' | 'USD_M' | string;  // string = specific symbol
  stopEngine: boolean;
  idempotencyKey: string;  // UUID, prevents duplicate executions
}

interface EmergencyCloseResponse {
  success: boolean;
  canceledOrders: number;
  closedPositions: number;
  engineStopped: boolean;
  errors: string[];
  executionTimeMs: number;
}
```

### GET /api/engine/pipeline-health

```typescript
interface PipelineHealthResponse {
  symbols: Array<{
    symbol: string;
    timeframe: string;
    lastCandleTime: string;
    lastProcessedTime: string;
    lagMs: number;
  }>;
  lastDecision: {
    timestamp: string;
    symbol: string;
    action: 'BUY' | 'SELL' | 'HOLD';
    reason: string;
  } | null;
  averageLagMs: number;
  status: 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY';
}
```

---

## Validation Checklist

```bash
# Frontend
pnpm --filter @repo/ui typecheck
pnpm --filter @repo/ui lint
pnpm --filter @repo/ui test
pnpm --filter @repo/ui build

# Backend BFF
pnpm --filter @repo/bff typecheck
pnpm --filter @repo/bff lint
pnpm --filter @repo/bff test
pnpm --filter @repo/bff build

# Engine
cd app/engine && ruff check . && mypy . && pytest tests/ -v

# Router
cd app/router && go test ./...

# Integration
make test-integration
```

---

## Open Questions (Require Decision)

1. **Equity snapshot frequency**: Every 15 minutes OR on every position change?
   - Recommendation: Both - timer + on position open/close events

2. **Emergency close default scope**: ALL, or require explicit selection?
   - Recommendation: Require selection to prevent accidents

3. **Pipeline health polling interval**: How often to refresh?
   - Recommendation: WebSocket push on change, fallback to 10s polling

4. **Sharpe ratio period**: Rolling 30 days or since inception?
   - Recommendation: Configurable with default 30 days

---

## Dependencies

- Lightweight Charts (already installed)
- class-validator (already in BFF)
- No new external dependencies required

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Emergency close fails mid-execution | Idempotency key allows retry; show partial results |
| Equity snapshots miss price gaps | Snapshot on position events, not just timer |
| Guard status stale | WebSocket push + fallback polling |
| KPIs misleading with few trades | Min-N gates with clear "insufficient data" messaging |
| User triggers emergency close accidentally | Typed confirmation + scope selection required |
