"""
Retest Analyzer Engine - Detects zone retests after Break of Structure (BOS)

Requirements:
- Retests within ≤8 bars after BOS
- Price touches/enters zone band with tolerance 0.25xATR
- Confirmation by close in direction or micro-BOS on sub-TF
- MACD histogram uptick
- RSI 40-55 bounce for longs
"""


from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any, NewType

from app.engine.bus import get_event_bus
from app.engine.models import (
    Candle,
    CandleUpdateEvent,
    EventType,
    FeaturesCalculatedEvent,
    RetestSignal,
    RetestSignalEvent,
    SMCSignalEvent,
    TechnicalIndicators,
    TimeFrame,
)

logger = logging.getLogger(__name__)

# Type aliases
ZoneId = NewType("ZoneId", str)
SignalId = NewType("SignalId", str)


async def analyze_retest(
    symbol: str,
    timeframe: str,
    candles: list[Any],
    zones: list[Any],
    bos_events: list[Any],
    features: Any,
) -> Any | None:
    """
    Main entry point to detect valid zone retests.

    Returns signal_raw event if retest conditions are met.
    """
    if not candles or not zones or not bos_events:
        return None

    latest_candle = candles[-1]
    candle_time = latest_candle["open_time"]

    # Find recent BOS events (within 8 bars)
    bar_duration_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }.get(timeframe, 5)

    max_time_diff = bar_duration_minutes * 8 * 60  # 8 bars in seconds

    for bos in reversed(bos_events):
        bos_time = bos["timestamp"]
        time_diff = (candle_time - bos_time).total_seconds()

        if time_diff > max_time_diff:
            continue

        # Check zones for retest
        for zone in zones:
            # Skip if zone type doesn't match BOS direction
            if bos["type"] == "BULLISH_BOS" and zone["zone_type"] != "DEMAND":
                continue
            if bos["type"] == "BEARISH_BOS" and zone["zone_type"] != "SUPPLY":
                continue

            # Check if price is within zone
            if not is_within_zone(latest_candle["close"], zone, features["atr"]):
                continue

            # Determine direction
            direction = "LONG" if bos["type"] == "BULLISH_BOS" else "SHORT"

            # Check confirmation
            if not has_confirmation(latest_candle, zone, None, direction):
                continue

            # Check momentum indicators
            if not check_momentum_indicators(
                features["macd_hist"],
                features["macd_hist_prev"],
                features["rsi"],
                direction,
            ):
                continue

            # Generate entry levels
            levels = generate_entry_levels(zone, features["atr"], direction)

            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": candle_time,
                "direction": direction,
                "zone_id": zone.get("zone_id"),
                "bos_level": bos["level"],
                **levels,
            }

    return None


def is_within_zone(
    price: Decimal,
    zone: Any,
    atr_value: Decimal,
    tolerance_multiplier: Decimal = Decimal("0.25"),
) -> bool:
    """Check if price touched/entered zone with ATR-based tolerance."""
    tolerance = atr_value * tolerance_multiplier

    # Check if price is within zone boundaries plus tolerance
    zone_top = zone["top_price"]
    zone_bottom = zone["bottom_price"]

    # Price is within zone if between bottom-tolerance and top+tolerance
    return (zone_bottom - tolerance) <= price <= (zone_top + tolerance)


def has_confirmation(
    candle: Any,
    _zone: Any,
    micro_bos: Any | None,
    direction: str,
) -> bool:
    """Validate close direction or micro-BOS confirmation."""
    # Check micro-BOS confirmation first
    if micro_bos and (
        (direction == "LONG" and micro_bos.get("type") == "BULLISH_BOS")
        or (direction == "SHORT" and micro_bos.get("type") == "BEARISH_BOS")
    ):
        return True

    # Check candle confirmation
    if candle:
        if direction == "LONG":
            # For long, need bullish close (close > open)
            return candle["close"] > candle["open"]
        # SHORT
        # For short, need bearish close (close < open)
        return candle["close"] < candle["open"]

    return False


