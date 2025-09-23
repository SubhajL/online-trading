#!/usr/bin/env python3
"""Isolated test for structure tracking with inline implementations"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum


# Inline types
class TimeFrame(str, Enum):
    M5 = "5m"


class StructureState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SMCEventKind(str, Enum):
    CHOCH = "CHOCH"
    BOS = "BOS"


class SwingType(str, Enum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"
    EH = "EH"
    EL = "EL"


class Pivot:
    def __init__(self, timestamp, price, is_high, strength, bar_index):
        self.timestamp = timestamp
        self.price = price
        self.is_high = is_high
        self.strength = strength
        self.bar_index = bar_index


class StructurePoint:
    def __init__(self, pivot, swing_type):
        self.pivot = pivot
        self.swing_type = swing_type


class SMCEvent:
    def __init__(self, kind, timestamp, price, from_state, to_state, trigger_pivot, reference_pivot, strength):
        self.kind = kind
        self.timestamp = timestamp
        self.price = price
        self.from_state = from_state
        self.to_state = to_state
        self.trigger_pivot = trigger_pivot
        self.reference_pivot = reference_pivot
        self.strength = strength


class StructureTracker:
    def __init__(self, symbol, timeframe):
        self.symbol = symbol
        self.timeframe = timeframe
        self.state = StructureState.NEUTRAL
        self.last_hh = None
        self.last_hl = None
        self.last_lh = None
        self.last_ll = None
        self.pivots = []
        self.max_pivots = 100


# Inline implementations
def classify_pivot_relationship(prev_pivot, curr_pivot, tolerance=Decimal("0.0001")):
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


def update_structure_state(tracker, pivot):
    last_same_type = None
    for sp in reversed(tracker.pivots):
        if sp.pivot.is_high == pivot.is_high:
            last_same_type = sp.pivot
            break

    swing_type = None
    if last_same_type:
        swing_type = classify_pivot_relationship(last_same_type, pivot)

    structure_point = StructurePoint(pivot, swing_type or SwingType.EH)
    tracker.pivots.append(structure_point)

    if len(tracker.pivots) > tracker.max_pivots:
        tracker.pivots = tracker.pivots[-tracker.max_pivots:]

    if swing_type:
        if pivot.is_high:
            if swing_type == SwingType.HH:
                tracker.last_hh = pivot
                if tracker.last_hl:
                    tracker.state = StructureState.BULLISH
            elif swing_type == SwingType.LH:
                tracker.last_lh = pivot
                if tracker.last_ll:
                    tracker.state = StructureState.BEARISH
        else:
            if swing_type == SwingType.HL:
                tracker.last_hl = pivot
                if tracker.last_hh:
                    tracker.state = StructureState.BULLISH
            elif swing_type == SwingType.LL:
                tracker.last_ll = pivot
                if tracker.last_lh:
                    tracker.state = StructureState.BEARISH


def detect_choch(tracker, close_price, close_bar_index, timestamp):
    if tracker.state == StructureState.NEUTRAL:
        return None

    if tracker.state == StructureState.BULLISH:
        if tracker.last_hl and close_price < tracker.last_hl.price:
            return SMCEvent(
                kind=SMCEventKind.CHOCH,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BULLISH,
                to_state=StructureState.BEARISH,
                trigger_pivot=Pivot(timestamp, close_price, False, 1, close_bar_index),
                reference_pivot=tracker.last_hl,
                strength=Decimal("1.0"),
            )

    elif tracker.state == StructureState.BEARISH:
        if tracker.last_lh and close_price > tracker.last_lh.price:
            return SMCEvent(
                kind=SMCEventKind.CHOCH,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BEARISH,
                to_state=StructureState.BULLISH,
                trigger_pivot=Pivot(timestamp, close_price, True, 1, close_bar_index),
                reference_pivot=tracker.last_lh,
                strength=Decimal("1.0"),
            )

    return None


def detect_bos(tracker, close_price, close_bar_index, timestamp):
    if tracker.state == StructureState.NEUTRAL:
        return None

    if tracker.state == StructureState.BULLISH:
        if tracker.last_hh and close_price > tracker.last_hh.price:
            return SMCEvent(
                kind=SMCEventKind.BOS,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BULLISH,
                to_state=StructureState.BULLISH,
                trigger_pivot=Pivot(timestamp, close_price, True, 1, close_bar_index),
                reference_pivot=tracker.last_hh,
                strength=Decimal("1.0"),
            )

    elif tracker.state == StructureState.BEARISH:
        if tracker.last_ll and close_price < tracker.last_ll.price:
            return SMCEvent(
                kind=SMCEventKind.BOS,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BEARISH,
                to_state=StructureState.BEARISH,
                trigger_pivot=Pivot(timestamp, close_price, False, 1, close_bar_index),
                reference_pivot=tracker.last_ll,
                strength=Decimal("1.0"),
            )

    return None


def get_key_levels(tracker):
    levels = {"state": tracker.state}

    if tracker.state == StructureState.BULLISH:
        if tracker.last_hh:
            levels["last_hh"] = tracker.last_hh.price
        if tracker.last_hl:
            levels["last_hl"] = tracker.last_hl.price
    elif tracker.state == StructureState.BEARISH:
        if tracker.last_lh:
            levels["last_lh"] = tracker.last_lh.price
        if tracker.last_ll:
            levels["last_ll"] = tracker.last_ll.price

    return levels


# Tests
def test_bullish_structure():
    print("Testing bullish structure formation...")
    tracker = StructureTracker("BTCUSDT", TimeFrame.M5)

    pivots = [
        Pivot(datetime.now(), Decimal("100"), False, 3, 0),  # Low
        Pivot(datetime.now(), Decimal("110"), True, 3, 1),   # High
        Pivot(datetime.now(), Decimal("105"), False, 3, 2),  # Higher Low
        Pivot(datetime.now(), Decimal("120"), True, 3, 3),   # Higher High
    ]

    for pivot in pivots:
        update_structure_state(tracker, pivot)

    assert tracker.state == StructureState.BULLISH
    assert tracker.last_hh.price == Decimal("120")
    assert tracker.last_hl.price == Decimal("105")
    print("  ✓ Test passed")


def test_choch_detection():
    print("Testing CHOCH detection...")
    tracker = StructureTracker("BTCUSDT", TimeFrame.M5)
    tracker.state = StructureState.BULLISH
    tracker.last_hl = Pivot(datetime.now(), Decimal("100"), False, 3, 10)

    event = detect_choch(tracker, Decimal("98"), 15, datetime.now())

    assert event is not None
    assert event.kind == SMCEventKind.CHOCH
    assert event.from_state == StructureState.BULLISH
    assert event.to_state == StructureState.BEARISH
    print("  ✓ Test passed")


def test_bos_detection():
    print("Testing BOS detection...")
    tracker = StructureTracker("BTCUSDT", TimeFrame.M5)
    tracker.state = StructureState.BULLISH
    tracker.last_hh = Pivot(datetime.now(), Decimal("120"), True, 3, 10)

    event = detect_bos(tracker, Decimal("122"), 15, datetime.now())

    assert event is not None
    assert event.kind == SMCEventKind.BOS
    assert event.price == Decimal("122")
    print("  ✓ Test passed")


if __name__ == "__main__":
    print("\nRunning isolated structure tests...\n")

    tests = [test_bullish_structure, test_choch_detection, test_bos_detection]

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print("\n✅ All tests passed!\n")