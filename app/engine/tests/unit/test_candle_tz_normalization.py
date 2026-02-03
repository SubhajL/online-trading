"""Tests for datetime timezone normalization in TimescaleDB adapter.

Verifies that tz-aware datetimes are converted to naive UTC before passing
to asyncpg, which requires naive datetimes for TIMESTAMP WITHOUT TIME ZONE columns.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter, _to_naive_utc
from app.engine.models import Candle, TimeFrame


class TestToNaiveUtc:
    """Tests for the _to_naive_utc helper function."""

    def test_strips_utc_tzinfo(self) -> None:
        """tz-aware UTC datetime becomes naive UTC."""
        dt_aware = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        result = _to_naive_utc(dt_aware)

        assert result.tzinfo is None
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_converts_non_utc_to_utc_then_strips(self) -> None:
        """Non-UTC timezone converts to UTC then strips tzinfo."""
        # 10:30 AM in US/Eastern (UTC-5) = 15:30 UTC
        eastern = ZoneInfo("America/New_York")
        dt_eastern = datetime(2024, 1, 15, 10, 30, 0, tzinfo=eastern)

        result = _to_naive_utc(dt_eastern)

        assert result.tzinfo is None
        # Eastern is UTC-5 in January (no DST)
        assert result == datetime(2024, 1, 15, 15, 30, 0)

    def test_leaves_naive_datetime_unchanged(self) -> None:
        """Naive datetime passes through unchanged."""
        dt_naive = datetime(2024, 1, 15, 10, 30, 0)

        result = _to_naive_utc(dt_naive)

        assert result.tzinfo is None
        assert result == dt_naive
        assert result is dt_naive  # Should be the same object


class TestInsertCandleNormalization:
    """Tests that insert_candle normalizes datetime fields."""

    @pytest.fixture
    def adapter(self) -> TimescaleDBAdapter:
        """Create adapter without connecting."""
        return TimescaleDBAdapter(
            host="localhost",
            port=5432,
            database="test",
            username="test",
            password="test",
        )

    @pytest.fixture
    def tz_aware_candle(self) -> Candle:
        """Create a candle with tz-aware datetimes."""
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

    @pytest.mark.asyncio
    async def test_passes_naive_datetimes_to_asyncpg(
        self, adapter: TimescaleDBAdapter, tz_aware_candle: Candle
    ) -> None:
        """insert_candle passes naive open_time/close_time to conn.execute."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        adapter._write_pool = mock_pool
        adapter._initialized = True

        result = await adapter.insert_candle(tz_aware_candle)

        assert result is True
        mock_conn.execute.assert_called_once()

        # Extract positional args from the execute call
        call_args = mock_conn.execute.call_args[0]
        # Args are: SQL, venue, symbol, timeframe, open_time, close_time, ...
        open_time_arg = call_args[4]
        close_time_arg = call_args[5]

        # Both should be naive (no tzinfo)
        assert open_time_arg.tzinfo is None, "open_time should be naive"
        assert close_time_arg.tzinfo is None, "close_time should be naive"

        # Values should be correct (same as input, just without tzinfo)
        assert open_time_arg == datetime(2024, 1, 15, 10, 30, 0)
        assert close_time_arg == datetime(2024, 1, 15, 10, 35, 0)


class TestInsertCandlesBatchNormalization:
    """Tests that insert_candles_batch normalizes datetime fields."""

    @pytest.fixture
    def adapter(self) -> TimescaleDBAdapter:
        """Create adapter without connecting."""
        return TimescaleDBAdapter(
            host="localhost",
            port=5432,
            database="test",
            username="test",
            password="test",
        )

    @pytest.fixture
    def tz_aware_candles(self) -> list[Candle]:
        """Create multiple candles with tz-aware datetimes."""
        return [
            Candle(
                venue="SPOT",
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=datetime(2024, 1, 15, 10, 30 + i * 5, 0, tzinfo=timezone.utc),
                close_time=datetime(2024, 1, 15, 10, 35 + i * 5, 0, tzinfo=timezone.utc),
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
            for i in range(3)
        ]

    @pytest.mark.asyncio
    async def test_executemany_path_normalizes_all_rows(
        self, adapter: TimescaleDBAdapter, tz_aware_candles: list[Candle]
    ) -> None:
        """insert_candles_batch (executemany path) normalizes all datetime fields."""
        mock_conn = AsyncMock()
        mock_conn.executemany = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        adapter._write_pool = mock_pool
        adapter._initialized = True

        # Ensure we use executemany path (threshold > batch size)
        with patch.dict("os.environ", {"TIMESCALE_COPY_THRESHOLD": "1000"}):
            result = await adapter.insert_candles_batch(tz_aware_candles)

        assert result == 3
        mock_conn.executemany.assert_called_once()

        # Extract records from executemany call
        call_args = mock_conn.executemany.call_args[0]
        records = call_args[1]

        for record in records:
            # open_time is at index 3, close_time is at index 4
            open_time = record[3]
            close_time = record[4]

            assert open_time.tzinfo is None, "open_time should be naive"
            assert close_time.tzinfo is None, "close_time should be naive"

    @pytest.mark.asyncio
    async def test_copy_path_normalizes_all_rows(
        self, adapter: TimescaleDBAdapter, tz_aware_candles: list[Candle]
    ) -> None:
        """insert_candles_batch (COPY path) normalizes all datetime fields."""
        mock_conn = AsyncMock()
        mock_conn.copy_records_to_table = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        adapter._write_pool = mock_pool
        adapter._initialized = True

        # Force COPY path by setting low threshold
        with patch.dict("os.environ", {"TIMESCALE_COPY_THRESHOLD": "1"}):
            result = await adapter.insert_candles_copy(tz_aware_candles)

        assert result == 3
        mock_conn.copy_records_to_table.assert_called_once()

        # Extract records from copy_records_to_table call
        call_kwargs = mock_conn.copy_records_to_table.call_args[1]
        records = call_kwargs["records"]

        for record in records:
            # open_time is at index 3, close_time is at index 4
            open_time = record[3]
            close_time = record[4]

            assert open_time.tzinfo is None, "open_time should be naive"
            assert close_time.tzinfo is None, "close_time should be naive"
