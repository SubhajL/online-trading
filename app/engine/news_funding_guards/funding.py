"""
Funding Rate Monitor for USD-M Futures

Blocks trading when predicted funding payment exceeds threshold.
"""

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any

logger = logging.getLogger(__name__)


class FundingRateData:
    """Funding rate information for a symbol."""

    def __init__(
        self,
        symbol: str,
        current_rate: Decimal,
        predicted_rate: Decimal | None,
        next_funding_time: datetime,
    ) -> None:
        self.symbol = symbol
        self.current_rate = current_rate
        self.predicted_rate = predicted_rate or current_rate
        self.next_funding_time = next_funding_time

    def get_predicted_payment_rate(self, position_side: str) -> Decimal:
        """Calculate predicted funding payment rate based on position side."""
        # Long positions pay funding when rate is positive
        # Short positions receive funding when rate is positive
        if position_side == "LONG":
            return self.predicted_rate
        # SHORT
        return -self.predicted_rate


async def get_funding_rate(
    symbol: str,
    exchange_client: Any,
) -> FundingRateData | None:
    """Fetch current and predicted funding rates."""
    try:
        # Mock implementation - would use exchange API
        # Example: response = await exchange_client.futures_funding_rate(symbol=symbol)

        # For now, return mock data
        current_time = datetime.now(UTC)
        next_funding = current_time.replace(minute=0, second=0, microsecond=0)

        # Round to next 8-hour funding interval
        hour = next_funding.hour
        next_hour = ((hour // 8) + 1) * 8
        if next_hour >= 24:
            next_funding = next_funding.replace(hour=0) + timedelta(days=1)
        else:
            next_funding = next_funding.replace(hour=next_hour)

        return FundingRateData(
            symbol=symbol,
            current_rate=Decimal("0.0001"),  # 0.01%
            predicted_rate=Decimal("0.0001"),  # Would calculate from order book
            next_funding_time=next_funding,
        )

    except Exception as e:
        logger.error(f"Error fetching funding rate for {symbol}: {e}")
        return None


def is_funding_safe(
    funding_data: FundingRateData,
    position_side: str,
    max_payment_rate: Decimal,
) -> bool:
    """Check if predicted funding payment is within acceptable threshold."""
    payment_rate = funding_data.get_predicted_payment_rate(position_side)

    # If we're receiving funding (negative payment), it's always safe
    if payment_rate < 0:
        return True

    # Check if we would pay more than threshold
    return payment_rate <= max_payment_rate


def calculate_hours_until_funding(funding_time: datetime) -> float:
    """Calculate hours until next funding."""
    current_time = datetime.now(UTC)
    time_diff = funding_time - current_time
    return max(0, time_diff.total_seconds() / 3600)


def should_block_near_funding(
    hours_until: float,
    blackout_hours_before: float,
) -> bool:
    """Check if too close to funding time."""
    return hours_until <= blackout_hours_before


class FundingMonitor:
    """Monitors funding rates and enforces safety thresholds."""

    def __init__(
        self,
        config: dict[str, Any],
        exchange_client: Any | None = None,
    ) -> None:
        self.config = config
        self.exchange_client = exchange_client
        self._cache: dict[str, tuple[FundingRateData, datetime]] = {}

        # Configuration
        self._cache_ttl_seconds = config.get("cache_ttl_seconds", 300)
        self.max_payment_rate = Decimal(str(config.get("max_payment_rate", 0.0005)))
        self.blackout_hours_before = config.get("blackout_hours_before_funding", 0.5)

    async def check_funding_safety(
        self,
        symbol: str,
        position_side: str,
    ) -> tuple[bool, str]:
        """
        Check if funding rate is safe for trading.

        Returns (is_safe, reason)
        """
        try:
            # Get funding data
            funding_data = await self.get_current_funding(symbol)
            if not funding_data:
                return (True, "No funding data available")

            # Check funding rate threshold
            if not is_funding_safe(funding_data, position_side, self.max_payment_rate):
                payment_rate = funding_data.get_predicted_payment_rate(position_side)
                return (
                    False,
                    f"Predicted funding payment too high: {payment_rate:.4%}",
                )

            # Check if too close to funding time
            hours_until = calculate_hours_until_funding(funding_data.next_funding_time)
            if should_block_near_funding(hours_until, self.blackout_hours_before):
                return (False, f"Too close to funding time: {hours_until:.1f}h")

            return (True, "Funding rate acceptable")

        except Exception as e:
            logger.error(f"Error checking funding safety: {e}", exc_info=True)
            return (True, "Error checking funding - allowing trade")

    async def get_current_funding(
        self,
        symbol: str,
    ) -> FundingRateData | None:
        """Get current funding rate data with caching."""
        # Check cache
        if self._is_cache_valid(symbol):
            return self._cache[symbol][0]

        # Fetch new data
        funding_data = await get_funding_rate(symbol, self.exchange_client)

        if funding_data:
            self._cache[symbol] = (funding_data, datetime.now(UTC))

        return funding_data

    def _is_cache_valid(
        self,
        symbol: str,
        max_age_seconds: int | None = None,
    ) -> bool:
        """Check if cached data is still valid."""
        if symbol not in self._cache:
            return False

        if max_age_seconds is None:
            max_age_seconds = self._cache_ttl_seconds

        _, cache_time = self._cache[symbol]
        age_seconds = (datetime.now(UTC) - cache_time).total_seconds()

        return age_seconds < max_age_seconds

    async def evaluate_funding_risk(
        self,
        symbols: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Evaluate funding risk for multiple symbols."""
        results = {}

        for symbol in symbols:
            funding_data = await self.get_current_funding(symbol)

            if funding_data:
                hours_until = calculate_hours_until_funding(
                    funding_data.next_funding_time,
                )

                results[symbol] = {
                    "current_rate": float(funding_data.current_rate),
                    "predicted_rate": float(funding_data.predicted_rate),
                    "next_funding_time": funding_data.next_funding_time.isoformat(),
                    "hours_until_funding": hours_until,
                    "long_payment": float(
                        funding_data.get_predicted_payment_rate("LONG"),
                    ),
                    "short_payment": float(
                        funding_data.get_predicted_payment_rate("SHORT"),
                    ),
                    "near_funding": should_block_near_funding(
                        hours_until, self.blackout_hours_before,
                    ),
                }
            else:
                results[symbol] = {"error": "No funding data available"}

        return results
