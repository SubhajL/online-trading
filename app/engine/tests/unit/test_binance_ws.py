"""Unit tests for Binance WebSocket client message handling."""

from datetime import UTC, datetime, timedelta
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from websockets import State as WebSocketState

from app.engine.ingest.binance_ws import (
    BinanceWebSocketClient,
    unwrap_combined_stream_message,
)


@pytest.fixture
def client() -> BinanceWebSocketClient:
    return BinanceWebSocketClient(event_bus=MagicMock())


class TestUnwrapCombinedStreamMessage:
    """Tests for combined stream message unwrapping"""

    def test_extracts_inner_data_from_combined_stream(self) -> None:
        """Combined stream wrapper returns inner data dict"""
        combined_msg = {
            "stream": "btcusdt@kline_5m",
            "data": {"e": "kline", "k": {"s": "BTCUSDT", "i": "5m"}},
        }

        result = unwrap_combined_stream_message(combined_msg)

        assert result == {"e": "kline", "k": {"s": "BTCUSDT", "i": "5m"}}

    def test_preserves_direct_message_with_event_type(self) -> None:
        """Direct message (already has 'e') passes through unchanged"""
        direct_msg = {"e": "kline", "k": {"s": "BTCUSDT", "i": "5m"}}

        result = unwrap_combined_stream_message(direct_msg)

        assert result == direct_msg

    def test_ignores_combined_stream_with_non_dict_data(self) -> None:
        """{"stream":"x","data":"oops"} returns original (non-dict data)"""
        malformed_msg = {"stream": "btcusdt@kline_5m", "data": "oops"}

        result = unwrap_combined_stream_message(malformed_msg)

        assert result == malformed_msg

    @pytest.mark.parametrize(
        ("input_data", "expected"),
        [
            pytest.param([1, 2, 3], [1, 2, 3], id="list_passthrough"),
            pytest.param("string", "string", id="string_passthrough"),
            pytest.param(42, 42, id="int_passthrough"),
            pytest.param(None, None, id="none_passthrough"),
        ],
    )
    def test_handles_non_dict_input(self, input_data: Any, expected: Any) -> None:
        """Non-dict input returns unchanged"""
        result = unwrap_combined_stream_message(input_data)
        assert result == expected

    def test_handles_missing_data_key(self) -> None:
        """{"stream":"x"} (no 'data' key) returns original"""
        msg_without_data = {"stream": "btcusdt@kline_5m"}

        result = unwrap_combined_stream_message(msg_without_data)

        assert result == msg_without_data

    def test_handles_missing_stream_key(self) -> None:
        """{"data":{...}} (no 'stream' key) returns original"""
        msg_without_stream = {"data": {"e": "kline"}}

        result = unwrap_combined_stream_message(msg_without_stream)

        assert result == msg_without_stream

    def test_extracts_ticker_from_combined_stream(self) -> None:
        """Combined stream ticker message is unwrapped correctly"""
        combined_ticker = {
            "stream": "btcusdt@ticker",
            "data": {"e": "24hrTicker", "s": "BTCUSDT", "c": "50000.00"},
        }

        result = unwrap_combined_stream_message(combined_ticker)

        assert result == {"e": "24hrTicker", "s": "BTCUSDT", "c": "50000.00"}


