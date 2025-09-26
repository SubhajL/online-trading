# Trading System Test Plan

## Overview
This test plan covers the complete trading system implementation, focusing on critical paths and integration points.

## System Architecture to Test

```
Binance WS → Ingestor → TimescaleDB → Features → SMC → Decision → Router → Orders
                ↓                         ↓        ↓        ↓
              Events                   Events   Events   Events
                ↓                         ↓        ↓        ↓
              BFF ←────────────────────────────────────────→ UI
                ↓
            Telegram
```

## Test Categories

### 1. Unit Tests (Component-Level)

#### Python Engine (`app/engine/`)
- [ ] **Ingestor** (`app/engine/ingest/`)
  - WebSocket connection handling
  - Candle deduplication
  - REST backfill logic
  - Error recovery

- [ ] **Features** (`app/engine/features/`)
  - EMA/SMA calculations
  - RSI accuracy
  - MACD signals
  - ATR volatility
  - Bollinger Bands

- [ ] **SMC Module** (`app/engine/smc/`)
  - Pivot detection (HH/HL/LH/LL)
  - CHOCH/BOS identification
  - Order Block detection
  - Fair Value Gap logic
  - Zone strength calculation

- [ ] **Decision Engine** (`app/engine/decision/`)
  - Signal fusion logic
  - Position sizing (0.5% risk)
  - Risk management rules
  - Confidence scoring

- [ ] **Paper Broker** (`app/engine/paper/`)
  - Order execution simulation
  - Slippage modeling
  - P&L tracking
  - Position management

#### Go Router (`app/router/`)
- [ ] Exchange info parsing
- [ ] Order validation
- [ ] Signature generation
- [ ] Idempotency handling
- [ ] Error responses

#### TypeScript BFF/UI (`app/bff/`, `app/ui/`)
- [ ] WebSocket connection management
- [ ] Alert handling
- [ ] Snapshot generation
- [ ] Chart rendering
- [ ] Order form validation

### 2. Integration Tests (Multi-Component)

#### Data Pipeline Tests
```python
# tests/integration/test_data_pipeline.py
class TestDataPipeline:
    async def test_candle_to_features_flow(self):
        """Test: Candle → Features calculation → DB storage"""

    async def test_features_to_smc_flow(self):
        """Test: Features → SMC events → Zones"""

    async def test_smc_to_signals_flow(self):
        """Test: SMC events → Signal generation → Decision"""
```

#### Event Bus Tests
```python
# tests/integration/test_event_bus.py
class TestEventBus:
    async def test_event_propagation(self):
        """Test events flow through the system correctly"""

    async def test_subscriber_error_handling(self):
        """Test system continues when one subscriber fails"""
```

#### Database Tests
```python
# tests/integration/test_database.py
class TestDatabase:
    async def test_concurrent_writes(self):
        """Test multiple services writing simultaneously"""

    async def test_timescale_partitioning(self):
        """Test hypertable partitioning works correctly"""
```

### 3. End-to-End Tests (Full System)

#### Trading Flow Test
```typescript
// tests/e2e/trading-flow.spec.ts
test('complete trading cycle', async () => {
  // 1. Inject test candles
  await injectCandles([/* bullish pattern */])

  // 2. Wait for SMC detection
  const smcEvent = await waitFor('smc_events.v1')
  expect(smcEvent.type).toBe('BOS')

  // 3. Verify signal generation
  const signal = await waitFor('signals_raw.v1')
  expect(signal.confidence).toBeGreaterThan(0.7)

  // 4. Check decision
  const decision = await waitFor('decision.v1')
  expect(decision.position_size).toBeLessThan(accountBalance * 0.005)

  // 5. Verify order sent
  const order = await waitFor('order_update.v1')
  expect(order.status).toBe('NEW')
})
```

#### Alert Flow Test
```typescript
// tests/e2e/alert-flow.spec.ts
test('signal to alert with snapshot', async () => {
  // 1. Generate signal
  const signalId = await generateTestSignal()

  // 2. Verify snapshot created
  const snapshot = await getSnapshot(signalId)
  expect(snapshot.imagePath).toMatch(/\.png$/)

  // 3. Check alert in UI
  const alert = await getAlert(signalId)
  expect(alert.imageUrl).toBeDefined()

  // 4. Verify Telegram notification
  const telegramMessage = await mockTelegram.getLastMessage()
  expect(telegramMessage.photo).toBeDefined()
})
```

### 4. Performance Tests

#### Latency Benchmarks
```javascript
// tests/performance/latency.js
export default function() {
  const start = Date.now()

  // Measure candle → decision latency
  emitCandle()
  const decision = waitForDecision()

  check(decision, {
    'latency < 900ms': () => Date.now() - start < 900
  })
}
```

