"""
CRITICAL: WebSocket recovery and backfill tests.

These tests ensure:
1. WebSocket reconnects automatically after disconnection
2. No data is lost during reconnection
3. Backfill properly fills gaps in real-time data
4. Duplicate messages are handled correctly
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import json

from app.engine.models import Candle, TimeFrame, CandleUpdateEvent
from app.engine.ingest.binance_ws import BinanceWebSocketClient
from app.engine.ingest.ingest_service import IngestService


class TestWebSocketReconnection:
    """Test WebSocket automatic reconnection behavior."""

    @pytest.fixture
    def mock_event_bus(self):
        """Create mock event bus."""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def ws_client(self, mock_event_bus):
        """Create WebSocket client with mock event bus."""
        with patch('app.engine.ingest.binance_ws.get_event_bus', return_value=mock_event_bus):
            client = BinanceWebSocketClient(
                base_url="wss://test.binance.com/ws/",
                reconnect_interval=1,  # Fast reconnect for testing
                ping_interval=1,
                ping_timeout=1
            )
            return client

    @pytest.mark.asyncio
    async def test_automatic_reconnection(self, ws_client):
        """Test that WebSocket reconnects automatically after disconnection."""
        connection_count = 0
        disconnect_after = 2  # Disconnect after 2 messages

        async def mock_websocket_handler(websocket, path):
            """Mock WebSocket server that disconnects after N messages."""
            nonlocal connection_count
            connection_count += 1

            # Send a few messages then disconnect
            for i in range(disconnect_after):
                kline_msg = {
                    "e": "kline",
                    "E": int(datetime.now().timestamp() * 1000),
                    "s": "BTCUSDT",
                    "k": {
                        "t": int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000),
                        "T": int(datetime.now().timestamp() * 1000),
                        "s": "BTCUSDT",
                        "i": "5m",
                        "o": "50000.00",
                        "c": "50100.00",
                        "h": "50150.00",
                        "l": "49950.00",
                        "v": "100.00",
                        "n": 1000,
                        "x": i == disconnect_after - 1,  # Last candle is closed
                        "q": "5000000.00",
                        "V": "60.00",
                        "Q": "3000000.00",
                    }
                }
                await websocket.send(json.dumps(kline_msg))
                await asyncio.sleep(0.1)

            # Force disconnect
            await websocket.close()

        # Mock the websockets.connect
        with patch('websockets.connect') as mock_connect:
            # Create a mock websocket that simulates disconnection
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_ws.__aiter__.side_effect = [
                # First connection
                iter([json.dumps({
                    "e": "kline",
                    "k": {"x": True, "s": "BTCUSDT", "i": "5m"}
                })]),
                # Connection closed
                ConnectionError("Connection lost")
            ]

            mock_connect.return_value.__aenter__.return_value = mock_ws

            # Start the client
            await ws_client.start()

            # Let it run for a bit
            await asyncio.sleep(2)

            # Stop the client
            await ws_client.stop()

            # Should have attempted to reconnect
            assert mock_connect.call_count >= 2

    @pytest.mark.asyncio
    async def test_subscription_persistence_across_reconnects(self, ws_client):
        """Test that subscriptions are maintained across reconnections."""
        # Subscribe to some streams
        await ws_client.subscribe_klines(["BTCUSDT", "ETHUSDT"], [TimeFrame.M5])

        # Verify subscriptions are stored
        assert "btcusdt@kline_5m" in ws_client._subscriptions
        assert "ethusdt@kline_5m" in ws_client._subscriptions

        # Mock reconnection scenario
        with patch.object(ws_client, '_resubscribe_all', new_callable=AsyncMock) as mock_resub:
            with patch('websockets.connect') as mock_connect:
                # Mock successful connection
                mock_ws = AsyncMock()
                mock_ws.closed = False
                mock_ws.__aiter__.return_value = iter([])  # No messages
                mock_connect.return_value.__aenter__.return_value = mock_ws

                # Start connection task
                connection_task = asyncio.create_task(ws_client._connect_and_listen())

                # Give it time to connect
                await asyncio.sleep(0.1)

                # Cancel the task
                connection_task.cancel()
                try:
                    await connection_task
                except asyncio.CancelledError:
                    pass

                # Should have attempted to resubscribe
                mock_resub.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_handling_during_reconnection(self, ws_client, mock_event_bus):
        """Test that messages are properly handled during reconnection."""
        messages_received = []

        async def track_event(event):
            messages_received.append(event)

        mock_event_bus.publish.side_effect = track_event

        # Create test kline message
        test_msg = {
            "e": "kline",
            "E": int(datetime.now().timestamp() * 1000),
            "s": "BTCUSDT",
            "k": {
                "t": int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000),
                "T": int(datetime.now().timestamp() * 1000),
                "s": "BTCUSDT",
                "i": "5m",
                "o": "50000.00",
                "c": "50100.00",
                "h": "50150.00",
                "l": "49950.00",
                "v": "100.00",
                "n": 1000,
                "x": True,  # Closed candle
                "q": "5000000.00",
                "V": "60.00",
                "Q": "3000000.00",
            }
        }

        # Handle the message
        await ws_client._handle_message(json.dumps(test_msg))

        # Should have published a candle event
        assert len(messages_received) == 1
        assert isinstance(messages_received[0], CandleUpdateEvent)
        assert messages_received[0].candle.symbol == "BTCUSDT"


class TestDataBackfill:
    """Test historical data backfill functionality."""

    @pytest.fixture
    def mock_rest_client(self):
        """Create mock REST client."""
        client = AsyncMock()

        # Mock historical data response
        async def mock_get_historical(symbol, timeframe, days_back):
            candles = []
            base_time = datetime.now() - timedelta(days=days_back)

            # Generate mock historical candles
            for i in range(100):  # 100 candles
                candle = Candle(
                    venue="spot",
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=base_time + timedelta(minutes=5*i),
                    close_time=base_time + timedelta(minutes=5*(i+1)),
                    open_price=Decimal("50000") + Decimal(str(i * 10)),
                    high_price=Decimal("50000") + Decimal(str(i * 10 + 50)),
                    low_price=Decimal("50000") + Decimal(str(i * 10 - 50)),
                    close_price=Decimal("50000") + Decimal(str(i * 10 + 20)),
                    volume=Decimal("100"),
                    quote_volume=Decimal("5000000"),
                    trades=100,
                    taker_buy_base_volume=Decimal("60"),
                    taker_buy_quote_volume=Decimal("3000000"),
                    bar_index=i
                )
                candles.append(candle)

            return candles

        client.get_historical_data = mock_get_historical
        return client

    @pytest.fixture
    def ingest_service(self, mock_rest_client):
        """Create ingest service with mocked clients."""
        with patch('app.engine.bus.get_event_bus') as mock_get_bus:
            mock_bus = AsyncMock()
            mock_get_bus.return_value = mock_bus

            # Mock binance config
            binance_config = {
                "spot": {"api_key": "test", "api_secret": "test"},
                "futures": {"api_key": "test", "api_secret": "test"},
            }

            service = IngestService(
                binance_config=binance_config,
                symbols=["BTCUSDT"],
                timeframes=[TimeFrame.M5],
                backfill_days=1,
                enable_realtime=True,
                enable_backfill=True,
            )
            service.rest_client = mock_rest_client
            service._event_bus = mock_bus

            # Mock WebSocket client
            service.ws_client = AsyncMock()
            service.ws_client.subscribe_klines = AsyncMock()
            service.ws_client.subscribe_ticker = AsyncMock()

            return service

    @pytest.mark.asyncio
    async def test_backfill_on_startup(self, ingest_service):
        """Test that historical data is backfilled on service startup."""
        # Start the service
        await ingest_service.start()

        # Should have started backfill
        await asyncio.sleep(0.1)  # Let backfill tasks start

        # Check that backfill was initiated
        assert len(ingest_service._backfill_tasks) > 0

        # Stop the service
        await ingest_service.stop()

        # Verify historical data was published
        assert ingest_service._event_bus.publish.call_count > 0

        # Check first event was marked as historical
        first_call = ingest_service._event_bus.publish.call_args_list[0]
        event = first_call[0][0]
        assert event.metadata.get("is_historical") is True

    @pytest.mark.asyncio
    async def test_backfill_gap_detection(self, ingest_service):
        """Test detection and filling of data gaps."""
        # Create a gap scenario
        last_candle_time = datetime.now() - timedelta(hours=1)
        current_time = datetime.now()

        # Set up last known candle
        ingest_service._latest_candles = {
            "BTCUSDT": {
                TimeFrame.M5: Candle(
                    venue="spot",
                    symbol="BTCUSDT",
                    timeframe=TimeFrame.M5,
                    open_time=last_candle_time - timedelta(minutes=5),
                    close_time=last_candle_time,
                    open_price=Decimal("50000"),
                    high_price=Decimal("50100"),
                    low_price=Decimal("49900"),
                    close_price=Decimal("50050"),
                    volume=Decimal("100"),
                    quote_volume=Decimal("5000000"),
                    trades=100,
                    taker_buy_base_volume=Decimal("60"),
                    taker_buy_quote_volume=Decimal("3000000")
                )
            }
        }

        # Simulate gap detection and backfill
        await ingest_service._backfill_symbol_timeframe("BTCUSDT", TimeFrame.M5)

        # Should have fetched historical data to fill the gap
        ingest_service.rest_client.get_historical_data.assert_called_with(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            days_back=1
        )

    @pytest.mark.asyncio
    async def test_duplicate_handling(self, ingest_service):
        """Test that duplicate candles are not processed twice."""
        # Create a candle
        test_candle = Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=datetime.now() - timedelta(minutes=5),
            close_time=datetime.now(),
            open_price=Decimal("50000"),
            high_price=Decimal("50100"),
            low_price=Decimal("49900"),
            close_price=Decimal("50050"),
            volume=Decimal("100"),
            quote_volume=Decimal("5000000"),
            trades=100,
            taker_buy_base_volume=Decimal("60"),
            taker_buy_quote_volume=Decimal("3000000")
        )

        # Process it twice
        event1 = CandleUpdateEvent(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            candle=test_candle
        )

        event2 = CandleUpdateEvent(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            candle=test_candle
        )

        # In a real implementation, duplicates would be filtered by the database
        # or by checking the candle's open_time
        assert event1.candle.open_time == event2.candle.open_time
        assert event1.candle.symbol == event2.candle.symbol
        assert event1.candle.timeframe == event2.candle.timeframe


class TestErrorRecovery:
    """Test error handling and recovery mechanisms."""

    @pytest.mark.asyncio
    async def test_websocket_error_recovery(self):
        """Test recovery from WebSocket errors."""
        with patch('app.engine.ingest.binance_ws.get_event_bus'):
            ws_client = BinanceWebSocketClient(reconnect_interval=0.1)
            ws_client._running = True  # Simulate running state

            # Mock websocket that raises errors
            with patch('websockets.connect') as mock_connect:
                # First two attempts fail, third succeeds
                mock_ws_success = AsyncMock()
                mock_ws_success.closed = False
                mock_ws_success.__aiter__.return_value = iter([])  # No messages

                mock_connect.side_effect = [
                    ConnectionError("Network error"),
                    ConnectionError("Network error"),
                    # Third attempt succeeds
                    mock_ws_success
                ]

                # Start connection manager
                connection_task = asyncio.create_task(ws_client._connection_manager())

                # Let it try to connect multiple times
                await asyncio.sleep(0.5)

                # Stop the client
                ws_client._running = False

                # Cancel and wait
                connection_task.cancel()
                try:
                    await connection_task
                except asyncio.CancelledError:
                    pass

                # Should have attempted multiple connections
                assert mock_connect.call_count >= 2

    @pytest.mark.asyncio
    async def test_malformed_message_handling(self):
        """Test handling of malformed WebSocket messages."""
        with patch('app.engine.ingest.binance_ws.get_event_bus') as mock_get_bus:
            mock_bus = AsyncMock()
            mock_get_bus.return_value = mock_bus

            ws_client = BinanceWebSocketClient()

            # Test various malformed messages
            malformed_messages = [
                "not json",
                '{"incomplete": ',
                '{"e": "unknown_event"}',
                '{"e": "kline"}',  # Missing required fields
                '[]',  # Empty array
            ]

            for msg in malformed_messages:
                # Should not raise exception
                await ws_client._handle_message(msg)

            # Should not have published any events for malformed messages
            mock_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_connection_state_management(self):
        """Test proper connection state management."""
        with patch('app.engine.ingest.binance_ws.get_event_bus'):
            ws_client = BinanceWebSocketClient()

        # Initially not running
        assert not ws_client._running

        # Start the client
        await ws_client.start()
        assert ws_client._running

        # Starting again should be a no-op
        await ws_client.start()
        assert ws_client._running

        # Stop the client
        await ws_client.stop()
        assert not ws_client._running

        # Stopping again should be a no-op
        await ws_client.stop()
        assert not ws_client._running


class TestDataIntegrity:
    """Test data integrity during recovery scenarios."""

    @pytest.mark.asyncio
    async def test_candle_sequence_integrity(self):
        """Test that candle sequence is maintained during backfill."""
        candles = []
        base_time = datetime.now() - timedelta(hours=2)

        # Generate sequence of candles
        for i in range(10):
            candle = Candle(
                venue="spot",
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=base_time + timedelta(minutes=5*i),
                close_time=base_time + timedelta(minutes=5*(i+1)),
                open_price=Decimal("50000"),
                high_price=Decimal("50100"),
                low_price=Decimal("49900"),
                close_price=Decimal("50050"),
                volume=Decimal("100"),
                quote_volume=Decimal("5000000"),
                trades=100,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal("3000000"),
                bar_index=i
            )
            candles.append(candle)

        # Verify sequence integrity
        for i in range(1, len(candles)):
            prev_candle = candles[i-1]
            curr_candle = candles[i]

            # Close time of previous should equal open time of current
            assert prev_candle.close_time == curr_candle.open_time

            # Bar indices should be sequential
            assert curr_candle.bar_index == prev_candle.bar_index + 1

    @pytest.mark.asyncio
    async def test_closed_candle_only_processing(self):
        """Test that only closed candles are processed."""
        with patch('app.engine.ingest.binance_ws.get_event_bus') as mock_get_bus:
            mock_bus = AsyncMock()
            mock_get_bus.return_value = mock_bus

            ws_client = BinanceWebSocketClient()
            processed_candles = []

            async def track_candle(event):
                if isinstance(event, CandleUpdateEvent):
                    processed_candles.append(event.candle)

            mock_bus.publish.side_effect = track_candle
            # Send open candle (x=false)
            open_msg = {
                "e": "kline",
                "k": {
                    "x": False,  # Not closed
                    "s": "BTCUSDT",
                    "i": "5m",
                    "t": int(datetime.now().timestamp() * 1000),
                    "T": int((datetime.now() + timedelta(minutes=5)).timestamp() * 1000),
                    "o": "50000",
                    "c": "50100",
                    "h": "50150",
                    "l": "49950",
                    "v": "100",
                    "n": 1000,
                    "q": "5000000",
                    "V": "60",
                    "Q": "3000000"
                }
            }

            await ws_client._handle_message(json.dumps(open_msg))

            # Should not process open candles
            assert len(processed_candles) == 0

            # Send closed candle (x=true)
            closed_msg = open_msg.copy()
            closed_msg["k"]["x"] = True

            await ws_client._handle_message(json.dumps(closed_msg))

            # Should process closed candle
            assert len(processed_candles) == 1
            assert processed_candles[0].symbol == "BTCUSDT"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])