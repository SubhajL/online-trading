# Automated Testing Plan for Trading Platform

## Overview

This document outlines the comprehensive automated testing strategy for the trading platform (engine + router + BFF + UI), identifying which tests can be automated, which require manual intervention, and the infrastructure needed for implementation.

## Test Environment Requirements

### Infrastructure Setup
```yaml
Required Components:
  - Binance Testnet API credentials (spot + futures)
  - Isolated test database instance (TimescaleDB)
  - Binance Testnet WebSocket streams (real data)
  - CI/CD pipeline with parallel test execution
  - Monitoring stack (Prometheus/Grafana) for test metrics
  - Selenium Grid or Playwright for UI automation
  - Load testing infrastructure (K6/Locust)
  - Redis test instance for caching tests
```

### Architecture Clarification
```yaml
Data Flow:
  - Candles: Binance WebSocket → Ingestor → TimescaleDB
  - Orders: Decision Engine → Router → Binance REST API
  - No mocking needed for primary data flow!

When to Use Real vs Mock:
  - Real Binance Testnet: Integration/E2E tests
  - Mock only for: Unit tests, edge cases, chaos testing
```

### Test Data Requirements
- Historical candle data for backtesting validation
- **Economic calendar CSV file** with major events (CPI, NFP, FOMC, ECB, BOE)
  - Format: `event_type,timestamp,impact,currency`
  - Location: `./data/economic_calendar.csv`
  - Must be manually maintained (no external API)
- Synthetic order book data for slippage simulation
- Test account with small balance for live verification

### When to Use Mocking vs Real Services

#### Use Real Binance Testnet For:
- **Integration Tests**: Full pipeline validation
- **E2E Tests**: Complete trading cycle verification
- **Performance Tests**: Realistic latency measurements
- **Regression Tests**: Ensure changes don't break live flow

#### Use Mocks Only For:
- **Unit Tests**: Testing pure logic (SMC math, indicator calculations)
- **Edge Cases**: Simulating rare events (flash crashes, API errors)
- **Chaos Testing**: Network failures, service crashes
- **Speed**: When waiting for real candles would be too slow

Example of appropriate mocking:
```python
# Unit test - mock is appropriate here
def test_smc_pivot_detection():
    """Test pivot logic without waiting for real data"""
    mock_candles = [
        {'high': 100, 'low': 90},   # Candle 1
        {'high': 110, 'low': 95},   # Candle 2 - potential HH
        {'high': 105, 'low': 92},   # Candle 3
    ]
    pivots = detect_pivots(mock_candles, lookback=1)
    assert pivots[1].type == 'HH'  # Higher High
```

## Test Categories by Automation Level

### ✅ Fully Automatable Tests

#### 1. Data Pipeline Integrity
```python
# Integration test using real Binance Testnet WebSocket
@pytest.mark.integration
async def test_real_candle_processing():
    """Test with actual Binance testnet data"""
    # Connect to real Binance testnet WebSocket
    await ingestor.connect_binance_testnet('BTCUSDT', '15m')

    # Wait for real candle close (k.x == true)
    candle = await wait_for_closed_candle(timeout=60)

    # Verify full pipeline processing
    assert await db.candle_exists(candle['t'])  # open_time
    assert await redis.get(f"features:BTCUSDT:15m:{candle['t']}")

    # Check signal generation latency
    signal_time = await get_signal_timestamp(candle['t'])
    assert (signal_time - candle['T']) < 500  # <500ms latency
```

**Coverage:**
- Real WebSocket message handling
- Actual k.x==true detection
- Production deduplication logic
- Real REST API gap backfilling
- Live event bus performance

#### 2. Service Health and Recovery
```bash
# Automated with Docker + health check scripts
make test-service-recovery
# Systematically kills each service, validates auto-recovery
```

**Test Cases:**
- Individual service restart recovery
- Database connection pool recovery
- Redis cache failure handling
- WebSocket reconnection logic
- Circuit breaker behavior

