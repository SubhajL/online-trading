from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.smc.structure import (
    detect_bos,
    detect_choch,
    get_key_levels,
    update_structure_state,
)
from app.engine.types import Pivot, StructureState, StructureTracker, SMCEventKind


def create_pivot(price: Decimal, is_high: bool, bar_index: int) -> Pivot:
    return Pivot(
        timestamp=datetime.now() + timedelta(minutes=bar_index * 5),
        price=price,
        is_high=is_high,
        strength=3,
        bar_index=bar_index,
    )


def create_tracker() -> StructureTracker:
    return StructureTracker(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
    )


class TestStructureStateTracking:
    def test_initial_state_is_neutral(self) -> None:
        tracker = create_tracker()
        assert tracker.state == StructureState.NEUTRAL

    def test_bullish_structure_formation(self) -> None:
        tracker = create_tracker()

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
        assert tracker.last_hh is not None
        assert tracker.last_hl is not None
        assert tracker.last_hh.price == Decimal("120")
        assert tracker.last_hl.price == Decimal("105")

    def test_bearish_structure_formation(self) -> None:
        tracker = create_tracker()

        # Add pivots forming LH and LL
        pivots = [
            create_pivot(Decimal("120"), True, 0),   # High
            create_pivot(Decimal("110"), False, 1),  # Low
            create_pivot(Decimal("115"), True, 2),   # Lower High
            create_pivot(Decimal("100"), False, 3),  # Lower Low
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.BEARISH
        assert tracker.last_lh is not None
        assert tracker.last_ll is not None
        assert tracker.last_lh.price == Decimal("115")
        assert tracker.last_ll.price == Decimal("100")

    def test_pivot_history_maintenance(self) -> None:
        tracker = create_tracker()
        tracker.max_pivots = 5

        # Add more pivots than max_pivots
        for i in range(10):
            pivot = create_pivot(Decimal(str(100 + i)), i % 2 == 0, i)
            update_structure_state(tracker, pivot)

        assert len(tracker.pivots) == 5
        # Oldest pivots should be removed
        assert tracker.pivots[0].pivot.bar_index == 5


class TestCHOCHDetection:
    def test_bearish_to_bullish_choch(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BEARISH
        tracker.last_lh = create_pivot(Decimal("110"), True, 10)

        # Price closes above last LH
        close_price = Decimal("112")
        close_bar_index = 15

        event = detect_choch(tracker, close_price, close_bar_index, datetime.now())

        assert event is not None
        assert event.kind == SMCEventKind.CHOCH
        assert event.from_state == StructureState.BEARISH
        assert event.to_state == StructureState.BULLISH
        assert event.price == close_price
        assert event.reference_pivot == tracker.last_lh

    def test_bullish_to_bearish_choch(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BULLISH
        tracker.last_hl = create_pivot(Decimal("100"), False, 10)

        # Price closes below last HL
        close_price = Decimal("98")
        close_bar_index = 15

        event = detect_choch(tracker, close_price, close_bar_index, datetime.now())

        assert event is not None
        assert event.kind == SMCEventKind.CHOCH
        assert event.from_state == StructureState.BULLISH
        assert event.to_state == StructureState.BEARISH
        assert event.price == close_price
        assert event.reference_pivot == tracker.last_hl

    def test_no_choch_when_neutral(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.NEUTRAL

        event = detect_choch(tracker, Decimal("100"), 10, datetime.now())
        assert event is None

    def test_no_choch_without_key_levels(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BULLISH
        # No HL set

        event = detect_choch(tracker, Decimal("90"), 10, datetime.now())
        assert event is None


class TestBOSDetection:
    def test_bullish_bos_on_hh_break(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BULLISH
        tracker.last_hh = create_pivot(Decimal("120"), True, 10)

        # Price closes above last HH
        close_price = Decimal("122")
        close_bar_index = 15

        event = detect_bos(tracker, close_price, close_bar_index, datetime.now())

        assert event is not None
        assert event.kind == SMCEventKind.BOS
        assert event.from_state == StructureState.BULLISH
        assert event.to_state == StructureState.BULLISH
        assert event.price == close_price
        assert event.reference_pivot == tracker.last_hh

    def test_bearish_bos_on_ll_break(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BEARISH
        tracker.last_ll = create_pivot(Decimal("90"), False, 10)

        # Price closes below last LL
        close_price = Decimal("88")
        close_bar_index = 15

        event = detect_bos(tracker, close_price, close_bar_index, datetime.now())

        assert event is not None
        assert event.kind == SMCEventKind.BOS
        assert event.from_state == StructureState.BEARISH
        assert event.to_state == StructureState.BEARISH
        assert event.price == close_price
        assert event.reference_pivot == tracker.last_ll

    def test_no_bos_when_neutral(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.NEUTRAL

        event = detect_bos(tracker, Decimal("100"), 10, datetime.now())
        assert event is None

    def test_no_bos_without_extreme_levels(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BULLISH
        # No HH set

        event = detect_bos(tracker, Decimal("200"), 10, datetime.now())
        assert event is None


class TestKeyLevels:
    def test_get_key_levels_bullish(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BULLISH
        tracker.last_hh = create_pivot(Decimal("120"), True, 10)
        tracker.last_hl = create_pivot(Decimal("105"), False, 8)

        levels = get_key_levels(tracker)

        assert levels["state"] == StructureState.BULLISH
        assert levels["last_hh"] == Decimal("120")
        assert levels["last_hl"] == Decimal("105")
        assert levels.get("last_lh") is None
        assert levels.get("last_ll") is None

    def test_get_key_levels_bearish(self) -> None:
        tracker = create_tracker()
        tracker.state = StructureState.BEARISH
        tracker.last_lh = create_pivot(Decimal("110"), True, 10)
        tracker.last_ll = create_pivot(Decimal("95"), False, 8)

        levels = get_key_levels(tracker)

        assert levels["state"] == StructureState.BEARISH
        assert levels["last_lh"] == Decimal("110")
        assert levels["last_ll"] == Decimal("95")
        assert levels.get("last_hh") is None
        assert levels.get("last_hl") is None

    def test_get_key_levels_neutral(self) -> None:
        tracker = create_tracker()

        levels = get_key_levels(tracker)

        assert levels["state"] == StructureState.NEUTRAL
        assert len(levels) == 1  # Only state, no price levels


class TestCompleteSequences:
    def test_full_bullish_to_bearish_sequence(self) -> None:
        tracker = create_tracker()

        # Build bullish structure
        pivots = [
            create_pivot(Decimal("100"), False, 0),  # Low
            create_pivot(Decimal("110"), True, 1),   # High
            create_pivot(Decimal("105"), False, 2),  # Higher Low
            create_pivot(Decimal("120"), True, 3),   # Higher High - confirms bullish
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.BULLISH

        # Test BOS on HH break
        bos_event = detect_bos(tracker, Decimal("122"), 4, datetime.now())
        assert bos_event is not None
        assert bos_event.kind == SMCEventKind.BOS

        # Test CHOCH when price breaks below HL
        choch_event = detect_choch(tracker, Decimal("103"), 5, datetime.now())
        assert choch_event is not None
        assert choch_event.kind == SMCEventKind.CHOCH
        assert choch_event.to_state == StructureState.BEARISH

    def test_full_bearish_to_bullish_sequence(self) -> None:
        tracker = create_tracker()

        # Build bearish structure
        pivots = [
            create_pivot(Decimal("120"), True, 0),   # High
            create_pivot(Decimal("110"), False, 1),  # Low
            create_pivot(Decimal("115"), True, 2),   # Lower High
            create_pivot(Decimal("100"), False, 3),  # Lower Low - confirms bearish
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.BEARISH

        # Test BOS on LL break
        bos_event = detect_bos(tracker, Decimal("98"), 4, datetime.now())
        assert bos_event is not None
        assert bos_event.kind == SMCEventKind.BOS

        # Test CHOCH when price breaks above LH
        choch_event = detect_choch(tracker, Decimal("117"), 5, datetime.now())
        assert choch_event is not None
        assert choch_event.kind == SMCEventKind.CHOCH
        assert choch_event.to_state == StructureState.BULLISH