#### Load Tests
```javascript
// tests/performance/load.js
import { check } from 'k6'

export const options = {
  vus: 10, // 10 parallel symbols
  duration: '5m',
}

export default function() {
  const symbols = ['BTCUSDT', 'ETHUSDT', /* ... */]

  symbols.forEach(symbol => {
    emitCandle(symbol)
  })

  check(response, {
    'no errors': (r) => r.errors === 0,
    'all events processed': (r) => r.processed === r.total
  })
}
```

### 5. Failure & Recovery Tests

#### WebSocket Disconnection
```python
async def test_websocket_recovery():
    """Test system recovers from Binance disconnection"""
    # 1. Start normal operation
    await start_ingestor()

    # 2. Simulate disconnection
    await mock_binance.disconnect()

    # 3. Verify REST backfill triggered
    assert await verify_backfill_started()

    # 4. Reconnect and verify no gaps
    await mock_binance.reconnect()
    assert await verify_no_data_gaps()
```

#### Component Failure
```python
async def test_component_resilience():
    """Test system continues when one component fails"""
    # 1. Kill features service
    await features_service.stop()

    # 2. Verify other services continue
    assert ingestor.is_running()
    assert smc_service.is_running()

    # 3. Restart and verify recovery
    await features_service.start()
    assert await verify_all_services_healthy()
```

### 6. Data Validation Tests

#### Contract Validation
```typescript
// tests/contracts/events.spec.ts
describe('Event Contracts', () => {
  test('candles.v1 schema', () => {
    const event = generateCandleEvent()
    expect(validateSchema(event, candleSchema)).toBe(true)
  })

  test('decision.v1 includes required fields', () => {
    const decision = generateDecisionEvent()
    expect(decision).toHaveProperty('signal_id')
    expect(decision).toHaveProperty('position_size')
    expect(decision).toHaveProperty('risk_amount')
  })
})
```

## Test Execution Strategy

### 1. Continuous Integration (CI)
- **On every commit**: Unit tests, linting
- **On PR**: Unit + Integration tests
- **On merge to main**: Full test suite
- **Nightly**: Performance + Chaos tests

### 2. Test Environments
- **Unit tests**: No external dependencies
- **Integration tests**: Docker containers
- **E2E tests**: Testnet when needed
- **Performance tests**: Dedicated hardware

### 3. Test Data Management
```python
# tests/fixtures/market_data.py
def generate_trend_reversal_candles():
    """Generate candles showing trend reversal pattern"""
    return [
        {'open': 50000, 'high': 50500, 'low': 49800, 'close': 50200},
        {'open': 50200, 'high': 50700, 'low': 50100, 'close': 50600},
        # ... bearish reversal pattern
    ]

def generate_ranging_market_candles():
    """Generate sideways market data"""
    # ...
```

## Critical Test Scenarios

### 1. Money-Critical Tests
- [ ] Position sizing never exceeds 0.5% risk
- [ ] Stop loss orders always created
- [ ] No duplicate orders
- [ ] Correct decimal precision

### 2. Data Integrity Tests
- [ ] No missing candles
- [ ] Deduplication works
- [ ] Time zone handling correct
- [ ] Database constraints enforced

### 3. Performance SLAs
- [ ] Candle → Signal: < 500ms p95
- [ ] Decision → Order: < 300ms p95
- [ ] WebSocket reconnect: < 5s
- [ ] REST backfill rate: > 100 candles/sec

## Test Metrics & Reporting

### Coverage Goals
- Unit tests: > 80% code coverage
- Integration tests: All critical paths
- E2E tests: Happy path + key error cases

### Quality Metrics
```python
# tests/metrics/collector.py
class TestMetrics:
    def collect(self):
        return {
            'test_count': self.count_tests(),
            'coverage': self.get_coverage(),
            'flaky_tests': self.find_flaky_tests(),
            'slowest_tests': self.get_slowest_tests(10),
            'last_run': datetime.now()
        }
```

### Dashboard
- Test execution trends
- Coverage over time
- Flaky test tracking
- Performance regression alerts

## Next Steps

1. **Prioritize**: Start with money-critical and data integrity tests
2. **Implement**: Write missing unit tests for SMC and Decision modules
3. **Integrate**: Set up CI pipeline with GitHub Actions
4. **Monitor**: Deploy test metrics dashboard
5. **Iterate**: Add tests as bugs are found

## Test Implementation Order

### Week 1: Core Logic
1. SMC algorithm unit tests
2. Position sizing tests
3. Risk management tests

### Week 2: Integration
1. Data pipeline flow
2. Event bus reliability
3. Database operations

### Week 3: E2E & Performance
1. Full trading cycle
2. Load testing
3. Latency benchmarks

### Week 4: Resilience
1. Failure recovery
2. Chaos experiments
3. Edge cases