"""
Binance WebSocket Client

Real-time data ingestion from Binance WebSocket streams.
Handles kline/candlestick data, ticker updates, and order book streams.
"""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urljoin

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from ..types import Candle, CandleUpdateEvent, TimeFrame
from ..bus import get_event_bus


logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """
    Binance WebSocket client for real-time market data.

    Supports:
    - Kline/Candlestick streams
    - Individual symbol ticker streams
    - All market tickers stream
    - Partial book depth streams
    - Trade streams
    """

    def __init__(
        self,
        base_url: str = "wss://stream.binance.com:9443/ws/",
        testnet: bool = False,
        reconnect_interval: int = 5,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        self.base_url = base_url
        if testnet:
            self.base_url = "wss://testnet.binance.vision/ws/"

        self.reconnect_interval = reconnect_interval
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self._websocket: Optional[websockets.WebSocketServerProtocol] = None
        self._subscriptions: Set[str] = set()
        self._symbols: Set[str] = set()
        self._timeframes: Set[TimeFrame] = set()
        self._running = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._handlers: Dict[str, Callable] = {}
        self._event_bus = get_event_bus()

        # Stream message handlers
        self._handlers.update({
            "kline": self._handle_kline_message,
            "24hrTicker": self._handle_ticker_message,
            "!ticker": self._handle_all_tickers_message,
            "depthUpdate": self._handle_depth_message,
            "trade": self._handle_trade_message,
        })

        logger.info(f"BinanceWebSocketClient initialized with base_url: {self.base_url}")

    async def start(self):
        """Start the WebSocket client"""
        if self._running:
            logger.warning("WebSocket client is already running")
            return

        self._running = True
        self._reconnect_task = asyncio.create_task(self._connection_manager())
        logger.info("WebSocket client started")

    async def stop(self):
        """Stop the WebSocket client"""
        if not self._running:
            return

        self._running = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._websocket:
            await self._websocket.close()

        logger.info("WebSocket client stopped")

    async def subscribe_klines(self, symbols: List[str], timeframes: List[TimeFrame]):
        """
        Subscribe to kline/candlestick streams

        Args:
            symbols: List of trading symbols (e.g., ["BTCUSDT", "ETHUSDT"])
            timeframes: List of timeframes to subscribe to
        """
        streams = []
        for symbol in symbols:
            for timeframe in timeframes:
                stream = f"{symbol.lower()}@kline_{timeframe.value}"
                streams.append(stream)
                self._subscriptions.add(stream)

        self._symbols.update(symbols)
        self._timeframes.update(timeframes)

        if self._websocket and not self._websocket.closed:
            await self._subscribe_streams(streams)

        logger.info(f"Subscribed to klines for {len(symbols)} symbols and {len(timeframes)} timeframes")

    async def subscribe_ticker(self, symbols: List[str]):
        """
        Subscribe to 24hr ticker streams

        Args:
            symbols: List of trading symbols
        """
        streams = [f"{symbol.lower()}@ticker" for symbol in symbols]
        self._subscriptions.update(streams)
        self._symbols.update(symbols)

        if self._websocket and not self._websocket.closed:
            await self._subscribe_streams(streams)

        logger.info(f"Subscribed to ticker for {len(symbols)} symbols")

    async def subscribe_all_tickers(self):
        """Subscribe to all market tickers stream"""
        stream = "!ticker@arr"
        self._subscriptions.add(stream)

        if self._websocket and not self._websocket.closed:
            await self._subscribe_streams([stream])

        logger.info("Subscribed to all market tickers")

    async def subscribe_depth(self, symbols: List[str], levels: int = 20, update_speed: str = "1000ms"):
        """
        Subscribe to partial book depth streams

        Args:
            symbols: List of trading symbols
            levels: Number of price levels (5, 10, or 20)
            update_speed: Update speed (1000ms or 100ms)
        """
        streams = [f"{symbol.lower()}@depth{levels}@{update_speed}" for symbol in symbols]
        self._subscriptions.update(streams)
        self._symbols.update(symbols)

        if self._websocket and not self._websocket.closed:
            await self._subscribe_streams(streams)

        logger.info(f"Subscribed to depth for {len(symbols)} symbols")

    async def subscribe_trades(self, symbols: List[str]):
        """
        Subscribe to trade streams

        Args:
            symbols: List of trading symbols
        """
        streams = [f"{symbol.lower()}@trade" for symbol in symbols]
        self._subscriptions.update(streams)
        self._symbols.update(symbols)

        if self._websocket and not self._websocket.closed:
            await self._subscribe_streams(streams)

        logger.info(f"Subscribed to trades for {len(symbols)} symbols")

    async def unsubscribe_streams(self, streams: List[str]):
        """
        Unsubscribe from streams

        Args:
            streams: List of stream names to unsubscribe from
        """
        self._subscriptions.difference_update(streams)

        if self._websocket and not self._websocket.closed:
            await self._unsubscribe_streams(streams)

        logger.info(f"Unsubscribed from {len(streams)} streams")

    async def _connection_manager(self):
        """Manage WebSocket connection with automatic reconnection"""
        while self._running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")

            if self._running:
                logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
                await asyncio.sleep(self.reconnect_interval)

    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages"""
        try:
            # Build WebSocket URL
            if self._subscriptions:
                streams = "/".join(sorted(self._subscriptions))
                url = urljoin(self.base_url, streams)
            else:
                # Use a dummy stream for connection
                url = urljoin(self.base_url, "btcusdt@ticker")

            logger.info(f"Connecting to WebSocket: {url[:100]}...")

            async with websockets.connect(
                url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                max_size=2**20,  # 1MB max message size
                compression=None  # Disable compression for lower latency
            ) as websocket:
                self._websocket = websocket
                logger.info("WebSocket connected successfully")

                # Subscribe to streams if we have any
                if self._subscriptions:
                    await self._resubscribe_all()

                # Listen for messages
                async for message in websocket:
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

    async def _handle_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)

            # Handle array of ticker data (all market tickers)
            if isinstance(data, list):
                for item in data:
                    await self._route_message(item)
            else:
                await self._route_message(data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def _route_message(self, data: Dict[str, Any]):
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

    async def _handle_kline_message(self, data: Dict[str, Any]):
        """Handle kline/candlestick message"""
        try:
            kline_data = data["k"]

            # Parse candle data
            candle = Candle(
                symbol=kline_data["s"],
                timeframe=TimeFrame(kline_data["i"]),
                open_time=datetime.fromtimestamp(kline_data["t"] / 1000),
                close_time=datetime.fromtimestamp(kline_data["T"] / 1000),
                open_price=Decimal(kline_data["o"]),
                high_price=Decimal(kline_data["h"]),
                low_price=Decimal(kline_data["l"]),
                close_price=Decimal(kline_data["c"]),
                volume=Decimal(kline_data["v"]),
                quote_volume=Decimal(kline_data["q"]),
                trades=int(kline_data["n"]),
                taker_buy_base_volume=Decimal(kline_data["V"]),
                taker_buy_quote_volume=Decimal(kline_data["Q"])
            )

            # Create and publish candle update event
            event = CandleUpdateEvent(
                timestamp=datetime.utcnow(),
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                candle=candle
            )

            await self._event_bus.publish(event)

            logger.debug(f"Published candle update for {candle.symbol} {candle.timeframe}")

        except Exception as e:
            logger.error(f"Error handling kline message: {e}")

    async def _handle_ticker_message(self, data: Dict[str, Any]):
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

    async def _handle_all_tickers_message(self, data: Dict[str, Any]):
        """Handle all market tickers message"""
        try:
            symbol = data["s"]
            price = Decimal(data["c"])
            volume = Decimal(data["v"])

            logger.debug(f"All tickers update: {symbol} = {price}, volume = {volume}")

        except Exception as e:
            logger.error(f"Error handling all tickers message: {e}")

    async def _handle_depth_message(self, data: Dict[str, Any]):
        """Handle order book depth message"""
        try:
            symbol = data["s"]
            bids = data["b"]
            asks = data["a"]

            logger.debug(f"Depth update for {symbol}: {len(bids)} bids, {len(asks)} asks")

        except Exception as e:
            logger.error(f"Error handling depth message: {e}")

    async def _handle_trade_message(self, data: Dict[str, Any]):
        """Handle trade message"""
        try:
            symbol = data["s"]
            price = Decimal(data["p"])
            quantity = Decimal(data["q"])
            is_buyer_maker = data["m"]

            logger.debug(f"Trade: {symbol} {quantity} @ {price} (buyer_maker: {is_buyer_maker})")

        except Exception as e:
            logger.error(f"Error handling trade message: {e}")

    async def _subscribe_streams(self, streams: List[str]):
        """Subscribe to additional streams"""
        if not streams:
            return

        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        }

        try:
            await self._websocket.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to {len(streams)} additional streams")
        except Exception as e:
            logger.error(f"Error subscribing to streams: {e}")

    async def _unsubscribe_streams(self, streams: List[str]):
        """Unsubscribe from streams"""
        if not streams:
            return

        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": 2
        }

        try:
            await self._websocket.send(json.dumps(unsubscribe_msg))
            logger.info(f"Unsubscribed from {len(streams)} streams")
        except Exception as e:
            logger.error(f"Error unsubscribing from streams: {e}")

    async def _resubscribe_all(self):
        """Resubscribe to all streams after reconnection"""
        if self._subscriptions:
            await self._subscribe_streams(list(self._subscriptions))

    def get_subscriptions(self) -> List[str]:
        """Get current subscriptions"""
        return list(self._subscriptions)

    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._websocket is not None and not self._websocket.closed

    async def health_check(self) -> Dict[str, Any]:
        """Get health status"""
        return {
            "connected": self.is_connected(),
            "subscriptions": len(self._subscriptions),
            "symbols": len(self._symbols),
            "timeframes": len(self._timeframes),
            "running": self._running
        }