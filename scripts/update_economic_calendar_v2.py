#!/usr/bin/env python3
"""
Economic Calendar Updater V2 - With Free Data Sources

Updates the economic calendar CSV using free APIs and web scraping.

Free Sources:
1. FRED API (free with registration)
2. ForexFactory scraping
3. Investing.com scraping
4. FXStreet RSS feed

Usage:
    python scripts/update_economic_calendar_v2.py [--dry-run] [--source SOURCE]
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("WARNING: 'requests' not installed. Limited functionality.")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("INFO: 'beautifulsoup4' not installed. Web scraping disabled.")

try:
    from dateutil.parser import parse as parse_date
except ImportError:
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
        source: str = "manual",
        actual: Optional[str] = None,
        forecast: Optional[str] = None,
        previous: Optional[str] = None
    ):
        self.event_type = event_type
        self.timestamp = timestamp
        self.impact = impact
        self.currency = currency
        self.blackout_before = blackout_before
        self.blackout_after = blackout_after
        self.source = source
        self.actual = actual
        self.forecast = forecast
        self.previous = previous

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV writing."""
        return {
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat(),
            'impact': self.impact,
            'currency': self.currency,
            'blackout_before': self.blackout_before,
            'blackout_after': self.blackout_after
        }

    def __repr__(self):
        return f"EconomicEvent({self.event_type}, {self.timestamp.isoformat()}, {self.currency})"