class TestHandleMessageRouting:
    """Tests for _handle_message combined stream routing"""

    @pytest.fixture
    def mock_event_bus(self) -> MagicMock:
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        return bus

    @pytest.fixture
    def client(self, mock_event_bus: MagicMock) -> BinanceWebSocketClient:
        return BinanceWebSocketClient(event_bus=mock_event_bus)

    @pytest.mark.asyncio
    async def test_routes_combined_stream_kline_to_handler(
        self,
        client: BinanceWebSocketClient,
    ) -> None:
        """Combined stream kline message routes to _handle_kline_message"""
        combined_kline_msg = json.dumps(
            {
                "stream": "btcusdt@kline_5m",
                "data": {
                    "e": "kline",
                    "E": 1234567890123,
                    "s": "BTCUSDT",
                    "k": {
                        "t": 1234567800000,
                        "T": 1234568099999,
                        "s": "BTCUSDT",
                        "i": "5m",
                        "o": "50000.00",
                        "h": "50500.00",
                        "l": "49500.00",
                        "c": "50250.00",
                        "v": "100.5",
                        "q": "5025000.00",
                        "n": 1000,
                        "V": "60.3",
                        "Q": "3015000.00",
                        "x": True,
                    },
                },
            },
        )

        mock_handler = AsyncMock()
        client._handlers["kline"] = mock_handler

        await client._handle_message(combined_kline_msg)

        mock_handler.assert_awaited_once()
        call_args = mock_handler.call_args[0][0]
        # Verify unwrapped: no "stream" key, has expected structure
        assert "stream" not in call_args
        assert call_args["e"] == "kline"
        assert call_args["k"]["s"] == "BTCUSDT"
        assert call_args["k"]["i"] == "5m"


class TestWatchdog:
    @pytest.mark.asyncio
    async def test_ws_watchdog_forces_reconnect_when_stale(self) -> None:
        """Stale connection triggers forced reconnect (close)."""
        from app.engine.ingest import binance_ws

        client = BinanceWebSocketClient(event_bus=MagicMock())
        websocket = MagicMock()
        websocket.state = WebSocketState.OPEN
        websocket.close = AsyncMock(return_value=None)
        client._websocket = websocket

        now = datetime.now(UTC)
        client._running = True
        client._last_message_at = now - timedelta(seconds=client._stale_threshold_seconds + 1)

        async def fake_sleep(_seconds: float) -> None:
            client._running = False

        binance_ws_asyncio_sleep = binance_ws.asyncio.sleep
        binance_ws.asyncio.sleep = fake_sleep  # type: ignore[assignment]
        try:
            await client._watchdog_loop()
        finally:
            binance_ws.asyncio.sleep = binance_ws_asyncio_sleep

        websocket.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_combined_stream_ticker_to_handler(
        self,
        client: BinanceWebSocketClient,
    ) -> None:
        """Combined stream ticker message routes to _handle_ticker_message"""
        combined_ticker_msg = json.dumps(
            {
                "stream": "btcusdt@ticker",
                "data": {
                    "e": "24hrTicker",
                    "s": "BTCUSDT",
                    "c": "50000.00",
                    "P": "2.5",
                },
            },
        )

        mock_handler = AsyncMock()
        client._handlers["24hrTicker"] = mock_handler

        await client._handle_message(combined_ticker_msg)

        mock_handler.assert_awaited_once()
        call_args = mock_handler.call_args[0][0]
        # Verify unwrapped: no "stream" key, has expected structure
        assert "stream" not in call_args
        assert call_args["e"] == "24hrTicker"
        assert call_args["s"] == "BTCUSDT"
        assert call_args["c"] == "50000.00"

    @pytest.mark.asyncio
    async def test_routes_direct_kline_message(
        self,
        client: BinanceWebSocketClient,
    ) -> None:
        """Direct kline message (no wrapper) still routes correctly"""
        direct_kline_msg = json.dumps(
            {
                "e": "kline",
                "E": 1234567890123,
                "s": "BTCUSDT",
                "k": {
                    "t": 1234567800000,
                    "T": 1234568099999,
                    "s": "BTCUSDT",
                    "i": "5m",
                    "o": "50000.00",
                    "h": "50500.00",
                    "l": "49500.00",
                    "c": "50250.00",
                    "v": "100.5",
                    "q": "5025000.00",
                    "n": 1000,
                    "V": "60.3",
                    "Q": "3015000.00",
                    "x": False,
                },
            },
        )

        mock_handler = AsyncMock()
        client._handlers["kline"] = mock_handler

        await client._handle_message(direct_kline_msg)

        mock_handler.assert_awaited_once()
        call_args = mock_handler.call_args[0][0]
        assert call_args["e"] == "kline"
        assert call_args["k"]["s"] == "BTCUSDT"


