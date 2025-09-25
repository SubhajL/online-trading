#!/usr/bin/env python3
"""
Economic Calendar Health Check

Verifies the calendar is up-to-date and contains upcoming events.
Exit codes:
  0 - Healthy
  1 - Needs attention
  2 - Critical issue
"""

import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    csv_path = Path('./data/economic_calendar.csv')

    # Check file exists
    if not csv_path.exists():
        print("❌ CRITICAL: Calendar file missing!")
        print(f"   Expected at: {csv_path.absolute()}")
        sys.exit(2)

    # Check last modified time
    mtime = datetime.fromtimestamp(csv_path.stat().st_mtime, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    age_hours = (now - mtime).total_seconds() / 3600

    print(f"📅 Calendar Status")
    print(f"   Last updated: {mtime.strftime('%Y-%m-%d %H:%M UTC')} ({age_hours:.1f} hours ago)")

    if age_hours > 48:
        print(f"❌ CRITICAL: Calendar is {age_hours:.1f} hours old!")
        sys.exit(2)
    elif age_hours > 24:
        print(f"⚠️  WARNING: Calendar is {age_hours:.1f} hours old")
        exit_code = 1
    else:
        print(f"✅ Update recency: OK")
        exit_code = 0

    # Check content
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            events = list(reader)

        # Count upcoming events
        upcoming_events = []
        next_7_days = []
        next_24_hours = []

        for event in events:
            try:
                event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                if event_time > now:
                    upcoming_events.append(event)

                    if event_time <= now + timedelta(days=7):
                        next_7_days.append(event)

                    if event_time <= now + timedelta(hours=24):
                        next_24_hours.append(event)

            except (KeyError, ValueError) as e:
                print(f"⚠️  WARNING: Invalid event format: {event}")
                exit_code = 1

        print(f"\n📊 Event Statistics:")
        print(f"   Total upcoming events: {len(upcoming_events)}")
        print(f"   Events in next 24h: {len(next_24_hours)}")
        print(f"   Events in next 7d: {len(next_7_days)}")

        if len(upcoming_events) == 0:
            print("❌ CRITICAL: No upcoming events found!")
            sys.exit(2)

        # Show next 24h events
        if next_24_hours:
            print(f"\n⚠️  HIGH PRIORITY - Events in next 24 hours:")
            for event in sorted(next_24_hours, key=lambda x: x['timestamp']):
                event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                hours_until = (event_time - now).total_seconds() / 3600
                print(f"   - {event['event_type']} ({event['currency']}) in {hours_until:.1f} hours")
                print(f"     {event_time.strftime('%Y-%m-%d %H:%M UTC')}")

        # Show next event
        if upcoming_events:
            next_event = min(upcoming_events, key=lambda x: x['timestamp'])
            event_time = datetime.fromisoformat(next_event['timestamp'].replace('Z', '+00:00'))
            hours_until = (event_time - now).total_seconds() / 3600

            print(f"\n📌 Next Event:")
            print(f"   {next_event['event_type']} ({next_event['currency']})")
            print(f"   {event_time.strftime('%Y-%m-%d %H:%M UTC')} ({hours_until:.1f} hours from now)")
            print(f"   Trading blocked: {next_event.get('blackout_before', '30')}min before, "
                  f"{next_event.get('blackout_after', '30')}min after")

    except Exception as e:
        print(f"❌ ERROR reading calendar: {e}")
        sys.exit(2)

    # Final status
    print(f"\n📋 Overall Status: {'HEALTHY' if exit_code == 0 else 'NEEDS ATTENTION'}")
    sys.exit(exit_code)


if __name__ == '__main__':
    main()