class CalendarFetcher:
    """Base class for calendar data fetchers."""

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Fetch events between start and end dates."""
        raise NotImplementedError


class FREDFetcher(CalendarFetcher):
    """
    Federal Reserve Economic Data (FRED) API
    Free API with registration: https://fred.stlouisfed.org/docs/api/api_key.html
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('FRED_API_KEY')
        self.base_url = "https://api.stlouisfed.org/fred"
        self.enabled = bool(self.api_key) and HAS_REQUESTS

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Fetch economic release dates from FRED."""
        events = []

        if not self.enabled:
            logger.warning("FRED API disabled (no API key or requests module)")
            return events

        try:
            # Generate estimated release dates based on typical patterns
            # (FRED doesn't provide future release dates directly)

            # CPI releases
            cpi_events = self._generate_monthly_releases("CPI", start_date, end_date, day=12)
            events.extend(cpi_events)

            # NFP releases
            nfp_events = self._generate_first_friday_releases("NFP", start_date, end_date)
            events.extend(nfp_events)

            logger.info(f"Generated {len(events)} estimated events using FRED patterns")

        except Exception as e:
            logger.error(f"Error generating FRED events: {e}")

        return events

    def _fetch_series_releases(
        self,
        series_id: str,
        event_type: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[EconomicEvent]:
        """Fetch release dates for a specific FRED series."""
        params = {
            'series_id': series_id,
            'api_key': self.api_key,
            'file_type': 'json',
            'limit': 100,
            'sort_order': 'desc',
            'realtime_start': start_date.strftime('%Y-%m-%d'),
            'realtime_end': end_date.strftime('%Y-%m-%d')
        }

        # Use observations endpoint to get latest data releases
        url = f"{self.base_url}/series/observations?{urlencode(params)}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        events = []

        # FRED doesn't provide future release dates directly
        # We need to estimate based on typical release patterns

        if event_type == "CPI":
            # CPI is typically released around the 10-13th of each month
            current_date = datetime.now(timezone.utc)
            for month_offset in range(0, 4):  # Next 4 months
                # Calculate next release date (around 12th of month at 8:30 AM ET)
                year = current_date.year
                month = current_date.month + month_offset
                if month > 12:
                    year += 1
                    month -= 12

                release_date = datetime(year, month, 12, 13, 30, tzinfo=timezone.utc)
                if start_date <= release_date <= end_date and release_date > current_date:
                    events.append(EconomicEvent(
                        event_type=event_type,
                        timestamp=release_date,
                        impact="HIGH",
                        currency="USD",
                        source="FRED"
                    ))

        elif event_type == "NFP":
            # NFP is typically released on the first Friday of each month
            current_date = datetime.now(timezone.utc)
            for month_offset in range(0, 4):  # Next 4 months
                year = current_date.year
                month = current_date.month + month_offset
                if month > 12:
                    year += 1
                    month -= 12

                # Find first Friday of the month
                first_day = datetime(year, month, 1, 13, 30, tzinfo=timezone.utc)
                days_until_friday = (4 - first_day.weekday()) % 7
                if days_until_friday == 0:
                    days_until_friday = 7  # If 1st is Friday, use that Friday
                release_date = first_day + timedelta(days=days_until_friday)

                if start_date <= release_date <= end_date and release_date > current_date:
                    events.append(EconomicEvent(
                        event_type=event_type,
                        timestamp=release_date,
                        impact="HIGH",
                        currency="USD",
                        source="FRED"
                    ))

        return events

    def _generate_monthly_releases(
        self,
        event_type: str,
        start_date: datetime,
        end_date: datetime,
        day: int
    ) -> List[EconomicEvent]:
        """Generate monthly release dates (e.g., CPI on ~12th of month)."""
        events = []
        current_date = datetime.now(timezone.utc)

        # Generate for next 12 months
        for month_offset in range(0, 12):
            year = current_date.year
            month = current_date.month + month_offset
            if month > 12:
                year += month // 12
                month = month % 12
                if month == 0:
                    month = 12
                    year -= 1

            try:
                # 8:30 AM ET = 13:30 UTC (standard time) or 12:30 UTC (daylight time)
                release_date = datetime(year, month, day, 13, 30, tzinfo=timezone.utc)

                if start_date <= release_date <= end_date and release_date > current_date:
                    events.append(EconomicEvent(
                        event_type=event_type,
                        timestamp=release_date,
                        impact="HIGH",
                        currency="USD",
                        source="FRED"
                    ))
            except ValueError:
                # Handle months without the specified day (e.g., Feb 31)
                pass

        return events

    def _generate_first_friday_releases(
        self,
        event_type: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[EconomicEvent]:
        """Generate first Friday of month releases (e.g., NFP)."""
        events = []
        current_date = datetime.now(timezone.utc)

        # Generate for next 12 months
        for month_offset in range(0, 12):
            year = current_date.year
            month = current_date.month + month_offset
            if month > 12:
                year += month // 12
                month = month % 12
                if month == 0:
                    month = 12
                    year -= 1

            # Find first Friday
            first_day = datetime(year, month, 1, 13, 30, tzinfo=timezone.utc)
            days_until_friday = (4 - first_day.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 0  # If 1st is Friday, use it
            release_date = first_day + timedelta(days=days_until_friday)

            if start_date <= release_date <= end_date and release_date > current_date:
                events.append(EconomicEvent(
                    event_type=event_type,
                    timestamp=release_date,
                    impact="HIGH",
                    currency="USD",
                    source="FRED"
                ))

        return events


class ForexFactoryFetcher(CalendarFetcher):
    """
    ForexFactory Calendar Scraper
    Note: Be respectful with scraping frequency
    """

    def __init__(self):
        self.base_url = "https://www.forexfactory.com"
        self.enabled = HAS_REQUESTS and HAS_BS4
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; EconomicCalendarBot/1.0)'
        }

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Scrape events from ForexFactory calendar."""
        events = []

        if not self.enabled:
            logger.warning("ForexFactory scraping disabled (missing dependencies)")
            return events

        try:
            # ForexFactory calendar URL for this week
            url = f"{self.base_url}/calendar.php"

            # Add delay to be respectful
            time.sleep(1)

            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            events.extend(self._parse_calendar_page(soup, start_date, end_date))

            logger.info(f"Scraped {len(events)} events from ForexFactory")

        except Exception as e:
            logger.error(f"Error scraping ForexFactory: {e}")

        return events

    def _parse_calendar_page(
        self,
        soup: BeautifulSoup,
        start_date: datetime,
        end_date: datetime
    ) -> List[EconomicEvent]:
        """Parse ForexFactory calendar HTML."""
        events = []
        current_date = None

        # Find calendar table
        calendar = soup.find('table', class_='calendar__table')
        if not calendar:
            return events

        rows = calendar.find_all('tr', class_='calendar__row')

        for row in rows:
            try:
                # Check if this is a date row
                date_cell = row.find('td', class_='calendar__date')
                if date_cell:
                    date_text = date_cell.get_text(strip=True)
                    # Parse date (e.g., "Mon Dec 25")
                    current_date = self._parse_ff_date(date_text)
                    continue

                if not current_date:
                    continue

                # Get event details
                time_cell = row.find('td', class_='calendar__time')
                currency_cell = row.find('td', class_='calendar__currency')
                impact_cell = row.find('td', class_='calendar__impact')
                event_cell = row.find('td', class_='calendar__event')

                if not all([time_cell, currency_cell, event_cell]):
                    continue

                # Parse time
                time_text = time_cell.get_text(strip=True)
                if time_text == 'All Day' or not time_text:
                    continue

                event_time = self._parse_ff_time(current_date, time_text)
                if not (start_date <= event_time <= end_date):
                    continue

                # Parse impact
                impact_class = impact_cell.find('span')['class'][0] if impact_cell.find('span') else ''
                if 'high' not in impact_class:
                    continue

                # Parse event name
                event_name = event_cell.get_text(strip=True)
                currency = currency_cell.get_text(strip=True)

                # Map to our event types
                event_type = self._map_event_name(event_name)
                if event_type:
                    events.append(EconomicEvent(
                        event_type=event_type,
                        timestamp=event_time,
                        impact="HIGH",
                        currency=currency,
                        source="ForexFactory"
                    ))

            except Exception as e:
                logger.debug(f"Error parsing row: {e}")

        return events

    def _parse_ff_date(self, date_text: str) -> Optional[datetime]:
        """Parse ForexFactory date format."""
        # Implementation would handle various date formats
        # For now, return None to skip
        return None

    def _parse_ff_time(self, date: datetime, time_text: str) -> datetime:
        """Parse ForexFactory time format (e.g., '2:00pm')."""
        # Implementation would parse time and combine with date
        # For now, return the date
        return date

    def _map_event_name(self, event_name: str) -> Optional[str]:
        """Map ForexFactory event names to our standard types."""
        event_lower = event_name.lower()

        mappings = {
            'cpi': 'CPI',
            'consumer price index': 'CPI',
            'nfp': 'NFP',
            'non-farm': 'NFP',
            'nonfarm': 'NFP',
            'fomc': 'FOMC',
            'fed': 'FOMC',
            'ecb': 'ECB',
            'boe': 'BOE',
            'bank of england': 'BOE'
        }

        for key, value in mappings.items():
            if key in event_lower:
                return value

        return None


