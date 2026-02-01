"""
Data Ingestion Service

Orchestrates real-time data ingestion and historical data backfilling.
Manages WebSocket connections and REST API calls.
"""

import asyncio
from datetime import UTC, datetime
import logging
from typing import Any

from ..bus import get_event_bus
from ..core.interfaces import DatabaseAdapterInterface
from ..models import Candle, CandleOrigin, CandleUpdateEvent, ErrorEvent, EventType, TimeFrame
from .binance_rest import BinanceRestClient
from .binance_ws import BinanceWebSocketClient

logger = logging.getLogger(__name__)

# Number of recent candles to publish for pipeline warm-up during backfill
WARMUP_CANDLE_COUNT = 10

# Mapping of timeframe suffix to seconds multiplier
_TF_SECONDS: dict[str, int] = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def _timeframe_to_seconds(tf: TimeFrame) -> int:
    """Convert TimeFrame enum value (e.g. '15m', '4h') to seconds."""
    val = tf.value  # e.g. "15m"
    suffix = val[-1]
    num = int(val[:-1])
    return num * _TF_SECONDS.get(suffix, 60)


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

    def __init__(  # noqa: PLR0913
        self,
        binance_config: dict[Any, Any],
        symbols: list[str],
        timeframes: list[TimeFrame],
        backfill_days: int = 30,
        enable_realtime: bool = True,
        enable_backfill: bool = True,
        binance_breakers_config: dict[str, Any] | None = None,
        db_adapter: DatabaseAdapterInterface | None = None,
    ) -> None:
        self.symbols = symbols
        self.timeframes = timeframes
        self.backfill_days = backfill_days
        self.enable_realtime = enable_realtime
        self.enable_backfill = enable_backfill
        self._db_adapter = db_adapter

        # Select credentials (supports nested shape with spot/futures)
        creds = self._select_binance_credentials(binance_config)

        # Initialize clients
        ws_kwargs: dict[str, Any] = {
            "testnet": creds.get("testnet", True),
            "reconnect_interval": creds.get("reconnect_interval", 5),
        }
        ws_base_url = creds.get("ws_base_url")
        if isinstance(ws_base_url, str) and ws_base_url:
            ws_kwargs["base_url"] = ws_base_url
        self.ws_client = BinanceWebSocketClient(**ws_kwargs)

        rest_kwargs: dict[str, Any] = {
            "api_key": creds["api_key"],
            "api_secret": creds["api_secret"],
            "testnet": creds.get("testnet", True),
            "per_endpoint_breakers_config": binance_breakers_config,
        }
        rest_base_url = creds.get("base_url")
        if isinstance(rest_base_url, str) and rest_base_url:
            rest_kwargs["base_url"] = rest_base_url
        self.rest_client = BinanceRestClient(**rest_kwargs)

        self._event_bus = get_event_bus()
        self._running = False
        self._backfill_tasks: list[asyncio.Task[Any]] = []
        self._latest_candles: dict[str, dict[TimeFrame, Candle]] = {}
        self._backfill_complete: set[str] = set()
        self._candle_subscription_id: str | None = None

        logger.info(
            f"IngestService initialized for {len(symbols)} symbols "
            f"and {len(timeframes)} timeframes (db_adapter={'yes' if db_adapter else 'no'})",
        )

    # Provide a property to allow tests to inject a mockable client while preserving call assertions
    @property
    def rest_client(self) -> Any:
        return self._rest_client

    @rest_client.setter
    def rest_client(self, client: Any) -> None:
        self._rest_client = client

    def _select_binance_credentials(self, config: dict[Any, Any]) -> dict[str, Any]:
        """Select credentials from nested or flat binance config.

        Prefers 'spot' section when nested; otherwise expects flat keys.
        Raises KeyError if required keys are missing.
        """
        # Nested shape: {"spot": {...}, "futures": {...}}
        if "spot" in config or "futures" in config:
            spot = config.get("spot") or {}
            # Default to spot creds; allow top-level flags/URLs to override
            base = {
                "api_key": spot["api_key"],
                "api_secret": spot["api_secret"],
            }
            # Merge optional flags from top-level if present
            for k in ("testnet", "base_url", "ws_base_url", "reconnect_interval"):
                if k in config:
                    base[k] = config[k]
            return base

        # Flat shape fallback
        return {
            "api_key": config["api_key"],
            "api_secret": config["api_secret"],
            "testnet": config.get("testnet", True),
            "base_url": config.get("base_url"),
            "ws_base_url": config.get("ws_base_url"),
            "reconnect_interval": config.get("reconnect_interval", 5),
        }

    async def start(self) -> None:
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

            # Subscribe to candle updates for persistence (when db_adapter is present)
            if self._db_adapter is not None:
                self._candle_subscription_id = await self._event_bus.subscribe(
                    subscriber_id="ingest-candle-persistence",
                    handler=self._on_candle_update,
                    event_types=[EventType.CANDLE_UPDATE],
                )
                logger.info("IngestService subscribed to candle updates for DB persistence")

            # Start historical data backfill if enabled
            if self.enable_backfill:
                await self._start_backfill()

            logger.info("IngestService started successfully")

        except Exception as e:
            logger.error(f"Error starting IngestService: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the ingestion service"""
        if not self._running:
            return

        self._running = False

        # Cancel backfill tasks
        for task in self._backfill_tasks:
            task.cancel()

        await asyncio.gather(*self._backfill_tasks, return_exceptions=True)
        self._backfill_tasks.clear()

        # Unsubscribe from candle updates
        if self._candle_subscription_id is not None:
            await self._event_bus.unsubscribe(self._candle_subscription_id)
            self._candle_subscription_id = None
            logger.info("IngestService unsubscribed from candle updates")

        # Stop clients
        if self.ws_client:
            await self.ws_client.stop()

        if self.rest_client:
            await self.rest_client.stop()

        logger.info("IngestService stopped")

    async def _setup_realtime_streams(self) -> None:
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

    async def _on_candle_update(self, event: CandleUpdateEvent) -> None:
        """Handle CandleUpdateEvent and persist REALTIME/GAP_FILL candles to DB.

        BACKFILL candles are skipped since they're already written during backfill.
        """
        # Update latest candles tracking
        symbol = event.symbol
        timeframe = event.timeframe
        logger.info(
            f"_on_candle_update received: {symbol} {timeframe.value} origin={event.origin.value}",
        )

        if symbol not in self._latest_candles:
            self._latest_candles[symbol] = {}
        self._latest_candles[symbol][timeframe] = event.candle

        # Skip BACKFILL events - already written during backfill
        if event.origin == CandleOrigin.BACKFILL:
            logger.debug(f"Skipping BACKFILL candle: {symbol} {timeframe.value}")
            return

        # Persist REALTIME and GAP_FILL candles to DB
        if self._db_adapter is not None:
            try:
                await self._db_adapter.insert_candle(event.candle)
                logger.info(
                    f"Persisted {event.origin.value} candle to DB: {symbol} {timeframe.value}",
                )
            except Exception as e:
                logger.exception("Failed to persist candle %s %s", symbol, timeframe.value)
                await self._emit_error(
                    str(e),
                    "candle_persistence_failed",
                    symbol=symbol,
                )
        else:
            logger.warning(f"No db_adapter - skipping candle persist: {symbol} {timeframe.value}")

    async def _emit_error(self, message: str, error_type: str, symbol: str = "") -> None:
        try:
            error_event = ErrorEvent(
                event_type=EventType.ERROR,
                timestamp=datetime.now(UTC),
                symbol=symbol,
                error_type=error_type,
                error_message=message,
                component="ingest_service",
            )
            await self._event_bus.publish(error_event, priority=7)
        except Exception:
            logger.exception("Failed to publish ingest service error event")

    async def _start_backfill(self) -> None:
        """Start historical data backfill for all symbols and timeframes"""
        try:
            for symbol in self.symbols:
                for timeframe in self.timeframes:
                    task = asyncio.create_task(
                        self._backfill_symbol_timeframe(symbol, timeframe),
                    )
                    self._backfill_tasks.append(task)

            logger.info(f"Started {len(self._backfill_tasks)} backfill tasks")

        except Exception as e:
            logger.error(f"Error starting backfill: {e}")
            raise

    async def _backfill_symbol_timeframe(
        self,
        symbol: str,
        timeframe: TimeFrame,
    ) -> None:
        """Backfill historical data for a specific symbol and timeframe.

        If db_adapter is available, writes directly to database to avoid
        saturating the event bus queue. Only publishes the last N candles
        for pipeline warm-up with BACKFILL origin.

        Without db_adapter, falls back to publishing all candles to event bus.
        """
        try:
            logger.info(f"Starting backfill for {symbol} {timeframe.value}")

            # Get historical data
            candles = await self.rest_client.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                days_back=self.backfill_days,
            )

            if not candles:
                logger.info(f"No candles retrieved for {symbol} {timeframe.value}")
                return

            logger.info(
                f"Retrieved {len(candles)} candles for {symbol} {timeframe.value}",
            )

            if self._db_adapter is not None:
                # Optimized path: write directly to database
                inserted = await self._db_adapter.insert_candles_batch(candles)
                logger.info(
                    f"Inserted {inserted} candles to DB for {symbol} {timeframe.value}",
                )

                # Publish only the last N candles for pipeline warm-up
                warmup_candles = candles[-WARMUP_CANDLE_COUNT:]
                for candle in warmup_candles:
                    event = CandleUpdateEvent(
                        timestamp=datetime.now(UTC),
                        symbol=symbol,
                        timeframe=timeframe,
                        candle=candle,
                        origin=CandleOrigin.BACKFILL,
                    )
                    event.metadata["is_historical"] = True
                    await self._event_bus.publish(event)
            else:
                # Legacy path: publish all candles to event bus
                for candle in candles:
                    event = CandleUpdateEvent(
                        timestamp=datetime.now(UTC),
                        symbol=symbol,
                        timeframe=timeframe,
                        candle=candle,
                        origin=CandleOrigin.BACKFILL,
                    )
                    event.metadata["is_historical"] = True
                    await self._event_bus.publish(event)

            # Update latest candle tracking
            if symbol not in self._latest_candles:
                self._latest_candles[symbol] = {}
            self._latest_candles[symbol][timeframe] = candles[-1]

            # Mark backfill as complete for this symbol-timeframe
            backfill_key = f"{symbol}_{timeframe.value}"
            self._backfill_complete.add(backfill_key)

            logger.info(f"Backfill complete for {symbol} {timeframe.value}")

        except Exception as e:
            logger.error(f"Error backfilling {symbol} {timeframe.value}: {e}")

    async def add_symbol(self, symbol: str) -> None:
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
                    self._backfill_symbol_timeframe(symbol, timeframe),
                )
                self._backfill_tasks.append(task)

        logger.info(f"Added symbol {symbol} to ingestion")

    async def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol from ingestion"""
        if symbol not in self.symbols:
            logger.warning(f"Symbol {symbol} not being tracked")
            return

        self.symbols.remove(symbol)

        # Remove from WebSocket streams if running
        if self._running and self.enable_realtime:
            # Build stream names to unsubscribe
            streams = [f"{symbol.lower()}@kline_{tf.value}" for tf in self.timeframes] + [
                f"{symbol.lower()}@ticker",
            ]

            await self.ws_client.unsubscribe_streams(streams)

        # Clean up tracking data
        if symbol in self._latest_candles:
            del self._latest_candles[symbol]

        # Remove from backfill completion tracking
        to_remove = [key for key in self._backfill_complete if key.startswith(symbol)]
        for key in to_remove:
            self._backfill_complete.remove(key)

        logger.info(f"Removed symbol {symbol} from ingestion")

    async def add_timeframe(self, timeframe: TimeFrame) -> None:
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
                    self._backfill_symbol_timeframe(symbol, timeframe),
                )
                self._backfill_tasks.append(task)

        logger.info(f"Added timeframe {timeframe.value} to ingestion")

    async def get_latest_candle(
        self,
        symbol: str,
        timeframe: TimeFrame,
    ) -> Candle | None:
        """Get the latest candle for a symbol and timeframe"""
        return self._latest_candles.get(symbol, {}).get(timeframe)

    async def get_gap_detection(
        self,
        symbol: str,
        timeframe: TimeFrame,
    ) -> list[dict[Any, Any]]:
        """Detect gaps in candle data by comparing consecutive close_times.

        Compares each candle's close_time against the expected next close.
        If the delta exceeds the timeframe duration, a gap is reported.
        """
        if self._db_adapter is None or not hasattr(self._db_adapter, "get_candles"):
            return []

        try:
            candles = await self._db_adapter.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=1000,
            )
        except Exception as e:
            logger.error(f"Gap detection query failed for {symbol} {timeframe.value}: {e}")
            return []

        if len(candles) < 2:
            return []

        candles = sorted(candles, key=lambda c: c.open_time)

        duration_s = _timeframe_to_seconds(timeframe)
        # Allow 10% tolerance for slight timestamp drift
        threshold_s = duration_s * 1.1

        gaps: list[dict[Any, Any]] = []
        for i in range(1, len(candles)):
            prev_close = candles[i - 1].close_time
            curr_open = candles[i].open_time
            delta = (curr_open - prev_close).total_seconds()
            if delta > threshold_s:
                gaps.append(
                    {
                        "start_time": prev_close,
                        "end_time": curr_open,
                        "missing_seconds": delta,
                        "expected_candles": int(delta / duration_s) - 1,
                    }
                )

        if gaps:
            logger.warning(
                "Detected %d gaps for %s %s",
                len(gaps),
                symbol,
                timeframe.value,
            )

        return gaps

    async def fill_gaps(
        self,
        symbol: str,
        timeframe: TimeFrame,
        gaps: list[dict[Any, Any]],
    ) -> None:
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
                        timestamp=datetime.now(UTC),
                        symbol=symbol,
                        timeframe=timeframe,
                        candle=candle,
                        origin=CandleOrigin.GAP_FILL,
                    )
                    event.metadata["is_gap_fill"] = True
                    await self._event_bus.publish(event)

                logger.info(
                    f"Filled gap for {symbol} {timeframe.value}: {len(candles)} candles",
                )

            except Exception as e:
                logger.error(f"Error filling gap for {symbol} {timeframe.value}: {e}")

    def is_backfill_complete(self, symbol: str, timeframe: TimeFrame) -> bool:
        """Check if backfill is complete for a symbol and timeframe"""
        backfill_key = f"{symbol}_{timeframe.value}"
        return backfill_key in self._backfill_complete

    def get_backfill_progress(self) -> dict[str, dict[str, bool]]:
        """Get backfill progress for all symbols and timeframes"""
        progress: dict[str, dict[str, bool]] = {}
        for symbol in self.symbols:
            progress[symbol] = {}
            for timeframe in self.timeframes:
                progress[symbol][timeframe.value] = self.is_backfill_complete(
                    symbol,
                    timeframe,
                )
        return progress

    async def health_check(self) -> dict[str, Any]:
        """Get health status of the ingestion service"""
        ws_health = (
            await self.ws_client.health_check() if self.enable_realtime else {"status": "disabled"}
        )
        rest_health = await self.rest_client.health_check()

        now = datetime.now(UTC)
        latest_candle_ago_seconds: dict[str, dict[str, float]] = {}
        for symbol, by_timeframe in self._latest_candles.items():
            latest_candle_ago_seconds[symbol] = {}
            for timeframe, candle in by_timeframe.items():
                close_time = candle.close_time
                if close_time.tzinfo is None:
                    close_time = close_time.replace(tzinfo=UTC)
                latest_candle_ago_seconds[symbol][timeframe.value] = (
                    now - close_time
                ).total_seconds()

        return {
            "running": self._running,
            "symbols": len(self.symbols),
            "timeframes": len(self.timeframes),
            "backfill_tasks": len(self._backfill_tasks),
            "backfill_complete": len(self._backfill_complete),
            "websocket": ws_health,
            "rest_api": rest_health,
            "latest_candles": len(self._latest_candles),
            "latest_candle_ago_seconds": latest_candle_ago_seconds,
        }