#### 3. Multi-Symbol Performance
```python
# Automated load test with pytest-benchmark
def test_multi_symbol_latency():
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT',
               'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT',
               'DOTUSDT', 'MATICUSDT']  # 10+ symbols

    results = run_parallel_pipelines(symbols)
    assert measure_p95_latency(results) < 900  # ms
    assert memory_usage() < 4_000_000_000  # 4GB
```

#### 4. Configuration Validation
```yaml
# Automated config validation test cases
invalid_configs:
  - name: "excessive_risk"
    config: {risk_per_trade: 2.0}  # >0.5%
    expected_error: "Risk per trade exceeds maximum 0.5%"

  - name: "invalid_leverage"
    config: {max_leverage: 10}  # >3x
    expected_error: "Maximum leverage cannot exceed 3x"

  - name: "missing_api_keys"
    config: {}  # no API credentials
    expected_error: "Required API keys not configured"
```

#### 5. Mathematical Accuracy
```python
# Golden vector tests for indicators
def test_indicator_calculations():
    """Compare against verified reference implementations"""
    candles = load_test_candles('BTCUSDT_15m_1000.json')

    # Test each indicator
    assert calculate_ema(candles, 21) == golden_ema_21
    assert calculate_rsi(candles, 14) == golden_rsi_14
    assert calculate_macd(candles) == golden_macd
    assert calculate_atr(candles, 14) == golden_atr_14
```

#### 6. Order Management Logic
```go
// Router order validation tests
func TestOrderRounding(t *testing.T) {
    tests := []struct {
        name     string
        symbol   string
        quantity float64
        price    float64
        expected Order
    }{
        {
            name:     "BTCUSDT spot rounding",
            symbol:   "BTCUSDT",
            quantity: 0.00123456,
            price:    50123.456,
            expected: Order{
                Quantity: "0.00123",  // Round to LOT_SIZE
                Price:    "50123.46", // Round to PRICE_FILTER
            },
        },
    }
}
```

### ⚠️ Semi-Automated Tests (Automated + Manual Verification)

#### 1. End-to-End Trade Execution
```python
# Fully automated on Binance Testnet
@pytest.mark.testnet
async def test_full_trading_cycle():
    """Real testnet trading with actual WebSocket + REST"""
    # 1. Wait for real SMC signal from live testnet data
    signal = await wait_for_smc_signal(
        symbol='BTCUSDT',
        timeframe='15m',
        pattern='BOS'  # Break of Structure
    )

    # 2. Verify decision engine processes it
    decision = await wait_for_decision(signal.id)
    assert decision.position_size > 0
    assert decision.position_size <= account_balance * 0.005  # 0.5% risk

    # 3. Track order through router to Binance
    order_updates = await track_order_lifecycle(decision.order_id)

    # 4. Verify real testnet execution
    assert order_updates[-1]['status'] == 'FILLED'
    assert 'BTCUSDT-TESTNET' in order_updates[-1]['symbol']

    # 5. Confirm bracket orders placed
    tp_orders = await get_related_orders(decision.order_id, 'TAKE_PROFIT')
    sl_order = await get_related_orders(decision.order_id, 'STOP_LOSS')
    assert len(tp_orders) == 2  # TP ladder
    assert sl_order.type == 'STOP_MARKET'

# Manual verification needed:
# - Execute one $10-50 REAL MAINNET trade (not testnet)
# - Verify actual Binance mainnet fees
# - Check real market slippage
```

#### 2. UI Real-Time Updates
```javascript
// Automated visual regression with Playwright
test('chart updates smoothly on price changes', async ({ page }) => {
  await page.goto('/trading/BTCUSDT');

  // Automated: functional verification
  await mockPriceUpdate(50000, 50100);
  await expect(page.locator('.price')).toHaveText('50,100.00');
  await expect(page.locator('.chart')).toHaveScreenshot('price-update.png');

  // Manual verification needed:
  // - Chart animation smoothness
  // - No visual glitches during rapid updates
  // - Mobile touch responsiveness
});
```

