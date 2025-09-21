"""
Feature Engine - Consumes candles and produces technical indicators

This engine listens to candle events, calculates technical indicators using
the shared math library, writes to the database, and publishes feature events.
"""

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal
from typing import Deque, Dict, List, Optional

import numpy as np

from ..shared.math import (
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_vwap,
    calculate_vwma,
)

from ..models import (
    BaseEvent,
    EventType,
    TimeFrame,
    Candle,
    TechnicalIndicators,
    FeaturesCalculatedEvent,
)

from ..bus import get_event_bus
from ..adapters.db.timescale_adapter import TimescaleDBAdapter

logger = logging.getLogger(__name__)


class FeatureEngine:
    """
    Feature engine that calculates technical indicators from candles.

    Features:
    - Consumes candles.v1 events from bus or DB tail
    - Calculates EMA(20/50/200), RSI(14), MACD(12,26,9), ATR(14), BB(20,2), VWAP
    - Writes to indicators table
    - Publishes features.v1 events
    - Idempotent on (symbol, tf, ts)
    """

    def __init__(
        self,
        db_adapter: TimescaleDBAdapter,
        buffer_size: int = 500,
        ema_periods: List[int] = [20, 50, 200],
        rsi_period: int = 14,
        macd_params: tuple = (12, 26, 9),
        atr_period: int = 14,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
        vwma_period: int = 20,
    ):
        self.db_adapter = db_adapter
        self.buffer_size = buffer_size
        self.ema_periods = sorted(ema_periods)  # Ensure sorted for efficiency
        self.rsi_period = rsi_period
        self.macd_params = macd_params
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.bb_std_dev = bb_std_dev
        self.vwma_period = vwma_period

        # Candle buffers: symbol -> timeframe -> deque of candles
        self._candle_buffers: Dict[str, Dict[TimeFrame, Deque[Candle]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=buffer_size))
        )

        # Track processed timestamps to ensure idempotency
        self._processed: Dict[str, Dict[TimeFrame, set]] = defaultdict(
            lambda: defaultdict(set)
        )

        self._event_bus = get_event_bus()
        self._running = False
        self._subscription_id: Optional[str] = None

        # Statistics
        self._calculations_performed = 0
        self._db_writes = 0

        logger.info(
            f"FeatureEngine initialized with buffer_size={buffer_size}, "
            f"EMA periods={ema_periods}"
        )

    async def start(self):
        """Start the feature engine"""
        if self._running:
            logger.warning("FeatureEngine is already running")
            return

        self._running = True

        # Subscribe to candle events
        self._subscription_id = await self._event_bus.subscribe(
            subscriber_id="feature_engine",
            handler=self._handle_candle_event,
            event_types=[EventType.CANDLE_UPDATE],
            priority=5,
        )

        logger.info("FeatureEngine started and subscribed to candle updates")

    async def stop(self):
        """Stop the feature engine"""
        if not self._running:
            return

        self._running = False

        # Unsubscribe from events
        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

        logger.info("FeatureEngine stopped")

    async def _handle_candle_event(self, event: BaseEvent):
        """Handle candle update events"""
        try:
            if event.event_type != EventType.CANDLE_UPDATE:
                return

            candle = event.candle
            await self.process_candle(candle)

        except Exception as e:
            logger.error(f"Error handling candle event: {e}", exc_info=True)

    async def process_candle(self, candle: Candle):
        """Process a single candle, calculate indicators, and publish results"""
        symbol = candle.symbol
        timeframe = candle.timeframe
        timestamp = candle.close_time

        # Check idempotency
        if timestamp in self._processed[symbol][timeframe]:
            logger.debug(f"Already processed {symbol} {timeframe} at {timestamp}")
            return

        # Add candle to buffer
        self._candle_buffers[symbol][timeframe].append(candle)

        # Check if we have enough data for all indicators
        min_required = max(
            max(self.ema_periods),
            self.rsi_period + 1,  # RSI needs one extra for price changes
            max(self.macd_params),
            self.atr_period,
            self.bb_period,
            self.vwma_period,
        )

        if len(self._candle_buffers[symbol][timeframe]) < min_required:
            logger.debug(
                f"Insufficient data for {symbol} {timeframe}: "
                f"{len(self._candle_buffers[symbol][timeframe])} < {min_required}"
            )
            return

        # Calculate indicators
        indicators = await self._calculate_indicators(symbol, timeframe)

        if indicators:
            # Write to database
            await self._write_to_database(indicators)

            # Publish event
            await self._publish_features_event(indicators)

            # Mark as processed
            self._processed[symbol][timeframe].add(timestamp)

    async def _calculate_indicators(
        self, symbol: str, timeframe: TimeFrame
    ) -> Optional[TechnicalIndicators]:
        """Calculate all technical indicators for the latest candle"""
        try:
            candles = list(self._candle_buffers[symbol][timeframe])
            if not candles:
                return None

            latest_candle = candles[-1]

            # Extract price arrays
            close_prices = np.array([float(c.close_price) for c in candles])
            high_prices = np.array([float(c.high_price) for c in candles])
            low_prices = np.array([float(c.low_price) for c in candles])
            volumes = np.array([float(c.volume) for c in candles])

            # Create indicators object
            indicators = TechnicalIndicators(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=latest_candle.close_time,
            )

            # Calculate EMAs
            for period in self.ema_periods:
                ema_values = calculate_ema(close_prices, period)
                if period == 9:
                    indicators.ema_9 = (
                        Decimal(str(ema_values[-1]))
                        if not np.isnan(ema_values[-1])
                        else None
                    )
                elif period == 20:
                    indicators.ema_21 = (
                        Decimal(str(ema_values[-1]))
                        if not np.isnan(ema_values[-1])
                        else None
                    )
                elif period == 21:
                    indicators.ema_21 = (
                        Decimal(str(ema_values[-1]))
                        if not np.isnan(ema_values[-1])
                        else None
                    )
                elif period == 50:
                    indicators.ema_50 = (
                        Decimal(str(ema_values[-1]))
                        if not np.isnan(ema_values[-1])
                        else None
                    )
                elif period == 200:
                    indicators.ema_200 = (
                        Decimal(str(ema_values[-1]))
                        if not np.isnan(ema_values[-1])
                        else None
                    )

            # Calculate RSI
            rsi_values = calculate_rsi(close_prices, self.rsi_period)
            indicators.rsi_14 = (
                Decimal(str(rsi_values[-1])) if not np.isnan(rsi_values[-1]) else None
            )

            # Calculate MACD
            macd_line, signal_line, histogram = calculate_macd(
                close_prices,
                self.macd_params[0],
                self.macd_params[1],
                self.macd_params[2],
            )
            indicators.macd_line = (
                Decimal(str(macd_line[-1])) if not np.isnan(macd_line[-1]) else None
            )
            indicators.macd_signal = (
                Decimal(str(signal_line[-1])) if not np.isnan(signal_line[-1]) else None
            )
            indicators.macd_histogram = (
                Decimal(str(histogram[-1])) if not np.isnan(histogram[-1]) else None
            )

            # Calculate ATR
            atr_values = calculate_atr(
                high_prices, low_prices, close_prices, self.atr_period
            )
            indicators.atr_14 = (
                Decimal(str(atr_values[-1])) if not np.isnan(atr_values[-1]) else None
            )

            # Calculate Bollinger Bands
            upper_band, middle_band, lower_band = calculate_bollinger_bands(
                close_prices, self.bb_period, self.bb_std_dev
            )
            indicators.bb_upper = (
                Decimal(str(upper_band[-1])) if not np.isnan(upper_band[-1]) else None
            )
            indicators.bb_middle = (
                Decimal(str(middle_band[-1])) if not np.isnan(middle_band[-1]) else None
            )
            indicators.bb_lower = (
                Decimal(str(lower_band[-1])) if not np.isnan(lower_band[-1]) else None
            )

            # Calculate BB width and percent
            if all(
                v is not None
                for v in [
                    indicators.bb_upper,
                    indicators.bb_middle,
                    indicators.bb_lower,
                ]
            ):
                indicators.bb_width = (
                    indicators.bb_upper - indicators.bb_lower
                ) / indicators.bb_middle
                indicators.bb_percent = (
                    latest_candle.close_price - indicators.bb_lower
                ) / (indicators.bb_upper - indicators.bb_lower)

            self._calculations_performed += 1
            return indicators

        except Exception as e:
            logger.error(
                f"Error calculating indicators for {symbol} {timeframe}: {e}",
                exc_info=True,
            )
            return None

    async def _write_to_database(self, indicators: TechnicalIndicators):
        """Write indicators to the database"""
        try:
            async with self.db_adapter.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO technical_indicators (
                        timestamp, symbol, timeframe,
                        ema_9, ema_21, ema_50, ema_200,
                        rsi_14,
                        macd_line, macd_signal, macd_histogram,
                        atr_14,
                        bb_upper, bb_middle, bb_lower, bb_width, bb_percent
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                    ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE SET
                        ema_9 = EXCLUDED.ema_9,
                        ema_21 = EXCLUDED.ema_21,
                        ema_50 = EXCLUDED.ema_50,
                        ema_200 = EXCLUDED.ema_200,
                        rsi_14 = EXCLUDED.rsi_14,
                        macd_line = EXCLUDED.macd_line,
                        macd_signal = EXCLUDED.macd_signal,
                        macd_histogram = EXCLUDED.macd_histogram,
                        atr_14 = EXCLUDED.atr_14,
                        bb_upper = EXCLUDED.bb_upper,
                        bb_middle = EXCLUDED.bb_middle,
                        bb_lower = EXCLUDED.bb_lower,
                        bb_width = EXCLUDED.bb_width,
                        bb_percent = EXCLUDED.bb_percent
                    """,
                    indicators.timestamp,
                    indicators.symbol,
                    indicators.timeframe.value,
                    indicators.ema_9,
                    indicators.ema_21,
                    indicators.ema_50,
                    indicators.ema_200,
                    indicators.rsi_14,
                    indicators.macd_line,
                    indicators.macd_signal,
                    indicators.macd_histogram,
                    indicators.atr_14,
                    indicators.bb_upper,
                    indicators.bb_middle,
                    indicators.bb_lower,
                    indicators.bb_width,
                    indicators.bb_percent,
                )

                self._db_writes += 1
                logger.debug(
                    f"Wrote indicators for {indicators.symbol} {indicators.timeframe} at {indicators.timestamp}"
                )

        except Exception as e:
            logger.error(f"Error writing indicators to database: {e}", exc_info=True)

    async def _publish_features_event(self, indicators: TechnicalIndicators):
        """Publish a features calculated event"""
        try:
            event = FeaturesCalculatedEvent(
                timestamp=datetime.utcnow(),
                symbol=indicators.symbol,
                timeframe=indicators.timeframe,
                features=indicators,
            )

            await self._event_bus.publish(event, priority=5)
            logger.debug(
                f"Published features event for {indicators.symbol} {indicators.timeframe}"
            )

        except Exception as e:
            logger.error(f"Error publishing features event: {e}", exc_info=True)

    async def process_historical_candles(
        self, symbol: str, timeframe: TimeFrame, candles: List[Candle]
    ):
        """
        Process a batch of historical candles (e.g., from DB tail).

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            candles: List of candles in chronological order
        """
        try:
            # Sort to ensure chronological order
            sorted_candles = sorted(candles, key=lambda c: c.open_time)

            logger.info(
                f"Processing {len(sorted_candles)} historical candles for {symbol} {timeframe}"
            )

            for candle in sorted_candles:
                await self.process_candle(candle)

        except Exception as e:
            logger.error(f"Error processing historical candles: {e}", exc_info=True)

    def get_buffer_stats(self) -> Dict:
        """Get statistics about the feature engine"""
        stats = {
            "buffer_stats": {},
            "calculations_performed": self._calculations_performed,
            "db_writes": self._db_writes,
            "running": self._running,
        }

        for symbol in self._candle_buffers:
            stats["buffer_stats"][symbol] = {}
            for timeframe in self._candle_buffers[symbol]:
                buffer = self._candle_buffers[symbol][timeframe]
                processed = self._processed[symbol][timeframe]
                stats["buffer_stats"][symbol][timeframe.value] = {
                    "buffer_size": len(buffer),
                    "processed_count": len(processed),
                    "oldest_candle": (
                        buffer[0].open_time.isoformat() if buffer else None
                    ),
                    "newest_candle": (
                        buffer[-1].close_time.isoformat() if buffer else None
                    ),
                }

        return stats