class TestWebSocketHealth:
    @pytest.mark.asyncio
    async def test_health_check_reports_stale_when_no_messages_recently(self) -> None:
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)

        client = BinanceWebSocketClient(event_bus=bus)
        client._running = True
        client._websocket = MagicMock(state=WebSocketState.OPEN)
        client._last_message_at = datetime.now(UTC) - timedelta(seconds=600)

        health = await client.health_check()

        assert health["stale"] is True
        assert health["connected"] is False
        assert health["last_message_ago_seconds"] >= 600


class TestStaleThresholdConfiguration:
    """Tests for configurable stale threshold."""

    def test_default_stale_threshold_is_60_seconds(self) -> None:
        """Default stale threshold should be 60 seconds for faster detection."""
        client = BinanceWebSocketClient(event_bus=MagicMock())
        assert client._stale_threshold_seconds == 60

    def test_stale_threshold_can_be_configured(self) -> None:
        """Stale threshold can be configured via constructor."""
        client = BinanceWebSocketClient(
            event_bus=MagicMock(),
            stale_threshold_seconds=120,
        )
        assert client._stale_threshold_seconds == 120

    def test_connection_marked_stale_after_threshold(self) -> None:
        """Connection is marked stale after threshold seconds without messages."""
        client = BinanceWebSocketClient(
            event_bus=MagicMock(),
            stale_threshold_seconds=30,
        )
        now = datetime.now(UTC)
        client._last_message_at = now - timedelta(seconds=31)

        assert client._is_stale(now) is True

    def test_connection_not_stale_before_threshold(self) -> None:
        """Connection is not stale before threshold seconds."""
        client = BinanceWebSocketClient(
            event_bus=MagicMock(),
            stale_threshold_seconds=30,
        )
        now = datetime.now(UTC)
        client._last_message_at = now - timedelta(seconds=29)

        assert client._is_stale(now) is False


class TestPingKeepalive:
    """Tests for WebSocket ping keepalive functionality."""

    @pytest.mark.asyncio
    async def test_ping_loop_sends_ping_when_connected(self) -> None:
        """Ping loop sends ping frame when WebSocket is connected."""
        from app.engine.ingest import binance_ws

        client = BinanceWebSocketClient(
            event_bus=MagicMock(),
            ping_keepalive_interval=30,
        )
        websocket = MagicMock()
        websocket.state = WebSocketState.OPEN
        websocket.ping = AsyncMock(return_value=None)
        client._websocket = websocket
        client._running = True

        ping_count = 0
        original_sleep = binance_ws.asyncio.sleep

        async def fake_sleep(_seconds: float) -> None:
            nonlocal ping_count
            ping_count += 1
            if ping_count >= 2:
                client._running = False

        binance_ws.asyncio.sleep = fake_sleep  # type: ignore[assignment]
        try:
            await client._ping_keepalive_loop()
        finally:
            binance_ws.asyncio.sleep = original_sleep

        assert websocket.ping.await_count >= 1

    @pytest.mark.asyncio
    async def test_ping_loop_skips_when_disconnected(self) -> None:
        """Ping loop skips sending when WebSocket is not connected."""
        from app.engine.ingest import binance_ws

        client = BinanceWebSocketClient(
            event_bus=MagicMock(),
            ping_keepalive_interval=30,
        )
        websocket = MagicMock()
        websocket.state = WebSocketState.CLOSED
        websocket.ping = AsyncMock(return_value=None)
        client._websocket = websocket
        client._running = True

        loop_count = 0
        original_sleep = binance_ws.asyncio.sleep

        async def fake_sleep(_seconds: float) -> None:
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                client._running = False

        binance_ws.asyncio.sleep = fake_sleep  # type: ignore[assignment]
        try:
            await client._ping_keepalive_loop()
        finally:
            binance_ws.asyncio.sleep = original_sleep

        websocket.ping.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ping_loop_handles_exception_gracefully(self) -> None:
        """Ping loop continues after ping exception (connection may be dead)."""
        from app.engine.ingest import binance_ws

        client = BinanceWebSocketClient(
            event_bus=MagicMock(),
            ping_keepalive_interval=30,
        )
        websocket = MagicMock()
        websocket.state = WebSocketState.OPEN
        websocket.ping = AsyncMock(side_effect=Exception("Connection lost"))
        websocket.close = AsyncMock(return_value=None)
        client._websocket = websocket
        client._running = True

        loop_count = 0
        original_sleep = binance_ws.asyncio.sleep

        async def fake_sleep(_seconds: float) -> None:
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 2:
                client._running = False

        binance_ws.asyncio.sleep = fake_sleep  # type: ignore[assignment]
        try:
            await client._ping_keepalive_loop()
        finally:
            binance_ws.asyncio.sleep = original_sleep

        # Should have attempted ping and closed connection on failure
        websocket.ping.assert_awaited()
        websocket.close.assert_awaited()

    def test_default_ping_keepalive_interval_is_30_seconds(self) -> None:
        """Default ping keepalive interval is 30 seconds."""
        client = BinanceWebSocketClient(event_bus=MagicMock())
        assert client._ping_keepalive_interval == 30


