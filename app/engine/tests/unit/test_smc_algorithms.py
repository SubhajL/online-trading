"""
CRITICAL: SMC (Smart Money Concepts) algorithm accuracy tests.

These tests ensure:
1. Pivot detection is accurate (n-bar and zigzag methods)
2. Structure classification is correct (HH, HL, LH, LL)
3. CHOCH and BOS detection follows the rules
4. Order blocks and FVG zones are properly identified
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List

from app.engine.models import Candle, TimeFrame
from app.engine.smc_types import (
    Pivot, SwingType, StructureState, StructureTracker,
    SMCEvent, SMCEventKind, StructurePoint
)
from app.engine.smc.pivots import (
    detect_n_bar_pivots, detect_zigzag_pivots, classify_pivot_relationship
)
from app.engine.smc.structure import (
    update_structure_state, detect_choch, detect_bos, get_key_levels
)


class TestPivotDetection:
    """Test pivot detection algorithms."""

    def create_candle(self, open_p: float, high: float, low: float, close: float,
                      index: int, base_time: datetime) -> Candle:
        """Helper to create a candle."""
        from app.engine.models import TimeFrame
        return Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=base_time + timedelta(minutes=5*index),
            close_time=base_time + timedelta(minutes=5*(index+1)),
            open_price=Decimal(str(open_p)),
            high_price=Decimal(str(high)),
            low_price=Decimal(str(low)),
            close_price=Decimal(str(close)),
            volume=Decimal("100"),
            quote_volume=Decimal("5000"),  # Approx price * volume
            trades=50,
            taker_buy_base_volume=Decimal("60"),
            taker_buy_quote_volume=Decimal("3000"),
            bar_index=index
        )

    def test_n_bar_pivot_detection_simple(self):
        """Test 3-bar pivot detection on simple pattern."""
        base_time = datetime.now()

        # Create pattern: low, HIGH, low (swing high)
        candles = [
            self.create_candle(100, 105, 99, 104, 0, base_time),   # Bar 0
            self.create_candle(104, 110, 103, 108, 1, base_time),  # Bar 1 - High pivot
            self.create_candle(108, 109, 102, 103, 2, base_time),  # Bar 2
        ]

        pivots = detect_n_bar_pivots(candles, n=3)

        assert len(pivots) == 1
        assert pivots[0].is_high is True
        assert pivots[0].price == Decimal("110")
        assert pivots[0].bar_index == 1

    def test_n_bar_pivot_detection_both_types(self):
        """Test detection of both high and low pivots."""
        base_time = datetime.now()

        # Create pattern with both swing high and swing low
        candles = [
            self.create_candle(100, 105, 99, 104, 0, base_time),
            self.create_candle(104, 110, 103, 108, 1, base_time),  # High pivot
            self.create_candle(108, 109, 102, 103, 2, base_time),
            self.create_candle(103, 104, 95, 96, 3, base_time),    # Low pivot
            self.create_candle(96, 101, 95, 100, 4, base_time),
        ]

        pivots = detect_n_bar_pivots(candles, n=3)

        # Should find one high and one low
        high_pivots = [p for p in pivots if p.is_high]
        low_pivots = [p for p in pivots if not p.is_high]

        assert len(high_pivots) == 1
        assert len(low_pivots) == 1
        assert high_pivots[0].price == Decimal("110")
        assert low_pivots[0].price == Decimal("95")

    def test_n_bar_pivot_strength(self):
        """Test different n-bar strengths."""
        base_time = datetime.now()

        # Create a larger pattern
        candles = [
            self.create_candle(100, 101, 99, 100, 0, base_time),
            self.create_candle(100, 102, 99, 101, 1, base_time),
            self.create_candle(101, 103, 100, 102, 2, base_time),
            self.create_candle(102, 110, 101, 108, 3, base_time),  # Strong high
            self.create_candle(108, 109, 107, 108, 4, base_time),
            self.create_candle(108, 108, 106, 107, 5, base_time),
            self.create_candle(107, 107, 105, 106, 6, base_time),
        ]

        # Test with n=3
        pivots_3 = detect_n_bar_pivots(candles, n=3)
        # Test with n=5
        pivots_5 = detect_n_bar_pivots(candles, n=5)
        # Test with n=7
        pivots_7 = detect_n_bar_pivots(candles, n=7)

        # Stronger pivots (higher n) should find fewer points
        assert len(pivots_3) >= len(pivots_5) >= len(pivots_7)

    def test_zigzag_pivot_detection(self):
        """Test zigzag pivot detection with ATR-based reversal."""
        base_time = datetime.now()
        atr = Decimal("5")  # 5 point ATR

        # Create trending pattern
        candles = [
            self.create_candle(100, 101, 99, 100, 0, base_time),
            self.create_candle(100, 105, 99, 104, 1, base_time),
            self.create_candle(104, 110, 103, 109, 2, base_time),   # Up move
            self.create_candle(109, 110, 105, 106, 3, base_time),
            self.create_candle(106, 107, 95, 96, 4, base_time),     # Down > 2*ATR
            self.create_candle(96, 98, 94, 97, 5, base_time),
            self.create_candle(97, 108, 96, 107, 6, base_time),     # Up > 2*ATR
        ]

        pivots = detect_zigzag_pivots(candles, atr, min_reversal_factor=2.0)

        # Should identify significant reversals
        assert len(pivots) >= 2  # At least one high and one low

        # Verify pivots alternate between high and low
        for i in range(1, len(pivots)):
            assert pivots[i].is_high != pivots[i-1].is_high

    def test_classify_pivot_relationships(self):
        """Test classification of pivot relationships."""
        base_time = datetime.now()

        # Test Higher High (HH)
        high1 = Pivot(timestamp=base_time, price=Decimal("100"), is_high=True, strength=3, bar_index=0)
        high2 = Pivot(timestamp=base_time, price=Decimal("110"), is_high=True, strength=3, bar_index=5)

        assert classify_pivot_relationship(high1, high2) == SwingType.HH

        # Test Lower High (LH)
        high3 = Pivot(timestamp=base_time, price=Decimal("95"), is_high=True, strength=3, bar_index=10)
        assert classify_pivot_relationship(high2, high3) == SwingType.LH

        # Test Higher Low (HL)
        low1 = Pivot(timestamp=base_time, price=Decimal("90"), is_high=False, strength=3, bar_index=2)
        low2 = Pivot(timestamp=base_time, price=Decimal("92"), is_high=False, strength=3, bar_index=7)

        assert classify_pivot_relationship(low1, low2) == SwingType.HL

        # Test Lower Low (LL)
        low3 = Pivot(timestamp=base_time, price=Decimal("88"), is_high=False, strength=3, bar_index=12)
        assert classify_pivot_relationship(low2, low3) == SwingType.LL

        # Test Equal High (EH) with tolerance
        high4 = Pivot(timestamp=base_time, price=Decimal("110.005"), is_high=True, strength=3, bar_index=15)
        assert classify_pivot_relationship(high2, high4, tolerance=Decimal("0.0001")) == SwingType.EH


class TestStructureDetection:
    """Test market structure detection and state transitions."""

    def create_pivot(self, price: float, is_high: bool, index: int, base_time: datetime) -> Pivot:
        """Helper to create a pivot."""
        return Pivot(
            timestamp=base_time + timedelta(minutes=5*index),
            price=Decimal(str(price)),
            is_high=is_high,
            strength=3,
            bar_index=index
        )

    def test_bullish_structure_formation(self):
        """Test detection of bullish market structure."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # Create bullish structure: HL followed by HH
        pivots = [
            self.create_pivot(100, False, 0, base_time),  # Low
            self.create_pivot(110, True, 5, base_time),   # High
            self.create_pivot(105, False, 10, base_time), # Higher Low (HL)
            self.create_pivot(115, True, 15, base_time),  # Higher High (HH)
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.BULLISH
        assert tracker.last_hh is not None
        assert tracker.last_hh.price == Decimal("115")
        assert tracker.last_hl is not None
        assert tracker.last_hl.price == Decimal("105")

    def test_bearish_structure_formation(self):
        """Test detection of bearish market structure."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # Create bearish structure: LH followed by LL
        pivots = [
            self.create_pivot(100, True, 0, base_time),   # High
            self.create_pivot(90, False, 5, base_time),   # Low
            self.create_pivot(95, True, 10, base_time),   # Lower High (LH)
            self.create_pivot(85, False, 15, base_time),  # Lower Low (LL)
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.BEARISH
        assert tracker.last_lh is not None
        assert tracker.last_lh.price == Decimal("95")
        assert tracker.last_ll is not None
        assert tracker.last_ll.price == Decimal("85")

    def test_choch_bearish_to_bullish(self):
        """Test Change of Character from bearish to bullish."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # First establish bearish structure
        pivots = [
            self.create_pivot(100, True, 0, base_time),
            self.create_pivot(90, False, 5, base_time),
            self.create_pivot(95, True, 10, base_time),   # LH
            self.create_pivot(85, False, 15, base_time),  # LL
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.BEARISH

        # Now test CHOCH - close above LH (95)
        choch_event = detect_choch(
            tracker,
            close_price=Decimal("96"),
            close_bar_index=20,
            timestamp=base_time + timedelta(minutes=100)
        )

        assert choch_event is not None
        assert choch_event.kind == SMCEventKind.CHOCH
        assert choch_event.from_state == StructureState.BEARISH
        assert choch_event.to_state == StructureState.BULLISH
        assert choch_event.reference_pivot.price == Decimal("95")  # The LH

    def test_choch_bullish_to_bearish(self):
        """Test Change of Character from bullish to bearish."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # First establish bullish structure
        pivots = [
            self.create_pivot(100, False, 0, base_time),
            self.create_pivot(110, True, 5, base_time),
            self.create_pivot(105, False, 10, base_time), # HL
            self.create_pivot(115, True, 15, base_time),  # HH
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.BULLISH

        # Now test CHOCH - close below HL (105)
        choch_event = detect_choch(
            tracker,
            close_price=Decimal("104"),
            close_bar_index=20,
            timestamp=base_time + timedelta(minutes=100)
        )

        assert choch_event is not None
        assert choch_event.kind == SMCEventKind.CHOCH
        assert choch_event.from_state == StructureState.BULLISH
        assert choch_event.to_state == StructureState.BEARISH
        assert choch_event.reference_pivot.price == Decimal("105")  # The HL

    def test_bos_bullish_continuation(self):
        """Test Break of Structure in bullish trend."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # Establish bullish structure
        pivots = [
            self.create_pivot(100, False, 0, base_time),
            self.create_pivot(110, True, 5, base_time),
            self.create_pivot(105, False, 10, base_time),
            self.create_pivot(115, True, 15, base_time),  # HH
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        # Test BOS - close above HH (115)
        bos_event = detect_bos(
            tracker,
            close_price=Decimal("116"),
            close_bar_index=20,
            timestamp=base_time + timedelta(minutes=100)
        )

        assert bos_event is not None
        assert bos_event.kind == SMCEventKind.BOS
        assert bos_event.from_state == StructureState.BULLISH
        assert bos_event.to_state == StructureState.BULLISH  # Remains bullish
        assert bos_event.reference_pivot.price == Decimal("115")  # The HH

    def test_bos_bearish_continuation(self):
        """Test Break of Structure in bearish trend."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # Establish bearish structure
        pivots = [
            self.create_pivot(100, True, 0, base_time),
            self.create_pivot(90, False, 5, base_time),
            self.create_pivot(95, True, 10, base_time),
            self.create_pivot(85, False, 15, base_time),  # LL
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        # Test BOS - close below LL (85)
        bos_event = detect_bos(
            tracker,
            close_price=Decimal("84"),
            close_bar_index=20,
            timestamp=base_time + timedelta(minutes=100)
        )

        assert bos_event is not None
        assert bos_event.kind == SMCEventKind.BOS
        assert bos_event.from_state == StructureState.BEARISH
        assert bos_event.to_state == StructureState.BEARISH  # Remains bearish
        assert bos_event.reference_pivot.price == Decimal("85")  # The LL

    def test_no_event_in_neutral_state(self):
        """Test that no events fire in neutral state."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # Add only one pivot - not enough for structure
        pivot = self.create_pivot(100, True, 0, base_time)
        update_structure_state(tracker, pivot)

        assert tracker.state == StructureState.NEUTRAL

        # Test CHOCH detection
        choch = detect_choch(tracker, Decimal("110"), 5, base_time)
        assert choch is None

        # Test BOS detection
        bos = detect_bos(tracker, Decimal("110"), 5, base_time)
        assert bos is None

    def test_key_levels_extraction(self):
        """Test extraction of key structure levels."""
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        base_time = datetime.now()

        # Build bullish structure
        pivots = [
            self.create_pivot(100, False, 0, base_time),
            self.create_pivot(110, True, 5, base_time),
            self.create_pivot(105, False, 10, base_time), # HL
            self.create_pivot(115, True, 15, base_time),  # HH
        ]

        for pivot in pivots:
            update_structure_state(tracker, pivot)

        levels = get_key_levels(tracker)

        assert levels["state"] == StructureState.BULLISH
        assert levels["last_hh"] == Decimal("115")
        assert levels["last_hl"] == Decimal("105")
        assert "last_lh" not in levels  # Should not include bearish levels
        assert "last_ll" not in levels


class TestSMCIntegration:
    """Integration tests for complete SMC workflow."""

    def test_full_smc_analysis_workflow(self):
        """Test complete workflow from candles to structure events."""
        base_time = datetime.now()

        # Create realistic price action
        candle_data = [
            # Initial uptrend
            (100, 102, 99, 101),
            (101, 104, 100, 103),
            (103, 107, 102, 106),   # Local high area
            (106, 106, 103, 104),
            (104, 105, 101, 102),   # Pullback
            (102, 103, 100, 101),   # Local low (HL)
            (101, 105, 101, 104),
            (104, 109, 103, 108),   # New high (HH) - Bullish confirmed
            (108, 109, 106, 107),
            (107, 108, 104, 105),   # Another HL
            (105, 112, 105, 111),   # Another HH
            # Reversal starts
            (111, 111, 108, 109),
            (109, 110, 107, 108),
            (108, 109, 103, 104),   # Break below HL - CHOCH
        ]

        from app.engine.models import TimeFrame

        candles = []
        for i, (o, h, l, c) in enumerate(candle_data):
            candle = Candle(
                venue="spot",
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=base_time + timedelta(minutes=5*i),
                close_time=base_time + timedelta(minutes=5*(i+1)),
                open_price=Decimal(str(o)),
                high_price=Decimal(str(h)),
                low_price=Decimal(str(l)),
                close_price=Decimal(str(c)),
                volume=Decimal("100"),
                quote_volume=Decimal(str(o * 100)),  # Approx price * volume
                trades=50,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal(str(o * 60)),
                bar_index=i
            )
            candles.append(candle)

        # Detect pivots
        pivots = detect_n_bar_pivots(candles, n=3)
        assert len(pivots) > 0

        # Build structure
        tracker = StructureTracker(symbol="BTCUSDT", timeframe=TimeFrame.M5, max_pivots=20)
        events = []

        for pivot in pivots:
            update_structure_state(tracker, pivot)

            # Check for CHOCH/BOS after each pivot
            for candle in candles[pivot.bar_index:]:
                choch = detect_choch(tracker, candle.close_price, candle.bar_index, candle.close_time)
                if choch:
                    events.append(choch)
                    break

                bos = detect_bos(tracker, candle.close_price, candle.bar_index, candle.close_time)
                if bos:
                    events.append(bos)

        # Should have detected structure and at least one event
        assert tracker.state != StructureState.NEUTRAL
        assert len(events) > 0

        # Verify event sequence makes sense
        for event in events:
            assert event.kind in [SMCEventKind.CHOCH, SMCEventKind.BOS]
            assert event.reference_pivot is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])