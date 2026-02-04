# Plan: Fix Pretrade Risk Check Order & Add Equity Health Endpoint

## Overview

Fix the misleading `invalid_notional` error by reordering validation checks in `pretrade_risk.py` so `invalid_equity` is returned when equity is the root cause. Additionally, add a `/health/equity` endpoint for operators to quickly diagnose equity state without running SQL queries.

## Problem Statement

When `equity == 0`:
- `quantity = (equity × risk_per_trade) / stop_distance = 0`
- `notional = entry_price × 0 = 0`
- Current code returns `invalid_notional` but ROOT CAUSE is `invalid_equity`

The check order hides the actual problem from operators seeing Telegram alerts.

## Files to Change

| File | Purpose |
|------|---------|
| `app/engine/decision/pretrade_risk.py` | Reorder validation checks: equity before notional |
| `app/engine/tests/unit/test_pretrade_risk.py` | Add tests for check ordering |
| `app/engine/main.py` | Add `/health/equity` endpoint and response model |
| `app/engine/tests/unit/test_health_equity.py` | Tests for equity health endpoint (NEW) |

## Implementation Steps

### Part 1: Fix pretrade_risk.py Check Order

#### Function: `evaluate_pretrade_risk()` (MODIFY)

**Current order (problematic):**
```
1. allowed_symbols
2. missing_price_or_quantity
3. invalid_notional ← hides root cause when equity=0
4. invalid_equity   ← should come first
```

**Fixed order:**
```
1. allowed_symbols
2. missing_price_or_quantity
3. invalid_equity   ← root cause exposed first
4. invalid_notional ← now only fires for price=0 edge cases
```

**Change:** Check `snapshot.equity <= 0` BEFORE checking `new_notional <= 0`.

### Part 2: Add `/health/equity` Endpoint

#### Function: `equity_health_check()` (NEW in main.py)

Returns current equity state for debugging:
- `equity`: Current equity value from `equity_samples`
- `timestamp`: When sampled (ISO8601 UTC)
- `age_seconds`: How stale the sample is
- `paper_components`: Breakdown (fees, realized_pnl, unrealized_pnl, funding)
- `status`: "healthy" | "stale" | "missing" | "zero"

---

## Test Coverage

### Test: `test_pretrade_risk.py` (ADD)

| Test Name | Behavior |
|-----------|----------|
| `test_invalid_equity_returned_before_invalid_notional` | equity=0 returns invalid_equity not invalid_notional |
| `test_invalid_notional_when_entry_price_zero` | price=0 still returns invalid_notional |
| `test_invalid_equity_with_negative_equity` | negative equity returns invalid_equity |

### Test: `test_health_equity.py` (NEW)

| Test Name | Behavior |
|-----------|----------|
| `test_returns_latest_sample_and_components` | returns equity, timestamp, paper components |
| `test_returns_stale_status_when_sample_old` | age > 120s marks status stale |
| `test_returns_missing_when_no_samples` | no samples returns status=missing |
| `test_returns_zero_status_when_equity_zero` | equity=0 returns status=zero |
| `test_handles_database_service_missing` | missing db service returns 503 |
| `test_normalizes_naive_timestamp_to_utc` | naive timestamp treated as UTC |

---

## Wiring Verification Table

| Component | Entry Point (caller) | Registration Location | Schema/Table |
|-----------|---------------------|----------------------|--------------|
| `evaluate_pretrade_risk()` (modified) | `decision_publisher.py:126`, `router_execution_subscriber.py:327` | Import at top of callers | N/A |
| `GET /health/equity` (new endpoint) | HTTP requests from operators/dashboards | `app/engine/main.py:@app.get("/health/equity")` | `equity_samples`, `paper_positions` |

---

## Response Model

```python
class EquityHealthResponse(BaseModel):
    status: Literal["healthy", "stale", "missing", "zero"]
    equity: Decimal | None
    timestamp: str | None
    age_seconds: float | None
    paper_components: dict[str, str] | None
    message: str
```

---

## Validation Commands

```bash
# Run affected tests
pytest app/engine/tests/unit/test_pretrade_risk.py -v
pytest app/engine/tests/unit/test_health_equity.py -v

# Full engine tests
make test-engine

# Lint and format
ruff check app/engine/decision/pretrade_risk.py app/engine/main.py
ruff format app/engine/decision/pretrade_risk.py app/engine/main.py
```
