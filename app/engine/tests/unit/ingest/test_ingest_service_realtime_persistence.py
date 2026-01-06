"""
Tests for IngestService real-time candle persistence.

Verifies that REALTIME CandleUpdateEvents are persisted to DB,
while BACKFILL events are skipped (already written during backfill).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.bus import create_event_bus, set_event_bus
from app.engine.models import (
    Candle,
    CandleOrigin,
    CandleUpdateEvent,
    TimeFrame,
)

if TYPE_CHECKING:
    from app.engine.bus import EventBus


@pytest.fixture(autouse=True)
def event_bus_fixture() -> EventBus:
    """Set up event bus for tests."""
    bus = create_event_bus()
    set_event_bus(bus)
    return bus


def _make_candle(
    symbol: str = "BTCUSDT",
    timeframe: TimeFrame = TimeFrame.M5,
    close_price: Decimal = Decimal(50000),
) -> Candle:
    """Create a test candle."""
    now = datetime.now(UTC).replace(microsecond=0)
    return Candle(
        venue="spot",
        symbol=symbol,
        timeframe=timeframe,
        open_time=now - timedelta(minutes=5),
        close_time=now,
        open_price=Decimal(49900),
        high_price=Decimal(50100),
        low_price=Decimal(49800),
        close_price=close_price,
        volume=Decimal(100),
        quote_volume=Decimal(5000000),
        trades=1000,
        taker_buy_base_volume=Decimal(50),
        taker_buy_quote_volume=Decimal(2500000),
    )


def _make_candle_update_event(
    origin: CandleOrigin = CandleOrigin.REALTIME,
    symbol: str = "BTCUSDT",
    timeframe: TimeFrame = TimeFrame.M5,
) -> CandleUpdateEvent:
    """Create a test CandleUpdateEvent with specified origin."""
    candle = _make_candle(symbol=symbol, timeframe=timeframe)
    return CandleUpdateEvent(
        timestamp=datetime.now(UTC),
        symbol=symbol,
        timeframe=timeframe,
        candle=candle,
        origin=origin,
    )


class TestRealtimeCandlePersistence:
    """Tests for real-time candle persistence in IngestService."""

    @pytest.mark.asyncio
    async def test_realtime_candle_update_is_persisted_to_db_adapter(self) -> None:
        """REALTIME CandleUpdateEvent calls db_adapter.insert_candle()."""
        from app.engine.ingest.ingest_service import IngestService

        # Create mock db_adapter
        mock_db_adapter = MagicMock()
        mock_db_adapter.insert_candle = AsyncMock(return_value=True)

        # Create IngestService with db_adapter
        service = IngestService(
            binance_config={
                "api_key": "test",
                "api_secret": "test",
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,  # Don't start WS
            enable_backfill=False,  # Don't start backfill
            db_adapter=mock_db_adapter,
        )

        # Create REALTIME event
        event = _make_candle_update_event(origin=CandleOrigin.REALTIME)

        # Call handler directly
        await service._on_candle_update(event)

        # Verify insert_candle was called with the candle
        mock_db_adapter.insert_candle.assert_called_once_with(event.candle)

    @pytest.mark.asyncio
    async def test_backfill_candle_update_is_not_persisted(self) -> None:
        """BACKFILL CandleUpdateEvent does NOT call db_adapter.insert_candle()."""
        from app.engine.ingest.ingest_service import IngestService

        # Create mock db_adapter
        mock_db_adapter = MagicMock()
        mock_db_adapter.insert_candle = AsyncMock(return_value=True)

        # Create IngestService with db_adapter
        service = IngestService(
            binance_config={
                "api_key": "test",
                "api_secret": "test",
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )

        # Create BACKFILL event
        event = _make_candle_update_event(origin=CandleOrigin.BACKFILL)

        # Call handler directly
        await service._on_candle_update(event)

        # Verify insert_candle was NOT called
        mock_db_adapter.insert_candle.assert_not_called()

    @pytest.mark.asyncio
    async def test_gap_fill_candle_update_is_persisted(self) -> None:
        """GAP_FILL CandleUpdateEvent calls db_adapter.insert_candle()."""
        from app.engine.ingest.ingest_service import IngestService

        # Create mock db_adapter
        mock_db_adapter = MagicMock()
        mock_db_adapter.insert_candle = AsyncMock(return_value=True)

        # Create IngestService with db_adapter
        service = IngestService(
            binance_config={
                "api_key": "test",
                "api_secret": "test",
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )

        # Create GAP_FILL event
        event = _make_candle_update_event(origin=CandleOrigin.GAP_FILL)

        # Call handler directly
        await service._on_candle_update(event)

        # GAP_FILL should also be persisted (filling gaps in data)
        mock_db_adapter.insert_candle.assert_called_once_with(event.candle)

    @pytest.mark.asyncio
    async def test_realtime_candle_updates_latest_candles_tracking(self) -> None:
        """REALTIME event updates _latest_candles dict."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = MagicMock()
        mock_db_adapter.insert_candle = AsyncMock(return_value=True)

        service = IngestService(
            binance_config={
                "api_key": "test",
                "api_secret": "test",
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )

        event = _make_candle_update_event(
            origin=CandleOrigin.REALTIME,
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
        )

        await service._on_candle_update(event)

        # Verify _latest_candles was updated
        assert "BTCUSDT" in service._latest_candles
        assert TimeFrame.M5 in service._latest_candles["BTCUSDT"]
        assert service._latest_candles["BTCUSDT"][TimeFrame.M5] == event.candle

    @pytest.mark.asyncio
    async def test_no_db_adapter_skips_persistence(self) -> None:
        """When db_adapter is None, persistence is skipped gracefully."""
        from app.engine.ingest.ingest_service import IngestService

        # Create IngestService WITHOUT db_adapter
        service = IngestService(
            binance_config={
                "api_key": "test",
                "api_secret": "test",
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=None,
        )

        event = _make_candle_update_event(origin=CandleOrigin.REALTIME)

        # Should not raise - just skip persistence
        await service._on_candle_update(event)

        # _latest_candles should still be updated
        assert "BTCUSDT" in service._latest_candles

    @pytest.mark.asyncio
    async def test_default_binance_urls_used_when_not_provided(self) -> None:
        """When base URLs are absent, clients use their defaults."""
        from app.engine.ingest.ingest_service import IngestService

        service = IngestService(
            binance_config={
                "api_key": "test",
                "api_secret": "test",
                "testnet": False,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=None,
        )

        assert service.ws_client.base_url == "wss://stream.binance.com:9443/ws/"
        assert service.rest_client.base_url == "https://api.binance.com"
