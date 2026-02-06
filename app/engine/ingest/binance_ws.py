"""
Binance WebSocket Client

Real-time data ingestion from Binance WebSocket streams.
Handles kline/candlestick data, ticker updates, and order book streams.
"""

import asyncio
from collections import deque
import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import websockets
from websockets import State as WebSocketState
from websockets.exceptions import ConnectionClosed

try:
    from websockets.exceptions import InvalidStatusCode  # type: ignore[attr-defined]
except ImportError:
    from websockets.exceptions import InvalidStatus as InvalidStatusCode

from ..bus import get_event_bus
from ..models import Candle, CandleUpdateEvent, TimeFrame
from ..resilience.backoff import BackoffConfig, ExponentialBackoff
from ..resilience.thread_safe_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from .bar_index import bar_index_from_open_time

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..bus import EventBus

logger = logging.getLogger(__name__)


def unwrap_combined_stream_message(data: Any) -> Any:
    """
    Unwrap combined stream message wrapper if present.

    Binance combined streams (via /stream?streams=...) wrap messages in:
    {"stream": "btcusdt@kline_5m", "data": {"e": "kline", ...}}

    This function extracts the inner 'data' dict when the wrapper is detected.
    For direct messages or non-dict inputs, returns the original unchanged.

    Args:
        data: Parsed JSON message (can be dict, list, or primitive)

    Returns:
        Inner 'data' dict if combined stream wrapper detected, else original
    """
    if not isinstance(data, dict):
        return data

    if "stream" not in data or "data" not in data:
        return data

    inner = data["data"]
    if not isinstance(inner, dict):
        return data

    return inner


def build_combined_stream_url(base_url: str, streams: list[str]) -> str:
    """
    Build Binance-compliant combined stream WebSocket URL.

    Converts base URL and stream list into the format required by Binance:
    wss://host:port/stream?streams=stream1/stream2/stream3

    Args:
        base_url: Base WebSocket URL (e.g., "wss://stream.binance.com:9443/ws/")
        streams: List of stream names (e.g., ["btcusdt@kline_1m", "ethusdt@ticker"])

    Returns:
        Combined stream URL in Binance format
    """
    parsed = urlparse(base_url)

    # Construct new URL with /stream endpoint
    scheme = parsed.scheme
    netloc = parsed.netloc
    streams_param = "/".join(streams)

    return f"{scheme}://{netloc}/stream?streams={streams_param}"


