"""
Trading policies for backtesting: session windows, guards, and regime filters.
Enforces same rules as live Decision engine.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from ..models import TechnicalIndicators


class SessionPolicy:
    """
    Handles trading session windows and excluded periods.
    """

    def __init__(
        self,
        enabled: bool = True,
        exclude_periods: list[str] | None = None,
    ):
        """
        Initialize session policy.

        Args:
            enabled: Whether session filtering is enabled
            exclude_periods: List of excluded time ranges like "00:55-01:10Z"
        """
        self.enabled = enabled
        self.excluded_ranges = []

        if exclude_periods:
            for period in exclude_periods:
                self.excluded_ranges.append(self._parse_time_range(period))

    def _parse_time_range(self, time_range: str) -> tuple[time, time]:
        """
        Parse time range string like "00:55-01:10Z" into time objects.

        Args:
            time_range: Time range string

        Returns:
            Tuple of start and end time objects
        """
        # Remove 'Z' suffix if present
        clean_range = time_range.rstrip("Z")
        start_str, end_str = clean_range.split("-")

        start_parts = start_str.split(":")
        end_parts = end_str.split(":")

        start_time = time(int(start_parts[0]), int(start_parts[1]))
        end_time = time(int(end_parts[0]), int(end_parts[1]))

        return start_time, end_time

    def is_trading_allowed(self, timestamp: datetime) -> bool:
        """
        Check if trading is allowed at given timestamp.

        Args:
            timestamp: UTC timestamp to check

        Returns:
            True if trading is allowed
        """
        if not self.enabled:
            return True

        current_time = timestamp.time()

        # Check against excluded periods
        for start_time, end_time in self.excluded_ranges:
            if start_time <= end_time:
                # Same day range
                if start_time <= current_time <= end_time:
                    return False
            # Cross-midnight range
            elif current_time >= start_time or current_time <= end_time:
                return False

        return True


class NewsGuardPolicy:
    """
    Blocks trading around news events.
    """

    def __init__(
        self,
        enabled: bool = True,
        before_minutes: int = 15,
        after_minutes: int = 15,
    ):
        """
        Initialize news guard policy.

        Args:
            enabled: Whether news blocking is enabled
            before_minutes: Minutes to block before news
            after_minutes: Minutes to block after news
        """
        self.enabled = enabled
        self.before_minutes = before_minutes
        self.after_minutes = after_minutes
        self.news_events = []  # TODO: Load from calendar

    def add_news_event(
        self,
        timestamp: datetime,
        impact: str = "HIGH",
        currency: str = "USD",
    ):
        """
        Add a news event to the calendar.

        Args:
            timestamp: News event time
            impact: Impact level (LOW, MEDIUM, HIGH)
            currency: Affected currency
        """
        self.news_events.append(
            {
                "timestamp": timestamp,
                "impact": impact,
                "currency": currency,
            },
        )

    def is_news_block_active(self, timestamp: datetime, symbol: str) -> bool:
        """
        Check if news block is active at given timestamp.

        Args:
            timestamp: Current timestamp
            symbol: Trading symbol (e.g., "BTCUSDT")

        Returns:
            True if news block is active
        """
        if not self.enabled:
            return False

        # Extract currency from symbol
        # Simple heuristic: if symbol contains USD, check USD news
        currencies_to_check = ["USD"]  # Always check USD news
        if "BTC" in symbol:
            currencies_to_check.append("BTC")
        if "ETH" in symbol:
            currencies_to_check.append("ETH")

        for event in self.news_events:
            if event["currency"] not in currencies_to_check:
                continue

            # Only block for HIGH impact news
            if event["impact"] != "HIGH":
                continue

            news_time = event["timestamp"]
            block_start = news_time - timedelta(minutes=self.before_minutes)
            block_end = news_time + timedelta(minutes=self.after_minutes)

            if block_start <= timestamp <= block_end:
                return True

        return False


class FundingGuardPolicy:
    """
    Blocks trading around funding times for futures.
    """

    def __init__(
        self,
        enabled: bool = True,
        funding_threshold_pct: Decimal = Decimal("0.05"),  # 0.05%
        block_minutes_before: int = 10,
        block_minutes_after: int = 10,
    ):
        """
        Initialize funding guard policy.

        Args:
            enabled: Whether funding blocking is enabled
            funding_threshold_pct: Block if funding rate exceeds this %
            block_minutes_before: Minutes to block before funding
            block_minutes_after: Minutes to block after funding
        """
        self.enabled = enabled
        self.funding_threshold = funding_threshold_pct / Decimal(100)
        self.block_minutes_before = block_minutes_before
        self.block_minutes_after = block_minutes_after

    def is_funding_block_active(
        self,
        timestamp: datetime,
        current_funding_rate: Decimal,
    ) -> bool:
        """
        Check if funding block is active.

        Args:
            timestamp: Current timestamp
            current_funding_rate: Current funding rate

        Returns:
            True if funding block is active
        """
        if not self.enabled:
            return False

        # Check if funding rate exceeds threshold
        if abs(current_funding_rate) < self.funding_threshold:
            return False

        # Check if we're near a funding time (00:00, 08:00, 16:00 UTC)
        funding_hours = {0, 8, 16}
        current_hour = timestamp.hour
        current_minute = timestamp.minute

        for funding_hour in funding_hours:
            # Calculate time difference to funding hour
            funding_time = timestamp.replace(
                hour=funding_hour,
                minute=0,
                second=0,
                microsecond=0,
            )

            # Handle day rollover
            if funding_hour < current_hour:
                funding_time += timedelta(days=1)

            time_to_funding = (funding_time - timestamp).total_seconds() / 60

            # Check if within blocking window
            if (
                -self.block_minutes_after
                <= time_to_funding
                <= self.block_minutes_before
            ):
                return True

        return False


class RegimeFilter:
    """
    Filters trades based on market regime.
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize regime filter.

        Args:
            enabled: Whether regime filtering is enabled
        """
        self.enabled = enabled

    def is_regime_favorable(
        self,
        regime: str,
        signal_direction: str,
        indicators: TechnicalIndicators,
    ) -> bool:
        """
        Check if current regime is favorable for signal direction.

        Args:
            regime: Current market regime (trending/ranging/volatile)
            signal_direction: "long" or "short"
            indicators: Technical indicators for additional context

        Returns:
            True if regime is favorable
        """
        if not self.enabled:
            return True

        # Simple regime rules - can be enhanced
        if regime == "trending":
            # Trending markets favor directional trades
            return True

        if regime == "ranging":
            # Ranging markets favor mean reversion
            # Could check if signal aligns with range boundaries
            if indicators.rsi is not None:
                if signal_direction == "long" and indicators.rsi < 30:
                    return True  # Oversold in range
                if signal_direction == "short" and indicators.rsi > 70:
                    return True  # Overbought in range

        elif regime == "volatile":
            # Volatile markets - be more cautious
            # Could reduce position size or skip entirely
            return False

        return True


class TradingPolicyManager:
    """
    Manages all trading policies and provides unified filtering.
    """

    def __init__(
        self,
        session_policy: SessionPolicy | None = None,
        news_guard: NewsGuardPolicy | None = None,
        funding_guard: FundingGuardPolicy | None = None,
        regime_filter: RegimeFilter | None = None,
    ):
        """
        Initialize policy manager.

        Args:
            session_policy: Session window policy
            news_guard: News guard policy
            funding_guard: Funding guard policy
            regime_filter: Regime filter policy
        """
        self.session_policy = session_policy or SessionPolicy()
        self.news_guard = news_guard or NewsGuardPolicy()
        self.funding_guard = funding_guard or FundingGuardPolicy()
        self.regime_filter = regime_filter or RegimeFilter()

    def is_trading_allowed(
        self,
        timestamp: datetime,
        symbol: str,
        signal_direction: str | None = None,
        regime: str | None = None,
        indicators: TechnicalIndicators | None = None,
        funding_rate: Decimal | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Check if trading is allowed considering all policies.

        Args:
            timestamp: Current timestamp
            symbol: Trading symbol
            signal_direction: "long" or "short" if checking signal
            regime: Current market regime
            indicators: Technical indicators
            funding_rate: Current funding rate for futures

        Returns:
            Tuple of (allowed, list_of_blocking_reasons)
        """
        blocking_reasons = []

        # Check session policy
        if not self.session_policy.is_trading_allowed(timestamp):
            blocking_reasons.append("session_excluded")

        # Check news guard
        if self.news_guard.is_news_block_active(timestamp, symbol):
            blocking_reasons.append("news_block")

        # Check funding guard (for futures)
        if funding_rate is not None:
            if self.funding_guard.is_funding_block_active(timestamp, funding_rate):
                blocking_reasons.append("funding_block")

        # Check regime filter (if signal provided)
        if signal_direction and regime and indicators:
            if not self.regime_filter.is_regime_favorable(
                regime, signal_direction, indicators,
            ):
                blocking_reasons.append("regime_unfavorable")

        is_allowed = len(blocking_reasons) == 0
        return is_allowed, blocking_reasons

    def get_policy_status(self, timestamp: datetime, symbol: str) -> dict[str, bool]:
        """
        Get status of all policies at given timestamp.

        Args:
            timestamp: Current timestamp
            symbol: Trading symbol

        Returns:
            Dictionary with policy statuses
        """
        return {
            "session_allowed": self.session_policy.is_trading_allowed(timestamp),
            "news_block_active": self.news_guard.is_news_block_active(
                timestamp, symbol,
            ),
            "funding_block_active": self.funding_guard.is_funding_block_active(
                timestamp,
                Decimal("0.001"),  # Sample funding rate
            ),
            "regime_filter_enabled": self.regime_filter.enabled,
        }
