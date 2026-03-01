from __future__ import annotations

import numpy as np


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Vectorized True Range (TR).

    TR[0] = high[0] - low[0]
    TR[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    Returns an array of same shape as inputs (float64).
    """
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    n = close.shape[0]
    tr = np.zeros(n, dtype=np.float64)
    if n == 0:
        return tr

    # first element is simply high-low
    tr[0] = high[0] - low[0]

    if n > 1:
        prev_close = close[:-1]
        hl = high[1:] - low[1:]
        hc = np.abs(high[1:] - prev_close)
        lc = np.abs(low[1:] - prev_close)
        tr[1:] = np.maximum(hl, np.maximum(hc, lc))
    return tr


def atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int,
) -> np.ndarray:
    """Vectorized Average True Range using simple moving average over TR.

    Pads the first `period-1` values with 0 to preserve length.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    tr = true_range(high, low, close)
    n = tr.shape[0]
    out = np.zeros(n, dtype=np.float64)
    if n == 0:
        return out
    if n < period:
        # Not enough data; keep zeros (no legacy fallback)
        return out

    kernel = np.ones(period, dtype=np.float64) / float(period)
    valid = np.convolve(tr, kernel, mode="valid")
    out[period - 1 :] = valid
    return out
