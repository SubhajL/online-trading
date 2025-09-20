"""
Tests for Binance WebSocket and REST ingestors.

Tests closed candle filtering, reconnection backfill, deduplication,
rate limiting, and time sync error handling.
"""

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.engine.types import Candle, TimeFrame, kline_to_candle, rest_kline_to_candle
from app.engine.ingest.binance_spot import BinanceSpotIngester
from app.engine.ingest.binance_usdm import BinanceUSDMIngester


# Fixtures for WebSocket kline messages
@pytest.fixture
def partial_kline_message():
    """Kline message with x=false (not closed)"""
    return {
        "e": "kline",
        "E": 1638360000000,
        "s": "BTCUSDT",
        "k": {
            "t": 1638360000000,  # Kline start time
            "T": 1638360299999,  # Kline close time
            "s": "BTCUSDT",      # Symbol
            "i": "5m",           # Interval
            "f": 100,            # First trade ID
            "L": 200,            # Last trade ID
            "o": "50000.0",      # Open
            "c": "50100.0",      # Close
            "h": "50200.0",      # High
            "l": "49900.0",      # Low
            "v": "100.5",        # Base asset volume
            "n": 100,            # Number of trades
            "x": False,          # Is this kline closed?
            "q": "5025000.0",    # Quote asset volume
            "V": "50.5",         # Taker buy base asset volume
            "Q": "2527500.0"     # Taker buy quote asset volume
        }
    }


@pytest.fixture
def closed_kline_message():
    """Kline message with x=true (closed)"""
    return {
        "e": "kline",
        "E": 1638360300000,
        "s": "BTCUSDT",
        "k": {
            "t": 1638360000000,
            "T": 1638360299999,
            "s": "BTCUSDT",
            "i": "5m",
            "f": 100,
            "L": 250,
            "o": "50000.0",
            "c": "50150.0",
            "h": "50200.0",
            "l": "49900.0",
            "v": "120.5",
            "n": 150,
            "x": True,  # Closed candle
            "q": "6037500.0",
            "V": "60.5",
            "Q": "3037500.0"
        }
    }


@pytest.fixture
def rest_kline_data():
    """REST API kline response data"""
    return [
        [
            1638360000000,  # Open time
            "50000.0",      # Open
            "50200.0",      # High
            "49900.0",      # Low
            "50150.0",      # Close
            "120.5",        # Volume
            1638360299999,  # Close time
            "6037500.0",    # Quote asset volume
            150,            # Number of trades
            "60.5",         # Taker buy base asset volume
            "3037500.0",    # Taker buy quote asset volume
            "0"             # Ignore
        ]
    ]


@pytest.fixture
def mock_db_adapter():
    """Mock TimescaleDB adapter"""
    adapter = AsyncMock()
    adapter.get_latest_candle = AsyncMock(return_value=None)
    adapter.insert_candle = AsyncMock(return_value=True)
    adapter.get_candles = AsyncMock(return_value=[])
    return adapter


@pytest.fixture
def mock_event_bus():
    """Mock event bus"""
    bus = AsyncMock()
    bus.publish = AsyncMock(return_value=True)
    return bus


class TestKlineTransformUtilities:
    """Test kline to candle transformation utilities"""

    def test_kline_to_candle_spot(self, closed_kline_message):
        """Test WebSocket kline to Candle conversion for spot"""
        candle = kline_to_candle(closed_kline_message["k"], "spot")

        assert candle.symbol == "BTCUSDT"
        assert candle.timeframe == TimeFrame.M5
        assert candle.open_price == Decimal("50000.0")
        assert candle.close_price == Decimal("50150.0")
        assert candle.high_price == Decimal("50200.0")
        assert candle.low_price == Decimal("49900.0")
        assert candle.volume == Decimal("120.5")
        assert candle.trades == 150
        assert candle.open_time == datetime.fromtimestamp(1638360000000 / 1000)
        assert candle.close_time == datetime.fromtimestamp(1638360299999 / 1000)

    def test_kline_to_candle_futures(self, closed_kline_message):
        """Test WebSocket kline to Candle conversion for futures"""
        candle = kline_to_candle(closed_kline_message["k"], "usdm")

        assert candle.symbol == "BTCUSDT"
        assert candle.timeframe == TimeFrame.M5

    def test_rest_kline_to_candle(self, rest_kline_data):
        """Test REST API kline to Candle conversion"""
        candle = rest_kline_to_candle(
            rest_kline_data[0],
            symbol="BTCUSDT",
            timeframe="5m",
            venue="spot"
        )

        assert candle.symbol == "BTCUSDT"
        assert candle.timeframe == TimeFrame.M5
        assert candle.open_price == Decimal("50000.0")
        assert candle.close_price == Decimal("50150.0")
        assert candle.high_price == Decimal("50200.0")
        assert candle.low_price == Decimal("49900.0")
        assert candle.volume == Decimal("120.5")
        assert candle.trades == 150


