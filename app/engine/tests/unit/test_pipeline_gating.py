"""
Tests for pipeline gating in FeatureService and SMCEngine.

These tests verify that only REALTIME events trigger the trading pipeline,
while BACKFILL and GAP_FILL events only add to buffers without generating
trading signals or features events.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.bus import set_event_bus
from app.engine.models import (
    Candle,
    CandleOrigin,
    CandleUpdateEvent,
    EventType,
    TimeFrame,
)


@pytest.fixture(autouse=True)
def mock_event_bus_global():
    """Set up a mock event bus globally for all tests."""
    mock_bus = AsyncMock()
    set_event_bus(mock_bus)
    yield mock_bus


def make_test_candle(
    symbol: str = "BTCUSDT",
    timeframe: TimeFrame = TimeFrame.M15,
    idx: int = 0,
) -> Candle:
    """Create a test candle with valid data."""
    base_time = datetime.now(UTC) - timedelta(hours=100)
    return Candle(
        venue="SPOT",
        symbol=symbol,
        timeframe=timeframe,
        open_time=base_time + timedelta(minutes=idx * 15),
        close_time=base_time + timedelta(minutes=(idx + 1) * 15),
        open_price=Decimal("50000.00") + Decimal(idx * 10),
        high_price=Decimal("50500.00") + Decimal(idx * 10),
        low_price=Decimal("49500.00") + Decimal(idx * 10),
        close_price=Decimal("50250.00") + Decimal(idx * 10),
        volume=Decimal("100.5"),
        quote_volume=Decimal("5000000.00"),
        trades=1000,
        taker_buy_base_volume=Decimal("50.0"),
        taker_buy_quote_volume=Decimal("2500000.00"),
    )


def make_candle_event(
    candle: Candle,
    origin: CandleOrigin = CandleOrigin.REALTIME,
) -> CandleUpdateEvent:
    """Create a CandleUpdateEvent with specified origin."""
    return CandleUpdateEvent(
        timestamp=datetime.now(UTC),
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        candle=candle,
        origin=origin,
    )


class TestFeatureServiceGating:
    """Tests for FeatureService pipeline gating."""

    @pytest.mark.asyncio
    async def test_realtime_event_publishes_features(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """REALTIME events should trigger feature calculation and publish."""
        from app.engine.features.feature_service import FeatureService

        # Buffer must be large enough for EMA 200 calculation
        service = FeatureService(buffer_size=300)

        # Seed buffer with enough candles (need at least 200 for EMA 200)
        for i in range(250):
            candle = make_test_candle(idx=i)
            event = make_candle_event(candle, CandleOrigin.BACKFILL)
            await service._handle_candle_update(event)

        # Reset mock to clear backfill calls
        mock_event_bus_global.publish.reset_mock()

        # Now send a REALTIME event
        realtime_candle = make_test_candle(idx=250)
        realtime_event = make_candle_event(realtime_candle, CandleOrigin.REALTIME)
        await service._handle_candle_update(realtime_event)

        # Should have published features
        assert mock_event_bus_global.publish.call_count > 0
        # Published event should be FeaturesCalculatedEvent
        call_args = mock_event_bus_global.publish.call_args[0][0]
        assert call_args.event_type == EventType.FEATURES_CALCULATED

    @pytest.mark.asyncio
    async def test_backfill_event_does_not_publish_features(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """BACKFILL events should add to buffer but not publish features."""
        from app.engine.features.feature_service import FeatureService

        service = FeatureService(buffer_size=500)

        # Reset mock
        mock_event_bus_global.publish.reset_mock()

        # Send 250 BACKFILL events (enough for all indicators)
        for i in range(250):
            candle = make_test_candle(idx=i)
            event = make_candle_event(candle, CandleOrigin.BACKFILL)
            await service._handle_candle_update(event)

        # Should NOT have published any features
        assert mock_event_bus_global.publish.call_count == 0

        # But buffer should have candles
        buffer_info = service.get_buffer_info("BTCUSDT", TimeFrame.M15)
        assert buffer_info["size"] == 250

    @pytest.mark.asyncio
    async def test_gap_fill_event_does_not_publish_features(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """GAP_FILL events should add to buffer but not publish features."""
        from app.engine.features.feature_service import FeatureService

        service = FeatureService(buffer_size=500)

        # Seed with backfill
        for i in range(200):
            candle = make_test_candle(idx=i)
            event = make_candle_event(candle, CandleOrigin.BACKFILL)
            await service._handle_candle_update(event)

        # Reset mock
        mock_event_bus_global.publish.reset_mock()

        # Send GAP_FILL events
        for i in range(10):
            candle = make_test_candle(idx=200 + i)
            event = make_candle_event(candle, CandleOrigin.GAP_FILL)
            await service._handle_candle_update(event)

        # Should NOT have published any features
        assert mock_event_bus_global.publish.call_count == 0


class TestSMCEngineGating:
    """Tests for SMCEngine pipeline gating."""

    @pytest.mark.asyncio
    async def test_backfill_event_stores_but_does_not_process(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """BACKFILL events should store candles but not emit events."""
        from app.engine.smc.engine import SMCEngine

        service = SMCEngine()

        # Reset mock
        mock_event_bus_global.publish.reset_mock()

        # Send BACKFILL events
        for i in range(50):
            candle = make_test_candle(idx=i)
            event = make_candle_event(candle, CandleOrigin.BACKFILL)
            await service._handle_candle_update(event)

        # Should NOT have published any SMC signals
        assert mock_event_bus_global.publish.call_count == 0

        # But candle history should have data
        assert len(service._candle_history[("BTCUSDT", TimeFrame.M15)]) == 50

    @pytest.mark.asyncio
    async def test_gap_fill_event_stores_but_does_not_process(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """GAP_FILL events should store candles but not emit events."""
        from app.engine.smc.engine import SMCEngine

        service = SMCEngine()

        # Seed with backfill
        for i in range(30):
            candle = make_test_candle(idx=i)
            event = make_candle_event(candle, CandleOrigin.BACKFILL)
            await service._handle_candle_update(event)

        # Reset mock
        mock_event_bus_global.publish.reset_mock()

        # Send GAP_FILL events
        for i in range(10):
            candle = make_test_candle(idx=30 + i)
            event = make_candle_event(candle, CandleOrigin.GAP_FILL)
            await service._handle_candle_update(event)

        # Should NOT have published any SMC signals
        assert mock_event_bus_global.publish.call_count == 0

    @pytest.mark.asyncio
    async def test_realtime_event_triggers_processing(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """REALTIME events should be processed with emit_events enabled."""
        from app.engine.smc.engine import SMCEngine

        service = SMCEngine()
        process_candle = AsyncMock()

        with patch.object(service, "process_candle", process_candle):
            # Send REALTIME event
            realtime_candle = make_test_candle(idx=50)
            realtime_event = make_candle_event(realtime_candle, CandleOrigin.REALTIME)
            await service._handle_candle_update(realtime_event)

        process_candle.assert_awaited_once()
        _args, kwargs = process_candle.call_args
        assert kwargs["emit_events"] is True


class TestIsRealtimeCandleEvent:
    """Tests for the is_realtime_candle_event helper function."""

    def test_shared_is_realtime_candle_event(self) -> None:
        """Test is_realtime_candle_event from models."""
        from app.engine.models import is_realtime_candle_event

        assert is_realtime_candle_event(CandleOrigin.REALTIME) is True
        assert is_realtime_candle_event(CandleOrigin.BACKFILL) is False
        assert is_realtime_candle_event(CandleOrigin.GAP_FILL) is False

    def test_all_origin_values_covered(self) -> None:
        """Ensure all CandleOrigin values are handled correctly."""
        from app.engine.models import is_realtime_candle_event

        # Only REALTIME should return True
        tradeable_count = sum(
            1 for origin in CandleOrigin if is_realtime_candle_event(origin)
        )
        assert tradeable_count == 1  # Only REALTIME
