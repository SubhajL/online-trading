#!/usr/bin/env python3
"""
Economic Calendar Updater Script

Updates the economic calendar CSV with upcoming high-impact events.
Fetches from multiple sources for reliability.

Usage:
    python scripts/update_economic_calendar.py [--dry-run] [--notify]
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from dateutil.parser import parse as parse_date
except ImportError:
    # Fallback to basic ISO format parsing
    def parse_date(date_str):
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EconomicEvent:
    """Represents an economic calendar event."""

    def __init__(
        self,
        event_type: str,
        timestamp: datetime,
        impact: str = "HIGH",
        currency: str = "USD",
        blackout_before: int = 30,
        blackout_after: int = 30,
        source: str = "manual"
    ):
        self.event_type = event_type
        self.timestamp = timestamp
        self.impact = impact
        self.currency = currency
        self.blackout_before = blackout_before
        self.blackout_after = blackout_after
        self.source = source

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV writing."""
        return {
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat(),
            'impact': self.impact,
            'currency': self.currency,
            'blackout_before': self.blackout_before,
            'blackout_after': self.blackout_after,
            'source': self.source
        }

    def __repr__(self):
        return f"EconomicEvent({self.event_type}, {self.timestamp.isoformat()}, {self.currency})"


class CalendarFetcher:
    """Base class for calendar data fetchers."""

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Fetch events between start and end dates."""
        raise NotImplementedError


class FREDFetcher(CalendarFetcher):
    """Fetches CPI and NFP data from FRED API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('FRED_API_KEY')
        self.base_url = "https://api.stlouisfed.org/fred"

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Fetch CPI and NFP release dates from FRED."""
        events = []

        if not self.api_key:
            logger.warning("FRED_API_KEY not set, skipping FRED data")
            return events

        # CPI releases (usually around 8:30 AM ET on ~12th of month)
        # NFP releases (usually first Friday of month at 8:30 AM ET)

        # For now, return estimated dates based on typical schedule
        # In production, you'd query FRED API for actual release dates

        current = start_date
        while current <= end_date:
            # CPI: Around 12th of each month
            cpi_date = current.replace(day=12, hour=13, minute=30, second=0, microsecond=0)
            if start_date <= cpi_date <= end_date:
                events.append(EconomicEvent(
                    event_type="CPI",
                    timestamp=cpi_date,
                    impact="HIGH",
                    currency="USD",
                    source="FRED"
                ))

            # NFP: First Friday of month
            first_day = current.replace(day=1)
            first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
            nfp_date = first_friday.replace(hour=13, minute=30, second=0, microsecond=0)
            if start_date <= nfp_date <= end_date:
                events.append(EconomicEvent(
                    event_type="NFP",
                    timestamp=nfp_date,
                    impact="HIGH",
                    currency="USD",
                    source="FRED"
                ))

            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return events


class CentralBankFetcher(CalendarFetcher):
    """Fetches central bank meeting dates."""

    # Known 2025 FOMC meetings (usually Wednesday 2:00 PM ET)
    FOMC_2025_DATES = [
        "2025-01-29T19:00:00Z",
        "2025-03-19T18:00:00Z",
        "2025-05-07T18:00:00Z",
        "2025-06-18T18:00:00Z",
        "2025-07-30T18:00:00Z",
        "2025-09-17T18:00:00Z",
        "2025-11-05T19:00:00Z",
        "2025-12-17T19:00:00Z"
    ]

    # ECB meetings (usually Thursday 1:45 PM CET)
    ECB_2025_DATES = [
        "2025-01-23T12:45:00Z",
        "2025-02-06T12:45:00Z",
        "2025-03-20T12:45:00Z",
        "2025-05-08T12:45:00Z",
        "2025-06-12T12:45:00Z",
        "2025-07-24T12:45:00Z",
        "2025-09-11T12:45:00Z",
        "2025-10-23T12:45:00Z",
        "2025-12-11T12:45:00Z"
    ]

    # BOE meetings (usually Thursday 12:00 PM GMT)
    BOE_2025_DATES = [
        "2025-02-06T12:00:00Z",
        "2025-03-20T12:00:00Z",
        "2025-05-08T11:00:00Z",
        "2025-06-19T11:00:00Z",
        "2025-08-07T11:00:00Z",
        "2025-09-18T11:00:00Z",
        "2025-11-06T12:00:00Z",
        "2025-12-18T12:00:00Z"
    ]

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Fetch central bank meeting dates."""
        events = []

        # FOMC
        for date_str in self.FOMC_2025_DATES:
            date = parse_date(date_str)
            if start_date <= date <= end_date:
                events.append(EconomicEvent(
                    event_type="FOMC",
                    timestamp=date,
                    impact="HIGH",
                    currency="USD",
                    blackout_before=30,
                    blackout_after=60,  # Longer blackout after FOMC
                    source="manual"
                ))

        # ECB
        for date_str in self.ECB_2025_DATES:
            date = parse_date(date_str)
            if start_date <= date <= end_date:
                events.append(EconomicEvent(
                    event_type="ECB",
                    timestamp=date,
                    impact="HIGH",
                    currency="EUR",
                    source="manual"
                ))

        # BOE
        for date_str in self.BOE_2025_DATES:
            date = parse_date(date_str)
            if start_date <= date <= end_date:
                events.append(EconomicEvent(
                    event_type="BOE",
                    timestamp=date,
                    impact="HIGH",
                    currency="GBP",
                    source="manual"
                ))

        return events


