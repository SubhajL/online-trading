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
import os
import socket
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import websockets
from websockets import State as WebSocketState
from websockets.exceptions import ConnectionClosed, InvalidStatus

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


def normalize_ws_base_url(base_url: str) -> str:
    """Normalize a Binance WS base URL to `/ws`.

    We intentionally use the `/ws` endpoint and manage subscriptions with
    `SUBSCRIBE` / `UNSUBSCRIBE` frames.

    This avoids mixed strategies (combined-stream URL + SUBSCRIBE frames) which
    can lead to "tickers alive, klines dead" when the server ignores the frames.
    """
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return base_url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}/ws"


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
        ws_connector: "Callable[..., Any] | None" = None,
        stale_threshold_seconds: int = 60,
        ping_keepalive_interval: int = 30,
        dispatch_queue_maxsize: int | None = None,
        dispatch_workers: int | None = None,
    ) -> None:
        self.base_url = normalize_ws_base_url(base_url)
        if testnet:
            self.base_url = normalize_ws_base_url("wss://stream.testnet.binance.vision/ws/")

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
        self._ws_connector = ws_connector

        self._last_message_at: datetime | None = None
        self._message_times: deque[datetime] = deque(maxlen=2000)
        self._stale_threshold_seconds = stale_threshold_seconds
        self._watchdog_interval_seconds = 30
        self._watchdog_task: asyncio.Task[Any] | None = None

        # Kline-specific tracking (separate from generic message tracking)
        # Enables detection of "tickers alive, klines dead" scenarios
        self._last_kline_at: datetime | None = None
        self._last_closed_kline_at: datetime | None = None

        # Subscription (SUBSCRIBE) response tracking for health/debugging.
        # Binance returns {"result": null, "id": 1} on success, or
        # {"error": {...}, "id": 1} on failure.
        self._last_subscribe_ok_at: datetime | None = None
        self._last_subscribe_error_at: datetime | None = None
        self._last_subscribe_error: str | None = None
        self._last_subscribe_response_id: int | None = None

        # Ping keepalive to prevent NAT/firewall silent disconnects
        self._ping_keepalive_interval = ping_keepalive_interval
        self._ping_keepalive_task: asyncio.Task[Any] | None = None

        if dispatch_queue_maxsize is None:
            dispatch_queue_maxsize = int(os.getenv("WS_DISPATCH_QUEUE_SIZE", "2000"))
        if dispatch_workers is None:
            dispatch_workers = int(os.getenv("WS_DISPATCH_WORKERS", "2"))
        if dispatch_queue_maxsize <= 0:
            dispatch_queue_maxsize = 2000
        if dispatch_workers <= 0:
            dispatch_workers = 1

        self._dispatch_queue_maxsize = dispatch_queue_maxsize
        self._dispatch_workers = dispatch_workers
        self._dispatch_queue: asyncio.Queue[dict[str, Any]] | None = None
        self._dispatch_tasks: list[asyncio.Task[None]] = []
        self._dispatch_dropped_messages_total: int = 0

        # Resilience: max retry limit
        self._max_reconnect_attempts = max_reconnect_attempts
        self._consecutive_failures = 0
        self._consecutive_dns_failures = 0

        self._last_connect_error_kind: str | None = None
        self._last_connect_error_at: datetime | None = None
        self._last_connect_error: str | None = None

        self._dns_probe_initial_seconds = float(
            os.getenv("WS_DNS_PROBE_INITIAL_SECONDS", "5"),
        )
        self._dns_probe_max_seconds = float(os.getenv("WS_DNS_PROBE_MAX_SECONDS", "30"))

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

        logger.info("BinanceWebSocketClient initialized")

    def _is_websocket_open(self) -> bool:
        """Check if WebSocket connection is open.

        Uses websockets 13+ State API instead of deprecated .closed attribute.
        """
        state = getattr(self._websocket, "state", None)
        return self._websocket is not None and state == WebSocketState.OPEN

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
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                kind = await self._on_connection_failure(e)

                if self._running:
                    if kind == "dns":
                        host, port = self._ws_host_port()
                        if host is not None and port is not None:
                            await self._wait_for_dns_recovery(host, port)
                            continue
                    delay = self._backoff.next_delay()
                    logger.info(
                        f"Reconnecting in {delay:.1f}s "
                        f"(attempt {self._consecutive_failures}/{self._max_reconnect_attempts})...",
                    )
                    await asyncio.sleep(delay)

    async def _on_connection_success(self) -> None:
        """Handle successful connection: reset backoff and circuit breaker."""
        self._consecutive_failures = 0
        self._consecutive_dns_failures = 0
        self._backoff.reset()
        await self._circuit_breaker.record_success()
        logger.info("Connection successful, resilience counters reset")

    def _classify_connect_error(self, error: BaseException) -> str:
        if isinstance(error, socket.gaierror):
            return "dns"
        if isinstance(error, OSError):
            if getattr(error, "errno", None) == -3:
                return "dns"
        msg = str(error).lower()
        if "temporary failure in name resolution" in msg or "name or service not known" in msg:
            return "dns"
        return "other"

    def _ws_host_port(self) -> tuple[str | None, int | None]:
        parsed = urlparse(self.base_url)
        host = parsed.hostname
        if host is None:
            return None, None
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "wss" else 80
        return host, port

    async def _wait_for_dns_recovery(self, host: str, port: int) -> None:
        delay = max(0.1, self._dns_probe_initial_seconds)
        max_delay = max(delay, self._dns_probe_max_seconds)
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                logger.info("DNS resolution recovered for %s:%s", host, port)
                return
            except Exception:
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    async def _on_connection_failure(self, error: Exception) -> str:
        """Handle connection failure: record to circuit breaker, increment counter."""
        kind = self._classify_connect_error(error)
        now = datetime.now(UTC)

        self._last_connect_error_kind = kind
        self._last_connect_error_at = now
        self._last_connect_error = str(error)[:500]

        if kind == "dns":
            self._consecutive_dns_failures += 1
        else:
            self._consecutive_failures += 1
            self._consecutive_dns_failures = 0
            await self._circuit_breaker.record_failure()

        logger.warning(
            "Connection failed (%d/%d): %s",
            self._consecutive_failures,
            self._max_reconnect_attempts,
            error,
        )
        return kind

    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for messages"""
        try:
            url = self.base_url

            logger.info(f"Connecting to WebSocket: {url[:100]}...")

            connector = self._ws_connector or get_ws_connector()
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
                self._dispatch_queue = asyncio.Queue(maxsize=self._dispatch_queue_maxsize)
                self._dispatch_tasks = [
                    asyncio.create_task(self._dispatch_worker(self._dispatch_queue))
                    for _ in range(self._dispatch_workers)
                ]
                try:
                    msg_count = 0
                    async for message in websocket:
                        msg_count += 1
                        self._mark_message_received(datetime.now(UTC))
                        if msg_count <= 3 or msg_count % 50 == 0:
                            logger.info(f"WS msg #{msg_count} received (len={len(message)})")
                        try:
                            await self._enqueue_message(message)
                        except Exception as e:
                            logger.error(f"Error handling message: {e}")
                finally:
                    # Ensure dispatch workers are always cleaned up, even if the WS loop raises.
                    for t in self._dispatch_tasks:
                        t.cancel()
                    await asyncio.gather(*self._dispatch_tasks, return_exceptions=True)
                    self._dispatch_tasks.clear()
                    self._dispatch_queue = None

        except (ConnectionClosed, InvalidStatus) as e:
            logger.warning(f"WebSocket connection closed: {e}")
            raise
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            raise

    async def _dispatch_worker(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        while True:
            data = await queue.get()
            try:
                await self._route_message(data)
            except Exception:
                logger.exception("Dispatch worker error routing message")
            finally:
                queue.task_done()

    async def _enqueue_message(self, message: str) -> None:
        """Parse/unpack a WS message and enqueue for background dispatch.

        This keeps the WS receive loop fast so ping/pong isn't starved by slow handlers.
        """
        if self._dispatch_queue is None:
            # Fallback (shouldn't happen): process inline.
            await self._handle_message(message)
            return

        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message: {e}")
            return

        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                unwrapped = unwrap_combined_stream_message(item)
                if isinstance(unwrapped, dict):
                    await self._try_enqueue_dispatch(unwrapped)
            return

        if isinstance(data, dict):
            unwrapped = unwrap_combined_stream_message(data)
            if isinstance(unwrapped, dict):
                await self._try_enqueue_dispatch(unwrapped)

    async def _try_enqueue_dispatch(self, data: dict[str, Any]) -> None:
        """Enqueue a parsed message; drop non-critical types under pressure."""
        if self._dispatch_queue is None:
            return

        try:
            self._dispatch_queue.put_nowait(data)
            return
        except asyncio.QueueFull:
            pass

        event_type = data.get("e")
        if event_type == "kline":
            # Closed klines are critical; under sustained pressure, force reconnect rather than drop.
            logger.warning("Dispatch queue full while receiving klines; forcing reconnect")
            if self._websocket is not None:
                with contextlib.suppress(Exception):
                    await self._websocket.close()
            return

        self._dispatch_dropped_messages_total += 1
        return

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
                if self._maybe_handle_subscribe_response(data):
                    return
                logger.debug(f"Message without event type: {data}")

        except Exception as e:
            logger.error(f"Error routing message: {e}")

    def _maybe_handle_subscribe_response(self, data: dict[str, Any]) -> bool:
        """Handle Binance SUBSCRIBE/UNSUBSCRIBE ack/error responses.

        Returns True if the message was recognized and handled.
        """
        if "id" not in data:
            return False
        if "result" not in data and "error" not in data:
            return False

        now = datetime.now(UTC)
        response_id = data.get("id")
        if isinstance(response_id, int):
            self._last_subscribe_response_id = response_id

        error = data.get("error")
        if error is not None:
            self._last_subscribe_error_at = now
            self._last_subscribe_error = json.dumps(error, default=str)[:500]
            logger.warning("WS subscription response error (id=%s): %s", response_id, error)
            return True

        # Success response is typically {"result": null, "id": 1}
        self._last_subscribe_ok_at = now
        self._last_subscribe_error_at = None
        self._last_subscribe_error = None
        logger.info("WS subscription response ok (id=%s)", response_id)
        return True

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

    def _ago_seconds(self, ts: datetime | None, now: datetime) -> float | None:
        if ts is None:
            return None
        return (now - ts).total_seconds()

    async def health_check(self) -> dict[str, Any]:
        """Get health status including resilience metrics."""
        circuit_state = await self._circuit_breaker.get_state()
        now = datetime.now(UTC)
        last_ago = self._last_message_ago_seconds(now)
        cutoff = now - timedelta(minutes=1)
        messages_per_minute = sum(1 for t in self._message_times if t >= cutoff)
        open_ = self._is_websocket_open()
        stale = self._is_stale(now) if open_ else False
        kline_subscriptions = sum(1 for s in self._subscriptions if "@kline_" in s)
        ticker_subscriptions = sum(
            1 for s in self._subscriptions if s.endswith("@ticker") or s == "!ticker@arr"
        )
        return {
            "connected": self.is_connected(),
            "open": open_,
            "subscriptions": len(self._subscriptions),
            "kline_subscriptions": kline_subscriptions,
            "ticker_subscriptions": ticker_subscriptions,
            "symbols": len(self._symbols),
            "timeframes": len(self._timeframes),
            "running": self._running,
            "stale": stale,
            "last_message_ago_seconds": last_ago,
            "messages_per_minute": messages_per_minute,
            "last_connect_error_kind": self._last_connect_error_kind,
            "last_connect_error": self._last_connect_error,
            "last_connect_error_ago_seconds": self._ago_seconds(
                self._last_connect_error_at,
                now,
            ),
            "dispatch_queue_size": self._dispatch_queue.qsize()
            if self._dispatch_queue is not None
            else 0,
            "dispatch_queue_max": self._dispatch_queue.maxsize
            if self._dispatch_queue is not None
            else self._dispatch_queue_maxsize,
            "dispatch_dropped_messages_total": self._dispatch_dropped_messages_total,
            # Kline-specific freshness (for detecting "tickers alive, klines dead")
            "last_kline_ago_seconds": self._last_kline_ago_seconds(now),
            "last_closed_kline_ago_seconds": self._last_closed_kline_ago_seconds(now),
            # Subscription response diagnostics (SUBSCRIBE ack/error)
            "last_subscribe_ok_ago_seconds": self._ago_seconds(self._last_subscribe_ok_at, now),
            "last_subscribe_error_ago_seconds": self._ago_seconds(
                self._last_subscribe_error_at,
                now,
            ),
            "last_subscribe_error": self._last_subscribe_error,
            "last_subscribe_response_id": self._last_subscribe_response_id,
            # Resilience metrics
            "consecutive_failures": self._consecutive_failures,
            "consecutive_dns_failures": self._consecutive_dns_failures,
            "circuit_state": circuit_state.value,
            "backoff_attempt": self._backoff.current_attempt,
            "max_reconnect_attempts": self._max_reconnect_attempts,
        }


def get_ws_connector() -> "Callable[..., Any]":
    """Return the WebSocket connector callable.

    Allows tests to inject a fake connector without importing external modules.
    """
    return websockets.connect