#### 3. Risk Management Validation
```python
# Automated limit checking
def test_risk_limits():
    account = {'balance': 10000, 'equity': 9500}

    # Test position sizing
    position = calculate_position_size(
        account=account,
        entry=50000,
        stop_loss=49500,
        confidence=0.8
    )
    assert position.risk_amount <= account['equity'] * 0.005  # 0.5%

    # Test daily drawdown
    daily_loss = -280  # $280 loss
    assert should_halt_trading(account, daily_loss) == False

    daily_loss = -350  # Exceeds 3% limit
    assert should_halt_trading(account, daily_loss) == True

# Manual verification needed:
# - Emergency "CLOSE ALL" button during high volatility
# - Behavior when multiple positions hit stops simultaneously
# - System response during flash crash scenarios
```

### 🚫 Manual-Only Tests

#### 1. Real Money Validation
- **Live Trade Execution**: Place $10-50 trades to verify:
  - Actual fill prices vs expected
  - Exchange fee calculations
  - Slippage in various market conditions
  - Order rejection handling

#### 2. Economic Calendar Maintenance
- **Update CSV File**: Manually update `./data/economic_calendar.csv` with:
  - Upcoming CPI, NFP, FOMC meeting dates
  - ECB and BOE policy meetings
  - Format: `event_type,timestamp,impact,currency`
- **Verify Blackout Windows**: Test trading halts 30min before/after events
- **No External API**: Must maintain manually (no ForexFactory/Investing.com integration)

#### 3. Visual/UX Quality
- **Chart Readability**: During high volatility periods
- **Mobile Experience**: On actual iOS/Android devices
- **Notification Timing**: Push notifications arrive promptly
- **Dark Mode**: All UI elements properly styled

#### 4. Business Continuity
- **Disaster Recovery Drill**: Annual full system recovery
- **Manual Trading Fallback**: Practice manual order entry
- **Communication Protocols**: Team notification procedures
- **Regulatory Compliance**: Audit trail completeness

#### 5. Security Testing
- **API Key Rotation**: Quarterly key rotation procedure
- **Access Control Audit**: Role-based permissions review
- **Penetration Testing**: Annual third-party security audit
- **Log Sanitization**: Verify no sensitive data in logs

## Implementation Phases

### Phase 1: Foundation (Week 1)
```bash
# Setup test infrastructure
make test-infra-setup

# Core unit tests
pytest tests/unit/           # Python: SMC, indicators, risk
go test ./...               # Go: router, order management
jest tests/contracts/       # TypeScript: schema validation

# Basic integration tests
npm run test:integration    # Service communication
```

### Phase 2: Data Pipeline (Week 2)

#### Additional Tests for Robustness

```python
# tests/integration/test_websocket_resilience.py
class TestWebSocketResilience:
    async def test_websocket_reconnection(self):
        """Test automatic reconnection after disconnect"""
        # Start with active connection
        await ingestor.connect_binance_testnet('BTCUSDT', '15m')

        # Force disconnect
        await ingestor.disconnect()
        await asyncio.sleep(5)

        # Should auto-reconnect
        await ingestor.wait_for_reconnection(timeout=30)

        # Verify no missed candles
        gaps = await db.find_candle_gaps('BTCUSDT', '15m')
        assert len(gaps) == 0

    async def test_retry_logic_with_backoff(self):
        """Test exponential backoff on repeated failures"""
        retry_times = []

        async def track_retries(event):
            retry_times.append(time.time())

        ingestor.on('retry', track_retries)

        # Simulate network failure
        await simulate_network_failure(duration=60)

        # Verify exponential backoff
        for i in range(1, len(retry_times)):
            gap = retry_times[i] - retry_times[i-1]
            expected_gap = min(2 ** i, 60)  # Max 60s
            assert abs(gap - expected_gap) < 1

# tests/integration/test_data_pipeline.py
class TestDataPipeline:
    async def test_real_websocket_flow(self):
        """Test with real Binance testnet WebSocket"""
        # Connect to actual testnet stream
        await ingestor.start_testnet_streams([
            'BTCUSDT@kline_15m',
            'ETHUSDT@kline_15m',
        ])

        # Wait for real closed candles
        btc_candle = await wait_for_closed_candle('BTCUSDT', '15m')
        eth_candle = await wait_for_closed_candle('ETHUSDT', '15m')

        # Verify persistence
        assert await db.candle_exists('BTCUSDT', btc_candle['t'])
        assert await db.candle_exists('ETHUSDT', eth_candle['t'])

    async def test_gap_detection_and_backfill(self):
        """Test real REST backfill when WebSocket has gaps"""
        # Simulate connection drop
        await ingestor.disconnect_websocket()
        await asyncio.sleep(120)  # Miss ~2 candles

        # Reconnect and verify backfill
        await ingestor.reconnect_with_backfill()

        # Check gaps were filled from REST
        gaps = await db.find_candle_gaps('BTCUSDT', '15m')
        assert len(gaps) == 0
```

