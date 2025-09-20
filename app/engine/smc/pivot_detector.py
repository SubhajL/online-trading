"""
Pivot Point Detector

Identifies swing highs and swing lows in price data for Smart Money Concepts analysis.
Implements various pivot detection algorithms with configurable sensitivity.
"""

import logging
from collections import deque
from decimal import Decimal
from typing import List, Optional, Dict, Tuple
from datetime import datetime

from ..models import Candle, PivotPoint, TimeFrame


logger = logging.getLogger(__name__)


class PivotDetector:
    """
    Detects pivot points (swing highs and lows) in candlestick data.

    Uses configurable lookback periods to identify significant highs and lows
    that can be used for Smart Money Concepts analysis.
    """

    def __init__(
        self,
        left_bars: int = 5,
        right_bars: int = 5,
        min_strength: int = 1,
        max_strength: int = 10,
    ):
        """
        Initialize pivot detector

        Args:
            left_bars: Number of bars to look back from pivot candidate
            right_bars: Number of bars to look forward from pivot candidate
            min_strength: Minimum strength requirement for pivot validation
            max_strength: Maximum strength value for scaling
        """
        self.left_bars = left_bars
        self.right_bars = right_bars
        self.min_strength = min_strength
        self.max_strength = max_strength

        # Buffer for candles needed for pivot detection
        self._candle_buffer = deque(maxlen=left_bars + right_bars + 1)
        self._confirmed_pivots: List[PivotPoint] = []

        logger.info(
            f"PivotDetector initialized with left_bars={left_bars}, "
            f"right_bars={right_bars}"
        )

    def add_candle(self, candle: Candle) -> List[PivotPoint]:
        """
        Add a new candle and detect any confirmed pivots

        Args:
            candle: New candle to process

        Returns:
            List of newly confirmed pivot points
        """
        self._candle_buffer.append(candle)
        new_pivots = []

        # Need enough candles for detection
        if len(self._candle_buffer) >= self.left_bars + self.right_bars + 1:
            # Check for pivot at the position that now has enough right-side bars
            pivot_idx = self.left_bars
            pivot_candle = self._candle_buffer[pivot_idx]

            # Check for swing high
            high_pivot = self._detect_swing_high(pivot_idx)
            if high_pivot:
                new_pivots.append(high_pivot)
                self._confirmed_pivots.append(high_pivot)

            # Check for swing low
            low_pivot = self._detect_swing_low(pivot_idx)
            if low_pivot:
                new_pivots.append(low_pivot)
                self._confirmed_pivots.append(low_pivot)

        return new_pivots

    def _detect_swing_high(self, pivot_idx: int) -> Optional[PivotPoint]:
        """
        Detect swing high at the given index

        Args:
            pivot_idx: Index in buffer to check for swing high

        Returns:
            PivotPoint if swing high detected, None otherwise
        """
        try:
            pivot_candle = self._candle_buffer[pivot_idx]
            pivot_high = pivot_candle.high_price

            # Check left side - all highs should be lower
            for i in range(pivot_idx - self.left_bars, pivot_idx):
                if self._candle_buffer[i].high_price >= pivot_high:
                    return None

            # Check right side - all highs should be lower
            for i in range(pivot_idx + 1, pivot_idx + self.right_bars + 1):
                if self._candle_buffer[i].high_price >= pivot_high:
                    return None

            # Calculate strength based on price distance and volume
            strength = self._calculate_pivot_strength(pivot_idx, is_high=True)

            if strength >= self.min_strength:
                return PivotPoint(
                    symbol=pivot_candle.symbol,
                    timeframe=pivot_candle.timeframe,
                    timestamp=pivot_candle.open_time,
                    price=pivot_high,
                    is_high=True,
                    strength=min(strength, self.max_strength),
                    volume_profile=pivot_candle.volume,
                )

        except Exception as e:
            logger.error(f"Error detecting swing high: {e}")

        return None

    def _detect_swing_low(self, pivot_idx: int) -> Optional[PivotPoint]:
        """
        Detect swing low at the given index

        Args:
            pivot_idx: Index in buffer to check for swing low

        Returns:
            PivotPoint if swing low detected, None otherwise
        """
        try:
            pivot_candle = self._candle_buffer[pivot_idx]
            pivot_low = pivot_candle.low_price

            # Check left side - all lows should be higher
            for i in range(pivot_idx - self.left_bars, pivot_idx):
                if self._candle_buffer[i].low_price <= pivot_low:
                    return None

            # Check right side - all lows should be higher
            for i in range(pivot_idx + 1, pivot_idx + self.right_bars + 1):
                if self._candle_buffer[i].low_price <= pivot_low:
                    return None

            # Calculate strength based on price distance and volume
            strength = self._calculate_pivot_strength(pivot_idx, is_high=False)

            if strength >= self.min_strength:
                return PivotPoint(
                    symbol=pivot_candle.symbol,
                    timeframe=pivot_candle.timeframe,
                    timestamp=pivot_candle.open_time,
                    price=pivot_low,
                    is_high=False,
                    strength=min(strength, self.max_strength),
                    volume_profile=pivot_candle.volume,
                )

        except Exception as e:
            logger.error(f"Error detecting swing low: {e}")

        return None

    def _calculate_pivot_strength(self, pivot_idx: int, is_high: bool) -> int:
        """
        Calculate the strength of a pivot point

        Args:
            pivot_idx: Index of the pivot in the buffer
            is_high: True if calculating for swing high, False for swing low

        Returns:
            Strength value (1-10)
        """
        try:
            pivot_candle = self._candle_buffer[pivot_idx]
            pivot_price = pivot_candle.high_price if is_high else pivot_candle.low_price

            # Calculate price distance factor
            distances = []

            # Distance from left side bars
            for i in range(pivot_idx - self.left_bars, pivot_idx):
                candle = self._candle_buffer[i]
                compare_price = candle.high_price if is_high else candle.low_price

                if is_high:
                    distance = abs(pivot_price - compare_price) / pivot_price
                else:
                    distance = abs(compare_price - pivot_price) / pivot_price

                distances.append(distance)

            # Distance from right side bars
            for i in range(pivot_idx + 1, pivot_idx + self.right_bars + 1):
                candle = self._candle_buffer[i]
                compare_price = candle.high_price if is_high else candle.low_price

                if is_high:
                    distance = abs(pivot_price - compare_price) / pivot_price
                else:
                    distance = abs(compare_price - pivot_price) / pivot_price

                distances.append(distance)

            # Base strength on average distance (larger distance = stronger pivot)
            avg_distance = sum(distances) / len(distances) if distances else 0
            distance_strength = min(int(avg_distance * 1000), 5)  # Scale to 0-5

            # Volume strength (higher volume = stronger pivot)
            volume_avg = sum(candle.volume for candle in self._candle_buffer) / len(
                self._candle_buffer
            )
            volume_ratio = (
                float(pivot_candle.volume / volume_avg) if volume_avg > 0 else 1
            )
            volume_strength = min(int(volume_ratio), 5)  # Scale to 0-5

            # Combine factors
            total_strength = distance_strength + volume_strength

            return max(self.min_strength, min(total_strength, self.max_strength))

        except Exception as e:
            logger.error(f"Error calculating pivot strength: {e}")
            return self.min_strength

    def get_recent_pivots(self, count: int = 20) -> List[PivotPoint]:
        """
        Get the most recent confirmed pivots

        Args:
            count: Number of recent pivots to return

        Returns:
            List of recent PivotPoint objects
        """
        return self._confirmed_pivots[-count:] if self._confirmed_pivots else []

    def get_pivots_in_range(
        self, start_time: datetime, end_time: datetime
    ) -> List[PivotPoint]:
        """
        Get pivots within a specific time range

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of PivotPoint objects in the time range
        """
        return [
            pivot
            for pivot in self._confirmed_pivots
            if start_time <= pivot.timestamp <= end_time
        ]

    def get_swing_highs(self, count: int = 10) -> List[PivotPoint]:
        """
        Get recent swing highs

        Args:
            count: Number of swing highs to return

        Returns:
            List of swing high PivotPoint objects
        """
        highs = [pivot for pivot in self._confirmed_pivots if pivot.is_high]
        return highs[-count:] if highs else []

    def get_swing_lows(self, count: int = 10) -> List[PivotPoint]:
        """
        Get recent swing lows

        Args:
            count: Number of swing lows to return

        Returns:
            List of swing low PivotPoint objects
        """
        lows = [pivot for pivot in self._confirmed_pivots if not pivot.is_high]
        return lows[-count:] if lows else []

    def get_highest_pivot(self, count: int = 50) -> Optional[PivotPoint]:
        """
        Get the highest swing high from recent pivots

        Args:
            count: Number of recent pivots to consider

        Returns:
            Highest PivotPoint or None
        """
        recent_highs = self.get_swing_highs(count)
        if not recent_highs:
            return None

        return max(recent_highs, key=lambda p: p.price)

    def get_lowest_pivot(self, count: int = 50) -> Optional[PivotPoint]:
        """
        Get the lowest swing low from recent pivots

        Args:
            count: Number of recent pivots to consider

        Returns:
            Lowest PivotPoint or None
        """
        recent_lows = self.get_swing_lows(count)
        if not recent_lows:
            return None

        return min(recent_lows, key=lambda p: p.price)

    def detect_double_top(
        self, tolerance: float = 0.001
    ) -> Optional[Tuple[PivotPoint, PivotPoint]]:
        """
        Detect double top pattern in recent pivots

        Args:
            tolerance: Price tolerance for considering peaks equal (as percentage)

        Returns:
            Tuple of (first_peak, second_peak) if double top detected
        """
        highs = self.get_swing_highs(10)
        if len(highs) < 2:
            return None

        for i in range(len(highs) - 1):
            for j in range(i + 1, len(highs)):
                peak1, peak2 = highs[i], highs[j]
                price_diff = abs(peak1.price - peak2.price) / max(
                    peak1.price, peak2.price
                )

                if price_diff <= tolerance:
                    return (peak1, peak2)

        return None

    def detect_double_bottom(
        self, tolerance: float = 0.001
    ) -> Optional[Tuple[PivotPoint, PivotPoint]]:
        """
        Detect double bottom pattern in recent pivots

        Args:
            tolerance: Price tolerance for considering troughs equal (as percentage)

        Returns:
            Tuple of (first_trough, second_trough) if double bottom detected
        """
        lows = self.get_swing_lows(10)
        if len(lows) < 2:
            return None

        for i in range(len(lows) - 1):
            for j in range(i + 1, len(lows)):
                trough1, trough2 = lows[i], lows[j]
                price_diff = abs(trough1.price - trough2.price) / max(
                    trough1.price, trough2.price
                )

                if price_diff <= tolerance:
                    return (trough1, trough2)

        return None

    def clear_history(self):
        """Clear all stored pivot history"""
        self._confirmed_pivots.clear()
        self._candle_buffer.clear()
        logger.info("Cleared pivot detector history")

    def get_statistics(self) -> Dict:
        """Get pivot detection statistics"""
        if not self._confirmed_pivots:
            return {
                "total_pivots": 0,
                "swing_highs": 0,
                "swing_lows": 0,
                "average_strength": 0,
                "strongest_pivot": None,
            }

        highs = [p for p in self._confirmed_pivots if p.is_high]
        lows = [p for p in self._confirmed_pivots if not p.is_high]

        avg_strength = sum(p.strength for p in self._confirmed_pivots) / len(
            self._confirmed_pivots
        )
        strongest = max(self._confirmed_pivots, key=lambda p: p.strength)

        return {
            "total_pivots": len(self._confirmed_pivots),
            "swing_highs": len(highs),
            "swing_lows": len(lows),
            "average_strength": round(avg_strength, 2),
            "strongest_pivot": {
                "price": strongest.price,
                "strength": strongest.strength,
                "is_high": strongest.is_high,
                "timestamp": strongest.timestamp,
            },
        }