class TestBinanceSpotIngester:
    """Test Binance Spot ingester functionality"""

    @pytest.mark.asyncio
    async def test_partial_vs_closed_candle(self, partial_kline_message, closed_kline_message, mock_db_adapter, mock_event_bus):
        """Verify only closed candles (x=true) are emitted"""
        ingester = BinanceSpotIngester(
            db_adapter=mock_db_adapter,
            event_bus=mock_event_bus,
            symbols=["BTCUSDT"],
            timeframes=["5m"]
        )

        # Process partial candle
        await ingester._on_kline_message(partial_kline_message)
        mock_event_bus.publish.assert_not_called()
        mock_db_adapter.insert_candle.assert_not_called()

        # Process closed candle
        await ingester._on_kline_message(closed_kline_message)
        mock_event_bus.publish.assert_called_once()
        mock_db_adapter.insert_candle.assert_called_once()

        # Verify event published with correct topic
        call_args = mock_event_bus.publish.call_args
        assert call_args[0][0] == "candles.v1"
        assert isinstance(call_args[0][1], dict)

    @pytest.mark.asyncio
    async def test_websocket_reconnection_triggers_backfill(self, mock_db_adapter, mock_event_bus):
        """Test that reconnection triggers REST backfill"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value=[])
            mock_response.status = 200
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_response

            ingester = BinanceSpotIngester(
                db_adapter=mock_db_adapter,
                event_bus=mock_event_bus,
                symbols=["BTCUSDT"],
                timeframes=["5m"]
            )

            # Mock latest candle from 10 minutes ago
            latest_candle = MagicMock()
            latest_candle.close_time = datetime.utcnow() - timedelta(minutes=10)
            mock_db_adapter.get_latest_candle.return_value = latest_candle

            await ingester._on_reconnect()

            # Verify backfill was called
            mock_session.return_value.get.assert_called()
            call_url = mock_session.return_value.get.call_args[0][0]
            assert "/api/v3/klines" in call_url

    @pytest.mark.asyncio
    async def test_rest_backfill_deduplication(self, rest_kline_data, mock_db_adapter, mock_event_bus):
        """Verify no duplicate candle inserts"""
        # Setup existing candle in DB
        existing_candle = MagicMock()
        existing_candle.open_time = datetime.fromtimestamp(1638360000000 / 1000)
        mock_db_adapter.get_candles.return_value = [existing_candle]

        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value=rest_kline_data)
            mock_response.status = 200
            mock_session.return_value.get.return_value.__aenter__.return_value = mock_response

            ingester = BinanceSpotIngester(
                db_adapter=mock_db_adapter,
                event_bus=mock_event_bus,
                symbols=["BTCUSDT"],
                timeframes=["5m"]
            )

            await ingester._backfill_missing_candles("BTCUSDT", "5m", datetime.utcnow() - timedelta(hours=1))

            # Should not insert duplicate
            mock_db_adapter.insert_candle.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, mock_db_adapter, mock_event_bus):
        """Test exponential backoff on 429 rate limit"""
        with patch('aiohttp.ClientSession') as mock_session:
            # First call returns 429, second succeeds
            mock_response_429 = AsyncMock()
            mock_response_429.status = 429
            mock_response_429.headers = {"Retry-After": "1"}

            mock_response_ok = AsyncMock()
            mock_response_ok.status = 200
            mock_response_ok.json = AsyncMock(return_value=[])

            mock_session.return_value.get.return_value.__aenter__.side_effect = [
                mock_response_429, mock_response_ok
            ]

            ingester = BinanceSpotIngester(
                db_adapter=mock_db_adapter,
                event_bus=mock_event_bus,
                symbols=["BTCUSDT"],
                timeframes=["5m"]
            )

            with patch('asyncio.sleep') as mock_sleep:
                await ingester._backfill_missing_candles("BTCUSDT", "5m", datetime.utcnow() - timedelta(hours=1))

                # Verify exponential backoff was applied
                mock_sleep.assert_called()
                assert mock_sleep.call_args[0][0] >= 1  # At least 1 second delay


class TestBinanceUSDMIngester:
    """Test Binance USD-M Futures ingester functionality"""

    @pytest.mark.asyncio
    async def test_time_sync_error_recovery(self, mock_db_adapter, mock_event_bus):
        """Test handling of -1021 time sync errors"""
        with patch('aiohttp.ClientSession') as mock_session:
            # First call returns -1021 error, second succeeds
            mock_response_error = AsyncMock()
            mock_response_error.status = 400
            mock_response_error.json = AsyncMock(return_value={
                "code": -1021,
                "msg": "Timestamp for this request was 1000ms ahead of the server's time."
            })

            mock_response_ok = AsyncMock()
            mock_response_ok.status = 200
            mock_response_ok.json = AsyncMock(return_value=[])

            mock_session.return_value.get.return_value.__aenter__.side_effect = [
                mock_response_error, mock_response_ok
            ]

            ingester = BinanceUSDMIngester(
                db_adapter=mock_db_adapter,
                event_bus=mock_event_bus,
                symbols=["BTCUSDT"],
                timeframes=["5m"]
            )

            await ingester._backfill_missing_candles("BTCUSDT", "5m", datetime.utcnow() - timedelta(hours=1))

            # Verify retry with adjusted recvWindow
            assert mock_session.return_value.get.call_count == 2
            second_call_url = mock_session.return_value.get.call_args_list[1][0][0]
            assert "recvWindow=" in second_call_url

    @pytest.mark.asyncio
    async def test_futures_websocket_url(self, mock_db_adapter, mock_event_bus):
        """Test that futures ingester uses correct WebSocket URL"""
        ingester = BinanceUSDMIngester(
            db_adapter=mock_db_adapter,
            event_bus=mock_event_bus,
            symbols=["BTCUSDT"],
            timeframes=["5m"]
        )

        # Verify futures WebSocket URL
        assert "fstream" in ingester.ws_base_url or "dstream" in ingester.ws_base_url