class BinanceWebSocketClient:
    """
    Binance WebSocket client for real-time market data.

    Supports:
    - Kline/Candlestick streams
    - Individual symbol ticker streams
    - All market tickers stream
    - Partial book depth streams
    - Trade streams

    Resilience features:
    - Exponential backoff with jitter
    - Circuit breaker integration
    - Max retry limit
    """

    def __init__(  # noqa: PLR0913
        self,
        base_url: str = "wss://stream.binance.com:9443/ws/",
        testnet: bool = False,
        reconnect_interval: int = 5,
        ping_interval: int = 20,
        ping_timeout: int = 10,
        *,
        max_reconnect_attempts: int = 50,
        backoff_config: BackoffConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        event_bus: "EventBus | None" = None,
        stale_threshold_seconds: int = 60,
        ping_keepalive_interval: int = 30,
    ) -> None:
        self.base_url = base_url
        if testnet:
            self.base_url = "wss://stream.testnet.binance.vision/ws/"

        self.reconnect_interval = reconnect_interval
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self._websocket: Any = None
        self._subscriptions: set[str] = set()
        self._symbols: set[str] = set()
        self._timeframes: set[TimeFrame] = set()
        self._running = False
        self._reconnect_task: asyncio.Task[Any] | None = None
        self._handlers: dict[str, Callable[..., Any]] = {}

        # Event bus - use provided or get global
        self._event_bus = event_bus if event_bus is not None else get_event_bus()

        self._last_message_at: datetime | None = None
        self._message_times: deque[datetime] = deque(maxlen=2000)
        self._stale_threshold_seconds = stale_threshold_seconds
        self._watchdog_interval_seconds = 30
        self._watchdog_task: asyncio.Task[Any] | None = None

        # Kline-specific tracking (separate from generic message tracking)
        # Enables detection of "tickers alive, klines dead" scenarios
        self._last_kline_at: datetime | None = None
        self._last_closed_kline_at: datetime | None = None

        # Ping keepalive to prevent NAT/firewall silent disconnects
        self._ping_keepalive_interval = ping_keepalive_interval
        self._ping_keepalive_task: asyncio.Task[Any] | None = None

        # Resilience: max retry limit
        self._max_reconnect_attempts = max_reconnect_attempts
        self._consecutive_failures = 0

        # Resilience: exponential backoff
        self._backoff = ExponentialBackoff(backoff_config or BackoffConfig())

        # Resilience: circuit breaker
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout_seconds=60,
            ),
        )

        # Stream message handlers
        self._handlers.update(
            {
                "kline": self._handle_kline_message,
                "24hrTicker": self._handle_ticker_message,
                "!ticker": self._handle_all_tickers_message,
                "depthUpdate": self._handle_depth_message,
                "trade": self._handle_trade_message,
            },
        )

        logger.info(
            f"BinanceWebSocketClient initialized with base_url: {self.base_url}",
        )

    def _is_websocket_open(self) -> bool:
        """Check if WebSocket connection is open.

        Uses websockets 13+ State API instead of deprecated .closed attribute.
        """
        return self._websocket is not None and self._websocket.state == WebSocketState.OPEN

    async def start(self) -> None:
        """Start the WebSocket client"""
        if self._running:
            logger.warning("WebSocket client is already running")
            return

        self._running = True
        self._reconnect_task = asyncio.create_task(self._connection_manager())
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        self._ping_keepalive_task = asyncio.create_task(self._ping_keepalive_loop())
        logger.info("WebSocket client started")

    async def stop(self) -> None:
        """Stop the WebSocket client"""
        if not self._running:
            return

        self._running = False

        if self._ping_keepalive_task:
            self._ping_keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ping_keepalive_task
            self._ping_keepalive_task = None

        if self._watchdog_task:
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
            self._watchdog_task = None

        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None

        if self._websocket:
            await self._websocket.close()

        logger.info("WebSocket client stopped")

    async def subscribe_klines(
        self,
        symbols: list[str],
        timeframes: list[TimeFrame],
    ) -> None:
        """
        Subscribe to kline/candlestick streams

        Args:
            symbols: list[Any] of trading symbols (e.g., ["BTCUSDT", "ETHUSDT"])
            timeframes: list[Any] of timeframes to subscribe to
        """
        streams = []
        for symbol in symbols:
            for timeframe in timeframes:
                stream = f"{symbol.lower()}@kline_{timeframe.value}"
                streams.append(stream)
                self._subscriptions.add(stream)

        self._symbols.update(symbols)
        self._timeframes.update(timeframes)

        if self._is_websocket_open():
            await self._subscribe_streams(streams)

        logger.info(
            f"Subscribed to klines for {len(symbols)} symbols and {len(timeframes)} timeframes",
        )

    async def subscribe_ticker(self, symbols: list[str]) -> None:
        """
        Subscribe to 24hr ticker streams

        Args:
            symbols: list[Any] of trading symbols
        """
        streams = [f"{symbol.lower()}@ticker" for symbol in symbols]
        self._subscriptions.update(streams)
        self._symbols.update(symbols)

        if self._is_websocket_open():
            await self._subscribe_streams(streams)

        logger.info(f"Subscribed to ticker for {len(symbols)} symbols")

    async def subscribe_all_tickers(self) -> None:
        """Subscribe to all market tickers stream"""
        stream = "!ticker@arr"
        self._subscriptions.add(stream)

        if self._is_websocket_open():
            await self._subscribe_streams([stream])

        logger.info("Subscribed to all market tickers")

    async def subscribe_depth(
        self,
        symbols: list[str],
        levels: int = 20,
        update_speed: str = "1000ms",
    ) -> None:
        """
        Subscribe to partial book depth streams

        Args:
            symbols: list[Any] of trading symbols
            levels: Number of price levels (5, 10, or 20)
            update_speed: Update speed (1000ms or 100ms)
        """
        streams = [f"{symbol.lower()}@depth{levels}@{update_speed}" for symbol in symbols]
        self._subscriptions.update(streams)
        self._symbols.update(symbols)

        if self._is_websocket_open():
            await self._subscribe_streams(streams)

        logger.info(f"Subscribed to depth for {len(symbols)} symbols")

    async def subscribe_trades(self, symbols: list[str]) -> None:
        """
        Subscribe to trade streams

        Args:
            symbols: list[Any] of trading symbols
        """
        streams = [f"{symbol.lower()}@trade" for symbol in symbols]
        self._subscriptions.update(streams)
        self._symbols.update(symbols)

        if self._is_websocket_open():
            await self._subscribe_streams(streams)

        logger.info(f"Subscribed to trades for {len(symbols)} symbols")

    async def unsubscribe_streams(self, streams: list[str]) -> None:
        """
        Unsubscribe from streams

        Args:
            streams: list[Any] of stream names to unsubscribe from
        """
        self._subscriptions.difference_update(streams)

        if self._is_websocket_open():
            await self._unsubscribe_streams(streams)

        logger.info(f"Unsubscribed from {len(streams)} streams")

    async def _connection_manager(self) -> None:
        """Manage WebSocket connection with automatic reconnection and resilience."""
        while self._running:
            # Check max retry limit
            if self._consecutive_failures >= self._max_reconnect_attempts:
                logger.critical(
                    f"Max reconnection attempts ({self._max_reconnect_attempts}) "
                    "exceeded. Stopping WebSocket client.",
                )
                self._running = False
                break

            # Check circuit breaker
            if not await self._circuit_breaker.should_allow_request():
                circuit_state = await self._circuit_breaker.get_state()
                logger.warning(
                    f"Circuit breaker is {circuit_state.value}, skipping connection attempt",
                )
                delay = self._backoff.next_delay()
                await asyncio.sleep(delay)
                continue

            try:
                await self._connect_and_listen()
                # If we reach here, connection was successful but closed gracefully
                await self._on_connection_success()
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                await self._on_connection_failure(e)

                if self._running:
                    delay = self._backoff.next_delay()
                    logger.info(
                        f"Reconnecting in {delay:.1f}s "
                        f"(attempt {self._consecutive_failures}/{self._max_reconnect_attempts})...",
                    )
                    await asyncio.sleep(delay)

    async def _on_connection_success(self) -> None:
        """Handle successful connection: reset backoff and circuit breaker."""
        self._consecutive_failures = 0
        self._backoff.reset()
        await self._circuit_breaker.record_success()
        logger.info("Connection successful, resilience counters reset")

    async def _on_connection_failure(self, error: Exception) -> None:
        """Handle connection failure: record to circuit breaker, increment counter."""
        self._consecutive_failures += 1
        await self._circuit_breaker.record_failure()
        logger.warning(
            "Connection failed (%d/%d): %s",
            self._consecutive_failures,
            self._max_reconnect_attempts,
            error,
        )

    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for messages"""
        try:
            # Build WebSocket URL using Binance combined stream format
            if self._subscriptions:
                url = build_combined_stream_url(
                    self.base_url,
                    sorted(self._subscriptions),
                )
            else:
                # Use a dummy stream for initial connection
                url = build_combined_stream_url(self.base_url, ["btcusdt@ticker"])

            logger.info(f"Connecting to WebSocket: {url[:100]}...")

            connector = get_ws_connector()
            async with connector(
                url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                max_size=2**20,  # 1MB max message size
                compression=None,  # Disable compression for lower latency
            ) as websocket:
                self._websocket = websocket
                logger.info("WebSocket connected successfully")

                # Mark connection as successful
                await self._on_connection_success()

                # Subscribe to streams if we have any
                if self._subscriptions:
                    await self._resubscribe_all()

                # Listen for messages
                msg_count = 0
                async for message in websocket:
                    msg_count += 1
                    self._mark_message_received(datetime.now(UTC))
                    if msg_count <= 3 or msg_count % 50 == 0:
                        logger.info(f"WS msg #{msg_count} received (len={len(message)})")
                    try:
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")

        except (ConnectionClosed, InvalidStatusCode) as e:
            logger.warning(f"WebSocket connection closed: {e}")
            raise
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            raise

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message: {e}")
            return

        # Handle array of ticker data (all market tickers)
        if isinstance(data, list):
            for item in data:
                try:
                    unwrapped = unwrap_combined_stream_message(item)
                    await self._route_message(unwrapped)
                except Exception:
                    logger.exception("Error processing list item")
        else:
            try:
                unwrapped = unwrap_combined_stream_message(data)
                await self._route_message(unwrapped)
            except Exception:
                logger.exception("Error processing message")

    async def _route_message(self, data: dict[str, Any]) -> None:
        """Route message to appropriate handler"""
        try:
            # Determine message type
            if "e" in data:
                event_type = data["e"]
                if event_type in self._handlers:
                    await self._handlers[event_type](data)
                else:
                    logger.debug(f"No handler for event type: {event_type}")
            else:
                logger.debug(f"Message without event type: {data}")

        except Exception as e:
            logger.error(f"Error routing message: {e}")

    async def _handle_kline_message(self, data: dict[str, Any]) -> None:
        """Handle kline/candlestick message"""
        try:
            kline_data = data["k"]
            symbol = kline_data.get("s", "?")
            timeframe = kline_data.get("i", "?")
            is_closed = kline_data.get("x", False)

            # Track ANY kline message (open or closed) for freshness detection
            now = datetime.now(UTC)
            self._last_kline_at = now

            # Only process closed candles (k.x == true)
            if not is_closed:
                return

            # Track closed klines specifically for gap-fill triggering
            self._last_closed_kline_at = now

            logger.info(f"Received CLOSED candle: {symbol} {timeframe}")

            # Parse candle data
            open_time = datetime.fromtimestamp(kline_data["t"] / 1000, tz=UTC)
            candle = Candle(
                venue="SPOT",
                symbol=kline_data["s"],
                timeframe=TimeFrame(kline_data["i"]),
                open_time=open_time,
                close_time=datetime.fromtimestamp(kline_data["T"] / 1000, tz=UTC),
                open_price=Decimal(kline_data["o"]),
                high_price=Decimal(kline_data["h"]),
                low_price=Decimal(kline_data["l"]),
                close_price=Decimal(kline_data["c"]),
                volume=Decimal(kline_data["v"]),
                quote_volume=Decimal(kline_data["q"]),
                trades=int(kline_data["n"]),
                taker_buy_base_volume=Decimal(kline_data["V"]),
                taker_buy_quote_volume=Decimal(kline_data["Q"]),
                bar_index=bar_index_from_open_time(open_time, TimeFrame(kline_data["i"])),
            )

            # Create and publish candle update event
            event = CandleUpdateEvent(
                timestamp=datetime.now(UTC),
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                candle=candle,
            )

            published = await self._event_bus.publish(event)

            logger.info(
                "Published candle event: %s %s (published=%s)",
                candle.symbol,
                candle.timeframe,
                published,
            )

        except Exception as e:
            logger.error(f"Error handling kline message: {e}")

    async def _handle_ticker_message(self, data: dict[str, Any]) -> None:
        """Handle 24hr ticker message"""
        try:
            # Process ticker data
            symbol = data["s"]
            price = Decimal(data["c"])
            change_percent = Decimal(data["P"])

            logger.debug(f"Ticker update: {symbol} = {price} ({change_percent}%)")

            # Could publish ticker event here if needed
            # For now, just log the data

        except Exception as e:
            logger.error(f"Error handling ticker message: {e}")

    async def _handle_all_tickers_message(self, data: dict[str, Any]) -> None:
        """Handle all market tickers message"""
        try:
            symbol = data["s"]
            price = Decimal(data["c"])
            volume = Decimal(data["v"])

            logger.debug(f"All tickers update: {symbol} = {price}, volume = {volume}")

        except Exception as e:
            logger.error(f"Error handling all tickers message: {e}")

    async def _handle_depth_message(self, data: dict[str, Any]) -> None:
        """Handle order book depth message"""
        try:
            symbol = data["s"]
            bids = data["b"]
            asks = data["a"]

            logger.debug(
                f"Depth update for {symbol}: {len(bids)} bids, {len(asks)} asks",
            )

        except Exception as e:
            logger.error(f"Error handling depth message: {e}")

    async def _handle_trade_message(self, data: dict[str, Any]) -> None:
        """Handle trade message"""
        try:
            symbol = data["s"]
            price = Decimal(data["p"])
            quantity = Decimal(data["q"])
            is_buyer_maker = data["m"]

            logger.debug(
                f"Trade: {symbol} {quantity} @ {price} (buyer_maker: {is_buyer_maker})",
            )

        except Exception as e:
            logger.error(f"Error handling trade message: {e}")

    async def _subscribe_streams(self, streams: list[str]) -> None:
        """Subscribe to additional streams"""
        if not streams:
            return

        subscribe_msg = {"method": "SUBSCRIBE", "params": streams, "id": 1}

        try:
            await self._websocket.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to {len(streams)} additional streams")
        except Exception as e:
            logger.error(f"Error subscribing to streams: {e}")

    async def _unsubscribe_streams(self, streams: list[str]) -> None:
        """Unsubscribe from streams"""
        if not streams:
            return

        unsubscribe_msg = {"method": "UNSUBSCRIBE", "params": streams, "id": 2}

        try:
            await self._websocket.send(json.dumps(unsubscribe_msg))
            logger.info(f"Unsubscribed from {len(streams)} streams")
        except Exception as e:
            logger.error(f"Error unsubscribing from streams: {e}")

    async def _resubscribe_all(self) -> None:
        """Resubscribe to all streams after reconnection"""
        if self._subscriptions:
            await self._subscribe_streams(list(self._subscriptions))

    def get_subscriptions(self) -> list[str]:
        """Get current subscriptions"""
        return list(self._subscriptions)

    def _mark_message_received(self, at: datetime) -> None:
        self._last_message_at = at
        self._message_times.append(at)

    def _last_message_ago_seconds(self, now: datetime) -> float | None:
        if self._last_message_at is None:
            return None
        return (now - self._last_message_at).total_seconds()

    def _is_stale(self, now: datetime) -> bool:
        ago = self._last_message_ago_seconds(now)
        if ago is None:
            return True
        return ago > self._stale_threshold_seconds

    def _last_kline_ago_seconds(self, now: datetime) -> float | None:
        """Seconds since last kline message (any, open or closed)."""
        if self._last_kline_at is None:
            return None
        return (now - self._last_kline_at).total_seconds()

    def _last_closed_kline_ago_seconds(self, now: datetime) -> float | None:
        """Seconds since last closed kline (k.x == true)."""
        if self._last_closed_kline_at is None:
            return None
        return (now - self._last_closed_kline_at).total_seconds()

    async def _watchdog_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._watchdog_interval_seconds)

            if not self._is_websocket_open():
                continue

            now = datetime.now(UTC)
            if self._is_stale(now):
                logger.warning(
                    "WebSocket stale: no messages for %ss; forcing reconnect",
                    self._last_message_ago_seconds(now),
                )
                if self._websocket is not None:
                    with contextlib.suppress(Exception):
                        await self._websocket.close()

    async def _ping_keepalive_loop(self) -> None:
        """Send periodic ping frames to keep the connection alive.

        NAT/firewalls may silently drop idle connections. Sending ping frames
        every 30 seconds prevents this and detects dead connections faster.
        """
        while self._running:
            await asyncio.sleep(self._ping_keepalive_interval)

            if not self._is_websocket_open():
                continue

            try:
                await self._websocket.ping()
                logger.debug("Sent keepalive ping")
            except Exception as e:
                logger.warning("Keepalive ping failed: %s; forcing reconnect", e)
                if self._websocket is not None:
                    with contextlib.suppress(Exception):
                        await self._websocket.close()

    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._is_websocket_open() and not self._is_stale(datetime.now(UTC))

    async def health_check(self) -> dict[str, Any]:
        """Get health status including resilience metrics."""
        circuit_state = await self._circuit_breaker.get_state()
        now = datetime.now(UTC)
        last_ago = self._last_message_ago_seconds(now)
        cutoff = now - timedelta(minutes=1)
        messages_per_minute = sum(1 for t in self._message_times if t >= cutoff)
        stale = self._is_stale(now) if self._is_websocket_open() else False
        return {
            "connected": self.is_connected(),
            "subscriptions": len(self._subscriptions),
            "symbols": len(self._symbols),
            "timeframes": len(self._timeframes),
            "running": self._running,
            "stale": stale,
            "last_message_ago_seconds": last_ago,
            "messages_per_minute": messages_per_minute,
            # Kline-specific freshness (for detecting "tickers alive, klines dead")
            "last_kline_ago_seconds": self._last_kline_ago_seconds(now),
            "last_closed_kline_ago_seconds": self._last_closed_kline_ago_seconds(now),
            # Resilience metrics
            "consecutive_failures": self._consecutive_failures,
            "circuit_state": circuit_state.value,
            "backoff_attempt": self._backoff.current_attempt,
            "max_reconnect_attempts": self._max_reconnect_attempts,
        }


def get_ws_connector() -> "Callable[..., Any]":
    """Return the WebSocket connector callable.

    Allows tests to inject a fake connector without importing external modules.
    """
    return websockets.connect
