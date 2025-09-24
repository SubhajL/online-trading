"""
Retest Analyzer Engine - Detects zone retests after Break of Structure (BOS)

Requirements:
- Retests within ≤8 bars after BOS
- Price touches/enters zone band with tolerance 0.25×ATR
- Confirmation by close in direction or micro-BOS on sub-TF
- MACD histogram uptick
- RSI 40-55 bounce for longs
"""

from datetime import datetime
from decimal import Decimal
import logging
from typing import Any

from ..bus import get_event_bus
from ..types import BaseEvent, Brand

logger = logging.getLogger(__name__)

ZoneId = Brand[str, 'ZoneId']
SignalId = Brand[str, 'SignalId']


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
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440,
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
    zone: Any,
    micro_bos: Any | None,
    direction: str,
) -> bool:
    """Validate close direction or micro-BOS confirmation."""
    # Check micro-BOS confirmation first
    if micro_bos:
        if direction == "LONG" and micro_bos.get("type") == "BULLISH_BOS":
            return True
        elif direction == "SHORT" and micro_bos.get("type") == "BEARISH_BOS":
            return True

    # Check candle confirmation
    if candle:
        if direction == "LONG":
            # For long, need bullish close (close > open)
            return candle["close"] > candle["open"]
        else:  # SHORT
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
        rsi_in_range = Decimal("40") <= rsi <= Decimal("55")
        return macd_improving and rsi_in_range
    else:  # SHORT
        # For short: MACD histogram declining (downtick) and RSI in resistance range 45-60
        macd_declining = macd_hist < macd_hist_prev
        rsi_in_range = Decimal("45") <= rsi <= Decimal("60")
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
        tp2 = entry + (risk * Decimal("2"))
        tp3 = entry + (risk * Decimal("3"))
    else:  # SHORT
        tp1 = entry - (risk * Decimal("1.5"))
        tp2 = entry - (risk * Decimal("2"))
        tp3 = entry - (risk * Decimal("3"))

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

    async def start(self) -> None:
        """Start the retest engine."""
        raise NotImplementedError()

    async def stop(self) -> None:
        """Stop the retest engine."""
        raise NotImplementedError()

    async def _process_candle_event(self, event: Any) -> None:
        """Process incoming candle events."""
        raise NotImplementedError()

    async def _process_zone_event(self, event: Any) -> None:
        """Process incoming zone events."""
        raise NotImplementedError()

    async def _process_smc_event(self, event: Any) -> None:
        """Process incoming SMC events (BOS/CHOCH)."""
        raise NotImplementedError()

    async def _emit_signal(self, signal: Any) -> None:
        """Emit signal_raw.v1 event."""
        raise NotImplementedError()