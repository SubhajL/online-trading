from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.smc.pivots import (
    PivotMethod,
    classify_pivot_relationship,
    detect_n_bar_pivots,
    detect_zigzag_pivots,
)
from app.engine.smc_types import Pivot, SwingType


def create_candle(
    timestamp: datetime,
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
        open_price=close,
        high_price=high,
        low_price=low,
        close_price=close,
        volume=Decimal("100"),
        quote_volume=Decimal("10000"),
        trades=100,
        bar_index=bar_index,
    )


@pytest.fixture
def bullish_trend_candles() -> list[Candle]:
    base_time = datetime(2024, 1, 1)
    candles = []
    prices = [
        (100, 90, 95),   # 0
        (105, 92, 103),  # 1
        (110, 100, 108), # 2 - high
        (109, 103, 105), # 3
        (107, 101, 102), # 4 - low
        (108, 100, 107), # 5
        (115, 106, 114), # 6 - high
        (113, 109, 110), # 7
        (112, 107, 108), # 8 - low
        (120, 105, 118), # 9 - high
    ]

    for i, (h, l, c) in enumerate(prices):
        candles.append(
            create_candle(
                base_time + timedelta(minutes=5*i),
                Decimal(str(h)),
                Decimal(str(l)),
                Decimal(str(c)),
                i,
            )
        )

    return candles


@pytest.fixture
def bearish_trend_candles() -> list[Candle]:
    base_time = datetime(2024, 1, 1)
    candles = []
    prices = [
        (120, 110, 115), # 0
        (118, 105, 107), # 1
        (110, 100, 102), # 2 - low
        (107, 101, 105), # 3
        (109, 103, 108), # 4 - high
        (106, 98, 100),  # 5
        (103, 92, 94),   # 6 - low
        (98, 93, 96),    # 7
        (102, 95, 101),  # 8 - high
        (95, 85, 87),    # 9 - low
    ]

    for i, (h, l, c) in enumerate(prices):
        candles.append(
            create_candle(
                base_time + timedelta(minutes=5*i),
                Decimal(str(h)),
                Decimal(str(l)),
                Decimal(str(c)),
                i,
            )
        )

    return candles


class TestNBarPivotDetection:
    def test_n_bar_pivot_detection_3_bar(self, bullish_trend_candles: list[Candle]) -> None:
        pivots = detect_n_bar_pivots(bullish_trend_candles, n=3)

        assert len(pivots) >= 3

        high_pivots = [p for p in pivots if p.is_high]
        low_pivots = [p for p in pivots if not p.is_high]

        assert len(high_pivots) >= 2
        assert len(low_pivots) >= 1

        assert high_pivots[0].price == Decimal("110")
        assert high_pivots[0].bar_index == 2

        assert low_pivots[0].price == Decimal("101")
        assert low_pivots[0].bar_index == 4

    def test_n_bar_pivot_detection_5_bar(self, bullish_trend_candles: list[Candle]) -> None:
        pivots = detect_n_bar_pivots(bullish_trend_candles, n=5)

        assert len(pivots) >= 1

        high_pivots = [p for p in pivots if p.is_high]
        assert len(high_pivots) >= 1
        assert high_pivots[0].price == Decimal("115")
        assert high_pivots[0].bar_index == 6

    def test_n_bar_no_pivots_insufficient_data(self) -> None:
        candles = [
            create_candle(datetime.now(), Decimal("100"), Decimal("90"), Decimal("95"), 0),
            create_candle(datetime.now(), Decimal("105"), Decimal("92"), Decimal("103"), 1),
        ]

        pivots = detect_n_bar_pivots(candles, n=3)
        assert len(pivots) == 0

    def test_n_bar_equal_highs_detection(self) -> None:
        base_time = datetime(2024, 1, 1)
        candles = []
        for i in range(7):
            if i in [2, 4]:  # Equal highs
                candles.append(
                    create_candle(base_time + timedelta(minutes=5*i),
                                Decimal("110"), Decimal("100"), Decimal("105"), i)
                )
            else:
                candles.append(
                    create_candle(base_time + timedelta(minutes=5*i),
                                Decimal("105"), Decimal("95"), Decimal("100"), i)
                )

        pivots = detect_n_bar_pivots(candles, n=3)
        high_pivots = [p for p in pivots if p.is_high]

        assert len(high_pivots) == 2
        assert all(p.price == Decimal("110") for p in high_pivots)


