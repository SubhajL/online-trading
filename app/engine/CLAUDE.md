# Python Trading Engine

**Technology**: Python 3.11+ | FastAPI | AsyncIO | Pydantic
**Entry Point**: `app/engine/main.py`
**Parent Context**: This extends [../../CLAUDE.md](../../CLAUDE.md)

---

## Development Commands

### This Package

```bash
# From app/engine directory
python -m pytest tests/ -v                    # Run all tests
python -m pytest tests/unit/ -v               # Unit tests only
python -m pytest tests/integration/ -v        # Integration tests
python -m pytest tests/unit/test_file.py -v   # Specific file

# Linting and formatting
ruff check .                                  # Lint
ruff check . --fix                           # Auto-fix
ruff format .                                # Format
mypy .                                       # Type check
```

### From Root

```bash
make dev-engine          # Start with hot reload (uvicorn)
make test-engine         # Run pytest with coverage
make lint                # Lint all (includes engine)
make typecheck           # Type check all (includes mypy)
```

### Pre-PR Checklist

```bash
ruff check . && ruff format --check . && mypy . && pytest tests/ -v
```

---

## Architecture

### Directory Structure

```
app/engine/
├── adapters/                # External integrations
│   ├── alert/              # Telegram, LINE alerts
│   ├── db/                 # TimescaleDB adapter
│   ├── redis/              # Redis cache
│   └── router_client/      # Go router HTTP client
├── backtest/               # Vectorized backtesting
│   ├── backtest_engine.py  # Main backtester
│   ├── wfo.py              # Walk-forward optimization
│   └── metrics.py          # Performance metrics
├── core/                   # Shared infrastructure
│   ├── database.py         # DB connection pool
│   ├── error_handling.py   # Error management
│   ├── security.py         # Validation rules
│   └── tracing.py          # Distributed tracing
├── decision/               # Trading decisions
│   ├── service.py          # Decision service
│   ├── position_sizer.py   # Position sizing logic
│   └── risk_guards.py      # Risk management
├── delivery/               # Alert delivery
├── features/               # Technical indicators
│   └── indicators.py       # EMA, RSI, MACD, ATR, BB
├── ingest/                 # Data ingestion
│   └── binance_ws.py       # Binance WebSocket client
├── monitoring/             # Health & metrics
│   ├── health.py           # Health checks
│   ├── metrics.py          # Prometheus metrics
│   └── endpoints.py        # FastAPI endpoints
├── news_funding_guards/    # Risk guards
├── paper/                  # Paper trading
│   └── broker.py           # Simulated broker
├── preflight/              # Startup checks
├── regime_vol/             # Market regime detection
├── retest/                 # Zone retest analysis
├── smc/                    # Smart Money Concepts
│   ├── pivots.py           # HH/HL/LH/LL detection
│   ├── structure.py        # CHOCH/BOS detection
│   └── engine.py           # SMC orchestrator
├── tests/                  # Test suite
│   ├── unit/               # Pure logic tests
│   ├── integration/        # DB-touching tests
│   ├── e2e/                # End-to-end tests
│   ├── chaos/              # Chaos engineering
│   └── performance/        # Benchmarks
├── bus.py                  # In-memory event bus
├── models.py               # Pydantic models & enums
├── types.py                # Type definitions
└── main.py                 # FastAPI application
```

### Code Organization Patterns

#### Event Bus Pattern

```python
# ✅ DO: Subscribe to events
async def on_candle(event: CandleEvent) -> None:
    features = calculate_features(event)
    await bus.publish("features.v1", features)

bus.subscribe("candles.v1", on_candle)

# ❌ DON'T: Direct function calls between modules
# features = feature_module.process(candle)  # Avoid coupling
```

#### Pydantic Models

```python
# ✅ DO: Use Pydantic for all events
class CandleEvent(BaseModel):
    venue: str
    symbol: str
    timeframe: TimeFrame
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

# ✅ DO: Use Enums for fixed values
class TimeFrame(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
```

#### Async Patterns

```python
# ✅ DO: Use async/await consistently
async def fetch_candles(symbol: str) -> list[Candle]:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# ❌ DON'T: Block the event loop
# time.sleep(1)  # Never use
# requests.get(url)  # Use aiohttp instead
```

#### Error Handling

```python
# ✅ DO: Use custom exceptions
class OrderValidationError(TradingError):
    """Raised when order validation fails."""
    pass

# ✅ DO: Handle errors at boundaries
try:
    await router_client.submit_order(order)
except RouterError as e:
    logger.error("Order submission failed", error=str(e))
    await error_manager.handle(e)
```

