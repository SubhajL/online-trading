from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.smc.zones import (
    detect_fair_value_gap,
    detect_order_block,
    expire_old_zones,
    zone_to_dict,
)
from app.engine.types import SMCEvent, SMCEventKind, Zone, ZoneSide


def create_candle(
    timestamp: datetime,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    bar_index: int,
) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        open_time=timestamp,
        close_time=timestamp + timedelta(minutes=5),
        open_price=open_,
        high_price=high,
        low_price=low,
        close_price=close,
        volume=Decimal("100"),
        quote_volume=Decimal("10000"),
        trades=100,
        bar_index=bar_index,
    )


class TestFairValueGapDetection:
    def test_bullish_fvg_detection(self) -> None:
        base_time = datetime(2024, 1, 1)
        candles = [
            # Bullish FVG pattern: gap between candle[0].high and candle[2].low
            create_candle(base_time, Decimal("100"), Decimal("102"), Decimal("99"), Decimal("101"), 0),
            create_candle(base_time + timedelta(minutes=5), Decimal("101"), Decimal("110"), Decimal("101"), Decimal("109"), 1),
            create_candle(base_time + timedelta(minutes=10), Decimal("109"), Decimal("111"), Decimal("105"), Decimal("106"), 2),
        ]

        zone = detect_fair_value_gap(candles, "BTCUSDT", TimeFrame.M5)

        assert zone is not None
        assert zone.zone_type == "FVG"
        assert zone.side == ZoneSide.LOW  # Bullish FVG on low side
        assert zone.bottom_price == Decimal("102")  # candles[0].high
        assert zone.top_price == Decimal("105")     # candles[2].low
        assert zone.created_bar_index == 2

    def test_bearish_fvg_detection(self) -> None:
        base_time = datetime(2024, 1, 1)
        candles = [
            # Bearish FVG pattern: gap between candle[0].low and candle[2].high
            create_candle(base_time, Decimal("110"), Decimal("111"), Decimal("108"), Decimal("109"), 0),
            create_candle(base_time + timedelta(minutes=5), Decimal("109"), Decimal("109"), Decimal("100"), Decimal("101"), 1),
            create_candle(base_time + timedelta(minutes=10), Decimal("101"), Decimal("105"), Decimal("100"), Decimal("104"), 2),
        ]

        zone = detect_fair_value_gap(candles, "BTCUSDT", TimeFrame.M5)

        assert zone is not None
        assert zone.zone_type == "FVG"
        assert zone.side == ZoneSide.HIGH  # Bearish FVG on high side
        assert zone.bottom_price == Decimal("105")  # candles[2].high
        assert zone.top_price == Decimal("108")     # candles[0].low
        assert zone.created_bar_index == 2

    def test_no_fvg_when_no_gap(self) -> None:
        base_time = datetime(2024, 1, 1)
        candles = [
            # No gap - candles overlap completely
            create_candle(base_time, Decimal("100"), Decimal("105"), Decimal("99"), Decimal("103"), 0),
            create_candle(base_time + timedelta(minutes=5), Decimal("103"), Decimal("106"), Decimal("101"), Decimal("104"), 1),
            create_candle(base_time + timedelta(minutes=10), Decimal("104"), Decimal("107"), Decimal("102"), Decimal("105"), 2),
        ]

        zone = detect_fair_value_gap(candles, "BTCUSDT", TimeFrame.M5)
        assert zone is None

    def test_insufficient_candles_for_fvg(self) -> None:
        base_time = datetime(2024, 1, 1)
        candles = [
            create_candle(base_time, Decimal("100"), Decimal("105"), Decimal("99"), Decimal("103"), 0),
            create_candle(base_time + timedelta(minutes=5), Decimal("103"), Decimal("106"), Decimal("101"), Decimal("104"), 1),
        ]

        zone = detect_fair_value_gap(candles, "BTCUSDT", TimeFrame.M5)
        assert zone is None