### Phase 3: Trading Logic (Week 3)

#### Economic Calendar Integration Tests

```python
# tests/integration/test_news_guards.py
class TestNewsGuards:
    async def test_news_guard_blocks_trading(self):
        """Test that upcoming news events block new trades"""
        # Add NFP event 10 minutes in future
        event_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        await add_economic_event(
            event_type="NFP",
            timestamp=event_time,
            blackout_before=30,
            blackout_after=30
        )

        # Generate a valid signal
        signal = await generate_buy_signal('BTCUSDT')

        # Decision engine should block due to news
        decision = await decision_engine.evaluate(signal)
        assert decision.blocked == True
        assert decision.block_reason == "High-impact news event window"

    async def test_existing_positions_during_news(self):
        """Test handling of open positions during news"""
        # Create an open position
        position = await create_test_position('BTCUSDT', side='BUY')

        # Add news event starting now
        await add_economic_event("FOMC", datetime.now(timezone.utc))

        # Check position management
        action = await position_manager.evaluate_during_news(position)
        assert action in ['HOLD', 'CLOSE', 'TIGHTEN_STOP']
```

### Phase 3: Trading Logic (Week 3) - Original Tests
```typescript
// tests/e2e/trading.spec.ts
describe('Trading Flow', () => {
  test('signal generation to order execution', async () => {
    // Mock market conditions
    await setupMarketScenario('uptrend_with_pullback');

    // Verify full flow
    await expectSignalGeneration();
    await expectDecisionWithRiskLimits();
    await expectOrderExecution();
    await expectPositionTracking();
  });
});
```

### Phase 4: Load Testing (Week 4)
```javascript
// k6/scenarios/multi-symbol-load.js
import { check, group } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 symbols
    { duration: '5m', target: 10 },   // Stay at 10 symbols
    { duration: '2m', target: 50 },   // Spike to 50 symbols
    { duration: '5m', target: 50 },   // Sustained high load
    { duration: '2m', target: 0 },    // Ramp down
  ],
};

export default function() {
  group('websocket load', () => {
    // Test implementation
  });
}
```

### Phase 5: Chaos Engineering (Week 5)
```yaml
# chaos/experiments/service-failure.yaml
experiments:
  - name: "Router failure during order"
    target: "router"
    action: "pod-kill"
    expected: "Order retry with idempotency"

  - name: "Database latency spike"
    target: "postgres"
    action: "network-delay"
    latency: "500ms"
    expected: "Graceful degradation"
```

#### Test Data Cleanup

```python
# tests/fixtures/database.py
import pytest
from contextlib import contextmanager

@pytest.fixture(scope='function')
def clean_test_db(test_db):
    """Clean database between test runs"""
    yield test_db

    # Cleanup after test
    with test_db.connect() as conn:
        conn.execute("""
            TRUNCATE TABLE
            candles,
            indicators,
            smc_events,
            zones,
            signals,
            orders,
            positions
            CASCADE;
        """)

@pytest.fixture(scope='session')
def isolated_test_environment():
    """Create isolated environment for each test session"""
    # Create unique test database
    test_db_name = f"test_trading_{uuid.uuid4().hex[:8]}"
    create_test_database(test_db_name)

    yield test_db_name

    # Cleanup
    drop_test_database(test_db_name)

# Usage in tests
def test_full_trading_cycle(clean_test_db, isolated_test_environment):
    # Test runs with clean database
    # No interference from other tests
```

## Continuous Integration Pipeline

