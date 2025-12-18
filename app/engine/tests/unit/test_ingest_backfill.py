"""
Tests for IngestService backfill behavior.

These tests verify that backfill writes directly to DB and only publishes
a limited number of recent candles for pipeline warm-up.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.bus import set_event_bus
from app.engine.models import Candle, CandleOrigin, TimeFrame


@pytest.fixture(autouse=True)
def mock_event_bus_global():
    """Set up a mock event bus globally for all tests."""
    mock_bus = AsyncMock()
    set_event_bus(mock_bus)
    yield mock_bus


def make_test_candles(count: int, symbol: str = "BTCUSDT") -> list[Candle]:
    """Create a list of test candles with sequential timestamps."""
    base_time = datetime.now(UTC) - timedelta(hours=count)
    candles = []
    for i in range(count):
        candles.append(
            Candle(
                symbol=symbol,
                timeframe=TimeFrame.M15,
                open_time=base_time + timedelta(minutes=i * 15),
                close_time=base_time + timedelta(minutes=(i + 1) * 15),
                open_price=Decimal("50000.00") + Decimal(i),
                high_price=Decimal("50500.00") + Decimal(i),
                low_price=Decimal("49500.00") + Decimal(i),
                close_price=Decimal("50250.00") + Decimal(i),
                volume=Decimal("100.5"),
                quote_volume=Decimal("5000000.00"),
                trades=1000,
                taker_buy_base_volume=Decimal("50.0"),
                taker_buy_quote_volume=Decimal("2500000.00"),
            )
        )
    return candles


class TestIngestServiceBackfill:
    """Tests for IngestService backfill optimization."""

    @pytest.mark.asyncio
    async def test_backfill_writes_to_db_not_event_bus(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill should write candles to DB instead of publishing each one."""
        from app.engine.ingest.ingest_service import IngestService

        # Create mocks
        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=100)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(
            return_value=make_test_candles(100)
        )

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,  # Don't auto-start backfill
            db_adapter=mock_db_adapter,
        )
        # Replace REST client with mock
        service._rest_client = mock_rest_client

        # Run backfill manually
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # Verify DB batch insert was called
        mock_db_adapter.insert_candles_batch.assert_called_once()
        inserted_candles = mock_db_adapter.insert_candles_batch.call_args[0][0]
        assert len(inserted_candles) == 100

        # Verify event bus publish was called far fewer times (only warmup candles)
        # Should be <= WARMUP_CANDLE_COUNT (default 10)
        assert mock_event_bus_global.publish.call_count <= 10

    @pytest.mark.asyncio
    async def test_backfill_publishes_warmup_candles_with_backfill_origin(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Warmup candles should be published with BACKFILL origin."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=50)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(
            return_value=make_test_candles(50)
        )

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )
        service._rest_client = mock_rest_client

        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # Check that published events have BACKFILL origin
        if mock_event_bus_global.publish.call_count > 0:
            for call in mock_event_bus_global.publish.call_args_list:
                event = call[0][0]
                assert event.origin == CandleOrigin.BACKFILL

    @pytest.mark.asyncio
    async def test_backfill_marks_completion(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill should mark symbol-timeframe as complete."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=10)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(
            return_value=make_test_candles(10)
        )

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )
        service._rest_client = mock_rest_client

        assert not service.is_backfill_complete("BTCUSDT", TimeFrame.M15)

        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        assert service.is_backfill_complete("BTCUSDT", TimeFrame.M15)

    @pytest.mark.asyncio
    async def test_backfill_updates_latest_candle_tracking(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill should update latest candle tracking."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=20)

        candles = make_test_candles(20)
        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=candles)

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )
        service._rest_client = mock_rest_client

        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # Latest candle should be the last one
        latest = await service.get_latest_candle("BTCUSDT", TimeFrame.M15)
        assert latest is not None
        assert latest.open_time == candles[-1].open_time

    @pytest.mark.asyncio
    async def test_backfill_handles_empty_response(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill should handle empty REST response gracefully."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=0)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=[])

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )
        service._rest_client = mock_rest_client

        # Reset mock to clear any calls from __init__
        mock_event_bus_global.publish.reset_mock()

        # Should not raise
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # DB should not be called with empty list
        mock_db_adapter.insert_candles_batch.assert_not_called()

        # Event bus should not be called
        mock_event_bus_global.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_backfill_without_db_adapter_falls_back_to_event_bus(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Without DB adapter, backfill should publish all candles to event bus."""
        from app.engine.ingest.ingest_service import IngestService

        candles = make_test_candles(20)
        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=candles)

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=None,  # No DB adapter
        )
        service._rest_client = mock_rest_client

        # Reset mock to clear any calls from __init__
        mock_event_bus_global.publish.reset_mock()

        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # All candles should be published to event bus (legacy behavior)
        assert mock_event_bus_global.publish.call_count == 20
