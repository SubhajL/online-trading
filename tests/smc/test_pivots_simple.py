#!/usr/bin/env python3
"""Simplified test runner for pivot detection without dependencies"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

# Simple test data structures
class TimeFrame(str, Enum):
    M5 = "5m"

class SwingType(str, Enum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"
    EH = "EH"
    EL = "EL"

class Candle:
    def __init__(self, high_price, low_price, close_time, bar_index):
        self.high_price = high_price
        self.low_price = low_price
        self.close_time = close_time
        self.bar_index = bar_index

class Pivot:
    def __init__(self, timestamp, price, is_high, strength, bar_index):
        self.timestamp = timestamp
        self.price = price
        self.is_high = is_high
        self.strength = strength
        self.bar_index = bar_index


# Copy of pivot detection functions
def detect_n_bar_pivots(candles: list[Candle], n: int = 3) -> list[Pivot]:
    if len(candles) < n:
        return []

    pivots = []
    half_n = n // 2

    for i in range(half_n, len(candles) - half_n):
        current = candles[i]

        # Check for swing high
        is_high = True
        for j in range(i - half_n, i + half_n + 1):
            if j != i and candles[j].high_price > current.high_price:
                is_high = False
                break

        if is_high:
            pivots.append(
                Pivot(
                    timestamp=current.close_time,
                    price=current.high_price,
                    is_high=True,
                    strength=n,
                    bar_index=current.bar_index,
                )
            )

        # Check for swing low
        is_low = True
        for j in range(i - half_n, i + half_n + 1):
            if j != i and candles[j].low_price < current.low_price:
                is_low = False
                break

        if is_low:
            pivots.append(
                Pivot(
                    timestamp=current.close_time,
                    price=current.low_price,
                    is_high=False,
                    strength=n,
                    bar_index=current.bar_index,
                )
            )

    return pivots


def classify_pivot_relationship(
    prev_pivot: Pivot,
    curr_pivot: Pivot,
    tolerance: Decimal = Decimal("0.0001"),
) -> SwingType | None:
    if prev_pivot.is_high != curr_pivot.is_high:
        return None

    price_diff = curr_pivot.price - prev_pivot.price
    relative_diff = abs(price_diff) / prev_pivot.price

    if relative_diff <= tolerance:
        return SwingType.EH if prev_pivot.is_high else SwingType.EL

    if prev_pivot.is_high:
        return SwingType.HH if price_diff > 0 else SwingType.LH
    else:
        return SwingType.HL if price_diff > 0 else SwingType.LL


# Tests
def test_n_bar_detection():
    print("Testing N-bar pivot detection...")
    base_time = datetime(2024, 1, 1)

    prices = [
        (100, 90),   # 0
        (105, 92),   # 1
        (110, 100),  # 2 - high
        (109, 103),  # 3
        (107, 101),  # 4 - low
        (108, 100),  # 5
        (115, 106),  # 6 - high
        (112, 107),  # 7
        (111, 105),  # 8
    ]

    candles = []
    for i, (h, l) in enumerate(prices):
        candles.append(
            Candle(
                high_price=Decimal(str(h)),
                low_price=Decimal(str(l)),
                close_time=base_time + timedelta(minutes=5*i),
                bar_index=i,
            )
        )

    pivots = detect_n_bar_pivots(candles, n=3)

    high_pivots = [p for p in pivots if p.is_high]
    low_pivots = [p for p in pivots if not p.is_high]

    print(f"  Found {len(pivots)} pivots ({len(high_pivots)} highs, {len(low_pivots)} lows)")

    # With n=3, we should get pivots at indices that have at least 1 bar on each side
    # So valid indices are 1 through 7 (with 0-8 total indices)
    assert len(pivots) >= 2, f"Expected at least 2 pivots, got {len(pivots)}"

    if high_pivots:
        assert high_pivots[0].price == Decimal("110"), f"Expected first high at 110, got {high_pivots[0].price}"
        assert high_pivots[0].bar_index == 2, f"Expected first high at index 2, got {high_pivots[0].bar_index}"

    if len(high_pivots) >= 2:
        assert high_pivots[1].price == Decimal("115"), f"Expected second high at 115, got {high_pivots[1].price}"
        assert high_pivots[1].bar_index == 6, f"Expected second high at index 6, got {high_pivots[1].bar_index}"

    print("  ✓ Test passed")


def test_pivot_classification():
    print("Testing pivot classification...")

    # Test HH
    prev = Pivot(datetime.now(), Decimal("100"), True, 3, 0)
    curr = Pivot(datetime.now(), Decimal("110"), True, 3, 5)
    assert classify_pivot_relationship(prev, curr) == SwingType.HH
    print("  ✓ HH classification passed")

    # Test LL
    prev = Pivot(datetime.now(), Decimal("90"), False, 3, 0)
    curr = Pivot(datetime.now(), Decimal("85"), False, 3, 5)
    assert classify_pivot_relationship(prev, curr) == SwingType.LL
    print("  ✓ LL classification passed")

    # Test EH
    prev = Pivot(datetime.now(), Decimal("100.00"), True, 3, 0)
    curr = Pivot(datetime.now(), Decimal("100.05"), True, 3, 5)
    assert classify_pivot_relationship(prev, curr, Decimal("0.001")) == SwingType.EH
    print("  ✓ EH classification passed")


if __name__ == "__main__":
    print("\nRunning simplified pivot tests...\n")

    try:
        test_n_bar_detection()
        test_pivot_classification()
        print("\n✅ All tests passed!\n")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)