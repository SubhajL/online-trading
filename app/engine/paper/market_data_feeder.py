"""
Market Data Feeder for Paper Broker

Feeds live market data to paper broker for realistic order fills.
Can consume from:
1. Live WebSocket feeds
2. Database historical data
3. CSV files for testing
"""

import asyncio
from datetime import UTC, datetime, timedelta
import logging

from ..backtest.dataset import StreamingDataset, create_dataset
from ..models import TimeFrame
from .broker import PaperBroker

logger = logging.getLogger(__name__)


class MarketDataFeeder:
    """
    Feeds market data to paper broker for realistic fills.

    Supports both live and historical data sources.
    """

    def __init__(
        self,
        broker: PaperBroker,
        symbols: list[str],
        timeframes: list[TimeFrame],
        data_source: str = "timescale",
        **data_source_kwargs,
    ):
        self.broker = broker
        self.symbols = symbols
        self.timeframes = timeframes
        self.data_source = data_source
        self.data_source_kwargs = data_source_kwargs

        self.is_running = False
        self.datasets: dict[str, StreamingDataset] = {}
        self.tasks: list[asyncio.Task] = []

        logger.info(f"Market data feeder configured for {len(symbols)} symbols")

    async def start_live_feed(self):
        """Start live market data feed"""
        if self.is_running:
            logger.warning("Market data feeder already running")
            return

        self.is_running = True

        try:
            # Create dataset for each symbol/timeframe combination
            for symbol in self.symbols:
                for timeframe in self.timeframes:
                    key = f"{symbol}_{timeframe.value}"

                    dataset = create_dataset(
                        self.data_source,
                        **self.data_source_kwargs,
                    )
                    streaming_dataset = StreamingDataset(dataset)
                    self.datasets[key] = streaming_dataset

                    # Start streaming task
                    task = asyncio.create_task(
                        self._stream_candles(symbol, timeframe, streaming_dataset),
                    )
                    self.tasks.append(task)

            logger.info(f"Started {len(self.tasks)} market data streams")

        except Exception as e:
            logger.error(f"Error starting market data feed: {e}")
            await self.stop()
            raise

    async def start_historical_feed(
        self,
        start_date: datetime,
        end_date: datetime,
        speed_multiplier: float = 1.0,
    ):
        """Start historical data feed for testing"""
        if self.is_running:
            logger.warning("Market data feeder already running")
            return

        self.is_running = True

        try:
            # Create historical streaming tasks
            for symbol in self.symbols:
                for timeframe in self.timeframes:
                    task = asyncio.create_task(
                        self._stream_historical_candles(
                            symbol,
                            timeframe,
                            start_date,
                            end_date,
                            speed_multiplier,
                        ),
                    )
                    self.tasks.append(task)

            logger.info(f"Started historical feed from {start_date} to {end_date}")

        except Exception as e:
            logger.error(f"Error starting historical feed: {e}")
            await self.stop()
            raise

    async def _stream_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        streaming_dataset: StreamingDataset,
    ):
        """Stream live candles for a symbol/timeframe"""
        logger.info(f"Starting live stream for {symbol} {timeframe.value}")

        try:
            # For live data, we'd typically connect to WebSocket
            # For now, simulate by streaming recent data
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(days=1)  # Last 24 hours

            streaming_dataset.start_stream(symbol, timeframe, start_time, end_time)

            while self.is_running and streaming_dataset.has_more():
                candle = streaming_dataset.next_candle()
                if candle:
                    await self.broker.update_market_data(candle)
                    logger.debug(
                        f"Fed candle: {symbol} {timeframe.value} @ {candle.close_price}",
                    )

                # Wait for next candle interval
                await asyncio.sleep(self._get_interval_seconds(timeframe))

        except Exception as e:
            logger.error(f"Error in candle stream {symbol} {timeframe.value}: {e}")

    async def _stream_historical_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_date: datetime,
        end_date: datetime,
        speed_multiplier: float,
    ):
        """Stream historical candles at accelerated speed"""
        logger.info(f"Starting historical stream for {symbol} {timeframe.value}")

        try:
            dataset = create_dataset(self.data_source, **self.data_source_kwargs)
            streaming_dataset = StreamingDataset(dataset)

            streaming_dataset.start_stream(symbol, timeframe, start_date, end_date)

            interval_seconds = self._get_interval_seconds(timeframe) / speed_multiplier

            while self.is_running and streaming_dataset.has_more():
                candle = streaming_dataset.next_candle()
                if candle:
                    await self.broker.update_market_data(candle)
                    logger.debug(
                        f"Fed historical candle: {symbol} @ {candle.close_price}",
                    )

                await asyncio.sleep(interval_seconds)

        except Exception as e:
            logger.error(f"Error in historical stream {symbol} {timeframe.value}: {e}")

    def _get_interval_seconds(self, timeframe: TimeFrame) -> int:
        """Get interval in seconds for timeframe"""
        intervals = {
            TimeFrame.M1: 60,
            TimeFrame.M5: 300,
            TimeFrame.M15: 900,
            TimeFrame.M30: 1800,
            TimeFrame.H1: 3600,
            TimeFrame.H4: 14400,
            TimeFrame.D1: 86400,
        }
        return intervals.get(timeframe, 300)  # Default to 5 minutes

    async def stop(self):
        """Stop market data feed"""
        if not self.is_running:
            return

        self.is_running = False

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

        self.tasks.clear()
        self.datasets.clear()

        logger.info("Market data feeder stopped")

    def is_feeding(self) -> bool:
        """Check if feeder is running"""
        return self.is_running and any(not task.done() for task in self.tasks)

    async def add_symbol(self, symbol: str):
        """Add a new symbol to the feed"""
        if symbol in self.symbols:
            return

        self.symbols.append(symbol)

        if not self.is_running:
            return

        # Start streaming for new symbol
        for timeframe in self.timeframes:
            key = f"{symbol}_{timeframe.value}"

            dataset = create_dataset(self.data_source, **self.data_source_kwargs)
            streaming_dataset = StreamingDataset(dataset)
            self.datasets[key] = streaming_dataset

            task = asyncio.create_task(
                self._stream_candles(symbol, timeframe, streaming_dataset),
            )
            self.tasks.append(task)

        logger.info(f"Added symbol {symbol} to market data feed")

    async def remove_symbol(self, symbol: str):
        """Remove a symbol from the feed"""
        if symbol not in self.symbols:
            return

        self.symbols.remove(symbol)

        # Cancel tasks for this symbol
        tasks_to_remove = []
        for i, task in enumerate(self.tasks):
            task_name = task.get_name() if hasattr(task, "get_name") else ""
            if symbol in task_name:
                task.cancel()
                tasks_to_remove.append(i)

        # Remove cancelled tasks
        for i in reversed(tasks_to_remove):
            self.tasks.pop(i)

        # Remove datasets
        keys_to_remove = [k for k in self.datasets.keys() if symbol in k]
        for key in keys_to_remove:
            del self.datasets[key]

        logger.info(f"Removed symbol {symbol} from market data feed")


class MockLiveDataFeeder:
    """
    Mock live data feeder that replays recent historical data.

    Useful for testing without needing actual live WebSocket connections.
    """

    def __init__(
        self,
        broker: PaperBroker,
        symbols: list[str],
        timeframe: TimeFrame = TimeFrame.M1,
        lookback_hours: int = 24,
    ):
        self.broker = broker
        self.symbols = symbols
        self.timeframe = timeframe
        self.lookback_hours = lookback_hours
        self.is_running = False

    async def start(self, database_url: str):
        """Start mock live data feed"""
        if self.is_running:
            return

        self.is_running = True

        try:
            # Create feeder with recent historical data
            feeder = MarketDataFeeder(
                broker=self.broker,
                symbols=self.symbols,
                timeframes=[self.timeframe],
                data_source="timescale",
                database_url=database_url,
            )

            # Stream recent data as "live" feed
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=self.lookback_hours)

            await feeder.start_historical_feed(
                start_time,
                end_time,
                speed_multiplier=60.0,  # 60x speed for testing
            )

            # Keep running
            while self.is_running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Mock live data feeder error: {e}")
        finally:
            self.is_running = False

    def stop(self):
        """Stop mock feeder"""
        self.is_running = False
