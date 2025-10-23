from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

import numpy as np

from ..models import Candle


def to_float_ohlc_arrays(
    candles: Iterable[Candle],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert an iterable of Candle models to contiguous float64 OHLC arrays.

    Returns (open, high, low, close) arrays with dtype float64 and identical length.
    """
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for c in candles:
        # Convert Decimal to float explicitly; callers accept double precision rounding
        def f(x: Decimal | float) -> float:
            return float(x)  # no legacy fallback

        opens.append(f(c.open_price))
        highs.append(f(c.high_price))
        lows.append(f(c.low_price))
        closes.append(f(c.close_price))

    return (
        np.ascontiguousarray(opens, dtype=np.float64),
        np.ascontiguousarray(highs, dtype=np.float64),
        np.ascontiguousarray(lows, dtype=np.float64),
        np.ascontiguousarray(closes, dtype=np.float64),
    )