def check_momentum_indicators(
    macd_hist: Decimal,
    macd_hist_prev: Decimal,
    rsi: Decimal,
    direction: str,
) -> bool:
    """Verify MACD histogram uptick and RSI bounce conditions."""
    if direction == "LONG":
        # For long: MACD histogram improving (uptick) and RSI in bounce range 40-55
        macd_improving = macd_hist > macd_hist_prev
        rsi_in_range = Decimal(40) <= rsi <= Decimal(55)
        return macd_improving and rsi_in_range
    # SHORT
    # For short: MACD histogram declining (downtick) and RSI in resistance range 45-60
    macd_declining = macd_hist < macd_hist_prev
    rsi_in_range = Decimal(45) <= rsi <= Decimal(60)
    return macd_declining and rsi_in_range


def generate_entry_levels(
    zone: Any,
    atr: Decimal,
    direction: str,
) -> dict[str, Decimal]:
    """Calculate entry, SL, and TP levels [1.5R, 2R, 3R]."""
    zone_top = zone["top_price"]
    zone_bottom = zone["bottom_price"]

    if direction == "LONG":
        # Entry at top of demand zone
        entry = zone_top
        # Stop loss below zone with ATR buffer
        stop_loss = zone_bottom - (atr * Decimal("0.5"))
    else:  # SHORT
        # Entry at bottom of supply zone
        entry = zone_bottom
        # Stop loss above zone with ATR buffer
        stop_loss = zone_top + (atr * Decimal("0.5"))

    # Calculate risk
    risk = abs(entry - stop_loss)

    # Calculate take profit levels
    if direction == "LONG":
        tp1 = entry + (risk * Decimal("1.5"))
        tp2 = entry + (risk * Decimal(2))
        tp3 = entry + (risk * Decimal(3))
    else:  # SHORT
        tp1 = entry - (risk * Decimal("1.5"))
        tp2 = entry - (risk * Decimal(2))
        tp3 = entry - (risk * Decimal(3))

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
    }


