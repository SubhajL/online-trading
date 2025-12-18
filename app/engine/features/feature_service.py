from typing import Any

"""
Feature Service

Manages the calculation and distribution of technical analysis features.
Listens for candle updates and calculates indicators in real-time.
"""

from collections import defaultdict, deque
from datetime import UTC, datetime
import logging

from ..bus import get_event_bus
from ..models import (
    Candle,
    CandleUpdateEvent,
    EventType,
    FeaturesCalculatedEvent,
    TechnicalIndicators,
    TimeFrame,
    is_realtime_candle_event,
)
from .indicators import TechnicalIndicatorsCalculator

logger = logging.getLogger(__name__)


class FeatureService:
    """
    Service for calculating and managing technical analysis features.

    Features:
    - Real-time indicator calculation on candle updates
    - Multi-symbol and multi-timeframe support
    - Configurable indicator parameters
    - Historical candle buffering for calculations
    - Event-driven architecture
    """

    def __init__(
        self,
        buffer_size: int = 1000,
        ema_periods: list[int] = [9, 21, 50, 200],
        rsi_period: int = 14,
        macd_params: tuple[Any, ...] = (12, 26, 9),
        atr_period: int = 14,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
    ) -> None:
        self.buffer_size = buffer_size
        self.ema_periods = ema_periods
        self.rsi_period = rsi_period
        self.macd_params = macd_params
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.bb_std_dev = bb_std_dev

        # Candle buffers: symbol -> timeframe -> deque of candles
        self._candle_buffers: dict[str, dict[TimeFrame, deque[Candle]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=buffer_size)),
        )

        # Latest indicators: symbol -> timeframe -> TechnicalIndicators
        self._latest_indicators: dict[str, dict[TimeFrame, TechnicalIndicators]] = (
            defaultdict(dict[Any, Any])
        )

        self._event_bus = get_event_bus()
        self._running = False
        self._subscription_id: str | None = None

        # Statistics
        self._calculations_performed = 0
        self._last_calculation_time: datetime | None = None

        logger.info(
            f"FeatureService initialized with buffer_size={buffer_size}, "
            f"EMA periods={ema_periods}",
        )

    async def start(self) -> None:
        """Start the feature service"""
        if self._running:
            logger.warning("FeatureService is already running")
            return

        self._running = True

        # Subscribe to candle update events
        self._subscription_id = await self._event_bus.subscribe(
            subscriber_id="feature_service",
            handler=self._handle_candle_update,
            event_types=[EventType.CANDLE_UPDATE],
            priority=5,  # High priority for real-time processing
        )

        logger.info("FeatureService started and subscribed to candle updates")

    async def stop(self) -> None:
        """Stop the feature service"""
        if not self._running:
            return

        self._running = False

        # Unsubscribe from events
        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

        logger.info("FeatureService stopped")

    async def _handle_candle_update(self, event: CandleUpdateEvent) -> None:
        """Handle candle update events.

        Always adds candles to buffer for indicator calculation context.
        Only publishes features for REALTIME events to avoid trading on
        historical data.
        """
        try:
            candle = event.candle
            symbol = candle.symbol
            timeframe = candle.timeframe

            # Always add candle to buffer for warm-up/context
            self._candle_buffers[symbol][timeframe].append(candle)

            # Only process REALTIME events through the trading pipeline
            if not is_realtime_candle_event(event.origin):
                logger.debug(
                    f"Skipping non-realtime candle for {symbol} {timeframe.value} "
                    f"(origin={event.origin.value})"
                )
                return

            # Calculate indicators if we have enough data
            min_required = max(
                max(self.ema_periods) if self.ema_periods else 0,
                self.rsi_period,
                max(self.macd_params),
                self.atr_period,
                self.bb_period,
            )

            if len(self._candle_buffers[symbol][timeframe]) >= min_required:
                await self._calculate_and_publish_indicators(symbol, timeframe)

            logger.debug(f"Processed candle update for {symbol} {timeframe.value}")

        except Exception as e:
            logger.error(f"Error handling candle update: {e}")

    async def _calculate_and_publish_indicators(
        self,
        symbol: str,
        timeframe: TimeFrame,
    ) -> None:
        """Calculate indicators and publish features calculated event"""
        try:
            # Get candles from buffer
            candles = list(self._candle_buffers[symbol][timeframe])

            # Calculate indicators
            indicators = TechnicalIndicatorsCalculator.calculate_all_indicators(
                candles=candles,
                ema_periods=self.ema_periods,
                rsi_period=self.rsi_period,
                macd_params=self.macd_params,
                atr_period=self.atr_period,
                bb_period=self.bb_period,
                bb_std_dev=self.bb_std_dev,
            )

            # Store latest indicators
            self._latest_indicators[symbol][timeframe] = indicators

            # Create and publish features calculated event
            event = FeaturesCalculatedEvent(
                timestamp=datetime.now(UTC),
                symbol=symbol,
                timeframe=timeframe,
                features=indicators,
            )

            await self._event_bus.publish(event, priority=5)

            # Update statistics
            self._calculations_performed += 1
            self._last_calculation_time = datetime.now(UTC)

            logger.debug(f"Published features for {symbol} {timeframe.value}")

        except Exception as e:
            logger.error(
                f"Error calculating indicators for {symbol} {timeframe.value}: {e}",
            )

    async def get_latest_indicators(
        self,
        symbol: str,
        timeframe: TimeFrame,
    ) -> TechnicalIndicators | None:
        """Get the latest calculated indicators for a symbol and timeframe"""
        return self._latest_indicators.get(symbol, {}).get(timeframe)

    async def get_indicators_history(
        self,
        symbol: str,
        timeframe: TimeFrame,
        limit: int = 100,
    ) -> list[TechnicalIndicators]:
        """
        Get historical indicators by recalculating for each candle in buffer

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            limit: Maximum number of indicators to return

        Returns:
            list[Any] of TechnicalIndicators in chronological order
        """
        try:
            candles = list(self._candle_buffers[symbol][timeframe])
            if not candles:
                return []

            indicators_history = []
            min_required = max(
                max(self.ema_periods) if self.ema_periods else 0,
                self.rsi_period,
                max(self.macd_params),
                self.atr_period,
                self.bb_period,
            )

            # Calculate indicators for each point with sufficient history
            for i in range(min_required - 1, len(candles)):
                candle_subset = candles[: i + 1]

                indicators = TechnicalIndicatorsCalculator.calculate_all_indicators(
                    candles=candle_subset,
                    ema_periods=self.ema_periods,
                    rsi_period=self.rsi_period,
                    macd_params=self.macd_params,
                    atr_period=self.atr_period,
                    bb_period=self.bb_period,
                    bb_std_dev=self.bb_std_dev,
                )

                indicators_history.append(indicators)

            # Return last 'limit' indicators
            return indicators_history[-limit:]

        except Exception as e:
            logger.error(f"Error getting indicators history: {e}")
            return []

    async def add_candles_bulk(
        self,
        symbol: str,
        timeframe: TimeFrame,
        candles: list[Candle],
    ) -> None:
        """
        Add multiple candles to the buffer (useful for historical data)

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            candles: list[Any] of candles in chronological order
        """
        try:
            # Sort candles by timestamp to ensure chronological order
            sorted_candles = sorted(candles, key=lambda c: c.open_time)

            # Add to buffer
            buffer = self._candle_buffers[symbol][timeframe]
            for candle in sorted_candles:
                buffer.append(candle)

            # Calculate latest indicators if we have enough data
            min_required = max(
                max(self.ema_periods) if self.ema_periods else 0,
                self.rsi_period,
                max(self.macd_params),
                self.atr_period,
                self.bb_period,
            )

            if len(buffer) >= min_required:
                await self._calculate_and_publish_indicators(symbol, timeframe)

            logger.info(f"Added {len(candles)} candles for {symbol} {timeframe.value}")

        except Exception as e:
            logger.error(f"Error adding bulk candles: {e}")

    def get_buffer_info(self, symbol: str, timeframe: TimeFrame) -> dict[Any, Any]:
        """Get information about the candle buffer for a symbol and timeframe"""
        buffer = self._candle_buffers[symbol][timeframe]
        return {
            "size": len(buffer),
            "max_size": buffer.maxlen,
            "oldest_candle": buffer[0].open_time if buffer else None,
            "newest_candle": buffer[-1].open_time if buffer else None,
        }

    def get_all_tracked_symbols_timeframes(self) -> list[tuple[Any, ...]]:
        """Get all symbol-timeframe combinations currently being tracked"""
        combinations = []
        for symbol in self._candle_buffers:
            for timeframe in self._candle_buffers[symbol]:
                if len(self._candle_buffers[symbol][timeframe]) > 0:
                    combinations.append((symbol, timeframe))
        return combinations

    async def recalculate_indicators(self, symbol: str, timeframe: TimeFrame) -> None:
        """Force recalculation of indicators for a symbol and timeframe"""
        try:
            if len(self._candle_buffers[symbol][timeframe]) > 0:
                await self._calculate_and_publish_indicators(symbol, timeframe)
                logger.info(f"Recalculated indicators for {symbol} {timeframe.value}")
            else:
                logger.warning(f"No candles available for {symbol} {timeframe.value}")
        except Exception as e:
            logger.error(f"Error recalculating indicators: {e}")

    def clear_buffer(self, symbol: str, timeframe: TimeFrame) -> None:
        """Clear the candle buffer for a symbol and timeframe"""
        self._candle_buffers[symbol][timeframe].clear()
        if (
            symbol in self._latest_indicators
            and timeframe in self._latest_indicators[symbol]
        ):
            del self._latest_indicators[symbol][timeframe]
        logger.info(f"Cleared buffer for {symbol} {timeframe.value}")

    def clear_all_buffers(self) -> None:
        """Clear all candle buffers"""
        self._candle_buffers.clear()
        self._latest_indicators.clear()
        logger.info("Cleared all buffers")

    async def health_check(self) -> dict[Any, Any]:
        """Get health status of the feature service"""
        total_symbols = len(self._candle_buffers)
        total_timeframes = sum(
            len(tf_dict) for tf_dict in self._candle_buffers.values()
        )
        total_candles = sum(
            len(buffer)
            for symbol_dict in self._candle_buffers.values()
            for buffer in symbol_dict.values()
        )

        return {
            "running": self._running,
            "subscription_active": self._subscription_id is not None,
            "tracked_symbols": total_symbols,
            "tracked_timeframes": total_timeframes,
            "total_candles_buffered": total_candles,
            "calculations_performed": self._calculations_performed,
            "last_calculation": (
                self._last_calculation_time.isoformat()
                if self._last_calculation_time
                else None
            ),
            "configuration": {
                "buffer_size": self.buffer_size,
                "ema_periods": self.ema_periods,
                "rsi_period": self.rsi_period,
                "macd_params": self.macd_params,
                "atr_period": self.atr_period,
                "bb_period": self.bb_period,
                "bb_std_dev": self.bb_std_dev,
            },
        }
