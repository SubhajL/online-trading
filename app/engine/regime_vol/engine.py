"""
Market Regime and Volatility Analyzer

Classifies market into TREND/RANGE/SHOCK regimes using:
- ATR percentiles
- Bollinger Band width
- ADX percentiles
"""

from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import logging
from typing import Any

from ..bus import get_event_bus
from ..models import (
    BaseEvent,
    Candle,
    EventType,
    FeaturesCalculatedEvent,
    TechnicalIndicators,
    TimeFrame,
)

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification."""

    TREND = "TREND"
    RANGE = "RANGE"
    SHOCK = "SHOCK"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"


def classify_regime(
    atr_percentile: Decimal,
    bb_width_percentile: Decimal,
    adx_percentile: Decimal,
    config: dict[str, Any],
) -> MarketRegime:
    """Main classifier returning TREND/RANGE/SHOCK."""
    # Extract thresholds
    trend_thresh = config["trend_thresholds"]
    range_thresh = config["range_thresholds"]
    shock_thresh = config["shock_thresholds"]

    # Check for SHOCK first (highest priority)
    if (
        atr_percentile >= shock_thresh["atr_percentile_min"]
        and bb_width_percentile >= shock_thresh["bb_width_min"]
    ):
        return MarketRegime.SHOCK

    # Check for TREND
    if (
        adx_percentile >= trend_thresh["adx_min"]
        and bb_width_percentile <= trend_thresh["bb_width_max"]
    ):
        return MarketRegime.TREND

    # Check for RANGE
    if (
        adx_percentile <= range_thresh["adx_max"]
        and atr_percentile <= range_thresh["atr_percentile_max"]
    ):
        return MarketRegime.RANGE

    # Default to RANGE for ambiguous cases
    return MarketRegime.RANGE


def calculate_volatility_metrics(
    candles: list[Any],
    lookback_period: int,
) -> dict[str, Decimal]:
    """Compute ATR, BB-width, ADX percentiles over lookback period."""
    lookback_period = min(lookback_period, len(candles))

    # Calculate ATR
    atr_values = calculate_atr_series(candles, 14)
    if atr_values:
        # Calculate percentile based on historical distribution
        atr_normalized = [
            float(atr / candles[i]["close"])
            for i, atr in enumerate(atr_values[-lookback_period:])
        ]
        current_atr_norm = atr_normalized[-1] if atr_normalized else 0
        atr_percentile = Decimal(
            str(calculate_percentile(atr_normalized, current_atr_norm)),
        )
    else:
        atr_percentile = Decimal(50)

    # Calculate BB width
    bb_width_values = calculate_bb_width_series(candles, 20)
    if bb_width_values:
        bb_width_normalized = [float(w) for w in bb_width_values[-lookback_period:]]
        current_bb_width = bb_width_normalized[-1] if bb_width_normalized else 0
        bb_width_percentile = Decimal(
            str(calculate_percentile(bb_width_normalized, current_bb_width)),
        )
    else:
        bb_width_percentile = Decimal(50)

    # Calculate ADX
    adx_values = calculate_adx_series(candles, 14)
    if adx_values:
        adx_list = [float(adx) for adx in adx_values[-lookback_period:]]
        current_adx = adx_list[-1] if adx_list else 0
        adx_percentile = Decimal(str(calculate_percentile(adx_list, current_adx)))
    else:
        adx_percentile = Decimal(50)

    return {
        "atr_percentile": atr_percentile,
        "bb_width_percentile": bb_width_percentile,
        "adx_percentile": adx_percentile,
    }


def calculate_atr_series(candles: list[Any], period: int = 14) -> list[Decimal]:
    """Calculate ATR series."""
    if len(candles) < 2:
        return []

    atr_values = []
    tr_values = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]

        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)

        if len(tr_values) >= period:
            atr = sum(tr_values[-period:]) / period
            atr_values.append(atr)

    return atr_values


def calculate_bb_width_series(candles: list[Any], period: int = 20) -> list[Decimal]:
    """Calculate Bollinger Band width series."""
    if len(candles) < period:
        return []

    bb_width_values = []
    closes = [c["close"] for c in candles]

    for i in range(period - 1, len(candles)):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std_dev = variance ** Decimal("0.5")
        bb_width = (std_dev * 2) / mean if mean > 0 else Decimal(0)
        bb_width_values.append(bb_width)

    return bb_width_values


def calculate_adx_series(candles: list[Any], period: int = 14) -> list[Decimal]:
    """Calculate ADX series (simplified)."""
    if len(candles) < period + 1:
        return []

    adx_values = []

    # Simplified ADX based on price volatility
    for i in range(period, len(candles)):
        window = candles[i - period + 1 : i + 1]
        price_changes = []

        for j in range(1, len(window)):
            change = (
                abs(window[j]["close"] - window[j - 1]["close"])
                / window[j - 1]["close"]
            )
            price_changes.append(float(change))

        if price_changes:
            # Convert volatility to ADX-like scale (0-100)
            avg_change = sum(price_changes) / len(price_changes)
            adx = min(100, avg_change * 1000)  # Scale to 0-100
            adx_values.append(Decimal(str(adx)))

    return adx_values


def calculate_percentile(values: list[float], current_value: float) -> float:
    """Calculate percentile of current value in historical distribution."""
    if not values:
        return 50.0

    sorted_values = sorted(values)
    count_below = sum(1 for v in sorted_values if v < current_value)
    percentile = (count_below / len(values)) * 100
    return min(100, max(0, percentile))


def determine_regime(
    metrics: dict[str, Decimal],
    thresholds: dict[str, Any],
) -> MarketRegime:
    """Logic to map percentiles to regime."""
    # Check SHOCK conditions first
    if (
        metrics["atr_percentile"] >= thresholds["shock"]["atr_min"]
        and metrics["bb_width_percentile"] >= thresholds["shock"]["bb_width_min"]
    ):
        return MarketRegime.SHOCK

    # Check TREND conditions
    if (
        metrics["adx_percentile"] >= thresholds["trend"]["adx_min"]
        and metrics["bb_width_percentile"] <= thresholds["trend"]["bb_width_max"]
    ):
        return MarketRegime.TREND

    # Check RANGE conditions
    if (
        metrics["adx_percentile"] <= thresholds["range"]["adx_max"]
        and metrics["atr_percentile"] <= thresholds["range"]["atr_max"]
    ):
        return MarketRegime.RANGE

    # Default to RANGE
    return MarketRegime.RANGE


async def emit_regime_event(
    symbol: str,
    timeframe: str,
    regime: MarketRegime,
    metrics: dict[str, Decimal],
    event_bus: Any,
) -> None:
    """Publish regime classification for downstream modules."""
    try:
        event = BaseEvent(
            event_type=EventType.REGIME_UPDATE,
            timestamp=datetime.now(UTC),
            symbol=symbol,
            timeframe=TimeFrame(timeframe),
            metadata={
                "regime": regime.value,
                "metrics": {
                    "atr_percentile": str(metrics["atr_percentile"]),
                    "bb_width_percentile": str(metrics["bb_width_percentile"]),
                    "adx_percentile": str(metrics["adx_percentile"]),
                },
            },
        )

        await event_bus.publish(event, priority=7)
        logger.info(f"Published regime update for {symbol}: {regime.value}")

    except Exception as e:
        logger.error(f"Error emitting regime event: {e}", exc_info=True)


class RegimeVolEngine:
    """Market regime and volatility classification engine."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.event_bus = get_event_bus()
        self._running = False
        self._regime_cache: dict[str, MarketRegime] = {}
        self._subscription_ids: list[str] = []

        # Data storage
        self._candle_history: dict[str, deque[Candle]] = {}
        self._features_history: dict[str, deque[TechnicalIndicators]] = {}
        self._regime_history: dict[str, deque[tuple[datetime, MarketRegime]]] = {}

        # Configuration
        regime_config = config.get("regime", {})
        self.lookback_periods = regime_config.get("atr_lookback_periods", 100)
        self.regime_lookback_bars = regime_config.get("regime_lookback_bars", 50)
        self.regime_thresholds = {
            "trend": regime_config.get("trend_thresholds", {}),
            "range": regime_config.get("range_thresholds", {}),
            "shock": regime_config.get("shock_thresholds", {}),
        }

    async def start(self) -> None:
        """Start the regime engine."""
        if self._running:
            logger.warning("RegimeVolEngine already running")
            return

        self._running = True

        # Subscribe to features events
        sub_id = await self.event_bus.subscribe(
            subscriber_id="regime_engine_features",
            handler=self._process_features_event,
            event_types=[EventType.FEATURES_CALCULATED],
            priority=4,
        )
        self._subscription_ids.append(sub_id)

        logger.info("RegimeVolEngine started")

    async def stop(self) -> None:
        """Stop the regime engine."""
        if not self._running:
            return

        self._running = False

        # Unsubscribe from all events
        for sub_id in self._subscription_ids:
            await self.event_bus.unsubscribe(sub_id)

        self._subscription_ids.clear()
        logger.info("RegimeVolEngine stopped")

    async def _process_features_event(self, event: FeaturesCalculatedEvent) -> None:
        """Process incoming feature events to classify regime."""
        try:
            features = event.features
            key = f"{features.symbol}:{features.timeframe.value}"

            # Store features
            if key not in self._features_history:
                self._features_history[key] = deque(maxlen=self.lookback_periods)
            self._features_history[key].append(features)

            # Get candles for this symbol/timeframe
            candles = list(self._candle_history.get(key, []))
            if len(candles) < self.regime_lookback_bars:
                return

            # Calculate percentiles
            metrics = await self._calculate_percentiles(
                features.symbol, features.timeframe.value,
            )

            # Classify regime
            regime = classify_regime(
                atr_percentile=metrics["atr_percentile"],
                bb_width_percentile=metrics["bb_width_percentile"],
                adx_percentile=metrics["adx_percentile"],
                config=self.config,
            )

            # Cache regime
            self._regime_cache[key] = regime

            # Store regime history
            if key not in self._regime_history:
                self._regime_history[key] = deque(maxlen=1000)
            self._regime_history[key].append((datetime.now(UTC), regime))

            # Emit regime event
            await emit_regime_event(
                symbol=features.symbol,
                timeframe=features.timeframe.value,
                regime=regime,
                metrics=metrics,
                event_bus=self.event_bus,
            )

        except Exception as e:
            logger.error(f"Error processing features event: {e}", exc_info=True)

    async def _calculate_percentiles(
        self,
        symbol: str,
        timeframe: str,
    ) -> dict[str, Decimal]:
        """Calculate volatility metric percentiles."""
        key = f"{symbol}:{timeframe}"
        candles = list(self._candle_history.get(key, []))

        if not candles:
            return {
                "atr_percentile": Decimal(50),
                "bb_width_percentile": Decimal(50),
                "adx_percentile": Decimal(50),
            }

        # Convert candles to dict format for calculation
        candle_dicts = [
            {
                "high": c.high_price,
                "low": c.low_price,
                "close": c.close_price,
                "open": c.open_price,
                "volume": c.volume,
            }
            for c in candles
        ]

        return calculate_volatility_metrics(
            candles=candle_dicts, lookback_period=self.lookback_periods,
        )

    def get_current_regime(self, symbol: str, timeframe: str) -> MarketRegime | None:
        """Get current regime for symbol/timeframe."""
        key = f"{symbol}:{timeframe}"
        return self._regime_cache.get(key)

    async def process_candle_update(self, candle: Candle) -> None:
        """Store candle data for regime calculations."""
        key = f"{candle.symbol}:{candle.timeframe.value}"
        if key not in self._candle_history:
            self._candle_history[key] = deque(maxlen=self.lookback_periods * 2)
        self._candle_history[key].append(candle)
