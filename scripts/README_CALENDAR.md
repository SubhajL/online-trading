# Economic Calendar Scripts

## Quick Start

### 1. Basic Usage (No Dependencies)
```bash
# Update calendar manually
python3 scripts/update_economic_calendar.py

# Check calendar health
python3 scripts/check_calendar_health.py
```

### 2. Full Setup (Recommended)
```bash
# Install optional dependencies for notifications
pip install -r scripts/requirements_calendar.txt

# Add to crontab (runs twice daily)
crontab -e
# Add: 0 6,18 * * * /path/to/online-trader/scripts/calendar_cron.sh
```

## Script Descriptions

- **`update_economic_calendar.py`** - Fetches and updates economic events
- **`check_calendar_health.py`** - Verifies calendar is current and valid
- **`calendar_cron.sh`** - Wrapper for cron with logging

## Data Sources

Currently implemented:
- **Manual dates**: Central bank meetings (FOMC, ECB, BOE) for 2025
- **Estimated dates**: CPI (12th of month), NFP (first Friday)

Not yet pulling from external APIs - you must:
1. Manually verify dates are correct
2. Add new events as they're announced
3. Consider paid API integration for automation

## Risk Management

**CRITICAL**: The economic calendar prevents trading during high-impact news events. Missing updates could result in significant losses.

### Recommended Update Frequency

| Your Trading Style | Update Frequency | Cron Schedule |
|-------------------|------------------|---------------|
| High-frequency/Algo | Every 6 hours | `0 */6 * * *` |
| Daily trading | Twice daily | `0 6,18 * * *` |
| Swing trading | Daily | `0 6 * * *` |

### Manual Fallback

If automated updates fail, manually update the CSV:
```csv
event_type,timestamp,impact,currency,blackout_before,blackout_after
FOMC,2025-01-29T19:00:00Z,HIGH,USD,30,60
NFP,2025-02-07T13:30:00Z,HIGH,USD,30,30
```

## Monitoring

Add to your monitoring routine:
```bash
# Daily check
python3 scripts/check_calendar_health.py

# View upcoming events
head -20 data/economic_calendar.csv | column -t -s,

# Check last update time
ls -la data/economic_calendar.csv
```

## Future Improvements

1. **Add paid API** for automatic updates (TradingEconomics, Econoday)
2. **Web scraping fallback** from ForexFactory/Investing.com
3. **Email/SMS alerts** for failed updates
4. **Historical event tracking** for backtesting

## Important Notes

- Events block trading 30 minutes before and after by default
- Only HIGH impact events are tracked
- FOMC meetings have 60-minute post-event blackout
- Calendar must be <24 hours old or trading should halt

Remember: This calendar is your first defense against news volatility!