# Step-by-Step Economic Calendar Setup Guide

## Prerequisites
- Python 3.8+ installed
- Access to terminal/command line
- ~5 minutes for initial setup

## Step 1: Install Required Python Packages

```bash
# Navigate to your project directory
cd /path/to/online-trader

# Install the calendar script dependencies
pip3 install -r scripts/requirements_calendar.txt
```

If you get permission errors, try:
```bash
pip3 install --user -r scripts/requirements_calendar.txt
```

## Step 2: Get Free FRED API Key (Recommended, 2 minutes)

1. Visit https://fred.stlouisfed.org/docs/api/api_key.html
2. Click "Request API Key"
3. Fill out the simple form:
   - Name: Your name
   - Email: Your email
   - Purpose: "Personal research"
4. Check email and click verification link
5. Copy your API key from the email

## Step 3: Configure Environment Variables

```bash
# Create .env file if it doesn't exist
cp .env.example .env

# Edit .env file
nano .env  # or use your preferred editor
```

Add these lines:
```bash
# Add your FRED API key (from Step 2)
FRED_API_KEY=your_actual_fred_api_key_here

# Optional: Add Slack webhook for notifications
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK
```

## Step 4: Test the Script Manually

```bash
# First, do a dry run to see what would be fetched
python3 scripts/update_economic_calendar_v2.py --dry-run

# Check the output - you should see events like:
# 2025-10-23 12:45:00 - ECB meeting
# 2025-11-05 19:00:00 - FOMC meeting
```

## Step 5: Run the Script for Real

```bash
# Create the data directory if it doesn't exist
mkdir -p data

# Run the updater to create/update the CSV
python3 scripts/update_economic_calendar_v2.py

# Verify the CSV was created
ls -la data/economic_calendar.csv
cat data/economic_calendar.csv
```

## Step 6: Check Calendar Health

```bash
# Run the health check script
python3 scripts/check_calendar_health.py

# You should see output like:
# ✅ Calendar Status: Updated 0.1 hours ago
# 📊 Total upcoming events: 15
# 📌 Next Event: ECB meeting in 720 hours
```

## Step 7: Set Up Automatic Updates

### Option A: Using Cron (Recommended)

```bash
# Open crontab editor
crontab -e

# Add this line for updates every 6 hours:
0 */6 * * * cd /path/to/online-trader && /usr/bin/python3 scripts/update_economic_calendar_v2.py >> logs/calendar_update.log 2>&1

# Or for twice daily (6 AM and 6 PM UTC):
0 6,18 * * * cd /path/to/online-trader && /usr/bin/python3 scripts/update_economic_calendar_v2.py >> logs/calendar_update.log 2>&1
```

### Option B: Using the Provided Cron Script

```bash
# Make the cron script executable
chmod +x scripts/calendar_cron.sh

# Edit crontab
crontab -e

# Add this line:
0 */6 * * * /path/to/online-trader/scripts/calendar_cron.sh
```

## Step 8: Verify Automatic Updates

```bash
# Wait for the next cron run, or test immediately:
./scripts/calendar_cron.sh

# Check the logs
tail -f logs/calendar_update_$(date +%Y%m%d).log

# Verify cron is set up correctly
crontab -l
```

## Step 9: Integration with Trading System

Make sure your trading configuration points to the calendar:

```yaml
# In app/engine/config.yaml
guards:
  calendar:
    source_type: csv
    csv_path: ./data/economic_calendar.csv
```

## Step 10: Monitor and Maintain

### Daily Check (Add to your routine)
```bash
# Quick health check
python3 scripts/check_calendar_health.py
```

### Weekly Verification
```bash
# Verify sources are still working
python3 scripts/update_economic_calendar_v2.py --source fred --dry-run
python3 scripts/update_economic_calendar_v2.py --source forexfactory --dry-run
```

## Troubleshooting

### "No module named 'requests'" or similar
```bash
# Ensure you installed requirements
pip3 install requests beautifulsoup4 lxml python-dateutil
```

### "No events found"
```bash
# Test each source individually
python3 scripts/update_economic_calendar_v2.py --source fred --dry-run
python3 scripts/update_economic_calendar_v2.py --source tradingeconomics --dry-run

# If FRED fails, check your API key
echo $FRED_API_KEY
```

### Cron not running
```bash
# Check cron service is running
service cron status  # On Linux
# or
sudo launchctl list | grep cron  # On macOS

# Check cron logs
grep CRON /var/log/syslog  # On Linux
# or
log show --predicate 'process == "cron"' --last 1h  # On macOS
```

### Permission denied
```bash
# Make sure scripts are executable
chmod +x scripts/update_economic_calendar_v2.py
chmod +x scripts/check_calendar_health.py
chmod +x scripts/calendar_cron.sh
```

## Quick Verification Checklist

Run this to verify everything is working:

```bash
# 1. Check dependencies installed
python3 -c "import requests, bs4, dateutil; print('✅ All dependencies installed')"

# 2. Check FRED API key is set
python3 -c "import os; print('✅ FRED API key set' if os.getenv('FRED_API_KEY') else '❌ FRED API key missing')"

# 3. Run a quick update
python3 scripts/update_economic_calendar_v2.py --days-ahead 30

# 4. Check the calendar
python3 scripts/check_calendar_health.py

# 5. Verify cron is set
crontab -l | grep calendar && echo "✅ Cron job configured" || echo "❌ Cron job not found"
```

## Next Steps

1. **Monitor for a week** to ensure updates are reliable
2. **Set up notifications** if you have Slack/email webhooks
3. **Consider backup sources** if primary sources fail
4. **Document any custom events** your strategy needs

## Summary

You now have an automated economic calendar that:
- ✅ Updates from multiple free sources
- ✅ Runs automatically via cron
- ✅ Blocks trading during high-impact news
- ✅ Has health monitoring built-in
- ✅ Includes manual fallback dates

The system will protect you from trading during major economic events without requiring manual maintenance!