class CalendarUpdater:
    """Main class for updating the economic calendar."""

    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.fetchers = [
            FREDFetcher(),
            CentralBankFetcher()
        ]

    def fetch_all_events(self, days_ahead: int = 90) -> List[EconomicEvent]:
        """Fetch events from all sources."""
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=days_ahead)

        all_events = []
        for fetcher in self.fetchers:
            try:
                events = fetcher.fetch_events(start_date, end_date)
                all_events.extend(events)
                logger.info(f"Fetched {len(events)} events from {fetcher.__class__.__name__}")
            except Exception as e:
                logger.error(f"Error fetching from {fetcher.__class__.__name__}: {e}")

        return all_events

    def deduplicate_events(self, events: List[EconomicEvent]) -> List[EconomicEvent]:
        """Remove duplicate events, keeping the most authoritative source."""
        # Group by event type and approximate time
        unique_events = {}

        for event in events:
            # Key is event type + date (ignoring exact time)
            key = (event.event_type, event.timestamp.date())

            if key not in unique_events:
                unique_events[key] = event
            else:
                # Prefer manual/authoritative sources
                if event.source == "manual":
                    unique_events[key] = event

        return list(unique_events.values())

    def validate_events(self, events: List[EconomicEvent]) -> List[EconomicEvent]:
        """Validate events and filter out suspicious data."""
        valid_events = []

        for event in events:
            # Check event is in the future
            if event.timestamp < datetime.now(timezone.utc):
                continue

            # Check event type is recognized
            if event.event_type not in ["CPI", "NFP", "FOMC", "ECB", "BOE"]:
                logger.warning(f"Unknown event type: {event.event_type}")
                continue

            # Check blackout windows are reasonable
            if event.blackout_before > 120 or event.blackout_after > 120:
                logger.warning(f"Suspicious blackout window for {event}")
                continue

            valid_events.append(event)

        return valid_events

    def update_csv(self, events: List[EconomicEvent], dry_run: bool = False) -> None:
        """Update the CSV file with new events."""
        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)

        if dry_run:
            logger.info("DRY RUN - Would write the following events:")
            for event in events:
                logger.info(f"  {event}")
            return

        # Create directory if it doesn't exist
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Write CSV
        with open(self.csv_path, 'w', newline='') as f:
            fieldnames = ['event_type', 'timestamp', 'impact', 'currency',
                         'blackout_before', 'blackout_after']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for event in events:
                row = event.to_dict()
                # Remove source field for CSV
                row.pop('source', None)
                writer.writerow(row)

        logger.info(f"Updated {self.csv_path} with {len(events)} events")

    def send_notification(self, message: str) -> None:
        """Send notification about calendar update."""
        # In production, this could send to Slack, email, etc.
        logger.info(f"NOTIFICATION: {message}")

        # Example Slack webhook (if configured)
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        if webhook_url and HAS_REQUESTS:
            try:
                requests.post(webhook_url, json={'text': message}, timeout=5)
            except Exception as e:
                logger.error(f"Failed to send Slack notification: {e}")
        elif webhook_url and not HAS_REQUESTS:
            logger.warning("Slack webhook configured but 'requests' module not installed")


def main():
    parser = argparse.ArgumentParser(description='Update economic calendar CSV')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without writing')
    parser.add_argument('--notify', action='store_true',
                       help='Send notifications about updates')
    parser.add_argument('--days-ahead', type=int, default=90,
                       help='Number of days to look ahead (default: 90)')
    parser.add_argument('--csv-path', type=Path,
                       default=Path('./data/economic_calendar.csv'),
                       help='Path to CSV file')

    args = parser.parse_args()

    updater = CalendarUpdater(args.csv_path)

    try:
        # Fetch events
        events = updater.fetch_all_events(args.days_ahead)

        # Deduplicate and validate
        events = updater.deduplicate_events(events)
        events = updater.validate_events(events)

        if not events:
            logger.warning("No valid events found!")
            if args.notify:
                updater.send_notification(
                    "⚠️ Economic calendar update found no valid events!"
                )
            sys.exit(1)

        # Update CSV
        updater.update_csv(events, dry_run=args.dry_run)

        # Send notification if requested
        if args.notify and not args.dry_run:
            updater.send_notification(
                f"✅ Economic calendar updated with {len(events)} events"
            )

        # Log upcoming events in next 7 days
        upcoming = [e for e in events
                   if e.timestamp <= datetime.now(timezone.utc) + timedelta(days=7)]
        if upcoming:
            logger.info(f"Upcoming events in next 7 days: {len(upcoming)}")
            for event in upcoming:
                logger.info(f"  - {event}")

    except Exception as e:
        logger.error(f"Fatal error updating calendar: {e}", exc_info=True)
        if args.notify:
            updater.send_notification(
                f"❌ Economic calendar update failed: {str(e)}"
            )
        sys.exit(1)


if __name__ == '__main__':
    main()