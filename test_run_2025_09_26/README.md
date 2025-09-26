# 5-Day Integration Test Documentation

## Overview
This is a 5-day integration test of the trading platform with real Binance testnet connections, starting on 2025-09-26.

## Test Configuration
- **Initial Capital**: 100,000 THB ($2,800 USD)
- **Allocation**:
  - Spot Trading: 70,000 THB
  - Futures Trading: 30,000 THB
  - Reserve: 20%
- **Symbols**: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, MATICUSDT
- **Timeframes**: 15m, 1h
- **Risk Per Trade**: 0.5%
- **Daily Loss Limit**: 2%

## Current Status

### Services
- ✅ PostgreSQL: Connected and running
- ✅ Redis: Connected and running
- ✅ Binance Testnet: Connected and receiving data
- ✅ Telegram Bot: Connected and sending notifications
- ⚠️ Engine: Module import issue needs fixing

### Known Issues
1. **Engine Module Import**: The main engine has import errors that need to be fixed:
   - `app.engine.decision.decision_engine` should be `app.engine.decision.engine`
   - `app.engine.decision.risk_manager` should be `app.engine.decision.risk_guards`

2. **Local PostgreSQL Conflict**: Had to stop local PostgreSQL service to use Docker container

## Daily Monitoring

Run the daily monitoring script to check progress:
```bash
cd test_run_2025_09_26
python daily_monitor.py
```

This will:
- Check account balance and P&L
- Count orders and positions
- Monitor data collection
- Send report to Telegram
- Save report locally

## Quick Service Checks

### Verify Services
```bash
python scripts/verify_services.py
```

### Simple Integration Test
```bash
python scripts/simplified_integration_test.py
```

### Check Test Status
```bash
python test_run_2025_09_26/monitor_status.py
```

## Directory Structure
```
test_run_2025_09_26/
├── config/
│   ├── test_config.json      # Main test configuration
│   ├── engine_config.json    # Engine-specific config
│   └── report_template.html  # Daily report template
├── signals/                  # Generated trading signals
│   ├── BTCUSDT/
│   ├── ETHUSDT/
│   └── ...
├── orders/                   # Order history
│   ├── executed/
│   ├── failed/
│   └── cancelled/
├── reports/                  # Daily reports
├── logs/                     # Service logs
│   ├── engine/
│   ├── router/
│   └── bff/
└── account_history/          # Balance tracking
    └── balance_history.csv
```

## Telegram Notifications

The bot (@sltradingalert_bot) sends:
- Service status updates
- Daily reports with P&L
- Trading signals (when engine is running)
- Failed order alerts

## Next Steps

1. **Fix Engine Imports**: Update `app/engine/main.py` with correct module paths
2. **Start Full Test**: Run `python scripts/start_integration_test.py` after fixes
3. **Monitor Daily**: Check progress with daily monitor script
4. **Collect Results**: After 5 days, analyze results

## Emergency Commands

### Stop All Services
```bash
pkill -f "python.*engine"
pkill -f router
docker stop trading-postgres trading-redis
```

### Restart Services
```bash
docker start trading-postgres trading-redis
python scripts/start_integration_test.py
```

## Important Notes

- All services use Binance **TESTNET** - no real funds at risk
- PostgreSQL password is hardcoded as "your_secure_password_here"
- Telegram credentials are stored in .env file
- Test will run for 5 days unless manually stopped