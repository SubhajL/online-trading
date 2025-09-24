"""Tests for news and funding guards."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
import asyncio

from app.engine.news_funding_guards.calendar import EconomicEvent
from app.engine.news_funding_guards.funding import FundingRateData, is_funding_safe
from app.engine.news_funding_guards.guard_api import check_all_guards


def test_news_window_blocking():
    """Ensure proper blackout periods around news events."""
    # Create a high-impact event
    event_time = datetime.now(timezone.utc) + timedelta(minutes=15)
    event = EconomicEvent(
        event_type="FOMC",
        timestamp=event_time,
        impact="HIGH",
        currency="USD",
    )

    # Before blackout window (> 30 mins before)
    current_time = event_time - timedelta(minutes=35)
    assert event.is_in_blackout_window(current_time) is False

    # Within blackout window (15 mins before)
    current_time = event_time - timedelta(minutes=15)
    assert event.is_in_blackout_window(current_time) is True

    # During event
    assert event.is_in_blackout_window(event_time) is True

    # After event but within blackout (15 mins after)
    current_time = event_time + timedelta(minutes=15)
    assert event.is_in_blackout_window(current_time) is True

    # After blackout window (> 30 mins after)
    current_time = event_time + timedelta(minutes=35)
    assert event.is_in_blackout_window(current_time) is False


def test_funding_threshold():
    """Verify 0.05% funding rate blocking."""
    # Create funding data
    funding_data = FundingRateData(
        symbol="BTCUSDT",
        current_rate=Decimal("0.0001"),  # 0.01%
        predicted_rate=Decimal("0.0006"),  # 0.06%
        next_funding_time=datetime.now(timezone.utc) + timedelta(hours=4),
    )

    # Long position pays funding when rate is positive
    # 0.06% > 0.05% threshold - should block
    assert is_funding_safe(
        funding_data,
        position_side="LONG",
        max_payment_rate=Decimal("0.0005"),  # 0.05%
    ) is False

    # Short position receives funding when rate is positive - should be safe
    assert is_funding_safe(
        funding_data,
        position_side="SHORT",
        max_payment_rate=Decimal("0.0005"),
    ) is True

    # Lower funding rate - should be safe for long
    funding_data.predicted_rate = Decimal("0.0003")  # 0.03%
    assert is_funding_safe(
        funding_data,
        position_side="LONG",
        max_payment_rate=Decimal("0.0005"),
    ) is True


def test_negative_funding_rates():
    """Test behavior with negative funding rates."""
    funding_data = FundingRateData(
        symbol="BTCUSDT",
        current_rate=Decimal("-0.0001"),
        predicted_rate=Decimal("-0.0006"),  # -0.06%
        next_funding_time=datetime.now(timezone.utc) + timedelta(hours=4),
    )

    # With negative rate, shorts pay and longs receive
    # Short paying 0.06% > 0.05% threshold - should block
    assert is_funding_safe(
        funding_data,
        position_side="SHORT",
        max_payment_rate=Decimal("0.0005"),
    ) is False

    # Long receives funding - should be safe
    assert is_funding_safe(
        funding_data,
        position_side="LONG",
        max_payment_rate=Decimal("0.0005"),
    ) is True


@pytest.mark.asyncio
async def test_combined_guards():
    """Test combined news and funding guard decisions."""
    # Mock calendar manager
    class MockCalendarManager:
        def __init__(self, in_blackout: bool):
            self.in_blackout = in_blackout

        def is_news_blackout(self, current_time=None):
            return self.in_blackout

    # Mock funding monitor
    class MockFundingMonitor:
        def __init__(self, funding_safe: bool):
            self.funding_safe = funding_safe

        async def check_funding_safety(self, symbol, position_side):
            if self.funding_safe:
                return (True, "Funding rate acceptable")
            return (False, "Funding rate too high")

    # Both guards safe
    status, reason = await check_all_guards(
        symbol="BTCUSDT",
        position_side="LONG",
        calendar_manager=MockCalendarManager(in_blackout=False),
        funding_monitor=MockFundingMonitor(funding_safe=True),
    )
    assert status == "SAFE"

    # News blackout active
    status, reason = await check_all_guards(
        symbol="BTCUSDT",
        position_side="LONG",
        calendar_manager=MockCalendarManager(in_blackout=True),
        funding_monitor=MockFundingMonitor(funding_safe=True),
    )
    assert status == "BLOCK"
    assert "news" in reason.lower()

    # Funding rate too high
    status, reason = await check_all_guards(
        symbol="BTCUSDT",
        position_side="LONG",
        calendar_manager=MockCalendarManager(in_blackout=False),
        funding_monitor=MockFundingMonitor(funding_safe=False),
    )
    assert status == "BLOCK"
    assert "funding" in reason.lower()