"""
Main Guard API

Combines news and funding guards to provide unified SAFE/BLOCK decisions.
"""

from datetime import datetime
from decimal import Decimal
import logging
from typing import Any, Literal

from .calendar import CalendarManager
from .funding import FundingMonitor

logger = logging.getLogger(__name__)

GuardStatus = Literal["SAFE", "BLOCK"]


async def check_all_guards(
    symbol: str,
    position_side: str,
    calendar_manager: CalendarManager | None = None,
    funding_monitor: FundingMonitor | None = None,
) -> tuple[GuardStatus, str]:
    """
    Check all trading guards and return combined status.

    Returns (status, reason) where status is SAFE or BLOCK.
    """
    # Check news guard
    if calendar_manager:
        is_blocked, reason = check_news_blackout(calendar_manager)
        if is_blocked:
            return ("BLOCK", reason)

    # Check funding guard
    if funding_monitor:
        is_safe, reason = await evaluate_funding_safety(
            symbol, position_side, funding_monitor
        )
        if not is_safe:
            return ("BLOCK", reason)

    return ("SAFE", "All guards passed")


def check_news_blackout(
    calendar_manager: CalendarManager,
    current_time: datetime | None = None,
) -> tuple[bool, str]:
    """Check if currently in news blackout window."""
    if calendar_manager.is_news_blackout(current_time):
        return (True, "Trading blocked: High-impact news event window")
    return (False, "No news events")


async def evaluate_funding_safety(
    symbol: str,
    position_side: str,
    funding_monitor: FundingMonitor,
) -> tuple[bool, str]:
    """Evaluate funding rate safety."""
    return await funding_monitor.check_funding_safety(symbol, position_side)


class GuardService:
    """Main service coordinating all trading guards."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.calendar_manager = CalendarManager(config.get("calendar", {}))
        self.funding_monitor = FundingMonitor(config.get("funding", {}))
        self._initialized = False
        self._overrides: dict[str, GuardStatus | None] = {}

    async def initialize(self) -> None:
        """Initialize guard components."""
        if self._initialized:
            return

        try:
            # Load calendar events
            await self.calendar_manager.load_events()

            self._initialized = True
            logger.info("GuardService initialized")

        except Exception as e:
            logger.error(f"Error initializing GuardService: {e}", exc_info=True)

    async def check_trading_allowed(
        self,
        symbol: str,
        position_side: str,
        current_time: datetime | None = None,
    ) -> tuple[GuardStatus, str]:
        """Main API to check if trading is allowed."""
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        # Check overrides
        if "all" in self._overrides and self._overrides["all"] is not None:
            return (self._overrides["all"], "Manual override active")

        # Check news guard
        if self._overrides.get("news") != "SAFE":
            is_blocked, reason = check_news_blackout(
                self.calendar_manager,
                current_time
            )
            if is_blocked:
                return ("BLOCK", reason)

        # Check funding guard (futures only)
        if symbol.endswith("USDT") and self.config.get("funding_check_enabled", True):
            if self._overrides.get("funding") != "SAFE":
                is_safe, reason = await evaluate_funding_safety(
                    symbol,
                    position_side,
                    self.funding_monitor
                )
                if not is_safe:
                    return ("BLOCK", reason)

        return ("SAFE", "All guards passed")

    async def get_guard_status(self) -> dict[str, Any]:
        """Get current status of all guards."""
        status = {
            "initialized": self._initialized,
            "overrides": self._overrides,
            "news": {
                "blackout": self.calendar_manager.is_news_blackout(),
                "upcoming_events": [
                    {
                        "event_type": e.event_type,
                        "timestamp": e.timestamp.isoformat(),
                        "impact": e.impact,
                        "currency": e.currency,
                    }
                    for e in self.calendar_manager.get_upcoming_events(hours_ahead=24)
                ],
            },
            "funding": {},
        }

        # Get funding status for common symbols
        symbols = ["BTCUSDT", "ETHUSDT"]
        if self.funding_monitor:
            status["funding"] = await self.funding_monitor.evaluate_funding_risk(symbols)

        return status

    def set_override(
        self,
        guard_type: str,
        override_status: GuardStatus | None,
    ) -> None:
        """Set manual override for specific guard."""
        self._overrides[guard_type] = override_status
        logger.info(f"Set override for {guard_type}: {override_status}")