class TestOrderBlockDetection:
    def test_bullish_order_block_before_bos(self) -> None:
        base_time = datetime(2024, 1, 1)
        # Last bearish candle before bullish BOS
        last_opposite_candle = create_candle(
            base_time, Decimal("100"), Decimal("101"), Decimal("95"), Decimal("96"), 5
        )

        # BOS event (price breaking above resistance)
        bos_event = SMCEvent(
            kind=SMCEventKind.BOS,
            timestamp=base_time + timedelta(minutes=10),
            price=Decimal("110"),
            from_state="BULLISH",
            to_state="BULLISH",
            trigger_pivot=None,
            reference_pivot=None,
        )

        zone = detect_order_block(last_opposite_candle, bos_event, TimeFrame.M5)

        assert zone is not None
        assert zone.zone_type == "OB_BULL"
        assert zone.side == ZoneSide.LOW
        assert zone.bottom_price == Decimal("95")   # candle low
        assert zone.top_price == Decimal("101")     # candle high
        assert zone.created_bar_index == 5

    def test_bearish_order_block_before_bos(self) -> None:
        base_time = datetime(2024, 1, 1)
        # Last bullish candle before bearish BOS
        last_opposite_candle = create_candle(
            base_time, Decimal("110"), Decimal("115"), Decimal("109"), Decimal("114"), 7
        )

        # BOS event (price breaking below support)
        bos_event = SMCEvent(
            kind=SMCEventKind.BOS,
            timestamp=base_time + timedelta(minutes=10),
            price=Decimal("100"),
            from_state="BEARISH",
            to_state="BEARISH",
            trigger_pivot=None,
            reference_pivot=None,
        )

        zone = detect_order_block(last_opposite_candle, bos_event, TimeFrame.M5)

        assert zone is not None
        assert zone.zone_type == "OB_BEAR"
        assert zone.side == ZoneSide.HIGH
        assert zone.bottom_price == Decimal("109")  # candle low
        assert zone.top_price == Decimal("115")     # candle high
        assert zone.created_bar_index == 7

    def test_no_order_block_for_choch(self) -> None:
        base_time = datetime(2024, 1, 1)
        candle = create_candle(
            base_time, Decimal("100"), Decimal("105"), Decimal("99"), Decimal("103"), 5
        )

        # CHOCH event (not BOS)
        choch_event = SMCEvent(
            kind=SMCEventKind.CHOCH,
            timestamp=base_time + timedelta(minutes=10),
            price=Decimal("110"),
            from_state="BEARISH",
            to_state="BULLISH",
            trigger_pivot=None,
            reference_pivot=None,
        )

        zone = detect_order_block(candle, choch_event, TimeFrame.M5)
        assert zone is None

    def test_order_block_requires_body_ratio(self) -> None:
        base_time = datetime(2024, 1, 1)
        # Doji candle with tiny body
        doji_candle = create_candle(
            base_time, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100.1"), 5
        )

        bos_event = SMCEvent(
            kind=SMCEventKind.BOS,
            timestamp=base_time + timedelta(minutes=10),
            price=Decimal("110"),
            from_state="BULLISH",
            to_state="BULLISH",
            trigger_pivot=None,
            reference_pivot=None,
        )

        zone = detect_order_block(doji_candle, bos_event, TimeFrame.M5, min_body_ratio=0.5)
        assert zone is None  # Body too small relative to range


class TestZoneExpiration:
    def test_expire_old_zones(self) -> None:
        zones = []
        base_time = datetime(2024, 1, 1)

        # Create zones at different bar indices
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
                expiry_bars=10,  # Expires after 10 bars
            )
            zones.append(zone)

        # Current bar index is 15
        active_zones = expire_old_zones(zones, current_bar_index=15)

        # Only zones created at bar index 6 or later should remain
        # (15 - 10 = 5, so zones 0-4 should be expired)
        assert len(active_zones) == 0  # All zones are older than 10 bars

        # Test with current bar index 12
        active_zones = expire_old_zones(zones, current_bar_index=12)
        assert len(active_zones) == 2  # Zones at indices 3 and 4 remain

    def test_zone_touches_increment(self) -> None:
        zone = Zone(
            zone_id=uuid.uuid4(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            zone_type="FVG",
            side=ZoneSide.LOW,
            top_price=Decimal("105"),
            bottom_price=Decimal("100"),
            created_at=datetime.now(),
            created_bar_index=0,
            expiry_bars=50,
            touches=0,
        )

        # Simulate touches
        zone.touches += 1
        assert zone.touches == 1

        zone.touches += 1
        assert zone.touches == 2


class TestZoneSerialization:
    def test_zone_to_dict(self) -> None:
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

        assert zone_dict["zone_id"] == str(zone.zone_id)
        assert zone_dict["symbol"] == "BTCUSDT"
        assert zone_dict["timeframe"] == "5m"
        assert zone_dict["zone_type"] == "OB_BULL"
        assert zone_dict["side"] == "LOW"
        assert zone_dict["top_price"] == "105.50"
        assert zone_dict["bottom_price"] == "100.25"
        assert zone_dict["created_bar_index"] == 42
        assert zone_dict["expiry_bars"] == 100
        assert zone_dict["touches"] == 3
        assert zone_dict["strength"] == "0.85"
        assert "created_at" in zone_dict

    def test_zone_mid_price_property(self) -> None:
        zone = Zone(
            zone_id=uuid.uuid4(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            zone_type="FVG",
            side=ZoneSide.LOW,
            top_price=Decimal("110"),
            bottom_price=Decimal("100"),
            created_at=datetime.now(),
            created_bar_index=0,
            expiry_bars=50,
        )

        assert zone.mid_price == Decimal("105")