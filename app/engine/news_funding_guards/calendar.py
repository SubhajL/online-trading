"""
Economic Calendar Event Loader

Loads major economic events (CPI/NFP/FOMC) from:
- CSV files
- Google Sheets (optional)
"""

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Any

import csv

logger = logging.getLogger(__name__)


class EconomicEvent:
    """Represents an economic calendar event."""

    def __init__(
        self,
        event_type: str,
        timestamp: datetime,
        impact: str,
        currency: str,
    ) -> None:
        self.event_type = event_type  # CPI, NFP, FOMC
        self.timestamp = timestamp
        self.impact = impact  # HIGH, MEDIUM, LOW
        self.currency = currency  # USD, EUR, etc.
        self.blackout_minutes_before = 30
        self.blackout_minutes_after = 30

    def is_in_blackout_window(self, current_time: datetime) -> bool:
        """Check if current time is within event blackout window."""
        start = self.timestamp - timedelta(minutes=self.blackout_minutes_before)
        end = self.timestamp + timedelta(minutes=self.blackout_minutes_after)
        return start <= current_time <= end


async def load_calendar_events(
    source_path: str,
    source_type: str = "csv",
) -> list[EconomicEvent]:
    """Load events from CSV or Google Sheets."""
    if source_type == "csv":
        return parse_csv_events(Path(source_path))
    elif source_type == "google_sheets":
        return await load_google_sheets_events(source_path)
    else:
        raise ValueError(f"Unknown source type: {source_type}")


def parse_csv_events(file_path: Path) -> list[EconomicEvent]:
    """Parse events from CSV file."""
    events = []

    if not file_path.exists():
        logger.warning(f"Calendar CSV file not found: {file_path}")
        return events

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Expected columns: event_type, timestamp, impact, currency
                event = EconomicEvent(
                    event_type=row['event_type'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    impact=row['impact'],
                    currency=row['currency']
                )

                # Optional: override blackout windows
                if 'blackout_before' in row:
                    event.blackout_minutes_before = int(row['blackout_before'])
                if 'blackout_after' in row:
                    event.blackout_minutes_after = int(row['blackout_after'])

                events.append(event)

    except Exception as e:
        logger.error(f"Error parsing calendar CSV: {e}", exc_info=True)

    return events


async def load_google_sheets_events(sheet_id: str) -> list[EconomicEvent]:
    """Load events from Google Sheets."""
    # Placeholder - would use Google Sheets API
    logger.warning("Google Sheets integration not implemented")
    return []


def filter_high_impact_events(
    events: list[EconomicEvent],
    currencies: list[str] | None = None,
) -> list[EconomicEvent]:
    """Filter for high impact events only."""
    filtered = []

    for event in events:
        # Filter by impact
        if event.impact.upper() != "HIGH":
            continue

        # Filter by currency if specified
        if currencies and event.currency not in currencies:
            continue

        filtered.append(event)

    return filtered


class CalendarManager:
    """Manages economic calendar events."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._events: list[EconomicEvent] = []
        self._last_loaded: datetime | None = None

        # Configuration
        self.source_type = config.get("source_type", "csv")
        self.csv_path = config.get("csv_path", "./data/economic_calendar.csv")
        self.google_sheets_id = config.get("google_sheets_id")
        self.tracked_events = config.get("tracked_events", ["CPI", "NFP", "FOMC"])
        self.reload_interval_hours = config.get("reload_interval_hours", 24)

    async def load_events(self) -> None:
        """Load events from configured source."""
        try:
            if self.source_type == "csv":
                self._events = await load_calendar_events(
                    self.csv_path,
                    source_type="csv"
                )
            elif self.source_type == "google_sheets":
                self._events = await load_calendar_events(
                    self.google_sheets_id,
                    source_type="google_sheets"
                )

            # Filter for tracked event types
            self._events = [
                e for e in self._events
                if e.event_type in self.tracked_events
            ]

            # Filter for high impact
            if self.config.get("high_impact_only", True):
                self._events = filter_high_impact_events(self._events)

            self._last_loaded = datetime.now(timezone.utc)
            logger.info(f"Loaded {len(self._events)} calendar events")

        except Exception as e:
            logger.error(f"Error loading calendar events: {e}", exc_info=True)

    async def reload_if_stale(self, max_age_hours: int | None = None) -> None:
        """Reload events if data is stale."""
        if max_age_hours is None:
            max_age_hours = self.reload_interval_hours

        if self._last_loaded is None:
            await self.load_events()
            return

        age_hours = (datetime.now(timezone.utc) - self._last_loaded).total_seconds() / 3600
        if age_hours > max_age_hours:
            await self.load_events()

    def get_upcoming_events(
        self,
        hours_ahead: int = 48,
    ) -> list[EconomicEvent]:
        """Get events in the next N hours."""
        current_time = datetime.now(timezone.utc)
        cutoff_time = current_time + timedelta(hours=hours_ahead)

        upcoming = [
            event for event in self._events
            if current_time <= event.timestamp <= cutoff_time
        ]

        # Sort by timestamp
        upcoming.sort(key=lambda e: e.timestamp)

        return upcoming

    def is_news_blackout(
        self,
        current_time: datetime | None = None,
    ) -> bool:
        """Check if currently in any news blackout window."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        for event in self._events:
            if event.is_in_blackout_window(current_time):
                return True

        return False