"""
Tests for CandleOrigin enum and CandleUpdateEvent origin field.

These tests verify the backfill vs realtime distinction for pipeline gating.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.engine.models import (
    Candle,
    CandleOrigin,
    CandleUpdateEvent,
    EventType,
    TimeFrame,
)


def make_test_candle(symbol: str = "BTCUSDT") -> Candle:
    """Create a test candle with valid data."""
    return Candle(
        symbol=symbol,
        timeframe=TimeFrame.M15,
        open_time=datetime.now(UTC),
        close_time=datetime.now(UTC),
        open_price=Decimal("50000.00"),
        high_price=Decimal("50500.00"),
        low_price=Decimal("49500.00"),
        close_price=Decimal("50250.00"),
        volume=Decimal("100.5"),
        quote_volume=Decimal("5000000.00"),
        trades=1000,
        taker_buy_base_volume=Decimal("50.0"),
        taker_buy_quote_volume=Decimal("2500000.00"),
    )


class TestCandleOrigin:
    """Tests for CandleOrigin enum."""

    def test_candle_origin_has_three_values(self) -> None:
        """CandleOrigin should have exactly three values."""
        assert len(CandleOrigin) == 3
        assert CandleOrigin.REALTIME.value == "realtime"
        assert CandleOrigin.BACKFILL.value == "backfill"
        assert CandleOrigin.GAP_FILL.value == "gap_fill"

    def test_candle_origin_is_string_enum(self) -> None:
        """CandleOrigin values should be usable as strings."""
        assert CandleOrigin.REALTIME.value == "realtime"
        assert CandleOrigin.BACKFILL.value == "backfill"
        # Can compare with string
        assert CandleOrigin.REALTIME == "realtime"
        assert CandleOrigin.BACKFILL == "backfill"


class TestCandleUpdateEventOrigin:
    """Tests for CandleUpdateEvent origin field."""

    def test_default_origin_is_realtime(self) -> None:
        """CandleUpdateEvent should default to REALTIME origin."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
        )
        assert event.origin == CandleOrigin.REALTIME

    def test_backfill_origin_can_be_set(self) -> None:
        """CandleUpdateEvent should accept BACKFILL origin."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
            origin=CandleOrigin.BACKFILL,
        )
        assert event.origin == CandleOrigin.BACKFILL

    def test_gap_fill_origin_can_be_set(self) -> None:
        """CandleUpdateEvent should accept GAP_FILL origin."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
            origin=CandleOrigin.GAP_FILL,
        )
        assert event.origin == CandleOrigin.GAP_FILL

    def test_event_type_is_candle_update(self) -> None:
        """CandleUpdateEvent should have CANDLE_UPDATE event type."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
        )
        assert event.event_type == EventType.CANDLE_UPDATE

    @pytest.mark.parametrize(
        "origin",
        [CandleOrigin.REALTIME, CandleOrigin.BACKFILL, CandleOrigin.GAP_FILL],
    )
    def test_origin_serializes_correctly(self, origin: CandleOrigin) -> None:
        """CandleOrigin should serialize to its string value."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
            origin=origin,
        )
        data = event.model_dump()
        assert data["origin"] == origin.value


def is_tradeable_event(event: CandleUpdateEvent) -> bool:
    """Check if an event should trigger the trading pipeline.

    Only REALTIME events should be processed by features/SMC/decision services.
    BACKFILL and GAP_FILL events are for data persistence only.
    """
    return event.origin == CandleOrigin.REALTIME


class TestIsTradeableEvent:
    """Tests for the is_tradeable_event helper function."""

    def test_realtime_event_is_tradeable(self) -> None:
        """REALTIME events should be tradeable."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
            origin=CandleOrigin.REALTIME,
        )
        assert is_tradeable_event(event) is True

    def test_backfill_event_is_not_tradeable(self) -> None:
        """BACKFILL events should not be tradeable."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
            origin=CandleOrigin.BACKFILL,
        )
        assert is_tradeable_event(event) is False

    def test_gap_fill_event_is_not_tradeable(self) -> None:
        """GAP_FILL events should not be tradeable."""
        event = CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=make_test_candle(),
            origin=CandleOrigin.GAP_FILL,
        )
        assert is_tradeable_event(event) is False
