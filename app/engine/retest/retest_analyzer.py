"""
Retest Analyzer

Analyzes price retests of key levels, zones, and support/resistance areas.
Generates signals when price successfully retests important levels.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from collections import deque

from ..models import (
    BaseEvent,
    Candle,
    CandleUpdateEvent,
    RetestSignal,
    RetestSignalEvent,
    SupplyDemandZone,
    PivotPoint,
    TimeFrame,
)
from ..bus import get_event_bus


logger = logging.getLogger(__name__)


class RetestAnalyzer:
    """
    Analyzes price retests and generates signals.

    Features:
    - Support/resistance retest detection
    - Zone retest analysis
    - Volume confirmation
    - Success probability calculation
    """

    def __init__(
        self,
        retest_tolerance: float = 0.002,  # 0.2% tolerance
        min_volume_ratio: float = 1.2,
        min_time_between_tests: int = 300,  # 5 minutes
    ):
        self.retest_tolerance = retest_tolerance
        self.min_volume_ratio = min_volume_ratio
        self.min_time_between_tests = min_time_between_tests

        # Track levels and zones
        self._key_levels: Dict[str, List[Dict]] = {}  # symbol -> levels
        self._recent_candles: Dict[str, deque] = {}  # symbol -> candles

        # Event bus
        self._event_bus = get_event_bus()
        self._running = False
        self._subscription_id: Optional[str] = None

        logger.info("RetestAnalyzer initialized")

    async def start(self):
        """Start the retest analyzer"""
        if self._running:
            return

        self._running = True

        # Subscribe to candle updates
        self._subscription_id = await self._event_bus.subscribe(
            subscriber_id="retest_analyzer",
            handler=self._handle_candle_update,
            event_types=[BaseEvent.EventType.CANDLE_UPDATE],
            priority=3,
        )

        logger.info("RetestAnalyzer started")

    async def stop(self):
        """Stop the retest analyzer"""
        if not self._running:
            return

        self._running = False

        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)

        logger.info("RetestAnalyzer stopped")

    async def _handle_candle_update(self, event: CandleUpdateEvent):
        """Handle candle updates for retest analysis"""
        try:
            candle = event.candle
            symbol = candle.symbol

            # Store recent candles
            if symbol not in self._recent_candles:
                self._recent_candles[symbol] = deque(maxlen=50)

            self._recent_candles[symbol].append(candle)

            # Analyze for retests
            await self._analyze_retests(symbol, candle)

        except Exception as e:
            logger.error(f"Error handling candle update: {e}")

    async def _analyze_retests(self, symbol: str, current_candle: Candle):
        """Analyze current candle for retest opportunities"""
        try:
            if symbol not in self._key_levels:
                return

            levels = self._key_levels[symbol]
            recent_candles = list(self._recent_candles.get(symbol, []))

            if len(recent_candles) < 5:
                return

            for level in levels:
                retest_signal = self._check_level_retest(
                    level, current_candle, recent_candles
                )

                if retest_signal:
                    await self._publish_retest_signal(retest_signal)

        except Exception as e:
            logger.error(f"Error analyzing retests: {e}")

    def _check_level_retest(
        self, level: Dict, current_candle: Candle, recent_candles: List[Candle]
    ) -> Optional[RetestSignal]:
        """Check if current price action represents a valid retest"""
        try:
            level_price = level["price"]
            level_type = level["type"]  # 'support' or 'resistance'

            # Check if price is near the level
            price_distance = abs(current_candle.close_price - level_price) / level_price
            if price_distance > self.retest_tolerance:
                return None

            # Check for proper retest behavior
            if level_type == "support":
                # For support retest, look for bounce
                if (
                    current_candle.low_price <= level_price
                    and current_candle.close_price > level_price
                ):
                    volume_confirmation = self._check_volume_confirmation(
                        current_candle, recent_candles
                    )

                    success_probability = self._calculate_success_probability(
                        level, current_candle, recent_candles, "support"
                    )

                    confluence_factors = self._get_confluence_factors(
                        level, current_candle, recent_candles
                    )

                    return RetestSignal(
                        symbol=current_candle.symbol,
                        timeframe=current_candle.timeframe,
                        timestamp=current_candle.close_time,
                        level_price=level_price,
                        retest_type="support_retest",
                        success_probability=success_probability,
                        volume_confirmation=volume_confirmation,
                        confluence_factors=confluence_factors,
                    )

            elif level_type == "resistance":
                # For resistance retest, look for rejection
                if (
                    current_candle.high_price >= level_price
                    and current_candle.close_price < level_price
                ):
                    volume_confirmation = self._check_volume_confirmation(
                        current_candle, recent_candles
                    )

                    success_probability = self._calculate_success_probability(
                        level, current_candle, recent_candles, "resistance"
                    )

                    confluence_factors = self._get_confluence_factors(
                        level, current_candle, recent_candles
                    )

                    return RetestSignal(
                        symbol=current_candle.symbol,
                        timeframe=current_candle.timeframe,
                        timestamp=current_candle.close_time,
                        level_price=level_price,
                        retest_type="resistance_retest",
                        success_probability=success_probability,
                        volume_confirmation=volume_confirmation,
                        confluence_factors=confluence_factors,
                    )

            return None

        except Exception as e:
            logger.error(f"Error checking level retest: {e}")
            return None

    def _check_volume_confirmation(
        self, current_candle: Candle, recent_candles: List[Candle]
    ) -> bool:
        """Check if volume confirms the retest"""
        try:
            if len(recent_candles) < 5:
                return False

            # Calculate average volume
            avg_volume = sum(c.volume for c in recent_candles[-5:]) / 5

            # Check if current volume is above average
            volume_ratio = float(current_candle.volume / avg_volume)

            return volume_ratio >= self.min_volume_ratio

        except Exception as e:
            logger.error(f"Error checking volume confirmation: {e}")
            return False

    def _calculate_success_probability(
        self,
        level: Dict,
        current_candle: Candle,
        recent_candles: List[Candle],
        level_type: str,
    ) -> Decimal:
        """Calculate probability of successful retest"""
        try:
            base_probability = Decimal("0.6")  # Base 60% probability

            # Adjust based on level strength
            level_strength = level.get("strength", 5)
            strength_adjustment = (level_strength - 5) * Decimal("0.05")
            base_probability += strength_adjustment

            # Adjust based on number of previous tests
            previous_tests = level.get("test_count", 0)
            if previous_tests > 2:
                base_probability -= Decimal("0.1")  # Weaker after multiple tests

            # Adjust based on time since level creation
            level_age_hours = (
                current_candle.close_time - level["created_at"]
            ).total_seconds() / 3600
            if level_age_hours < 24:
                base_probability += Decimal("0.1")  # Fresh levels more reliable

            # Adjust based on market volatility
            volatility = self._calculate_recent_volatility(recent_candles)
            if volatility > Decimal("0.03"):  # High volatility
                base_probability -= Decimal("0.1")

            # Ensure probability stays within bounds
            return max(Decimal("0.1"), min(Decimal("0.9"), base_probability))

        except Exception as e:
            logger.error(f"Error calculating success probability: {e}")
            return Decimal("0.5")

    def _calculate_recent_volatility(self, candles: List[Candle]) -> Decimal:
        """Calculate recent volatility measure"""
        try:
            if len(candles) < 2:
                return Decimal("0")

            # Simple volatility based on price range
            recent = candles[-5:] if len(candles) >= 5 else candles
            ranges = []

            for candle in recent:
                price_range = (
                    candle.high_price - candle.low_price
                ) / candle.close_price
                ranges.append(price_range)

            return sum(ranges) / len(ranges)

        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            return Decimal("0.02")

    def _get_confluence_factors(
        self, level: Dict, current_candle: Candle, recent_candles: List[Candle]
    ) -> List[str]:
        """Get confluence factors supporting the retest"""
        factors = []

        try:
            # Volume confluence
            if self._check_volume_confirmation(current_candle, recent_candles):
                factors.append("volume_confirmation")

            # Time-based confluence
            level_age_hours = (
                current_candle.close_time - level["created_at"]
            ).total_seconds() / 3600
            if level_age_hours < 48:  # Fresh level
                factors.append("fresh_level")

            # Wick confirmation
            if level["type"] == "support":
                if (
                    current_candle.low_price
                    < level["price"]
                    < current_candle.close_price
                ):
                    factors.append("wick_rejection")
            else:  # resistance
                if (
                    current_candle.close_price
                    < level["price"]
                    < current_candle.high_price
                ):
                    factors.append("wick_rejection")

            # Multiple timeframe confluence (simplified)
            factors.append("multi_timeframe")

        except Exception as e:
            logger.error(f"Error getting confluence factors: {e}")

        return factors

    async def _publish_retest_signal(self, signal: RetestSignal):
        """Publish retest signal event"""
        try:
            event = RetestSignalEvent(
                timestamp=datetime.utcnow(),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            )

            await self._event_bus.publish(event, priority=6)

            logger.info(
                f"Published retest signal: {signal.symbol} {signal.retest_type} "
                f"at {signal.level_price} (probability: {signal.success_probability})"
            )

        except Exception as e:
            logger.error(f"Error publishing retest signal: {e}")

    def add_key_level(
        self,
        symbol: str,
        price: Decimal,
        level_type: str,
        strength: int = 5,
        created_at: Optional[datetime] = None,
    ):
        """Add a key level to track for retests"""
        try:
            if symbol not in self._key_levels:
                self._key_levels[symbol] = []

            level = {
                "price": price,
                "type": level_type,  # 'support' or 'resistance'
                "strength": strength,
                "created_at": created_at or datetime.utcnow(),
                "test_count": 0,
            }

            self._key_levels[symbol].append(level)

            # Keep only recent levels
            if len(self._key_levels[symbol]) > 20:
                self._key_levels[symbol] = self._key_levels[symbol][-20:]

            logger.debug(f"Added key level: {symbol} {level_type} at {price}")

        except Exception as e:
            logger.error(f"Error adding key level: {e}")

    def add_zone_for_retest(self, zone: SupplyDemandZone):
        """Add a supply/demand zone to track for retests"""
        try:
            symbol = zone.symbol
            zone_center = (zone.top_price + zone.bottom_price) / 2

            level_type = (
                "resistance"
                if zone.zone_type.value in ["SUPPLY", "ORDER_BLOCK_BEARISH"]
                else "support"
            )

            self.add_key_level(
                symbol=symbol,
                price=zone_center,
                level_type=level_type,
                strength=zone.strength,
                created_at=zone.created_at,
            )

        except Exception as e:
            logger.error(f"Error adding zone for retest: {e}")

    def add_pivot_levels(self, pivots: List[PivotPoint]):
        """Add pivot points as key levels to track"""
        try:
            for pivot in pivots:
                level_type = "resistance" if pivot.is_high else "support"

                self.add_key_level(
                    symbol=pivot.symbol,
                    price=pivot.price,
                    level_type=level_type,
                    strength=pivot.strength,
                    created_at=pivot.timestamp,
                )

        except Exception as e:
            logger.error(f"Error adding pivot levels: {e}")

    async def health_check(self) -> Dict:
        """Health check for retest analyzer"""
        return {
            "running": self._running,
            "tracked_symbols": len(self._key_levels),
            "total_levels": sum(len(levels) for levels in self._key_levels.values()),
            "recent_candles": sum(
                len(candles) for candles in self._recent_candles.values()
            ),
        }
