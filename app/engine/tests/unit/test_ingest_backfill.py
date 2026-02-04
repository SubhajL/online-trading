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
                venue="spot",
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
        from app.engine.ingest.ingest_service import IngestService, WARMUP_CANDLE_COUNT

        # Create more candles than WARMUP_CANDLE_COUNT to test limiting
        total_candles = WARMUP_CANDLE_COUNT + 100  # 350 candles

        # Create mocks
        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=total_candles)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(
            return_value=make_test_candles(total_candles)
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

        # Verify DB batch insert was called with all candles
        mock_db_adapter.insert_candles_batch.assert_called_once()
        inserted_candles = mock_db_adapter.insert_candles_batch.call_args[0][0]
        assert len(inserted_candles) == total_candles

        # Verify event bus publish was called only for warmup candles (not all)
        # Should be exactly WARMUP_CANDLE_COUNT
        assert mock_event_bus_global.publish.call_count == WARMUP_CANDLE_COUNT

    @pytest.mark.asyncio
    async def test_backfill_publishes_warmup_candles_with_backfill_origin(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Warmup candles should be published with BACKFILL origin."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=50)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=make_test_candles(50))

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
    async def test_backfill_marks_completion(self, mock_event_bus_global: AsyncMock) -> None:
        """Backfill should mark symbol-timeframe as complete."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=10)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=make_test_candles(10))

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
    async def test_backfill_handles_empty_response(self, mock_event_bus_global: AsyncMock) -> None:
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
    async def test_empty_backfill_still_marks_complete(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Empty backfill response should still mark backfill as complete."""
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

        # Before backfill, should not be complete
        assert service.is_backfill_complete("BTCUSDT", TimeFrame.M15) is False

        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # After empty backfill, should still mark as complete
        assert service.is_backfill_complete("BTCUSDT", TimeFrame.M15) is True

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


class TestIngestServiceStartupAlerts:
    """Tests for IngestService startup alert functionality."""

    @pytest.mark.asyncio
    async def test_publishes_backfill_complete_event_when_all_tasks_done(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """IngestService publishes STARTUP_COMPLETE when all backfill tasks complete."""
        from app.engine.ingest.ingest_service import IngestService
        from app.engine.models import EventType, StartupCompleteEvent

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=10)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=make_test_candles(10))

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
        mock_event_bus_global.publish.reset_mock()

        # Run backfill and wait for completion event
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)
        await service._check_and_publish_backfill_complete()

        # Find the StartupCompleteEvent in published events
        startup_events = [
            call[0][0]
            for call in mock_event_bus_global.publish.call_args_list
            if hasattr(call[0][0], "event_type")
            and call[0][0].event_type == EventType.STARTUP_COMPLETE
        ]

        assert len(startup_events) == 1
        event = startup_events[0]
        assert isinstance(event, StartupCompleteEvent)
        assert event.phase == "backfill_complete"
        assert "BTCUSDT" in event.symbols

    @pytest.mark.asyncio
    async def test_backfill_complete_event_includes_candle_counts(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill complete event includes candle counts per symbol."""
        from app.engine.ingest.ingest_service import IngestService
        from app.engine.models import EventType, StartupCompleteEvent

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=50)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=make_test_candles(50))

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )
        service._rest_client = mock_rest_client
        mock_event_bus_global.publish.reset_mock()

        # Run backfill for both symbols
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)
        await service._backfill_symbol_timeframe("ETHUSDT", TimeFrame.M15)
        await service._check_and_publish_backfill_complete()

        startup_events = [
            call[0][0]
            for call in mock_event_bus_global.publish.call_args_list
            if hasattr(call[0][0], "event_type")
            and call[0][0].event_type == EventType.STARTUP_COMPLETE
        ]

        assert len(startup_events) == 1
        event = startup_events[0]
        assert "BTCUSDT" in event.candle_counts
        assert "ETHUSDT" in event.candle_counts

    @pytest.mark.asyncio
    async def test_no_startup_event_until_all_backfills_done(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """No STARTUP_COMPLETE event until all symbol-timeframe combos finish."""
        from app.engine.ingest.ingest_service import IngestService
        from app.engine.models import EventType

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=10)

        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(return_value=make_test_candles(10))

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=[TimeFrame.M15, TimeFrame.H1],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )
        service._rest_client = mock_rest_client
        mock_event_bus_global.publish.reset_mock()

        # Only complete 1 of 4 backfills
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)
        await service._check_and_publish_backfill_complete()

        # No startup event should be published yet
        startup_events = [
            call[0][0]
            for call in mock_event_bus_global.publish.call_args_list
            if hasattr(call[0][0], "event_type")
            and call[0][0].event_type == EventType.STARTUP_COMPLETE
        ]
        assert len(startup_events) == 0


class TestIngestServiceBackfillExceptionHandling:
    """Tests for IngestService backfill exception handling."""

    @pytest.mark.asyncio
    async def test_backfill_marks_complete_on_exception(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill should mark symbol-timeframe as complete even when exception occurs.

        This prevents the system from waiting forever when a backfill fails.
        The startup event should still be published after all backfills complete,
        even if some failed with exceptions.
        """
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=10)

        # REST client throws an exception
        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(
            side_effect=Exception("Network error: connection refused")
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

        # Before backfill, should not be complete
        assert service.is_backfill_complete("BTCUSDT", TimeFrame.M15) is False

        # Run backfill - should not raise but should still mark as complete
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # After failed backfill, should still be marked as complete
        assert service.is_backfill_complete("BTCUSDT", TimeFrame.M15) is True

    @pytest.mark.asyncio
    async def test_backfill_tracks_failures_separately(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill should track failures separately for observability."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()

        # REST client throws an exception
        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
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

        # Verify failure is tracked
        assert "BTCUSDT_15m" in service._backfill_failures
        assert "API rate limit exceeded" in service._backfill_failures["BTCUSDT_15m"]

    @pytest.mark.asyncio
    async def test_startup_event_published_with_partial_failures(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """STARTUP_COMPLETE event should be published even when some backfills fail."""
        from app.engine.ingest.ingest_service import IngestService
        from app.engine.models import EventType, StartupCompleteEvent

        mock_db_adapter = AsyncMock()
        mock_db_adapter.insert_candles_batch = AsyncMock(return_value=10)

        # First call fails, second succeeds
        mock_rest_client = AsyncMock()
        mock_rest_client.get_historical_data = AsyncMock(
            side_effect=[
                Exception("Network error"),  # BTCUSDT fails
                make_test_candles(10),  # ETHUSDT succeeds
            ]
        )

        service = IngestService(
            binance_config={
                "spot": {"api_key": "test", "api_secret": "test"},
                "testnet": True,
            },
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=mock_db_adapter,
        )
        service._rest_client = mock_rest_client
        mock_event_bus_global.publish.reset_mock()

        # Run backfills
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)
        await service._backfill_symbol_timeframe("ETHUSDT", TimeFrame.M15)
        await service._check_and_publish_backfill_complete()

        # Both should be marked complete
        assert service.is_backfill_complete("BTCUSDT", TimeFrame.M15) is True
        assert service.is_backfill_complete("ETHUSDT", TimeFrame.M15) is True

        # Startup event should be published
        startup_events = [
            call[0][0]
            for call in mock_event_bus_global.publish.call_args_list
            if hasattr(call[0][0], "event_type")
            and call[0][0].event_type == EventType.STARTUP_COMPLETE
        ]

        assert len(startup_events) == 1
        event = startup_events[0]
        assert isinstance(event, StartupCompleteEvent)
        assert event.phase == "backfill_complete"

    @pytest.mark.asyncio
    async def test_backfill_marks_complete_on_db_insert_failure(
        self, mock_event_bus_global: AsyncMock
    ) -> None:
        """Backfill should mark complete even when DB insert fails."""
        from app.engine.ingest.ingest_service import IngestService

        mock_db_adapter = AsyncMock()
        # DB insert throws exception
        mock_db_adapter.insert_candles_batch = AsyncMock(
            side_effect=Exception("Database connection lost")
        )

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

        # Run backfill - should not raise
        await service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M15)

        # Should still be marked as complete
        assert service.is_backfill_complete("BTCUSDT", TimeFrame.M15) is True
