# Economic Calendar Update Scheduling Guide

## Overview

The economic calendar is critical for risk management. Missing an update could mean trading during high-impact news events, potentially causing significant losses. This guide provides scheduling recommendations to maximize safety while minimizing resource usage.

## Script Components

1. **`scripts/update_economic_calendar.py`** - Main update script
2. **`scripts/calendar_cron.sh`** - Cron wrapper with logging
3. **`data/economic_calendar.csv`** - Output file used by trading guards

## Scheduling Recommendations

### 🔴 Critical: Production Trading (Real Money)

**Frequency: Every 6 hours**
```bash
# Crontab entry
0 */6 * * * /path/to/calendar_cron.sh
```

**Rationale:**
- Central banks sometimes announce emergency meetings with 24-48h notice
- Economic data releases can be rescheduled
- 6-hour updates ensure maximum 6h delay in detecting changes
- Runs at: 00:00, 06:00, 12:00, 18:00 UTC

### 🟡 Recommended: Most Users

**Frequency: Twice Daily**
```bash
# Crontab entry - 6 AM and 6 PM UTC
0 6,18 * * * /path/to/calendar_cron.sh
```

**Rationale:**
- Balances safety with resource usage
- Morning update catches overnight announcements
- Evening update prepares for next trading day
- Sufficient for most trading strategies

### 🟢 Minimum: Low-Frequency Trading

**Frequency: Daily**
```bash
# Crontab entry - 6 AM UTC (before London open)
0 6 * * * /path/to/calendar_cron.sh
```

**Rationale:**
- Acceptable if you trade infrequently
- Still catches most economic calendar updates
- Minimal resource usage

## Setup Instructions

### 1. Make Script Executable
```bash
chmod +x scripts/update_economic_calendar.py
chmod +x scripts/calendar_cron.sh
```

### 2. Configure Environment
```bash
# Add to .env file
FRED_API_KEY=your_fred_api_key  # Optional, get from https://fred.stlouisfed.org/docs/api/api_key.html
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL  # Optional
```

### 3. Test Manually
```bash
# Dry run to see what would be updated
python scripts/update_economic_calendar.py --dry-run

# Actual update
python scripts/update_economic_calendar.py --notify
```

### 4. Add to Crontab
```bash
# Edit crontab
crontab -e

# Add your chosen schedule (example: twice daily)
0 6,18 * * * /home/user/online-trader/scripts/calendar_cron.sh
```

### 5. Alternative: Systemd Timer (More Robust)

Create `/etc/systemd/system/economic-calendar.service`:
```ini
[Unit]
Description=Update Economic Calendar
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=trader
WorkingDirectory=/home/trader/online-trader
ExecStart=/home/trader/online-trader/scripts/calendar_cron.sh
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/economic-calendar.timer`:
```ini
[Unit]
Description=Update Economic Calendar Every 6 Hours
Requires=economic-calendar.service

[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
RandomizedDelaySec=10min

[Install]
WantedBy=timers.target
```

Enable timer:
```bash
sudo systemctl enable economic-calendar.timer
sudo systemctl start economic-calendar.timer
```

## Monitoring & Alerts

### 1. Check Last Update
```bash
# View last update time
ls -la data/economic_calendar.csv

# Check upcoming events
head -20 data/economic_calendar.csv | column -t -s,
```

### 2. Monitor Script Health
```python
#!/usr/bin/env python3
# scripts/check_calendar_health.py

import sys
from datetime import datetime, timedelta
from pathlib import Path

csv_path = Path('./data/economic_calendar.csv')

# Check file exists
if not csv_path.exists():
    print("❌ Calendar file missing!")
    sys.exit(1)

# Check last modified time
mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
age_hours = (datetime.now() - mtime).total_seconds() / 3600

if age_hours > 24:
    print(f"⚠️  Calendar is {age_hours:.1f} hours old!")
    sys.exit(1)

print(f"✅ Calendar updated {age_hours:.1f} hours ago")
```

### 3. Add to Monitoring Stack
```yaml
# prometheus/rules.yml
groups:
  - name: trading_alerts
    rules:
      - alert: EconomicCalendarStale
        expr: time() - economic_calendar_last_update_timestamp > 86400
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Economic calendar hasn't been updated in 24 hours"
          description: "Last update was {{ humanizeDuration $value }} ago"
```

## Data Sources & Limitations

### Current Implementation

1. **Manual Central Bank Dates**: FOMC, ECB, BOE meeting dates are hardcoded for 2025
2. **Estimated CPI/NFP**: Uses typical release patterns (needs manual verification)
3. **No Real-Time API**: To add paid services, extend the fetcher classes

### Recommended Enhancements

1. **Add Paid API** (Most Reliable):
   ```python
   # Example: TradingEconomics
   class TradingEconomicsFetcher(CalendarFetcher):
       def __init__(self, api_key: str):
           self.api_key = api_key
           self.base_url = "https://api.tradingeconomics.com/calendar"
   ```

2. **Multiple Sources** for redundancy:
   - Primary: Paid API (TradingEconomics, Econoday)
   - Backup: Web scraping (Investing.com, ForexFactory)
   - Fallback: Manual CSV maintained by team

3. **Validation Rules**:
   - Cross-check multiple sources
   - Flag discrepancies for manual review
   - Never trade if calendar data is >24h old

## Risk Mitigation

### What Happens If Updates Fail?

1. **Trading continues** with stale data (risky!)
2. **Manual override** required to halt trading
3. **Alert notifications** should trigger immediate action

### Best Practices

1. **Never rely on single update source**
2. **Always verify critical events manually** (FOMC, ECB, BOE)
3. **Set up redundant scheduling** (cron + systemd + monitoring)
4. **Test monthly** to ensure scripts still work
5. **Have manual fallback** procedure documented

### Emergency Procedures

If automated updates fail:
```bash
# 1. Check known events
curl -s https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

# 2. Update manually
cat > data/economic_calendar.csv << EOF
event_type,timestamp,impact,currency,blackout_before,blackout_after
FOMC,2025-01-29T19:00:00Z,HIGH,USD,30,60
NFP,2025-02-07T13:30:00Z,HIGH,USD,30,30
EOF

# 3. Notify team
echo "⚠️ Manual calendar update applied" | notify-team
```

## Cost-Benefit Analysis

### Update Frequency vs Risk

| Frequency | Max Delay | Risk Level | Resource Usage | Recommended For |
|-----------|-----------|------------|----------------|-----------------|
| Hourly | 1 hour | Very Low | High | High-frequency algo trading |
| 6 hours | 6 hours | Low | Medium | **Production trading** |
| 12 hours | 12 hours | Medium | Low | Most retail traders |
| Daily | 24 hours | High | Very Low | Occasional traders |
| Weekly | 7 days | Critical | Minimal | Not recommended |

### Monthly Costs

- **API Costs**: $0-500/month depending on provider
- **Server Resources**: ~1 CPU second per update
- **Network**: <1MB per update
- **Storage**: <100KB for CSV

## Conclusion

For production trading with real money, **update every 6 hours** minimum. The cost of missing a major economic event far exceeds the resource cost of frequent updates. Remember: this calendar is your first line of defense against trading during high-impact news events.