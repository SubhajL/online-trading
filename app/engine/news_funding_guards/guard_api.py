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

    async def initialize(self) -> None:
        """Initialize guard components."""
        raise NotImplementedError()

    async def check_trading_allowed(
        self,
        symbol: str,
        position_side: str,
        current_time: datetime | None = None,
    ) -> tuple[GuardStatus, str]:
        """Main API to check if trading is allowed."""
        raise NotImplementedError()

    async def get_guard_status(self) -> dict[str, Any]:
        """Get current status of all guards."""
        raise NotImplementedError()

    def set_override(
        self,
        guard_type: str,
        override_status: GuardStatus | None,
    ) -> None:
        """Set manual override for specific guard."""
        raise NotImplementedError()