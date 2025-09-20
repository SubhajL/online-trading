"""
Data Ingestion Service

Orchestrates real-time data ingestion and historical data backfilling.
Manages WebSocket connections and REST API calls.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from .binance_ws import BinanceWebSocketClient
from .binance_rest import BinanceRestClient
from ..models import Candle, CandleUpdateEvent, TimeFrame
from ..bus import get_event_bus


logger = logging.getLogger(__name__)


class IngestService:
    """
    Main data ingestion service that coordinates real-time and historical data.

    Features:
    - Real-time WebSocket data streams
    - Historical data backfilling
    - Gap detection and filling
    - Multi-symbol and multi-timeframe support
    - Error handling and recovery
    """

    def __init__(
        self,
        binance_config: Dict,
        symbols: List[str],
        timeframes: List[TimeFrame],
        backfill_days: int = 30,
        enable_realtime: bool = True,
        enable_backfill: bool = True,
    ):
        self.symbols = symbols
        self.timeframes = timeframes
        self.backfill_days = backfill_days
        self.enable_realtime = enable_realtime
        self.enable_backfill = enable_backfill

        # Initialize clients
        self.ws_client = BinanceWebSocketClient(
            testnet=binance_config.get("testnet", True),
            base_url=binance_config.get("ws_base_url"),
            reconnect_interval=binance_config.get("reconnect_interval", 5),
        )

        self.rest_client = BinanceRestClient(
            api_key=binance_config["api_key"],
            api_secret=binance_config["api_secret"],
            testnet=binance_config.get("testnet", True),
            base_url=binance_config.get("base_url"),
        )

        self._event_bus = get_event_bus()
        self._running = False
        self._backfill_tasks: List[asyncio.Task] = []
        self._latest_candles: Dict[str, Dict[TimeFrame, Candle]] = {}
        self._backfill_complete: Set[str] = set()

        logger.info(
            f"IngestService initialized for {len(symbols)} symbols "
            f"and {len(timeframes)} timeframes"
        )

    async def start(self):
        """Start the ingestion service"""
        if self._running:
            logger.warning("IngestService is already running")
            return

        self._running = True

        try:
            # Start REST client
            await self.rest_client.start()

            # Start WebSocket client if enabled
            if self.enable_realtime:
                await self.ws_client.start()
                await self._setup_realtime_streams()

            # Start historical data backfill if enabled
            if self.enable_backfill:
                await self._start_backfill()

            logger.info("IngestService started successfully")

        except Exception as e:
            logger.error(f"Error starting IngestService: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop the ingestion service"""
        if not self._running:
            return

        self._running = False

        # Cancel backfill tasks
        for task in self._backfill_tasks:
            task.cancel()

        await asyncio.gather(*self._backfill_tasks, return_exceptions=True)
        self._backfill_tasks.clear()

        # Stop clients
        if self.ws_client:
            await self.ws_client.stop()

        if self.rest_client:
            await self.rest_client.stop()

        logger.info("IngestService stopped")

    async def _setup_realtime_streams(self):
        """Setup real-time WebSocket streams"""
        try:
            # Subscribe to kline streams for all symbols and timeframes
            await self.ws_client.subscribe_klines(self.symbols, self.timeframes)

            # Subscribe to ticker streams for price updates
            await self.ws_client.subscribe_ticker(self.symbols)

            logger.info("Real-time streams setup complete")

        except Exception as e:
            logger.error(f"Error setting up real-time streams: {e}")
            raise

    async def _start_backfill(self):
        """Start historical data backfill for all symbols and timeframes"""
        try:
            for symbol in self.symbols:
                for timeframe in self.timeframes:
                    task = asyncio.create_task(
                        self._backfill_symbol_timeframe(symbol, timeframe)
                    )
                    self._backfill_tasks.append(task)

            logger.info(f"Started {len(self._backfill_tasks)} backfill tasks")

        except Exception as e:
            logger.error(f"Error starting backfill: {e}")
            raise

    async def _backfill_symbol_timeframe(self, symbol: str, timeframe: TimeFrame):
        """Backfill historical data for a specific symbol and timeframe"""
        try:
            logger.info(f"Starting backfill for {symbol} {timeframe.value}")

            # Get historical data
            candles = await self.rest_client.get_historical_data(
                symbol=symbol, timeframe=timeframe, days_back=self.backfill_days
            )

            logger.info(
                f"Retrieved {len(candles)} candles for {symbol} {timeframe.value}"
            )

            # Publish historical candles as events
            for candle in candles:
                event = CandleUpdateEvent(
                    timestamp=datetime.utcnow(),
                    symbol=symbol,
                    timeframe=timeframe,
                    candle=candle,
                )
                event.metadata["is_historical"] = True
                await self._event_bus.publish(event)

                # Update latest candle tracking
                if symbol not in self._latest_candles:
                    self._latest_candles[symbol] = {}
                self._latest_candles[symbol][timeframe] = candle

            # Mark backfill as complete for this symbol-timeframe
            backfill_key = f"{symbol}_{timeframe.value}"
            self._backfill_complete.add(backfill_key)

            logger.info(f"Backfill complete for {symbol} {timeframe.value}")

        except Exception as e:
            logger.error(f"Error backfilling {symbol} {timeframe.value}: {e}")

    async def add_symbol(self, symbol: str):
        """Add a new symbol to ingestion"""
        if symbol in self.symbols:
            logger.warning(f"Symbol {symbol} already being tracked")
            return

        self.symbols.append(symbol)

        # Add to WebSocket streams if running
        if self._running and self.enable_realtime:
            await self.ws_client.subscribe_klines([symbol], self.timeframes)
            await self.ws_client.subscribe_ticker([symbol])

        # Start backfill for new symbol if enabled
        if self._running and self.enable_backfill:
            for timeframe in self.timeframes:
                task = asyncio.create_task(
                    self._backfill_symbol_timeframe(symbol, timeframe)
                )
                self._backfill_tasks.append(task)

        logger.info(f"Added symbol {symbol} to ingestion")

    async def remove_symbol(self, symbol: str):
        """Remove a symbol from ingestion"""
        if symbol not in self.symbols:
            logger.warning(f"Symbol {symbol} not being tracked")
            return

        self.symbols.remove(symbol)

        # Remove from WebSocket streams if running
        if self._running and self.enable_realtime:
            # Build stream names to unsubscribe
            streams = []
            for timeframe in self.timeframes:
                streams.append(f"{symbol.lower()}@kline_{timeframe.value}")
            streams.append(f"{symbol.lower()}@ticker")

            await self.ws_client.unsubscribe_streams(streams)

        # Clean up tracking data
        if symbol in self._latest_candles:
            del self._latest_candles[symbol]

        # Remove from backfill completion tracking
        to_remove = [key for key in self._backfill_complete if key.startswith(symbol)]
        for key in to_remove:
            self._backfill_complete.remove(key)

        logger.info(f"Removed symbol {symbol} from ingestion")

    async def add_timeframe(self, timeframe: TimeFrame):
        """Add a new timeframe to ingestion"""
        if timeframe in self.timeframes:
            logger.warning(f"Timeframe {timeframe.value} already being tracked")
            return

        self.timeframes.append(timeframe)

        # Add to WebSocket streams if running
        if self._running and self.enable_realtime:
            await self.ws_client.subscribe_klines(self.symbols, [timeframe])

        # Start backfill for new timeframe if enabled
        if self._running and self.enable_backfill:
            for symbol in self.symbols:
                task = asyncio.create_task(
                    self._backfill_symbol_timeframe(symbol, timeframe)
                )
                self._backfill_tasks.append(task)

        logger.info(f"Added timeframe {timeframe.value} to ingestion")

    async def get_latest_candle(
        self, symbol: str, timeframe: TimeFrame
    ) -> Optional[Candle]:
        """Get the latest candle for a symbol and timeframe"""
        return self._latest_candles.get(symbol, {}).get(timeframe)

    async def get_gap_detection(self, symbol: str, timeframe: TimeFrame) -> List[Dict]:
        """Detect gaps in historical data"""
        # This would implement gap detection logic
        # For now, return empty list
        gaps = []

        # TODO: Implement actual gap detection by checking timestamp sequences
        # in the database or cached data

        return gaps

    async def fill_gaps(self, symbol: str, timeframe: TimeFrame, gaps: List[Dict]):
        """Fill detected gaps in historical data"""
        for gap in gaps:
            try:
                start_time = gap["start_time"]
                end_time = gap["end_time"]

                # Fetch missing data
                candles = await self.rest_client.get_klines(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_time=start_time,
                    end_time=end_time,
                )

                # Publish gap-fill candles
                for candle in candles:
                    event = CandleUpdateEvent(
                        timestamp=datetime.utcnow(),
                        symbol=symbol,
                        timeframe=timeframe,
                        candle=candle,
                    )
                    event.metadata["is_gap_fill"] = True
                    await self._event_bus.publish(event)

                logger.info(
                    f"Filled gap for {symbol} {timeframe.value}: {len(candles)} candles"
                )

            except Exception as e:
                logger.error(f"Error filling gap for {symbol} {timeframe.value}: {e}")

    def is_backfill_complete(self, symbol: str, timeframe: TimeFrame) -> bool:
        """Check if backfill is complete for a symbol and timeframe"""
        backfill_key = f"{symbol}_{timeframe.value}"
        return backfill_key in self._backfill_complete

    def get_backfill_progress(self) -> Dict[str, Dict[str, bool]]:
        """Get backfill progress for all symbols and timeframes"""
        progress = {}
        for symbol in self.symbols:
            progress[symbol] = {}
            for timeframe in self.timeframes:
                progress[symbol][timeframe.value] = self.is_backfill_complete(
                    symbol, timeframe
                )
        return progress

    async def health_check(self) -> Dict[str, any]:
        """Get health status of the ingestion service"""
        ws_health = (
            await self.ws_client.health_check()
            if self.enable_realtime
            else {"status": "disabled"}
        )
        rest_health = await self.rest_client.health_check()

        return {
            "running": self._running,
            "symbols": len(self.symbols),
            "timeframes": len(self.timeframes),
            "backfill_tasks": len(self._backfill_tasks),
            "backfill_complete": len(self._backfill_complete),
            "websocket": ws_health,
            "rest_api": rest_health,
            "latest_candles": len(self._latest_candles),
        }