---

## Key Files

### Core Files (understand these first)

- `bus.py` - In-memory async event bus, pub/sub pattern
- `models.py` - All Pydantic models and enums
- `types.py` - Type aliases and protocols
- `main.py` - FastAPI app, startup/shutdown hooks

### Trading Logic

- `decision/service.py` - Signal fusion, final trading decisions
- `decision/position_sizer.py` - ATR-scaled position sizing
- `decision/risk_guards.py` - Drawdown limits, exposure checks

### Smart Money Concepts

- `smc/pivots.py` - HH/HL/LH/LL detection with configurable lookback
- `smc/structure.py` - CHOCH/BOS sequence detection
- `smc/engine.py` - Orchestrates SMC analysis pipeline

### Data Flow

- `ingest/binance_ws.py` - WebSocket connection, only emit on `k.x == true`
- `features/indicators.py` - Stateless indicator calculations
- `retest/engine.py` - Zone retest with confluence checking

---

## Quick Search Commands

### Find Functions

```bash
# Find async function definitions
rg -n "^async def " app/engine/

# Find class definitions
rg -n "^class " app/engine/

# Find event handlers
rg -n "subscribe\(" app/engine/

# Find Pydantic models
rg -n "class.*\(BaseModel\)" app/engine/
```

### Find Tests

```bash
# Find unit tests
fd -g "test_*.py" app/engine/tests/unit/

# Find tests for specific module
rg -n "def test_" app/engine/tests/unit/test_decision.py

# Run tests matching pattern
pytest -k "position_sizer" -v
```

### Find Imports

```bash
# Find where a module is imported
rg -n "from.*smc import|import.*smc" app/engine/

# Find external dependencies
rg -n "^from|^import" app/engine/decision/service.py | head -20
```

---

## Common Gotchas

- **Decimal vs Float**: Always use `Decimal` for prices/quantities to avoid floating point errors
- **Timezone Awareness**: All datetimes must be UTC-aware: `datetime.now(timezone.utc)`
- **Candle Emission**: Only emit candles when `k.x == true` (closed candle)
- **Database Keys**: Unique on `(venue, symbol, tf, open_time)`
- **Async Context**: Never use `time.sleep()` or blocking I/O in async functions
- **Event Bus**: Events are processed in subscription order; don't assume parallelism

---

## Testing Guidelines

### Unit Tests

- Location: `tests/unit/test_<module>.py`
- Framework: pytest + pytest-asyncio
- Pattern: Test pure logic, no DB/network

```python
# ✅ DO: Test pure functions
def test_calculate_atr_returns_expected_value():
    candles = [make_candle(h=100, l=90, c=95) for _ in range(14)]
    result = calculate_atr(candles, period=14)
    assert result == Decimal("10.0")

# ✅ DO: Use fixtures
@pytest.fixture
def sample_candles() -> list[Candle]:
    return [make_candle(...) for _ in range(100)]
```

### Integration Tests

- Location: `tests/integration/`
- Require: Running PostgreSQL + Redis
- Marker: `@pytest.mark.integration`

```python
@pytest.mark.integration
async def test_order_persists_to_database(db_session):
    order = await create_order(...)
    await db_session.commit()

    saved = await get_order_by_id(order.id)
    assert saved.status == OrderStatus.PENDING
```

### Running Tests

```bash
# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests (requires DB)
pytest tests/integration/ -v -m integration

# With coverage
pytest tests/ --cov=app/engine --cov-report=html

# Specific test
pytest tests/unit/test_smc.py::test_pivot_detection -v
```

---

## Pre-PR Checklist

Run this before creating a PR:

```bash
# All must pass
ruff check . && \
ruff format --check . && \
mypy . && \
pytest tests/unit/ -v && \
pytest tests/integration/ -v -m integration
```

---

## Domain Vocabulary

Use these terms consistently:

| Term | Meaning |
|------|---------|
| `candle` | OHLCV bar (not "bar", "kline") |
| `pivot` | HH/HL/LH/LL swing point |
| `CHOCH` | Change of Character (structure break) |
| `BOS` | Break of Structure |
| `OB` | Order Block |
| `FVG` | Fair Value Gap |
| `zone` | Supply/demand area |
| `signal` | Candidate trade entry |
| `decision` | Final trade with sizing |
