"""Tests for ingest service persistence logging.

Verifies that persistence logs accurately reflect insert_candle() return value:
- INFO log "Persisted" only when insert returns True
- WARNING log when insert returns False
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.bus import set_event_bus
from app.engine.ingest.ingest_service import IngestService
from app.engine.models import Candle, CandleOrigin, CandleUpdateEvent, EventType, TimeFrame


@pytest.fixture(autouse=True)
def mock_event_bus_global() -> AsyncMock:
    """Set up a mock event bus globally for all tests."""
    mock_bus = AsyncMock()
    mock_bus.subscribe = AsyncMock(return_value="sub-id")
    mock_bus.unsubscribe = AsyncMock()
    mock_bus.publish = AsyncMock()
    set_event_bus(mock_bus)
    yield mock_bus


@pytest.fixture
def mock_db_adapter() -> MagicMock:
    """Create a mock database adapter."""
    adapter = MagicMock()
    adapter.insert_candle = AsyncMock(return_value=True)
    return adapter


@pytest.fixture
def sample_candle() -> Candle:
    """Create a sample candle for testing."""
    return Candle(
        venue="SPOT",
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        open_time=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        close_time=datetime(2024, 1, 15, 10, 35, 0, tzinfo=timezone.utc),
        open_price=Decimal("42000.00"),
        high_price=Decimal("42100.00"),
        low_price=Decimal("41900.00"),
        close_price=Decimal("42050.00"),
        volume=Decimal("100.5"),
        quote_volume=Decimal("4200000.00"),
        trades=1500,
        taker_buy_base_volume=Decimal("50.25"),
        taker_buy_quote_volume=Decimal("2100000.00"),
    )


@pytest.fixture
def realtime_candle_event(sample_candle: Candle) -> CandleUpdateEvent:
    """Create a REALTIME candle update event."""
    return CandleUpdateEvent(
        event_type=EventType.CANDLE_UPDATE,
        timestamp=datetime.now(timezone.utc),
        symbol=sample_candle.symbol,
        timeframe=sample_candle.timeframe,
        candle=sample_candle,
        origin=CandleOrigin.REALTIME,
    )


class TestIngestPersistenceLogging:
    """Tests for persistence logging in IngestService."""

    @pytest.mark.asyncio
    async def test_logs_persisted_only_on_successful_insert(
        self,
        mock_db_adapter: MagicMock,
        mock_event_bus_global: AsyncMock,
        realtime_candle_event: CandleUpdateEvent,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """INFO log 'Persisted' appears only when insert_candle returns True."""
        mock_db_adapter.insert_candle = AsyncMock(return_value=True)

        service = IngestService(
            binance_config={"spot": {"api_key": "test", "api_secret": "test"}, "testnet": True},
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )

        with caplog.at_level(logging.INFO):
            await service._on_candle_update(realtime_candle_event)

        # Verify insert was called
        mock_db_adapter.insert_candle.assert_called_once_with(realtime_candle_event.candle)

        # Verify INFO log with "Persisted" is present
        persisted_logs = [r for r in caplog.records if "Persisted" in r.message and r.levelno == logging.INFO]
        assert len(persisted_logs) == 1
        assert "realtime" in persisted_logs[0].message.lower()

    @pytest.mark.asyncio
    async def test_logs_warning_on_failed_insert(
        self,
        mock_db_adapter: MagicMock,
        mock_event_bus_global: AsyncMock,
        realtime_candle_event: CandleUpdateEvent,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """WARNING log appears when insert_candle returns False, no 'Persisted' INFO."""
        mock_db_adapter.insert_candle = AsyncMock(return_value=False)

        service = IngestService(
            binance_config={"spot": {"api_key": "test", "api_secret": "test"}, "testnet": True},
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )

        with caplog.at_level(logging.WARNING):
            await service._on_candle_update(realtime_candle_event)

        # Verify insert was called
        mock_db_adapter.insert_candle.assert_called_once_with(realtime_candle_event.candle)

        # Verify WARNING log is present
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1
        assert any("Failed to persist" in r.message for r in warning_logs)

        # Verify NO INFO log with "Persisted" is present
        persisted_info_logs = [
            r for r in caplog.records if "Persisted" in r.message and r.levelno == logging.INFO
        ]
        assert len(persisted_info_logs) == 0

    @pytest.mark.asyncio
    async def test_no_persist_log_for_backfill_candles(
        self,
        mock_db_adapter: MagicMock,
        mock_event_bus_global: AsyncMock,
        sample_candle: Candle,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """BACKFILL candles skip persistence and don't log 'Persisted'."""
        backfill_event = CandleUpdateEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(timezone.utc),
            symbol=sample_candle.symbol,
            timeframe=sample_candle.timeframe,
            candle=sample_candle,
            origin=CandleOrigin.BACKFILL,
        )

        service = IngestService(
            binance_config={"spot": {"api_key": "test", "api_secret": "test"}, "testnet": True},
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M5],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )

        with caplog.at_level(logging.DEBUG):
            await service._on_candle_update(backfill_event)

        # insert_candle should NOT be called for BACKFILL
        mock_db_adapter.insert_candle.assert_not_called()

        # No "Persisted" log should appear
        persisted_logs = [r for r in caplog.records if "Persisted" in r.message]
        assert len(persisted_logs) == 0
