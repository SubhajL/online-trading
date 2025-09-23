from __future__ import annotations

from decimal import Decimal

from ..models import Candle
from ..types import Pivot, PivotMethod, SwingType


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