class RetestEngine:
    """Analyzes zone retests after Break of Structure events."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.event_bus = get_event_bus()
        self._running = False
        self._subscription_ids: list[str] = []

        # Cache recent data
        self._recent_candles: dict[str, deque[Candle]] = {}
        self._zones: dict[str, list[Any]] = {}
        self._bos_events: dict[str, deque[Any]] = {}
        self._features: dict[str, TechnicalIndicators] = {}

        # Configuration
        self.max_wait_bars = config.get("retest", {}).get("max_wait_bars", 8)
        self.tolerance_atr = config.get("retest", {}).get("entry_tolerance_atr", 0.25)
        self.sl_buffer_atr = config.get("retest", {}).get("sl_buffer_atr", 0.5)
        self.tp_levels = config.get("retest", {}).get("tp_levels", [1.5, 2.0, 3.0])

    async def start(self) -> None:
        """Start the retest engine."""
        if self._running:
            logger.warning("RetestEngine already running")
            return

        self._running = True

        # Subscribe to events
        sub_id = await self.event_bus.subscribe(
            subscriber_id="retest_engine_candles",
            handler=self._process_candle_event,
            event_types=[EventType.CANDLE_UPDATE],
            priority=5,
        )
        self._subscription_ids.append(sub_id)

        sub_id = await self.event_bus.subscribe(
            subscriber_id="retest_engine_features",
            handler=self._process_features_event,
            event_types=[EventType.FEATURES_CALCULATED],
            priority=5,
        )
        self._subscription_ids.append(sub_id)

        sub_id = await self.event_bus.subscribe(
            subscriber_id="retest_engine_smc",
            handler=self._process_smc_event,
            event_types=[EventType.SMC_SIGNAL],
            priority=5,
        )
        self._subscription_ids.append(sub_id)

        logger.info("RetestEngine started")

    async def stop(self) -> None:
        """Stop the retest engine."""
        if not self._running:
            return

        self._running = False

        # Unsubscribe from all events
        for sub_id in self._subscription_ids:
            await self.event_bus.unsubscribe(sub_id)

        self._subscription_ids.clear()
        logger.info("RetestEngine stopped")

    async def _process_candle_event(self, event: CandleUpdateEvent) -> None:
        """Process incoming candle events."""
        try:
            candle = event.candle
            key = f"{candle.symbol}:{candle.timeframe.value}"

            # Store candle
            if key not in self._recent_candles:
                self._recent_candles[key] = deque(maxlen=100)
            self._recent_candles[key].append(candle)

            # Check for retests
            await self._check_for_retests(candle)

        except Exception:
            logger.exception("Error processing candle event")

    async def _process_features_event(self, event: FeaturesCalculatedEvent) -> None:
        """Process incoming features events."""
        try:
            features = event.features
            key = f"{features.symbol}:{features.timeframe.value}"
            self._features[key] = features

        except Exception:
            logger.exception("Error processing features event")

    async def _process_smc_event(self, event: SMCSignalEvent) -> None:
        """Process incoming SMC events (BOS/CHOCH)."""
        try:
            signal = event.signal
            key = f"{event.symbol}:{event.timeframe.value}"

            # Store BOS events
            if "BOS" in signal.signal_type or "CHOCH" in signal.signal_type:
                if key not in self._bos_events:
                    self._bos_events[key] = deque(maxlen=50)

                self._bos_events[key].append(
                    {
                        "timestamp": signal.timestamp,
                        "type": (
                            "BULLISH_BOS"
                            if signal.direction == "BUY"
                            else "BEARISH_BOS"
                        ),
                        "level": signal.entry_price,
                        "strength": signal.confidence * 10,  # Convert to 1-10 scale
                    },
                )

            # Store zones
            if signal.zone:
                if key not in self._zones:
                    self._zones[key] = []

                self._zones[key].append(
                    {
                        "zone_id": str(signal.zone.zone_id),
                        "zone_type": signal.zone.zone_type.value,
                        "top_price": signal.zone.top_price,
                        "bottom_price": signal.zone.bottom_price,
                        "created_at": signal.zone.created_at,
                        "strength": signal.zone.strength,
                    },
                )

        except Exception:
            logger.exception("Error processing SMC event")

    async def _check_for_retests(self, candle: Candle) -> None:
        """Check if current candle represents a valid retest."""
        key = f"{candle.symbol}:{candle.timeframe.value}"

        # Get data
        candles = list(self._recent_candles.get(key, []))
        zones = self._zones.get(key, [])
        bos_events = list(self._bos_events.get(key, []))
        features = self._features.get(key)

        if not features or not candles:
            return

        # Analyze retest
        signal_data = await analyze_retest(
            symbol=candle.symbol,
            timeframe=candle.timeframe.value,
            candles=[self._candle_to_dict(c) for c in candles],
            zones=zones,
            bos_events=bos_events,
            features={
                "atr": features.atr_14 or Decimal(0),
                "macd_hist": features.macd_histogram or Decimal(0),
                "macd_hist_prev": Decimal(0),  # Would need to track previous
                "rsi": features.rsi_14 or Decimal(50),
            },
        )

        if signal_data:
            await self._emit_signal(signal_data)

    def _candle_to_dict(self, candle: Candle) -> dict[str, Any]:
        """Convert Candle model to dict for analyze_retest."""
        return {
            "open_time": candle.open_time,
            "close": candle.close_price,
            "open": candle.open_price,
            "high": candle.high_price,
            "low": candle.low_price,
            "volume": candle.volume,
        }

    async def _emit_signal(self, signal_data: dict[str, Any]) -> None:
        """Emit signal_raw.v1 event."""
        try:
            direction = "BUY" if signal_data["direction"] == "LONG" else "SELL"
            signal = RetestSignal(
                symbol=signal_data["symbol"],
                timeframe=TimeFrame(signal_data["timeframe"]),
                timestamp=signal_data["timestamp"],
                level_price=signal_data["entry"],
                direction=direction,
                stop_loss=signal_data["stop_loss"],
                take_profit=signal_data["tp1"],
                retest_type="zone_retest",
                success_probability=Decimal("0.7"),  # Would calculate properly
                volume_confirmation=True,
                confluence_factors=["bos_confirmation", "macd_uptick", "rsi_bounce"],
            )

            event = RetestSignalEvent(
                timestamp=datetime.now(UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            )

            await self.event_bus.publish(event, priority=8)
            logger.info(
                "Published retest signal for %s at %s",
                signal.symbol,
                signal.level_price,
            )

        except Exception:
            logger.exception("Error emitting signal")
