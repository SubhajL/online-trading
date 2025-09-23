#!/usr/bin/env python3
"""Isolated test for zone detection with inline implementations"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum


# Inline types
class TimeFrame(str, Enum):
    M5 = "5m"


class ZoneSide(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class SMCEventKind(str, Enum):
    CHOCH = "CHOCH"
    BOS = "BOS"


class Candle:
    def __init__(self, symbol, timeframe, open_price, high_price, low_price, close_price, bar_index, close_time):
        self.symbol = symbol
        self.timeframe = timeframe
        self.open_price = open_price
        self.high_price = high_price
        self.low_price = low_price
        self.close_price = close_price
        self.bar_index = bar_index
        self.close_time = close_time


class SMCEvent:
    def __init__(self, kind, timestamp, price, from_state, to_state):
        self.kind = kind
        self.timestamp = timestamp
        self.price = price
        self.from_state = from_state
        self.to_state = to_state


class Zone:
    def __init__(self, zone_id, symbol, timeframe, zone_type, side, top_price, bottom_price,
                 created_at, created_bar_index, expiry_bars, touches=0, strength=Decimal("1.0")):
        self.zone_id = zone_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.zone_type = zone_type
        self.side = side
        self.top_price = top_price
        self.bottom_price = bottom_price
        self.created_at = created_at
        self.created_bar_index = created_bar_index
        self.expiry_bars = expiry_bars
        self.touches = touches
        self.strength = strength

    @property
    def mid_price(self):
        return (self.top_price + self.bottom_price) / 2


# Inline implementations
def detect_fair_value_gap(candles, symbol, timeframe):
    if len(candles) < 3:
        return None

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
            side=ZoneSide.LOW,
            top_price=third.low_price,
            bottom_price=first.high_price,
            created_at=third.close_time,
            created_bar_index=third.bar_index,
            expiry_bars=100,
            strength=Decimal("1.0"),
        )

    # Check for bearish FVG: gap between third.high and first.low
    if third.high_price < first.low_price:
        return Zone(
            zone_id=uuid.uuid4(),
            symbol=symbol,
            timeframe=timeframe,
            zone_type="FVG",
            side=ZoneSide.HIGH,
            top_price=first.low_price,
            bottom_price=third.high_price,
            created_at=third.close_time,
            created_bar_index=third.bar_index,
            expiry_bars=100,
            strength=Decimal("1.0"),
        )

    return None


def detect_order_block(last_opposite_candle, smc_event, timeframe, min_body_ratio=0.0):
    if smc_event.kind != SMCEventKind.BOS:
        return None

    candle_range = last_opposite_candle.high_price - last_opposite_candle.low_price
    if candle_range == 0:
        return None

    candle_body = abs(last_opposite_candle.close_price - last_opposite_candle.open_price)
    body_ratio = float(candle_body / candle_range)

    if body_ratio < min_body_ratio:
        return None

    if smc_event.from_state == "BULLISH" or smc_event.to_state == "BULLISH":
        zone_type = "OB_BULL"
        side = ZoneSide.LOW
    else:
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


def expire_old_zones(zones, current_bar_index):
    active_zones = []
    for zone in zones:
        bars_since_creation = current_bar_index - zone.created_bar_index
        if bars_since_creation < zone.expiry_bars:
            active_zones.append(zone)
    return active_zones


def zone_to_dict(zone):
    return {
        "zone_id": str(zone.zone_id),
        "symbol": zone.symbol,
        "timeframe": zone.timeframe.value if hasattr(zone.timeframe, 'value') else zone.timeframe,
        "zone_type": zone.zone_type,
        "side": zone.side.value if hasattr(zone.side, 'value') else zone.side,
        "top_price": str(zone.top_price),
        "bottom_price": str(zone.bottom_price),
        "created_at": zone.created_at.isoformat(),
        "created_bar_index": zone.created_bar_index,
        "expiry_bars": zone.expiry_bars,
        "touches": zone.touches,
        "strength": str(zone.strength),
    }


# Tests
def test_bullish_fvg():
    print("Testing bullish FVG detection...")
    base_time = datetime(2024, 1, 1)

    candles = [
        Candle("BTCUSDT", TimeFrame.M5, Decimal("100"), Decimal("102"), Decimal("99"), Decimal("101"), 0, base_time),
        Candle("BTCUSDT", TimeFrame.M5, Decimal("101"), Decimal("110"), Decimal("101"), Decimal("109"), 1, base_time + timedelta(minutes=5)),
        Candle("BTCUSDT", TimeFrame.M5, Decimal("109"), Decimal("111"), Decimal("105"), Decimal("106"), 2, base_time + timedelta(minutes=10)),
    ]

    zone = detect_fair_value_gap(candles, "BTCUSDT", TimeFrame.M5)

    assert zone is not None
    assert zone.zone_type == "FVG"
    assert zone.side == ZoneSide.LOW
    assert zone.bottom_price == Decimal("102")
    assert zone.top_price == Decimal("105")
    print("  ✓ Test passed")


def test_order_block():
    print("Testing order block detection...")
    base_time = datetime(2024, 1, 1)

    candle = Candle("BTCUSDT", TimeFrame.M5, Decimal("100"), Decimal("101"), Decimal("95"), Decimal("96"), 5, base_time)
    bos_event = SMCEvent(SMCEventKind.BOS, base_time + timedelta(minutes=10), Decimal("110"), "BULLISH", "BULLISH")

    zone = detect_order_block(candle, bos_event, TimeFrame.M5)

    assert zone is not None
    assert zone.zone_type == "OB_BULL"
    assert zone.side == ZoneSide.LOW
    assert zone.bottom_price == Decimal("95")
    assert zone.top_price == Decimal("101")
    print("  ✓ Test passed")


def test_zone_expiration():
    print("Testing zone expiration...")
    base_time = datetime(2024, 1, 1)

    zones = []
    for i in range(5):
        zone = Zone(
            uuid.uuid4(), "BTCUSDT", TimeFrame.M5, "FVG", ZoneSide.LOW,
            Decimal("105"), Decimal("100"), base_time + timedelta(minutes=i * 5),
            i, 10
        )
        zones.append(zone)

    active_zones = expire_old_zones(zones, current_bar_index=12)

    assert len(active_zones) == 2
    assert all(z.created_bar_index >= 3 for z in active_zones)
    print("  ✓ Test passed")


if __name__ == "__main__":
    print("\nRunning isolated zone tests...\n")

    tests = [test_bullish_fvg, test_order_block, test_zone_expiration]

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print("\n✅ All tests passed!\n")