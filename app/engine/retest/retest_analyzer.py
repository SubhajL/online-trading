"""
Retest Analyzer

Analyzes price retests of key levels, zones, and support/resistance areas.
Generates signals when price successfully retests important levels.
"""

from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any

from app.engine.bus import get_event_bus
from app.engine.models import (
    Candle,
    CandleUpdateEvent,
    EventType,
    PivotPoint,
    RetestSignal,
    RetestSignalEvent,
    SupplyDemandZone,
)

logger = logging.getLogger(__name__)

MAX_RECENT_CANDLES = 50
MIN_RECENT_CANDLES = 5
MAX_LEVELS_PER_SYMBOL = 20
MAX_PREVIOUS_TESTS_BEFORE_PENALTY = 2
FRESH_LEVEL_MAX_AGE_HOURS = 24
FRESH_LEVEL_CONFLUENCE_HOURS = 48
MIN_VOLATILITY_CANDLES = 2
VOLATILITY_WINDOW = 5


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
    ) -> None:
        self.retest_tolerance = retest_tolerance
        self.min_volume_ratio = min_volume_ratio
        self.min_time_between_tests = min_time_between_tests

        # Track levels and zones
        self._key_levels: dict[str, list[dict[Any, Any]]] = {}  # symbol -> levels
        self._recent_candles: dict[str, deque[Any]] = {}  # symbol -> candles

        # Event bus
        self._event_bus = get_event_bus()
        self._running = False
        self._subscription_id: str | None = None

        logger.info("RetestAnalyzer initialized")

    async def start(self) -> None:
        """Start the retest analyzer"""
        if self._running:
            return

        self._running = True

        # Subscribe to candle updates
        self._subscription_id = await self._event_bus.subscribe(
            subscriber_id="retest_analyzer",
            handler=self._handle_candle_update,
            event_types=[EventType.CANDLE_UPDATE],
            priority=3,
        )

        logger.info("RetestAnalyzer started")

    async def stop(self) -> None:
        """Stop the retest analyzer"""
        if not self._running:
            return

        self._running = False

        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)

        logger.info("RetestAnalyzer stopped")

    async def _handle_candle_update(self, event: CandleUpdateEvent) -> None:
        """Handle candle updates for retest analysis"""
        try:
            candle = event.candle
            symbol = candle.symbol

            # Store recent candles
            if symbol not in self._recent_candles:
                self._recent_candles[symbol] = deque(maxlen=MAX_RECENT_CANDLES)

            self._recent_candles[symbol].append(candle)

            # Analyze for retests
            await self._analyze_retests(symbol, candle)

        except Exception:
            logger.exception("Error handling candle update")

    async def _analyze_retests(self, symbol: str, current_candle: Candle) -> None:
        """Analyze current candle for retest opportunities"""
        try:
            if symbol not in self._key_levels:
                return

            levels = self._key_levels[symbol]
            recent_candles = list(self._recent_candles.get(symbol, []))

            if len(recent_candles) < MIN_RECENT_CANDLES:
                return

            for level in levels:
                retest_signal = self._check_level_retest(
                    level,
                    current_candle,
                    recent_candles,
                )

                if retest_signal:
                    await self._publish_retest_signal(retest_signal)

        except Exception:
            logger.exception("Error analyzing retests")

    def _check_level_retest(
        self,
        level: dict[Any, Any],
        current_candle: Candle,
        recent_candles: list[Candle],
    ) -> RetestSignal | None:
        """Check if current price action represents a valid retest"""
        try:
            level_price = level["price"]
            level_type = level["type"]  # 'support' or 'resistance'

            # Check if price is near the level
            price_distance = abs(current_candle.close_price - level_price) / level_price
            if price_distance > self.retest_tolerance:
                return None

            # Check for proper retest behavior
            if level_type == "support" and (
                current_candle.low_price <= level_price and current_candle.close_price > level_price
            ):
                volume_confirmation = self._check_volume_confirmation(
                    current_candle,
                    recent_candles,
                )

                success_probability = self._calculate_success_probability(
                    level,
                    current_candle,
                    recent_candles,
                )

                confluence_factors = self._get_confluence_factors(
                    level,
                    current_candle,
                    recent_candles,
                )

                stop_distance = level_price * Decimal("0.002")
                return RetestSignal(
                    symbol=current_candle.symbol,
                    timeframe=current_candle.timeframe,
                    timestamp=current_candle.close_time,
                    level_price=level_price,
                    direction="BUY",
                    stop_loss=level_price - stop_distance,
                    take_profit=level_price + (stop_distance * Decimal("1.5")),
                    retest_type="support_retest",
                    success_probability=success_probability,
                    volume_confirmation=volume_confirmation,
                    confluence_factors=confluence_factors,
                )

            if level_type == "resistance" and (
                current_candle.high_price >= level_price
                and current_candle.close_price < level_price
            ):
                volume_confirmation = self._check_volume_confirmation(
                    current_candle,
                    recent_candles,
                )

                success_probability = self._calculate_success_probability(
                    level,
                    current_candle,
                    recent_candles,
                )

                confluence_factors = self._get_confluence_factors(
                    level,
                    current_candle,
                    recent_candles,
                )

                stop_distance = level_price * Decimal("0.002")
                return RetestSignal(
                    symbol=current_candle.symbol,
                    timeframe=current_candle.timeframe,
                    timestamp=current_candle.close_time,
                    level_price=level_price,
                    direction="SELL",
                    stop_loss=level_price + stop_distance,
                    take_profit=level_price - (stop_distance * Decimal("1.5")),
                    retest_type="resistance_retest",
                    success_probability=success_probability,
                    volume_confirmation=volume_confirmation,
                    confluence_factors=confluence_factors,
                )

        except Exception:
            logger.exception("Error checking level retest")
        return None

    def _check_volume_confirmation(
        self,
        current_candle: Candle,
        recent_candles: list[Candle],
    ) -> bool:
        """Check if volume confirms the retest"""
        try:
            if len(recent_candles) < MIN_RECENT_CANDLES:
                return False

            # Calculate average volume
            avg_volume = sum(c.volume for c in recent_candles[-5:]) / 5

            # Check if current volume is above average
            volume_ratio = float(current_candle.volume / Decimal(str(avg_volume)))

            return volume_ratio >= self.min_volume_ratio

        except Exception:
            logger.exception("Error checking volume confirmation")
            return False
        else:
            return volume_ratio >= self.min_volume_ratio

    def _calculate_success_probability(
        self,
        level: dict[Any, Any],
        current_candle: Candle,
        recent_candles: list[Candle],
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
            if previous_tests > MAX_PREVIOUS_TESTS_BEFORE_PENALTY:
                base_probability -= Decimal("0.1")  # Weaker after multiple tests

            # Adjust based on time since level creation
            level_age_hours = (
                current_candle.close_time - level["created_at"]
            ).total_seconds() / 3600
            if level_age_hours < FRESH_LEVEL_MAX_AGE_HOURS:
                base_probability += Decimal("0.1")  # Fresh levels more reliable

            # Adjust based on market volatility
            volatility = self._calculate_recent_volatility(recent_candles)
            if volatility > Decimal("0.03"):  # High volatility
                base_probability -= Decimal("0.1")

            # Ensure probability stays within bounds
            return max(Decimal("0.1"), min(Decimal("0.9"), base_probability))

        except Exception:
            logger.exception("Error calculating success probability")
            return Decimal("0.5")

    def _calculate_recent_volatility(self, candles: list[Candle]) -> Decimal:
        """Calculate recent volatility measure"""
        try:
            if len(candles) < MIN_VOLATILITY_CANDLES:
                return Decimal(0)

            # Simple volatility based on price range
            recent = candles[-VOLATILITY_WINDOW:] if len(candles) >= VOLATILITY_WINDOW else candles
            ranges = []

            for candle in recent:
                price_range = (candle.high_price - candle.low_price) / candle.close_price
                ranges.append(price_range)

            return Decimal(str(sum(ranges) / len(ranges)))

        except Exception:
            logger.exception("Error calculating volatility")
            return Decimal("0.02")

    def _get_confluence_factors(
        self,
        level: dict[Any, Any],
        current_candle: Candle,
        recent_candles: list[Candle],
    ) -> list[str]:
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
            if level_age_hours < FRESH_LEVEL_CONFLUENCE_HOURS:  # Fresh level
                factors.append("fresh_level")

            # Wick confirmation
            if level["type"] == "support":
                if current_candle.low_price < level["price"] < current_candle.close_price:
                    factors.append("wick_rejection")
            elif current_candle.close_price < level["price"] < current_candle.high_price:
                factors.append("wick_rejection")

            # Multiple timeframe confluence (simplified)
            factors.append("multi_timeframe")

        except Exception:
            logger.exception("Error getting confluence factors")

        return factors

    async def _publish_retest_signal(self, signal: RetestSignal) -> None:
        """Publish retest signal event"""
        try:
            event = RetestSignalEvent(
                timestamp=datetime.now(UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            )

            await self._event_bus.publish(event, priority=6)

            logger.info(
                "Published retest signal: %s %s at %s (probability: %s)",
                signal.symbol,
                signal.retest_type,
                signal.level_price,
                signal.success_probability,
            )

        except Exception:
            logger.exception("Error publishing retest signal")

    def add_key_level(
        self,
        symbol: str,
        price: Decimal,
        level_type: str,
        strength: int = 5,
        created_at: datetime | None = None,
    ) -> None:
        """Add a key level to track for retests"""
        try:
            if symbol not in self._key_levels:
                self._key_levels[symbol] = []

            level = {
                "price": price,
                "type": level_type,  # 'support' or 'resistance'
                "strength": strength,
                "created_at": created_at or datetime.now(UTC),
                "test_count": 0,
            }

            self._key_levels[symbol].append(level)

            # Keep only recent levels
            if len(self._key_levels[symbol]) > MAX_LEVELS_PER_SYMBOL:
                self._key_levels[symbol] = self._key_levels[symbol][-MAX_LEVELS_PER_SYMBOL:]

            logger.debug("Added key level: %s %s at %s", symbol, level_type, price)

        except Exception:
            logger.exception("Error adding key level")

    def add_zone_for_retest(self, zone: SupplyDemandZone) -> None:
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

        except Exception:
            logger.exception("Error adding zone for retest")

    def add_pivot_levels(self, pivots: list[PivotPoint]) -> None:
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

        except Exception:
            logger.exception("Error adding pivot levels")

    async def health_check(self) -> dict[Any, Any]:
        """Health check for retest analyzer"""
        return {
            "running": self._running,
            "tracked_symbols": len(self._key_levels),
            "total_levels": sum(len(levels) for levels in self._key_levels.values()),
            "recent_candles": sum(len(candles) for candles in self._recent_candles.values()),
        }
