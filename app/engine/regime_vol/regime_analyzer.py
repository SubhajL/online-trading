"""
Market Regime and Volatility Analyzer

Analyzes market regime (trending/ranging) and volatility conditions
to provide context for trading decisions.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from collections import deque

from ..types import (
    BaseEvent,
    Candle,
    CandleUpdateEvent,
    MarketRegime,
    TimeFrame,
    TechnicalIndicators,
    FeaturesCalculatedEvent,
)
from ..bus import get_event_bus


logger = logging.getLogger(__name__)


class RegimeVolatilityAnalyzer:
    """
    Analyzes market regime and volatility conditions.

    Features:
    - Trend/range regime detection
    - Volatility measurement and classification
    - Regime change detection
    - Multi-timeframe analysis
    """

    def __init__(
        self,
        lookback_periods: int = 20,
        volatility_threshold: float = 0.02,
        trend_threshold: float = 0.01,
    ):
        self.lookback_periods = lookback_periods
        self.volatility_threshold = volatility_threshold
        self.trend_threshold = trend_threshold

        # Store market data
        self._candles: Dict[str, deque] = {}  # symbol_timeframe -> candles
        self._indicators: Dict[str, TechnicalIndicators] = {}

        # Current regime state
        self._current_regime: Dict[str, MarketRegime] = {}  # symbol_timeframe -> regime
        self._volatility_state: Dict[str, str] = (
            {}
        )  # symbol_timeframe -> volatility level

        # Event bus
        self._event_bus = get_event_bus()
        self._running = False
        self._subscription_ids: List[str] = []

        logger.info("RegimeVolatilityAnalyzer initialized")

    async def start(self):
        """Start the regime analyzer"""
        if self._running:
            return

        self._running = True

        # Subscribe to events
        subscriptions = [
            (
                "regime_candle_handler",
                self._handle_candle_update,
                [BaseEvent.EventType.CANDLE_UPDATE],
            ),
            (
                "regime_features_handler",
                self._handle_features_calculated,
                [BaseEvent.EventType.FEATURES_CALCULATED],
            ),
        ]

        for subscriber_id, handler, event_types in subscriptions:
            sub_id = await self._event_bus.subscribe(
                subscriber_id=subscriber_id,
                handler=handler,
                event_types=event_types,
                priority=3,
            )
            self._subscription_ids.append(sub_id)

        logger.info("RegimeVolatilityAnalyzer started")

    async def stop(self):
        """Stop the regime analyzer"""
        if not self._running:
            return

        self._running = False

        for sub_id in self._subscription_ids:
            await self._event_bus.unsubscribe(sub_id)
        self._subscription_ids.clear()

        logger.info("RegimeVolatilityAnalyzer stopped")

    async def _handle_candle_update(self, event: CandleUpdateEvent):
        """Handle candle updates"""
        try:
            candle = event.candle
            key = f"{candle.symbol}_{candle.timeframe.value}"

            # Store candle
            if key not in self._candles:
                self._candles[key] = deque(maxlen=self.lookback_periods * 2)

            self._candles[key].append(candle)

            # Analyze regime if we have enough data
            if len(self._candles[key]) >= self.lookback_periods:
                await self._analyze_regime(candle.symbol, candle.timeframe)

        except Exception as e:
            logger.error(f"Error handling candle update: {e}")

    async def _handle_features_calculated(self, event: FeaturesCalculatedEvent):
        """Handle features calculated events"""
        try:
            indicators = event.features
            key = f"{indicators.symbol}_{indicators.timeframe.value}"
            self._indicators[key] = indicators

        except Exception as e:
            logger.error(f"Error handling features calculated: {e}")

    async def _analyze_regime(self, symbol: str, timeframe: TimeFrame):
        """Analyze market regime for symbol and timeframe"""
        try:
            key = f"{symbol}_{timeframe.value}"
            candles = list(self._candles[key])

            if len(candles) < self.lookback_periods:
                return

            # Detect regime
            regime = self._detect_market_regime(candles)
            volatility_level = self._classify_volatility(candles)

            # Update state
            prev_regime = self._current_regime.get(key)
            self._current_regime[key] = regime
            self._volatility_state[key] = volatility_level

            # Log regime changes
            if prev_regime and prev_regime != regime:
                logger.info(
                    f"Regime change detected: {symbol} {timeframe.value} from {prev_regime.value} to {regime.value}"
                )

        except Exception as e:
            logger.error(f"Error analyzing regime: {e}")

    def _detect_market_regime(self, candles: List[Candle]) -> MarketRegime:
        """Detect market regime from price action"""
        try:
            recent_candles = candles[-self.lookback_periods :]

            # Calculate price movement metrics
            highs = [c.high_price for c in recent_candles]
            lows = [c.low_price for c in recent_candles]
            closes = [c.close_price for c in recent_candles]

            # Trend analysis
            price_change = (closes[-1] - closes[0]) / closes[0]
            trend_strength = abs(price_change)

            # Volatility analysis
            price_ranges = [(h - l) / c for h, l, c in zip(highs, lows, closes)]
            avg_volatility = sum(price_ranges) / len(price_ranges)

            # Higher highs and higher lows detection
            higher_highs = sum(
                1 for i in range(1, len(highs)) if highs[i] > highs[i - 1]
            )
            lower_lows = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i - 1])

            # Regime classification
            if trend_strength > self.trend_threshold:
                if price_change > 0:
                    return MarketRegime.TRENDING_UP
                else:
                    return MarketRegime.TRENDING_DOWN
            elif avg_volatility > self.volatility_threshold:
                return MarketRegime.VOLATILE
            else:
                if avg_volatility < self.volatility_threshold * 0.5:
                    return MarketRegime.LOW_VOLATILITY
                else:
                    return MarketRegime.RANGING

        except Exception as e:
            logger.error(f"Error detecting market regime: {e}")
            return MarketRegime.RANGING

    def _classify_volatility(self, candles: List[Candle]) -> str:
        """Classify volatility level"""
        try:
            recent_candles = candles[-self.lookback_periods :]

            # Calculate ATR-like volatility
            volatilities = []
            for i in range(1, len(recent_candles)):
                current = recent_candles[i]
                previous = recent_candles[i - 1]

                tr1 = current.high_price - current.low_price
                tr2 = abs(current.high_price - previous.close_price)
                tr3 = abs(current.low_price - previous.close_price)

                true_range = max(tr1, tr2, tr3)
                volatility = true_range / current.close_price
                volatilities.append(volatility)

            avg_volatility = sum(volatilities) / len(volatilities)

            # Classify
            if avg_volatility > self.volatility_threshold * 1.5:
                return "high"
            elif avg_volatility > self.volatility_threshold:
                return "medium"
            else:
                return "low"

        except Exception as e:
            logger.error(f"Error classifying volatility: {e}")
            return "medium"

    def get_regime(self, symbol: str, timeframe: TimeFrame) -> Optional[MarketRegime]:
        """Get current market regime for symbol and timeframe"""
        key = f"{symbol}_{timeframe.value}"
        return self._current_regime.get(key)

    def get_volatility_level(self, symbol: str, timeframe: TimeFrame) -> Optional[str]:
        """Get current volatility level"""
        key = f"{symbol}_{timeframe.value}"
        return self._volatility_state.get(key)

    def get_regime_confidence(self, symbol: str, timeframe: TimeFrame) -> Decimal:
        """Get confidence in current regime classification"""
        try:
            key = f"{symbol}_{timeframe.value}"
            candles = self._candles.get(key)

            if not candles or len(candles) < self.lookback_periods:
                return Decimal("0.5")

            recent_candles = list(candles)[-self.lookback_periods :]

            # Calculate regime stability (simplified)
            closes = [c.close_price for c in recent_candles]
            price_changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

            # Count directional consistency
            positive_changes = sum(1 for pc in price_changes if pc > 0)
            negative_changes = sum(1 for pc in price_changes if pc < 0)

            total_changes = len(price_changes)
            if total_changes == 0:
                return Decimal("0.5")

            # Higher consistency = higher confidence
            max_direction = max(positive_changes, negative_changes)
            consistency_ratio = max_direction / total_changes

            # Convert to confidence (0.5 to 1.0)
            confidence = Decimal("0.5") + (
                Decimal(str(consistency_ratio)) * Decimal("0.5")
            )

            return min(Decimal("1.0"), confidence)

        except Exception as e:
            logger.error(f"Error calculating regime confidence: {e}")
            return Decimal("0.5")

    def is_regime_change(self, symbol: str, timeframe: TimeFrame) -> bool:
        """Check if regime has recently changed"""
        # This would track regime changes over time
        # Simplified implementation
        return False

    async def health_check(self) -> Dict:
        """Health check for regime analyzer"""
        return {
            "running": self._running,
            "tracked_symbols": len(self._candles),
            "current_regimes": {
                key: regime.value for key, regime in self._current_regime.items()
            },
            "volatility_states": dict(self._volatility_state),
        }
