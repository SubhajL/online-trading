from __future__ import annotations

from decimal import Decimal

import numpy as np

from ..models import Candle
from ..smc_types import Pivot, PivotMethod, SwingType


def detect_n_bar_pivots(candles: list[Candle], n: int = 3) -> list[Pivot]:
    """Detect n-bar pivots using window comparisons with NumPy assistance.

    This preserves exact Decimal prices from input candles while using
    vectorized window max/min checks to reduce Python-level overhead.
    """
    if n <= 1:
        return []
    if len(candles) < n:
        return []

    half_n = n // 2
    highs = np.array([float(c.high_price) for c in candles], dtype=np.float64)
    lows = np.array([float(c.low_price) for c in candles], dtype=np.float64)

    pivots: list[Pivot] = []
    for i in range(half_n, len(candles) - half_n):
        current = candles[i]
        # window excluding center index for strict comparison
        w_start = i - half_n
        w_end = i + half_n + 1
        # High pivot: no neighbor strictly greater than current high
        win_highs = highs[w_start:w_end]
        if win_highs.size:
            # max excluding center
            if win_highs.size == 1:
                max_excl = -np.inf
            else:
                max_excl = max(
                    np.max(win_highs[: i - w_start]),
                    np.max(win_highs[i - w_start + 1 :]),
                )
            if highs[i] >= max_excl:
                pivots.append(
                    Pivot(
                        timestamp=current.close_time,
                        price=current.high_price,  # preserve Decimal
                        is_high=True,
                        strength=n,
                        bar_index=current.bar_index,
                    ),
                )

        # Low pivot: no neighbor strictly lower than current low
        win_lows = lows[w_start:w_end]
        if win_lows.size:
            if win_lows.size == 1:
                min_excl = np.inf
            else:
                min_excl = min(
                    np.min(win_lows[: i - w_start]), np.min(win_lows[i - w_start + 1 :])
                )
            if lows[i] <= min_excl:
                pivots.append(
                    Pivot(
                        timestamp=current.close_time,
                        price=current.low_price,  # preserve Decimal
                        is_high=False,
                        strength=n,
                        bar_index=current.bar_index,
                    ),
                )

    return pivots


def detect_zigzag_pivots(
    candles: list[Candle],
    atr_value: Decimal,
    min_reversal_factor: float = 2.0,
) -> list[Pivot]:
    if len(candles) < 2:
        return []

    pivots = []
    min_reversal = atr_value * Decimal(str(min_reversal_factor))

    # Start with the first candle's extremes
    current_high = candles[0].high_price
    current_low = candles[0].low_price
    current_high_idx = 0
    current_low_idx = 0
    last_pivot_is_high = None

    for i in range(1, len(candles)):
        candle = candles[i]

        if last_pivot_is_high is None:
            # Initial state - determine first significant move
            if candle.high_price > current_high:
                current_high = candle.high_price
                current_high_idx = i
            if candle.low_price < current_low:
                current_low = candle.low_price
                current_low_idx = i

            # Check if we have a significant move from the start
            if current_high - current_low >= min_reversal:
                if current_high_idx > current_low_idx:
                    # Low came first
                    pivots.append(
                        Pivot(
                            timestamp=candles[current_low_idx].close_time,
                            price=current_low,
                            is_high=False,
                            strength=int(min_reversal_factor),
                            bar_index=candles[current_low_idx].bar_index,
                        )
                    )
                    last_pivot_is_high = False
                    current_low = candle.low_price
                    current_low_idx = i
                else:
                    # High came first
                    pivots.append(
                        Pivot(
                            timestamp=candles[current_high_idx].close_time,
                            price=current_high,
                            is_high=True,
                            strength=int(min_reversal_factor),
                            bar_index=candles[current_high_idx].bar_index,
                        )
                    )
                    last_pivot_is_high = True
                    current_high = candle.high_price
                    current_high_idx = i

        elif last_pivot_is_high:
            # Looking for a low
            if candle.low_price < current_low:
                current_low = candle.low_price
                current_low_idx = i

            # Check for reversal to upside
            if candle.high_price > current_high:
                # Check if the down move was significant
                if pivots[-1].price - current_low >= min_reversal:
                    # Add the low pivot
                    pivots.append(
                        Pivot(
                            timestamp=candles[current_low_idx].close_time,
                            price=current_low,
                            is_high=False,
                            strength=int(min_reversal_factor),
                            bar_index=candles[current_low_idx].bar_index,
                        )
                    )
                    last_pivot_is_high = False
                    current_high = candle.high_price
                    current_high_idx = i
                else:
                    # Update the high if reversal wasn't significant
                    current_high = candle.high_price
                    current_high_idx = i

        else:  # last_pivot_is_high is False
            # Looking for a high
            if candle.high_price > current_high:
                current_high = candle.high_price
                current_high_idx = i

            # Check for reversal to downside
            if candle.low_price < current_low:
                # Check if the up move was significant
                if current_high - pivots[-1].price >= min_reversal:
                    # Add the high pivot
                    pivots.append(
                        Pivot(
                            timestamp=candles[current_high_idx].close_time,
                            price=current_high,
                            is_high=True,
                            strength=int(min_reversal_factor),
                            bar_index=candles[current_high_idx].bar_index,
                        )
                    )
                    last_pivot_is_high = True
                    current_low = candle.low_price
                    current_low_idx = i
                else:
                    # Update the low if reversal wasn't significant
                    current_low = candle.low_price
                    current_low_idx = i

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