class TestKlineSpecificTracking:
    """Tests for kline-specific message freshness tracking.

    The WS client tracks ALL messages via _mark_message_received(), but this
    doesn't distinguish klines from tickers. These tests verify that kline
    messages are tracked separately so LiveRestFallbackService can detect
    "tickers alive, klines dead" scenarios.
    """

    @pytest.mark.asyncio
    async def test_kline_message_updates_last_kline_at(self) -> None:
        """Any kline message (open or closed) updates _last_kline_at."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)

        assert client._last_kline_at is None

        # Open kline (k.x = False)
        open_kline_data = {
            "e": "kline",
            "k": {
                "t": 1234567800000,
                "T": 1234568099999,
                "s": "BTCUSDT",
                "i": "5m",
                "o": "50000.00",
                "h": "50500.00",
                "l": "49500.00",
                "c": "50250.00",
                "v": "100.5",
                "q": "5025000.00",
                "n": 1000,
                "V": "60.3",
                "Q": "3015000.00",
                "x": False,
            },
        }

        await client._handle_kline_message(open_kline_data)

        assert client._last_kline_at is not None

    @pytest.mark.asyncio
    async def test_closed_kline_updates_last_closed_kline_at(self) -> None:
        """Closed kline (k.x=true) updates _last_closed_kline_at."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)

        assert client._last_closed_kline_at is None

        # Closed kline (k.x = True)
        closed_kline_data = {
            "e": "kline",
            "k": {
                "t": 1234567800000,
                "T": 1234568099999,
                "s": "BTCUSDT",
                "i": "5m",
                "o": "50000.00",
                "h": "50500.00",
                "l": "49500.00",
                "c": "50250.00",
                "v": "100.5",
                "q": "5025000.00",
                "n": 1000,
                "V": "60.3",
                "Q": "3015000.00",
                "x": True,
            },
        }

        await client._handle_kline_message(closed_kline_data)

        assert client._last_closed_kline_at is not None

    @pytest.mark.asyncio
    async def test_non_closed_kline_does_not_update_closed_timestamp(self) -> None:
        """Open kline doesn't update _last_closed_kline_at."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)

        # Open kline (k.x = False)
        open_kline_data = {
            "e": "kline",
            "k": {
                "t": 1234567800000,
                "T": 1234568099999,
                "s": "BTCUSDT",
                "i": "5m",
                "o": "50000.00",
                "h": "50500.00",
                "l": "49500.00",
                "c": "50250.00",
                "v": "100.5",
                "q": "5025000.00",
                "n": 1000,
                "V": "60.3",
                "Q": "3015000.00",
                "x": False,
            },
        }

        await client._handle_kline_message(open_kline_data)

        assert client._last_kline_at is not None
        assert client._last_closed_kline_at is None

    @pytest.mark.asyncio
    async def test_ticker_message_does_not_update_kline_timestamps(self) -> None:
        """Ticker messages don't affect kline timestamps."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)

        # Process ticker message
        ticker_data = {
            "e": "24hrTicker",
            "s": "BTCUSDT",
            "c": "50000.00",
            "P": "2.5",
        }

        await client._handle_ticker_message(ticker_data)

        assert client._last_kline_at is None
        assert client._last_closed_kline_at is None

    @pytest.mark.asyncio
    async def test_health_check_includes_kline_ago_fields(self) -> None:
        """health_check() returns both kline age fields."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)
        client._running = True
        client._websocket = MagicMock(state=WebSocketState.OPEN)

        # Set kline timestamps to known values
        now = datetime.now(UTC)
        client._last_kline_at = now - timedelta(seconds=30)
        client._last_closed_kline_at = now - timedelta(seconds=120)
        client._last_message_at = now - timedelta(seconds=5)

        health = await client.health_check()

        assert "last_kline_ago_seconds" in health
        assert "last_closed_kline_ago_seconds" in health
        assert health["last_kline_ago_seconds"] >= 30
        assert health["last_closed_kline_ago_seconds"] >= 120

    @pytest.mark.asyncio
    async def test_health_check_kline_ago_none_when_no_klines(self) -> None:
        """Returns None for kline ages when no klines received."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)
        client._running = True
        client._websocket = MagicMock(state=WebSocketState.OPEN)
        client._last_message_at = datetime.now(UTC)

        health = await client.health_check()

        assert health["last_kline_ago_seconds"] is None
        assert health["last_closed_kline_ago_seconds"] is None


