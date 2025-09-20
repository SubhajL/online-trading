"""
Binance Spot WebSocket and REST ingester.

Subscribes to kline streams for multiple symbols and timeframes,
emits only closed candles, handles reconnection with backfill.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from decimal import Decimal
import websockets
from websockets.exceptions import ConnectionClosed
import aiohttp

from ..models import Candle, kline_to_candle, rest_kline_to_candle, TimeFrame
from ..adapters.db import TimescaleDBAdapter
from ..bus import EventBus, publish_event


logger = logging.getLogger(__name__)


class BinanceSpotIngester:
    """
    Binance Spot market data ingester.

    Features:
    - WebSocket streaming for real-time kline data
    - REST API backfill on reconnection
    - Deduplication based on (venue, symbol, timeframe, open_time)
    - Exponential backoff for rate limiting
    - Time sync error handling
    """

    def __init__(
        self,
        db_adapter: TimescaleDBAdapter,
        event_bus: EventBus,
        symbols: List[str],
        timeframes: List[str],
        ws_base_url: str = "wss://stream.binance.com:9443",
        rest_base_url: str = "https://api.binance.com",
        max_reconnect_attempts: int = 5,
        reconnect_delay_ms: int = 5000
    ):
        self.db_adapter = db_adapter
        self.event_bus = event_bus
        self.symbols = symbols
        self.timeframes = timeframes
        self.venue = "spot"

        self.ws_base_url = ws_base_url
        self.rest_base_url = rest_base_url
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay_ms = reconnect_delay_ms

        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._last_candle_times: Dict[str, datetime] = {}
        self._reconnect_count = 0

    async def start(self) -> None:
        """Start the ingester with automatic reconnection."""
        self._running = True

        while self._running and self._reconnect_count < self.max_reconnect_attempts:
            try:
                await self._connect_and_subscribe()
                await self._message_loop()
            except ConnectionClosed:
                logger.warning(f"WebSocket connection closed, reconnecting in {self.reconnect_delay_ms}ms...")
                await asyncio.sleep(self.reconnect_delay_ms / 1000)
                self._reconnect_count += 1
                await self._on_reconnect()
            except Exception as e:
                logger.error(f"Unexpected error in WebSocket loop: {e}")
                await asyncio.sleep(self.reconnect_delay_ms / 1000)
                self._reconnect_count += 1

    async def stop(self) -> None:
        """Stop the ingester."""
        self._running = False
        if self._websocket:
            await self._websocket.close()

    async def _connect_and_subscribe(self) -> None:
        """Connect to WebSocket and subscribe to kline streams."""
        # Build stream names for combined subscription
        streams = []
        for symbol in self.symbols:
            for tf in self.timeframes:
                streams.append(f"{symbol.lower()}@kline_{tf}")

        # Combined stream URL
        url = f"{self.ws_base_url}/stream?streams={'/'.join(streams)}"

        logger.info(f"Connecting to Binance Spot WebSocket: {url}")
        self._websocket = await websockets.connect(url)
        self._reconnect_count = 0
        logger.info(f"Connected and subscribed to {len(streams)} streams")

    async def _message_loop(self) -> None:
        """Process incoming WebSocket messages."""
        async for message in self._websocket:
            try:
                data = json.loads(message)

                # Combined stream wraps data in 'data' field
                if "data" in data:
                    await self._process_stream_data(data["data"])
                else:
                    await self._process_stream_data(data)

            except json.JSONDecodeError:
                logger.error(f"Failed to decode message: {message}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def _process_stream_data(self, data: Dict) -> None:
        """Process stream data based on event type."""
        event_type = data.get("e")

        if event_type == "kline":
            await self._on_kline_message(data)

    async def _on_kline_message(self, data: Dict) -> None:
        """
        Process kline message, emit only when k.x == true (closed).

        Args:
            data: Kline event data from WebSocket
        """
        kline_data = data.get("k", {})

        # Only process closed candles
        if not kline_data.get("x", False):
            return

        # Convert to Candle
        candle = kline_to_candle(kline_data, self.venue)

        # Track last candle time for backfill
        key = f"{candle.symbol}:{candle.timeframe.value}"
        self._last_candle_times[key] = candle.close_time

        # Deduplicate - check if candle already exists
        if await self._deduplicate_candle(candle):
            logger.debug(f"Skipping duplicate candle: {candle.symbol} {candle.timeframe.value} {candle.open_time}")
            return

        # Persist to database
        try:
            await self.db_adapter.insert_candle(candle)
        except Exception as e:
            logger.error(f"Failed to insert candle: {e}")
            return

        # Publish to event bus
        await self._publish_candle(candle)

        logger.info(f"CLOSED candle: {candle.symbol} {candle.timeframe.value} "
                   f"O:{candle.open_price} H:{candle.high_price} L:{candle.low_price} C:{candle.close_price} "
                   f"V:{candle.volume}")

    async def _deduplicate_candle(self, candle: Candle) -> bool:
        """
        Check if candle already exists in database.

        Args:
            candle: The candle to check

        Returns:
            True if candle exists (is duplicate), False otherwise
        """
        existing = await self.db_adapter.get_candles(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            start_time=candle.open_time,
            end_time=candle.open_time,
            limit=1
        )

        return len(existing) > 0

    async def _publish_candle(self, candle: Candle) -> None:
        """Publish candle to event bus."""
        await publish_event("candles.v1", {
            "venue": self.venue,
            "symbol": candle.symbol,
            "timeframe": candle.timeframe.value,
            "timestamp": candle.close_time,
            "open_time": candle.open_time,
            "close_time": candle.close_time,
            "open": str(candle.open_price),
            "high": str(candle.high_price),
            "low": str(candle.low_price),
            "close": str(candle.close_price),
            "volume": str(candle.volume),
            "quote_volume": str(candle.quote_volume),
            "trades": candle.trades
        })

    async def _on_reconnect(self) -> None:
        """Handle reconnection - trigger REST backfill for missing data."""
        logger.info("Starting backfill after reconnection...")

        tasks = []
        for symbol in self.symbols:
            for tf in self.timeframes:
                # Get last candle time
                key = f"{symbol}:{tf}"
                last_time = self._last_candle_times.get(key)

                if not last_time:
                    # Get latest from DB if we don't have it in memory
                    latest_candle = await self.db_adapter.get_latest_candle(
                        symbol=symbol,
                        timeframe=TimeFrame(tf)
                    )
                    if latest_candle:
                        last_time = latest_candle.close_time
                    else:
                        # Default to 24 hours ago if no data
                        last_time = datetime.utcnow() - timedelta(hours=24)

                # Create backfill task
                task = self._backfill_missing_candles(symbol, tf, last_time)
                tasks.append(task)

        # Run all backfill tasks concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Backfill completed")

    async def _backfill_missing_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        retry_count: int = 0
    ) -> None:
        """
        Backfill missing candles via REST API.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe string
            start_time: Start time for backfill
            retry_count: Current retry attempt
        """
        # Convert timeframe to milliseconds
        interval_map = {
            "1m": 60000, "3m": 180000, "5m": 300000, "15m": 900000,
            "30m": 1800000, "1h": 3600000, "2h": 7200000, "4h": 14400000,
            "6h": 21600000, "8h": 28800000, "12h": 43200000, "1d": 86400000
        }
        interval_ms = interval_map.get(timeframe, 300000)  # Default to 5m

        # Calculate start and end times
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(datetime.utcnow().timestamp() * 1000)

        # Binance limit is 1000 candles per request
        max_candles = 1000

        async with aiohttp.ClientSession() as session:
            while start_ts < end_ts:
                # Calculate limit for this batch
                candles_needed = (end_ts - start_ts) // interval_ms
                limit = min(max_candles, candles_needed)

                if limit <= 0:
                    break

                # Build request URL
                url = (f"{self.rest_base_url}/api/v3/klines?"
                      f"symbol={symbol}&interval={timeframe}"
                      f"&startTime={start_ts}&limit={limit}")

                try:
                    async with session.get(url) as response:
                        if response.status == 429:
                            # Rate limited - exponential backoff
                            retry_after = int(response.headers.get("Retry-After", "60"))
                            delay = min(retry_after * (2 ** retry_count), 300)  # Max 5 minutes
                            logger.warning(f"Rate limited, retrying after {delay}s")
                            await asyncio.sleep(delay)

                            if retry_count < 3:
                                return await self._backfill_missing_candles(
                                    symbol, timeframe, start_time, retry_count + 1
                                )
                            else:
                                logger.error(f"Max retries exceeded for {symbol} {timeframe}")
                                return

                        elif response.status == 400:
                            # Check for time sync error
                            data = await response.json()
                            if data.get("code") == -1021:
                                await self._handle_time_sync_error(data.get("msg", ""))
                                # Retry with adjusted parameters
                                return await self._backfill_missing_candles(
                                    symbol, timeframe, start_time, retry_count
                                )

                        response.raise_for_status()

                        klines = await response.json()

                        if not klines:
                            break

                        # Process klines
                        for kline in klines:
                            candle = rest_kline_to_candle(kline, symbol, timeframe, self.venue)

                            # Deduplicate
                            if not await self._deduplicate_candle(candle):
                                await self.db_adapter.insert_candle(candle)
                                await self._publish_candle(candle)

                        # Update start time for next batch
                        last_kline = klines[-1]
                        start_ts = last_kline[6] + 1  # Close time + 1ms

                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.1)

                except aiohttp.ClientError as e:
                    logger.error(f"HTTP error during backfill: {e}")
                    return
                except Exception as e:
                    logger.error(f"Error during backfill: {e}")
                    return

    async def _handle_time_sync_error(self, error_msg: str) -> None:
        """
        Handle Binance -1021 time sync errors.

        Logs guidance for fixing time sync issues. In production,
        could adjust recvWindow parameter dynamically.

        Args:
            error_msg: The error message from Binance
        """
        logger.error(f"Time sync error: {error_msg}")
        logger.info("Time sync error (-1021) guidance:")
        logger.info("1. Check system time is synchronized (use NTP)")
        logger.info("2. On Linux/Mac: sudo ntpdate -s time.nist.gov")
        logger.info("3. Consider increasing recvWindow parameter (default 5000ms)")
        logger.info("4. Ensure network latency is stable")

        # In production, could implement dynamic recvWindow adjustment
        # For now, just log the guidance