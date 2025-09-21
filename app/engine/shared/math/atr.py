"""
Average True Range (ATR) calculation

Implements ATR using Wilder's smoothing method for volatility measurement.
"""

import numpy as np

from .ema import calculate_ema_wilder


def calculate_atr(
    high: np.ndarray,  # type: ignore[type-arg]
    low: np.ndarray,  # type: ignore[type-arg]
    close: np.ndarray,  # type: ignore[type-arg]
    period: int = 14
) -> np.ndarray:  # type: ignore[type-arg]
    """
    Calculate Average True Range (ATR).

    ATR measures volatility by considering the greatest of:
    - Current high minus current low
    - Absolute value of current high minus previous close
    - Absolute value of current low minus previous close

    Args:
        high: Array of high prices
        low: Array of low prices
        close: Array of close prices
        period: ATR period (default 14)

    Returns:
        Array of ATR values with same length as input.
        First 'period' values will be NaN.
    """
    if len(high) != len(low) or len(high) != len(close):
        raise ValueError("All price arrays must have the same length")

    if len(high) < period:
        return np.full_like(high, np.nan, dtype=np.float64)

    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")

    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)

    # Calculate True Range
    tr = calculate_true_range(high, low, close)

    # Calculate ATR using Wilder's smoothing
    atr = calculate_ema_wilder(tr, period)

    # Shift by 1 to align with candle timestamps
    # (TR[0] corresponds to the first candle, ATR[0] should be NaN)
    result = np.full_like(high, np.nan, dtype=np.float64)
    result[1:] = atr[:-1]
    result[period] = atr[period - 1]  # First valid ATR

    return result


def calculate_true_range(
    high: np.ndarray,  # type: ignore[type-arg]
    low: np.ndarray,  # type: ignore[type-arg]
    close: np.ndarray  # type: ignore[type-arg]
) -> np.ndarray:  # type: ignore[type-arg]
    """
    Calculate True Range for each period.

    True Range is the greatest of:
    - Current high minus current low
    - Absolute value of current high minus previous close
    - Absolute value of current low minus previous close

    Args:
        high: Array of high prices
        low: Array of low prices
        close: Array of close prices

    Returns:
        Array of true range values
    """
    if len(high) == 0:
        return np.array([], dtype=np.float64)

    tr = np.full(len(high), np.nan, dtype=np.float64)

    # First candle: TR = High - Low
    tr[0] = high[0] - low[0]

    # Subsequent candles: max of three calculations
    for i in range(1, len(high)):
        if np.isnan(high[i]) or np.isnan(low[i]) or np.isnan(close[i - 1]):
            tr[i] = np.nan
        else:
            hl = high[i] - low[i]  # High - Low
            hc = abs(high[i] - close[i - 1])  # |High - Previous Close|
            lc = abs(low[i] - close[i - 1])  # |Low - Previous Close|
            tr[i] = max(hl, hc, lc)

    return tr