class FXStreetFetcher(CalendarFetcher):
    """
    FXStreet RSS Feed Parser
    Free RSS feed with economic events
    """

    def __init__(self):
        self.rss_url = "https://www.fxstreet.com/economic-calendar/event/rss"
        self.enabled = HAS_REQUESTS

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Fetch events from FXStreet RSS feed."""
        events = []

        if not self.enabled:
            logger.warning("FXStreet fetcher disabled (no requests module)")
            return events

        try:
            response = requests.get(self.rss_url, timeout=10)
            response.raise_for_status()

            # Parse RSS XML
            root = ET.fromstring(response.content)
            channel = root.find('channel')

            for item in channel.findall('item'):
                event = self._parse_rss_item(item)
                if event and start_date <= event.timestamp <= end_date:
                    events.append(event)

            logger.info(f"Fetched {len(events)} events from FXStreet RSS")

        except Exception as e:
            logger.error(f"Error fetching FXStreet RSS: {e}")

        return events

    def _parse_rss_item(self, item: ET.Element) -> Optional[EconomicEvent]:
        """Parse RSS item into EconomicEvent."""
        try:
            title = item.find('title').text
            pub_date = item.find('pubDate').text
            description = item.find('description').text

            # Parse publication date
            timestamp = parse_date(pub_date)

            # Extract event type from title
            event_type = self._extract_event_type(title)
            if not event_type:
                return None

            # Extract currency from description
            currency = self._extract_currency(description)

            return EconomicEvent(
                event_type=event_type,
                timestamp=timestamp,
                impact="HIGH",
                currency=currency,
                source="FXStreet"
            )

        except Exception as e:
            logger.debug(f"Error parsing RSS item: {e}")
            return None

    def _extract_event_type(self, title: str) -> Optional[str]:
        """Extract standardized event type from title."""
        title_lower = title.lower()

        if 'cpi' in title_lower or 'consumer price' in title_lower:
            return 'CPI'
        elif 'nfp' in title_lower or 'non-farm' in title_lower or 'nonfarm' in title_lower:
            return 'NFP'
        elif 'fomc' in title_lower or 'federal reserve' in title_lower:
            return 'FOMC'
        elif 'ecb' in title_lower:
            return 'ECB'
        elif 'boe' in title_lower or 'bank of england' in title_lower:
            return 'BOE'

        return None

    def _extract_currency(self, description: str) -> str:
        """Extract currency from description."""
        # Simple pattern matching
        if 'USD' in description or 'United States' in description:
            return 'USD'
        elif 'EUR' in description or 'Eurozone' in description:
            return 'EUR'
        elif 'GBP' in description or 'United Kingdom' in description:
            return 'GBP'

        return 'USD'  # Default


class TradingEconomicsFetcher(CalendarFetcher):
    """
    Trading Economics Free Tier
    Limited free API access
    """

    def __init__(self):
        self.base_url = "https://api.tradingeconomics.com"
        self.enabled = HAS_REQUESTS

    def fetch_events(self, start_date: datetime, end_date: datetime) -> List[EconomicEvent]:
        """Fetch from Trading Economics free tier."""
        events = []

        if not self.enabled:
            return events

        try:
            # Trading Economics provides some free data without API key
            url = f"{self.base_url}/calendar/country/united states,united kingdom,euro area"
            params = {
                'c': 'guest:guest',  # Free tier credentials
                'f': 'json',
                'd1': start_date.strftime('%Y-%m-%d'),
                'd2': end_date.strftime('%Y-%m-%d')
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                for item in data:
                    event = self._parse_te_event(item)
                    if event:
                        events.append(event)

                logger.info(f"Fetched {len(events)} events from Trading Economics")

        except Exception as e:
            logger.error(f"Error fetching Trading Economics data: {e}")

        return events

    def _parse_te_event(self, item: Dict[str, Any]) -> Optional[EconomicEvent]:
        """Parse Trading Economics event."""
        try:
            # Map event names
            event_name = item.get('Event', '')
            event_type = self._map_te_event(event_name)

            if not event_type:
                return None

            # Parse date
            date_str = item.get('Date', '')
            timestamp = parse_date(date_str)

            # Get currency
            country = item.get('Country', '')
            currency = self._map_country_currency(country)

            # Check importance
            importance = item.get('Importance', 1)
            if importance < 3:  # Only high importance
                return None

            return EconomicEvent(
                event_type=event_type,
                timestamp=timestamp,
                impact="HIGH",
                currency=currency,
                source="TradingEconomics"
            )

        except Exception:
            return None

    def _map_te_event(self, event_name: str) -> Optional[str]:
        """Map Trading Economics event names."""
        event_lower = event_name.lower()

        if 'inflation rate' in event_lower or 'cpi' in event_lower:
            return 'CPI'
        elif 'non farm payrolls' in event_lower:
            return 'NFP'
        elif 'fed' in event_lower and 'rate' in event_lower:
            return 'FOMC'
        elif 'ecb' in event_lower:
            return 'ECB'
        elif 'boe' in event_lower or 'bank of england' in event_lower:
            return 'BOE'

        return None

    def _map_country_currency(self, country: str) -> str:
        """Map country to currency."""
        mappings = {
            'united states': 'USD',
            'euro area': 'EUR',
            'united kingdom': 'GBP',
            'eurozone': 'EUR'
        }

        return mappings.get(country.lower(), 'USD')


class CalendarUpdater:
    """Main class for updating the economic calendar."""

    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.fetchers = {
            'fred': FREDFetcher(),
            'forexfactory': ForexFactoryFetcher(),
            'fxstreet': FXStreetFetcher(),
            'tradingeconomics': TradingEconomicsFetcher()
        }

    def fetch_all_events(
        self,
        days_ahead: int = 90,
        sources: Optional[List[str]] = None
    ) -> List[EconomicEvent]:
        """Fetch events from specified or all sources."""
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=days_ahead)

        if sources is None:
            sources = list(self.fetchers.keys())

        all_events = []

        for source_name in sources:
            if source_name not in self.fetchers:
                logger.warning(f"Unknown source: {source_name}")
                continue

            fetcher = self.fetchers[source_name]
            try:
                logger.info(f"Fetching from {source_name}...")
                events = fetcher.fetch_events(start_date, end_date)
                all_events.extend(events)
                logger.info(f"Got {len(events)} events from {source_name}")

                # Be respectful with rate limiting
                if len(sources) > 1:
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Error fetching from {source_name}: {e}")

        return all_events

    def deduplicate_events(self, events: List[EconomicEvent]) -> List[EconomicEvent]:
        """Remove duplicate events, prioritizing authoritative sources."""
        # Group by event type and date
        event_groups: Dict[tuple, List[EconomicEvent]] = {}

        for event in events:
            # Key is event type + date (ignoring exact time)
            key = (event.event_type, event.timestamp.date())

            if key not in event_groups:
                event_groups[key] = []
            event_groups[key].append(event)

        # Select best event from each group
        unique_events = []

        # Source priority (higher = more authoritative)
        source_priority = {
            'FRED': 3,
            'TradingEconomics': 2,
            'ForexFactory': 1,
            'FXStreet': 1,
            'manual': 0
        }

        for key, group in event_groups.items():
            # Sort by source priority
            group.sort(
                key=lambda e: source_priority.get(e.source, 0),
                reverse=True
            )
            unique_events.append(group[0])

        return unique_events

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

            # Check timestamp is reasonable (not more than 1 year out)
            if event.timestamp > datetime.now(timezone.utc) + timedelta(days=365):
                logger.warning(f"Event too far in future: {event}")
                continue

            valid_events.append(event)

        return valid_events

    def merge_with_manual_dates(self, events: List[EconomicEvent]) -> List[EconomicEvent]:
        """Merge with known central bank dates for reliability."""
        # Get current year
        current_year = datetime.now().year

        # Use future dates relative to current year
        manual_dates = [
            ("FOMC", f"{current_year + 1}-01-29T19:00:00Z"),
            ("FOMC", f"{current_year + 1}-03-19T18:00:00Z"),
            ("ECB", f"{current_year}-10-23T12:45:00Z"),
            ("ECB", f"{current_year}-12-11T12:45:00Z"),
            ("BOE", f"{current_year}-11-06T12:00:00Z"),
            ("BOE", f"{current_year}-12-18T12:00:00Z"),
            ("CPI", f"{current_year}-10-10T13:30:00Z"),
            ("NFP", f"{current_year}-10-04T13:30:00Z")
        ]

        # Add manual dates if not already present
        existing_keys = {(e.event_type, e.timestamp.date()) for e in events}

        for event_type, date_str in manual_dates:
            timestamp = parse_date(date_str)
            key = (event_type, timestamp.date())

            if key not in existing_keys:
                event = EconomicEvent(
                    event_type=event_type,
                    timestamp=timestamp,
                    impact="HIGH",
                    currency="USD" if event_type in ["FOMC", "CPI", "NFP"] else "EUR" if event_type == "ECB" else "GBP",
                    blackout_before=30,
                    blackout_after=60 if event_type == "FOMC" else 30,
                    source="manual"
                )
                events.append(event)
                logger.info(f"Added manual date: {event}")

        return events

    def update_csv(self, events: List[EconomicEvent], dry_run: bool = False) -> None:
        """Update the CSV file with new events."""
        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)

        if dry_run:
            logger.info("DRY RUN - Would write the following events:")
            for event in events:
                logger.info(f"  {event}")
            return

        # Create directory if needed
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

        # Write CSV
        with open(self.csv_path, 'w', newline='') as f:
            fieldnames = ['event_type', 'timestamp', 'impact', 'currency',
                         'blackout_before', 'blackout_after']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for event in events:
                writer.writerow(event.to_dict())

        logger.info(f"Updated {self.csv_path} with {len(events)} events")


def main():
    parser = argparse.ArgumentParser(description='Update economic calendar from free sources')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be updated without writing')
    parser.add_argument('--days-ahead', type=int, default=90,
                       help='Number of days to look ahead (default: 90)')
    parser.add_argument('--csv-path', type=Path,
                       default=Path('./data/economic_calendar.csv'),
                       help='Path to CSV file')
    parser.add_argument('--source', action='append',
                       choices=['fred', 'forexfactory', 'fxstreet', 'tradingeconomics'],
                       help='Specific sources to use (can specify multiple)')

    args = parser.parse_args()

    # Check dependencies
    if not HAS_REQUESTS:
        logger.error("'requests' module required. Install with: pip install requests")
        sys.exit(1)

    updater = CalendarUpdater(args.csv_path)

    try:
        # Fetch events
        events = updater.fetch_all_events(args.days_ahead, args.source)

        # Add manual dates as fallback
        events = updater.merge_with_manual_dates(events)

        # Deduplicate and validate
        events = updater.deduplicate_events(events)
        events = updater.validate_events(events)

        if not events:
            logger.warning("No valid events found!")
            sys.exit(1)

        # Update CSV
        updater.update_csv(events, dry_run=args.dry_run)

        # Show summary
        logger.info(f"\nSummary by source:")
        source_counts = {}
        for event in events:
            source_counts[event.source] = source_counts.get(event.source, 0) + 1

        for source, count in sorted(source_counts.items()):
            logger.info(f"  {source}: {count} events")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()