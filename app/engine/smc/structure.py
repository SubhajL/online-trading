from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ..smc.pivots import classify_pivot_relationship
from ..smc_types import (
    Pivot,
    SMCEvent,
    SMCEventKind,
    StructurePoint,
    StructureState,
    StructureTracker,
    SwingType,
)


def update_structure_state(tracker: StructureTracker, pivot: Pivot) -> None:
    # Find the last pivot of the same type
    last_same_type = None
    for sp in reversed(tracker.pivots):
        if sp.pivot.is_high == pivot.is_high:
            last_same_type = sp.pivot
            break

    # Classify the relationship if we have a previous pivot of the same type
    swing_type = None
    if last_same_type:
        swing_type = classify_pivot_relationship(last_same_type, pivot)

    # Add to history
    structure_point = StructurePoint(pivot=pivot, swing_type=swing_type or SwingType.EH)
    tracker.pivots.append(structure_point)

    # Maintain max pivots
    if len(tracker.pivots) > tracker.max_pivots:
        tracker.pivots = tracker.pivots[-tracker.max_pivots:]

    # Update structure based on swing type
    if swing_type:
        if pivot.is_high:
            if swing_type == SwingType.HH:
                tracker.last_hh = pivot
                if tracker.last_hl:  # Need both HH and HL for bullish
                    tracker.state = StructureState.BULLISH
            elif swing_type == SwingType.LH:
                tracker.last_lh = pivot
                if tracker.last_ll:  # Need both LH and LL for bearish
                    tracker.state = StructureState.BEARISH
        else:  # Low pivot
            if swing_type == SwingType.HL:
                tracker.last_hl = pivot
                if tracker.last_hh:  # Need both HH and HL for bullish
                    tracker.state = StructureState.BULLISH
            elif swing_type == SwingType.LL:
                tracker.last_ll = pivot
                if tracker.last_lh:  # Need both LH and LL for bearish
                    tracker.state = StructureState.BEARISH


def detect_choch(
    tracker: StructureTracker,
    close_price: Decimal,
    close_bar_index: int,
    timestamp: datetime,
) -> SMCEvent | None:
    if tracker.state == StructureState.NEUTRAL:
        return None

    if tracker.state == StructureState.BULLISH:
        # Check for close below HL (bearish CHOCH)
        if tracker.last_hl and close_price < tracker.last_hl.price:
            return SMCEvent(
                kind=SMCEventKind.CHOCH,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BULLISH,
                to_state=StructureState.BEARISH,
                trigger_pivot=Pivot(
                    timestamp=timestamp,
                    price=close_price,
                    is_high=False,
                    strength=1,
                    bar_index=close_bar_index,
                ),
                reference_pivot=tracker.last_hl,
                strength=Decimal("1.0"),
            )

    elif tracker.state == StructureState.BEARISH:
        # Check for close above LH (bullish CHOCH)
        if tracker.last_lh and close_price > tracker.last_lh.price:
            return SMCEvent(
                kind=SMCEventKind.CHOCH,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BEARISH,
                to_state=StructureState.BULLISH,
                trigger_pivot=Pivot(
                    timestamp=timestamp,
                    price=close_price,
                    is_high=True,
                    strength=1,
                    bar_index=close_bar_index,
                ),
                reference_pivot=tracker.last_lh,
                strength=Decimal("1.0"),
            )

    return None


def detect_bos(
    tracker: StructureTracker,
    close_price: Decimal,
    close_bar_index: int,
    timestamp: datetime,
) -> SMCEvent | None:
    if tracker.state == StructureState.NEUTRAL:
        return None

    if tracker.state == StructureState.BULLISH:
        # Check for close above HH (bullish BOS)
        if tracker.last_hh and close_price > tracker.last_hh.price:
            return SMCEvent(
                kind=SMCEventKind.BOS,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BULLISH,
                to_state=StructureState.BULLISH,
                trigger_pivot=Pivot(
                    timestamp=timestamp,
                    price=close_price,
                    is_high=True,
                    strength=1,
                    bar_index=close_bar_index,
                ),
                reference_pivot=tracker.last_hh,
                strength=Decimal("1.0"),
            )

    elif tracker.state == StructureState.BEARISH:
        # Check for close below LL (bearish BOS)
        if tracker.last_ll and close_price < tracker.last_ll.price:
            return SMCEvent(
                kind=SMCEventKind.BOS,
                timestamp=timestamp,
                price=close_price,
                from_state=StructureState.BEARISH,
                to_state=StructureState.BEARISH,
                trigger_pivot=Pivot(
                    timestamp=timestamp,
                    price=close_price,
                    is_high=False,
                    strength=1,
                    bar_index=close_bar_index,
                ),
                reference_pivot=tracker.last_ll,
                strength=Decimal("1.0"),
            )

    return None


def get_key_levels(tracker: StructureTracker) -> dict[str, StructureState | Decimal]:
    levels: dict[str, StructureState | Decimal] = {"state": tracker.state}

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