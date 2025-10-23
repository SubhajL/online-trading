from __future__ import annotations

from decimal import Decimal
import uuid

from ..models import Candle, TimeFrame
from ..smc_types import SMCEvent, SMCEventKind, Zone, ZoneSide


def detect_fair_value_gap(
    candles: list[Candle],
    symbol: str,
    timeframe: TimeFrame,
) -> Zone | None:
    if len(candles) < 3:
        return None

    # FVG requires 3 candles
    first = candles[0]
    second = candles[1]
    third = candles[2]

    # Check for bullish FVG: gap between first.high and third.low
    if first.high_price < third.low_price:
        return Zone(
            zone_id=uuid.uuid4(),
            symbol=symbol,
            timeframe=timeframe,
            zone_type="FVG",
            side=ZoneSide.LOW,  # Bullish FVG is on the low side
            top_price=third.low_price,
            bottom_price=first.high_price,
            created_at=third.close_time,
            created_bar_index=third.bar_index,
            expiry_bars=100,  # Default expiry
            strength=Decimal("1.0"),
        )

    # Check for bearish FVG: gap between third.high and first.low
    if third.high_price < first.low_price:
        return Zone(
            zone_id=uuid.uuid4(),
            symbol=symbol,
            timeframe=timeframe,
            zone_type="FVG",
            side=ZoneSide.HIGH,  # Bearish FVG is on the high side
            top_price=first.low_price,
            bottom_price=third.high_price,
            created_at=third.close_time,
            created_bar_index=third.bar_index,
            expiry_bars=100,
            strength=Decimal("1.0"),
        )

    return None


def detect_order_block(
    last_opposite_candle: Candle,
    smc_event: SMCEvent,
    timeframe: TimeFrame,
    min_body_ratio: float = 0.0,
) -> Zone | None:
    # Only create order blocks on BOS events
    if smc_event.kind != SMCEventKind.BOS:
        return None

    candle_range = last_opposite_candle.high_price - last_opposite_candle.low_price
    if candle_range == 0:
        return None

    candle_body = abs(
        last_opposite_candle.close_price - last_opposite_candle.open_price,
    )
    body_ratio = float(candle_body / candle_range)

    # Check minimum body ratio requirement
    if body_ratio < min_body_ratio:
        return None

    # Determine if this is a bullish or bearish OB based on the BOS state
    if smc_event.from_state == "BULLISH" or smc_event.to_state == "BULLISH":
        # Bullish OB (last bearish candle before bullish BOS)
        zone_type = "OB_BULL"
        side = ZoneSide.LOW
    else:
        # Bearish OB (last bullish candle before bearish BOS)
        zone_type = "OB_BEAR"
        side = ZoneSide.HIGH

    return Zone(
        zone_id=uuid.uuid4(),
        symbol=last_opposite_candle.symbol,
        timeframe=timeframe,
        zone_type=zone_type,
        side=side,
        top_price=last_opposite_candle.high_price,
        bottom_price=last_opposite_candle.low_price,
        created_at=smc_event.timestamp,
        created_bar_index=last_opposite_candle.bar_index,
        expiry_bars=100,
        strength=Decimal("1.0"),
    )


def expire_old_zones(
    zones: list[Zone],
    current_bar_index: int,
) -> list[Zone]:
    active_zones = []

    for zone in zones:
        bars_since_creation = current_bar_index - zone.created_bar_index
        if bars_since_creation < zone.expiry_bars:
            active_zones.append(zone)

    return active_zones


def zone_to_dict(zone: Zone) -> dict[str, str | int | float]:
    return {
        "zone_id": str(zone.zone_id),
        "symbol": zone.symbol,
        "timeframe": zone.timeframe.value,
        "zone_type": zone.zone_type,
        "side": zone.side.value,
        "top_price": str(zone.top_price),
        "bottom_price": str(zone.bottom_price),
        "created_at": zone.created_at.isoformat(),
        "created_bar_index": zone.created_bar_index,
        "expiry_bars": zone.expiry_bars,
        "touches": zone.touches,
        "strength": str(zone.strength),
    }