class TestZigZagPivotDetection:
    def test_zigzag_pivot_detection_basic(self, bullish_trend_candles: list[Candle]) -> None:
        atr_value = Decimal("2.0")
        pivots = detect_zigzag_pivots(bullish_trend_candles, atr_value, min_reversal_factor=2.0)

        assert len(pivots) >= 2

        for i in range(1, len(pivots)):
            prev = pivots[i-1]
            curr = pivots[i]
            assert prev.is_high != curr.is_high

    def test_zigzag_respects_atr_threshold(self) -> None:
        base_time = datetime(2024, 1, 1)
        candles = []

        # Small movements that should be filtered by ATR
        for i in range(10):
            high = Decimal("100") + Decimal(str(i % 2))
            low = Decimal("98") + Decimal(str(i % 2))
            close = Decimal("99") + Decimal(str(i % 2))
            candles.append(create_candle(base_time + timedelta(minutes=5*i), high, low, close, i))

        atr_value = Decimal("5.0")
        pivots = detect_zigzag_pivots(candles, atr_value, min_reversal_factor=2.0)

        assert len(pivots) == 0 or len(pivots) == 1

    def test_zigzag_large_moves_detected(self) -> None:
        base_time = datetime(2024, 1, 1)
        candles = []

        # Large price swings
        prices = [
            (100, 90, 95),
            (120, 95, 118),   # Big up
            (119, 80, 82),    # Big down
            (140, 81, 138),   # Big up
        ]

        for i, (h, l, c) in enumerate(prices):
            candles.append(
                create_candle(base_time + timedelta(minutes=5*i),
                            Decimal(str(h)), Decimal(str(l)), Decimal(str(c)), i)
            )

        atr_value = Decimal("5.0")
        pivots = detect_zigzag_pivots(candles, atr_value, min_reversal_factor=2.0)

        assert len(pivots) >= 3
        assert pivots[0].price == Decimal("90")  # Low
        assert pivots[1].price == Decimal("120") # High
        assert pivots[2].price == Decimal("80")  # Low


class TestPivotClassification:
    def test_classify_higher_high(self) -> None:
        prev_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("100"),
            is_high=True,
            strength=3,
            bar_index=0,
        )

        curr_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("110"),
            is_high=True,
            strength=3,
            bar_index=5,
        )

        swing_type = classify_pivot_relationship(prev_pivot, curr_pivot)
        assert swing_type == SwingType.HH

    def test_classify_lower_low(self) -> None:
        prev_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("90"),
            is_high=False,
            strength=3,
            bar_index=0,
        )

        curr_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("85"),
            is_high=False,
            strength=3,
            bar_index=5,
        )

        swing_type = classify_pivot_relationship(prev_pivot, curr_pivot)
        assert swing_type == SwingType.LL

    def test_classify_higher_low(self) -> None:
        prev_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("85"),
            is_high=False,
            strength=3,
            bar_index=0,
        )

        curr_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("90"),
            is_high=False,
            strength=3,
            bar_index=5,
        )

        swing_type = classify_pivot_relationship(prev_pivot, curr_pivot)
        assert swing_type == SwingType.HL

    def test_classify_lower_high(self) -> None:
        prev_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("110"),
            is_high=True,
            strength=3,
            bar_index=0,
        )

        curr_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("105"),
            is_high=True,
            strength=3,
            bar_index=5,
        )

        swing_type = classify_pivot_relationship(prev_pivot, curr_pivot)
        assert swing_type == SwingType.LH

    def test_classify_equal_high_within_tolerance(self) -> None:
        prev_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("100.00"),
            is_high=True,
            strength=3,
            bar_index=0,
        )

        curr_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("100.05"),
            is_high=True,
            strength=3,
            bar_index=5,
        )

        swing_type = classify_pivot_relationship(prev_pivot, curr_pivot, tolerance=Decimal("0.001"))
        assert swing_type == SwingType.EH

    def test_classify_different_types_returns_none(self) -> None:
        high_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("100"),
            is_high=True,
            strength=3,
            bar_index=0,
        )

        low_pivot = Pivot(
            timestamp=datetime.now(),
            price=Decimal("90"),
            is_high=False,
            strength=3,
            bar_index=5,
        )

        swing_type = classify_pivot_relationship(high_pivot, low_pivot)
        assert swing_type is None