```yaml
# .github/workflows/automated-tests.yml
name: Automated Trading Platform Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 */4 * * *'  # Every 4 hours

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        component: [engine, router, bff, ui]
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: make test-unit-${{ matrix.component }}

  integration-tests:
    needs: unit-tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:2.11-pg15
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
    steps:
      - name: Run integration tests
        run: make test-integration

  e2e-testnet:
    needs: integration-tests
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Run E2E tests on testnet
        run: make test-e2e-testnet
        env:
          BINANCE_TESTNET_KEY: ${{ secrets.BINANCE_TESTNET_KEY }}
          BINANCE_TESTNET_SECRET: ${{ secrets.BINANCE_TESTNET_SECRET }}

  performance-tests:
    runs-on: [self-hosted, high-memory]
    if: github.event_name == 'schedule'
    steps:
      - name: Run performance benchmarks
        run: make test-performance
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: performance-metrics
          path: test-results/performance/
```

## Test Metrics and Reporting

### Key Metrics to Track
```python
# tests/metrics/collector.py
class TestMetricsCollector:
    def collect_test_health(self):
        return {
            # Coverage metrics
            'line_coverage': self.get_line_coverage(),
            'branch_coverage': self.get_branch_coverage(),
            'mutation_score': self.get_mutation_testing_score(),

            # Reliability metrics
            'flaky_test_rate': self.calculate_flakiness(),
            'false_positive_rate': self.track_false_positives(),
            'test_execution_time': self.measure_runtime(),

            # Trading-specific metrics
            'strategy_accuracy': self.backtest_vs_live_correlation(),
            'latency_regression': self.detect_performance_regression(),
            'api_mock_coverage': self.verify_mock_completeness(),
        }
```

### Test Results Dashboard
```sql
-- Grafana query for test trends
SELECT
    date_trunc('day', created_at) as date,
    component,
    COUNT(*) FILTER (WHERE status = 'passed') as passed,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    COUNT(*) FILTER (WHERE status = 'flaky') as flaky,
    AVG(duration_ms) as avg_duration,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration
FROM test_runs
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY date, component
ORDER BY date DESC, component;
```

## Manual Testing Checklist

### Pre-Release Manual Tests
- [ ] Real money test trade ($10-50) on mainnet
- [ ] Visual inspection of charts on 3 devices (desktop, tablet, mobile)
- [ ] Emergency stop button test during volatile market
- [ ] API key rotation without service interruption
- [ ] Full disaster recovery drill (quarterly)
- [ ] Security audit findings review
- [ ] Regulatory compliance documentation update
- [ ] Performance during major news event

### Monthly Manual Reviews
- [ ] Error log analysis for unhandled exceptions
- [ ] Database query performance review
- [ ] WebSocket reconnection stability
- [ ] Memory leak detection
- [ ] Cost analysis (cloud resources + trading fees)

## Success Criteria

### Automation Goals
- **Unit Test Coverage**: >90% for core trading logic
- **Integration Test Coverage**: >80% for service communication
- **E2E Test Coverage**: >70% for critical user journeys
- **Test Execution Time**: <15 minutes for PR validation
- **Flaky Test Rate**: <2% of total test suite
- **Performance Regression Detection**: Within 5% threshold

### Platform Stability Targets
- **Candle → Signal Latency**: <500ms p95
- **Signal → Order Latency**: <300ms p95
- **Order Fill Rate**: >98% on testnet
- **WebSocket Uptime**: >99.9% (excluding exchange downtime)
- **Data Pipeline Accuracy**: 100% (no missed candles)

## Maintenance and Evolution

### Weekly Tasks
- Review flaky test reports
- Update test data fixtures
- Verify mock accuracy against live APIs
- Performance benchmark review

### Monthly Tasks
- Dependency updates for test frameworks
- Chaos experiment rotation
- Test coverage gap analysis
- Manual test checklist execution

### Quarterly Tasks
- Full disaster recovery test
- Security audit preparation
- Test infrastructure cost review
- Testing strategy retrospective

---

*Last Updated: 2025-01-25*
*Version: 1.0*
*Owner: QA Team*