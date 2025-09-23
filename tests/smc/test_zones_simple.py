#!/usr/bin/env python3
"""Simplified test runner for zone detection without dependencies"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.engine.smc.zones import (
    detect_fair_value_gap,
    detect_order_block,
    expire_old_zones,
    zone_to_dict,
)


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
    def __init__(self, kind, timestamp, price, from_state, to_state, trigger_pivot=None, reference_pivot=None):
        self.kind = kind
        self.timestamp = timestamp
        self.price = price
        self.from_state = from_state
        self.to_state = to_state
        self.trigger_pivot = trigger_pivot
        self.reference_pivot = reference_pivot


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


# Tests
def test_bullish_fvg_detection():
    print("Testing bullish FVG detection...")
    base_time = datetime(2024, 1, 1)

    candles = [
        # Bullish FVG: gap between candle[0].high and candle[2].low
        Candle("BTCUSDT", TimeFrame.M5, Decimal("100"), Decimal("102"), Decimal("99"), Decimal("101"), 0, base_time),
        Candle("BTCUSDT", TimeFrame.M5, Decimal("101"), Decimal("110"), Decimal("101"), Decimal("109"), 1, base_time + timedelta(minutes=5)),
        Candle("BTCUSDT", TimeFrame.M5, Decimal("109"), Decimal("111"), Decimal("105"), Decimal("106"), 2, base_time + timedelta(minutes=10)),
    ]

    zone = detect_fair_value_gap(candles, "BTCUSDT", TimeFrame.M5)

    assert zone is not None
    assert zone.zone_type == "FVG"
    assert zone.side == ZoneSide.LOW
    assert zone.bottom_price == Decimal("102")  # candles[0].high
    assert zone.top_price == Decimal("105")     # candles[2].low
    print("  ✓ Test passed")


def test_bearish_fvg_detection():
    print("Testing bearish FVG detection...")
    base_time = datetime(2024, 1, 1)

    candles = [
        # Bearish FVG: gap between candle[2].high and candle[0].low
        Candle("BTCUSDT", TimeFrame.M5, Decimal("110"), Decimal("111"), Decimal("108"), Decimal("109"), 0, base_time),
        Candle("BTCUSDT", TimeFrame.M5, Decimal("109"), Decimal("109"), Decimal("100"), Decimal("101"), 1, base_time + timedelta(minutes=5)),
        Candle("BTCUSDT", TimeFrame.M5, Decimal("101"), Decimal("105"), Decimal("100"), Decimal("104"), 2, base_time + timedelta(minutes=10)),
    ]

    zone = detect_fair_value_gap(candles, "BTCUSDT", TimeFrame.M5)

    assert zone is not None
    assert zone.zone_type == "FVG"
    assert zone.side == ZoneSide.HIGH
    assert zone.bottom_price == Decimal("105")  # candles[2].high
    assert zone.top_price == Decimal("108")     # candles[0].low
    print("  ✓ Test passed")


def test_order_block_detection():
    print("Testing order block detection...")
    base_time = datetime(2024, 1, 1)

    # Last bearish candle before bullish BOS
    candle = Candle("BTCUSDT", TimeFrame.M5, Decimal("100"), Decimal("101"), Decimal("95"), Decimal("96"), 5, base_time)

    # BOS event
    bos_event = SMCEvent(
        kind=SMCEventKind.BOS,
        timestamp=base_time + timedelta(minutes=10),
        price=Decimal("110"),
        from_state="BULLISH",
        to_state="BULLISH",
    )

    zone = detect_order_block(candle, bos_event, TimeFrame.M5)

    assert zone is not None
    assert zone.zone_type == "OB_BULL"
    assert zone.side == ZoneSide.LOW
    assert zone.bottom_price == Decimal("95")   # candle low
    assert zone.top_price == Decimal("101")     # candle high
    print("  ✓ Test passed")


def test_zone_expiration():
    print("Testing zone expiration...")
    base_time = datetime(2024, 1, 1)

    zones = []
    for i in range(5):
        zone = Zone(
            zone_id=uuid.uuid4(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            zone_type="FVG",
            side=ZoneSide.LOW,
            top_price=Decimal("105"),
            bottom_price=Decimal("100"),
            created_at=base_time + timedelta(minutes=i * 5),
            created_bar_index=i,
            expiry_bars=10,
        )
        zones.append(zone)

    # Current bar index is 12
    active_zones = expire_old_zones(zones, current_bar_index=12)

    # Zones created at indices 3 and 4 should remain (12 - 10 = 2)
    assert len(active_zones) == 2
    assert all(z.created_bar_index >= 3 for z in active_zones)
    print("  ✓ Test passed")


def test_zone_serialization():
    print("Testing zone serialization...")
    zone = Zone(
        zone_id=uuid.uuid4(),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        zone_type="OB_BULL",
        side=ZoneSide.LOW,
        top_price=Decimal("105.50"),
        bottom_price=Decimal("100.25"),
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        created_bar_index=42,
        expiry_bars=100,
        touches=3,
        strength=Decimal("0.85"),
    )

    zone_dict = zone_to_dict(zone)

    assert zone_dict["symbol"] == "BTCUSDT"
    assert zone_dict["zone_type"] == "OB_BULL"
    assert zone_dict["top_price"] == "105.50"
    assert zone_dict["touches"] == 3
    print("  ✓ Test passed")


if __name__ == "__main__":
    print("\nRunning zone detection tests...\n")

    tests = [
        test_bullish_fvg_detection,
        test_bearish_fvg_detection,
        test_order_block_detection,
        test_zone_expiration,
        test_zone_serialization,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print("\n✅ All tests passed!\n")