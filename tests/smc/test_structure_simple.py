#!/usr/bin/env python3
"""Simplified test runner for structure tracking without dependencies"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.engine.smc.structure import (
    detect_bos,
    detect_choch,
    get_key_levels,
    update_structure_state,
)
from app.engine.smc_types import (
    Pivot,
    SMCEventKind,
    StructureState,
    StructureTracker,
    TimeFrame,
)


def create_pivot(price: Decimal, is_high: bool, bar_index: int) -> Pivot:
    return Pivot(
        timestamp=datetime.now() + timedelta(minutes=bar_index * 5),
        price=price,
        is_high=is_high,
        strength=3,
        bar_index=bar_index,
    )


def test_bullish_structure_formation():
    print("Testing bullish structure formation...")
    tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5)

    # Add pivots forming HH and HL
    pivots = [
        create_pivot(Decimal("100"), False, 0),  # Low
        create_pivot(Decimal("110"), True, 1),   # High
        create_pivot(Decimal("105"), False, 2),  # Higher Low
        create_pivot(Decimal("120"), True, 3),   # Higher High
    ]

    for pivot in pivots:
        update_structure_state(tracker, pivot)

    assert tracker.state == StructureState.BULLISH
    assert tracker.last_hh.price == Decimal("120")
    assert tracker.last_hl.price == Decimal("105")
    print("  ✓ Bullish structure test passed")


def test_bearish_choch_detection():
    print("Testing bearish CHOCH detection...")
    tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5)
    tracker.state = StructureState.BULLISH
    tracker.last_hl = create_pivot(Decimal("100"), False, 10)

    # Price closes below last HL
    event = detect_choch(tracker, Decimal("98"), 15, datetime.now())

    assert event is not None
    assert event.kind == SMCEventKind.CHOCH
    assert event.from_state == StructureState.BULLISH
    assert event.to_state == StructureState.BEARISH
    assert event.price == Decimal("98")
    print("  ✓ Bearish CHOCH test passed")


def test_bullish_bos_detection():
    print("Testing bullish BOS detection...")
    tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5)
    tracker.state = StructureState.BULLISH
    tracker.last_hh = create_pivot(Decimal("120"), True, 10)

    # Price closes above last HH
    event = detect_bos(tracker, Decimal("122"), 15, datetime.now())

    assert event is not None
    assert event.kind == SMCEventKind.BOS
    assert event.from_state == StructureState.BULLISH
    assert event.to_state == StructureState.BULLISH
    assert event.price == Decimal("122")
    print("  ✓ Bullish BOS test passed")


def test_key_levels():
    print("Testing key levels extraction...")
    tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5)
    tracker.state = StructureState.BULLISH
    tracker.last_hh = create_pivot(Decimal("120"), True, 10)
    tracker.last_hl = create_pivot(Decimal("105"), False, 8)

    levels = get_key_levels(tracker)

    assert levels["state"] == StructureState.BULLISH
    assert levels["last_hh"] == Decimal("120")
    assert levels["last_hl"] == Decimal("105")
    print("  ✓ Key levels test passed")


if __name__ == "__main__":
    print("\nRunning structure tracking tests...\n")

    tests = [
        test_bullish_structure_formation,
        test_bearish_choch_detection,
        test_bullish_bos_detection,
        test_key_levels,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test_func.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test_func.__name__} error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Tests passed: {passed}")
    print(f"Tests failed: {failed}")
    print(f"{'='*50}\n")

    sys.exit(0 if failed == 0 else 1)