class TestSubscribeResponses:
    @pytest.mark.asyncio
    async def test_subscribe_ack_updates_health(self) -> None:
        """SUBSCRIBE ack frames are tracked for health/debugging."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)
        client._running = True
        client._websocket = MagicMock(state=WebSocketState.OPEN)
        client._last_message_at = datetime.now(UTC)

        # Binance SUBSCRIBE success response
        await client._handle_message(json.dumps({"result": None, "id": 1}))

        health = await client.health_check()

        assert health["last_subscribe_ok_ago_seconds"] is not None
        assert health["last_subscribe_error_ago_seconds"] is None
        assert health["last_subscribe_error"] is None
        assert health["last_subscribe_response_id"] == 1

    @pytest.mark.asyncio
    async def test_subscribe_error_updates_health(self) -> None:
        """SUBSCRIBE error frames are tracked for health/debugging."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)
        client._running = True
        client._websocket = MagicMock(state=WebSocketState.OPEN)
        client._last_message_at = datetime.now(UTC)

        await client._handle_message(
            json.dumps(
                {
                    "error": {"code": 123, "msg": "bad stream"},
                    "id": 1,
                },
            ),
        )

        health = await client.health_check()

        assert health["last_subscribe_ok_ago_seconds"] is None
        assert health["last_subscribe_error_ago_seconds"] is not None
        assert health["last_subscribe_error"] is not None
        assert health["last_subscribe_response_id"] == 1

    @pytest.mark.asyncio
    async def test_health_check_includes_subscription_breakdown(self) -> None:
        """health_check() includes kline/ticker subscription counts."""
        bus = MagicMock()
        bus.publish = AsyncMock(return_value=True)
        client = BinanceWebSocketClient(event_bus=bus)
        client._running = True
        client._websocket = MagicMock(state=WebSocketState.OPEN)
        client._last_message_at = datetime.now(UTC)

        client._subscriptions.update(
            {
                "btcusdt@ticker",
                "ethusdt@kline_5m",
                "!ticker@arr",
            },
        )

        health = await client.health_check()

        assert health["open"] is True
        assert health["kline_subscriptions"] == 1
        assert health["ticker_subscriptions"] == 2
