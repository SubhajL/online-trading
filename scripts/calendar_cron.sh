#!/bin/bash
#
# Economic Calendar Update Cron Script
#
# Add to crontab with: crontab -e
# Then add one of these lines:
#
# Daily at 6 AM UTC (before market open):
# 0 6 * * * /path/to/online-trader/scripts/calendar_cron.sh
#
# Twice daily at 6 AM and 6 PM UTC:
# 0 6,18 * * * /path/to/online-trader/scripts/calendar_cron.sh
#
# Every 12 hours with some randomization to avoid API limits:
# 0 */12 * * * sleep $((RANDOM % 600)) && /path/to/online-trader/scripts/calendar_cron.sh

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment if exists
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(cat "$PROJECT_DIR/.env" | grep -v '^#' | xargs)
fi

# Log file
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/calendar_update_$(date +%Y%m%d).log"

# Python environment
PYTHON_ENV="$PROJECT_DIR/venv/bin/python"
if [ ! -f "$PYTHON_ENV" ]; then
    PYTHON_ENV="python3"
fi

# Run the update script
echo "[$(date)] Starting economic calendar update" >> "$LOG_FILE"

$PYTHON_ENV "$SCRIPT_DIR/update_economic_calendar.py" \
    --notify \
    --days-ahead 90 \
    --csv-path "$PROJECT_DIR/data/economic_calendar.csv" \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date)] Calendar update failed with exit code $EXIT_CODE" >> "$LOG_FILE"

    # Send alert if webhook is configured
    if [ ! -z "$SLACK_WEBHOOK_URL" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data '{"text":"❌ Economic calendar update failed! Check logs."}' \
            "$SLACK_WEBHOOK_URL" 2>/dev/null
    fi
else
    echo "[$(date)] Calendar update completed successfully" >> "$LOG_FILE"
fi

# Rotate old logs (keep last 7 days)
find "$LOG_DIR" -name "calendar_update_*.log" -mtime +7 -delete

exit $EXIT_CODE