#!/usr/bin/env python3
"""Simple test runner for SMC tests without pytest"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.engine.models import Candle, TimeFrame
from app.engine.smc.pivots import (
    classify_pivot_relationship,
    detect_n_bar_pivots,
    detect_zigzag_pivots,
)
from app.engine.types import Pivot, SwingType


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


def test_n_bar_3_detection():
    print("Testing N-bar (3) pivot detection...")
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

    pivots = detect_n_bar_pivots(candles, n=3)

    print(f"  Found {len(pivots)} pivots")
    high_pivots = [p for p in pivots if p.is_high]
    low_pivots = [p for p in pivots if not p.is_high]

    assert len(high_pivots) >= 2, f"Expected at least 2 high pivots, got {len(high_pivots)}"
    assert len(low_pivots) >= 1, f"Expected at least 1 low pivot, got {len(low_pivots)}"
    assert high_pivots[0].price == Decimal("110"), f"Expected first high at 110, got {high_pivots[0].price}"
    assert low_pivots[0].price == Decimal("101"), f"Expected first low at 101, got {low_pivots[0].price}"

    print("  ✓ N-bar (3) detection test passed")


def test_zigzag_detection():
    print("Testing ZigZag pivot detection...")
    base_time = datetime(2024, 1, 1)
    candles = []
    prices = [
        (100, 90, 95),
        (120, 95, 118),   # Big up
        (119, 80, 82),    # Big down
        (140, 81, 138),   # Big up
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

    atr_value = Decimal("5.0")
    pivots = detect_zigzag_pivots(candles, atr_value, min_reversal_factor=2.0)

    print(f"  Found {len(pivots)} pivots")

    assert len(pivots) >= 3, f"Expected at least 3 pivots, got {len(pivots)}"
    assert pivots[0].price == Decimal("90"), f"Expected first pivot at 90, got {pivots[0].price}"
    assert pivots[1].price == Decimal("120"), f"Expected second pivot at 120, got {pivots[1].price}"
    assert pivots[2].price == Decimal("80"), f"Expected third pivot at 80, got {pivots[2].price}"

    print("  ✓ ZigZag detection test passed")


def test_pivot_classification():
    print("Testing pivot classification...")

    # Test Higher High
    prev_high = Pivot(
        timestamp=datetime.now(),
        price=Decimal("100"),
        is_high=True,
        strength=3,
        bar_index=0,
    )
    curr_high = Pivot(
        timestamp=datetime.now(),
        price=Decimal("110"),
        is_high=True,
        strength=3,
        bar_index=5,
    )

    result = classify_pivot_relationship(prev_high, curr_high)
    assert result == SwingType.HH, f"Expected HH, got {result}"
    print("  ✓ Higher High classification passed")

    # Test Lower Low
    prev_low = Pivot(
        timestamp=datetime.now(),
        price=Decimal("90"),
        is_high=False,
        strength=3,
        bar_index=0,
    )
    curr_low = Pivot(
        timestamp=datetime.now(),
        price=Decimal("85"),
        is_high=False,
        strength=3,
        bar_index=5,
    )

    result = classify_pivot_relationship(prev_low, curr_low)
    assert result == SwingType.LL, f"Expected LL, got {result}"
    print("  ✓ Lower Low classification passed")

    # Test Equal High
    prev = Pivot(
        timestamp=datetime.now(),
        price=Decimal("100.00"),
        is_high=True,
        strength=3,
        bar_index=0,
    )
    curr = Pivot(
        timestamp=datetime.now(),
        price=Decimal("100.05"),
        is_high=True,
        strength=3,
        bar_index=5,
    )

    result = classify_pivot_relationship(prev, curr, tolerance=Decimal("0.001"))
    assert result == SwingType.EH, f"Expected EH, got {result}"
    print("  ✓ Equal High classification passed")


def run_all_tests():
    tests = [
        test_n_bar_3_detection,
        test_zigzag_detection,
        test_pivot_classification,
    ]

    passed = 0
    failed = 0

    print("\nRunning SMC pivot tests...\n")

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test_func.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test_func.__name__} error: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Tests passed: {passed}")
    print(f"Tests failed: {failed}")
    print(f"{'='*50}\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)